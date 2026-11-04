"""Carbon-intensity access. DB-backed provider + pluggable external adapter.
Forecasting = hour-of-day profile (seasonal mean) - a simple, testable method."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.entities import CarbonIntensity


class ExternalCarbonAdapter:
    """Placeholder adapter for APIs such as ElectricityMaps / WattTime (paid or key-gated).
    Implement `fetch(region, start, end)` returning (timestamp, g_per_kwh) rows; disabled by default."""
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url, self.api_key = base_url, api_key

    def fetch(self, region, start, end):
        raise NotImplementedError("External carbon API not configured; using cached/sample data.")


class CarbonProvider:
    def __init__(self, db: Session):
        self.db = db
        self._cache: dict[str, pd.Series] = {}

    def series(self, region: str) -> pd.Series:
        if region not in self._cache:
            rows = (self.db.query(CarbonIntensity.timestamp, CarbonIntensity.g_per_kwh)
                    .filter(CarbonIntensity.region_code == region).order_by(CarbonIntensity.timestamp).all())
            s = pd.Series([r[1] for r in rows], index=pd.to_datetime([r[0] for r in rows]), dtype=float)
            self._cache[region] = s
        return self._cache[region]

    def regions(self) -> list[str]:
        return [r[0] for r in self.db.query(CarbonIntensity.region_code).distinct().all()]

    def profile(self, region: str) -> np.ndarray:
        """Mean intensity per UTC hour-of-day (24,) from available history."""
        s = self.series(region)
        if s.empty:
            return np.full(24, 400.0)
        prof = s.groupby(s.index.hour).mean().reindex(range(24))
        return prof.interpolate(limit_direction="both").to_numpy()

    def daily_mean(self, region: str) -> float:
        return float(self.profile(region).mean())

    def window_mean(self, region: str, start_hour_utc: float, hours: float) -> float:
        """Mean forecast intensity for a window beginning at start_hour_utc (circular over 24h)."""
        prof = self.profile(region)
        n = max(1, int(math.ceil(hours)))
        idx = [(int(math.floor(start_hour_utc)) + k) % 24 for k in range(n)]
        return float(prof[idx].mean())

    def at(self, region: str, ts: datetime) -> float:
        s = self.series(region)
        t = pd.Timestamp(ts)
        if not s.empty and s.index[0] <= t <= s.index[-1] + pd.Timedelta(hours=1):
            i = s.index.searchsorted(t, side="right") - 1
            return float(s.iloc[max(i, 0)])
        return float(self.profile(region)[t.hour])

    def forecast(self, region: str, hours: int = 48) -> pd.DataFrame:
        s = self.series(region)
        if s.empty:
            return pd.DataFrame(columns=["timestamp", "g_per_kwh", "method"])
        start = s.index[-1] + pd.Timedelta(hours=1)
        ts = [start + pd.Timedelta(hours=h) for h in range(hours)]
        enough = len(s) >= 48
        prof = self.profile(region)
        vals = [prof[t.hour] if enough else float(s.mean()) for t in ts]
        return pd.DataFrame({"timestamp": ts, "g_per_kwh": vals,
                             "method": "forecast_hour_of_day_profile" if enough else "forecast_flat_mean"})

    def backtest(self, region: str, holdout_hours: int = 24) -> dict:
        """Honest accuracy check of the profile forecaster on the last `holdout_hours`."""
        s = self.series(region)
        if len(s) < 48 + holdout_hours:
            return {"region": region, "mae": None, "note": "insufficient history"}
        train, test = s.iloc[:-holdout_hours], s.iloc[-holdout_hours:]
        prof = train.groupby(train.index.hour).mean()
        pred = np.array([prof.get(t.hour, train.mean()) for t in test.index])
        mae = float(np.mean(np.abs(pred - test.to_numpy())))
        naive = float(np.mean(np.abs(train.iloc[-1] - test.to_numpy())))
        return {"region": region, "mae_g_per_kwh": round(mae, 2), "naive_last_value_mae": round(naive, 2),
                "holdout_hours": holdout_hours}
