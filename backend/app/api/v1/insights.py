from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.database.session import get_db
from app.ml.explain import global_importance
from app.models.entities import Anomaly, Resource, Simulation, User
from app.services import anomaly as anomaly_service
from app.services import analytics, explain_service, reporting, simulation

router = APIRouter(tags=["insights"])


@router.get("/cost/summary")
def cost(days: int = 7, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return analytics.cost_summary(db, days)


@router.get("/explain/recommendation/{rec_id}")
def explain_rec(rec_id: int, include_model: bool = True, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return explain_service.explain_recommendation(db, rec_id, include_model)


@router.get("/explain/model/{target}")
def explain_model(target: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return global_importance(db, target)


class Scenario(BaseModel):
    type: str
    name: str | None = None
    percent: float | None = Field(None, gt=0, lt=100)
    region: str | None = None
    offset_hours: float | None = Field(None, ge=0, le=72)
    instance_type: str | None = None
    resource_ids: list[int] | None = None
    target_instance: str | None = None


class SimIn(BaseModel):
    resource_id: int
    scenarios: list[Scenario] = Field(min_length=1, max_length=10)


@router.post("/simulate")
def simulate(body: SimIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    scs = [s.model_dump(exclude_none=True) for s in body.scenarios]
    for s in scs:
        need = {"reduce_cpu": "percent", "reduce_memory": "percent", "region": "region", "shift": "offset_hours",
                "instance": "instance_type", "consolidate": "resource_ids"}.get(s["type"])
        if need and need not in s:
            raise ValueError(f"scenario '{s['type']}' requires '{need}'")
    res = simulation.run(db, body.resource_id, scs)
    db.add(Simulation(user_id=user.id, scenario={"resource_id": body.resource_id, "scenarios": scs}, results=res))
    db.commit()
    return res


@router.get("/simulate/history")
def sim_history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(Simulation).filter(Simulation.user_id == user.id).order_by(Simulation.id.desc()).limit(20).all()
    return [{"id": r.id, "created_at": analytics.utc(r.created_at), "scenario": r.scenario} for r in rows]


class DetectIn(BaseModel):
    contamination: float | None = Field(None, gt=0, le=0.2, description="null = automatic threshold")
    z_min: float = Field(3.5, ge=2, le=20)
    resource_id: int | None = None


@router.post("/anomalies/detect")
def detect(body: DetectIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return anomaly_service.detect(db, body.contamination, body.z_min, body.resource_id)


@router.get("/anomalies")
def anomalies(severity: str | None = None, resource_id: int | None = None, db: Session = Depends(get_db),
              _: User = Depends(current_user)):
    names = {r.id: r.name for r in db.query(Resource).all()}
    q = db.query(Anomaly)
    if severity:
        q = q.filter(Anomaly.severity == severity)
    if resource_id:
        q = q.filter(Anomaly.resource_id == resource_id)
    return [{"id": a.id, "resource_id": a.resource_id, "resource": names.get(a.resource_id), "ts": analytics.utc(a.ts),
             "metric": a.metric, "severity": a.severity, "score": round(a.score, 4),
             "investigate": anomaly_service.investigation_steps(a.metric)} for a in q.order_by(Anomaly.ts.desc()).limit(500).all()]


class ReportIn(BaseModel):
    format: str = Field("pdf", pattern="^(csv|pdf)$")
    section: str = "full"


@router.post("/reports/generate")
def report(body: ReportIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    if body.format == "pdf":
        data, mime, ext = reporting.make_pdf(db), "application/pdf", "pdf"
    else:
        data, mime, ext = reporting.make_csv(db, body.section), "text/csv", "csv"
    return Response(data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="greencloud_{body.section}.{ext}"'})
