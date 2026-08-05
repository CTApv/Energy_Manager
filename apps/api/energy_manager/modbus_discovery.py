from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from typing import Any

from pymodbus.client import AsyncModbusTcpClient


RFC1918_NETWORKS = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def resolved_ipv4(host: str) -> set[str]:
    addresses = {host}
    try:
        addresses.update(item[4][0] for item in socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM))
    except OSError:
        pass
    return addresses


def parse_scan_network(value: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise ValueError("Inserire una rete IPv4 valida, ad esempio 192.168.2.0/24") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError("La discovery supporta reti IPv4")
    if network.num_addresses > 256:
        raise ValueError("Per sicurezza è possibile analizzare al massimo una rete /24")
    if not any(network.subnet_of(private) for private in RFC1918_NETWORKS):
        raise ValueError("La discovery è limitata alle reti private RFC1918")
    return network


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip("\x00 ")
    return str(value).strip()


def decode_identity(response: Any) -> dict[str, str]:
    information = getattr(response, "information", None) or {}
    decoded = {int(key): _text(value) for key, value in information.items() if _text(value)}
    return {
        "vendor": decoded.get(0, ""),
        "product_code": decoded.get(1, ""),
        "revision": decoded.get(2, ""),
        "model": decoded.get(4, decoded.get(1, "")),
    }


def profile_candidates(identity: dict[str, str], profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vendor = identity.get("vendor", "").lower()
    product = " ".join((identity.get("product_code", ""), identity.get("model", ""))).lower()
    candidates = []
    for profile in profiles:
        definition = profile.get("definition", profile)
        if "modbus_tcp" not in definition.get("protocols", []):
            continue
        manufacturer = str(definition.get("manufacturer", ""))
        model = str(definition.get("model", profile.get("id", "")))
        score = 0.35
        reasons = ["mappa Modbus TCP compatibile"]
        if manufacturer and manufacturer.lower() in vendor:
            score = 0.72
            reasons.append("produttore identificato")
        tokens = [token for token in model.lower().replace("-", " ").split() if len(token) >= 3]
        if tokens and any(token in product for token in tokens):
            score = 0.96
            reasons.append("modello identificato")
        candidates.append({
            "profile_id": definition.get("id", profile.get("id")),
            "manufacturer": manufacturer,
            "model": model,
            "category": definition.get("category", "device"),
            "confidence": round(score, 2),
            "reason": ", ".join(reasons),
        })
    return sorted(candidates, key=lambda item: (-item["confidence"], item["manufacturer"], item["model"]))[:8]


async def _port_open(host: str, port: int, timeout: float, semaphore: asyncio.Semaphore) -> bool:
    async with semaphore:
        writer = None
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
            return True
        except (TimeoutError, OSError):
            return False
        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass


async def _probe_endpoint(host: str, port: int, unit_ids: list[int], timeout: float, probe_address: int, profiles: list[dict[str, Any]], configured: set[tuple[str, int, int]]) -> dict[str, Any]:
    client = AsyncModbusTcpClient(host, port=port, timeout=timeout, retries=0)
    units = []
    try:
        if not await client.connect():
            return {"host": host, "port": port, "status": "tcp_only", "units": []}
        for unit_id in unit_ids:
            identity: dict[str, str] = {}
            responded = False
            try:
                identification = await client.read_device_information(device_id=unit_id)
                if identification and not identification.isError():
                    identity = decode_identity(identification)
                    responded = True
            except Exception:
                pass
            if not responded:
                try:
                    if not client.connected and not await client.connect():
                        continue
                    response = await client.read_holding_registers(probe_address, count=1, device_id=unit_id)
                    responded = bool(response and not response.isError())
                except Exception:
                    responded = False
            if responded:
                units.append({
                    "unit_id": unit_id,
                    "identity": identity,
                    "already_configured": (host, port, unit_id) in configured,
                    "profile_candidates": profile_candidates(identity, profiles),
                })
    finally:
        client.close()
    return {"host": host, "port": port, "status": "modbus" if units else "tcp_only", "units": units}


async def discover_modbus(network: ipaddress.IPv4Network, ports: list[int], unit_ids: list[int], timeout: float, probe_address: int, profiles: list[dict[str, Any]], configured: set[tuple[str, int, int]]) -> dict[str, Any]:
    started = time.monotonic()
    hosts = [str(host) for host in network.hosts()]
    if network.prefixlen == 32:
        hosts = [str(network.network_address)]
    semaphore = asyncio.Semaphore(64)
    checks = [(host, port) for host in hosts for port in ports]
    states = await asyncio.gather(*(_port_open(host, port, timeout, semaphore) for host, port in checks))
    open_endpoints = [endpoint for endpoint, opened in zip(checks, states) if opened]
    endpoints_skipped = max(0, len(open_endpoints) - 32)
    open_endpoints = open_endpoints[:32]
    probe_semaphore = asyncio.Semaphore(12)

    async def limited_probe(host: str, port: int) -> dict[str, Any]:
        async with probe_semaphore:
            return await _probe_endpoint(host, port, unit_ids, timeout, probe_address, profiles, configured)

    results = await asyncio.gather(*(limited_probe(host, port) for host, port in open_endpoints))
    return {
        "network": str(network),
        "hosts_scanned": len(hosts),
        "ports": ports,
        "unit_ids": unit_ids,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "endpoints": sorted(results, key=lambda item: (ipaddress.ip_address(item["host"]), item["port"])),
        "endpoints_skipped": endpoints_skipped,
        "devices_found": sum(len(item["units"]) for item in results),
    }
