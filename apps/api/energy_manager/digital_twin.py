from __future__ import annotations

import asyncio
import math
import statistics
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, field_validator
from pymodbus.client import AsyncModbusTcpClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .decoder import decode_registers
from .models import Device, DigitalTwinRun, SyncOutbox, TelemetrySample, utcnow


SCENARIOS = [
    {"id": "residential_sunny", "name": "Villa solare", "description": "Giornata limpida, accumulo in autoconsumo e ricarica serale", "tone": "solar"},
    {"id": "residential_cloudy", "name": "Nuvolosità variabile", "description": "Produzione intermittente e cicli batteria frequenti", "tone": "cloud"},
    {"id": "winter_heat_pump", "name": "Inverno efficiente", "description": "Pompa di calore, poco sole e picchi mattina/sera", "tone": "ice"},
    {"id": "evening_peak", "name": "Picco serale", "description": "EV, cucina e climatizzazione contemporanei", "tone": "peak"},
    {"id": "industrial_shift", "name": "Turno produttivo", "description": "Carico industriale diurno e fotovoltaico di taglia maggiore", "tone": "industry"},
    {"id": "grid_outage", "name": "Blackout controllato", "description": "Rete assente, carichi essenziali alimentati dal microgrid", "tone": "outage"},
]
SCENARIO_IDS = {item["id"] for item in SCENARIOS}
FAULTS = [
    {"id": "offline_units", "name": "Dispositivo offline", "description": "Lo slave selezionato risponde con errore di comunicazione", "value_kind": "units"},
    {"id": "latency_ms", "name": "Latenza elevata", "description": "Ritarda ogni lettura Modbus", "value_kind": "milliseconds"},
    {"id": "frozen", "name": "Registri congelati", "description": "I valori smettono di aggiornarsi", "value_kind": "boolean"},
    {"id": "identical_registers", "name": "Registri tutti uguali", "description": "Riproduce uno slave casuale incoerente", "value_kind": "boolean"},
    {"id": "nan_value", "name": "Valore non numerico", "description": "Inietta NaN nella misura principale", "value_kind": "boolean"},
    {"id": "counter_reset_units", "name": "Reset contatore", "description": "Azzera i totalizzatori degli slave scelti", "value_kind": "units"},
    {"id": "phase_loss", "name": "Perdita fase", "description": "Azzera tensione, corrente e potenza della fase L2", "value_kind": "boolean"},
    {"id": "voltage_unbalance", "name": "Squilibrio tensione", "description": "Porta le tre fasi fuori dal campo nominale", "value_kind": "boolean"},
    {"id": "power_spike", "name": "Picco di potenza", "description": "Moltiplica la potenza del contatore generale", "value_kind": "boolean"},
]
FAULT_IDS = {item["id"] for item in FAULTS}


class ScenarioCommand(BaseModel):
    scenario: str
    time_scale: float = Field(default=60, ge=.1, le=86400)
    virtual_time: datetime | None = None

    @field_validator("scenario")
    @classmethod
    def known_scenario(cls, value: str) -> str:
        if value not in SCENARIO_IDS: raise ValueError("unknown Digital Twin scenario")
        return value


class FaultCommand(BaseModel):
    name: str
    enabled: bool = True
    value: bool | float | list[int] = True
    profiles: list[Literal["meter", "pv", "storage", "ev", "weather"]] = Field(default_factory=lambda: ["meter", "pv", "storage", "ev", "weather"])

    @field_validator("name")
    @classmethod
    def known_fault(cls, value: str) -> str:
        if value not in FAULT_IDS: raise ValueError("unknown Digital Twin fault")
        return value


class StressCommand(BaseModel):
    units: int = Field(default=100, ge=1, le=150)
    cycles: int = Field(default=2, ge=1, le=10)
    mode: Literal["shared_gateway", "bounded_pool"] = "shared_gateway"
    max_connections: int = Field(default=8, ge=1, le=32)
    timeout_seconds: float = Field(default=2, ge=.2, le=10)


async def _request_all(settings: Settings, method: str = "GET", payload: dict | None = None, profiles: list[str] | None = None) -> dict[str, dict]:
    targets = {key: value for key, value in settings.digital_twin_urls.items() if profiles is None or key in profiles}
    async with httpx.AsyncClient(timeout=8) as client:
        async def one(profile: str, url: str) -> tuple[str, dict]:
            started = time.perf_counter()
            try:
                response = await client.request(method, url, json=payload if method != "GET" else None)
                response.raise_for_status()
                return profile, {"reachable": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1), **response.json()}
            except Exception as exc:
                return profile, {"reachable": False, "error": f"{type(exc).__name__}: {exc}"}
        return dict(await asyncio.gather(*(one(profile, url) for profile, url in targets.items())))


async def lab_status(settings: Settings) -> dict:
    services = await _request_all(settings)
    reachable = sum(1 for item in services.values() if item.get("reachable"))
    meter = services.get("meter", {})
    snapshots = [item.get("snapshot", {}) for item in services.values() if item.get("snapshot")]
    max_balance_error = max((abs(float(item.get("balance_error_kw", 0))) for item in snapshots), default=0)
    return {
        "enabled": settings.digital_twin_enabled,
        "healthy": reachable == len(settings.digital_twin_urls),
        "reachable": reachable,
        "total": len(settings.digital_twin_urls),
        "scenario": meter.get("scenario"), "virtual_time": meter.get("virtual_time"), "time_scale": meter.get("time_scale"),
        "faults": meter.get("faults", {}), "snapshot": meter.get("snapshot", {}), "balance_error_kw": max_balance_error,
        "services": services, "scenarios": SCENARIOS, "fault_catalog": FAULTS,
    }


