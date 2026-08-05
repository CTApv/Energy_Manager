from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from energy_manager.main import DeviceRemovalInput, delete_device, device_removal_impact
from energy_manager.models import Base, Connection, Device, DeviceProfile, MeasurementBinding, TelemetrySample, User, utcnow


def lifecycle_session() -> tuple[Session, Device, User]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    connection = Connection(name="Test", kind="modbus_tcp", config={"host": "192.168.2.108", "port": 502})
    profile = DeviceProfile(id="test-meter", version="1", definition={"protocols": ["modbus_tcp"]}, valid=True)
    user = User(username="commissioner", password_hash="unused", role="technician")
    db.add_all([connection, profile, user]); db.flush()
    device = Device(connection_id=connection.id, profile_id=profile.id, name="Contatore linea", unit_id=7)
    db.add(device); db.flush()
    db.add(TelemetrySample(device_id=device.id, measurement_key="electrical.active_power.total", value=12.5, unit="kW", sample_at=utcnow()))
    db.commit()
    return db, device, user


def test_removal_preserves_history_by_default():
    db, device, user = lifecycle_session()
    impact = device_removal_impact(device.id, user, db)
    assert impact["samples"] == 1 and impact["history_preserved_by_default"] is True
    result = delete_device(device.id, DeviceRemovalInput(confirm_name=device.name), user, db)
    assert result["history_purged"] is False
    assert db.get(Device, device.id).status == "removed"
    assert db.scalar(select(TelemetrySample).where(TelemetrySample.device_id == device.id)) is not None
    db.close()


def test_removal_can_purge_history():
    db, device, user = lifecycle_session()
    result = delete_device(device.id, DeviceRemovalInput(confirm_name=device.name, purge_history=True), user, db)
    assert result["samples_removed"] == 1
    assert db.scalar(select(TelemetrySample).where(TelemetrySample.device_id == device.id)) is None
    db.close()
