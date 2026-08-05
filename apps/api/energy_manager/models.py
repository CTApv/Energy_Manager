import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uuid4() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Quality(str, enum.Enum):
    good = "good"
    stale = "stale"
    invalid = "invalid"
    communication_error = "communication_error"
    estimated = "estimated"
    missing = "missing"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)


class Site(Base, TimestampMixin):
    __tablename__ = "sites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))


class Edge(Base, TimestampMixin):
    __tablename__ = "edges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    hostname: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(30), default="offline")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_hash: Mapped[str] = mapped_column(String(255), default="")
    app_version: Mapped[str] = mapped_column(String(30), default="0.5.1")


class Role(Base, TimestampMixin):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="administrator")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LocalSite(Base, TimestampMixin):
    __tablename__ = "local_sites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))


class EnergySettings(Base, TimestampMixin):
    __tablename__ = "energy_settings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    import_price_per_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    export_price_per_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    co2_kg_per_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    contracted_power_kw: Mapped[float | None] = mapped_column(Float)
    monthly_energy_budget_kwh: Mapped[float | None] = mapped_column(Float)
    monthly_cost_budget: Mapped[float | None] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Rome")
    workday_start: Mapped[str] = mapped_column(String(5), default="08:00")
    workday_end: Mapped[str] = mapped_column(String(5), default="18:00")
    working_days: Mapped[list] = mapped_column(JSON, default=lambda: [0, 1, 2, 3, 4])


class SystemPreference(Base, TimestampMixin):
    __tablename__ = "system_preferences"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Connection(Base, TimestampMixin):
    __tablename__ = "connections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="unknown")
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class CatalogProfile(Base, TimestampMixin):
    __tablename__ = "catalog_profiles"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    manufacturer: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(60))
    latest_version: Mapped[str] = mapped_column(String(30))


class CatalogProfileVersion(Base, TimestampMixin):
    __tablename__ = "catalog_profile_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    profile_id: Mapped[str] = mapped_column(ForeignKey("catalog_profiles.id"), index=True)
    version: Mapped[str] = mapped_column(String(30))
    definition: Mapped[dict] = mapped_column(JSON)
    valid: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (UniqueConstraint("profile_id", "version"),)


class DeviceProfile(Base, TimestampMixin):
    __tablename__ = "device_profiles"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[str] = mapped_column(String(30))
    definition: Mapped[dict] = mapped_column(JSON)
    valid: Mapped[bool] = mapped_column(Boolean, default=False)


class RegisterDefinition(Base, TimestampMixin):
    __tablename__ = "register_definitions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    profile_id: Mapped[str] = mapped_column(ForeignKey("device_profiles.id"), index=True)
    key: Mapped[str] = mapped_column(String(160))
    definition: Mapped[dict] = mapped_column(JSON)


class MeasurementDefinition(Base, TimestampMixin):
    __tablename__ = "measurement_definitions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(160), unique=True)
    label: Mapped[str] = mapped_column(String(160))
    unit: Mapped[str] = mapped_column(String(30), default="")


class Device(Base, TimestampMixin):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    connection_id: Mapped[str] = mapped_column(ForeignKey("connections.id"), index=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("device_profiles.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    unit_id: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="unknown")
    last_valid_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)
    cycle_duration_ms: Mapped[float | None] = mapped_column(Float)


class AssetNode(Base, TimestampMixin):
    __tablename__ = "asset_nodes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("asset_nodes.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60), default="asset")
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class MeasurementBinding(Base, TimestampMixin):
    __tablename__ = "measurement_bindings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    asset_id: Mapped[str] = mapped_column(ForeignKey("asset_nodes.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    measurement_key: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(30), default="primary")
    __table_args__ = (UniqueConstraint("asset_id", "device_id", "measurement_key"),)


class TelemetrySample(Base):
    __tablename__ = "telemetry_samples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    device_id: Mapped[str] = mapped_column(String(36), index=True)
    measurement_key: Mapped[str] = mapped_column(String(160), index=True)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30), default="")
    sample_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    quality: Mapped[str] = mapped_column(String(30), default=Quality.good.value)
    error: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(100), default="modbus")
    source_sample_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (Index("ix_sample_device_key_time", "device_id", "measurement_key", "sample_at"),)


class KpiDefinition(Base, TimestampMixin):
    __tablename__ = "kpi_definitions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(60))
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class KpiResult(Base):
    __tablename__ = "kpi_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    definition_id: Mapped[str | None] = mapped_column(ForeignKey("kpi_definitions.id"))
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("asset_nodes.id"))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30), default="")
    quality: Mapped[str] = mapped_column(String(30), default=Quality.good.value)
    reason: Mapped[str | None] = mapped_column(Text)


class AlarmRule(Base, TimestampMixin):
    __tablename__ = "alarm_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(60))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AlarmEvent(Base, TimestampMixin):
    __tablename__ = "alarm_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    rule_id: Mapped[str | None] = mapped_column(ForeignKey("alarm_rules.id"))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="open")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("asset_nodes.id"))
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"))
    measurement_key: Mapped[str | None] = mapped_column(String(160))
    value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text)


class SyncOutbox(Base):
    __tablename__ = "sync_outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class EdgeActivation(Base, TimestampMixin):
    __tablename__ = "edge_activations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    edge_id: Mapped[str] = mapped_column(ForeignKey("edges.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TailscaleNode(Base, TimestampMixin):
    __tablename__ = "tailscale_nodes"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    edge_id: Mapped[str | None] = mapped_column(ForeignKey("edges.id"), index=True)
    hostname: Mapped[str] = mapped_column(String(255))
    ip: Mapped[str] = mapped_column(String(64), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(100))
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class IngestedBatch(Base):
    __tablename__ = "ingested_batches"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    edge_id: Mapped[str] = mapped_column(String(36), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
