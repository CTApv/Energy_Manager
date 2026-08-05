import ipaddress

import pytest

from energy_manager.modbus_discovery import decode_identity, discover_modbus, parse_scan_network, profile_candidates, resolved_ipv4


def test_scan_is_limited_to_small_private_networks():
    assert parse_scan_network("192.168.2.108/24") == ipaddress.ip_network("192.168.2.0/24")
    assert parse_scan_network("10.20.30.40/32").prefixlen == 32
    with pytest.raises(ValueError, match="reti private"):
        parse_scan_network("8.8.8.8/32")
    with pytest.raises(ValueError, match="massimo"):
        parse_scan_network("172.16.0.0/16")


def test_device_identity_and_profile_ranking():
    class Response:
        information = {0: b"Siemens AG", 1: b"PAC3220", 2: b"2.1"}

    identity = decode_identity(Response())
    candidates = profile_candidates(identity, [
        {"definition": {"id": "pac2200", "manufacturer": "Siemens", "model": "PAC2200", "category": "multimeter", "protocols": ["modbus_tcp"]}},
        {"definition": {"id": "pac3220", "manufacturer": "Siemens", "model": "PAC3220", "category": "multimeter", "protocols": ["modbus_tcp"]}},
        {"definition": {"id": "rtu", "manufacturer": "Other", "model": "RTU", "category": "multimeter", "protocols": ["modbus_rtu"]}},
    ])
    assert identity["vendor"] == "Siemens AG"
    assert candidates[0]["profile_id"] == "pac3220"
    assert candidates[0]["confidence"] == .96
    assert all(item["profile_id"] != "rtu" for item in candidates)


def test_configured_hostname_is_resolved_for_duplicate_detection(monkeypatch):
    monkeypatch.setattr("energy_manager.modbus_discovery.socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("172.27.0.3", 0))])
    assert resolved_ipv4("simulator") == {"simulator", "172.27.0.3"}


@pytest.mark.asyncio
async def test_discovery_reports_open_endpoint_and_units(monkeypatch):
    async def fake_port(host, port, timeout, semaphore):
        return host == "192.168.2.108" and port == 5020

    async def fake_probe(host, port, unit_ids, timeout, probe_address, profiles, configured):
        return {"host": host, "port": port, "status": "modbus", "units": [{"unit_id": 1}, {"unit_id": 2}]}

    monkeypatch.setattr("energy_manager.modbus_discovery._port_open", fake_port)
    monkeypatch.setattr("energy_manager.modbus_discovery._probe_endpoint", fake_probe)
    result = await discover_modbus(parse_scan_network("192.168.2.108/32"), [502, 5020], [1, 2], .1, 0, [], set())
    assert result["hosts_scanned"] == 1
    assert result["devices_found"] == 2
    assert result["endpoints"][0]["port"] == 5020
