"""Explanation assembly for recommendations (+ optional global model influence via SHAP)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import Recommendation


def explain_recommendation(db: Session, rec_id: int, include_model: bool = True) -> dict:
    rec = db.get(Recommendation, rec_id)
    if rec is None:
        raise LookupError("recommendation not found")
    out = {"id": rec.id, "resource_id": rec.resource_id, "type": rec.rec_type, "status": rec.status.value,
           "risk": rec.risk, "rationale": rec.rationale, "explanation": rec.explanation}
    if include_model:
        try:
            from app.ml.explain import global_importance
            out["model_feature_influence"] = global_importance(db, "energy_wh", n_rows=300)
        except FileNotFoundError:
            out["model_feature_influence"] = None
            out["model_note"] = "Train the energy model to see SHAP-based feature influence."
    return out
