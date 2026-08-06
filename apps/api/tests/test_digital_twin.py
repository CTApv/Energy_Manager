import json

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import energy_manager.digital_twin as digital_twin
from energy_manager.config import Settings
from energy_manager.db import Base
from energy_manager.digital_twin import ScenarioCommand, StressCommand, lab_status, qualification_snapshot, run_stress


def settings() -> Settings:
    return Settings(
        environment="test",
        digital_twin_enabled=True,
        digital_twin_control_urls="meter=http://meter,pv=http://pv,storage=http://storage,ev=http://ev,weather=http://weather",
        digital_twin_modbus_host="simulator",
    )


def test_scenario_contract_rejects_unknown_or_unsafe_acceleration():
    with pytest.raises(ValidationError):
        ScenarioCommand(scenario="invented")
    with pytest.raises(ValidationError):
        ScenarioCommand(scenario="residential_sunny", time_scale=100_000)


@pytest.mark.asyncio
async def test_lab_status_reports_shared_balance_and_partial_outage(monkeypatch):
    async def fake_request_all(*_args, **_kwargs):
        snapshot = {"balance_error_kw": 0.0, "site_load_kw": 4.2, "pv_kw": 3.1, "storage_kw": 0.4, "grid_kw": 0.7}
        return {
            "meter": {"reachable": True, "scenario": "residential_sunny", "virtual_time": "2026-06-21T12:00:00+00:00", "time_scale": 60, "faults": {}, "snapshot": snapshot},
            "pv": {"reachable": True, "snapshot": snapshot},
            "storage": {"reachable": True, "snapshot": snapshot},
            "ev": {"reachable": True, "snapshot": snapshot},
            "weather": {"reachable": False, "error": "timeout"},
        }

    monkeypatch.setattr(digital_twin, "_request_all", fake_request_all)
    result = await lab_status(settings())
    assert result["healthy"] is False
    assert result["reachable"] == 4 and result["total"] == 5
    assert result["balance_error_kw"] == 0


@pytest.mark.asyncio
async def test_stress_uses_bounded_connections_and_distinct_units(monkeypatch):
    opened = []

    class Response:
        def __init__(self, unit):
            self.registers = [0x3F80 + unit, 0]

        def isError(self):
            return False

    class Client:
        def __init__(self, *_args, **_kwargs):
            opened.append(self)

        async def connect(self):
            return True

        async def read_holding_registers(self, *, address, count, device_id):
            assert address == 100 and count == 2
            return Response(device_id)

        def close(self):
            pass

    monkeypatch.setattr(digital_twin, "AsyncModbusTcpClient", Client)
    result = await run_stress(settings(), StressCommand(units=25, cycles=2, mode="bounded_pool", max_connections=6))
    assert len(opened) == result["connections_opened"] == 6
    assert result["requests_ok"] == 50 and result["requests_failed"] == 0
    assert result["distinct_values"] > 1 and result["passed"] is True


def test_production_configuration_cannot_enable_the_lab():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            digital_twin_enabled=True,
            secret_key="safe-secret-key-abcdefghijklmnop",
            edge_token="safe-edge-token-abcdefghijklmnop",
            webhook_secret="safe-webhook-token-abcdefghijkl",
            demo_admin_password="safe-admin-password-ABCDEFGHI",
        )


def test_qualification_result_is_persistable_json():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        result = qualification_snapshot(db, {"healthy": True, "reachable": 5, "total": 5, "balance_error_kw": 0})
    assert json.loads(json.dumps(result))["generated_at"].endswith("+00:00")
