"""Telemetry ingestion: validate -> store sample -> estimate energy -> update Prometheus."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.entities import DataOrigin, EnergyEstimate, Resource, TelemetrySample
from app.monitoring import prometheus
from app.services import settings_service
from app.services.carbon import CarbonProvider
from app.services.data import instance_specs, region_table
from app.services.energy import EnergyConfig, estimate_frame


def ingest_frame(db: Session, resource_id: int, df: pd.DataFrame, origin: str,
                 interval_s: float | None = None) -> dict:
    """df columns: ts, cpu, mem, [gpu, net_mbit_s, disk_mb_s, interval_s]. Returns counts."""
    if origin not in ("measured", "simulated"):
        raise ValueError("telemetry origin must be 'measured' or 'simulated'")
    res = db.get(Resource, resource_id)
    if res is None:
        raise ValueError("unknown resource")
    df = df.copy()
    if "interval_s" not in df:
        df["interval_s"] = interval_s or 60.0
    for c in ("gpu", "net_mbit_s", "disk_mb_s"):
        if c not in df:
            df[c] = np.nan
    cfg = EnergyConfig.from_dict(settings_service.get_all(db)["energy"])
    carbon = CarbonProvider(db)
    prof = carbon.profile(res.region_code)
    df["ci_g_per_kwh"] = [carbon.at(res.region_code, t) if len(carbon.series(res.region_code)) else prof[pd.Timestamp(t).hour]
                          for t in df["ts"]]
    df["instance_type"], df["region_code"] = res.instance_type, res.region_code
    est = estimate_frame(df.assign(gpu=df["gpu"], ), instance_specs(db), {k: v["pue"] for k, v in region_table(db).items()}, cfg)
    origin_enum = DataOrigin(origin)
    rows = []
    for r in df.itertuples(index=False):
        rows.append(TelemetrySample(resource_id=resource_id, ts=pd.Timestamp(r.ts).to_pydatetime(),
                                    interval_s=float(r.interval_s), cpu=float(r.cpu), mem=float(r.mem),
                                    gpu=None if pd.isna(r.gpu) else float(r.gpu),
                                    net_mbit_s=None if pd.isna(r.net_mbit_s) else float(r.net_mbit_s),
                                    disk_mb_s=None if pd.isna(r.disk_mb_s) else float(r.disk_mb_s),
                                    data_origin=origin_enum))
    db.add_all(rows)
    db.flush()
    conf_cache = {}
    ests = []
    for sample, e in zip(rows, est.itertuples(index=False)):
        has_net, has_disk = sample.net_mbit_s is not None, sample.disk_mb_s is not None
        key = (has_net, has_disk)
        if key not in conf_cache:
            from app.services.energy import confidence_score
            conf_cache[key] = confidence_score(utilization_origin=origin, has_net=has_net, has_disk=has_disk,
                                               calibrated=cfg.calibrated, measured_power=False)
        ests.append(EnergyEstimate(sample_id=sample.id, it_kwh=float(e.it_kwh), facility_kwh=float(e.facility_kwh),
                                   co2e_kg=float(e.co2e_kg), confidence=conf_cache[key],
                                   method=DataOrigin.estimated, assumptions={"ci_g_per_kwh": float(e.ci_g_per_kwh)}))
    db.add_all(ests)
    db.commit()
    last = est.iloc[-1]
    prometheus.observe(res.name, res.region_code, origin, float(last.cpu), float(last.mem), float(last.it_power_w),
                       float(est["facility_kwh"].sum()), float(est["co2e_kg"].sum()))
    return {"samples": len(rows), "origin": origin, "energy_method": "estimated"}
