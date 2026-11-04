"""Feature engineering. All lag/rolling features use ONLY past data (shift before roll)."""
from __future__ import annotations

import numpy as np
import pandas as pd

ENERGY_FEATURES = ["cpu", "mem", "gpu", "net_mbit_s", "disk_mb_s", "vcpu", "mem_gb", "idle_w", "peak_w",
                   "gpu_count", "hour", "dow", "region_idx", "cpu_x_mem", "cpu_lag1", "cpu_roll6", "cpu_roll6_std"]
FORECAST_FEATURES = ["cpu", "mem", "net_mbit_s", "disk_mb_s", "gpu", "vcpu", "mem_gb", "hour", "dow", "region_idx",
                     "cpu_x_mem", "cpu_lag1", "cpu_lag2", "cpu_lag3", "cpu_lag6", "cpu_roll6", "cpu_roll12",
                     "cpu_roll6_std", "cpu_lag_day", "cpu_delta1"]


def add_features(df: pd.DataFrame, specs: dict, region_codes: list[str], interval_s: float) -> pd.DataFrame:
    df = df.sort_values(["resource_id", "ts"]).copy()
    for c in ("gpu", "net_mbit_s", "disk_mb_s"):
        df[c] = df[c].fillna(0.0)
    df["vcpu"] = df["instance_type"].map(lambda n: specs[n].vcpu)
    df["mem_gb"] = df["instance_type"].map(lambda n: specs[n].mem_gb)
    df["idle_w"] = df["instance_type"].map(lambda n: specs[n].idle_w)
    df["peak_w"] = df["instance_type"].map(lambda n: specs[n].peak_w)
    df["gpu_count"] = df["instance_type"].map(lambda n: specs[n].gpu_count)
    df["hour"], df["dow"] = df["ts"].dt.hour, df["ts"].dt.day_of_week
    df["region_idx"] = df["region_code"].map({c: i for i, c in enumerate(region_codes)}).fillna(-1).astype(int)
    df["cpu_x_mem"] = df["cpu"] * df["mem"]
    g = df.groupby("resource_id")["cpu"]
    for k in (1, 2, 3, 6):
        df[f"cpu_lag{k}"] = g.shift(k)
    past = g.shift(1)
    df["cpu_roll6"] = past.groupby(df["resource_id"]).transform(lambda s: s.rolling(6, min_periods=1).mean())
    df["cpu_roll12"] = past.groupby(df["resource_id"]).transform(lambda s: s.rolling(12, min_periods=1).mean())
    df["cpu_roll6_std"] = past.groupby(df["resource_id"]).transform(lambda s: s.rolling(6, min_periods=2).std())
    day_steps = int(round(86400 / interval_s))
    df["cpu_lag_day"] = g.shift(day_steps)
    df["cpu_delta1"] = df["cpu"] - df["cpu_lag1"]
    return df


def build_energy_dataset(df: pd.DataFrame) -> pd.DataFrame:
    d = df.dropna(subset=["cpu_lag1", "cpu_roll6", "cpu_roll6_std", "facility_kwh"]).copy()
    d["target"] = d["facility_kwh"] * 1000.0          # Wh per interval (PROXY label from the power model)
    return d


def build_forecast_dataset(df: pd.DataFrame, horizon_steps: int, interval_s: float) -> pd.DataFrame:
    d = df.copy()
    d["target"] = d.groupby("resource_id")["cpu"].shift(-horizon_steps)
    d["target_ts"] = d["ts"] + pd.to_timedelta(horizon_steps * interval_s, unit="s")
    day_steps = int(round(86400 / interval_s))
    d["seasonal_naive"] = d.groupby("resource_id")["cpu"].shift(day_steps - horizon_steps)
    d["persistence"] = d["cpu"]
    return d.dropna(subset=FORECAST_FEATURES + ["target"])
