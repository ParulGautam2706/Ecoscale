from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.ratelimit import limiter
from app.database.session import get_db
from app.models.entities import RecStatus, Recommendation, Resource, User
from app.optimization import recommender
from app.optimization.evaluate import load_profiles, make_ctx
from app.optimization.multiobjective import optimize_fleet, tradeoff_table
from app.optimization.rightsizing import detect_idle
from app.optimization.scheduler import schedule_options
from app.services.analytics import utc
from app.services.data import telemetry_df

router = APIRouter(prefix="/optimization", tags=["optimization"])


class RunIn(BaseModel):
    window_days: int | None = Field(None, ge=1, le=90)


@router.post("/run")
@limiter.limit("30/hour")
def run(request: Request, body: RunIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Generates ADVISORY recommendations. Nothing is applied to any infrastructure."""
    return recommender.generate(db, body.window_days)


def _rec(r: Recommendation, names: dict) -> dict:
    return {"id": r.id, "resource_id": r.resource_id, "resource": names.get(r.resource_id), "type": r.rec_type,
            "rationale": r.rationale, "savings": r.savings, "risk": r.risk, "status": r.status.value,
            "priority": r.explanation.get("priority"), "confidence": r.explanation.get("confidence"),
            "performance_impact": r.explanation.get("performance_impact"), "created_at": utc(r.created_at),
            "advisory_only": True}


@router.get("/recommendations")
def recs(status: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    names = {r.id: r.name for r in db.query(Resource).all()}
    q = db.query(Recommendation)
    if status:
        q = q.filter(Recommendation.status == RecStatus(status))
    return [_rec(r, names) for r in q.order_by(Recommendation.id).all()]


class StatusIn(BaseModel):
    status: str = Field(pattern="^(accepted|rejected|pending)$")


@router.patch("/recommendations/{rec_id}")
def set_status(rec_id: int, body: StatusIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    r = db.get(Recommendation, rec_id)
    if not r:
        raise HTTPException(404, "recommendation not found")
    r.status = RecStatus(body.status)   # bookkeeping only: accepting does NOT change any infrastructure
    db.commit()
    return _rec(r, {x.id: x.name for x in db.query(Resource).all()})


class WeightsIn(BaseModel):
    carbon: float | None = Field(None, ge=0)
    cost: float | None = Field(None, ge=0)
    latency: float | None = Field(None, ge=0)
    sla: float | None = Field(None, ge=0)


def _weights(ctx, w: WeightsIn | None):
    if not w:
        return None
    merged = {**ctx.weights, **{k: v for k, v in w.model_dump().items() if v is not None}}
    if sum(merged.values()) <= 0:
        raise ValueError("weights must not all be zero")
    return merged


@router.post("/multiobjective")
def multiobjective(body: WeightsIn | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    ctx = make_ctx(db)
    profiles = load_profiles(db, ctx)
    if not profiles:
        raise ValueError("no telemetry")
    r = optimize_fleet(profiles, ctx, _weights(ctx, body))
    return {k: v for k, v in r.items() if not k.startswith("_")}


@router.get("/tradeoffs")
def tradeoffs(db: Session = Depends(get_db), _: User = Depends(current_user)):
    ctx = make_ctx(db)
    profiles = load_profiles(db, ctx)
    if not profiles:
        raise ValueError("no telemetry")
    return {"presets": tradeoff_table(profiles, ctx),
            "note": "Presets show trade-offs; no preset improves every metric for every workload."}


class ScheduleIn(BaseModel):
    resource_id: int
    weights: WeightsIn | None = None


@router.post("/schedule")
def schedule(body: ScheduleIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    ctx = make_ctx(db)
    profiles = load_profiles(db, ctx)
    if body.resource_id not in profiles:
        raise HTTPException(404, "resource has no telemetry")
    return schedule_options(profiles[body.resource_id], ctx, _weights(ctx, body.weights))


@router.get("/inefficiencies")
def inefficiencies(db: Session = Depends(get_db), _: User = Depends(current_user)):
    ctx = make_ctx(db)
    df = telemetry_df(db)
    if df.empty:
        return []
    profiles = load_profiles(db, ctx, df)
    idle = detect_idle(df, profiles, ctx)
    return [{"resource_id": p.resource_id, "resource": p.name, "instance": p.instance, "region": p.region,
             "mean_cpu": round(p.cpu_util_mean, 3), "mean_mem": round(p.mem_util_mean, 3),
             "underuse_share": round(p.sustained_underuse, 3), "idle": p.resource_id in idle, "flexible": p.is_flexible}
            for p in sorted(profiles.values(), key=lambda p: p.sustained_underuse, reverse=True)]
