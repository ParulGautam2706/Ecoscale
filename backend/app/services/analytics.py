"""Aggregations for dashboard, carbon analytics and cost pages. Every response states data origin."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.entities import RecStatus, Recommendation
from app.optimization.evaluate import evaluate, load_profiles, make_ctx
from app.services.carbon import CarbonProvider
from app.services.data import instance_specs, region_table, telemetry_df


def utc(ts) -> str | None:
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).isoformat() + "Z"


def window(db: Session, region=None, days: int | None = 7, start=None, end=None) -> pd.DataFrame:
    df = telemetry_df(db, region=region)
    if df.empty:
        return df
    end_ts = pd.Timestamp(end) if end else df["ts"].max()
    start_ts = pd.Timestamp(start) if start else end_ts - pd.Timedelta(days=days or 7)
    df = df[(df["ts"] >= start_ts) & (df["ts"] <= end_ts)].copy()
    specs, regs = instance_specs(db), region_table(db)
    price = df["region_code"].map({k: v["price_multiplier"] for k, v in regs.items()})
    df["cost_usd"] = df["instance_type"].map(lambda n: specs[n].hourly_cost) * price * df["interval_s"] / 3600.0
    return df


def origin_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"telemetry": [], "energy": [], "contains_simulated": False}
    return {"telemetry": sorted(df["data_origin"].unique().tolist()), "energy": sorted(df["energy_method"].unique().tolist()),
            "contains_simulated": bool((df["data_origin"] == "simulated").any()),
            "mean_confidence": round(float(df["confidence"].mean()), 2)}


def summary(db: Session, region=None, days=7, start=None, end=None) -> dict:
    from app.core.config import settings
    df = window(db, region, days, start, end)
    carbon = CarbonProvider(db)
    ci = [{"region": r, "latest_g_per_kwh": round(float(carbon.series(r).iloc[-1]), 1),
           "mean_g_per_kwh": round(float(carbon.series(r).mean()), 1)} for r in sorted(carbon.regions())
          if not region or r == region]
    recs = db.query(Recommendation).filter(Recommendation.status != RecStatus.rejected).all()
    if df.empty:
        return {"empty": True, "data_mode": settings.data_mode, "carbon_intensity_by_region": ci,
                "message": "No telemetry yet. Seed simulated data or ingest telemetry."}
    trend = (df.set_index("ts").resample("D").agg({"facility_kwh": "sum", "co2e_kg": "sum", "cost_usd": "sum"}).reset_index())
    hourly = (df.set_index("ts").resample("h").agg({"facility_kwh": "sum", "co2e_kg": "sum", "cpu": "mean", "mem": "mean"}).reset_index())
    pending = [r for r in recs if r.status == RecStatus.pending]
    last_ts = df["ts"].max()
    return {
        "empty": False, "data_mode": settings.data_mode, "origin": origin_summary(df),
        "window": {"start": utc(df["ts"].min()), "end": utc(last_ts), "region": region},
        "totals": {"energy_kwh": round(float(df["facility_kwh"].sum()), 3), "co2e_kg": round(float(df["co2e_kg"].sum()), 3),
                   "cost_usd": round(float(df["cost_usd"].sum()), 2)},
        "avg_cpu": round(float(df["cpu"].mean()), 4), "avg_mem": round(float(df["mem"].mean()), 4),
        "opportunities": {"count": len(pending), "potential_co2e_kg_month": round(sum(r.savings.get("co2e_kg_month", 0) for r in pending), 2),
                          "potential_cost_usd_month": round(sum(r.savings.get("cost_usd_month", 0) for r in pending), 2)},
        "carbon_intensity_by_region": ci,
        "energy_trend_daily": [{"ts": utc(r.ts), "energy_kwh": round(r.facility_kwh, 3), "co2e_kg": round(r.co2e_kg, 3)} for r in trend.itertuples()],
        "energy_trend_hourly": [{"ts": utc(r.ts), "energy_kwh": round(r.facility_kwh, 4), "co2e_kg": round(r.co2e_kg, 4)} for r in hourly.itertuples()],
        "recent_recommendations": [{"id": r.id, "type": r.rec_type, "rationale": r.rationale, "risk": r.risk,
                                    "co2e_kg_month": r.savings.get("co2e_kg_month"), "cost_usd_month": r.savings.get("cost_usd_month")}
                                   for r in sorted(pending, key=lambda r: -r.id)[:5]],
        "health": {"database": "ok", "latest_telemetry": utc(last_ts), "resources": int(df["resource_id"].nunique()),
                   "samples": int(len(df))},
    }


def carbon_timeseries(db, region=None, freq="h", days=7) -> dict:
    df = window(db, region, days)
    if df.empty:
        return {"series": [], "origin": origin_summary(df)}
    rs = df.set_index("ts").resample(freq).agg({"facility_kwh": "sum", "co2e_kg": "sum"}).reset_index()
    return {"series": [{"ts": utc(r.ts), "energy_kwh": round(r.facility_kwh, 4), "co2e_kg": round(r.co2e_kg, 4)} for r in rs.itertuples()],
            "origin": origin_summary(df)}


def by_region(db, days=7) -> dict:
    df = window(db, None, days)
    if df.empty:
        return {"regions": [], "origin": origin_summary(df)}
    g = df.groupby("region_code").agg(energy_kwh=("facility_kwh", "sum"), co2e_kg=("co2e_kg", "sum"), cost_usd=("cost_usd", "sum"),
                                      resources=("resource_id", "nunique")).reset_index()
    g["g_per_kwh_effective"] = g["co2e_kg"] * 1000 / g["energy_kwh"]
    return {"regions": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()} for r in g.to_dict("records")],
            "origin": origin_summary(df)}


def by_workload(db, days=7) -> dict:
    df = window(db, None, days)
    if df.empty:
        return {"workloads": [], "origin": origin_summary(df)}
    g = df.groupby(["resource_id", "resource", "region_code", "instance_type"]).agg(
        energy_kwh=("facility_kwh", "sum"), co2e_kg=("co2e_kg", "sum"), cost_usd=("cost_usd", "sum"),
        avg_cpu=("cpu", "mean"), avg_mem=("mem", "mean"), confidence=("confidence", "mean")).reset_index()
    return {"workloads": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
                          for r in g.sort_values("co2e_kg", ascending=False).to_dict("records")], "origin": origin_summary(df)}


def before_after(db) -> dict:
    ctx = make_ctx(db)
    profiles = load_profiles(db, ctx)
    if not profiles:
        return {"empty": True}
    per = {rid: evaluate(p, ctx.specs[p.instance], p.region, 0.0, ctx, enforce=False) for rid, p in profiles.items()}
    base = {"energy_kwh_day": sum(e.energy_kwh for e in per.values()), "co2e_kg_day": sum(e.co2e_kg for e in per.values()),
            "cost_usd_day": sum(e.cost_usd for e in per.values())}
    recs = db.query(Recommendation).filter(Recommendation.status != RecStatus.rejected).all()
    sv = {k: sum(r.savings.get(k, 0) for r in recs) for k in base}
    after = {k: max(base[k] - sv[k], 0.0) for k in base}
    return {"empty": False, "baseline_per_day": {k: round(v, 3) for k, v in base.items()},
            "after_per_day": {k: round(v, 3) for k, v in after.items()},
            "reduction_pct": {k: round(100 * (base[k] - after[k]) / base[k], 2) if base[k] else 0.0 for k in base},
            "recommendations_counted": len(recs),
            "note": "Estimated; assumes every non-rejected recommendation is applied. Not a measured outcome.",
            "origin": "estimated"}


def cost_summary(db, days=7) -> dict:
    df = window(db, None, days)
    if df.empty:
        return {"empty": True}
    by_res = df.groupby("resource").agg(cost_usd=("cost_usd", "sum"), co2e_kg=("co2e_kg", "sum")).reset_index().sort_values("cost_usd", ascending=False)
    by_reg = df.groupby("region_code").agg(cost_usd=("cost_usd", "sum")).reset_index()
    daily = df.set_index("ts").resample("D")["cost_usd"].sum().reset_index()
    pending = db.query(Recommendation).filter(Recommendation.status == RecStatus.pending).all()
    return {"empty": False, "total_usd": round(float(df["cost_usd"].sum()), 2),
            "by_resource": [{"resource": r.resource, "cost_usd": round(r.cost_usd, 2), "co2e_kg": round(r.co2e_kg, 2)} for r in by_res.itertuples()],
            "by_region": [{"region": r.region_code, "cost_usd": round(r.cost_usd, 2)} for r in by_reg.itertuples()],
            "daily": [{"ts": utc(r.ts), "cost_usd": round(r.cost_usd, 2)} for r in daily.itertuples()],
            "potential_savings_usd_month": round(sum(r.savings.get("cost_usd_month", 0) for r in pending), 2),
            "pricing_note": "Flat on-demand prices from the instance catalogue x regional multiplier (illustrative).",
            "origin": origin_summary(df)}
