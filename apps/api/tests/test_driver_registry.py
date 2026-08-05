from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from energy_manager.models import Base, DeviceProfile
from energy_manager.seed import seed_catalog


def test_driver_registry_loads_nested_files_with_source_provenance():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)

    definitions = seed_catalog(db, edge_mode=True)

    assert "siemens-sentron-pac2200" in definitions
    assert "schneider-iem3000-modbus" in definitions
    assert definitions["schneider-iem3000-modbus"]["driver"]["source_file"] == (
        "drivers/multimeters/schneider-acti9-iem3000.yaml"
    )
    assert definitions["huawei-sun2000-lb0-luna"]["driver"]["compatibility_group"] == (
        "huawei-sun2000-lb0-luna"
    )
    assert db.scalar(select(DeviceProfile).where(DeviceProfile.id == "abb-terra-ac-wallbox")) is not None
    db.close()
