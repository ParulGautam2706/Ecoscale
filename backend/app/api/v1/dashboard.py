import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import settings
from app.database.session import get_db
from app.models.entities import User
from app.services import analytics
from app.services.carbon import CarbonProvider
from app.services.data import instance_specs, region_table
from app.services.energy import EnergyConfig, estimate
from app.services import settings_service

router = APIRouter(tags=["analytics"])


@router.get("/dashboard/summary")
def dashboard(region: str | None = None, days: int = Query(7, ge=1, le=90), start: str | None = None,
              end: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return analytics.summary(db, region, days, start, end)


@router.get("/carbon/timeseries")
def timeseries(region: str | None = None, freq: str = Query("h", pattern="^(h|D)$"), days: int = 7,
               db: Session = Depends(get_db), _: User = Depends(current_user)):
    return analytics.carbon_timeseries(db, region, freq, days)


@router.get("/carbon/regions")
def regions(days: int = 7, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return analytics.by_region(db, days)


@router.get("/carbon/workloads")
def workloads(days: int = 7, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return analytics.by_workload(db, days)


@router.get("/carbon/before-after")
def before_after(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return analytics.before_after(db)


@router.get("/carbon/intensity")
def intensity(region: str | None = None, hours: int = Query(72, le=720), db: Session = Depends(get_db),
              _: User = Depends(current_user)):
    cp = CarbonProvider(db)
    out = []
    for r in sorted(cp.regions()):
        if region and r != region:
            continue
        s = cp.series(r).tail(hours)
        out.append({"region": r, "series": [{"ts": analytics.utc(t), "g_per_kwh": round(float(v), 1)} for t, v in s.items()],
                    "source": "illustrative_synthetic sample data unless replaced by a real feed"})
    return out


@router.get("/carbon/forecast")
def forecast(region: str, hours: int = Query(48, le=168), db: Session = Depends(get_db), _: User = Depends(current_user)):
    cp = CarbonProvider(db)
    f = cp.forecast(region, hours)
    return {"region": region, "backtest": cp.backtest(region), "origin": "predicted",
            "forecast": [{"ts": analytics.utc(r.timestamp), "g_per_kwh": round(float(r.g_per_kwh), 1)} for r in f.itertuples()],
            "method": f["method"].iloc[0] if len(f) else None}


class EstimateIn(BaseModel):
    instance_type: str
    region: str
    cpu: float = Field(ge=0, le=1)
    mem: float = Field(ge=0, le=1)
    gpu: float | None = Field(None, ge=0, le=1)
    net_mbit_s: float | None = Field(None, ge=0)
    disk_mb_s: float | None = Field(None, ge=0)
    interval_s: float = Field(3600, gt=0)
    measured_power_w: float | None = Field(None, gt=0)


@router.post("/carbon/estimate")
def estimate_ep(body: EstimateIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    specs, regs = instance_specs(db), region_table(db)
    if body.instance_type not in specs or body.region not in regs:
        from fastapi import HTTPException
        raise HTTPException(404, "unknown instance_type or region")
    cfg = EnergyConfig.from_dict(settings_service.get_all(db)["energy"])
    ci = CarbonProvider(db).daily_mean(body.region)
    r = estimate(specs[body.instance_type], body.cpu, body.mem, body.interval_s, ci, gpu=body.gpu, net_mbit_s=body.net_mbit_s,
                 disk_mb_s=body.disk_mb_s, pue=regs[body.region]["pue"], cfg=cfg, measured_power_w=body.measured_power_w)
    return {"it_power_w": float(r.it_power_w), "components_w": {k: float(v) for k, v in r.components_w.items()},
            "it_kwh": float(r.it_kwh), "facility_kwh": float(r.facility_kwh), "co2e_kg": float(r.co2e_kg), "pue": r.pue,
            "ci_g_per_kwh": ci, "confidence": r.confidence, "method": r.method, "assumptions": r.assumptions}
