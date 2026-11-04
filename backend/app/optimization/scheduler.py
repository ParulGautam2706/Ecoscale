"""Carbon-aware scheduling for ONE flexible workload: compares start times and regions
under deadline, latency, capacity-agnostic cost and data-transfer assumptions."""
from __future__ import annotations

from app.optimization.evaluate import Ctx, Profile, candidates, evaluate, latency_reference, score


def schedule_options(p: Profile, ctx: Ctx, weights: dict | None = None, top: int = 10,
                     same_instance_only: bool = True) -> dict:
    if not p.is_flexible:
        raise ValueError("resource is not marked flexible; scheduling applies to flexible workloads only")
    weights = weights or ctx.weights
    base = evaluate(p, ctx.specs[p.instance], p.region, 0.0, ctx, enforce=False)
    cl = [e for e in candidates(p, ctx) if (not same_instance_only or e.instance == p.instance)]
    score(cl, weights, base, latency_reference(p, ctx))
    by_carbon = sorted(cl, key=lambda e: e.co2e_kg)[:top]
    best = min(cl, key=lambda e: e.J)
    red = (base.co2e_kg - best.co2e_kg) / base.co2e_kg if base.co2e_kg else 0.0
    thr = ctx.thr["shift_min_improvement"]
    changed = (best.region, best.offset_h) != (p.region, 0.0)
    if changed and red >= thr:
        msg = (f"Move flexible workload '{p.name}' from {p.region} (start {int(p.start_hour_utc):02d}:00 UTC) to "
               f"{best.region} starting +{best.offset_h:g}h because estimated carbon intensity is "
               f"{best.ci_g_per_kwh:.0f} vs {base.ci_g_per_kwh:.0f} gCO2e/kWh, while latency "
               f"({best.latency_ms:.0f} ms) and cost (${best.cost_usd:.2f}/day vs ${base.cost_usd:.2f}) stay within configured limits.")
    else:
        msg = (f"No schedule change recommended for '{p.name}': best alternative reduces estimated carbon by only "
               f"{red*100:.1f}% (< {thr*100:.0f}% threshold) or the current schedule is already preferred.")
    return {"resource_id": p.resource_id, "name": p.name, "message": msg, "recommended_change": bool(changed and red >= thr),
            "carbon_reduction_pct": round(red * 100, 2), "baseline": base.to_dict(), "best": best.to_dict(),
            "alternatives_by_carbon": [e.to_dict() for e in by_carbon], "weights": weights,
            "origin": "estimated", "note": "Lower-carbon regions are not assumed cheaper; cost and latency are evaluated explicitly."}
