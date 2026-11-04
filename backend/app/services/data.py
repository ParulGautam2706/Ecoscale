"""Loaders that return analysis-ready DataFrames. All timestamps are naive UTC."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import EnergyEstimate, InstanceType, Region, Resource, TelemetrySample
from app.services.energy import InstanceSpec


def instance_specs(db: Session) -> dict[str, InstanceSpec]:
    return {i.name: InstanceSpec(i.name, i.vcpu, i.mem_gb, i.idle_w, i.peak_w, i.hourly_cost, i.gpu_count)
            for i in db.query(InstanceType).all()}


def region_table(db: Session) -> dict[str, dict]:
    return {r.code: {"name": r.name, "pue": r.pue, "price_multiplier": r.price_multiplier}
            for r in db.query(Region).all()}


def telemetry_df(db: Session, region: str | None = None, start=None, end=None,
                 resource_ids: list[int] | None = None) -> pd.DataFrame:
    q = (select(TelemetrySample.id.label("sample_id"), TelemetrySample.resource_id, TelemetrySample.ts,
                TelemetrySample.interval_s, TelemetrySample.cpu, TelemetrySample.mem, TelemetrySample.gpu,
                TelemetrySample.net_mbit_s, TelemetrySample.disk_mb_s,
                TelemetrySample.data_origin.label("data_origin"),
                Resource.name.label("resource"), Resource.region_code, Resource.instance_type,
                Resource.is_flexible,
                EnergyEstimate.it_kwh, EnergyEstimate.facility_kwh, EnergyEstimate.co2e_kg,
                EnergyEstimate.confidence, EnergyEstimate.method.label("energy_method"))
         .join(Resource, Resource.id == TelemetrySample.resource_id)
         .join(EnergyEstimate, EnergyEstimate.sample_id == TelemetrySample.id, isouter=True))
    if region:
        q = q.where(Resource.region_code == region)
    if start:
        q = q.where(TelemetrySample.ts >= start)
    if end:
        q = q.where(TelemetrySample.ts <= end)
    if resource_ids:
        q = q.where(TelemetrySample.resource_id.in_(resource_ids))
    df = pd.read_sql(q.order_by(TelemetrySample.ts), db.connection())
    df["ts"] = pd.to_datetime(df["ts"])
    if len(df):
        df["data_origin"] = df["data_origin"].astype(str).str.replace("DataOrigin.", "", regex=False)
        df["energy_method"] = df["energy_method"].astype(str).str.replace("DataOrigin.", "", regex=False)
    return df


def resources_df(db: Session) -> pd.DataFrame:
    rows = db.query(Resource).all()
    return pd.DataFrame([{"id": r.id, "name": r.name, "region_code": r.region_code,
                          "instance_type": r.instance_type, "is_flexible": r.is_flexible,
                          "deadline_hours": r.deadline_hours, "sla_latency_ms": r.sla_latency_ms} for r in rows])
