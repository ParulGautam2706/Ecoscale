"""Train energy / forecast models, pick the best by time-series CV RMSE, persist artifacts."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml import features as F
from app.ml.train import chronological_split, evaluate_models
from app.models.entities import ModelRun
from app.services.data import instance_specs, region_table, telemetry_df

PROXY_NOTE = ("Energy labels come from the configured power model, NOT from metered hardware. "
              "The model is a fast proxy estimator of that model; metrics measure agreement with it, "
              "not real-world accuracy.")
TARGETS = {"energy_wh": "Energy per interval (Wh, proxy label)", "cpu_forecast": "CPU utilization at +horizon (real forecast)"}


def _artifact_path(target: str) -> str:
    os.makedirs(settings.artifacts_dir, exist_ok=True)
    return os.path.join(settings.artifacts_dir, f"{target}_best.joblib")


def _prep(db: Session, horizon_steps: int):
    df = telemetry_df(db)
    if df.empty:
        raise ValueError("no telemetry available; seed or ingest data first")
    specs = instance_specs(db)
    regions = sorted(region_table(db))
    interval_s = float(df["interval_s"].median())
    return F.add_features(df, specs, regions, interval_s), regions, interval_s


def train_target(db: Session, target: str, horizon_steps: int = 12, only: list[str] | None = None,
                 cv_splits: int = 3) -> dict:
    if target not in TARGETS:
        raise ValueError(f"target must be one of {list(TARGETS)}")
    feat, regions, interval_s = _prep(db, horizon_steps)
    if target == "energy_wh":
        d, cols = F.build_energy_dataset(feat), F.ENERGY_FEATURES
        train, test, split_ts = chronological_split(d)
        baselines = {}
    else:
        d, cols = F.build_forecast_dataset(feat, horizon_steps, interval_s), F.FORECAST_FEATURES
        train, test, split_ts = chronological_split(d, target_time_col="target_ts")
        baselines = {}
        for b in ("persistence", "seasonal_naive"):
            p = test[b].to_numpy()
            y = test["target"].to_numpy()
            baselines[b] = {"mae": float(mean_absolute_error(y, p)),
                            "rmse": float(np.sqrt(mean_squared_error(y, p))), "r2": float(r2_score(y, p))}
    if len(train) < 200 or len(test) < 50:
        raise ValueError(f"not enough data to train (train={len(train)}, test={len(test)})")
    results, fitted = evaluate_models(train, test, cols, cv_splits=cv_splits, only=only)
    best = min(results, key=lambda r: r["cv_rmse_mean"])
    model, pred = fitted[best["model"]]
    resid = test["target"].to_numpy() - pred
    artifact = {"model": model, "features": cols, "target": target, "region_codes": regions,
                "horizon_steps": horizon_steps, "interval_s": interval_s, "model_name": best["model"],
                "residual_q05": float(np.quantile(resid, 0.05)), "residual_q95": float(np.quantile(resid, 0.95)),
                "trained_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), "split_ts": str(split_ts)}
    path = _artifact_path(target)
    joblib.dump(artifact, path)
    summary = {"split": "chronological", "split_ts": str(split_ts), "train_rows": int(len(train)),
               "test_rows": int(len(test)), "cv": f"TimeSeriesSplit(n_splits={cv_splits})",
               "selection_rule": "lowest mean time-series-CV RMSE on training period",
               "baselines": baselines, "all_models": results,
               "proxy_label_note": PROXY_NOTE if target == "energy_wh" else None,
               "features": cols, "horizon_steps": horizon_steps,
               "data_origins": sorted(set(telemetry_df(db).data_origin))}
    with open(os.path.join(settings.artifacts_dir, f"{target}_summary.json"), "w") as fh:
        json.dump({**summary, "best_model": best["model"], "trained_at": artifact["trained_at"]}, fh, default=str)
    runs = []
    for r in results:
        run = ModelRun(model_name=r["model"], target=target, split_strategy="chronological+TimeSeriesCV",
                       metrics={**r, "selected": r["model"] == best["model"]},
                       is_proxy_label=(target == "energy_wh"),
                       artifact_path=path if r["model"] == best["model"] else None)
        db.add(run)
        runs.append(run)
    db.commit()
    return {"target": target, "best_model": best["model"], "best_metrics_test": {k: best[k] for k in ("mae", "rmse", "r2")},
            "summary": summary, "artifact": path}


def load_summary(target: str) -> dict:
    path = os.path.join(settings.artifacts_dir, f"{target}_summary.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"no trained model for '{target}'; train first")
    with open(path) as fh:
        return json.load(fh)


def load_artifact(target: str) -> dict:
    path = _artifact_path(target)
    if not os.path.exists(path):
        raise FileNotFoundError(f"no trained model for '{target}'; train first")
    return joblib.load(path)


def forecast_resource(db: Session, resource_id: int) -> dict:
    art = load_artifact("cpu_forecast")
    df = telemetry_df(db, resource_ids=[resource_id])
    if df.empty:
        raise ValueError("no telemetry for resource")
    specs = instance_specs(db)
    feat = F.add_features(telemetry_df(db), specs, art["region_codes"], art["interval_s"])
    feat = feat[feat["resource_id"] == resource_id].dropna(subset=F.FORECAST_FEATURES)
    if feat.empty:
        raise ValueError("insufficient history for features")
    row = feat.iloc[[-1]]
    yhat = float(art["model"].predict(row[art["features"]].to_numpy())[0])
    lo, hi = yhat + art["residual_q05"], yhat + art["residual_q95"]
    horizon_min = art["horizon_steps"] * art["interval_s"] / 60
    return {"resource_id": resource_id, "as_of": str(row["ts"].iloc[0]), "horizon_minutes": horizon_min,
            "predicted_cpu_utilization": float(np.clip(yhat, 0, 1)),
            "interval_90": [float(np.clip(lo, 0, 1)), float(np.clip(hi, 0, 1))],
            "interval_method": "empirical 5-95% quantiles of held-out residuals",
            "model": art["model_name"], "origin": "predicted"}


def forecast_series(db: Session, resource_id: int, steps: int = 48) -> dict:
    """Walk-forward replay on recent history: predictions vs actuals for the chart."""
    art = load_artifact("cpu_forecast")
    specs = instance_specs(db)
    feat = F.add_features(telemetry_df(db), specs, art["region_codes"], art["interval_s"])
    d = F.build_forecast_dataset(feat, art["horizon_steps"], art["interval_s"])
    d = d[d["resource_id"] == resource_id].tail(steps)
    if d.empty:
        raise ValueError("insufficient data")
    pred = art["model"].predict(d[art["features"]].to_numpy())
    return {"points": [{"target_ts": str(t), "actual": float(a), "predicted": float(np.clip(p, 0, 1)),
                        "lower": float(np.clip(p + art["residual_q05"], 0, 1)),
                        "upper": float(np.clip(p + art["residual_q95"], 0, 1))}
                       for t, a, p in zip(d["target_ts"], d["target"], pred)],
            "note": "Replay of recent history using the trained model (some rows may be in the training period).",
            "model": art["model_name"], "origin": "predicted"}


def predict_energy_wh(db: Session, payload: dict) -> dict:
    art = load_artifact("energy_wh")
    specs = instance_specs(db)
    spec = specs[payload["instance_type"]]
    cpu = payload["cpu"]
    row = {"cpu": cpu, "mem": payload["mem"], "gpu": payload.get("gpu", 0.0), "net_mbit_s": payload.get("net_mbit_s", 0.0),
           "disk_mb_s": payload.get("disk_mb_s", 0.0), "vcpu": spec.vcpu, "mem_gb": spec.mem_gb, "idle_w": spec.idle_w,
           "peak_w": spec.peak_w, "gpu_count": spec.gpu_count, "hour": payload.get("hour", 12), "dow": payload.get("dow", 2),
           "region_idx": art["region_codes"].index(payload["region_code"]) if payload["region_code"] in art["region_codes"] else -1,
           "cpu_x_mem": cpu * payload["mem"], "cpu_lag1": payload.get("cpu_prev", cpu),
           "cpu_roll6": payload.get("cpu_prev", cpu), "cpu_roll6_std": 0.0}
    x = np.array([[row[f] for f in art["features"]]])
    wh = float(art["model"].predict(x)[0])
    return {"predicted_facility_wh_per_interval": wh, "model": art["model_name"], "origin": "predicted",
            "label_note": PROXY_NOTE}


def list_runs(db: Session, target: str | None = None) -> list[dict]:
    q = db.query(ModelRun).order_by(ModelRun.created_at.desc(), ModelRun.id.desc())
    if target:
        q = q.filter(ModelRun.target == target)
    return [{"id": r.id, "model": r.model_name, "target": r.target, "split": r.split_strategy, "metrics": r.metrics,
             "proxy_label": r.is_proxy_label, "created_at": str(r.created_at)} for r in q.limit(60).all()]
