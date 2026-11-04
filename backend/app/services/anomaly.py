"""Isolation Forest anomaly detection with false-positive controls:
 (1) per-resource model with low contamination, (2) robust z-score confirmation, (3) event merging."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler
from sqlalchemy.orm import Session

from app.models.entities import Anomaly
from app.services.data import telemetry_df

METRICS = ["cpu", "mem", "net_mbit_s", "disk_mb_s", "energy_wh"]
# Minimum "meaningful change" per metric: stops constant/idle series (tiny MAD) from alerting on noise.
FLOORS = {"cpu": 0.05, "mem": 0.05, "net_mbit_s": 2.0, "disk_mb_s": 1.0, "energy_wh": 0.05}
STEPS = {
    "cpu": ["Check deploys/cron jobs around the timestamp", "Inspect top processes and request volume", "Compare with the same hour on previous days"],
    "mem": ["Look for leaks or cache growth", "Check recent releases and container limits"],
    "net_mbit_s": ["Inspect traffic sources / possible scan or exfiltration", "Check backup or replication jobs"],
    "disk_mb_s": ["Check batch exports, logging bursts or runaway writers"],
    "energy_wh": ["Energy rose beyond what utilization alone explains; verify the power model inputs and hardware state"],
}


def detect_frame(df: pd.DataFrame, contamination: float | str = "auto", z_min: float = 3.5, merge_gap: int = 3,
                 seed: int = 42) -> pd.DataFrame:
    """df: one resource, sorted by ts. Returns merged events."""
    d = df.sort_values("ts").reset_index(drop=True).copy()
    d["energy_wh"] = d["facility_kwh"] * 1000.0
    for c in ("net_mbit_s", "disk_mb_s"):
        d[c] = d[c].fillna(0.0)
    if len(d) < 100:
        return pd.DataFrame(columns=["ts", "metric", "severity", "score", "z"])
    X = RobustScaler().fit_transform(d[METRICS].to_numpy())
    iso = IsolationForest(n_estimators=200, contamination=contamination, random_state=seed).fit(X)
    d["score"] = -iso.score_samples(X)
    d["flag"] = iso.predict(X) == -1
    z = {}
    hour = d["ts"].dt.hour
    for m in METRICS:
        med = d.groupby(hour)[m].transform("median")           # seasonal (hour-of-day) baseline
        mad = 1.4826 * (d[m] - med).abs().groupby(hour).transform("median")
        scale = np.maximum(np.maximum(mad, 0.05 * med.abs()), FLOORS[m])
        z[m] = (d[m] - med) / scale
    zdf = pd.DataFrame(z)
    d["z"] = zdf.abs().max(axis=1)
    d["metric"] = zdf.abs().idxmax(axis=1)
    cand = d[d["flag"] & (d["z"] >= z_min)]          # confirmation step cuts false positives
    events, last_i, cur = [], None, None
    for i, r in cand.iterrows():
        if last_i is not None and i - last_i <= merge_gap:
            if r["score"] > cur["score"]:
                cur = r
        else:
            if cur is not None:
                events.append(cur)
            cur = r
        last_i = i
    if cur is not None:
        events.append(cur)
    out = pd.DataFrame(events)
    if out.empty:
        return pd.DataFrame(columns=["ts", "metric", "severity", "score", "z"])
    out["severity"] = np.where(out["z"] >= 8, "high", np.where(out["z"] >= 5, "medium", "low"))
    return out[["ts", "metric", "severity", "score", "z"]]


def detect(db: Session, contamination: float | str | None = "auto", z_min: float = 3.5, resource_id: int | None = None) -> dict:
    contamination = "auto" if contamination is None else contamination
    df = telemetry_df(db, resource_ids=[resource_id] if resource_id else None)
    if df.empty:
        raise ValueError("no telemetry")
    q = db.query(Anomaly)
    if resource_id:
        q = q.filter(Anomaly.resource_id == resource_id)
    q.delete()
    total = 0
    for rid, sub in df.groupby("resource_id"):
        ev = detect_frame(sub, contamination, z_min)
        for r in ev.itertuples():
            db.add(Anomaly(resource_id=int(rid), ts=pd.Timestamp(r.ts).to_pydatetime(), metric=r.metric,
                           severity=r.severity, score=float(r.score)))
            total += 1
    db.commit()
    return {"events": total, "contamination": contamination, "z_min": z_min,
            "method": "IsolationForest + robust z-score confirmation + event merging", "origin": "estimated"}


def investigation_steps(metric: str) -> list[str]:
    return STEPS.get(metric, ["Review telemetry around the timestamp"])
