import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import yaml
import pytest

from energy_manager.catalog import expand_catalog_document
from energy_manager.decoder import decode_registers


ROOT = Path(__file__).parents[3]


def load_simulator():
    path = ROOT / "simulators" / "modbus-simulator" / "simulator.py"
    spec = importlib.util.spec_from_file_location("energy_manager_modbus_simulator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def profiles():
    directory = ROOT / "packages" / "modbus-catalog" / "profiles" / "templates"
    documents = []
    for name in ["generic-meter-v1.yaml", "generic-energy-assets.yaml"]:
        documents.extend(expand_catalog_document(yaml.safe_load((directory / name).read_text(encoding="utf-8"))))
    return {profile["category"]: profile for profile in documents}


def test_every_simulator_populates_every_catalog_register():
    simulator = load_simulator()
    configurations = {
        "multimeter": lambda context: simulator.update_meter(context, 30.0, 1),
        "pv_inverter": lambda context: simulator.update_pv(context, 30.0),
        "battery_storage": lambda context: simulator.update_storage(context, 30.0),
        "ev_charger": lambda context: simulator.update_ev(context, 30.0),
        "environmental_sensor": lambda context: simulator.update_weather(context, 30.0),
    }
    for category, profile in profiles().items():
        context = simulator.create_device()
        configurations[category](context)
        for point in profile["points"]:
            registers = context.getValues(3, point["address"], count=point["register_count"])
            value = decode_registers(registers, point)
            assert value is not None, (category, point["key"])


def test_all_scenarios_obey_the_instantaneous_energy_balance():
    simulator = load_simulator()
    for scenario in simulator.SCENARIOS:
        for hour in (0, 6, 9, 12, 18, 21, 23):
            stamp = datetime(2026, 6, 21, hour, tzinfo=timezone.utc).timestamp()
            snapshot = simulator.plant_snapshot(stamp, scenario)
            assert abs(snapshot["balance_error_kw"]) < 1e-9, (scenario, hour, snapshot)
            assert snapshot["grid_kw"] == pytest.approx(
                snapshot["site_load_kw"] - snapshot["pv_kw"] - snapshot["storage_kw"]
            )


def test_meter_tree_children_sum_to_upstream_and_phases_are_independent():
    simulator = load_simulator()
    stamp = datetime(2026, 6, 21, 20, tzinfo=timezone.utc).timestamp()
    snapshot = simulator.plant_snapshot(stamp, "evening_peak")
    powers = []
    for unit in range(1, 5):
        context = simulator.create_device(unit)
        simulator.update_meter(context, stamp, unit, snapshot)
        powers.append(decode_registers(context.getValues(3, 100, count=2), {"data_type": "float32", "register_count": 2}))
    assert powers[0] == pytest.approx(sum(powers[1:]), rel=1e-5)
    context = simulator.create_device(1)
    simulator.update_meter(context, stamp, 1, snapshot)
    voltages = [decode_registers(context.getValues(3, address, count=2), {"data_type": "float32", "register_count": 2}) for address in (120, 122, 124)]
    assert len({round(value, 3) for value in voltages}) == 3
