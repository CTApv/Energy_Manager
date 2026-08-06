from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from energy_manager.db import Base
import energy_manager.main as main


def test_system_status_reuses_inventory_cache(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    calls = {"network": 0, "serial": 0}

    def network():
        calls["network"] += 1
        return [{"name": "eth0", "state": "up", "addresses": []}]

    def serial():
        calls["serial"] += 1
        return []

    monkeypatch.setattr(main, "network_interfaces", network)
    monkeypatch.setattr(main, "serial_ports", serial)
    monkeypatch.setattr(main, "storage_capacity", lambda _settings: {"total_bytes": 1024**3, "used_bytes": 0, "free_bytes": 1024**3, "free_percent": 100})
    monkeypatch.setattr(main, "runtime_summary", lambda: {"hostname": "edge", "operating_system": "test", "os_release": "1", "architecture": "x64", "python": "3.13"})
    main._system_status_cache.update(expires_at=0.0, value=None)

    with Session(engine) as db:
        first = main.system_status_value(db)
        second = main.system_status_value(db)

    assert first is second
    assert first["database"] == "ok" and first["database_check"] == "connectivity"
    assert calls == {"network": 1, "serial": 1}
    main._system_status_cache.update(expires_at=0.0, value=None)
