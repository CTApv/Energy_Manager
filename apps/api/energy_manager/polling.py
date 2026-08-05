from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timezone
from typing import Any

from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient
from sqlalchemy import select

from .alarms import evaluate_alarm_rules, evaluate_device_health
from .config import get_settings
from .db import SessionLocal
from .decoder import decode_registers
from .models import Connection, Device, DeviceProfile, SyncOutbox, TelemetrySample


# Direct TCP devices own an independent endpoint/session. RTU serial buses and
# RTU-over-TCP gateways instead share one transport and serialize their Unit IDs.
# This avoids connection storms and prevents late gateway replies from being
# matched with a subsequent transaction.
_clients: dict[str, Any] = {}
_client_signatures: dict[str, tuple[Any, ...]] = {}
_connection_locks: dict[str, asyncio.Lock] = {}
_device_cycles: dict[str, int] = {}
settings = get_settings()


def _client_key(connection: Connection, device: Device) -> str:
    return device.id if connection.kind == "modbus_tcp" else connection.id


def _effective_config(connection: Connection, device: Device) -> dict[str, Any]:
    if connection.kind != "modbus_tcp":
        return connection.config
    endpoint = device.config or {}
    return {
        **connection.config,
        **endpoint,
    }


def _signature(connection: Connection, device: Device) -> tuple[Any, ...]:
    config = _effective_config(connection, device)
    return (
        connection.kind,
        config.get("host"), config.get("port"), config.get("baud_rate"),
        config.get("parity"), config.get("stop_bits"), config.get("byte_size"),
        config.get("timeout"), config.get("retry"),
    )


def _new_client(connection: Connection, device: Device):
    config = _effective_config(connection, device)
    if connection.kind in {"modbus_tcp", "modbus_rtu_tcp"}:
        return AsyncModbusTcpClient(
            config["host"],
            port=int(config.get("port", 502)),
            timeout=float(config.get("timeout", 2)),
            retries=int(config.get("retry", 0)),
        )
    if connection.kind == "modbus_rtu":
        return AsyncModbusSerialClient(
            port=config["port"],
            baudrate=int(config.get("baud_rate", 9600)),
            parity=config.get("parity", "N"),
            stopbits=int(config.get("stop_bits", 1)),
            bytesize=int(config.get("byte_size", 8)),
            timeout=float(config.get("timeout", 2)),
            retries=int(config.get("retry", 0)),
        )
    return None


def _pooled_client(connection: Connection, device: Device):
    key = _client_key(connection, device)
    signature = _signature(connection, device)
    client = _clients.get(key)
    if client is None or _client_signatures.get(key) != signature:
        if client is not None:
            client.close()
        client = _new_client(connection, device)
        _clients[key] = client
        _client_signatures[key] = signature
    return client


def build_read_blocks(points: list[dict[str, Any]], max_registers: int = 120) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for function_code in (1, 2, 3, 4):
        candidates = sorted((p for p in points if p["function_code"] == function_code), key=lambda p: p["address"])
        for point in candidates:
            start, end = point["address"], point["address"] + point["register_count"]
            if blocks and blocks[-1]["function_code"] == function_code and start <= blocks[-1]["end"] + 1 and end - blocks[-1]["start"] <= max_registers:
                blocks[-1]["end"] = max(blocks[-1]["end"], end)
                blocks[-1]["points"].append(point)
            else:
                blocks.append({"function_code": function_code, "start": start, "end": end, "points": [point]})
    return blocks


async def _read(client: AsyncModbusTcpClient, function_code: int, address: int, count: int, unit_id: int):
    kwargs = {"address": address, "count": count, "device_id": unit_id}
    if function_code == 1:
        return await client.read_coils(**kwargs)
    if function_code == 2:
        return await client.read_discrete_inputs(**kwargs)
    if function_code == 3:
        return await client.read_holding_registers(**kwargs)
    return await client.read_input_registers(**kwargs)


