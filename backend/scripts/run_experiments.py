"""Reproducible experiments. Writes research/results.json and research/results.md.
All data is SIMULATED (fixed seed); all numbers below are computed here, never typed in.
Usage:  python scripts/run_experiments.py [--days 7] [--interval 300] [--seed 42] [--fast]"""
import argparse
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.config import settings
from app.database.session import Base
from app.ml import pipeline
from app.optimization import recommender
from app.optimization.evaluate import load_profiles, make_ctx
from app.optimization.multiobjective import tradeoff_table
from app.services import anomaly
from app.services.carbon import CarbonProvider
from app.services.data import instance_specs, region_table, telemetry_df
from app.services.energy import estimate, paper_baseline_energy_kwh
from app.services.seed import FLEET, seed
from app.services.simulator import generate_workload


def pct(a, b):
    return round(100 * (a - b) / b, 2) if b else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fast", action="store_true", help="fewer models (for smoke runs)")
    a = ap.parse_args()
    settings.artifacts_dir = tempfile.mkdtemp()
    e = create_engine("sqlite://")
    Base.metadata.create_all(e)
    db = sessionmaker(bind=e)()
    R: dict = {"config": vars(a), "data_origin": "simulated (synthetic profiles; illustrative carbon intensity)"}
    t0 = time.time()
    R["seed"] = seed(db, a.days, a.interval, a.seed, end="2026-10-30")
    df = telemetry_df(db)
    specs, regs = instance_specs(db), region_table(db)

    # 1) Energy/carbon: original (paper, formula corrected) vs improved estimator, same telemetry
    base_kwh = paper_baseline_energy_kwh(df["cpu"], df["interval_s"], df["instance_type"].map(lambda n: specs[n].mem_gb))
    ci = df["co2e_kg"] / df["facility_kwh"].replace(0, np.nan)          # g/kWh*1e-3 -> effective factor per sample
    base_co2 = base_kwh * ci.fillna(ci.mean())
    per = df.assign(base_kwh=base_kwh, base_co2=base_co2).groupby("resource").agg(
        paper_baseline_kwh=("base_kwh", "sum"), improved_kwh=("facility_kwh", "sum"),
        paper_baseline_co2e_kg=("base_co2", "sum"), improved_co2e_kg=("co2e_kg", "sum")).round(3)
    R["estimation_comparison"] = {
        "note": "No metered ground truth exists, so neither is 'correct'; this shows how much the richer model changes the estimate.",
        "total_paper_baseline_kwh": round(float(base_kwh.sum()), 2), "total_improved_kwh": round(float(df["facility_kwh"].sum()), 2),
        "difference_pct": pct(float(df["facility_kwh"].sum()), float(base_kwh.sum())), "per_resource": per.reset_index().to_dict("records")}

    # 2) ML
    only = ["linear_regression", "hist_gradient_boosting", "xgboost", "lightgbm"] if a.fast else None
    ml = {}
    for tgt in ("cpu_forecast", "energy_wh"):
        r = pipeline.train_target(db, tgt, 12, only)
        s = r["summary"]
        ml[tgt] = {"best_model": r["best_model"], "train_rows": s["train_rows"], "test_rows": s["test_rows"], "split_ts": s["split_ts"],
                   "baselines": s["baselines"], "models": s["all_models"], "proxy_label_note": s["proxy_label_note"]}
        if tgt == "cpu_forecast":
            best = next(m for m in s["all_models"] if m["model"] == r["best_model"])
            ml[tgt]["rmse_improvement_vs_persistence_pct"] = pct(best["rmse"], s["baselines"]["persistence"]["rmse"])
            ml[tgt]["rmse_improvement_vs_seasonal_naive_pct"] = pct(best["rmse"], s["baselines"]["seasonal_naive"]["rmse"])
    R["ml"] = ml

    # 3) Optimization
    ctx = make_ctx(db)
    prof = load_profiles(db, ctx)
    R["recommendations"] = recommender.generate(db)
    from app.models.entities import Recommendation
    R["recommendation_list"] = [{"resource": prof[r.resource_id].name, "type": r.rec_type, "risk": r.risk, "priority": r.explanation.get("priority"),
                                 "co2e_pct": r.savings["co2e_kg_pct"], "cost_pct": r.savings["cost_usd_pct"],
                                 "co2e_kg_month": r.savings["co2e_kg_month"], "cost_usd_month": r.savings["cost_usd_month"],
                                 "confidence": r.explanation["confidence"]} for r in db.query(Recommendation).all()]
    from app.services.analytics import before_after
    R["before_after"] = before_after(db)
    R["tradeoffs"] = tradeoff_table(prof, ctx)

    # 4) Carbon-intensity forecast backtest
    cp = CarbonProvider(db)
    R["ci_forecast_backtest"] = [cp.backtest(r, 24) for r in sorted(cp.regions())]

    # 5) Anomaly detection against INJECTED anomalies (event-level)
    rng = np.random.default_rng(a.seed + 1)
    tp = fn = fp = 0
    start = pd.Timestamp("2026-10-23")
    for name, region, inst, profile, *_ in FLEET:
        w = generate_workload(profile, start, int(a.days * 86400 / a.interval), a.interval, region, rng, inject_anomalies=True)
        sp = specs[inst]
        res = estimate(sp, w["cpu"].to_numpy(), w["mem"].to_numpy(), a.interval, 300.0, gpu=w["gpu"].to_numpy() if "gpu" in w else None,
                       net_mbit_s=w["net_mbit_s"].to_numpy(), disk_mb_s=w["disk_mb_s"].to_numpy(), pue=1.2)
        w["facility_kwh"] = res.facility_kwh
        w["resource_id"] = 1
        ev = anomaly.detect_frame(w)
        inj = w["injected_anomaly"].to_numpy()
        runs, i = [], 0
        while i < len(inj):
            if inj[i]:
                j = i
                while j + 1 < len(inj) and inj[j + 1]:
                    j += 1
                runs.append((w["ts"].iloc[i], w["ts"].iloc[j]))
                i = j + 1
            else:
                i += 1
        pad = pd.Timedelta(seconds=a.interval * 3)
        hit = [False] * len(runs)
        for t in ev["ts"]:
            m = [k for k, (s_, e_) in enumerate(runs) if s_ - pad <= t <= e_ + pad]
            if m:
                hit[m[0]] = True
            else:
                fp += 1
        tp += sum(hit)
        fn += len(hit) - sum(hit)
    R["anomaly"] = {"injected_events": tp + fn, "detected": tp, "missed": fn, "false_alarms": fp,
                    "recall": round(tp / max(tp + fn, 1), 3), "precision": round(tp / max(tp + fp, 1), 3),
                    "note": "Injected CPU/network spikes in synthetic data; real-world precision/recall will differ."}
    R["runtime_seconds"] = round(time.time() - t0, 1)

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "research")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "results.json"), "w") as fh:
        json.dump(R, fh, indent=2, default=str)
    with open(os.path.join(out_dir, "results.md"), "w") as fh:
        fh.write(render_md(R))
    print(f"done in {R['runtime_seconds']}s -> {out_dir}")


