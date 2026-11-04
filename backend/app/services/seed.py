"""Seeds regions, instance types, sample carbon intensity, resources and SIMULATED telemetry."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.defaults import INSTANCE_TYPES, REGIONS
from app.models.entities import (Anomaly, CarbonIntensity, EnergyEstimate, InstanceType, Prediction,
                                 Recommendation, Region, Resource, TelemetrySample)
from app.services.ingestion import ingest_frame
from app.services.simulator import generate_carbon_intensity, generate_workload

# name, region, instance, profile, flexible, deadline_h, sla_ms
FLEET = [
    ("web-frontend-1", "us-east", "gp.large", "web", False, None, 120),
    ("web-frontend-2", "us-east", "gp.large", "web", False, None, 120),
    ("api-service", "eu-west", "gp.xlarge", "web", False, None, 150),
    ("legacy-reporting", "us-east", "gp.xlarge", "overprovisioned", False, None, 200),
    ("staging-db", "eu-west", "gp.large", "overprovisioned", False, None, 200),
    ("dev-sandbox-1", "ap-south", "gp.medium", "idle", False, None, None),
    ("dev-sandbox-2", "us-west", "gp.medium", "idle", False, None, None),
    ("nightly-etl", "us-east", "gp.xlarge", "batch", True, 12, None),
    ("report-batch", "ap-south", "gp.large", "batch", True, 24, None),
    ("ml-training", "us-east", "gpu.large", "gpu_ml", True, 24, None),
    ("cache-1", "us-west", "gp.medium", "overprovisioned", False, None, 200),
    ("cache-2", "us-west", "gp.medium", "overprovisioned", False, None, 200),
    ("metrics-collector", "eu-north", "gp.small", "web", False, None, 200),
]


def reset(db: Session) -> None:
    for m in (Prediction, Recommendation, Anomaly, EnergyEstimate, TelemetrySample, CarbonIntensity, Resource):
        db.query(m).delete()
    db.commit()


def seed(db: Session, days: int = 7, interval_s: int = 300, seed_value: int = 42, end=None,
         inject_anomalies: bool = True) -> dict:
    rng = np.random.default_rng(seed_value)
    reset(db)
    for code, name, pue, price, *_ in REGIONS:
        if not db.get(Region, code):
            db.add(Region(code=code, name=name, pue=pue, price_multiplier=price))
    for n, v, m, g, i, p, c in INSTANCE_TYPES:
        if not db.get(InstanceType, n):
            db.add(InstanceType(name=n, vcpu=v, mem_gb=m, gpu_count=g, idle_w=i, peak_w=p, hourly_cost=c))
    db.commit()
    end = pd.Timestamp(end) if end is not None else pd.Timestamp.now("UTC").tz_localize(None).floor("h")
    start = end - pd.Timedelta(days=days)
    ci = generate_carbon_intensity(start, days * 24 + 1, rng)
    db.bulk_insert_mappings(CarbonIntensity, [
        {"region_code": r.region_code, "timestamp": r.timestamp.to_pydatetime(), "g_per_kwh": float(r.g_per_kwh),
         "source": "illustrative_synthetic", "is_forecast": False} for r in ci.itertuples()])
    db.commit()
    periods = int(days * 86400 / interval_s)
    total = 0
    for i, (name, region, inst, prof, flex, dl, sla) in enumerate(FLEET):
        res = Resource(name=name, region_code=region, instance_type=inst, is_flexible=flex,
                       deadline_hours=dl, sla_latency_ms=sla)
        db.add(res)
        db.flush()
        df = generate_workload(prof, start, periods, interval_s, region, rng,
                               inject_anomalies=inject_anomalies and name == "web-frontend-1")
        total += ingest_frame(db, res.id, df.drop(columns=["injected_anomaly"]), "simulated", interval_s)["samples"]
    return {"resources": len(FLEET), "samples": total, "days": days, "interval_s": interval_s,
            "origin": "simulated", "carbon_intensity_source": "illustrative_synthetic"}
