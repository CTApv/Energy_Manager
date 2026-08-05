from __future__ import annotations

import asyncio
import json
import math
import os
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.server import StartAsyncTcpServer


STATE = {"anomaly": False, "unattributed_percent": 18.0, "reset_unit": None, "offline_units": [], "started": time.time()}
DEVICES: dict[int, ModbusDeviceContext] = {}


def float_registers(value: float) -> list[int]:
    payload = struct.pack(">f", value)
    return list(struct.unpack(">HH", payload))


def uint32_registers(value: int) -> list[int]:
    payload = struct.pack(">I", value & 0xFFFFFFFF)
    return list(struct.unpack(">HH", payload))


def create_device() -> ModbusDeviceContext:
    return ModbusDeviceContext(hr=ModbusSequentialDataBlock(0, [0] * 1000), ir=ModbusSequentialDataBlock(0, [0] * 1000), di=ModbusSequentialDataBlock(0, [0] * 1000), co=ModbusSequentialDataBlock(0, [0] * 1000))


def update_values() -> None:
    elapsed = time.time() - STATE["started"]
    wave = math.sin(elapsed / 30)
    general = (102 if STATE["anomaly"] else 86) + 8 * wave
    attributed = max(0.1, 1 - float(STATE["unattributed_percent"]) / 100)
    powers = {1: general, 2: general * attributed * 0.54, 3: general * attributed * 0.46, 4: 18 + 4 * wave}
    for unit, context in DEVICES.items():
        power = powers[unit]
        base_energy = {1: 125000, 2: 55000, 3: 47000, 4: 19000}[unit]
        energy = 0 if STATE["reset_unit"] == unit else int((base_energy + power * elapsed / 3600) * 100)
        context.setValues(3, 100, float_registers(power))
        context.setValues(3, 110, uint32_registers(energy))
        context.setValues(3, 120, float_registers(230 + 2 * wave))
        context.setValues(3, 122, float_registers(power * 1000 / (230 * 3)))
        context.setValues(3, 124, float_registers(0.94 + 0.02 * wave))
        context.setValues(3, 126, float_registers(50 + 0.03 * wave))


class ControlHandler(BaseHTTPRequestHandler):
    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self) -> None:
        self._reply(200, STATE)

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0")); payload = json.loads(self.rfile.read(size) or b"{}")
        allowed = {"anomaly", "unattributed_percent", "reset_unit", "offline_units"}
        STATE.update({key: value for key, value in payload.items() if key in allowed})
        self._reply(200, STATE)

    def log_message(self, format: str, *args) -> None:
        return


def start_control_server() -> None:
    port = int(os.getenv("SIMULATOR_CONTROL_PORT", "18090"))
    ThreadingHTTPServer(("0.0.0.0", port), ControlHandler).serve_forever()


async def updater() -> None:
    while True:
        update_values()
        await asyncio.sleep(1)


async def main() -> None:
    for unit in range(1, 5): DEVICES[unit] = create_device()
    threading.Thread(target=start_control_server, daemon=True).start()
    asyncio.create_task(updater())
    print("Energy Manager Modbus simulator: TCP :5020, controls HTTP :18090", flush=True)
    await StartAsyncTcpServer(context=ModbusServerContext(devices=DEVICES, single=False), address=("0.0.0.0", 5020))


if __name__ == "__main__":
    asyncio.run(main())
