from __future__ import annotations

import glob
import json
import platform
import shutil
import socket
import struct
import subprocess
from pathlib import Path
from typing import Any


def _ip_inventory() -> list[dict[str, Any]]:
    executable = shutil.which("ip")
    if not executable:
        return []
    try:
        result = subprocess.run(
            [executable, "-j", "address", "show"], capture_output=True, text=True, timeout=2, check=True
        )
        rows = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []
    interfaces = []
    for row in rows:
        addresses = [
            {"family": item.get("family"), "address": item.get("local"), "prefix": item.get("prefixlen")}
            for item in row.get("addr_info", []) if item.get("family") in {"inet", "inet6"}
        ]
        interfaces.append({
            "name": row.get("ifname", ""), "state": str(row.get("operstate", "unknown")).lower(),
            "mac": row.get("address", ""), "mtu": row.get("mtu"), "addresses": addresses,
        })
    return interfaces


def network_interfaces() -> list[dict[str, Any]]:
    detected = _ip_inventory()
    if detected:
        return detected
    interfaces = []
    for _, name in socket.if_nameindex():
        addresses = []
        try:
            import fcntl
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handle:
                packed = struct.pack("256s", name[:15].encode())
                address = socket.inet_ntoa(fcntl.ioctl(handle.fileno(), 0x8915, packed)[20:24])
                netmask = socket.inet_ntoa(fcntl.ioctl(handle.fileno(), 0x891B, packed)[20:24])
                prefix = sum(bin(int(part)).count("1") for part in netmask.split("."))
                addresses.append({"family": "inet", "address": address, "prefix": prefix})
        except (ImportError, OSError):
            pass
        sysfs = Path("/sys/class/net") / name
        try: mac = (sysfs / "address").read_text(encoding="utf-8").strip()
        except OSError: mac = ""
        try: state = (sysfs / "operstate").read_text(encoding="utf-8").strip()
        except OSError: state = "unknown"
        try: mtu = int((sysfs / "mtu").read_text(encoding="utf-8").strip())
        except (OSError, ValueError): mtu = None
        interfaces.append({"name": name, "state": state, "mac": mac, "mtu": mtu, "addresses": addresses})
    return interfaces


def serial_ports() -> list[dict[str, str]]:
    candidates: set[str] = set()
    try:
        from serial.tools import list_ports
        candidates.update(port.device for port in list_ports.comports())
    except ImportError:
        pass
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
                index = 0
                while True:
                    try:
                        candidates.add(str(winreg.EnumValue(key, index)[1])); index += 1
                    except OSError:
                        break
        except OSError:
            pass
    else:
        for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*", "/dev/ttyS*"):
            candidates.update(glob.glob(pattern))
    return [{"path": item, "available": Path(item).exists() if item.startswith("/") else True} for item in sorted(candidates)]


def runtime_summary() -> dict[str, Any]:
    return {
        "hostname": socket.gethostname(), "operating_system": platform.system(),
        "os_release": platform.release(), "architecture": platform.machine(),
        "python": platform.python_version(),
    }
