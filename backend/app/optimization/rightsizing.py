"""Rule detectors (paper thresholds, now configurable): idle resources and consolidation groups."""
from __future__ import annotations

import pandas as pd

from app.optimization.evaluate import Ctx, Evaluation, Profile, evaluate, family
from app.services.energy import InstanceSpec


def detect_idle(df: pd.DataFrame, profiles: dict[int, Profile], ctx: Ctx) -> set[int]:
    t = ctx.thr
    win = max(1, int(round(t["rolling_window_min"] * 60 / float(df["interval_s"].median()))))
    out = set()
    for rid, sub in df.groupby("resource_id"):
        p = profiles.get(rid)
        if p is None or p.is_flexible:
            continue
        sub = sub.sort_values("ts")
        rc = sub["cpu"].rolling(win, min_periods=1).mean()
        rn = sub["net_mbit_s"].fillna(0).rolling(win, min_periods=1).mean()
        frac = float(((rc < t["idle_cpu"]) & (rn < t["idle_net_mbit_s"])).mean())
        if frac >= t["idle_sustained_fraction"]:
            out.add(int(rid))
    return out


def find_consolidations(profiles: dict[int, Profile], ctx: Ctx, exclude: set[int]) -> list[dict]:
    """Greedy first-fit-decreasing over underutilised always-on workloads in the same region.
    Uses the SUM of p95 demands (conservative: assumes peaks may coincide)."""
    t = ctx.thr
    cands = [p for rid, p in profiles.items() if rid not in exclude and not p.is_flexible and p.gpu_mean < 0.05
             and p.cpu_util_mean < t["alpha_cpu"] and p.mem_util_mean < t["beta_mem"]
             and p.sustained_underuse >= t["sustained_fraction"]]
    groups: list[dict] = []
    by_region: dict[str, list[Profile]] = {}
    for p in cands:
        by_region.setdefault(p.region, []).append(p)
    for region, items in by_region.items():
        items.sort(key=lambda p: -p.cores_p95)
        remaining = list(items)
        while len(remaining) >= 2:
            members = [remaining.pop(0)]
            target = None
            for q in list(remaining):
                trial = members + [q]
                fit = _smallest_fit(trial, ctx)
                if fit:
                    members, target = trial, fit
                    remaining.remove(q)
            if len(members) >= 2 and target:
                groups.append({"region": region, "members": members, "target": target})
    return groups


def _smallest_fit(members: list[Profile], ctx: Ctx) -> InstanceSpec | None:
    cores = sum(m.cores_p95 for m in members)
    mem = sum(m.mem_gb_p95 for m in members)
    for spec in family(ctx, members[0].instance):
        if cores <= ctx.thr["max_cpu_p95_after"] * spec.vcpu and mem <= ctx.thr["max_mem_p95_after"] * spec.mem_gb:
            return spec
    return None


def combined_profile(members: list[Profile], name: str) -> Profile:
    f = members[0]
    return Profile(
        resource_id=f.resource_id, name=name, region=f.region, instance=f.instance, is_flexible=False,
        deadline_hours=None, sla_latency_ms=min([m.sla_latency_ms for m in members if m.sla_latency_ms] or [None]) if any(m.sla_latency_ms for m in members) else None,
        cores_mean=sum(m.cores_mean for m in members), cores_p95=sum(m.cores_p95 for m in members),
        mem_gb_mean=sum(m.mem_gb_mean for m in members), mem_gb_p95=sum(m.mem_gb_p95 for m in members),
        gpu_mean=0.0, net_mean=sum(m.net_mean for m in members), disk_mean=sum(m.disk_mean for m in members),
        job_hours=24.0, start_hour_utc=0.0, hours_observed=min(m.hours_observed for m in members),
        burstiness=max(m.burstiness for m in members), cpu_util_mean=0.0, mem_util_mean=0.0,
        sustained_underuse=min(m.sustained_underuse for m in members), n=min(m.n for m in members))


def evaluate_consolidation(group: dict, ctx: Ctx) -> tuple[Evaluation, list[Evaluation]]:
    members: list[Profile] = group["members"]
    before = [evaluate(m, ctx.specs[m.instance], m.region, 0.0, ctx, enforce=False) for m in members]
    after = evaluate(combined_profile(members, "+".join(m.name for m in members)), group["target"],
                     group["region"], 0.0, ctx, enforce=False)
    return after, before
