"""Synthetic telemetry generator. EVERYTHING produced here is labelled data_origin='simulated'.
Profiles are hand-designed shapes, not real workloads."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.defaults import REGIONS

_TZ = {r[0]: r[6] for r in REGIONS}


def _diurnal(ts: pd.DatetimeIndex, tz: float) -> np.ndarray:
    h = (ts.hour + ts.minute / 60 + tz) % 24
    return 0.5 * (1 + np.sin(2 * np.pi * (h - 9) / 24))  # peaks ~15:00 local


def generate_workload(profile: str, start, periods: int, interval_s: int, region: str,
                      rng: np.random.Generator, inject_anomalies: bool = False) -> pd.DataFrame:
    ts = pd.date_range(start, periods=periods, freq=f"{interval_s}s")
    d = _diurnal(ts, _TZ.get(region, 0.0))
    n = rng.normal(0, 1, periods)
    gpu = None
    if profile == "web":
        cpu = 0.18 + 0.30 * d + 0.03 * n
        mem = 0.45 + 0.08 * d + 0.01 * rng.normal(size=periods)
        net, disk = 40 + 120 * d + 4 * n, 5 + 12 * d + rng.normal(0, 0.5, periods)
    elif profile == "overprovisioned":
        cpu = 0.05 + 0.05 * d + 0.01 * n
        mem = 0.15 + 0.03 * d + 0.005 * rng.normal(size=periods)
        net, disk = 3 + 6 * d + 0.3 * n, 1 + 1.5 * d + rng.normal(0, 0.1, periods)
    elif profile == "idle":
        cpu = 0.006 + 0.004 * np.abs(n)
        mem = 0.08 + 0.004 * rng.normal(size=periods)
        net, disk = 0.2 + 0.1 * np.abs(n), 0.05 + 0.02 * np.abs(rng.normal(size=periods))
    elif profile == "batch":
        local_h = (ts.hour + _TZ.get(region, 0.0)) % 24
        active = ((local_h >= 1) & (local_h < 4)).astype(float)   # ~3h nightly job
        cpu = 0.03 + 0.80 * active + 0.03 * n * active
        mem = 0.10 + 0.55 * active + 0.01 * rng.normal(size=periods)
        net, disk = 2 + 150 * active + 3 * n * active, 1 + 90 * active
    elif profile == "gpu_ml":
        local_h = (ts.hour + _TZ.get(region, 0.0)) % 24
        active = ((local_h >= 20) | (local_h < 4)).astype(float)   # ~8h training window
        cpu = 0.05 + 0.45 * active + 0.02 * n * active
        mem = 0.20 + 0.45 * active + 0.01 * rng.normal(size=periods)
        gpu = 0.02 + 0.80 * active + 0.03 * n * active
        net, disk = 5 + 30 * active, 2 + 60 * active
    else:
        raise ValueError(f"unknown profile {profile}")
    df = pd.DataFrame({"ts": ts, "cpu": cpu, "mem": mem, "net_mbit_s": net, "disk_mb_s": disk})
    if gpu is not None:
        df["gpu"] = gpu
    df["injected_anomaly"] = False
    if inject_anomalies and periods > 200:
        for pos in rng.choice(np.arange(100, periods - 10), size=6, replace=False):
            df.loc[pos:pos + 2, "cpu"] = 0.98
            df.loc[pos:pos + 2, "net_mbit_s"] = df["net_mbit_s"].max() * 4
            df.loc[pos:pos + 2, "injected_anomaly"] = True
    for c in ("cpu", "mem"):
        df[c] = df[c].clip(0.0, 1.0)
    if "gpu" in df:
        df["gpu"] = df["gpu"].clip(0.0, 1.0)
    for c in ("net_mbit_s", "disk_mb_s"):
        df[c] = df[c].clip(lower=0.0)
    return df


def generate_carbon_intensity(start, hours: int, rng: np.random.Generator) -> pd.DataFrame:
    """Illustrative synthetic grid intensity (NOT real data). Replace via the CSV/API adapters."""
    ts = pd.date_range(start, periods=hours, freq="1h")
    rows = []
    for code, _n, _p, _m, base, amp, tz in REGIONS:
        h = (ts.hour + tz) % 24
        ci = base * (1 + amp * np.cos(2 * np.pi * (h - 19) / 24)) * (1 + 0.03 * rng.normal(size=hours))
        rows.append(pd.DataFrame({"region_code": code, "timestamp": ts, "g_per_kwh": np.maximum(ci, 5.0)}))
    return pd.concat(rows, ignore_index=True)
