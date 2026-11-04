"""Fleet-level multi-objective optimisation:  J = w1*Carbon + w2*Cost + w3*Latency + w4*SLA-risk.
Each workload picks one feasible candidate (instance, region, start); regional vCPU capacity is a coupling
constraint. Solved exactly as a MILP with scipy.optimize.milp."""
from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from app.optimization.evaluate import Ctx, Evaluation, Profile, candidates, evaluate, latency_reference, score

PRESETS = {
    "carbon_first": {"carbon": 0.70, "cost": 0.15, "latency": 0.10, "sla": 0.05},
    "cost_first": {"carbon": 0.15, "cost": 0.70, "latency": 0.10, "sla": 0.05},
    "performance_first": {"carbon": 0.10, "cost": 0.10, "latency": 0.40, "sla": 0.40},
    "balanced": {"carbon": 0.25, "cost": 0.25, "latency": 0.25, "sla": 0.25},
}


def _totals(evals: list[Evaluation], sensitive: set[int]) -> dict:
    """Latency/SLA means cover latency-sensitive (non-flexible) workloads only."""
    sens = [e for e in evals if e.resource_id in sensitive]
    n = max(len(sens), 1)
    return {"energy_kwh_day": sum(e.energy_kwh for e in evals), "co2e_kg_day": sum(e.co2e_kg for e in evals),
            "cost_usd_day": sum(e.cost_usd for e in evals), "mean_latency_ms": sum(e.latency_ms for e in sens) / n,
            "mean_sla_risk": sum(e.sla_risk for e in sens) / n}


def optimize_fleet(profiles: dict[int, Profile], ctx: Ctx, weights: dict | None = None,
                   exclude: set[int] | None = None) -> dict:
    weights = weights or ctx.weights
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}
    items = [p for rid, p in sorted(profiles.items()) if not exclude or rid not in exclude]
    cand_lists, baselines = [], []
    for p in items:
        base = evaluate(p, ctx.specs[p.instance], p.region, 0.0, ctx, enforce=False)
        base.feasible = True
        cl = candidates(p, ctx)
        ref = latency_reference(p, ctx)
        score(cl, weights, base, ref)
        score([base], weights, base, ref)
        cand_lists.append(cl)
        baselines.append(base)
    var = [(i, j) for i, cl in enumerate(cand_lists) for j in range(len(cl))]
    n = len(var)
    c = np.array([cand_lists[i][j].J for i, j in var])
    A_eq = np.zeros((len(items), n))
    for k, (i, j) in enumerate(var):
        A_eq[i, k] = 1
    regions = list(ctx.regions)
    A_cap = np.zeros((len(regions), n))
    for k, (i, j) in enumerate(var):
        A_cap[regions.index(cand_lists[i][j].region), k] = cand_lists[i][j].vcpu
    cap = float(ctx.limits["region_capacity_vcpu"])
    cons = [LinearConstraint(A_eq, 1, 1), LinearConstraint(A_cap, 0, cap)]
    solver = "scipy.optimize.milp (HiGHS)"
    res = milp(c, constraints=cons, integrality=np.ones(n), bounds=Bounds(0, 1)) if n else None
    if res is not None and res.success:
        x = np.round(res.x).astype(int)
        chosen = [None] * len(items)
        for k, (i, j) in enumerate(var):
            if x[k]:
                chosen[i] = cand_lists[i][j]
    else:
        solver = "per-workload argmin fallback (capacity ignored)"
        chosen = [min(cl, key=lambda e: e.J) for cl in cand_lists]
    rows = []
    for p, b, ch in zip(items, baselines, chosen):
        rows.append({"resource_id": p.resource_id, "name": p.name, "baseline": b.to_dict(), "chosen": ch.to_dict(),
                     "changed": (ch.instance, ch.region, ch.offset_h) != (b.instance, b.region, b.offset_h)})
    sensitive = {p.resource_id for p in items if not p.is_flexible}
    return {"weights": weights, "solver": solver, "assignments": rows, "baseline_totals": _totals(baselines, sensitive),
            "optimized_totals": _totals(chosen, sensitive), "_chosen": chosen, "_baselines": baselines,
            "assumptions": ["Per-day figures from telemetry-window profiles; flexible jobs modelled as ephemeral runs",
                            "Objectives normalised against each workload's baseline (carbon, cost), its latency SLA reference, and absolute SLA risk",
                            "SLA risk and queueing latency are heuristic functions of p95 utilization",
                            f"Regional capacity limit {cap:g} vCPU per region"]}


def tradeoff_table(profiles, ctx, exclude=None) -> list[dict]:
    out = []
    for name, w in PRESETS.items():
        r = optimize_fleet(profiles, ctx, w, exclude)
        b, o = r["baseline_totals"], r["optimized_totals"]
        out.append({"preset": name, "weights": r["weights"], "baseline": b, "optimized": o,
                    "delta_pct": {k: (round(100 * (o[k] - b[k]) / b[k], 2) if b[k] else 0.0)
                                  for k in ("energy_kwh_day", "co2e_kg_day", "cost_usd_day")},
                    "delta_abs": {k: round(o[k] - b[k], 4) for k in ("mean_latency_ms", "mean_sla_risk")},
                    "changed_workloads": sum(a["changed"] for a in r["assignments"])})
    return out
