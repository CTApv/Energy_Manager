import importlib.util
from pathlib import Path

import yaml

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
