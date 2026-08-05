import sqlite3

import pytest

from energy_manager.commissioning import validate_connection_config, validate_device_connection_config
from energy_manager.config import Settings
from energy_manager.maintenance import backup_file, create_backup, list_backups


def test_tcp_connection_is_normalized():
    config = validate_connection_config("modbus_tcp", {"host": "192.168.2.108", "port": "5020", "timeout": "5", "retry": "0"})
    assert config == {"port": 5020, "timeout": 5.0, "retry": 0}


@pytest.mark.parametrize(
    "config",
    [
        {"port": 0},
        {"port": 502, "timeout": 60},
        {"port": 502, "retry": 20},
    ],
)
def test_invalid_tcp_connection_is_rejected(config):
    with pytest.raises(ValueError):
        validate_connection_config("modbus_tcp", config)


def test_rtu_connection_is_normalized():
    config = validate_connection_config("modbus_rtu", {"port": "/dev/ttyUSB0", "baud_rate": 19200, "parity": "e", "stop_bits": 1, "byte_size": 8})
    assert config["parity"] == "E" and config["baud_rate"] == 19200


def test_rtu_over_tcp_gateway_is_normalized():
    config = validate_connection_config("modbus_rtu_tcp", {"host": "gateway.local", "port": "5020"})
    assert config["host"] == "gateway.local" and config["port"] == 5020


def test_direct_tcp_endpoint_belongs_to_device():
    config = validate_device_connection_config("modbus_tcp", {"host": "192.168.2.108", "port": "502"})
    assert config == {"host": "192.168.2.108", "port": 502}


@pytest.mark.parametrize("config", [{}, {"host": "http://meter"}, {"host": "meter", "port": 0}])
def test_invalid_device_tcp_endpoint_is_rejected(config):
    with pytest.raises(ValueError):
        validate_device_connection_config("modbus_tcp", config)


def test_sqlite_backup_is_consistent_and_pruned(tmp_path):
    database = tmp_path / "edge.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE telemetry (id INTEGER PRIMARY KEY, value REAL)")
        db.execute("INSERT INTO telemetry(value) VALUES (42.5)")
    settings = Settings(
        edge_database_url=f"sqlite:///{database.as_posix()}",
        backup_directory=str(tmp_path / "backups"),
        backup_retention_count=1,
    )
    manifest = create_backup(settings)
    assert manifest["integrity"] == "ok"
    assert len(manifest["sha256"]) == 64
    assert backup_file(settings, manifest["file"]).is_file()
    assert list_backups(settings)[0]["file"] == manifest["file"]


def test_backup_path_traversal_is_rejected(tmp_path):
    settings = Settings(backup_directory=str(tmp_path))
    with pytest.raises(ValueError):
        backup_file(settings, "../edge.db")


def test_production_rejects_placeholder_secrets():
    with pytest.raises(ValueError, match="Unsafe production configuration"):
        Settings(environment="production", seed_demo=False)


def test_production_accepts_distinct_generated_secrets():
    settings = Settings(
        environment="production",
        seed_demo=False,
        secret_key="A1!secret-key-2026-production-unique-value-0001",
        edge_token="B2!edge-token-2026-production-unique-value-0002",
        webhook_secret="C3!webhook-2026-production-unique-value-0003",
        demo_admin_password="D4!Admin-Commissioning-Password-0004",
    )
    assert settings.environment == "production"
