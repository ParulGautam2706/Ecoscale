from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.database.session import get_db
from app.models.entities import InstanceType, Region, Resource, TelemetrySample, User
from app.monitoring.collectors import LocalCollector, local_hardware
from app.services.analytics import utc
from app.services.ingestion import ingest_frame
from app.services.simulator import generate_workload

router = APIRouter(prefix="/telemetry", tags=["telemetry"])
_local: dict = {}


class Sample(BaseModel):
    ts: datetime
    cpu: float = Field(ge=0, le=1)
    mem: float = Field(ge=0, le=1)
    gpu: float | None = Field(None, ge=0, le=1)
    net_mbit_s: float | None = Field(None, ge=0)
    disk_mb_s: float | None = Field(None, ge=0)


class IngestIn(BaseModel):
    resource_id: int
    origin: str = Field("measured", pattern="^(measured|simulated)$")
    interval_s: float = Field(60, gt=0, le=3600)
    samples: list[Sample] = Field(min_length=1, max_length=5000)


@router.post("/ingest", status_code=201)
def ingest(body: IngestIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    df = pd.DataFrame([s.model_dump() for s in body.samples])
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)
    return ingest_frame(db, body.resource_id, df, body.origin, body.interval_s)


@router.get("")
def list_samples(resource_id: int, limit: int = 200, db: Session = Depends(get_db), _: User = Depends(current_user)):
    rows = (db.query(TelemetrySample).filter(TelemetrySample.resource_id == resource_id)
            .order_by(TelemetrySample.ts.desc()).limit(min(limit, 2000)).all())
    return [{"ts": utc(r.ts), "cpu": r.cpu, "mem": r.mem, "gpu": r.gpu, "net_mbit_s": r.net_mbit_s,
             "disk_mb_s": r.disk_mb_s, "origin": r.data_origin.value} for r in reversed(rows)]


class SimIn(BaseModel):
    resource_id: int
    hours: int = Field(6, ge=1, le=72)
    profile: str = "web"


@router.post("/simulate", status_code=201)
def simulate(body: SimIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    res = db.get(Resource, body.resource_id)
    if not res:
        raise HTTPException(404, "resource not found")
    last = (db.query(TelemetrySample.ts, TelemetrySample.interval_s).filter(TelemetrySample.resource_id == res.id)
            .order_by(TelemetrySample.ts.desc()).first())
    interval = int(last[1]) if last else 300
    start = (pd.Timestamp(last[0]) + pd.Timedelta(seconds=interval)) if last else pd.Timestamp.now("UTC").tz_localize(None).floor("min")
    df = generate_workload(body.profile, start, int(body.hours * 3600 / interval), interval, res.region_code,
                           np.random.default_rng(), False).drop(columns=["injected_anomaly"])
    return ingest_frame(db, res.id, df, "simulated", interval)


@router.post("/collect-local", status_code=201)
def collect_local(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Reads THIS machine's utilization with psutil (origin=measured). Energy remains an estimate."""
    hw = local_hardware()
    if not db.get(InstanceType, "local.machine"):
        db.add(InstanceType(name="local.machine", vcpu=hw["vcpu"], mem_gb=hw["mem_gb"], gpu_count=0,
                            idle_w=30.0, peak_w=30.0 + 6.0 * hw["vcpu"], hourly_cost=0.0))
        db.commit()
    res = db.query(Resource).filter(Resource.name == "local-machine").first()
    if not res:
        region = db.query(Region).first()
        if not region:
            raise HTTPException(409, "seed regions first (POST /admin/seed)")
        res = Resource(name="local-machine", region_code=region.code, instance_type="local.machine")
        db.add(res)
        db.commit()
    col = _local.setdefault("c", LocalCollector())
    s = col.collect()
    df = pd.DataFrame([{k: v for k, v in s.items() if k != "interval_s"}])
    out = ingest_frame(db, res.id, df, "measured", s["interval_s"])
    return {**out, "sample": {"cpu": s["cpu"], "mem": s["mem"]}, "resource_id": res.id,
            "note": "Utilization is measured; power uses a generic assumed model (30 W idle + 6 W per vCPU)."}
