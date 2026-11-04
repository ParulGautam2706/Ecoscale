from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_admin
from app.database.session import get_db
from app.models.entities import InstanceType, Region, Resource, User
from app.services import seed as seed_service
from app.services import settings_service

router = APIRouter(tags=["catalog"])


@router.get("/resources")
def resources(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [{"id": r.id, "name": r.name, "region": r.region_code, "instance_type": r.instance_type,
             "is_flexible": r.is_flexible, "deadline_hours": r.deadline_hours, "sla_latency_ms": r.sla_latency_ms}
            for r in db.query(Resource).order_by(Resource.id).all()]


@router.get("/regions")
def regions(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [{"code": r.code, "name": r.name, "pue": r.pue, "price_multiplier": r.price_multiplier} for r in db.query(Region).all()]


@router.get("/instance-types")
def instance_types(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [{"name": i.name, "vcpu": i.vcpu, "mem_gb": i.mem_gb, "gpu_count": i.gpu_count, "idle_w": i.idle_w,
             "peak_w": i.peak_w, "hourly_cost": i.hourly_cost} for i in db.query(InstanceType).all()]


class SeedIn(BaseModel):
    days: int = Field(7, ge=1, le=30)
    interval_s: int = Field(300, ge=60, le=3600)
    seed: int = 42


@router.post("/admin/seed")
def seed(body: SeedIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Replaces telemetry/carbon/resources with SIMULATED demo data (labelled data_origin=simulated)."""
    return seed_service.seed(db, body.days, body.interval_s, body.seed)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return settings_service.get_all(db)


@router.put("/settings/{group}")
def put_settings(group: str, body: dict, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return settings_service.update(db, group, body)
