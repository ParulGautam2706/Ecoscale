"""Generates ADVISORY recommendations with full explanations. Never touches real infrastructure."""
from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from app.models.entities import RecStatus, Recommendation
from app.optimization.evaluate import Ctx, Evaluation, Profile, evaluate, load_profiles, make_ctx
from app.optimization.multiobjective import optimize_fleet
from app.optimization.rightsizing import detect_idle, evaluate_consolidation, find_consolidations
from app.services.data import telemetry_df

ASSUMPTIONS = [
    "Savings are ESTIMATES from the configured power model, not metered energy",
    "Telemetry window is treated as representative of future demand",
    "Carbon intensity uses the hour-of-day profile of the cached/sample dataset",
    "Cost uses flat on-demand hourly prices configured in the instance catalogue",
]


def _confidence(p: Profile) -> float:
    coverage = min(1.0, p.hours_observed / 72.0)
    return round(0.85 * coverage * (0.5 + 0.5 * (1 - p.burstiness)), 2)


def _risk_level(sla: float, kind: str) -> str:
    if kind == "idle":
        return "medium"
    return "low" if sla < 0.05 else ("medium" if sla < 0.30 else "high")


def _savings(before: Evaluation | dict, after: Evaluation | dict) -> dict:
    b = before if isinstance(before, dict) else before.to_dict()
    a = after if isinstance(after, dict) else after.to_dict()
    out = {}
    for k_src, k_out in (("energy_kwh", "energy_kwh_day"), ("co2e_kg", "co2e_kg_day"), ("cost_usd", "cost_usd_day")):
        out[k_out] = round(b[k_src] - a[k_src], 4)
        out[k_out.replace("_day", "_pct")] = round(100 * (b[k_src] - a[k_src]) / b[k_src], 2) if b[k_src] else 0.0
    out["co2e_kg_month"] = round(out["co2e_kg_day"] * 30, 3)
    out["cost_usd_month"] = round(out["cost_usd_day"] * 30, 2)
    out["basis"] = "estimated, per 24h, extrapolated x30 for month"
    return out


def _explain(p: Profile, kind: str, why: str, savings: dict, perf: str, risks: list, before: dict, after: dict | None,
             extra_features: list | None = None) -> dict:
    return {
        "why": why,
        "influencing_features": [
            {"name": "cpu_utilization_mean", "value": round(p.cpu_util_mean, 3)},
            {"name": "cpu_cores_p95", "value": round(p.cores_p95, 2)},
            {"name": "memory_gb_p95", "value": round(p.mem_gb_p95, 2)},
            {"name": "sustained_underuse_share", "value": round(p.sustained_underuse, 3)},
            {"name": "observation_hours", "value": round(p.hours_observed, 1)},
        ] + (extra_features or []),
        "expected_savings": savings,
        "performance_impact": perf,
        "confidence": _confidence(p),
        "confidence_basis": "heuristic: telemetry coverage (72h = full) x stability; not a statistical interval",
        "risks": risks,
        "assumptions": ASSUMPTIONS,
        "before": before, "after": after,
        "origin": "estimated",
    }


