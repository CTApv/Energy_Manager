from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .maintenance import database_integrity, list_backups, storage_capacity
from .models import AlarmRule, AssetNode, Connection, Device, EnergySettings, LocalSite, MeasurementBinding, TelemetrySample, User


_HOSTNAME = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]+(?:\.(?!-)[A-Za-z0-9-]+)*$")


def validate_connection_config(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    if kind == "modbus_tcp":
        host = str(config.get("host", "")).strip()
        if not host or not _HOSTNAME.fullmatch(host):
            raise ValueError("Host TCP non valido")
        port = int(config.get("port", 502))
        if not 1 <= port <= 65535:
            raise ValueError("La porta TCP deve essere compresa tra 1 e 65535")
        timeout = float(config.get("timeout", 2))
        retry = int(config.get("retry", 0))
        if not 0.2 <= timeout <= 30:
            raise ValueError("Il timeout deve essere compreso tra 0,2 e 30 secondi")
        if not 0 <= retry <= 5:
            raise ValueError("I tentativi extra devono essere compresi tra 0 e 5")
        return {"host": host, "port": port, "timeout": timeout, "retry": retry}
    if kind == "modbus_rtu":
        port = str(config.get("port", "")).strip()
        if not port or "\x00" in port or len(port) > 255:
            raise ValueError("Porta seriale non valida")
        baud_rate = int(config.get("baud_rate", 9600))
        if baud_rate not in {1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200}:
            raise ValueError("Baud rate non supportato")
        parity = str(config.get("parity", "N")).upper()
        stop_bits = int(config.get("stop_bits", 1))
        byte_size = int(config.get("byte_size", 8))
        timeout = float(config.get("timeout", 2))
        retry = int(config.get("retry", 0))
        if parity not in {"N", "E", "O"} or stop_bits not in {1, 2} or byte_size not in {7, 8}:
            raise ValueError("Parametri seriali non validi")
        if not 0.2 <= timeout <= 30 or not 0 <= retry <= 5:
            raise ValueError("Timeout o tentativi extra non validi")
        return {"port": port, "baud_rate": baud_rate, "parity": parity, "stop_bits": stop_bits, "byte_size": byte_size, "timeout": timeout, "retry": retry}
    raise ValueError("Protocollo di connessione non supportato")


def _check(identifier: str, title: str, status: str, detail: str, action: str, blocking: bool = False) -> dict:
    return {"id": identifier, "title": title, "status": status, "detail": detail, "action": action, "blocking": blocking}


def commissioning_report(db: Session, settings: Settings) -> dict:
    site = db.scalar(select(LocalSite).limit(1))
    connections = list(db.scalars(select(Connection)))
    devices = list(db.scalars(select(Device)))
    active_devices = [item for item in devices if item.active]
    online = [item for item in active_devices if item.status == "online"]
    degraded = [item for item in active_devices if item.status == "degraded"]
    bindings = db.scalar(select(func.count()).select_from(MeasurementBinding)) or 0
    assets = db.scalar(select(func.count()).select_from(AssetNode)) or 0
    users = db.scalar(select(func.count()).select_from(User).where(User.active.is_(True))) or 0
    rules = db.scalar(select(func.count()).select_from(AlarmRule).where(AlarmRule.active.is_(True))) or 0
    energy = db.scalar(select(EnergySettings).limit(1))
    recent_samples = db.scalar(select(func.count()).select_from(TelemetrySample).where(TelemetrySample.sample_at >= datetime.now(timezone.utc) - timedelta(minutes=2))) or 0
    checks = []
    demo_name = not site or "demo" in site.name.lower()
    checks.append(_check("site", "Identità impianto", "fail" if demo_name else "pass", site.name if site else "Impianto non configurato", "Impostare il nome reale del sito cliente.", True))
    checks.append(_check("connections", "Reti industriali", "pass" if connections else "fail", f"{len(connections)} connessioni configurate", "Configurare e provare almeno una connessione Modbus.", True))
    untested = [item for item in connections if item.status != "online" or item.last_test_at is None]
    checks.append(_check("connection_tests", "Test connessioni", "pass" if connections and not untested else "fail", f"{len(connections)-len(untested)}/{len(connections)} connessioni collaudate", "Eseguire il test di ogni connessione con uno strumento reale.", True))
    checks.append(_check("devices", "Dispositivi installati", "pass" if active_devices else "fail", f"{len(active_devices)} dispositivi attivi", "Installare almeno un dispositivo dal catalogo.", True))
    device_status = "pass" if active_devices and len(online) == len(active_devices) else "warn" if online else "fail"
    checks.append(_check("live_data", "Acquisizione live", device_status, f"{len(online)} online, {len(degraded)} degradati, {len(active_devices)-len(online)-len(degraded)} offline", "Correggere mappe registro, cablaggio o parametri prima della consegna.", True))
    checks.append(_check("recent_samples", "Continuità del dato", "pass" if recent_samples else "fail", f"{recent_samples} campioni negli ultimi 2 minuti", "Verificare polling, orologio e persistenza.", True))
    checks.append(_check("energy_tree", "Modello energetico", "pass" if assets and bindings else "fail", f"{assets} nodi, {bindings} associazioni", "Completare gerarchia e associazioni delle misure.", True))
    default_secrets = any(value in candidate.lower() for value in ("change-me", "development-only", "demo-edge-token") for candidate in [settings.secret_key.lower(), settings.edge_token.lower(), settings.webhook_secret.lower()])
    secure_status = "fail" if settings.environment == "production" and default_secrets else "warn" if default_secrets else "pass"
    checks.append(_check("secrets", "Segreti di produzione", secure_status, "Valori predefiniti rilevati" if default_secrets else "Segreti personalizzati", "Generare chiavi casuali distinte e conservarle nel file .env protetto.", True))
    checks.append(_check("demo_seed", "Profilo cliente", "fail" if settings.seed_demo and settings.environment == "production" else "pass", "Dati demo attivi" if settings.seed_demo else "Seed demo disabilitato", "Impostare EM_SEED_DEMO=false sul deployment cliente.", True))
    checks.append(_check("users", "Account operativi", "pass" if users >= 2 else "warn", f"{users} utenti attivi", "Creare account nominativi e riservare admin al tecnico.", False))
    checks.append(_check("alarms", "Presidio allarmi", "pass" if rules else "warn", f"{rules} soglie attive", "Definire soglie concordate con il cliente.", False))
    energy_configured = bool(energy and energy.import_price_per_kwh > 0 and energy.co2_kg_per_kwh > 0 and energy.contracted_power_kw)
    checks.append(_check("energy_settings", "Parametri energetici", "pass" if energy_configured else "warn", "Tariffa, fattore CO₂ e potenza contrattuale configurati" if energy_configured else "Parametri economici o ambientali incompleti", "Inserire i parametri contrattuali e il fattore emissivo concordati con il cliente.", False))
    backups = list_backups(settings)
    checks.append(_check("backup", "Backup verificato", "pass" if backups else "fail", f"{len(backups)} backup disponibili", "Creare un backup e verificarne il ripristino prima della consegna.", True))
    integrity = database_integrity(settings)
    checks.append(_check("database", "Integrità database", "pass" if integrity == "ok" else "fail", integrity, "Bloccare il commissioning e ripristinare un backup integro.", True))
    capacity = storage_capacity(settings)
    capacity_status = "pass" if capacity["free_percent"] >= 20 else "warn" if capacity["free_percent"] >= 10 else "fail"
    checks.append(_check("storage", "Spazio disco", capacity_status, f'{capacity["free_percent"]}% libero', "Liberare spazio o aumentare la capacità del disco.", capacity_status == "fail"))
    blocking_failures = sum(1 for item in checks if item["blocking"] and item["status"] == "fail")
    passed = sum(1 for item in checks if item["status"] == "pass")
    return {
        "ready": blocking_failures == 0,
        "score": round(passed / len(checks) * 100),
        "blocking_failures": blocking_failures,
        "generated_at": datetime.now(timezone.utc),
        "release": settings.release,
        "environment": settings.environment,
        "checks": checks,
        "storage": capacity,
        "retention_days": settings.telemetry_retention_days,
        "backup_retention_count": settings.backup_retention_count,
        "backups": backups,
    }
