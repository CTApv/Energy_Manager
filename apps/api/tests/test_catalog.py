from pathlib import Path

import yaml

from energy_manager.catalog import expand_catalog_document, validate_profile
from energy_manager.polling import calculate_derived_points

def profile():
    return {"id":"meter-v1","manufacturer":"Demo","model":"M1","category":"meter","version":"1.0.0","protocols":["modbus_tcp"],"points":[{"key":"electrical.power","label":"Power","function_code":3,"address":10,"register_count":2,"data_type":"float32"}]}

def test_valid_profile(): assert validate_profile(profile())[0] is not None
def test_overlap_rejected():
    raw=profile(); raw["points"].append({"key":"electrical.energy","label":"Energy","function_code":3,"address":11,"register_count":2,"data_type":"uint32"})
    assert "overlap" in " ".join(validate_profile(raw)[1])
def test_write_function_rejected():
    raw=profile(); raw["points"][0]["function_code"]=6
    assert validate_profile(raw)[0] is None
def test_wrong_register_count_rejected():
    raw=profile(); raw["points"][0]["register_count"]=1
    assert validate_profile(raw)[0] is None


def test_siemens_pac_bundle_is_valid_and_normalized():
    path = Path(__file__).parents[3] / "packages" / "modbus-catalog" / "profiles" / "drivers" / "multimeters" / "siemens-sentron-pac.yaml"
    documents = expand_catalog_document(yaml.safe_load(path.read_text(encoding="utf-8")))
    profiles = {document["model"]: validate_profile(document)[0] for document in documents}
    assert set(profiles) == {"PAC2200", "PAC3200", "PAC3220"}
    assert all(item is not None for item in profiles.values())
    assert all(item.category == "multimeter" for item in profiles.values())
    assert all(set(item.protocols) == {"modbus_tcp", "modbus_rtu"} for item in profiles.values())
    assert all("electrical.active_power.total" in {point.key for point in item.points} for item in profiles.values())
    assert all("electrical.energy.import_total" in {point.key for point in item.derived_points} for item in profiles.values())
    assert len(profiles["PAC2200"].points) == 88
    assert len(profiles["PAC3200"].points) == 131
    assert len(profiles["PAC3220"].points) == 169


def test_tariff_energy_is_combined_into_competitor_neutral_total():
    values = {"energy.t1": 120.5, "energy.t2": 4.5}
    result = calculate_derived_points(values, [{"key": "electrical.energy.import_total", "operation": "sum", "sources": ["energy.t1", "energy.t2"], "unit": "kWh"}])
    assert result == [{"key": "electrical.energy.import_total", "value": 125.0, "unit": "kWh"}]


def test_multi_vector_energy_asset_profiles_are_valid():
    path = Path(__file__).parents[3] / "packages" / "modbus-catalog" / "profiles" / "templates" / "generic-energy-assets.yaml"
    documents = expand_catalog_document(yaml.safe_load(path.read_text(encoding="utf-8")))
    profiles = {document["category"]: validate_profile(document)[0] for document in documents}
    assert set(profiles) == {"pv_inverter", "battery_storage", "ev_charger", "environmental_sensor"}
    assert all(profile is not None for profile in profiles.values())
    assert "pv.power.ac_total" in {point.key for point in profiles["pv_inverter"].points}
    assert "storage.soc" in {point.key for point in profiles["battery_storage"].points}
    assert {category: len(profile.points) for category, profile in profiles.items()} == {
        "pv_inverter": 30,
        "battery_storage": 28,
        "ev_charger": 25,
        "environmental_sensor": 22,
    }


def test_complete_meter_simulator_profile_covers_three_phase_quality():
    path = Path(__file__).parents[3] / "packages" / "modbus-catalog" / "profiles" / "templates" / "generic-meter-v1.yaml"
    profile = validate_profile(yaml.safe_load(path.read_text(encoding="utf-8")))[0]
    assert profile is not None
    keys = {point.key for point in profile.points}
    assert len(profile.points) == 57
    assert {
        "electrical.voltage.l1n", "electrical.voltage.l2n", "electrical.voltage.l3n",
        "electrical.current.l1", "electrical.current.l2", "electrical.current.l3",
        "electrical.power_factor.total", "electrical.power_factor.l1",
        "electrical.thd.voltage.l1", "electrical.thd.current.l1",
        "electrical.unbalance.voltage", "electrical.energy.import_total",
    }.issubset(keys)


def test_italian_field_device_catalog_is_valid_and_traceable():
    root = Path(__file__).parents[3] / "packages" / "modbus-catalog" / "profiles" / "drivers"
    paths = [
        root / "multimeters" / "schneider-acti9-iem3000.yaml",
        root / "hybrid" / "huawei-sun2000-lb0-luna.yaml",
        root / "ev-chargers" / "abb-terra-ac.yaml",
    ]
    documents = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths]
    profiles = {document["id"]: validate_profile(document)[0] for document in documents}

    assert set(profiles) == {
        "schneider-iem3000-modbus",
        "huawei-sun2000-lb0-luna",
        "abb-terra-ac-wallbox",
    }
    assert all(profile is not None for profile in profiles.values())
    assert all(profile.documentation.get("url", "").startswith("https://") for profile in profiles.values())
    assert all(profile.documentation.get("verified") == "2026-08-05" for profile in profiles.values())
    assert all(profile.capabilities.get("writable") is False for profile in profiles.values())
    assert all(profile.driver.get("implementation") == "standard_modbus" for profile in profiles.values())
    assert len({profile.driver.get("register_map") for profile in profiles.values()}) == 3

    schneider = profiles["schneider-iem3000-modbus"]
    assert "electrical.energy.import_total" in {point.key for point in schneider.points}
    assert "electrical.energy.export_total" in {point.key for point in schneider.points}

    huawei = profiles["huawei-sun2000-lb0-luna"]
    assert set(huawei.capabilities["components"]) == {"photovoltaic", "battery_storage", "grid_meter"}
    assert {"pv.power.ac_total", "storage.soc", "electrical.active_power.grid"}.issubset(
        {point.key for point in huawei.points}
    )

    abb = profiles["abb-terra-ac-wallbox"]
    assert abb.defaults["polling_interval_seconds"] >= 30
    assert "ev.energy.session" in {point.key for point in abb.points}
