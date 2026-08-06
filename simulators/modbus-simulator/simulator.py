from __future__ import annotations

import asyncio
import json
import math
import os
import struct
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.server import StartAsyncTcpServer


PROFILE = os.getenv("SIMULATOR_PROFILE", "meter").strip().lower()
MODBUS_PORT = int(os.getenv("SIMULATOR_PORT", "5020"))
CONTROL_PORT = int(os.getenv("SIMULATOR_CONTROL_PORT", "18090"))
UNIT_COUNT = max(1, min(int(os.getenv("SIMULATOR_UNIT_COUNT", "100" if PROFILE == "meter" else "1")), 247))
SUPPORTED_PROFILES = {"meter", "pv", "storage", "ev", "weather"}
if PROFILE not in SUPPORTED_PROFILES:
    raise RuntimeError(f"Unsupported SIMULATOR_PROFILE={PROFILE!r}")

SCENARIOS: dict[str, dict[str, Any]] = {
    "residential_sunny": {"label": "Villa solare · giornata limpida", "cloud": 0.04, "load": 1.0, "pv_peak": 13.5, "ev": True, "battery": True},
    "residential_cloudy": {"label": "Villa solare · nuvolosità variabile", "cloud": 0.52, "load": 1.05, "pv_peak": 8.0, "ev": True, "battery": True},
    "winter_heat_pump": {"label": "Inverno · pompa di calore", "cloud": 0.35, "load": 1.32, "pv_peak": 7.5, "ev": True, "battery": True},
    "evening_peak": {"label": "Picco serale · EV e carichi domestici", "cloud": 0.15, "load": 1.45, "pv_peak": 11.0, "ev": True, "battery": True},
    "industrial_shift": {"label": "Turno produttivo · carico diurno", "cloud": 0.12, "load": 4.8, "pv_peak": 45.0, "ev": False, "battery": True},
    "grid_outage": {"label": "Blackout rete · funzionamento in isola", "cloud": 0.18, "load": 0.8, "pv_peak": 12.0, "ev": False, "battery": True},
}

STATE: dict[str, Any] = {
    "profile": PROFILE,
    "scenario": os.getenv("SIMULATOR_SCENARIO", "residential_sunny"),
    "time_scale": float(os.getenv("SIMULATOR_TIME_SCALE", "60")),
    "virtual_anchor": os.getenv("SIMULATOR_VIRTUAL_TIME", "2026-06-21T06:00:00+00:00"),
    "real_anchor": time.time(),
    "faults": {},
    "unattributed_percent": 0.0,
    "started": time.time(),
    "unit_count": UNIT_COUNT,
    "metrics": {"reads": 0, "updates": 0, "last_update_ms": 0.0},
}
if STATE["scenario"] not in SCENARIOS:
    STATE["scenario"] = "residential_sunny"

DEVICES: dict[int, ModbusDeviceContext] = {}
ENERGY: dict[tuple[str, int, str], float] = {}
LAST_VIRTUAL_SECONDS: float | None = None
LAST_SNAPSHOT: dict[str, float] = {}


