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


PROFILE = os.getenv("SIMULATOR_PROFILE", "meter").strip().lower()
MODBUS_PORT = int(os.getenv("SIMULATOR_PORT", "5020"))
CONTROL_PORT = int(os.getenv("SIMULATOR_CONTROL_PORT", "18090"))
SUPPORTED_PROFILES = {"meter", "pv", "storage", "ev", "weather"}
if PROFILE not in SUPPORTED_PROFILES:
    raise RuntimeError(f"Unsupported SIMULATOR_PROFILE={PROFILE!r}")

STATE = {
    "profile": PROFILE,
    "anomaly": False,
    "unattributed_percent": 18.0,
    "reset_unit": None,
    "offline_units": [],
    "started": time.time(),
}
DEVICES: dict[int, ModbusDeviceContext] = {}


def registers(fmt: str, value: float | int) -> list[int]:
    payload = struct.pack(">" + fmt, value)
    return list(struct.unpack(">" + "H" * (len(payload) // 2), payload))


def f32(value: float) -> list[int]:
    return registers("f", float(value))


def u16(value: int) -> list[int]:
    return registers("H", int(value) & 0xFFFF)


def u32(value: int) -> list[int]:
    return registers("I", int(value) & 0xFFFFFFFF)


def u64(value: int) -> list[int]:
    return registers("Q", int(value) & 0xFFFFFFFFFFFFFFFF)


def create_device() -> ModbusDeviceContext:
    block = lambda: ModbusSequentialDataBlock(0, [0] * 1000)
    return ModbusDeviceContext(hr=block(), ir=block(), di=block(), co=block())


def write(context: ModbusDeviceContext, values: dict[int, list[int]]) -> None:
    for address, payload in values.items():
        context.setValues(3, address, payload)


def update_meter(context: ModbusDeviceContext, elapsed: float, unit: int) -> None:
    wave = math.sin(elapsed / 24 + unit * 0.4)
    total_kw = ({1: 86, 2: 38, 3: 32, 4: 18}.get(unit, 20) + 5 * wave) * (1.18 if STATE["anomaly"] else 1)
    pf = 0.955 + 0.018 * math.sin(elapsed / 31 + unit)
    apparent = total_kw / pf
    reactive = math.sqrt(max(apparent**2 - total_kw**2, 0))
    phase_share = [0.34, 0.33, 0.33]
    phase_power = [total_kw * share for share in phase_share]
    phase_reactive = [reactive * share for share in phase_share]
    phase_apparent = [apparent * share for share in phase_share]
    voltages = [230.4 + 1.8 * wave, 229.8 + 1.2 * math.sin(elapsed / 27 + 2), 231.1 + 1.5 * math.sin(elapsed / 29 + 4)]
    currents = [phase_power[index] * 1000 / (voltages[index] * pf) for index in range(3)]
    base_energy = {1: 125000, 2: 55000, 3: 47000, 4: 19000}.get(unit, 1000)
    imported = 0 if STATE["reset_unit"] == unit else int((base_energy + total_kw * elapsed / 3600) * 100)
    values: dict[int, list[int]] = {
        100: f32(total_kw), 102: f32(reactive), 104: f32(apparent), 106: f32(pf), 108: f32(50 + 0.025 * wave),
        110: u32(imported), 112: u32(1200 + int(elapsed / 180)), 114: u32(int(imported * 0.22)),
        116: u32(3400), 118: u32(int(imported / max(pf, .01))),
        120: f32(voltages[0]), 122: f32(voltages[1]), 124: f32(voltages[2]),
        126: f32(voltages[0] * math.sqrt(3)), 128: f32(voltages[1] * math.sqrt(3)), 130: f32(voltages[2] * math.sqrt(3)),
        132: f32(currents[0]), 134: f32(currents[1]), 136: f32(currents[2]), 138: f32(abs(currents[0] - currents[2]) * .18),
        140: f32(phase_power[0]), 142: f32(phase_power[1]), 144: f32(phase_power[2]),
        146: f32(phase_reactive[0]), 148: f32(phase_reactive[1]), 150: f32(phase_reactive[2]),
        152: f32(phase_apparent[0]), 154: f32(phase_apparent[1]), 156: f32(phase_apparent[2]),
        158: f32(pf + .004), 160: f32(pf - .003), 162: f32(pf - .001),
        164: f32(1.8 + .2 * wave), 166: f32(1.9 + .16 * wave), 168: f32(1.7 + .18 * wave),
        170: f32(3.1 + .5 * wave), 172: f32(3.3 + .4 * wave), 174: f32(3.0 + .45 * wave),
        176: f32(.45 + .08 * abs(wave)), 178: f32(1.2 + .2 * abs(wave)),
        180: f32(total_kw * .96), 182: f32(total_kw * 1.18),
        184: f32(currents[0] * .95), 186: f32(currents[1] * .95), 188: f32(currents[2] * .95),
        190: f32(currents[0] * 1.22), 192: f32(currents[1] * 1.22), 194: f32(currents[2] * 1.22),
        196: f32(0), 198: f32(-120), 200: f32(120),
        202: u16(2 if STATE["anomaly"] else 1), 203: u16(101 if STATE["anomaly"] else 0),
        204: u32(int(elapsed + 480000)), 206: u16(0b0101), 207: u16(0b0010), 208: f32(37 + 2 * wave),
    }
    write(context, values)


def update_pv(context: ModbusDeviceContext, elapsed: float) -> None:
    solar = max(0.08, 0.72 + 0.25 * math.sin(elapsed / 75))
    dc_voltage = 690 + 18 * math.sin(elapsed / 43)
    dc_power = 48 * solar
    efficiency = 97.4 - 0.35 * abs(math.sin(elapsed / 50))
    ac_power = dc_power * efficiency / 100
    current_dc = dc_power * 1000 / dc_voltage
    voltage = [230.2, 229.7, 230.8]
    ac_current = ac_power * 1000 / (3 * 230 * .997)
    energy_today = 186.4 + ac_power * elapsed / 3600
    total_energy = 785420 + energy_today
    string1_power, string2_power = dc_power * .51, dc_power * .49
    write(context, {
        0: f32(dc_voltage), 2: f32(current_dc), 4: f32(dc_power), 6: f32(ac_power), 8: u64(int(total_energy * 100)),
        12: f32(50 + .018 * math.sin(elapsed / 20)), 14: f32(efficiency), 16: f32(43 + 4 * solar),
        18: u32(int(energy_today * 100)), 20: u16(3 if STATE["anomaly"] else 1), 21: u16(210 if STATE["anomaly"] else 0),
        22: f32(684), 24: f32(string1_power * 1000 / 684), 26: f32(string1_power),
        28: f32(696), 30: f32(string2_power * 1000 / 696), 32: f32(string2_power),
        34: f32(voltage[0]), 36: f32(voltage[1]), 38: f32(voltage[2]),
        40: f32(ac_current), 42: f32(ac_current * .99), 44: f32(ac_current * 1.01),
        46: f32(ac_power * .04), 48: f32(ac_power / .997), 50: f32(.997),
        52: u32(int((3240 + energy_today) * 100)), 54: u32(int(196000 + elapsed)),
        56: f32(2400 - 80 * solar), 58: f32(sum(voltage) / 3),
    })


def update_storage(context: ModbusDeviceContext, elapsed: float) -> None:
    power = 18 * math.sin(elapsed / 70)
    soc = 62 - 14 * math.sin(elapsed / 160)
    voltage = 742 + 8 * math.sin(elapsed / 41)
    current = power * 1000 / voltage
    charging = power < 0
    write(context, {
        100: f32(soc), 102: f32(96.8), 104: f32(power),
        106: u64(int((18420 + max(-power, 0) * elapsed / 3600) * 100)),
        110: u64(int((17680 + max(power, 0) * elapsed / 3600) * 100)),
        114: f32(voltage), 116: f32(current), 118: f32(27 + 2 * abs(power) / 18),
        120: u32(1286), 122: f32(92 * soc / 100), 124: u16(3 if STATE["anomaly"] else 1 if charging else 2),
        125: u16(320 if STATE["anomaly"] else 0), 126: f32(abs(power) * .03), 128: f32(abs(power) * 1.002),
        130: f32(23.4 + max(-power, 0) * elapsed / 3600), 132: f32(18.7 + max(power, 0) * elapsed / 3600),
        134: f32(92), 136: f32(3.438), 138: f32(3.421), 140: f32(30.2), 142: f32(25.8),
        144: f32(42), 146: f32(46), 148: f32(15), 150: u32(int(820000 + elapsed)),
        152: f32(1850), 154: u16(1), 155: u16(1),
    })


def update_ev(context: ModbusDeviceContext, elapsed: float) -> None:
    session_elapsed = int(elapsed) % 240
    charging = session_elapsed < 190
    power = (10.8 + .6 * math.sin(elapsed / 17)) if charging else 0
    current = power * 1000 / (3 * 230 * .99) if charging else 0
    session_energy = power * session_elapsed / 3600
    total = 28450 + power * elapsed / 3600
    write(context, {
        200: f32(power), 202: f32(session_energy), 204: u64(int(total * 100)), 208: u32(session_elapsed),
        210: u16(4 if STATE["anomaly"] else 2 if charging else 0), 211: u16(2 if charging else 0),
        212: f32(current), 214: f32(current * .99), 216: f32(current * 1.01),
        218: f32(230.4), 220: f32(229.8), 222: f32(230.7),
        224: f32(power * .05), 226: f32(power / .99 if power else 0), 228: f32(.99 if charging else 1),
        230: f32(50.01), 232: f32(16), 234: f32(32), 236: f32(34 + power * .25),
        238: f32(11.4), 240: u32(3486), 242: f32(99.7), 244: u16(440 if STATE["anomaly"] else 0),
        245: u16(3 if charging else 0), 246: u64(int(total * 100)),
    })


def update_weather(context: ModbusDeviceContext, elapsed: float) -> None:
    daylight = max(0, .72 + .25 * math.sin(elapsed / 85))
    poa = 920 * daylight
    ambient = 24 + 3 * math.sin(elapsed / 120)
    wind = 3.2 + 1.1 * math.sin(elapsed / 28)
    humidity = 56 - 8 * math.sin(elapsed / 120)
    write(context, {
        300: f32(poa), 302: f32(ambient), 304: f32(ambient + poa * .025), 306: f32(wind),
        308: f32(poa * .91), 310: f32(poa * .78), 312: f32(poa * .13), 314: f32(humidity),
        316: f32(1014 + 2 * math.sin(elapsed / 180)), 318: f32((215 + 25 * math.sin(elapsed / 70)) % 360),
        320: f32(wind * 1.55), 322: f32(.4), 324: f32(0), 326: f32(.19), 328: f32(96.5),
        330: f32(poa * .12), 332: f32(ambient + 2), 334: f32(14.8),
        336: u16(3 if STATE["anomaly"] else 1), 337: u16(510 if STATE["anomaly"] else 0),
        338: f32(24.2), 340: f32(0),
    })


UPDATERS = {
    "meter": update_meter,
    "pv": update_pv,
    "storage": update_storage,
    "ev": update_ev,
    "weather": update_weather,
}


def update_values() -> None:
    elapsed = time.time() - STATE["started"]
    for unit, context in DEVICES.items():
        if PROFILE == "meter":
            update_meter(context, elapsed, unit)
        else:
            UPDATERS[PROFILE](context, elapsed)


class ControlHandler(BaseHTTPRequestHandler):
    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._reply(200, STATE)

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size) or b"{}")
        allowed = {"anomaly", "unattributed_percent", "reset_unit", "offline_units"}
        STATE.update({key: value for key, value in payload.items() if key in allowed})
        self._reply(200, STATE)

    def log_message(self, format: str, *args) -> None:
        return


def start_control_server() -> None:
    ThreadingHTTPServer(("0.0.0.0", CONTROL_PORT), ControlHandler).serve_forever()


async def updater() -> None:
    while True:
        update_values()
        await asyncio.sleep(1)


async def main() -> None:
    unit_count = 4 if PROFILE == "meter" else 1
    for unit in range(1, unit_count + 1):
        DEVICES[unit] = create_device()
    update_values()
    threading.Thread(target=start_control_server, daemon=True).start()
    asyncio.create_task(updater())
    print(f"Energy Manager {PROFILE} simulator: Modbus TCP :{MODBUS_PORT}, controls HTTP :{CONTROL_PORT}", flush=True)
    await StartAsyncTcpServer(context=ModbusServerContext(devices=DEVICES, single=False), address=("0.0.0.0", MODBUS_PORT))


if __name__ == "__main__":
    asyncio.run(main())
