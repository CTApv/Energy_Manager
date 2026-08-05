from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SyncEvent(BaseModel):
    event_id: str = Field(min_length=36, max_length=36)
    sample_id: str = Field(min_length=36, max_length=36)
    device_id: str = Field(min_length=36, max_length=36)
    measurement_key: str = Field(min_length=3, max_length=160)
    value: float | None = None
    unit: str = Field(default="", max_length=30)
    sample_at: datetime
    received_at: datetime
    quality: Literal["good", "stale", "invalid", "communication_error", "estimated", "missing"] = "good"
    error: str | None = Field(default=None, max_length=1000)
    origin: str = Field(default="modbus", max_length=100)


class RemoteDeviceSnapshot(BaseModel):
    id: str
    name: str = Field(max_length=160)
    category: str = Field(default="device", max_length=60)
    manufacturer: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=100)
    profile_id: str = Field(default="", max_length=100)
    profile_version: str = Field(default="", max_length=30)
    status: str = Field(default="unknown", max_length=30)


class EdgeStatusSnapshot(BaseModel):
    hostname: str = Field(default="", max_length=255)
    app_version: str = Field(default="", max_length=30)
    configuration_version: str = Field(default="", max_length=80)
    backlog_count: int = Field(default=0, ge=0)
    disk_free_percent: float | None = Field(default=None, ge=0, le=100)
    devices: list[RemoteDeviceSnapshot] = Field(default_factory=list, max_length=5000)


class IngestBatchEnvelope(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    batch_id: str = Field(min_length=16, max_length=100)
    edge_id: str = Field(min_length=36, max_length=36)
    created_at: datetime
    status: EdgeStatusSnapshot
    events: list[SyncEvent] = Field(max_length=1000)


class TenantInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")


class SiteInput(BaseModel):
    tenant_id: str
    name: str = Field(min_length=2, max_length=160)


class EdgeInput(BaseModel):
    site_id: str
    name: str = Field(min_length=2, max_length=160)
    hostname: str = Field(default="", max_length=255)


class TariffInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    valid_from: datetime
    valid_to: datetime | None = None
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)), min_length=1)
    start_minute: int = Field(default=0, ge=0, le=1439)
    end_minute: int = Field(default=1440, ge=1, le=1440)
    import_price_per_kwh: float = Field(ge=0)
    export_price_per_kwh: float = Field(default=0, ge=0)
    priority: int = Field(default=0, ge=0, le=1000)
    active: bool = True

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("weekdays must contain values from 0 to 6")
        return sorted(set(value))

    @model_validator(mode="after")
    def valid_window(self) -> "TariffInput":
        if self.end_minute <= self.start_minute:
            raise ValueError("end_minute must be greater than start_minute")
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        return self


class BaselineInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    measurement_key: str = Field(default="electrical.energy.import_total", min_length=3, max_length=160)
    device_id: str | None = None
    period_start: datetime
    period_end: datetime
    baseline_value: float = Field(gt=0)
    unit: str = Field(default="kWh", max_length=30)
    normalization: dict[str, Any] = Field(default_factory=dict)
    active: bool = True

    @model_validator(mode="after")
    def valid_period(self) -> "BaselineInput":
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be later than period_start")
        return self