async def apply_scenario(settings: Settings, command: ScenarioCommand) -> dict:
    payload = {"action": "reset", "scenario": command.scenario, "time_scale": command.time_scale}
    if command.virtual_time: payload["virtual_time"] = command.virtual_time.astimezone(timezone.utc).isoformat()
    else: payload["virtual_time"] = "2026-06-21T06:00:00+00:00"
    return await _request_all(settings, "POST", payload)


async def apply_fault(settings: Settings, command: FaultCommand) -> dict:
    return await _request_all(settings, "POST", {"action": "fault", "name": command.name, "enabled": command.enabled, "value": command.value}, command.profiles)


async def reset_lab(settings: Settings) -> dict:
    return await _request_all(settings, "POST", {"action": "reset", "scenario": "residential_sunny", "time_scale": 60, "virtual_time": "2026-06-21T06:00:00+00:00"})


async def clear_faults(settings: Settings) -> dict:
    return await _request_all(settings, "POST", {"action": "clear_faults"})


async def run_stress(settings: Settings, command: StressCommand) -> dict:
    host, port = settings.digital_twin_modbus_host, settings.digital_twin_modbus_port
    latencies: list[float] = []; values: list[float] = []; errors: list[str] = []
    started = time.perf_counter(); connection_count = 1 if command.mode == "shared_gateway" else min(command.max_connections, command.units)
    queues = [[] for _ in range(connection_count)]
    for index, unit in enumerate(range(1, command.units + 1)):
        queues[index % connection_count].append(unit)

    async def worker(units: list[int]) -> None:
        client = AsyncModbusTcpClient(host, port=port, timeout=command.timeout_seconds, retries=0)
        try:
            if not await client.connect(): raise ConnectionError("Modbus connect failed")
            for _ in range(command.cycles):
                for unit in units:
                    tick = time.perf_counter()
                    try:
                        response = await client.read_holding_registers(address=100, count=2, device_id=unit)
                        if response.isError(): raise IOError(str(response))
                        values.append(float(decode_registers(response.registers, {"data_type": "float32", "register_count": 2})))
                        latencies.append((time.perf_counter() - tick) * 1000)
                    except Exception as exc: errors.append(f"unit {unit}: {type(exc).__name__}: {exc}")
        except Exception as exc: errors.append(f"connection: {type(exc).__name__}: {exc}")
        finally: client.close()

    await asyncio.gather(*(worker(queue) for queue in queues))
    elapsed = time.perf_counter() - started; expected = command.units * command.cycles; distinct = len({round(value, 4) for value in values})
    return {
        "mode": command.mode, "units": command.units, "cycles": command.cycles, "connections_opened": connection_count,
        "requests_expected": expected, "requests_ok": len(values), "requests_failed": len(errors), "success_percent": round(len(values) / expected * 100, 2),
        "duration_seconds": round(elapsed, 3), "requests_per_second": round(len(values) / elapsed, 1) if elapsed else 0,
        "latency_ms": {"min": round(min(latencies), 2) if latencies else None, "mean": round(statistics.mean(latencies), 2) if latencies else None, "p95": round(sorted(latencies)[min(len(latencies)-1, math.ceil(len(latencies)*.95)-1)], 2) if latencies else None, "max": round(max(latencies), 2) if latencies else None},
        "distinct_values": distinct, "coherence_warning": "all_registers_identical" if len(values) >= 10 and distinct <= 1 else None,
        "errors": errors[:20], "passed": len(errors) == 0 and distinct > 1,
    }


def qualification_snapshot(db: Session, status: dict) -> dict:
    devices = list(db.scalars(select(Device).where(Device.status != "removed")))
    online = sum(1 for item in devices if item.status == "online")
    samples = db.scalar(select(func.count()).select_from(TelemetrySample)) or 0
    pending = db.scalar(select(func.count()).select_from(SyncOutbox).where(SyncOutbox.sent_at.is_(None))) or 0
    checks = [
        {"id": "services", "label": "Simulatori raggiungibili", "passed": status.get("healthy", False), "detail": f"{status.get('reachable', 0)}/{status.get('total', 0)} servizi"},
        {"id": "balance", "label": "Bilancio energetico coerente", "passed": abs(status.get("balance_error_kw", 999)) < .01, "detail": f"errore {status.get('balance_error_kw', 0):.4f} kW"},
        {"id": "devices", "label": "Dispositivi acquisiti", "passed": online > 0, "detail": f"{online}/{len(devices)} online"},
        {"id": "history", "label": "Storico alimentato", "passed": samples > 0, "detail": f"{samples} campioni"},
        {"id": "outbox", "label": "Outbox sotto controllo", "passed": pending < 10000, "detail": f"{pending} eventi in attesa"},
    ]
    return {"passed": all(item["passed"] for item in checks), "score": round(sum(item["passed"] for item in checks) / len(checks) * 100), "checks": checks, "generated_at": utcnow().isoformat()}


def complete_run(db: Session, run: DigitalTwinRun, result: dict) -> dict:
    run.result = result; run.status = "passed" if result.get("passed") else "failed"; run.completed_at = utcnow(); db.commit()
    return {"id": run.id, "kind": run.kind, "scenario": run.scenario, "status": run.status, "parameters": run.parameters, "result": run.result, "started_at": run.started_at, "completed_at": run.completed_at}