def table(rows, cols):
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(f"{r[c]:.4g}" if isinstance(r[c], float) else str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def render_md(R):
    L = ["# Experimental results (auto-generated)", "",
         f"Data: **{R['data_origin']}**. Config: {R['config']}. Samples: {R['seed']['samples']}, resources: {R['seed']['resources']}.",
         "All values are computed by `backend/scripts/run_experiments.py`.", ""]
    ec = R["estimation_comparison"]
    L += ["## 1. Original (paper, corrected) vs improved energy estimation", ec["note"], "",
          f"Total paper-baseline energy: {ec['total_paper_baseline_kwh']} kWh; improved estimator (with RAM/GPU/storage/network/PUE): "
          f"{ec['total_improved_kwh']} kWh ({ec['difference_pct']:+}%).", "",
          table(ec["per_resource"], ["resource", "paper_baseline_kwh", "improved_kwh", "paper_baseline_co2e_kg", "improved_co2e_kg"]), ""]
    for tgt, title in (("cpu_forecast", "CPU utilization forecast (+60 min) - genuine forecasting target"),
                       ("energy_wh", "Energy per interval - PROXY target (labels derived from the power model)")):
        m = R["ml"][tgt]
        L += [f"## 2. ML: {title}", f"Chronological split at {m['split_ts']} (train {m['train_rows']}, test {m['test_rows']}). Best by CV RMSE: **{m['best_model']}**.", ""]
        if m["baselines"]:
            L += ["Baselines on the same test rows: " + "; ".join(f"{k}: RMSE {v['rmse']:.4f}, MAE {v['mae']:.4f}, R2 {v['r2']:.3f}" for k, v in m["baselines"].items()),
                  f"Best model RMSE vs persistence: {m['rmse_improvement_vs_persistence_pct']}%, vs seasonal-naive: {m['rmse_improvement_vs_seasonal_naive_pct']}% (negative = better).", ""]
        if m["proxy_label_note"]:
            L += [f"> {m['proxy_label_note']}", ""]
        L += [table(m["models"], ["model", "mae", "rmse", "r2", "cv_rmse_mean", "train_seconds", "predict_ms_per_1000", "model_size_kb"]), ""]
    ba = R["before_after"]
    L += ["## 3. Optimization (advisory, estimated)", f"Recommendations: {R['recommendations']['by_type']}.", "",
          f"Baseline per day: {ba['baseline_per_day']}; if all non-rejected applied: {ba['after_per_day']}; reduction %: {ba['reduction_pct']}.", "",
          table(R["recommendation_list"], ["resource", "type", "risk", "priority", "co2e_pct", "cost_pct", "co2e_kg_month", "cost_usd_month", "confidence"]), "",
          "### Trade-offs by weight preset (fleet, per day)", ""]
    rows = [{"preset": t["preset"], "co2e_%": t["delta_pct"]["co2e_kg_day"], "energy_%": t["delta_pct"]["energy_kwh_day"], "cost_%": t["delta_pct"]["cost_usd_day"],
             "latency_ms_abs": t["delta_abs"]["mean_latency_ms"], "sla_risk_abs": t["delta_abs"]["mean_sla_risk"], "changed": t["changed_workloads"]} for t in R["tradeoffs"]]
    L += [table(rows, list(rows[0])), "", "## 4. Carbon-intensity forecast backtest (hour-of-day profile, 24h hold-out)", "",
          table(R["ci_forecast_backtest"], ["region", "mae_g_per_kwh", "naive_last_value_mae"]), "",
          "## 5. Anomaly detection vs injected anomalies", f"{R['anomaly']}", "", f"Total runtime: {R['runtime_seconds']} s."]
    return "\n".join(L)


if __name__ == "__main__":
    main()
