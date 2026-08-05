from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from energy_manager.main import (
    DeviceInput,
    DeviceProvisioningInput,
    DeviceRemovalInput,
    ProvisioningPlacementInput,
    delete_device,
    device_removal_impact,
    provision_device,
)
from energy_manager.models import AssetNode, Base, Connection, Device, DeviceProfile, MeasurementBinding, TelemetrySample, User, utcnow


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
    asset = AssetNode(name="Ecosistema", category="site")
    db.add(asset); db.flush()
    db.add(MeasurementBinding(asset_id=asset.id, device_id=device.id, measurement_key="electrical.active_power.total", role="primary"))
    db.add(TelemetrySample(device_id=device.id, measurement_key="electrical.active_power.total", value=12.5, unit="kW", sample_at=utcnow()))
    db.commit()
    return db, device, user


def test_removal_preserves_history_by_default():
    db, device, user = lifecycle_session()
    impact = device_removal_impact(device.id, user, db)
    assert impact["samples"] == 1 and impact["history_preserved_by_default"] is True
    result = delete_device(device.id, DeviceRemovalInput(), user, db)
    assert result["history_purged"] is False
    assert result["bindings_removed"] == 1
    assert db.get(Device, device.id).status == "removed"
    assert db.scalar(select(MeasurementBinding).where(MeasurementBinding.device_id == device.id)) is None
    assert db.scalar(select(TelemetrySample).where(TelemetrySample.device_id == device.id)) is not None
    db.close()


def test_removal_can_purge_history():
    db, device, user = lifecycle_session()
    result = delete_device(device.id, DeviceRemovalInput(purge_history=True), user, db)
    assert result["samples_removed"] == 1
    assert db.scalar(select(TelemetrySample).where(TelemetrySample.device_id == device.id)) is None
    db.close()


def test_guided_provisioning_creates_device_asset_and_primary_binding_atomically():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    connection = Connection(name="Gateway", kind="modbus_tcp", config={"host": "192.168.2.108", "port": 5020})
    profile = DeviceProfile(
        id="test-meter",
        version="1",
        definition={
            "protocols": ["modbus_tcp"],
            "points": [{"key": "electrical.active_power.total"}],
        },
        valid=True,
    )
    user = User(username="commissioner", password_hash="unused", role="technician")
    db.add_all([connection, profile, user])
    db.flush()

    result = provision_device(
        DeviceProvisioningInput(
            device=DeviceInput(
                connection_id=connection.id,
                profile_id=profile.id,
                name="Contatore generale",
                config={"host": "192.168.2.108", "port": 5020},
            ),
            placement=ProvisioningPlacementInput(name="Punto di consegna", category="grid"),
            measurement_key="electrical.active_power.total",
        ),
        user,
        db,
    )

    assert result["device"]["name"] == "Contatore generale"
    assert result["asset"]["category"] == "grid"
    assert result["binding"]["role"] == "primary"
    assert db.scalar(select(Device).where(Device.name == "Contatore generale")) is not None
    assert db.scalar(select(MeasurementBinding).where(MeasurementBinding.device_id == result["device"]["id"])) is not None
    db.close()