def generate(db: Session, window_days: int | None = None) -> dict:
    ctx = make_ctx(db)
    df = telemetry_df(db)
    if df.empty:
        raise ValueError("no telemetry; seed or ingest data first")
    if window_days:
        df = df[df["ts"] >= df["ts"].max() - np.timedelta64(window_days, "D")]
    profiles = load_profiles(db, ctx, df)
    db.query(Recommendation).filter(Recommendation.status == RecStatus.pending).delete()
    created: list[Recommendation] = []
    handled: set[int] = set()

    # 1) idle resources
    for rid in sorted(detect_idle(df, profiles, ctx)):
        p = profiles[rid]
        base = evaluate(p, ctx.specs[p.instance], p.region, 0.0, ctx, enforce=False)
        zero = {"energy_kwh": 0.0, "co2e_kg": 0.0, "cost_usd": 0.0}
        sv = _savings(base, zero)
        why = (f"'{p.name}' stayed below {ctx.thr['idle_cpu']*100:.0f}% CPU and {ctx.thr['idle_net_mbit_s']:g} Mbit/s network "
               f"for at least {ctx.thr['idle_sustained_fraction']*100:.0f}% of the observation window. It may be abandoned or misconfigured.")
        created.append(Recommendation(resource_id=rid, rec_type="idle", rationale=why, savings=sv, risk="medium",
                                      explanation=_explain(p, "idle", why, sv, "No expected impact if truly unused",
                                                           ["Verify no scheduled/cron jobs or on-call access depend on it before stopping",
                                                            "Idle detection uses utilization only; check ownership and data"],
                                                           base.to_dict(), None)))
        handled.add(rid)

    # 2) consolidation
    for g in find_consolidations(profiles, ctx, handled):
        after, before = evaluate_consolidation(g, ctx)
        b_tot = {"energy_kwh": sum(e.energy_kwh for e in before), "co2e_kg": sum(e.co2e_kg for e in before),
                 "cost_usd": sum(e.cost_usd for e in before)}
        sv = _savings(b_tot, after)
        if sv["energy_kwh_day"] <= 0 or sv["cost_usd_day"] <= 0 or after.violations:
            continue
        names = [m.name for m in g["members"]]
        p0 = g["members"][0]
        why = (f"{', '.join(names)} in {g['region']} each ran below {ctx.thr['alpha_cpu']*100:.0f}% CPU / "
               f"{ctx.thr['beta_mem']*100:.0f}% memory. Their combined p95 demand ({after.cpu_util_p95*100:.0f}% CPU, "
               f"{after.mem_util_p95*100:.0f}% memory of one {g['target'].name}) fits on a single instance.")
        created.append(Recommendation(resource_id=p0.resource_id, rec_type="consolidate", rationale=why, savings=sv,
                                      risk=_risk_level(after.sla_risk, "consolidate"),
                                      explanation={**_explain(p0, "consolidate", why, sv,
                                                              f"Projected p95 CPU {after.cpu_util_p95*100:.0f}% (limit {ctx.thr['max_cpu_p95_after']*100:.0f}%)",
                                                              ["Noisy-neighbour contention if peaks coincide (p95s were summed conservatively)",
                                                               "Single point of failure; check isolation and licensing"],
                                                              {"per_member": [e.to_dict() for e in before]}, after.to_dict()),
                                                   "resource_ids": [m.resource_id for m in g["members"]],
                                                   "target_instance": g["target"].name}))
        handled.update(m.resource_id for m in g["members"])

    # 3) multi-objective optimisation for the rest
    fleet = optimize_fleet(profiles, ctx, exclude=handled)
    thr = ctx.thr["shift_min_improvement"]
    for a, ch, base in zip(fleet["assignments"], fleet["_chosen"], fleet["_baselines"]):
        if not a["changed"]:
            continue
        p = profiles[a["resource_id"]]
        spec_b, spec_c = ctx.specs[base.instance], ctx.specs[ch.instance]
        sv = _savings(base, ch)
        carbon_red = sv["co2e_kg_pct"] / 100
        moved_region, shifted, resized = ch.region != base.region, ch.offset_h != base.offset_h, ch.instance != base.instance
        if sv["co2e_kg_day"] <= 0 and sv["cost_usd_day"] <= 0:
            continue
        if -sv["cost_usd_pct"] > ctx.limits["max_cost_increase_pct"]:
            continue                      # lower carbon is never assumed to justify a large cost increase
        if ch.sla_risk >= 0.30 and ch.sla_risk > base.sla_risk:
            continue                      # never trade carbon for a high SLA risk
        if (moved_region or shifted) and carbon_red < thr:
            continue                      # paper rule: require >=20% carbon improvement to justify moving/shifting
        if resized and spec_c.vcpu < spec_b.vcpu and p.sustained_underuse < ctx.thr["sustained_fraction"]:
            continue                      # downsizing only for sustained under-utilisation
        kind = "region" if moved_region else ("shift" if shifted else "rightsize")
        parts = []
        if resized:
            parts.append(f"resize {base.instance}→{ch.instance}")
        if moved_region:
            parts.append(f"move {base.region}→{ch.region}")
        if shifted:
            parts.append(f"start +{ch.offset_h:g}h later")
        why = (f"Proposed change for '{p.name}': {', '.join(parts)}. Estimated carbon changes by {sv['co2e_kg_pct']:.1f}%, "
               f"cost by {sv['cost_usd_pct']:.1f}%, with p95 CPU {ch.cpu_util_p95*100:.0f}% and latency {ch.latency_ms:.0f} ms "
               f"inside configured limits. Selected by minimising J with weights {fleet['weights']}.")
        risks = ["Verify peak demand before applying; p95 from a limited window",
                 "Lower-carbon regions are not guaranteed cheaper or technically suitable (data residency, services)"]
        if moved_region:
            risks.append("Instance type availability, quotas and data-residency rules in the target region are NOT checked")
            risks.append(f"Latency rises {base.latency_ms:.0f}→{ch.latency_ms:.0f} ms; one-time data transfer assumed {ctx.limits['data_gb']} GB")
        perf = f"p95 CPU {base.cpu_util_p95*100:.0f}%→{ch.cpu_util_p95*100:.0f}%, latency {base.latency_ms:.0f}→{ch.latency_ms:.0f} ms, SLA risk {base.sla_risk:.3f}→{ch.sla_risk:.3f}"
        extra = [{"name": "carbon_intensity_g_per_kwh_before", "value": round(base.ci_g_per_kwh, 1)},
                 {"name": "carbon_intensity_g_per_kwh_after", "value": round(ch.ci_g_per_kwh, 1)}]
        created.append(Recommendation(resource_id=p.resource_id, rec_type=kind, rationale=why, savings=sv,
                                      risk=_risk_level(ch.sla_risk, kind),
                                      explanation=_explain(p, kind, why, sv, perf, risks, base.to_dict(), ch.to_dict(), extra)))
    # priority = rank by combined normalised carbon+cost saving
    if created:
        scores = np.array([r.savings["co2e_kg_day"] / (max(x.savings["co2e_kg_day"] for x in created) or 1) +
                           r.savings["cost_usd_day"] / (max(x.savings["cost_usd_day"] for x in created) or 1) for r in created])
        order = scores.argsort()[::-1]
        for rank, i in enumerate(order):
            third = len(created) / 3
            created[i].explanation = {**created[i].explanation,
                                      "priority": "high" if rank < third else ("medium" if rank < 2 * third else "low")}
    db.add_all(created)
    db.commit()
    return {"created": len(created), "by_type": {t: sum(r.rec_type == t for r in created) for t in {r.rec_type for r in created}},
            "totals": {k: round(sum(r.savings[k] for r in created), 3) for k in ("co2e_kg_day", "cost_usd_day", "energy_kwh_day")},
            "status": "advisory only; no infrastructure was modified"}
