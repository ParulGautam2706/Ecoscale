"""What-if simulator. Every scenario for a workload is evaluated with the SAME profile and assumptions
(app.optimization.evaluate), so comparisons are fair. Outputs are ESTIMATES, never measurements."""
from __future__ import annotations

from dataclasses import replace

from sqlalchemy.orm import Session

from app.optimization.evaluate import Ctx, evaluate, load_profiles, make_ctx
from app.optimization.rightsizing import combined_profile
from app.services.energy import InstanceSpec

TYPES = ["current", "reduce_cpu", "reduce_memory", "region", "shift", "instance", "consolidate"]


def _metrics(e) -> dict:
    return {"energy_kwh_day": e.energy_kwh, "co2e_kg_day": e.co2e_kg, "cost_usd_day": e.cost_usd,
            "latency_ms": e.latency_ms, "cpu_util_p95": e.cpu_util_p95, "mem_util_p95": e.mem_util_p95,
            "sla_risk": e.sla_risk, "region": e.region, "instance": e.instance, "offset_h": e.offset_h,
            "constraint_violations": e.violations}


def _delta(base: dict, sc: dict) -> dict:
    d = {}
    for k in ("energy_kwh_day", "co2e_kg_day", "cost_usd_day"):
        d[k + "_pct"] = round(100 * (sc[k] - base[k]) / base[k], 2) if base[k] else 0.0
    d["latency_ms_abs"] = round(sc["latency_ms"] - base["latency_ms"], 2)
    d["sla_risk_abs"] = round(sc["sla_risk"] - base["sla_risk"], 4)
    return d


def _scaled_spec(spec: InstanceSpec, cpu_factor: float = 1.0, mem_factor: float = 1.0) -> InstanceSpec:
    """Approximation: platform power and hourly cost scale with vCPU share; RAM with memory share."""
    return replace(spec, name=f"{spec.name}*", vcpu=max(1, round(spec.vcpu * cpu_factor)), mem_gb=spec.mem_gb * mem_factor,
                   idle_w=spec.idle_w * cpu_factor, peak_w=spec.peak_w * cpu_factor,
                   hourly_cost=spec.hourly_cost * (0.7 * cpu_factor + 0.3 * mem_factor))


def run(db: Session, resource_id: int, scenarios: list[dict]) -> dict:
    ctx = make_ctx(db)
    profiles = load_profiles(db, ctx)
    if resource_id not in profiles:
        raise ValueError("no telemetry for this resource")
    p = profiles[resource_id]
    base_spec = ctx.specs[p.instance]
    base_eval = evaluate(p, base_spec, p.region, 0.0, ctx, enforce=False)
    base = _metrics(base_eval)
    results = [{"name": "Current configuration", "type": "current", "metrics": base, "delta_vs_current": _delta(base, base),
                "assumptions": []}]
    for sc in scenarios:
        t = sc.get("type")
        name = sc.get("name") or t
        assumptions = ["Same telemetry window and demand as the current configuration"]
        spec, region, off = base_spec, p.region, 0.0
        prof = p
        if t == "reduce_cpu":
            f = 1 - float(sc["percent"]) / 100
            if not 0 < f < 1:
                raise ValueError("reduce_cpu.percent must be in (0, 100)")
            spec = _scaled_spec(base_spec, cpu_factor=f)
            assumptions.append("Power and cost scale linearly with vCPU share (approximation)")
        elif t == "reduce_memory":
            f = 1 - float(sc["percent"]) / 100
            if not 0 < f < 1:
                raise ValueError("reduce_memory.percent must be in (0, 100)")
            spec = _scaled_spec(base_spec, mem_factor=f)
        elif t == "region":
            if sc["region"] not in ctx.regions:
                raise ValueError("unknown region")
            region = sc["region"]
            assumptions.append("Instance availability and quotas in the target region are assumed")
        elif t == "shift":
            off = float(sc["offset_hours"])
            if not p.is_flexible:
                assumptions.append("Workload is not flexible: shifting changes nothing (always-on)")
                off = 0.0
        elif t == "instance":
            if sc["instance_type"] not in ctx.specs:
                raise ValueError("unknown instance type")
            spec = ctx.specs[sc["instance_type"]]
        elif t == "consolidate":
            ids = [int(i) for i in sc["resource_ids"]]
            if resource_id not in ids:
                ids.insert(0, resource_id)
            members = [profiles[i] for i in ids if i in profiles]
            prof = combined_profile(members, "consolidated")
            spec = ctx.specs[sc.get("target_instance", p.instance)]
            region = p.region
            before = [evaluate(m, ctx.specs[m.instance], m.region, 0.0, ctx, enforce=False) for m in members]
            ev = evaluate(prof, spec, region, 0.0, ctx, enforce=False)
            m = _metrics(ev)
            btot = {"energy_kwh_day": sum(e.energy_kwh for e in before), "co2e_kg_day": sum(e.co2e_kg for e in before),
                    "cost_usd_day": sum(e.cost_usd for e in before)}
            b2 = {**base, **btot}
            results.append({"name": name, "type": t, "metrics": m, "delta_vs_current": _delta(b2, m),
                            "comparison_basis": f"vs sum of {len(members)} separate workloads",
                            "assumptions": assumptions + ["p95 demands summed (peaks assumed to coincide)"]})
            continue
        elif t != "current":
            raise ValueError(f"unknown scenario type '{t}'; use one of {TYPES}")
        ev = evaluate(prof, spec, region, off, ctx, enforce=False)
        ev.violations = evaluate(prof, spec, region, off, ctx, enforce=True).violations
        m = _metrics(ev)
        results.append({"name": name, "type": t, "metrics": m, "delta_vs_current": _delta(base, m), "assumptions": assumptions})
    return {"resource_id": resource_id, "resource": p.name, "origin": "estimated", "results": results,
            "note": "Trade-offs are shown, not hidden: a scenario may lower carbon while raising latency or SLA risk."}
