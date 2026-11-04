"""Model zoo, chronological split, time-series CV, honest metrics."""
from __future__ import annotations

import io
import time

import joblib
import numpy as np
import pandas as pd
import psutil
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBRegressor
except Exception:  # pragma: no cover
    XGBRegressor = None
try:
    from lightgbm import LGBMRegressor
except Exception:  # pragma: no cover
    LGBMRegressor = None

SEED = 42


def model_zoo() -> dict:
    zoo = {
        "linear_regression": lambda: make_pipeline(StandardScaler(), LinearRegression()),
        "random_forest": lambda: RandomForestRegressor(n_estimators=80, max_depth=10, min_samples_leaf=5, n_jobs=-1, random_state=SEED),
        "gradient_boosting": lambda: GradientBoostingRegressor(n_estimators=120, learning_rate=0.05, max_depth=4, random_state=SEED),
        "hist_gradient_boosting": lambda: HistGradientBoostingRegressor(max_iter=200, learning_rate=0.08, random_state=SEED),
    }
    if XGBRegressor is not None:
        zoo["xgboost"] = lambda: XGBRegressor(n_estimators=200, max_depth=5, learning_rate=0.08, subsample=0.9,
                                              tree_method="hist", n_jobs=-1, random_state=SEED, verbosity=0)
    if LGBMRegressor is not None:
        zoo["lightgbm"] = lambda: LGBMRegressor(n_estimators=200, learning_rate=0.08, num_leaves=31, n_jobs=-1,
                                                random_state=SEED, verbose=-1)
    return zoo


def chronological_split(d: pd.DataFrame, test_frac: float = 0.2, time_col: str = "ts",
                        target_time_col: str | None = None):
    """Train rows must have ALL their information (incl. target time) before the split instant."""
    split_ts = d[time_col].sort_values().iloc[int(len(d) * (1 - test_frac))]
    tcol = target_time_col or time_col
    train = d[d[tcol] <= split_ts]
    test = d[d[time_col] > split_ts]
    return train, test, split_ts


def _metrics(y, p) -> dict:
    return {"mae": float(mean_absolute_error(y, p)),
            "rmse": float(np.sqrt(mean_squared_error(y, p))),
            "r2": float(r2_score(y, p))}


def evaluate_models(train: pd.DataFrame, test: pd.DataFrame, features: list[str], cv_splits: int = 3,
                    only: list[str] | None = None) -> tuple[list[dict], dict]:
    Xtr, ytr = train[features].to_numpy(), train["target"].to_numpy()
    Xte, yte = test[features].to_numpy(), test["target"].to_numpy()
    order = np.argsort(train["ts"].to_numpy())
    Xtr_o, ytr_o = Xtr[order], ytr[order]
    results, fitted = [], {}
    zoo = model_zoo()
    for name, make in zoo.items():
        if only and name not in only:
            continue
        cv_rmse = []
        for tr_idx, va_idx in TimeSeriesSplit(n_splits=cv_splits).split(Xtr_o):
            m = make().fit(Xtr_o[tr_idx], ytr_o[tr_idx])
            cv_rmse.append(float(np.sqrt(mean_squared_error(ytr_o[va_idx], m.predict(Xtr_o[va_idx])))))
        proc = psutil.Process()
        rss0 = proc.memory_info().rss
        t0 = time.perf_counter()
        model = make().fit(Xtr, ytr)
        train_s = time.perf_counter() - t0
        rss_delta = (proc.memory_info().rss - rss0) / 1e6
        t0 = time.perf_counter()
        pred = model.predict(Xte)
        lat_ms_per_1k = (time.perf_counter() - t0) / max(len(Xte), 1) * 1000 * 1000
        buf = io.BytesIO()
        joblib.dump(model, buf)
        r = {"model": name, **_metrics(yte, pred), "cv_rmse_mean": float(np.mean(cv_rmse)),
             "cv_rmse_std": float(np.std(cv_rmse)), "train_seconds": round(train_s, 3),
             "predict_ms_per_1000": round(lat_ms_per_1k, 3), "model_size_kb": round(buf.tell() / 1024, 1),
             "rss_delta_mb": round(rss_delta, 1)}
        results.append(r)
        fitted[name] = (model, pred)
    return results, fitted
