"""Shared what-if evaluator: energy, carbon, cost, latency and SLA risk for (workload, instance, region, start).
Used by right-sizing, carbon-aware scheduling, multi-objective optimisation and the simulator,
so all of them use IDENTICAL assumptions."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.defaults import region_latency
from app.services import settings_service
from app.services.carbon import CarbonProvider
from app.services.data import instance_specs, region_table, resources_df
from app.services.energy import EnergyConfig, InstanceSpec, estimate


@dataclass
class Ctx:
    carbon: CarbonProvider
    regions: dict
    specs: dict
    cfg: EnergyConfig
    limits: dict
    thr: dict
    weights: dict


def make_ctx(db: Session) -> Ctx:
    s = settings_service.get_all(db)
    return Ctx(CarbonProvider(db), region_table(db), instance_specs(db), EnergyConfig.from_dict(s["energy"]),
               s["limits"], s["thresholds"], s["weights"])


@dataclass
class Profile:
    resource_id: int
    name: str
    region: str
    instance: str
    is_flexible: bool
    deadline_hours: float | None
    sla_latency_ms: float | None
    cores_mean: float
    cores_p95: float
    mem_gb_mean: float
    mem_gb_p95: float
    gpu_mean: float
    net_mean: float
    disk_mean: float
    job_hours: float            # hours/day the workload is active (24 for always-on)
    start_hour_utc: float
    hours_observed: float
    burstiness: float
    cpu_util_mean: float        # on the CURRENT instance
    mem_util_mean: float
    sustained_underuse: float   # share of samples with rolling-mean cpu<alpha and mem<beta
    n: int


def build_profiles(df: pd.DataFrame, ctx: Ctx, only: list[int] | None = None) -> dict[int, Profile]:
    res = resources_df_cached(df)
    out: dict[int, Profile] = {}
    win = max(1, int(round(ctx.thr["rolling_window_min"] * 60 / float(df["interval_s"].median()))))
    for rid, sub in df.groupby("resource_id"):
        if only and rid not in only:
            continue
        r = res[rid]
        spec = ctx.specs[r["instance_type"]]
        sub = sub.sort_values("ts")
        cpu, mem = sub["cpu"], sub["mem"]
        roll_c, roll_m = cpu.rolling(win, min_periods=1).mean(), mem.rolling(win, min_periods=1).mean()
        under = float(((roll_c < ctx.thr["alpha_cpu"]) & (roll_m < ctx.thr["beta_mem"])).mean())
        flex = bool(r["is_flexible"])
        sel, job_hours, start_h = sub, 24.0, 0.0
        if flex:
            thr = max(0.15, 0.3 * float(cpu.quantile(0.99)))
            act = cpu > thr
            if act.any():
                sel = sub[act]
                job_hours = max(0.5, float(act.mean()) * 24.0)
                starts = sub.loc[act & ~act.shift(1, fill_value=False), "ts"].dt.hour
                start_h = float(starts.mode().iloc[0]) if len(starts) else float(sel["ts"].dt.hour.iloc[0])
        c = sel["cpu"]
        m = sel["mem"]
        p99, mean = float(c.quantile(0.99)), float(c.mean())
        out[rid] = Profile(
            resource_id=int(rid), name=r["name"], region=r["region_code"], instance=r["instance_type"],
            is_flexible=flex, deadline_hours=r["deadline_hours"], sla_latency_ms=r["sla_latency_ms"],
            cores_mean=mean * spec.vcpu, cores_p95=float(c.quantile(0.95)) * spec.vcpu,
            mem_gb_mean=float(m.mean()) * spec.mem_gb, mem_gb_p95=float(m.quantile(0.95)) * spec.mem_gb,
            gpu_mean=float(sel["gpu"].fillna(0).mean()), net_mean=float(sel["net_mbit_s"].fillna(0).mean()),
            disk_mean=float(sel["disk_mb_s"].fillna(0).mean()), job_hours=job_hours, start_hour_utc=start_h,
            hours_observed=len(sub) * float(sub["interval_s"].median()) / 3600.0,
            burstiness=float(np.clip((p99 - mean) / (p99 + 1e-9), 0, 1)),
            cpu_util_mean=mean, mem_util_mean=float(m.mean()), sustained_underuse=under, n=len(sub))
    return out


def resources_df_cached(df: pd.DataFrame) -> dict:
    g = df.groupby("resource_id").first()
    return {int(i): {"name": row["resource"], "region_code": row["region_code"], "instance_type": row["instance_type"],
                     "is_flexible": bool(row["is_flexible"]),
                     "deadline_hours": None, "sla_latency_ms": None} for i, row in g.iterrows()}


def attach_resource_meta(profiles: dict[int, Profile], db: Session) -> dict[int, Profile]:
    meta = resources_df(db).set_index("id")
    for rid, p in profiles.items():
        row = meta.loc[rid]
        p.deadline_hours = None if pd.isna(row["deadline_hours"]) else float(row["deadline_hours"])
        p.sla_latency_ms = None if pd.isna(row["sla_latency_ms"]) else float(row["sla_latency_ms"])
    return profiles


def load_profiles(db: Session, ctx: Ctx, df: pd.DataFrame | None = None, only: list[int] | None = None):
    from app.services.data import telemetry_df
    df = telemetry_df(db) if df is None else df
    if df.empty:
        return {}
    return attach_resource_meta(build_profiles(df, ctx, only), db)


@dataclass
class Evaluation:
    resource_id: int
    instance: str
    region: str
    offset_h: float
    vcpu: int
    energy_kwh: float
    co2e_kg: float
    cost_usd: float
    latency_ms: float
    cpu_util_mean: float
    cpu_util_p95: float
    mem_util_p95: float
    sla_risk: float
    ci_g_per_kwh: float
    feasible: bool = True
    violations: list = field(default_factory=list)
    J: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: (round(v, 5) if isinstance(v, float) else v) for k, v in d.items()}


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-12.0 * (x - 0.85)))


def evaluate(p: Profile, spec: InstanceSpec, region: str, offset_h: float, ctx: Ctx,
             enforce: bool = True) -> Evaluation:
    hours = p.job_hours if p.is_flexible else 24.0
    util_mean = min(p.cores_mean / spec.vcpu, 1.0)
    util_p95 = p.cores_p95 / spec.vcpu
    mem_mean = min(p.mem_gb_mean / spec.mem_gb, 1.0)
    mem_p95 = p.mem_gb_p95 / spec.mem_gb
    reg = ctx.regions[region]
    ci = (ctx.carbon.window_mean(region, p.start_hour_utc + offset_h, hours) if p.is_flexible
          else ctx.carbon.daily_mean(region))
    est = estimate(spec, util_mean, mem_mean, hours * 3600.0, ci, gpu=p.gpu_mean if spec.gpu_count else None,
                   net_mbit_s=p.net_mean, disk_mb_s=p.disk_mean, pue=reg["pue"], cfg=ctx.cfg)
    cost = spec.hourly_cost * reg["price_multiplier"] * hours
    if region != p.region:
        cost += ctx.limits["data_gb"] * ctx.limits["transfer_usd_per_gb"] / ctx.limits["amortize_days"]
    latency = region_latency(p.region, region) + 100.0 * float(np.clip((util_p95 - 0.7) / 0.3, 0, 3))
    limit = p.sla_latency_ms or (math.inf if p.is_flexible else ctx.limits["default_latency_limit_ms"])
    lat_risk = min(latency / limit, 1.0) ** 4 if math.isfinite(limit) else 0.0
    risk = max(_sig(util_p95), _sig(mem_p95), lat_risk)
    viol = []
    cpu_limit = ctx.thr["max_cpu_p95_after_batch"] if p.is_flexible else ctx.thr["max_cpu_p95_after"]
    if util_p95 > cpu_limit:
        viol.append("cpu_p95_above_limit")
    if mem_p95 > ctx.thr["max_mem_p95_after"]:
        viol.append("mem_p95_above_limit")
    if latency > limit:
        viol.append("latency_above_sla")
    if spec.gpu_count < (1 if p.gpu_mean > 0.05 else 0):
        viol.append("gpu_required")
    if p.is_flexible and p.deadline_hours is not None and offset_h + hours > p.deadline_hours + 1e-9:
        viol.append("deadline_missed")
    return Evaluation(p.resource_id, spec.name, region, float(offset_h), spec.vcpu, float(est.facility_kwh),
                      float(est.co2e_kg), float(cost), float(latency), float(util_mean), float(util_p95),
                      float(mem_p95), float(risk), float(ci), feasible=(not viol) or not enforce, violations=viol)


def family(ctx: Ctx, instance: str) -> list[InstanceSpec]:
    fam = instance.split(".")[0]
    return sorted([s for s in ctx.specs.values() if s.name.split(".")[0] == fam], key=lambda s: s.vcpu)


def candidates(p: Profile, ctx: Ctx, regions: list[str] | None = None, allow_shift: bool = True,
               allow_upsize: bool | None = None) -> list[Evaluation]:
    base = ctx.specs[p.instance]
    if allow_upsize is None:   # upsizing is only considered when the CURRENT setup already violates a constraint
        allow_upsize = bool(evaluate(p, base, p.region, 0.0, ctx).violations)
    offsets = [0.0]
    if p.is_flexible and allow_shift and p.deadline_hours:
        room = min(p.deadline_hours, ctx.limits["max_shift_hours"] + p.job_hours) - p.job_hours
        offsets = [float(h) for h in range(0, int(max(room, 0)) + 1)]
    out = []
    for spec in family(ctx, p.instance):
        if spec.vcpu > base.vcpu and not allow_upsize:
            continue
        for region in (regions or list(ctx.regions)):
            for off in offsets:
                e = evaluate(p, spec, region, off, ctx)
                is_base = spec.name == base.name and region == p.region and off == 0.0
                if e.feasible or is_base:
                    if is_base:
                        e.feasible = True
                    out.append(e)
    return out


def score(evals: list[Evaluation], weights: dict, base: Evaluation, lat_ref_ms: float) -> None:
    """Baseline-relative normalisation (avoids min-max amplifying trivial differences):
         C = CO2e / CO2e_base,  K = cost / cost_base,  L = latency / SLA reference,  R = SLA risk (already 0-1)
       J = w1*C + w2*K + w3*L + w4*R.   J(baseline) = w1 + w2 + w3*L_base + w4*R_base."""
    for e in evals:
        c = e.co2e_kg / base.co2e_kg if base.co2e_kg > 1e-12 else 1.0
        k = e.cost_usd / base.cost_usd if base.cost_usd > 1e-12 else 1.0
        l = e.latency_ms / lat_ref_ms
        e.J = float(weights["carbon"] * c + weights["cost"] * k + weights["latency"] * l + weights["sla"] * e.sla_risk)


def latency_reference(p: Profile, ctx: Ctx) -> float:
    return float(p.sla_latency_ms or ctx.limits["default_latency_limit_ms"])
