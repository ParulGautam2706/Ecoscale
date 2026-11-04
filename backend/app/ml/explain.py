"""Global feature influence for the selected model: SHAP (tree models) with permutation-importance fallback."""
from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from app.ml import features as F
from app.ml.pipeline import PROXY_NOTE, _prep, load_artifact


def global_importance(db: Session, target: str, n_rows: int = 400) -> dict:
    art = load_artifact(target)
    feat, _, interval_s = _prep(db, art["horizon_steps"])
    d = F.build_energy_dataset(feat) if target == "energy_wh" else F.build_forecast_dataset(feat, art["horizon_steps"], interval_s)
    d = d.tail(max(n_rows * 10, n_rows)).sample(n=min(n_rows, len(d)), random_state=0)
    X, y = d[art["features"]].to_numpy(), d["target"].to_numpy()
    model, method = art["model"], None
    try:
        import shap
        if art["model_name"] in ("random_forest", "gradient_boosting", "xgboost", "lightgbm"):
            sv = shap.TreeExplainer(model).shap_values(X)
            imp = np.abs(np.asarray(sv)).mean(axis=0)
            method = "SHAP TreeExplainer (mean |SHAP value|)"
        else:
            raise RuntimeError("fallback")
    except Exception:
        from sklearn.inspection import permutation_importance
        r = permutation_importance(model, X, y, n_repeats=3, random_state=0)
        imp = r.importances_mean
        method = "permutation importance (SHAP not applicable to this model type)"
    order = np.argsort(imp)[::-1]
    return {"target": target, "model": art["model_name"], "method": method,
            "features": [{"feature": art["features"][i], "importance": float(imp[i])} for i in order],
            "caveat": PROXY_NOTE if target == "energy_wh" else
            "Importance describes the model's behaviour, not causal effect on real workloads.",
            "rows_used": int(len(X))}
