from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from energy_manager.contracts import IngestBatchEnvelope, SyncEvent, TariffInput
from energy_manager.control_room import allowed_edge_ids, portfolio
from energy_manager.db import Base
from energy_manager.main import as_dict
from energy_manager.models import Edge, EnergyTariff, RemoteDevice, Site, TelemetryRollup, Tenant
from energy_manager.rollups import minute_bucket, update_minute_rollups
from energy_manager.tariffs import price_increments


def memory_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def event(value: float, second: int = 5, quality: str = "good") -> SyncEvent:
    stamp = datetime(2026, 8, 5, 10, 1, second, tzinfo=timezone.utc)
    return SyncEvent(event_id=f"00000000-0000-4000-8000-{second:012d}", sample_id=f"10000000-0000-4000-8000-{second:012d}", device_id="20000000-0000-4000-8000-000000000001", measurement_key="electrical.active_power.total", value=value, unit="kW", sample_at=stamp, received_at=stamp, quality=quality)


def test_ingest_contract_rejects_unknown_schema_and_short_edge_id():
    with pytest.raises(ValidationError):
        IngestBatchEnvelope.model_validate({"schema_version": "2.0", "batch_id": "batch-00000000000", "edge_id": "short", "created_at": datetime.now(timezone.utc), "status": {}, "events": []})


def test_rollup_aggregates_quality_and_statistics():
    with memory_db() as db:
        update_minute_rollups(db, "edge-0000000000000000000000000000000", [event(10), event(20, 20), event(30, 30, "stale")])
        db.commit()
        row = db.scalar(select(TelemetryRollup))
        assert row.sample_count == 3 and row.good_count == 2
        assert row.minimum == 10 and row.maximum == 30 and row.average == 20 and row.last_value == 30
        assert row.bucket_start == minute_bucket(event(10).sample_at).replace(tzinfo=None)


def test_effective_dated_tariff_overrides_default_price():
    with memory_db() as db:
        db.add(EnergyTariff(name="F1", valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc), weekdays=[0, 1, 2, 3, 4], start_minute=480, end_minute=1140, import_price_per_kwh=.31, export_price_per_kwh=.11, priority=10, active=True))
        db.commit()
        result = price_increments(db, [(datetime(2026, 8, 5, 10, tzinfo=timezone.utc), 10)], ZoneInfo("Europe/Rome"), .2)
        assert result["total"] == pytest.approx(3.1)
        assert result["breakdown"][0]["tariff"] == "F1"


def test_tariff_contract_rejects_inverted_window():
    with pytest.raises(ValidationError):
        TariffInput(name="F1", valid_from=datetime.now(timezone.utc), start_minute=900, end_minute=800, import_price_per_kwh=.2)


def test_serialization_never_exposes_enrollment_hash():
    edge = Edge(name="Edge", site_id="site", token_hash="secret-hash")
    assert "token_hash" not in as_dict(edge)


def test_control_room_portfolio_is_tenant_scoped():
    with memory_db() as db:
        first = Tenant(id="tenant-a", name="A", slug="tenant-a")
        second = Tenant(id="tenant-b", name="B", slug="tenant-b")
        db.add_all([first, second]); db.flush()
        db.add_all([Site(id="site-a", tenant_id=first.id, name="Site A"), Site(id="site-b", tenant_id=second.id, name="Site B")]); db.flush()
        db.add_all([Edge(id="00000000-0000-4000-8000-000000000001", site_id="site-a", name="Edge A", token_hash="x", status="online"), Edge(id="00000000-0000-4000-8000-000000000002", site_id="site-b", name="Edge B", token_hash="x", status="online")]); db.flush()
        db.add_all([RemoteDevice(edge_id="00000000-0000-4000-8000-000000000001", local_device_id="device-a", name="Meter A"), RemoteDevice(edge_id="00000000-0000-4000-8000-000000000002", local_device_id="device-b", name="Meter B")]); db.commit()
        assert allowed_edge_ids(db, "customer_admin", "tenant-a") == ["00000000-0000-4000-8000-000000000001"]
        scoped = portfolio(db, "customer_admin", "tenant-a")
        assert scoped["tenants"] == 1 and scoped["sites"] == 1 and scoped["edges"] == 1 and scoped["devices"] == 1