async def _read_with_session_recovery(
    client: Any,
    connection: Connection,
    device: Device,
    function_code: int,
    address: int,
    count: int,
    unit_id: int,
) -> tuple[Any, Any]:
    """Retry once on a fresh session when a slave corrupts the TCP transaction sequence."""
    try:
        return client, await _read(client, function_code, address, count, unit_id)
    except Exception:
        client_key = _client_key(connection, device)
        try:
            client.close()
        finally:
            _clients.pop(client_key, None)
            _client_signatures.pop(client_key, None)
        replacement = _pooled_client(connection, device)
        if not replacement.connected and not await replacement.connect():
            raise ConnectionError("Modbus reconnect failed")
        return replacement, await _read(replacement, function_code, address, count, unit_id)


def calculate_derived_points(values: dict[str, Any], definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calculate only catalog-declared operations over already normalized values."""
    calculated: list[dict[str, Any]] = []
    for derived in definitions:
        source_values = [values.get(key) for key in derived["sources"]]
        if any(not isinstance(value, (int, float)) for value in source_values):
            continue
        if derived["operation"] == "sum":
            value = sum(source_values)
        elif derived["operation"] == "mean":
            value = sum(source_values) / len(source_values)
        else:
            value = source_values[0] - source_values[1]
        values[derived["key"]] = value
        calculated.append({"key": derived["key"], "value": value, "unit": derived.get("unit", "")})
    return calculated


def sample_quality(key: str, value: Any) -> tuple[str, str | None]:
    """Reject obvious decode/map errors before they reach KPIs and alarms."""
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return "bad", "not_finite"
    numeric = float(value)
    if numeric != 0 and abs(numeric) < 1e-12:
        return "bad", "subnormal_value_register_map_mismatch"
    if ".voltage." in key or key.startswith("electrical.voltage"):
        if numeric != 0 and not 10 <= abs(numeric) <= 1500:
            return "bad", "voltage_out_of_range"
    if key == "electrical.frequency" and numeric != 0 and not 40 <= numeric <= 70:
        return "bad", "frequency_out_of_range"
    if "power_factor" in key and not -1.1 <= numeric <= 1.1:
        return "bad", "power_factor_out_of_range"
    if key in {"storage.soc", "storage.soh", "pv.inverter.efficiency"} and not 0 <= numeric <= 100:
        return "bad", "percentage_out_of_range"
    if "irradiance" in key and not 0 <= numeric <= 2000:
        return "bad", "irradiance_out_of_range"
    if "temperature" in key and not -80 <= numeric <= 200:
        return "bad", "temperature_out_of_range"
    if key in {"pv.voltage.dc", "storage.voltage.dc"} and not 0 <= numeric <= 2000:
        return "bad", "dc_voltage_out_of_range"
    if ".energy." in key and numeric < 0:
        return "bad", "negative_energy_counter"
    return "good", None


async def poll_device(device_id: str, scheduled: bool = False) -> int:
    started = time.monotonic()
    with SessionLocal() as db:
        device = db.get(Device, device_id)
        if not device or not device.active:
            return 0
        connection = db.get(Connection, device.connection_id)
        profile = db.get(DeviceProfile, device.profile_id)
        points = profile.definition["points"]
        if scheduled:
            cycle = _device_cycles.get(device_id, 0)
            _device_cycles[device_id] = cycle + 1
            due_groups = {"fast"}
            if cycle % 6 == 0: due_groups.add("normal")
            if cycle % 60 == 0: due_groups.add("slow")
            points = [point for point in points if point.get("polling_group", "normal") in due_groups]
    if connection.kind not in {"modbus_tcp", "modbus_rtu", "modbus_rtu_tcp"}:
        return 0
    samples: list[dict[str, Any]] = []
    error: str | None = None
    client_key = _client_key(connection, device)
    lock = _connection_locks.setdefault(client_key, asyncio.Lock())
    async with lock:
        client = _pooled_client(connection, device)
        try:
            if not client.connected and not await client.connect():
                raise ConnectionError("Modbus connection failed")
            base = int(profile.definition.get("address_base", 0))
            for block in build_read_blocks(points):
                protocol_unit_id = (
                    int((device.config or {}).get("protocol_unit_id", profile.definition.get("defaults", {}).get("unit_id", 1)))
                    if connection.kind == "modbus_tcp"
                    else device.unit_id
                )
                client, response = await _read_with_session_recovery(
                    client,
                    connection,
                    device,
                    block["function_code"],
                    block["start"] - base,
                    block["end"] - block["start"],
                    protocol_unit_id,
                )
                if response.isError():
                    raise IOError(str(response))
                values = response.bits if block["function_code"] in {1, 2} else response.registers
                for point in block["points"]:
                    offset = point["address"] - block["start"]
                    raw = values[offset: offset + point["register_count"]]
                    samples.append({"key": point["key"], "value": decode_registers(raw, point, resolve_enum=False), "unit": point.get("unit", "")})
            values_by_key = {item["key"]: item["value"] for item in samples}
            samples.extend(calculate_derived_points(values_by_key, profile.definition.get("derived_points", [])))
            for item in samples:
                item["quality"], item["quality_reason"] = sample_quality(item["key"], item["value"])
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            # Never retain a session after a failed recovery: its transaction
            # state is no longer trustworthy even if the socket is still open.
            try:
                client.close()
            finally:
                _clients.pop(client_key, None)
                _client_signatures.pop(client_key, None)
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        device = db.get(Device, device_id)
        device.cycle_duration_ms = round((time.monotonic() - started) * 1000, 2)
        bad_keys = [item["key"] for item in samples if item.get("quality") == "bad"]
        if error:
            device.status = "offline"; device.last_error = error; device.consecutive_errors += 1
            health_sample = TelemetrySample(
                device_id=device.id,
                measurement_key="system.communication.available",
                value=0,
                unit="",
                sample_at=now,
                quality="communication_error",
                error=error[:1000],
                origin="modbus",
            )
            db.add(health_sample); db.flush()
            if settings.sync_enabled:
                db.add(SyncOutbox(event_type="telemetry", payload={"sample_id": health_sample.id, "device_id": device.id, "measurement_key": health_sample.measurement_key, "value": 0, "unit": "", "sample_at": now.isoformat(), "received_at": health_sample.received_at.isoformat(), "quality": health_sample.quality, "error": health_sample.error, "origin": health_sample.origin}))
            evaluate_device_health(db, device, now, error, [])
        else:
            device.status = "degraded" if bad_keys else "online"
            device.last_error = f"DataQualityError: incoherent decoded values for {', '.join(bad_keys[:5])}" if bad_keys else None
            device.consecutive_errors = device.consecutive_errors + 1 if bad_keys else 0
            if any(item.get("quality") == "good" for item in samples): device.last_valid_poll_at = now
            persisted_samples: list[TelemetrySample] = []
            for item in samples:
                sample = TelemetrySample(device_id=device.id, measurement_key=item["key"], value=float(item["value"]) if isinstance(item["value"], (int, float, bool)) else None, unit=item["unit"], sample_at=now, quality=item.get("quality", "good"), origin="modbus")
                db.add(sample); db.flush(); persisted_samples.append(sample)
                if settings.sync_enabled:
                    db.add(SyncOutbox(event_type="telemetry", payload={"sample_id": sample.id, "device_id": device.id, "measurement_key": sample.measurement_key, "value": sample.value, "unit": sample.unit, "sample_at": sample.sample_at.isoformat(), "received_at": sample.received_at.isoformat(), "quality": sample.quality, "origin": sample.origin}))
            evaluate_alarm_rules(db, device, [sample for sample in persisted_samples if sample.quality == "good"], now)
            evaluate_device_health(db, device, now, None, bad_keys)
        db.commit()
    return len(samples)


async def polling_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        with SessionLocal() as db:
            device_ids = list(db.scalars(select(Device.id).where(Device.active.is_(True))))
        await asyncio.gather(*(poll_device(device_id, scheduled=True) for device_id in device_ids), return_exceptions=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=5)
        except TimeoutError:
            pass


def close_clients() -> None:
    for client in list(_clients.values()):
        try:
            client.close()
        except Exception:
            pass
    _clients.clear()
    _client_signatures.clear()
