from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from energy_manager.db import Base
from energy_manager.energy_reporting import IMPORT_KEY, POWER_KEY, build_energy_report, counter_usage, period_bounds
from energy_manager.models import AssetNode, Connection, Device, DeviceProfile, EnergySettings, MeasurementBinding, TelemetrySample


def sample(device: str, key: str, value: float, stamp: datetime, unit: str = "kWh") -> TelemetrySample:
    return TelemetrySample(device_id=device, measurement_key=key, value=value, unit=unit, sample_at=stamp, quality="good")


def test_month_comparison_uses_same_elapsed_calendar_window():
    now = datetime(2026, 5, 15, 10, tzinfo=timezone.utc)
    start, end, previous_start, previous_end = period_bounds("month", "Europe/Rome", now)
    assert start == datetime(2026, 4, 30, 22, tzinfo=timezone.utc)
    assert end == now
    assert previous_start == datetime(2026, 3, 31, 22, tzinfo=timezone.utc)
    assert previous_end - previous_start == end - start


def test_counter_reset_is_preserved_as_estimated_energy():
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    rows = [sample("meter", IMPORT_KEY, 98, start - timedelta(minutes=1)), sample("meter", IMPORT_KEY, 3, start + timedelta(minutes=1)), sample("meter", IMPORT_KEY, 8, start + timedelta(minutes=2))]
    result = counter_usage(rows, start, start + timedelta(hours=1))
    assert result["value"] == 8
    assert result["quality"] == "estimated"
    assert result["resets"] == 1


def test_report_calculates_cost_emissions_comparison_and_breakdown():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    now = datetime(2026, 5, 15, 10, tzinfo=timezone.utc)
    start, _, previous_start, _ = period_bounds("month", "Europe/Rome", now)
    with Session(engine) as db:
        db.add_all([
            EnergySettings(import_price_per_kwh=.25, export_price_per_kwh=.1, co2_kg_per_kwh=.3, contracted_power_kw=50, monthly_energy_budget_kwh=200, monthly_cost_budget=60, timezone="Europe/Rome", workday_start="08:00", workday_end="18:00", working_days=[0, 1, 2, 3, 4]),
            Connection(id="connection", name="LAN", kind="modbus_tcp", config={}),
            DeviceProfile(id="meter-profile", version="1", definition={"category": "multimeter"}, valid=True),
            Device(id="main", connection_id="connection", profile_id="meter-profile", name="Generale", unit_id=1, active=True),
            Device(id="line", connection_id="connection", profile_id="meter-profile", name="Linea presse", unit_id=2, active=True),
            AssetNode(id="root", name="Generale", category="meter"),
            AssetNode(id="press", parent_id="root", name="Presse", category="line"),
            MeasurementBinding(asset_id="root", device_id="main", measurement_key=IMPORT_KEY, role="primary"),
            MeasurementBinding(asset_id="press", device_id="line", measurement_key=IMPORT_KEY, role="primary"),
        ])
        db.add_all([
            sample("main", IMPORT_KEY, 100, start - timedelta(minutes=1)),
            sample("main", IMPORT_KEY, 110, start + timedelta(hours=1)),
            sample("main", IMPORT_KEY, 150, now),
            sample("main", IMPORT_KEY, 70, previous_start - timedelta(minutes=1)),
            sample("main", IMPORT_KEY, 90, previous_start + timedelta(hours=3)),
            sample("line", IMPORT_KEY, 20, start - timedelta(minutes=1)),
            sample("line", IMPORT_KEY, 45, now),
            sample("main", POWER_KEY, 22, start + timedelta(hours=1), "kW"),
            sample("main", POWER_KEY, 55, start + timedelta(hours=1, seconds=20), "kW"),
        ])
        db.commit()
        report = build_energy_report(db, db.query(EnergySettings).one(), "month", now)

    assert report["energy"]["import_kwh"] == 50
    assert report["economics"]["energy_cost"] == 12.5
    assert report["environment"]["co2_kg"] == 15
    assert report["comparison"]["previous_import_kwh"] == 20
    assert report["comparison"]["energy_change_percent"] == 150
    assert report["breakdown"][0]["energy_kwh"] == 25
    assert report["energy"]["unattributed_kwh"] == 25
    assert report["power"]["contract_exceeded"] is True
