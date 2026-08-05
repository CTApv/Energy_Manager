from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from energy_manager.alarms import evaluate_alarm_rules, evaluate_device_health
from energy_manager.db import Base
from energy_manager.models import AlarmEvent, AlarmRule, Device, TelemetrySample


def test_threshold_opens_once_and_clears_with_deadband():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        device = Device(id="device-1", connection_id="connection-1", profile_id="profile-1", name="Main", unit_id=1)
        rule = AlarmRule(name="High power", kind="measurement_above", config={"measurement_key": "electrical.active_power.total", "threshold": 100, "deadband": 5}, severity="high", active=True)
        db.add_all([device, rule]); db.flush()
        high = TelemetrySample(device_id=device.id, measurement_key="electrical.active_power.total", value=105, unit="kW", sample_at=now)
        evaluate_alarm_rules(db, device, [high], now)
        db.flush()
        event = db.scalar(select(AlarmEvent))
        assert event.status == "open"

        # A value inside the hysteresis band must keep the same event active.
        evaluate_alarm_rules(db, device, [TelemetrySample(device_id=device.id, measurement_key=high.measurement_key, value=98, unit="kW", sample_at=now)], now)
        db.flush()
        assert db.scalar(select(AlarmEvent)).status == "open"
        assert len(list(db.scalars(select(AlarmEvent)))) == 1

        evaluate_alarm_rules(db, device, [TelemetrySample(device_id=device.id, measurement_key=high.measurement_key, value=94, unit="kW", sample_at=now)], now)
        db.flush()
        assert db.scalar(select(AlarmEvent)).status == "closed"


def test_repeated_communication_failure_opens_and_recovers_system_alarm():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        device = Device(id="device-health", connection_id="connection-1", profile_id="profile-1", name="Main", unit_id=1, consecutive_errors=3)
        db.add(device); db.flush()
        evaluate_device_health(db, device, now, "TimeoutError", [])
        db.flush()
        event = db.scalar(select(AlarmEvent).where(AlarmEvent.measurement_key == "system.communication.available"))
        assert event.status == "open" and event.severity == "high"
        device.consecutive_errors = 0
        evaluate_device_health(db, device, now, None, [])
        db.flush()
        assert event.status == "closed" and event.closed_at == now