def registers(fmt: str, value: float | int) -> list[int]:
    payload = struct.pack(">" + fmt, value)
    return list(struct.unpack(">" + "H" * (len(payload) // 2), payload))


def f32(value: float) -> list[int]: return registers("f", float(value))
def u16(value: int) -> list[int]: return registers("H", int(value) & 0xFFFF)
def u32(value: int) -> list[int]: return registers("I", int(value) & 0xFFFFFFFF)
def u64(value: int) -> list[int]: return registers("Q", int(value) & 0xFFFFFFFFFFFFFFFF)


class FaultAwareDataBlock(ModbusSequentialDataBlock):
    def __init__(self, unit: int):
        super().__init__(0, [0] * 1000)
        self.unit = unit

    def getValues(self, address: int, count: int = 1):
        faults = STATE["faults"]
        if self.unit in faults.get("offline_units", []):
            raise RuntimeError(f"simulated unit {self.unit} offline")
        latency = max(0, min(float(faults.get("latency_ms", 0)), 5000))
        if latency:
            time.sleep(latency / 1000)
        STATE["metrics"]["reads"] += 1
        return super().getValues(address, count)


def create_device(unit: int = 1) -> ModbusDeviceContext:
    block = lambda: FaultAwareDataBlock(unit)
    return ModbusDeviceContext(hr=block(), ir=block(), di=block(), co=block())


def write(context: ModbusDeviceContext, values: dict[int, list[int]]) -> None:
    for address, payload in values.items():
        context.setValues(3, address, payload)


def _virtual_seconds() -> float:
    anchor = datetime.fromisoformat(str(STATE["virtual_anchor"]).replace("Z", "+00:00"))
    return anchor.timestamp() + (time.time() - float(STATE["real_anchor"])) * float(STATE["time_scale"])


def _bell(hour: float, center: float, width: float) -> float:
    distance = min(abs(hour - center), 24 - abs(hour - center))
    return math.exp(-0.5 * (distance / width) ** 2)


def plant_snapshot(virtual_seconds: float, scenario_name: str | None = None) -> dict[str, float]:
    """Return a deterministic, physically coherent instantaneous plant state."""
    scenario = SCENARIOS[scenario_name or STATE["scenario"]]
    stamp = datetime.fromtimestamp(virtual_seconds, timezone.utc)
    hour = stamp.hour + stamp.minute / 60 + stamp.second / 3600
    day = stamp.timetuple().tm_yday
    ripple = math.sin(virtual_seconds / 173 + day) * 0.035
    daylight = max(0.0, math.sin(math.pi * (hour - 5.5) / 14.2))
    cloud_wave = (0.5 + 0.5 * math.sin(virtual_seconds / 1100 + 1.7)) * scenario["cloud"]
    irradiance = max(0.0, 1000 * daylight * (1 - cloud_wave))
    pv_kw = scenario["pv_peak"] * irradiance / 1000 * (0.985 + ripple)

    base = (0.62 + 0.28 * _bell(hour, 7.3, 1.1) + 0.52 * _bell(hour, 20.0, 2.0)) * scenario["load"]
    heat_pump = (0.35 + 1.4 * _bell(hour, 6.8, 1.4) + 1.0 * _bell(hour, 19.2, 1.8)) * scenario["load"]
    appliances = (0.22 + 0.9 * _bell(hour, 12.8, 0.8) + 1.5 * _bell(hour, 20.1, 1.0)) * scenario["load"]
    selected_scenario = scenario_name or STATE["scenario"]
    if selected_scenario == "industrial_shift":
        active_shift = 1.0 if 7 <= hour < 18 else 0.12
        base, heat_pump, appliances = 12 * active_shift, 8.5 * active_shift, 18 * active_shift
    ev_kw = 0.0
    if scenario["ev"]:
        ev_kw = 7.4 * (_bell(hour, 21.5, 1.7) > 0.42)
        if selected_scenario == "evening_peak": ev_kw = 11.0 * (_bell(hour, 20.5, 2.2) > 0.25)
    site_load_kw = max(0.05, base + heat_pump + appliances + ev_kw)

    storage_kw = 0.0  # positive discharge, negative charge
    if scenario["battery"]:
        if pv_kw > site_load_kw + 1.0: storage_kw = -min(5.0, (pv_kw - site_load_kw) * 0.72)
        elif 18 <= hour <= 23 and site_load_kw > 2: storage_kw = min(5.0, site_load_kw * 0.55)
    grid_kw = site_load_kw - pv_kw - storage_kw
    if selected_scenario == "grid_outage":
        grid_kw = 0.0
        # Island mode: the virtual PCS follows the residual load exactly. This
        # makes the power-flow equation explicit for deterministic E2E checks.
        storage_kw = site_load_kw - pv_kw

    return {
        "hour": hour, "irradiance_wm2": irradiance, "ambient_c": 17 + 8 * daylight + 2 * math.sin(day / 18),
        "wind_ms": 2.8 + 1.4 * abs(math.sin(virtual_seconds / 1800)), "pv_kw": max(0.0, pv_kw),
        "base_kw": max(0.0, base), "heat_pump_kw": max(0.0, heat_pump), "appliances_kw": max(0.0, appliances),
        "ev_kw": max(0.0, ev_kw), "site_load_kw": site_load_kw, "storage_kw": storage_kw, "grid_kw": grid_kw,
        "balance_error_kw": grid_kw - (site_load_kw - pv_kw - storage_kw),
    }


def _energy(profile: str, unit: int, name: str, power_kw: float, delta_hours: float, base: float) -> float:
    key = (profile, unit, name)
    current = ENERGY.setdefault(key, base)
    current += max(power_kw, 0) * max(delta_hours, 0)
    ENERGY[key] = current
    return current


def _meter_power(snapshot: dict[str, float], unit: int) -> float:
    if unit == 1: return snapshot["site_load_kw"]
    if unit == 2: return snapshot["heat_pump_kw"]
    if unit == 3: return snapshot["appliances_kw"]
    if unit == 4: return snapshot["base_kw"] + snapshot["ev_kw"]
    # Stress-test units have unique, deterministic loads without affecting the four-unit energy tree.
    return 0.35 + (unit % 17) * 0.11 + 0.18 * math.sin(_virtual_seconds() / 300 + unit)


def _apply_faults(values: dict[int, list[int]], profile: str, unit: int) -> None:
    faults = STATE["faults"]
    if faults.get("phase_loss") and profile in {"meter", "ev"}:
        for address in ([122, 134, 142] if profile == "meter" else [220, 214]): values[address] = f32(0)
    if faults.get("voltage_unbalance") and profile in {"meter", "ev"}:
        addresses = [120, 122, 124] if profile == "meter" else [218, 220, 222]
        for address, voltage in zip(addresses, [188.0, 231.0, 267.0]): values[address] = f32(voltage)
    if faults.get("nan_value"):
        address = {"meter": 100, "pv": 6, "storage": 100, "ev": 200, "weather": 300}[profile]
        values[address] = f32(float("nan"))
    if faults.get("identical_registers"):
        for address, payload in list(values.items()):
            if len(payload) == 2: values[address] = f32(42.0)
    if unit in faults.get("counter_reset_units", []):
        for address in {"meter": [110], "pv": [8, 18], "storage": [106, 110], "ev": [204, 246], "weather": []}[profile]:
            values[address] = [0] * len(values[address])


def update_meter(context: ModbusDeviceContext, elapsed: float, unit: int, snapshot: dict[str, float] | None = None, delta_hours: float = 0.0) -> None:
    snapshot = snapshot or plant_snapshot(datetime(2026, 6, 21, 12, tzinfo=timezone.utc).timestamp() + elapsed)
    total_kw = _meter_power(snapshot, unit)
    if STATE["faults"].get("power_spike") and unit == 1: total_kw *= 4.2
    pf = 0.96 - (unit % 4) * 0.006 + 0.008 * math.sin(elapsed / 31 + unit)
    apparent = abs(total_kw) / max(abs(pf), .1)
    reactive = math.sqrt(max(apparent**2 - total_kw**2, 0))
    shares = [0.338 + .006 * math.sin(unit), 0.331, 0.331 - .006 * math.sin(unit)]
    phase_power = [total_kw * share for share in shares]
    voltages = [230.2 + 1.1 * math.sin(elapsed / 41 + unit), 229.7 + 1.4 * math.sin(elapsed / 47 + unit + 2), 231.0 + 1.0 * math.sin(elapsed / 53 + unit + 4)]
    currents = [abs(phase_power[i]) * 1000 / max(voltages[i] * pf, 1) for i in range(3)]
    imported = _energy("meter", unit, "import", total_kw, delta_hours, 120000 + unit * 8100)
    exported = _energy("meter", unit, "export", max(-total_kw, 0), delta_hours, 320 + unit * 18)
    values = {
        100: f32(total_kw), 102: f32(reactive), 104: f32(apparent), 106: f32(pf), 108: f32(50 + .018 * math.sin(elapsed / 20 + unit)),
        110: u32(int(imported * 100)), 112: u32(int(exported * 100)), 114: u32(int(imported * .22 * 100)),
        116: u32(int(exported * .12 * 100)), 118: u32(int(imported / max(pf, .01) * 100)),
        120: f32(voltages[0]), 122: f32(voltages[1]), 124: f32(voltages[2]),
        126: f32(voltages[0] * math.sqrt(3)), 128: f32(voltages[1] * math.sqrt(3)), 130: f32(voltages[2] * math.sqrt(3)),
        132: f32(currents[0]), 134: f32(currents[1]), 136: f32(currents[2]), 138: f32(abs(currents[0] - currents[2]) * .18),
        140: f32(phase_power[0]), 142: f32(phase_power[1]), 144: f32(phase_power[2]),
        146: f32(reactive * shares[0]), 148: f32(reactive * shares[1]), 150: f32(reactive * shares[2]),
        152: f32(apparent * shares[0]), 154: f32(apparent * shares[1]), 156: f32(apparent * shares[2]),
        158: f32(pf + .004), 160: f32(pf - .003), 162: f32(pf - .001),
        164: f32(1.7 + .13 * math.sin(unit)), 166: f32(1.9 + .11 * math.sin(unit + 1)), 168: f32(1.8 + .09 * math.sin(unit + 2)),
        170: f32(3.0 + .3 * abs(math.sin(unit))), 172: f32(3.2 + .24 * abs(math.sin(unit + 1))), 174: f32(3.1 + .27 * abs(math.sin(unit + 2))),
        176: f32(.38 + .05 * abs(math.sin(unit))), 178: f32(.9 + .12 * abs(math.sin(unit))),
        180: f32(total_kw * .91), 182: f32(total_kw * 1.16),
        184: f32(currents[0] * .88), 186: f32(currents[1] * .89), 188: f32(currents[2] * .87),
        190: f32(currents[0] * 1.18), 192: f32(currents[1] * 1.21), 194: f32(currents[2] * 1.19),
        196: f32(0), 198: f32(-120), 200: f32(120), 202: u16(1), 203: u16(0),
        204: u32(int(elapsed + 480000)), 206: u16(0b0101), 207: u16(0b0010), 208: f32(34 + abs(total_kw) * .08),
    }
    _apply_faults(values, "meter", unit); write(context, values)


def update_pv(context: ModbusDeviceContext, elapsed: float, snapshot: dict[str, float] | None = None, delta_hours: float = 0.0) -> None:
    snapshot = snapshot or plant_snapshot(datetime(2026, 6, 21, 12, tzinfo=timezone.utc).timestamp() + elapsed)
    ac_power = snapshot["pv_kw"]; efficiency = 97.2 if ac_power else 0.0; dc_power = ac_power / max(efficiency / 100, .01)
    dc_voltage = 690 + 8 * math.sin(elapsed / 43); current_dc = dc_power * 1000 / max(dc_voltage, 1)
    today = _energy("pv", 1, "today", ac_power, delta_hours, 0); total = _energy("pv", 1, "total", ac_power, delta_hours, 785420)
    voltage = [230.2, 229.7, 230.8]; ac_current = ac_power * 1000 / (3 * 230 * .997) if ac_power else 0
    values = {0:f32(dc_voltage),2:f32(current_dc),4:f32(dc_power),6:f32(ac_power),8:u64(int(total*100)),12:f32(50.0),14:f32(efficiency),16:f32(snapshot["ambient_c"]+snapshot["irradiance_wm2"]*.025),18:u32(int(today*100)),20:u16(1 if ac_power else 0),21:u16(0),22:f32(684),24:f32(current_dc*.51),26:f32(dc_power*.51),28:f32(696),30:f32(current_dc*.49),32:f32(dc_power*.49),34:f32(voltage[0]),36:f32(voltage[1]),38:f32(voltage[2]),40:f32(ac_current),42:f32(ac_current*.99),44:f32(ac_current*1.01),46:f32(ac_power*.04),48:f32(ac_power/.997 if ac_power else 0),50:f32(.997 if ac_power else 1),52:u32(int(today*100)),54:u32(int(elapsed)),56:f32(2400),58:f32(sum(voltage)/3)}
    _apply_faults(values,"pv",1); write(context,values)


def update_storage(context: ModbusDeviceContext, elapsed: float, snapshot: dict[str, float] | None = None, delta_hours: float = 0.0) -> None:
    snapshot = snapshot or plant_snapshot(datetime(2026, 6, 21, 12, tzinfo=timezone.utc).timestamp() + elapsed)
    power=snapshot["storage_kw"]; charge=_energy("storage",1,"charge",-power,delta_hours,18420); discharge=_energy("storage",1,"discharge",power,delta_hours,17680)
    soc=max(15,min(96,64+(charge-18420-(discharge-17680))*100/92)); voltage=742+5*math.sin(elapsed/41); current=power*1000/voltage
    values={100:f32(soc),102:f32(96.8),104:f32(power),106:u64(int(charge*100)),110:u64(int(discharge*100)),114:f32(voltage),116:f32(current),118:f32(26+abs(power)*.16),120:u32(1286),122:f32(92*soc/100),124:u16(1 if power<0 else 2 if power>0 else 0),125:u16(0),126:f32(abs(power)*.03),128:f32(abs(power)*1.002),130:f32(max(charge-18420,0)),132:f32(max(discharge-17680,0)),134:f32(92),136:f32(3.438),138:f32(3.421),140:f32(30.2),142:f32(25.8),144:f32(42),146:f32(46),148:f32(15),150:u32(int(elapsed)),152:f32(1850),154:u16(1),155:u16(1)}
    _apply_faults(values,"storage",1); write(context,values)


def update_ev(context: ModbusDeviceContext, elapsed: float, snapshot: dict[str, float] | None = None, delta_hours: float = 0.0) -> None:
    snapshot=snapshot or plant_snapshot(datetime(2026,6,21,12,tzinfo=timezone.utc).timestamp()+elapsed); power=snapshot["ev_kw"]
    total=_energy("ev",1,"total",power,delta_hours,28450); session=_energy("ev",1,"session",power,delta_hours,0); current=power*1000/(3*230*.99) if power else 0
    values={200:f32(power),202:f32(session),204:u64(int(total*100)),208:u32(int(elapsed)%14400),210:u16(2 if power else 0),211:u16(2 if power else 0),212:f32(current),214:f32(current*.99),216:f32(current*1.01),218:f32(230.4),220:f32(229.8),222:f32(230.7),224:f32(power*.05),226:f32(power/.99 if power else 0),228:f32(.99 if power else 1),230:f32(50.01),232:f32(16),234:f32(32),236:f32(31+power*.25),238:f32(11.0),240:u32(3486),242:f32(99.7),244:u16(0),245:u16(3 if power else 0),246:u64(int(total*100))}
    _apply_faults(values,"ev",1); write(context,values)


def update_weather(context: ModbusDeviceContext, elapsed: float, snapshot: dict[str, float] | None = None, delta_hours: float = 0.0) -> None:
    snapshot=snapshot or plant_snapshot(datetime(2026,6,21,12,tzinfo=timezone.utc).timestamp()+elapsed); poa=snapshot["irradiance_wm2"]; ambient=snapshot["ambient_c"]; wind=snapshot["wind_ms"]
    values={300:f32(poa),302:f32(ambient),304:f32(ambient+poa*.025),306:f32(wind),308:f32(poa*.91),310:f32(poa*.78),312:f32(poa*.13),314:f32(58-12*poa/1000),316:f32(1014),318:f32((215+25*math.sin(elapsed/70))%360),320:f32(wind*1.55),322:f32(.4),324:f32(0),326:f32(.19),328:f32(96.5),330:f32(poa*.12),332:f32(ambient+2),334:f32(ambient-5),336:u16(1),337:u16(0),338:f32(24.2),340:f32(0)}
    _apply_faults(values,"weather",1); write(context,values)


UPDATERS = {"meter": update_meter, "pv": update_pv, "storage": update_storage, "ev": update_ev, "weather": update_weather}


def update_values() -> None:
    global LAST_VIRTUAL_SECONDS, LAST_SNAPSHOT
    started=time.perf_counter(); virtual_seconds=_virtual_seconds(); delta_hours=0 if LAST_VIRTUAL_SECONDS is None else max(0,min((virtual_seconds-LAST_VIRTUAL_SECONDS)/3600,1))
    LAST_VIRTUAL_SECONDS=virtual_seconds; snapshot=plant_snapshot(virtual_seconds); LAST_SNAPSHOT=snapshot
    if not STATE["faults"].get("frozen"):
        for unit,context in DEVICES.items():
            if PROFILE=="meter": update_meter(context,virtual_seconds,unit,snapshot,delta_hours)
            else: UPDATERS[PROFILE](context,virtual_seconds,snapshot,delta_hours)
    STATE["metrics"]["updates"]+=1; STATE["metrics"]["last_update_ms"]=round((time.perf_counter()-started)*1000,3)


def public_state() -> dict[str, Any]:
    return {**STATE,"scenarios":{key:value["label"] for key,value in SCENARIOS.items()},"virtual_time":datetime.fromtimestamp(_virtual_seconds(),timezone.utc).isoformat(),"snapshot":LAST_SNAPSHOT}


def reset_state(payload: dict[str, Any] | None = None) -> None:
    global LAST_VIRTUAL_SECONDS
    payload=payload or {}; scenario=payload.get("scenario","residential_sunny")
    STATE["scenario"]=scenario if scenario in SCENARIOS else "residential_sunny"; STATE["time_scale"]=max(.1,min(float(payload.get("time_scale",60)),86400))
    STATE["virtual_anchor"]=payload.get("virtual_time","2026-06-21T06:00:00+00:00"); STATE["real_anchor"]=time.time(); STATE["faults"]={}; STATE["metrics"]={"reads":0,"updates":0,"last_update_ms":0.0}
    ENERGY.clear(); LAST_VIRTUAL_SECONDS=None; update_values()


class ControlHandler(BaseHTTPRequestHandler):
    def _reply(self,status:int,payload:dict)->None:
        body=json.dumps(payload,allow_nan=True).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self)->None: self._reply(200,public_state())
    def do_POST(self)->None:
        try:
            size=min(int(self.headers.get("Content-Length","0")),100_000); payload=json.loads(self.rfile.read(size) or b"{}")
            action=payload.get("action","configure")
            if action=="reset": reset_state(payload)
            else:
                if payload.get("scenario") in SCENARIOS: STATE["scenario"]=payload["scenario"]
                if "time_scale" in payload: STATE["time_scale"]=max(.1,min(float(payload["time_scale"]),86400))
                if "virtual_time" in payload: STATE["virtual_anchor"]=payload["virtual_time"]; STATE["real_anchor"]=time.time()
                if action=="clear_faults": STATE["faults"]={}
                if action=="fault":
                    name=str(payload.get("name","")); enabled=bool(payload.get("enabled",True)); value=payload.get("value",enabled)
                    if enabled: STATE["faults"][name]=value
                    else: STATE["faults"].pop(name,None)
                # Backward-compatible control fields.
                if "offline_units" in payload: STATE["faults"]["offline_units"]=[int(v) for v in payload["offline_units"]]
                if payload.get("reset_unit") is not None: STATE["faults"]["counter_reset_units"]=[int(payload["reset_unit"])]
                if "anomaly" in payload and payload["anomaly"]: STATE["faults"]["power_spike"]=True
                update_values()
            self._reply(200,public_state())
        except Exception as exc: self._reply(422,{"error":str(exc)})
    def log_message(self,format:str,*args)->None: return


def start_control_server()->None: ThreadingHTTPServer(("0.0.0.0",CONTROL_PORT),ControlHandler).serve_forever()


async def updater()->None:
    while True: update_values(); await asyncio.sleep(1)


async def main()->None:
    for unit in range(1,UNIT_COUNT+1): DEVICES[unit]=create_device(unit)
    update_values(); threading.Thread(target=start_control_server,daemon=True).start(); asyncio.create_task(updater())
    print(f"Energy Manager Digital Twin {PROFILE}: {UNIT_COUNT} units, Modbus :{MODBUS_PORT}, control :{CONTROL_PORT}",flush=True)
    await StartAsyncTcpServer(context=ModbusServerContext(devices=DEVICES,single=False),address=("0.0.0.0",MODBUS_PORT))


if __name__=="__main__": asyncio.run(main())
