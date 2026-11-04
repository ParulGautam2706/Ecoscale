from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_admin
from app.core.ratelimit import limiter
from app.database.session import get_db
from app.ml import pipeline
from app.ml.explain import global_importance
from app.models.entities import User

router = APIRouter(prefix="/ml", tags=["ml"])


class TrainIn(BaseModel):
    target: str = Field("cpu_forecast", pattern="^(energy_wh|cpu_forecast)$")
    models: list[str] | None = None
    horizon_steps: int = Field(12, ge=1, le=288)


@router.post("/train")
@limiter.limit("6/hour")
def train(request: Request, body: TrainIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return pipeline.train_target(db, body.target, body.horizon_steps, body.models)


@router.get("/models")
def models(target: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return pipeline.list_runs(db, target)


@router.get("/comparison/{target}")
def comparison(target: str, _: User = Depends(current_user)):
    return pipeline.load_summary(target)


@router.get("/forecast/{resource_id}")
def forecast(resource_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return pipeline.forecast_resource(db, resource_id)


@router.get("/forecast-series/{resource_id}")
def forecast_series(resource_id: int, steps: int = 72, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return pipeline.forecast_series(db, resource_id, min(steps, 500))


class EnergyIn(BaseModel):
    instance_type: str
    region_code: str
    cpu: float = Field(ge=0, le=1)
    mem: float = Field(ge=0, le=1)
    gpu: float = Field(0.0, ge=0, le=1)
    net_mbit_s: float = Field(0.0, ge=0)
    disk_mb_s: float = Field(0.0, ge=0)
    hour: int = Field(12, ge=0, le=23)
    dow: int = Field(2, ge=0, le=6)
    cpu_prev: float | None = Field(None, ge=0, le=1)


@router.post("/predict-energy")
def predict_energy(body: EnergyIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    d = body.model_dump()
    if d["cpu_prev"] is None:
        d.pop("cpu_prev")
    return pipeline.predict_energy_wh(db, d)


@router.get("/importance/{target}")
def importance(target: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return global_importance(db, target)
