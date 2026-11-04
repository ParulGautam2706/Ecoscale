"""ORM schema. Every numeric telemetry/energy row carries its provenance."""
import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


def _now():
    return datetime.now(timezone.utc)


class DataOrigin(str, enum.Enum):
    measured = "measured"
    estimated = "estimated"
    simulated = "simulated"
    predicted = "predicted"


class Role(str, enum.Enum):
    admin = "admin"
    analyst = "analyst"


class RecStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.analyst)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Region(Base):
    __tablename__ = "regions"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    pue: Mapped[float] = mapped_column(Float, default=1.58)
    price_multiplier: Mapped[float] = mapped_column(Float, default=1.0)


class CarbonIntensity(Base):
    __tablename__ = "carbon_intensity"
    id: Mapped[int] = mapped_column(primary_key=True)
    region_code: Mapped[str] = mapped_column(ForeignKey("regions.code"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    g_per_kwh: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64))
    is_forecast: Mapped[bool] = mapped_column(Boolean, default=False)


class InstanceType(Base):
    __tablename__ = "instance_types"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    vcpu: Mapped[int] = mapped_column(Integer)
    mem_gb: Mapped[float] = mapped_column(Float)
    gpu_count: Mapped[int] = mapped_column(Integer, default=0)
    idle_w: Mapped[float] = mapped_column(Float)
    peak_w: Mapped[float] = mapped_column(Float)
    hourly_cost: Mapped[float] = mapped_column(Float)


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    region_code: Mapped[str] = mapped_column(ForeignKey("regions.code"))
    instance_type: Mapped[str] = mapped_column(ForeignKey("instance_types.name"))
    is_flexible: Mapped[bool] = mapped_column(Boolean, default=False)
    deadline_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    sla_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class TelemetrySample(Base):
    __tablename__ = "telemetry_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    interval_s: Mapped[float] = mapped_column(Float, default=60.0)
    cpu: Mapped[float] = mapped_column(Float)          # fraction 0-1
    mem: Mapped[float] = mapped_column(Float)          # fraction 0-1
    gpu: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_mbit_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_mb_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_origin: Mapped[DataOrigin] = mapped_column(Enum(DataOrigin))


class EnergyEstimate(Base):
    __tablename__ = "energy_estimates"
    id: Mapped[int] = mapped_column(primary_key=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey("telemetry_samples.id"), index=True)
    it_kwh: Mapped[float] = mapped_column(Float)
    facility_kwh: Mapped[float] = mapped_column(Float)
    co2e_kg: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)   # 0-1
    method: Mapped[DataOrigin] = mapped_column(Enum(DataOrigin))
    assumptions: Mapped[dict] = mapped_column(JSON, default=dict)


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(64))
    split_strategy: Mapped[str] = mapped_column(String(64))
    metrics: Mapped[dict] = mapped_column(JSON)
    is_proxy_label: Mapped[bool] = mapped_column(Boolean, default=True)
    artifact_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id"))


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), index=True)
    rec_type: Mapped[str] = mapped_column(String(32))  # rightsize|shift|region|idle|consolidate
    rationale: Mapped[str] = mapped_column(Text)
    savings: Mapped[dict] = mapped_column(JSON, default=dict)
    risk: Mapped[str] = mapped_column(String(16), default="medium")
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[RecStatus] = mapped_column(Enum(RecStatus), default=RecStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Simulation(Base):
    __tablename__ = "simulations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    scenario: Mapped[dict] = mapped_column(JSON)
    results: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Anomaly(Base):
    __tablename__ = "anomalies"
    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metric: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="open")


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
