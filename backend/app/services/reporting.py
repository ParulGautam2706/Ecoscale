"""CSV / PDF report generation. Methodology and assumptions are always included."""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Recommendation
from app.services import analytics, settings_service

SECTIONS = ["summary", "carbon", "models", "recommendations", "comparison", "methodology"]

METHODOLOGY = [
    "Pipeline: utilization -> component power (CPU/platform, RAM, GPU, storage, network) -> IT energy (power x time / 3.6e6 = kWh) -> facility energy (x PUE) -> CO2e (x grid intensity g/kWh / 1000 = kg).",
    "Energy values are ESTIMATED from a configurable linear power model; they are not metered unless a record is labelled 'measured'.",
    "Telemetry labelled 'simulated' is synthetic. Carbon-intensity data shipped with the project is illustrative sample data.",
    "ML energy models are proxy estimators of the power model (labels are model-derived). Utilization forecasts are evaluated on chronological hold-out data against persistence and seasonal-naive baselines.",
    "Recommendations are advisory. Savings are per-24h estimates extrapolated x30; SLA risk and queueing latency are heuristic functions of p95 utilization.",
    "Confidence scores are heuristics (coverage and stability), not statistical intervals.",
]


def _frames(db: Session) -> dict[str, pd.DataFrame]:
    s = analytics.summary(db, days=7)
    out: dict[str, pd.DataFrame] = {}
    if not s.get("empty"):
        out["summary"] = pd.DataFrame([{"energy_kwh": s["totals"]["energy_kwh"], "co2e_kg": s["totals"]["co2e_kg"],
                                        "cost_usd": s["totals"]["cost_usd"], "avg_cpu": s["avg_cpu"], "avg_mem": s["avg_mem"],
                                        "telemetry_origin": ",".join(s["origin"]["telemetry"]), "energy_method": ",".join(s["origin"]["energy"]),
                                        "window_start": s["window"]["start"], "window_end": s["window"]["end"]}])
        out["carbon"] = pd.DataFrame(analytics.by_workload(db)["workloads"])
    try:
        from app.ml.pipeline import load_summary
        rows = []
        for tgt in ("cpu_forecast", "energy_wh"):
            try:
                sm = load_summary(tgt)
            except FileNotFoundError:
                continue
            for m in sm["all_models"]:
                rows.append({"target": tgt, **{k: (round(v, 5) if isinstance(v, float) else v) for k, v in m.items()},
                             "selected": m["model"] == sm["best_model"], "label_type": "proxy (model-derived)" if tgt == "energy_wh" else "real forecast"})
        out["models"] = pd.DataFrame(rows)
    except Exception:
        out["models"] = pd.DataFrame()
    recs = db.query(Recommendation).all()
    out["recommendations"] = pd.DataFrame([{"id": r.id, "resource_id": r.resource_id, "type": r.rec_type, "status": r.status.value,
                                            "risk": r.risk, "priority": r.explanation.get("priority"),
                                            "co2e_kg_month": r.savings.get("co2e_kg_month"), "cost_usd_month": r.savings.get("cost_usd_month"),
                                            "co2e_pct": r.savings.get("co2e_kg_pct"), "cost_pct": r.savings.get("cost_usd_pct"),
                                            "rationale": r.rationale} for r in recs])
    ba = analytics.before_after(db)
    out["comparison"] = (pd.DataFrame([{"metric": k, "before_per_day": ba["baseline_per_day"][k], "after_per_day": ba["after_per_day"][k],
                                        "reduction_pct": ba["reduction_pct"][k]} for k in ba["baseline_per_day"]])
                         if not ba.get("empty") else pd.DataFrame())
    out["methodology"] = pd.DataFrame({"statement": METHODOLOGY + [f"Settings snapshot: {json.dumps(settings_service.get_all(db))}"]})
    return out


def make_csv(db: Session, section: str = "full") -> bytes:
    frames = _frames(db)
    buf = io.StringIO()
    names = SECTIONS if section == "full" else [section]
    for n in names:
        if n not in frames:
            if section != "full":
                raise ValueError(f"unknown section '{n}'; use one of {SECTIONS + ['full']}")
            continue
        if section == "full":
            buf.write(f"# {n.upper()}\n")
        frames[n].to_csv(buf, index=False)
        buf.write("\n")
    return buf.getvalue().encode()


def make_pdf(db: Session) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    frames = _frames(db)
    st = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    el = [Paragraph("GreenCloud AI 2.0 - Carbon & Optimization Report", st["Title"]),
          Paragraph(f"Generated {datetime.now(timezone.utc).replace(tzinfo=None):%Y-%m-%d %H:%M} UTC. Values are ESTIMATED unless labelled measured; "
                    "simulated telemetry is synthetic.", st["Italic"]), Spacer(1, 10)]

    def table(df: pd.DataFrame, cols=None, maxrows=25):
        if df.empty:
            return Paragraph("No data available for this section.", st["BodyText"])
        d = df[cols] if cols else df
        data = [list(d.columns)] + [[(f"{v:.4g}" if isinstance(v, float) else str(v))[:60] for v in row] for row in d.head(maxrows).itertuples(index=False)]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14532d")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdf4")])]))
        return t

    el += [Paragraph("1. Monitoring summary", st["Heading2"]), table(frames.get("summary", pd.DataFrame()))]
    el += [Paragraph("2. Carbon footprint by workload", st["Heading2"]),
           table(frames.get("carbon", pd.DataFrame()), ["resource", "region_code", "instance_type", "energy_kwh", "co2e_kg", "cost_usd", "avg_cpu", "confidence"]
                 if "carbon" in frames and not frames["carbon"].empty else None)]
    m = frames.get("models", pd.DataFrame())
    el += [Paragraph("3. Model performance (chronological hold-out)", st["Heading2"]),
           table(m, ["target", "model", "mae", "rmse", "r2", "cv_rmse_mean", "train_seconds", "selected", "label_type"] if not m.empty else None)]
    r = frames.get("recommendations", pd.DataFrame())
    el += [Paragraph("4. Optimization recommendations (advisory)", st["Heading2"]),
           table(r, ["id", "type", "status", "risk", "priority", "co2e_kg_month", "cost_usd_month", "co2e_pct", "cost_pct"] if not r.empty else None)]
    el += [Paragraph("5. Before vs after (estimated)", st["Heading2"]), table(frames.get("comparison", pd.DataFrame()))]
    el += [Paragraph("6. Methodology and assumptions", st["Heading2"])] + [Paragraph("• " + s, st["BodyText"]) for s in METHODOLOGY]
    doc.build(el)
    return buf.getvalue()
