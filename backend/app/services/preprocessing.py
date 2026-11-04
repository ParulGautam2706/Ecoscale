"""Validation, imputation and outlier capping (IQR) for telemetry. Trees need no scaling,
so scaling is applied only inside pipelines of linear models."""
from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED = ["ts", "cpu", "mem"]
NUMERIC = ["cpu", "mem", "gpu", "net_mbit_s", "disk_mb_s"]


def validate_and_clean(df: pd.DataFrame, max_missing_frac: float = 0.30) -> tuple[pd.DataFrame, dict]:
    report = {"rows_in": int(len(df)), "dropped_missing": 0, "imputed_cells": 0, "capped_cells": 0}
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)
    cols = [c for c in NUMERIC if c in df.columns]
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    frac = df[cols].isna().mean(axis=1)
    keep = frac <= max_missing_frac
    report["dropped_missing"] = int((~keep).sum())
    df = df[keep].copy()
    for c in cols:
        n = int(df[c].isna().sum())
        if n:
            df[c] = df[c].fillna(df[c].median())
            report["imputed_cells"] += n
    for c in cols:                               # IQR capping (1.5x), as in the reference paper
        q1, q3 = df[c].quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        if c in ("cpu", "mem", "gpu"):
            lo, hi = max(lo, 0.0), min(max(hi, df[c].max() if iqr == 0 else hi), 1.0)
        if iqr > 0:
            capped = int(((df[c] < lo) | (df[c] > hi)).sum())
            df[c] = df[c].clip(lo, hi)
            report["capped_cells"] += capped
    report["rows_out"] = int(len(df))
    return df.sort_values("ts").reset_index(drop=True), report
