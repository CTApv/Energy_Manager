from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import io
import json
import secrets
import ipaddress
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import Body, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .auth import create_token, current_user, hash_password, require_roles, verify_password
from .catalog import expand_catalog_document, next_copy_id, parse_profile, validate_profile
from .commissioning import commissioning_report, validate_connection_config, validate_device_connection_config
from .config import get_settings
from .db import Base, SessionLocal, engine, get_db
from .decoder import decode_registers
from .energy_reporting import build_energy_report, safe_zone
from .kpi import counter_delta, unattributed_energy
from .maintenance import backup_file, create_backup, database_integrity, list_backups, maintenance_loop, run_retention, storage_capacity
from .modbus_discovery import discover_modbus, parse_scan_network, resolved_ipv4
from .models import (
    AlarmEvent, AlarmRule, AssetNode, AuditEvent, CatalogProfile, CatalogProfileVersion,
    Connection, Device, DeviceProfile, Edge, EdgeActivation, EnergySettings, IngestedBatch, KpiDefinition, LocalSite, MeasurementBinding,
    RegisterDefinition, Site, SyncOutbox, SystemPreference, TelemetrySample, Tenant, User, utcnow,
)
from .polling import close_clients, poll_device, polling_loop
from .seed import seed_database
from .sync import sync_loop, sync_once
from .tailscale import FakeTailscaleProvider, NetworkAgent, node_dict
from .system_inventory import network_interfaces, runtime_summary, serial_ports


settings = get_settings()
rate_buckets: dict[str, deque[float]] = defaultdict(deque)
tailscale_provider = FakeTailscaleProvider()


def as_dict(obj: Any) -> dict[str, Any]:
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}


def webhook_signature_valid(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def tenant_scope_allowed(role: str, user_tenant_id: str | None, target_tenant_id: str) -> bool:
    return role in {"platform_admin", "technician"} or (user_tenant_id is not None and user_tenant_id == target_tenant_id)


def batch_already_ingested(db: Session, batch_id: str) -> bool:
    return db.get(IngestedBatch, batch_id) is not None


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_database(db, settings)
    stop = asyncio.Event()
    tasks = []
    if settings.mode == "edge" and settings.polling_enabled:
        tasks.append(asyncio.create_task(polling_loop(stop)))
    if settings.mode == "edge" and settings.sync_enabled:
        tasks.append(asyncio.create_task(sync_loop(stop)))
    if settings.mode == "edge":
        tasks.append(asyncio.create_task(maintenance_loop(stop, settings)))
    yield
    stop.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    close_clients()


app = FastAPI(
    title=f"Energy Manager {settings.mode}",
    version=settings.release,
    contact={"name": "Filippo Lolli", "email": "filippoctass@gmail.com"},
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Webhook-Signature"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def sensitive_rate_limit(request: Request, limit: int = 12, window_seconds: int = 60) -> None:
    import time
    key = request.client.host if request.client else "unknown"
    now = time.monotonic(); bucket = rate_buckets[key]
    while bucket and bucket[0] < now - window_seconds: bucket.popleft()
    if len(bucket) >= limit: raise HTTPException(429, "Too many attempts")
    bucket.append(now)


class AssetInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    parent_id: str | None = None
    category: str = "asset"
    description: str = ""
    sort_order: int = 0
    active: bool = True


class ConnectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kind: str
    config: dict[str, Any]


class DeviceInput(BaseModel):
    connection_id: str
    profile_id: str
    name: str = Field(min_length=1, max_length=160)
    unit_id: int | None = Field(default=None, ge=0, le=247)
    config: dict[str, Any] = Field(default_factory=dict)


class ProvisioningPlacementInput(BaseModel):
    asset_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    parent_id: str | None = None
    category: str = Field(default="asset", min_length=1, max_length=60)


class DeviceProvisioningInput(BaseModel):
    device: DeviceInput
    placement: ProvisioningPlacementInput
    measurement_key: str = Field(min_length=3, max_length=160)
    auto_connection_kind: str | None = Field(default=None, pattern="^modbus_tcp$")


class LocalSiteInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class BindingInput(BaseModel):
    asset_id: str
    device_id: str
    measurement_key: str = Field(min_length=3, max_length=160)
    role: str = Field(default="primary", pattern="^(primary|process|secondary)$")


class AlarmRuleInput(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    device_id: str | None = None
    measurement_key: str = Field(min_length=3, max_length=160)
    condition: str = Field(pattern="^(above|below|outside)$")
    threshold: float | None = None
    low: float | None = None
    high: float | None = None
    deadband: float = Field(default=0, ge=0)
    severity: str = Field(default="warning", pattern="^(info|warning|high|critical)$")
    notification_channels: list[str] = Field(default_factory=lambda: ["in_app"])
    active: bool = True


class UserCreateInput(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(min_length=10, max_length=200)
    role: str = Field(pattern="^(platform_admin|technician|customer_admin|operator|viewer)$")
    active: bool = True


class UserUpdateInput(BaseModel):
    role: str = Field(pattern="^(platform_admin|technician|customer_admin|operator|viewer)$")
    active: bool = True
    password: str | None = Field(default=None, min_length=10, max_length=200)


class KpiDefinitionInput(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    kind: str = Field(pattern="^(latest|sum|ratio)$")
    config: dict[str, Any]


class EnergySettingsInput(BaseModel):
    currency: str = Field(default="EUR", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    import_price_per_kwh: float = Field(default=0, ge=0)
    export_price_per_kwh: float = Field(default=0, ge=0)
    co2_kg_per_kwh: float = Field(default=0, ge=0)
    contracted_power_kw: float | None = Field(default=None, gt=0)
    monthly_energy_budget_kwh: float | None = Field(default=None, gt=0)
    monthly_cost_budget: float | None = Field(default=None, gt=0)
    timezone: str = Field(default="Europe/Rome", min_length=1, max_length=64)
    workday_start: str = Field(default="08:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    workday_end: str = Field(default="18:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    working_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1, max_length=7)


class ModbusDiscoveryInput(BaseModel):
    network: str = Field(default="192.168.2.0/24", min_length=9, max_length=32)
    ports: list[int] = Field(default_factory=lambda: [502, 5020], min_length=1, max_length=4)
    unit_from: int = Field(default=1, ge=0, le=247)
    unit_to: int = Field(default=10, ge=0, le=247)
    timeout_seconds: float = Field(default=0.35, ge=0.1, le=2)
    probe_address: int = Field(default=0, ge=0, le=65535)


class ModbusDiscoveredInstallInput(BaseModel):
    host: str = Field(min_length=7, max_length=15)
    port: int = Field(ge=1, le=65535)
    unit_id: int = Field(ge=0, le=247)
    profile_id: str = Field(min_length=1, max_length=100)
    device_name: str = Field(min_length=1, max_length=160)
    transport: str = Field(default="modbus_tcp", pattern="^(modbus_tcp|modbus_rtu_tcp)$")


class DeviceRemovalInput(BaseModel):
    purge_history: bool = False


class NetworkProfileInput(BaseModel):
    mode: str = Field(pattern="^(dhcp|static)$")
    address: str = ""
    prefix: int = Field(default=24, ge=1, le=32)
    gateway: str = ""
    dns: list[str] = Field(default_factory=list, max_length=3)


class GeneralPreferencesInput(BaseModel):
    language: str = Field(default="it", pattern="^(it|en)$")
    theme: str = Field(default="system", pattern="^(light|dark|system)$")
    refresh_seconds: int = Field(default=5, ge=2, le=300)
    compact_numbers: bool = False


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "mode": settings.mode, "version": settings.release, "environment": settings.environment, "time": utcnow()}


@app.get("/api/ready")
def readiness() -> dict:
    try:
        integrity = database_integrity(settings)
        return {"status": "ready" if integrity == "ok" else "not_ready", "database": integrity, "storage": storage_capacity(settings)}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "not_ready", "error": type(exc).__name__})


def preference_value(db: Session, key: str, default: dict[str, Any]) -> dict[str, Any]:
    item = db.get(SystemPreference, key)
    return item.value if item else default


def save_preference(db: Session, key: str, value: dict[str, Any]) -> SystemPreference:
    item = db.get(SystemPreference, key)
    if item:
        item.value = value
    else:
        item = SystemPreference(key=key, value=value); db.add(item)
    return item


@app.get("/api/system/overview")
def system_overview(user: User = Depends(require_roles("platform_admin", "technician", "customer_admin")), db: Session = Depends(get_db)) -> dict:
    interfaces = network_interfaces()
    profiles = {item.key.removeprefix("network.interface."): item.value for item in db.scalars(select(SystemPreference).where(SystemPreference.key.like("network.interface.%")))}
    for interface in interfaces:
        interface["configured"] = profiles.get(interface["name"])
    capacity = storage_capacity(settings)
    capacity.update({"total_gb": round(capacity["total_bytes"] / 1024**3, 1), "used_gb": round(capacity["used_bytes"] / 1024**3, 1), "free_gb": round(capacity["free_bytes"] / 1024**3, 1)})
    return {
        "runtime": runtime_summary(), "release": settings.release, "environment": settings.environment,
        "database": database_integrity(settings), "storage": capacity,
        "interfaces": interfaces, "serial_ports": serial_ports(),
        "network_management": {"apply_enabled": settings.network_management_enabled, "profiles_saved": len(profiles)},
        "preferences": preference_value(db, "general", {"language": "it", "theme": "system", "refresh_seconds": 5, "compact_numbers": False}),
    }


@app.put("/api/system/preferences")
def update_system_preferences(data: GeneralPreferencesInput, user: User = Depends(require_roles("platform_admin", "technician", "customer_admin")), db: Session = Depends(get_db)) -> dict:
    value = data.model_dump(); save_preference(db, "general", value)
    db.add(AuditEvent(actor=user.username, action="system.preferences.update", target_type="system", target_id="general", details=value))
    db.commit(); return value


@app.put("/api/system/network/{interface_name}")
def update_network_profile(interface_name: str, data: NetworkProfileInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    detected = {item["name"] for item in network_interfaces()}
    if interface_name not in detected or not interface_name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(404, "Interfaccia di rete non rilevata")
    if data.mode == "static":
        try:
            ipaddress.ip_interface(f"{data.address}/{data.prefix}")
            if data.gateway: ipaddress.ip_address(data.gateway)
            for server in data.dns: ipaddress.ip_address(server)
        except ValueError as exc:
            raise HTTPException(422, "Indirizzo IP, gateway o DNS non valido") from exc
    value = data.model_dump(); value["pending_apply"] = True
    save_preference(db, f"network.interface.{interface_name}", value)
    db.add(AuditEvent(actor=user.username, action="network.profile.update", target_type="network_interface", target_id=interface_name, details={"mode": data.mode, "address": data.address, "pending_apply": True}))
    db.commit()
    return {"interface": interface_name, "profile": value, "apply_enabled": settings.network_management_enabled, "message": "Profilo salvato. L'applicazione richiede il servizio host Edge."}


def compliance_readiness(db: Session) -> dict[str, Any]:
    device_count = db.scalar(select(func.count()).select_from(Device)) or 0
    connection_count = db.scalar(select(func.count()).select_from(Connection)) or 0
    binding_count = db.scalar(select(func.count()).select_from(MeasurementBinding)) or 0
    sample_count = db.scalar(select(func.count()).select_from(TelemetrySample)) or 0
    audit_count = db.scalar(select(func.count()).select_from(AuditEvent)) or 0
    rule_count = db.scalar(select(func.count()).select_from(AlarmRule).where(AlarmRule.active.is_(True))) or 0
    user_count = db.scalar(select(func.count()).select_from(User).where(User.active.is_(True))) or 0
    oldest_sample = db.scalar(select(func.min(TelemetrySample.sample_at)))
    newest_sample = db.scalar(select(func.max(TelemetrySample.sample_at)))
    controls = [
        {"id": "t40_asset_map", "framework": "Transizione 4.0", "area": "Interconnessione", "title": "Identificazione e collocazione dei beni", "status": "ready" if device_count and binding_count else "action", "evidence": f"{device_count} dispositivi, {binding_count} associazioni all’albero", "action": "Associare ogni bene al processo e conservare matricola, schema e relazione tecnica."},
        {"id": "t40_factory_exchange", "framework": "Transizione 4.0", "area": "Integrazione", "title": "Scambio dati con sistemi di fabbrica", "status": "partial", "evidence": "API e sincronizzazione Edge disponibili; acquisizione Modbus intenzionalmente read-only", "action": "Documentare il flusso con MES/ERP/SCADA e verificare i requisiti di interconnessione del bene agevolato."},
        {"id": "t50_monitoring", "framework": "Transizione 5.0", "area": "Energy dashboarding", "title": "Monitoraggio continuo dei consumi", "status": "ready" if sample_count else "action", "evidence": f"{sample_count} campioni normalizzati; alberatura monte/valle e bilancio 24h", "action": "Definire periodo di osservazione, confini di processo e frequenza di misura nel piano di misura."},
        {"id": "t50_baseline", "framework": "Transizione 5.0", "area": "Risparmio energetico", "title": "Baseline ed EnPI ex ante/ex post", "status": "partial", "evidence": "Delta, KPI e storico disponibili; baseline certificata non ancora congelata", "action": "Aggiungere baseline versionata, variabili di aggiustamento e firma del tecnico abilitato."},
        {"id": "t50_certification", "framework": "Transizione 5.0", "area": "Procedura GSE", "title": "Certificazioni e fascicolo agevolativo", "status": "external", "evidence": "Il software può esportare evidenze, non sostituisce certificazione tecnica e contabile", "action": "Coinvolgere certificatore/perito e commercialista secondo la misura applicabile alla data dell’investimento."},
        {"id": "iso50001_enpi", "framework": "ISO 50001 / 50006", "area": "Prestazione energetica", "title": "EnPI, confini e miglioramento", "status": "partial", "evidence": "KPI, gerarchia energetica, quota non attribuita e storico presenti", "action": "Formalizzare baseline, obiettivi, normalizzazione e riesame periodico."},
        {"id": "meter_traceability", "framework": "MID / metrologia", "area": "Misura", "title": "Tracciabilità metrologica", "status": "action", "evidence": "Modello e profilo registri presenti; certificato e scadenza taratura non archiviati", "action": "Registrare matricola, classe, certificato MID/taratura, data verifica e catena di misura."},
        {"id": "cyber_access", "framework": "IEC 62443 / NIS2", "area": "Accesso e audit", "title": "Controllo accessi e tracciabilità", "status": "ready" if user_count and audit_count else "partial", "evidence": f"RBAC attivo, {user_count} utenti, {audit_count} eventi audit", "action": "Integrare MFA/SSO, revisione periodica degli accessi e conservazione audit definita."},
        {"id": "cra_lifecycle", "framework": "Cyber Resilience Act", "area": "Secure lifecycle", "title": "Vulnerabilità, SBOM e aggiornamenti firmati", "status": "action", "evidence": "Hardening HTTP presente; processo prodotto CRA non ancora documentato", "action": "Introdurre SBOM, vulnerability intake, disclosure, patch SLA, firma e rollback degli aggiornamenti."},
        {"id": "data_act", "framework": "EU Data Act", "area": "Portabilità dati", "title": "Accesso ed esportazione dei dati industriali", "status": "partial", "evidence": "API ed export catalogo disponibili", "action": "Aggiungere export self-service completo, policy di portabilità, contratti e metadati machine-readable."},
        {"id": "backup_continuity", "framework": "IEC 62443 / continuità", "area": "Resilienza", "title": "Backup, ripristino e continuità Edge", "status": "action", "evidence": "Buffer offline e retry presenti; backup verificato non configurato", "action": "Automatizzare backup cifrato, test di restore, retention e procedure disaster recovery."},
        {"id": "alarm_management", "framework": "ISA-18.2", "area": "Allarmi", "title": "Allarmi prioritizzati e azionabili", "status": "ready" if rule_count else "partial", "evidence": f"{rule_count} regole attive con priorità, isteresi, acknowledge e audit", "action": "Approvare filosofia allarmi, KPI di carico e revisione periodica delle soglie."},
    ]
    points = {"ready": 100, "partial": 55, "external": 25, "action": 0}
    score = round(sum(points[item["status"]] for item in controls) / len(controls))
    return {
        "generated_at": utcnow(), "assessment": "readiness_not_certification", "score": score,
        "summary": {"ready": sum(item["status"] == "ready" for item in controls), "partial": sum(item["status"] == "partial" for item in controls), "action": sum(item["status"] in {"action", "external"} for item in controls)},
        "system": {"devices": device_count, "connections": connection_count, "bindings": binding_count, "samples": sample_count, "audit_events": audit_count, "active_alarm_rules": rule_count, "oldest_sample_at": oldest_sample, "newest_sample_at": newest_sample},
        "controls": controls,
        "regulatory_horizon": [
            {"date": "2025-09-12", "title": "EU Data Act applicabile", "impact": "Accesso, uso e portabilità dei dati dei prodotti connessi."},
            {"date": "2026-09-11", "title": "CRA: reporting vulnerabilità", "impact": "Preparare incident e vulnerability reporting per prodotti digitali."},
            {"date": "2027-01-20", "title": "Regolamento Macchine", "impact": "Valutare applicabilità a integrazioni che incidono sulle funzioni della macchina."},
            {"date": "2027-12-11", "title": "Cyber Resilience Act pienamente applicabile", "impact": "Secure-by-design, gestione vulnerabilità e documentazione di prodotto."},
        ],
    }


@app.get("/api/compliance/readiness")
def compliance_status(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return compliance_readiness(db)


@app.get("/api/compliance/evidence-export")
def compliance_evidence(user: User = Depends(current_user), db: Session = Depends(get_db)) -> JSONResponse:
    snapshot = compliance_readiness(db)
    canonical = json.dumps(snapshot, default=str, sort_keys=True, separators=(",", ":"))
    snapshot["integrity"] = {"algorithm": "SHA-256", "digest": hashlib.sha256(canonical.encode()).hexdigest()}
    return JSONResponse(content=json.loads(json.dumps(snapshot, default=str)), headers={"Content-Disposition": 'attachment; filename="energy-manager-evidence.json"'})


@app.post("/api/auth/token")
def login(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()], db: Annotated[Session, Depends(get_db)]) -> dict:
    sensitive_rate_limit(request)
    user = db.scalar(select(User).where(User.username == form.username, User.active.is_(True)))
    if not user or not verify_password(form.password, user.password_hash):
        db.add(AuditEvent(actor=form.username[:100], action="auth.login_failed", target_type="session", target_id=None, details={"source": request.client.host if request.client else "unknown"})); db.commit()
        raise HTTPException(401, "Invalid credentials")
    db.add(AuditEvent(actor=user.username, action="auth.login", target_type="session", target_id=user.id, details={"source": request.client.host if request.client else "unknown"})); db.commit()
    return {"access_token": create_token(user), "token_type": "bearer", "user": {"username": user.username, "role": user.role}}


@app.get("/api/me")
def me(user: Annotated[User, Depends(current_user)], db: Session = Depends(get_db)) -> dict:
    ui_preferences = preference_value(db, "general", {"language": "it", "theme": "system", "refresh_seconds": 5, "compact_numbers": False})
    return {"id": user.id, "username": user.username, "role": user.role, "tenant_id": user.tenant_id, "ui_preferences": ui_preferences}


@app.get("/api/dashboard")
def dashboard(user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_db)], device_id: str | None = None) -> dict:
    if settings.mode == "control-room":
        return {
            "tenants": db.scalar(select(func.count()).select_from(Tenant)) or 0,
            "sites": db.scalar(select(func.count()).select_from(Site)) or 0,
            "edges": db.scalar(select(func.count()).select_from(Edge)) or 0,
            "online_edges": db.scalar(select(func.count()).select_from(Edge).where(Edge.status == "online")) or 0,
            "samples": db.scalar(select(func.count()).select_from(TelemetrySample)) or 0,
        }
    primary_binding = db.scalar(
        select(MeasurementBinding)
        .where(
            MeasurementBinding.role == "primary",
            MeasurementBinding.measurement_key == "electrical.energy.import_total",
        )
        .order_by(MeasurementBinding.created_at)
        .limit(1)
    )
    main_device = db.get(Device, primary_binding.device_id) if primary_binding else None
    if not main_device:
        main_device = db.scalar(select(Device).order_by(Device.unit_id).limit(1))
    if device_id:
        selected_device = db.get(Device, device_id)
        if not selected_device:
            raise HTTPException(404, "Device not found")
        main_device = selected_device
    latest_query = select(TelemetrySample).order_by(TelemetrySample.sample_at.desc()).limit(1000)
    if main_device:
        latest_query = latest_query.where(TelemetrySample.device_id == main_device.id)
    latest = list(db.scalars(latest_query))
    by_key: dict[str, TelemetrySample] = {}
    for sample in latest:
        by_key.setdefault(sample.measurement_key, sample)
    devices = list(db.scalars(select(Device).where(Device.status != "removed")))
    open_alarms = db.scalar(select(func.count()).select_from(AlarmEvent).where(AlarmEvent.status.in_(["open", "acknowledged"]))) or 0
    pending = db.scalar(select(func.count()).select_from(SyncOutbox).where(SyncOutbox.sent_at.is_(None))) or 0
    profile = db.get(DeviceProfile, main_device.profile_id) if main_device else None
    definition = profile.definition if profile else {}
    category = definition.get("category", "multimeter")
    power_key = {
        "pv_inverter": "pv.power.ac_total",
        "battery_storage": "storage.power.active",
        "ev_charger": "ev.power.active",
    }.get(category, "electrical.active_power.total")
    energy_key = {
        "pv_inverter": "pv.energy.today",
        "battery_storage": "storage.energy.discharge_total",
        "ev_charger": "ev.energy.session",
    }.get(category, "electrical.energy.import_total")
    power = by_key.get(power_key) or by_key.get("electrical.active_power.total")
    energy = by_key.get(energy_key) or by_key.get("electrical.energy.import_total")
    site = db.scalar(select(LocalSite).limit(1))
    primary_meter = None
    if main_device:
        primary_meter = {
            "id": main_device.id,
            "name": main_device.name,
            "manufacturer": definition.get("manufacturer", ""),
            "model": definition.get("model", main_device.profile_id),
            "category": category,
            "status": main_device.status,
            "last_valid_poll_at": main_device.last_valid_poll_at,
            "cycle_duration_ms": main_device.cycle_duration_ms,
        }
    point_definitions = definition.get("points", []) + definition.get("derived_points", [])
    point_meta = {point["key"]: point for point in point_definitions}
    def enum_display(key: str, value: Any) -> str | None:
        enum = point_meta.get(key, {}).get("enum")
        if not enum or value is None:
            return None
        try:
            return enum.get(str(int(float(value))))
        except (TypeError, ValueError):
            return None
    measurements = [{
        "key": key,
        "label": point_meta.get(key, {}).get("label", key),
        "group": point_meta.get(key, {}).get("group", "Misure"),
        "value": sample.value,
        "display_value": enum_display(key, sample.value),
        "unit": sample.unit,
        "quality": sample.quality,
        "sample_at": sample.sample_at,
    } for key, sample in by_key.items()]
    device_options = []
    for device in devices:
        device_profile = db.get(DeviceProfile, device.profile_id)
        device_definition = device_profile.definition if device_profile else {}
        device_options.append({"id": device.id, "name": device.name, "manufacturer": device_definition.get("manufacturer", ""), "model": device_definition.get("model", device.profile_id), "category": device_definition.get("category", "device"), "status": device.status, "last_valid_poll_at": device.last_valid_poll_at})
    series = list(db.scalars(select(TelemetrySample).where(TelemetrySample.device_id == main_device.id, TelemetrySample.measurement_key == power_key).order_by(TelemetrySample.sample_at.desc()).limit(60))) if main_device else []
    active_events = list(db.scalars(select(AlarmEvent).where(AlarmEvent.status.in_(["open", "acknowledged"])).order_by(AlarmEvent.opened_at.desc()).limit(8)))
    rules_count = db.scalar(select(func.count()).select_from(AlarmRule).where(AlarmRule.active.is_(True))) or 0
    return {
        "site_name": site.name if site else None,
        "primary_meter": primary_meter,
        "devices": device_options,
        "measurements": sorted(measurements, key=lambda item: (item["group"], item["label"])),
        "active_alarms": [as_dict(event) for event in active_events],
        "active_rules": rules_count,
        "power_kw": power.value if power else None,
        "energy_kwh": energy.value if energy else None,
        "primary_power_key": power_key,
        "primary_energy_key": energy_key,
        "power_factor": by_key.get("electrical.power_factor.total").value if by_key.get("electrical.power_factor.total") else None,
        "frequency_hz": by_key.get("electrical.frequency").value if by_key.get("electrical.frequency") else None,
        "peak_kw": max((s.value for s in series if s.value is not None), default=None),
        "devices_online": sum(d.status == "online" for d in devices),
        "devices_total": len(devices),
        "open_alarms": open_alarms,
        "quality": "good" if latest else "missing",
        "sync_pending": pending,
        "tailscale": NetworkAgent(dry_run=True).diagnostics(),
        "series": [{"time": s.sample_at, "value": s.value} for s in reversed(series)],
        "updated_at": max((sample.sample_at for sample in by_key.values()), default=None),
    }


@app.get("/api/catalog")
def catalog_list(user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_db)]) -> list[dict]:
    profiles = list(db.scalars(select(CatalogProfile).order_by(CatalogProfile.manufacturer, CatalogProfile.model)))
    result: list[dict] = []
    for profile in profiles:
        version = db.scalar(
            select(CatalogProfileVersion).where(
                CatalogProfileVersion.profile_id == profile.id,
                CatalogProfileVersion.version == profile.latest_version,
            )
        )
        definition = version.definition if version else {}
        result.append(
            {
                **as_dict(profile),
                "description": definition.get("description", ""),
                "protocols": definition.get("protocols", []),
                "capabilities": definition.get("capabilities", {}),
                "driver": definition.get("driver", {}),
                "documentation": definition.get("documentation", {}),
            }
        )
    return result


@app.get("/api/plant")
def plant(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if settings.mode != "edge": raise HTTPException(404)
    site = db.scalar(select(LocalSite).limit(1))
    bindings = db.execute(select(MeasurementBinding, AssetNode.name, Device.name).join(AssetNode, MeasurementBinding.asset_id == AssetNode.id).join(Device, MeasurementBinding.device_id == Device.id)).all()
    return {
        "site": as_dict(site) if site else None,
        "connections": [as_dict(item) for item in db.scalars(select(Connection).order_by(Connection.name))],
        "devices": [as_dict(item) for item in db.scalars(select(Device).where(Device.status != "removed").order_by(Device.name))],
        "assets": [as_dict(item) for item in db.scalars(select(AssetNode).order_by(AssetNode.sort_order, AssetNode.name))],
        "bindings": [{**as_dict(binding), "asset_name": asset_name, "device_name": device_name} for binding, asset_name, device_name in bindings],
        "profiles": [as_dict(item) for item in db.scalars(select(DeviceProfile).where(DeviceProfile.valid.is_(True)).order_by(DeviceProfile.id))],
    }


@app.get("/api/operations/tree")
def operations_tree(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Return the energy hierarchy with authoritative upstream values and downstream allocation."""
    assets = list(db.scalars(select(AssetNode).where(AssetNode.active.is_(True)).order_by(AssetNode.sort_order, AssetNode.name)))
    devices = list(db.scalars(select(Device).where(Device.active.is_(True)).order_by(Device.name)))
    bindings = list(db.scalars(select(MeasurementBinding).order_by(MeasurementBinding.created_at)))
    device_by_id = {device.id: device for device in devices}
    asset_devices: dict[str, list[str]] = defaultdict(list)
    assigned: set[str] = set()
    for binding in bindings:
        if binding.device_id in device_by_id and binding.device_id not in asset_devices[binding.asset_id]:
            asset_devices[binding.asset_id].append(binding.device_id)
            assigned.add(binding.device_id)

    def latest_value(device_id: str, key: str) -> tuple[float | None, datetime | None, str]:
        sample = db.scalar(select(TelemetrySample).where(TelemetrySample.device_id == device_id, TelemetrySample.measurement_key == key).order_by(TelemetrySample.sample_at.desc()).limit(1))
        if not sample: return (None, None, "missing")
        return (sample.value if sample.quality == "good" else None, sample.sample_at, sample.quality)

    device_stats: dict[str, dict[str, Any]] = {}
    for device in devices:
        profile = db.get(DeviceProfile, device.profile_id)
        definition = profile.definition if profile else {}
        category = definition.get("category", "device")
        power_key = {
            "pv_inverter": "pv.power.ac_total",
            "battery_storage": "storage.power.active",
            "ev_charger": "ev.power.active",
        }.get(category, "electrical.active_power.total")
        energy_keys = {
            "pv_inverter": ["pv.energy.total", "pv.energy.today"],
            "battery_storage": ["storage.energy.discharge_total"],
            "ev_charger": ["ev.energy.total", "ev.energy.session"],
        }.get(category, ["electrical.energy.import_total"])
        power, power_at, power_quality = latest_value(device.id, power_key)
        energy = energy_at = None
        energy_quality = "missing"
        energy_key = energy_keys[0]
        for candidate_key in energy_keys:
            candidate, candidate_at, candidate_quality = latest_value(device.id, candidate_key)
            if candidate is not None:
                energy, energy_at, energy_quality, energy_key = candidate, candidate_at, candidate_quality, candidate_key
                break
        # Some vendor drivers expose only the normalized electrical fallback.
        if power is None and power_key != "electrical.active_power.total":
            power, power_at, power_quality = latest_value(device.id, "electrical.active_power.total")
        period_start_sample = db.scalar(select(TelemetrySample).where(
            TelemetrySample.device_id == device.id,
            TelemetrySample.measurement_key == energy_key,
            TelemetrySample.sample_at >= utcnow() - timedelta(hours=24),
            TelemetrySample.quality == "good",
        ).order_by(TelemetrySample.sample_at).limit(1))
        energy_24h = None
        if energy is not None and period_start_sample and period_start_sample.value is not None:
            energy_24h = counter_delta(float(period_start_sample.value), float(energy)).value
        device_stats[device.id] = {
            "id": device.id, "name": device.name, "manufacturer": definition.get("manufacturer", ""),
            "model": definition.get("model", device.profile_id), "category": category, "status": device.status,
            "power_kw": power, "energy_kwh": energy, "sample_at": power_at or energy_at,
            "energy_24h_kwh": energy_24h,
            "quality": power_quality if power is not None else energy_quality,
            "power_key": power_key, "energy_key": energy_key,
        }

    children_by_parent: dict[str | None, list[AssetNode]] = defaultdict(list)
    for asset in assets:
        children_by_parent[asset.parent_id].append(asset)

    def build(asset: AssetNode) -> dict[str, Any]:
        children = [build(child) for child in children_by_parent.get(asset.id, [])]
        meters = [device_stats[device_id] for device_id in asset_devices.get(asset.id, [])]
        meter = meters[0] if meters else None
        downstream_power = sum(child["effective_power_kw"] for child in children if child["effective_power_kw"] is not None)
        downstream_energy = sum(child["effective_energy_kwh"] for child in children if child["effective_energy_kwh"] is not None)
        has_downstream_power = any(child["effective_power_kw"] is not None for child in children)
        has_downstream_energy = any(child["effective_energy_kwh"] is not None for child in children)
        measured_power = meter["power_kw"] if meter else None
        measured_energy = meter["energy_kwh"] if meter else None
        measured_energy_24h = meter["energy_24h_kwh"] if meter else None
        downstream_energy_24h = sum(child["effective_energy_24h_kwh"] for child in children if child["effective_energy_24h_kwh"] is not None)
        has_downstream_energy_24h = any(child["effective_energy_24h_kwh"] is not None for child in children)
        effective_power = measured_power if measured_power is not None else (downstream_power if has_downstream_power else None)
        effective_energy = measured_energy if measured_energy is not None else (downstream_energy if has_downstream_energy else None)
        effective_energy_24h = measured_energy_24h if measured_energy_24h is not None else (downstream_energy_24h if has_downstream_energy_24h else None)
        residual_power = measured_power - downstream_power if measured_power is not None and has_downstream_power else None
        residual_energy = measured_energy - downstream_energy if measured_energy is not None and has_downstream_energy else None
        coverage = downstream_power / measured_power * 100 if measured_power not in {None, 0} and has_downstream_power else None
        return {
            "id": asset.id, "parent_id": asset.parent_id, "name": asset.name, "category": asset.category,
            "description": asset.description, "meter": meter, "meters": meters, "children": children,
            "measured_power_kw": measured_power, "measured_energy_kwh": measured_energy,
            "downstream_power_kw": downstream_power if has_downstream_power else None,
            "downstream_energy_kwh": downstream_energy if has_downstream_energy else None,
            "effective_power_kw": effective_power, "effective_energy_kwh": effective_energy,
            "measured_energy_24h_kwh": measured_energy_24h,
            "downstream_energy_24h_kwh": downstream_energy_24h if has_downstream_energy_24h else None,
            "effective_energy_24h_kwh": effective_energy_24h,
            "residual_energy_24h_kwh": measured_energy_24h - downstream_energy_24h if measured_energy_24h is not None and has_downstream_energy_24h else None,
            "residual_power_kw": residual_power, "residual_energy_kwh": residual_energy,
            "coverage_percent": coverage,
        }

    roots = [build(asset) for asset in children_by_parent.get(None, [])]
    plant_power = sum(root["effective_power_kw"] for root in roots if root["effective_power_kw"] is not None)
    plant_energy = sum(root["effective_energy_kwh"] for root in roots if root["effective_energy_kwh"] is not None)
    plant_energy_24h = sum(root["effective_energy_24h_kwh"] for root in roots if root["effective_energy_24h_kwh"] is not None)
    unassigned = [device_stats[device.id] for device in devices if device.id not in assigned]
    return {
        "roots": roots,
        "plant": {"power_kw": plant_power, "energy_kwh": plant_energy, "energy_24h_kwh": plant_energy_24h, "root_count": len(roots)},
        "unassigned_devices": unassigned,
        "calculation_policy": "upstream_meter_authoritative_else_sum_children",
    }


@app.get("/api/energy/overview")
def energy_overview(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Vendor-neutral power-flow snapshot for grid, generation, storage and flexible loads."""
    devices = list(db.scalars(select(Device).where(Device.active.is_(True)).order_by(Device.name)))
    rows = list(db.scalars(select(TelemetrySample).where(TelemetrySample.quality == "good").order_by(TelemetrySample.sample_at.desc()).limit(10000)))
    latest: dict[tuple[str, str], TelemetrySample] = {}
    for sample in rows: latest.setdefault((sample.device_id, sample.measurement_key), sample)

    def value(device_id: str, *keys: str) -> float | None:
        for key in keys:
            sample = latest.get((device_id, key))
            if sample and sample.value is not None: return float(sample.value)
        return None

    inventory = []
    for device in devices:
        profile = db.get(DeviceProfile, device.profile_id)
        definition = profile.definition if profile else {}
        category = definition.get("category", "device")
        headline_keys = {
            "pv_inverter": ("pv.power.ac_total", "electrical.active_power.total"),
            "battery_storage": ("storage.power.active",),
            "ev_charger": ("ev.power.active", "electrical.active_power.total"),
            "multimeter": ("electrical.active_power.total",),
        }.get(category, ("electrical.active_power.total",))
        inventory.append({
            "id": device.id, "name": device.name, "category": category,
            "manufacturer": definition.get("manufacturer", ""), "model": definition.get("model", device.profile_id),
            "status": device.status, "power_kw": value(device.id, *headline_keys),
            "soc_percent": value(device.id, "storage.soc"), "energy_today_kwh": value(device.id, "pv.energy.today"),
            "temperature_c": value(device.id, "pv.inverter.temperature", "storage.temperature"),
            "updated_at": max((sample.sample_at for (owner, _), sample in latest.items() if owner == device.id), default=None),
        })

    def total(category: str) -> float:
        return sum(item["power_kw"] for item in inventory if item["category"] == category and item["power_kw"] is not None)

    primary_binding = db.scalar(select(MeasurementBinding).where(MeasurementBinding.role == "primary", MeasurementBinding.measurement_key == "electrical.energy.import_total").order_by(MeasurementBinding.created_at).limit(1))
    authoritative_grid = next((item for item in inventory if primary_binding and item["id"] == primary_binding.device_id and item["power_kw"] is not None), None)
    grid_candidates = [item for item in inventory if item["category"] == "multimeter" and item["power_kw"] is not None]
    grid_power = authoritative_grid["power_kw"] if authoritative_grid else grid_candidates[0]["power_kw"] if grid_candidates else 0.0
    solar_power = total("pv_inverter")
    storage_power = total("battery_storage")  # positive discharge, negative charge
    ev_power = max(0.0, total("ev_charger"))
    estimated_load = max(0.0, grid_power + solar_power + max(storage_power, 0) - max(-storage_power, 0))
    solar_to_load = min(max(solar_power, 0), estimated_load)
    self_consumption = solar_to_load / solar_power * 100 if solar_power > 0 else None
    renewable_share = solar_to_load / estimated_load * 100 if estimated_load > 0 else None
    storage_items = [item for item in inventory if item["category"] == "battery_storage" and item["soc_percent"] is not None]
    average_soc = sum(item["soc_percent"] for item in storage_items) / len(storage_items) if storage_items else None
    return {
        "generated_at": utcnow(), "inventory": inventory,
        "counts": {category: sum(item["category"] == category for item in inventory) for category in {item["category"] for item in inventory}},
        "flows": {
            "grid_kw": grid_power, "solar_kw": solar_power, "storage_kw": storage_power,
            "load_kw": estimated_load, "ev_kw": ev_power,
            "grid_direction": "import" if grid_power >= 0 else "export", "grid_device_id": authoritative_grid["id"] if authoritative_grid else None,
            "storage_direction": "discharge" if storage_power > 0 else "charge" if storage_power < 0 else "idle",
        },
        "kpis": {
            "self_consumption_percent": self_consumption, "renewable_share_percent": renewable_share,
            "storage_soc_percent": average_soc, "devices_online": sum(item["status"] == "online" for item in inventory),
            "devices_degraded": sum(item["status"] == "degraded" for item in inventory), "devices_total": len(inventory),
        },
    }


@app.put("/api/plant/site")
def update_local_site(data: LocalSiteInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    if settings.mode != "edge": raise HTTPException(404)
    site = db.scalar(select(LocalSite).limit(1))
    if not site:
        site = LocalSite(name=data.name); db.add(site)
    else:
        site.name = data.name
    db.add(AuditEvent(actor=user.username, action="plant.site.update", target_type="local_site", target_id=site.id, details={"name": data.name}))
    db.commit(); return as_dict(site)


def energy_configuration(db: Session) -> EnergySettings:
    configuration = db.scalar(select(EnergySettings).limit(1))
    if not configuration:
        configuration = EnergySettings()
        db.add(configuration); db.commit(); db.refresh(configuration)
    return configuration


@app.get("/api/energy/settings")
def get_energy_settings(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if settings.mode != "edge": raise HTTPException(404)
    return as_dict(energy_configuration(db))


@app.put("/api/energy/settings")
def update_energy_settings(data: EnergySettingsInput, user: User = Depends(require_roles("platform_admin", "technician", "customer_admin")), db: Session = Depends(get_db)) -> dict:
    if settings.mode != "edge": raise HTTPException(404)
    try:
        safe_zone(data.timezone)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if data.workday_start >= data.workday_end:
        raise HTTPException(422, "L'orario di fine attività deve essere successivo a quello di inizio")
    if any(day < 0 or day > 6 for day in data.working_days) or len(set(data.working_days)) != len(data.working_days):
        raise HTTPException(422, "I giorni lavorativi devono essere univoci e compresi tra 0 e 6")
    configuration = energy_configuration(db)
    for key, value in data.model_dump().items():
        setattr(configuration, key, value)
    db.add(AuditEvent(actor=user.username, action="energy.settings.update", target_type="energy_settings", target_id=configuration.id, details={"currency": data.currency, "timezone": data.timezone, "working_days": data.working_days}))
    db.commit(); db.refresh(configuration)
    return as_dict(configuration)


def energy_report_for(period: str, db: Session) -> dict[str, Any]:
    if settings.mode != "edge": raise HTTPException(404)
    if period not in {"day", "week", "month", "year"}:
        raise HTTPException(422, "Il periodo deve essere day, week, month oppure year")
    return build_energy_report(db, energy_configuration(db), period)


@app.get("/api/energy/report")
def energy_report(period: str = "month", user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return energy_report_for(period, db)


@app.get("/api/energy/report.csv")
def export_energy_report(period: str = "month", user: User = Depends(current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    report = energy_report_for(period, db)
    stream = io.StringIO()
    writer = csv.writer(stream, delimiter=";")
    writer.writerow(["sezione", "voce", "valore", "unità"])
    for key, unit in (("import_kwh", "kWh"), ("export_kwh", "kWh"), ("production_kwh", "kWh"), ("self_consumed_kwh", "kWh"), ("off_hours_kwh", "kWh"), ("unattributed_kwh", "kWh")):
        writer.writerow(["energia", key, report["energy"].get(key), unit])
    for key, unit in (("average_kw", "kW"), ("peak_kw", "kW"), ("contracted_kw", "kW"), ("coverage_percent", "%")):
        writer.writerow(["potenza", key, report["power"].get(key), unit])
    for key in ("energy_cost", "export_revenue", "net_cost", "projected_month_cost", "monthly_cost_budget"):
        writer.writerow(["economia", key, report["economics"].get(key), report["economics"]["currency"]])
    writer.writerow(["ambiente", "co2_kg", report["environment"]["co2_kg"], "kgCO2e"])
    writer.writerow([])
    writer.writerow(["ripartizione", "asset", "dispositivo", "energia_kwh", "qualità"])
    for item in report["breakdown"]:
        writer.writerow(["utenza", item["asset_name"], item["device_name"], item["energy_kwh"], item["quality"]])
    writer.writerow([])
    writer.writerow(["serie", "timestamp", "energia_kwh"])
    for item in report["timeline"]:
        writer.writerow(["consumo", item["time"], item["energy_kwh"]])
    payload = ("\ufeff" + stream.getvalue()).encode("utf-8")
    headers = {"Content-Disposition": f'attachment; filename="energy-report-{period}-{utcnow().date().isoformat()}.csv"'}
    return StreamingResponse(iter([payload]), media_type="text/csv; charset=utf-8", headers=headers)


@app.post("/api/catalog/import")
async def catalog_import(user: Annotated[User, Depends(require_roles("platform_admin", "technician"))], db: Annotated[Session, Depends(get_db)], file: UploadFile = File(...)) -> dict:
    content = (await file.read()).decode("utf-8")
    try: raw = parse_profile(content, "json" if file.filename and file.filename.endswith(".json") else "yaml")
    except Exception as exc: raise HTTPException(422, f"Cannot parse catalog: {exc}") from exc
    try: documents = expand_catalog_document(raw)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    validated = []
    all_errors = []
    for document in documents:
        profile, errors = validate_profile(document)
        if errors: all_errors.extend([f"{document.get('id', 'profile')}: {error}" for error in errors])
        else: validated.append(profile)
    if all_errors: return JSONResponse(status_code=422, content={"valid": False, "errors": all_errors})
    imported = []
    for profile in validated:
        definition = profile.model_dump()
        existing = db.get(CatalogProfile, profile.id)
        version_row = db.scalar(select(CatalogProfileVersion).where(CatalogProfileVersion.profile_id == profile.id, CatalogProfileVersion.version == profile.version))
        if not existing:
            db.add(CatalogProfile(id=profile.id, manufacturer=profile.manufacturer, model=profile.model, category=profile.category, latest_version=profile.version))
        else:
            existing.latest_version = profile.version; existing.manufacturer = profile.manufacturer; existing.model = profile.model; existing.category = profile.category
        if not version_row: db.add(CatalogProfileVersion(profile_id=profile.id, version=profile.version, definition=definition, valid=True))
        if settings.mode == "edge":
            local = db.get(DeviceProfile, profile.id)
            if local: local.version = profile.version; local.definition = definition; local.valid = True
            else: db.add(DeviceProfile(id=profile.id, version=profile.version, definition=definition, valid=True))
            existing_keys = set(db.scalars(select(RegisterDefinition.key).where(RegisterDefinition.profile_id == profile.id)))
            for point in definition["points"]:
                if point["key"] not in existing_keys: db.add(RegisterDefinition(profile_id=profile.id, key=point["key"], definition=point))
        db.add(AuditEvent(actor=user.username, action="catalog.import", target_type="profile", target_id=profile.id, details={"version": profile.version}))
        imported.append({"id": profile.id, "version": profile.version})
    db.commit()
    result = {"valid": True, "profiles": imported}
    if len(imported) == 1: result.update(imported[0])
    return result


@app.get("/api/catalog/{profile_id}/export")
def catalog_export(profile_id: str, user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_db)]):
    row = db.scalar(select(CatalogProfileVersion).where(CatalogProfileVersion.profile_id == profile_id).order_by(CatalogProfileVersion.created_at.desc()))
    if not row: raise HTTPException(404, "Profile not found")
    return JSONResponse(content=row.definition, headers={"Content-Disposition": f'attachment; filename="{profile_id}.json"'})


@app.post("/api/catalog/{profile_id}/duplicate")
def catalog_duplicate(profile_id: str, user: Annotated[User, Depends(require_roles("platform_admin", "technician"))], db: Annotated[Session, Depends(get_db)]) -> dict:
    source = db.scalar(select(CatalogProfileVersion).where(CatalogProfileVersion.profile_id == profile_id).order_by(CatalogProfileVersion.created_at.desc()))
    if not source: raise HTTPException(404, "Profile not found")
    new_id = next_copy_id(profile_id); suffix = 2
    while db.get(CatalogProfile, new_id): new_id = f"{next_copy_id(profile_id)}-{suffix}"; suffix += 1
    definition = dict(source.definition); definition["id"] = new_id
    db.add(CatalogProfile(id=new_id, manufacturer=definition["manufacturer"], model=definition["model"] + " Copy", category=definition["category"], latest_version=definition["version"]))
    db.add(CatalogProfileVersion(profile_id=new_id, version=definition["version"], definition=definition, valid=True))
    if settings.mode == "edge": db.add(DeviceProfile(id=new_id, version=definition["version"], definition=definition, valid=True))
    db.commit(); return {"id": new_id}


@app.post("/api/catalog/validate")
def catalog_validate(raw: dict = Body(...), user: User = Depends(current_user)) -> dict:
    try: documents = expand_catalog_document(raw)
    except ValueError as exc: return {"valid": False, "errors": [str(exc)]}
    errors = []
    for document in documents: errors.extend(validate_profile(document)[1])
    return {"valid": not errors, "errors": errors, "profiles": len(documents)}


@app.post("/api/catalog/preview")
def catalog_preview(payload: dict = Body(...), user: User = Depends(current_user)) -> dict:
    try: return {"value": decode_registers(payload["registers"], payload["definition"])}
    except Exception as exc: raise HTTPException(422, str(exc)) from exc


@app.get("/api/connections")
def connections(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [as_dict(item) for item in db.scalars(select(Connection))]


@app.post("/api/discovery/modbus")
async def modbus_discovery(data: ModbusDiscoveryInput, request: Request, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    if settings.mode != "edge": raise HTTPException(404)
    sensitive_rate_limit(request, limit=5, window_seconds=60)
    try:
        network = parse_scan_network(data.network)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if data.unit_to < data.unit_from or data.unit_to - data.unit_from + 1 > 32:
        raise HTTPException(422, "L'intervallo slave deve contenere da 1 a 32 Unit ID consecutivi")
    if len(set(data.ports)) != len(data.ports) or any(port < 1 or port > 65535 for port in data.ports):
        raise HTTPException(422, "Le porte devono essere univoche e comprese tra 1 e 65535")
    profiles = [{"id": item.id, "definition": item.definition} for item in db.scalars(select(DeviceProfile).where(DeviceProfile.valid.is_(True)))]
    connections_by_id = {
        item.id: item
        for item in db.scalars(select(Connection).where(Connection.kind.in_(["modbus_tcp", "modbus_rtu_tcp"])))
    }
    configured = set()
    for device in db.scalars(select(Device).where(Device.status != "removed")):
        connection = connections_by_id.get(device.connection_id)
        if connection:
            endpoint = device.config if connection.kind == "modbus_tcp" and device.config else connection.config
            unit_id = int((device.config or {}).get("protocol_unit_id", device.unit_id)) if connection.kind == "modbus_tcp" else device.unit_id
            configured.update((host, int(endpoint.get("port", 502)), unit_id) for host in resolved_ipv4(str(endpoint.get("host", ""))))
    result = await discover_modbus(network, sorted(data.ports), list(range(data.unit_from, data.unit_to + 1)), data.timeout_seconds, data.probe_address, profiles, configured)
    db.add(AuditEvent(actor=user.username, action="modbus.discovery", target_type="network", target_id=str(network), details={"ports": data.ports, "unit_from": data.unit_from, "unit_to": data.unit_to, "devices_found": result["devices_found"], "elapsed_ms": result["elapsed_ms"]}))
    db.commit()
    return result


@app.post("/api/discovery/modbus/install")
def install_discovered_modbus(data: ModbusDiscoveredInstallInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    if settings.mode != "edge": raise HTTPException(404)
    try:
        host = str(parse_scan_network(f"{data.host}/32").network_address)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    profile = db.get(DeviceProfile, data.profile_id)
    required_protocol = "modbus_tcp" if data.transport == "modbus_tcp" else "modbus_rtu"
    if not profile or not profile.valid or required_protocol not in profile.definition.get("protocols", []):
        raise HTTPException(422, "Il driver selezionato non supporta il trasporto rilevato")
    connections = list(db.scalars(select(Connection).where(Connection.kind == data.transport)))
    if data.transport == "modbus_tcp":
        connection = next((item for item in connections if not item.config.get("host")), None)
    else:
        connection = next((item for item in connections if host in resolved_ipv4(str(item.config.get("host"))) and int(item.config.get("port", 502)) == data.port), None)
    created_connection = False
    if not connection:
        if data.transport == "modbus_tcp":
            connection = Connection(name="Rete dispositivi Modbus TCP", kind="modbus_tcp", config={"port": 502, "timeout": 2.0, "retry": 1}, status="online", last_test_at=utcnow())
        else:
            connection = Connection(name=f"Gateway RTU {host}:{data.port}", kind="modbus_rtu_tcp", config={"host": host, "port": data.port, "timeout": 2.0, "retry": 1}, status="online", last_test_at=utcnow())
        db.add(connection); db.flush(); created_connection = True
    device_input = DeviceInput(
        connection_id=connection.id,
        profile_id=profile.id,
        name=data.device_name,
        unit_id=data.unit_id if data.transport == "modbus_rtu_tcp" else None,
        config={"host": host, "port": data.port, "protocol_unit_id": data.unit_id} if data.transport == "modbus_tcp" else {},
    )
    values = _normalized_device_values(device_input, connection, profile)
    _assert_device_address_available(db, connection, values)
    device = Device(**values, active=True, status="unknown")
    db.add(device); db.flush()
    db.add(AuditEvent(actor=user.username, action="modbus.discovery.install", target_type="device", target_id=device.id, details={"host": host, "port": data.port, "unit_id": data.unit_id, "transport": data.transport, "profile_id": profile.id, "connection_created": created_connection}))
    db.commit(); db.refresh(device)
    return {"connection": as_dict(connection), "device": as_dict(device), "connection_created": created_connection}


@app.post("/api/connections")
def create_connection(data: ConnectionInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    try: config = validate_connection_config(data.kind, data.config)
    except (ValueError, TypeError) as exc: raise HTTPException(422, str(exc)) from exc
    item = Connection(name=data.name, kind=data.kind, config=config); db.add(item); db.flush()
    db.add(AuditEvent(actor=user.username, action="connection.create", target_type="connection", target_id=item.id, details={"name": item.name, "kind": item.kind}))
    db.commit(); return as_dict(item)


@app.put("/api/connections/{connection_id}")
def update_connection(connection_id: str, data: ConnectionInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    try: config = validate_connection_config(data.kind, data.config)
    except (ValueError, TypeError) as exc: raise HTTPException(422, str(exc)) from exc
    item = db.get(Connection, connection_id)
    if not item: raise HTTPException(404, "Connection not found")
    if item.kind != data.kind and db.scalar(select(Device.id).where(Device.connection_id == connection_id, Device.status != "removed").limit(1)):
        raise HTTPException(409, "Rimuovere o spostare i dispositivi prima di cambiare il tipo di canale")
    item.name = data.name; item.kind = data.kind; item.config = config
    item.status = "unknown"; item.last_error = None
    db.add(AuditEvent(actor=user.username, action="connection.update", target_type="connection", target_id=item.id, details={"name": item.name, "kind": item.kind}))
    db.commit(); return as_dict(item)


@app.delete("/api/connections/{connection_id}")
def delete_connection(connection_id: str, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    item = db.get(Connection, connection_id)
    if not item: raise HTTPException(404, "Connessione non trovata")
    device_count = db.scalar(select(func.count()).select_from(Device).where(Device.connection_id == connection_id, Device.status != "removed")) or 0
    if device_count: raise HTTPException(409, f"La connessione è usata da {device_count} dispositivi. Rimuovili o spostali prima.")
    db.add(AuditEvent(actor=user.username, action="connection.delete", target_type="connection", target_id=item.id, details={"name": item.name}))
    db.delete(item); db.commit(); return {"deleted": connection_id}


@app.post("/api/connections/{connection_id}/test")
async def test_connection(connection_id: str, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    connection = db.get(Connection, connection_id)
    if not connection: raise HTTPException(404, "Connection not found")
    device = db.scalar(select(Device).where(Device.connection_id == connection_id, Device.status != "removed").limit(1))
    if not device: raise HTTPException(409, "No device configured")
    count = await poll_device(device.id); db.refresh(connection)
    connection.last_test_at = utcnow(); connection.status = "online" if count else "offline"; db.commit()
    return {"status": connection.status, "samples": count}


@app.get("/api/devices")
def devices(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [as_dict(item) for item in db.scalars(select(Device).where(Device.status != "removed").order_by(Device.name))]


def _profile_protocol(connection_kind: str) -> str:
    return "modbus_rtu" if connection_kind in {"modbus_rtu", "modbus_rtu_tcp"} else "modbus_tcp"


def _normalized_device_values(data: DeviceInput, connection: Connection, profile: DeviceProfile) -> dict[str, Any]:
    required_protocol = _profile_protocol(connection.kind)
    if required_protocol not in profile.definition.get("protocols", []):
        raise HTTPException(422, f"Il driver {data.profile_id} non supporta il trasporto selezionato")
    if connection.kind == "modbus_tcp":
        try:
            config = validate_device_connection_config(
                connection.kind,
                data.config,
                int(connection.config.get("port", 502)),
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        unit_id = int(config.get("protocol_unit_id", profile.definition.get("defaults", {}).get("unit_id", 1)))
    else:
        if data.unit_id is None:
            raise HTTPException(422, "Lo Unit ID è obbligatorio per RTU e RTU-over-TCP")
        unit_id = data.unit_id
        config = {}
    return {
        "connection_id": data.connection_id,
        "profile_id": data.profile_id,
        "name": data.name,
        "unit_id": unit_id,
        "config": config,
    }


def _assert_device_address_available(db: Session, connection: Connection, values: dict[str, Any], exclude_id: str | None = None) -> None:
    devices = list(db.scalars(select(Device).where(Device.status != "removed")))
    if exclude_id:
        devices = [device for device in devices if device.id != exclude_id]
    if connection.kind == "modbus_tcp":
        endpoint = (values["config"].get("host", "").lower(), int(values["config"].get("port", 502)))
        for device in devices:
            device_connection = db.get(Connection, device.connection_id)
            if not device_connection or device_connection.kind != "modbus_tcp":
                continue
            existing_config = device.config or device_connection.config
            existing = (str(existing_config.get("host", "")).lower(), int(existing_config.get("port", 502)))
            if existing == endpoint:
                raise HTTPException(409, "Questo endpoint IP è già assegnato a un dispositivo Modbus TCP")
        return
    duplicate = next(
        (
            device
            for device in devices
            if device.connection_id == connection.id and device.unit_id == values["unit_id"]
        ),
        None,
    )
    if duplicate:
        raise HTTPException(409, "Unit ID già configurato su questo bus")


@app.post("/api/devices")
def create_device(data: DeviceInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    connection = db.get(Connection, data.connection_id)
    profile = db.get(DeviceProfile, data.profile_id)
    if not connection or not profile:
        raise HTTPException(422, "Unknown connection or profile")
    values = _normalized_device_values(data, connection, profile)
    _assert_device_address_available(db, connection, values)
    item = Device(**values); db.add(item); db.flush()
    db.add(AuditEvent(actor=user.username, action="device.create", target_type="device", target_id=item.id, details={"name": item.name, "profile_id": item.profile_id, "unit_id": item.unit_id}))
    db.commit(); return as_dict(item)


@app.post("/api/provisioning/devices")
def provision_device(data: DeviceProvisioningInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    """Install a device and place its primary measurement in the energy tree atomically."""
    profile = db.get(DeviceProfile, data.device.profile_id)
    connection_created = False
    device_input = data.device
    if data.auto_connection_kind == "modbus_tcp":
        connection = next(
            (
                item
                for item in db.scalars(select(Connection).where(Connection.kind == "modbus_tcp").order_by(Connection.created_at))
                if not item.config.get("host")
            ),
            None,
        )
        if not connection:
            connection = Connection(
                name="Rete dispositivi Modbus TCP",
                kind="modbus_tcp",
                config={"port": 502, "timeout": 2.0, "retry": 1},
            )
            db.add(connection)
            db.flush()
            connection_created = True
        device_input = data.device.model_copy(update={"connection_id": connection.id})
    else:
        connection = db.get(Connection, data.device.connection_id)
    if not connection or not profile:
        raise HTTPException(422, "Connessione o driver non trovato")
    device_values = _normalized_device_values(device_input, connection, profile)
    _assert_device_address_available(db, connection, device_values)

    available_keys = {
        point.get("key")
        for point in [
            *profile.definition.get("points", []),
            *profile.definition.get("derived_points", []),
        ]
    }
    if data.measurement_key not in available_keys:
        raise HTTPException(422, "La misura primaria non appartiene al driver selezionato")

    placement = data.placement
    asset = db.get(AssetNode, placement.asset_id) if placement.asset_id else None
    if placement.asset_id and not asset:
        raise HTTPException(422, "Posizione nell'albero non trovata")
    if not asset:
        if not placement.name:
            raise HTTPException(422, "Indicare il nome del nuovo nodo energetico")
        if placement.parent_id and not db.get(AssetNode, placement.parent_id):
            raise HTTPException(422, "Nodo superiore non trovato")
        sibling_count = db.scalar(
            select(func.count()).select_from(AssetNode).where(AssetNode.parent_id == placement.parent_id)
        ) or 0
        asset = AssetNode(
            name=placement.name,
            parent_id=placement.parent_id,
            category=placement.category,
            description=f"Creato durante il provisioning di {data.device.name}",
            sort_order=sibling_count,
            active=True,
        )
        db.add(asset)
        db.flush()

    device = Device(**device_values, active=True, status="unknown")
    db.add(device)
    db.flush()
    binding = MeasurementBinding(
        asset_id=asset.id,
        device_id=device.id,
        measurement_key=data.measurement_key,
        role="primary",
    )
    db.add(binding)
    db.add(
        AuditEvent(
            actor=user.username,
            action="device.provision",
            target_type="device",
            target_id=device.id,
            details={
                "name": device.name,
                "profile_id": device.profile_id,
                "connection_id": device.connection_id,
                "unit_id": device.unit_id,
                "asset_id": asset.id,
                "asset_created": placement.asset_id is None,
                "measurement_key": data.measurement_key,
                "connection_created": connection_created,
            },
        )
    )
    db.commit()
    return {"device": as_dict(device), "asset": as_dict(asset), "binding": as_dict(binding), "connection_created": connection_created}


@app.put("/api/devices/{device_id}")
def update_device(device_id: str, data: DeviceInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    item = db.get(Device, device_id)
    if not item or item.status == "removed": raise HTTPException(404, "Device not found")
    connection = db.get(Connection, data.connection_id)
    profile = db.get(DeviceProfile, data.profile_id)
    if not connection or not profile: raise HTTPException(422, "Unknown connection or profile")
    values = _normalized_device_values(data, connection, profile)
    _assert_device_address_available(db, connection, values, exclude_id=device_id)
    for key, value in values.items(): setattr(item, key, value)
    item.status = "unknown"; item.last_error = None; item.consecutive_errors = 0
    db.add(AuditEvent(actor=user.username, action="device.update", target_type="device", target_id=item.id, details={"name": item.name, "profile_id": item.profile_id, "unit_id": item.unit_id}))
    db.commit(); return as_dict(item)


@app.get("/api/devices/{device_id}/removal-impact")
def device_removal_impact(device_id: str, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    item = db.get(Device, device_id)
    if not item or item.status == "removed": raise HTTPException(404, "Dispositivo non trovato")
    bindings = db.scalar(select(func.count()).select_from(MeasurementBinding).where(MeasurementBinding.device_id == device_id)) or 0
    samples = db.scalar(select(func.count()).select_from(TelemetrySample).where(TelemetrySample.device_id == device_id)) or 0
    alarms = db.scalar(select(func.count()).select_from(AlarmEvent).where(AlarmEvent.device_id == device_id)) or 0
    rules = sum(1 for rule in db.scalars(select(AlarmRule)) if rule.config.get("device_id") == device_id)
    return {"id": item.id, "name": item.name, "bindings": bindings, "samples": samples, "alarm_events": alarms, "alarm_rules": rules, "history_preserved_by_default": True}


@app.delete("/api/devices/{device_id}")
def delete_device(device_id: str, data: DeviceRemovalInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    item = db.get(Device, device_id)
    if not item or item.status == "removed": raise HTTPException(404, "Dispositivo non trovato")
    bindings = db.scalar(select(func.count()).select_from(MeasurementBinding).where(MeasurementBinding.device_id == device_id)) or 0
    if bindings: db.execute(delete(MeasurementBinding).where(MeasurementBinding.device_id == device_id))
    deleted_samples = 0
    if data.purge_history:
        result = db.execute(delete(TelemetrySample).where(TelemetrySample.device_id == device_id)); deleted_samples = result.rowcount or 0
    disabled_rules = 0
    for rule in db.scalars(select(AlarmRule)):
        if rule.config.get("device_id") == device_id and rule.active:
            rule.active = False; disabled_rules += 1
    item.active = False; item.status = "removed"; item.last_error = "Rimosso dalla configurazione"
    db.add(AuditEvent(actor=user.username, action="device.remove", target_type="device", target_id=item.id, details={"name": item.name, "bindings_removed": bindings, "alarm_rules_disabled": disabled_rules, "history_purged": data.purge_history, "samples_removed": deleted_samples}))
    db.commit()
    return {"removed": device_id, "bindings_removed": bindings, "history_purged": data.purge_history, "samples_removed": deleted_samples}


@app.patch("/api/devices/{device_id}/active")
def toggle_device(device_id: str, active: bool, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    item = db.get(Device, device_id)
    if not item or item.status == "removed": raise HTTPException(404, "Device not found")
    item.active = active
    db.add(AuditEvent(actor=user.username, action="device.active", target_type="device", target_id=item.id, details={"active": active}))
    db.commit(); return as_dict(item)


@app.post("/api/devices/{device_id}/poll")
async def manual_poll(device_id: str, user: User = Depends(require_roles("platform_admin", "technician"))) -> dict:
    return {"samples": await poll_device(device_id)}


@app.get("/api/assets")
def assets(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [as_dict(item) for item in db.scalars(select(AssetNode).order_by(AssetNode.sort_order))]


@app.post("/api/assets")
def create_asset(data: AssetInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    if data.parent_id and not db.get(AssetNode, data.parent_id): raise HTTPException(422, "Parent not found")
    item = AssetNode(**data.model_dump()); db.add(item); db.flush()
    db.add(AuditEvent(actor=user.username, action="asset.create", target_type="asset", target_id=item.id, details={"name": item.name, "parent_id": item.parent_id}))
    db.commit(); return as_dict(item)


@app.put("/api/assets/{asset_id}")
def update_asset(asset_id: str, data: AssetInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    item = db.get(AssetNode, asset_id)
    if not item: raise HTTPException(404, "Asset not found")
    if data.parent_id == asset_id: raise HTTPException(422, "Asset cannot be its own parent")
    ancestor_id = data.parent_id
    while ancestor_id:
        if ancestor_id == asset_id:
            raise HTTPException(422, "Asset hierarchy cannot contain cycles")
        ancestor = db.get(AssetNode, ancestor_id)
        if not ancestor:
            raise HTTPException(422, "Parent not found")
        ancestor_id = ancestor.parent_id
    for key, value in data.model_dump().items(): setattr(item, key, value)
    db.add(AuditEvent(actor=user.username, action="asset.update", target_type="asset", target_id=item.id, details={"name": item.name, "parent_id": item.parent_id, "sort_order": item.sort_order}))
    db.commit(); return as_dict(item)


@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: str, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    item = db.get(AssetNode, asset_id)
    if not item: raise HTTPException(404, "Asset not found")
    if db.scalar(select(AssetNode.id).where(AssetNode.parent_id == asset_id).limit(1)): raise HTTPException(409, "Move or delete child assets first")
    if db.scalar(select(MeasurementBinding.id).where(MeasurementBinding.asset_id == asset_id).limit(1)): raise HTTPException(409, "Remove measurement bindings first")
    db.delete(item); db.commit(); return {"deleted": asset_id}


@app.get("/api/bindings")
def bindings(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(MeasurementBinding, AssetNode.name, Device.name).join(AssetNode, MeasurementBinding.asset_id == AssetNode.id).join(Device, MeasurementBinding.device_id == Device.id)).all()
    return [{**as_dict(binding), "asset_name": asset_name, "device_name": device_name} for binding, asset_name, device_name in rows]


@app.post("/api/bindings")
def create_binding(data: BindingInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    if not db.get(AssetNode, data.asset_id) or not db.get(Device, data.device_id): raise HTTPException(422, "Asset or device not found")
    duplicate = db.scalar(select(MeasurementBinding).where(MeasurementBinding.asset_id == data.asset_id, MeasurementBinding.device_id == data.device_id, MeasurementBinding.measurement_key == data.measurement_key))
    if duplicate: raise HTTPException(409, "Measurement already associated")
    if data.role == "primary":
        other_placement = db.scalar(select(MeasurementBinding).where(MeasurementBinding.device_id == data.device_id, MeasurementBinding.role == "primary", MeasurementBinding.asset_id != data.asset_id).limit(1))
        if other_placement:
            raise HTTPException(409, "A device can have only one primary position in the energy tree")
    item = MeasurementBinding(**data.model_dump()); db.add(item); db.commit(); return as_dict(item)


@app.delete("/api/bindings/{binding_id}")
def delete_binding(binding_id: str, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    item = db.get(MeasurementBinding, binding_id)
    if not item: raise HTTPException(404, "Binding not found")
    db.delete(item); db.commit(); return {"deleted": binding_id}


@app.get("/api/telemetry/live")
def live(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(TelemetrySample).order_by(TelemetrySample.sample_at.desc()).limit(1000)).scalars()
    found = {}
    for row in rows: found.setdefault((row.device_id, row.measurement_key), as_dict(row))
    return list(found.values())


@app.get("/api/telemetry/history")
def history(measurement_key: str | None = None, hours: int = 24, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    query = select(TelemetrySample).where(TelemetrySample.sample_at >= utcnow() - timedelta(hours=min(hours, 24 * 90))).order_by(TelemetrySample.sample_at)
    if measurement_key: query = query.where(TelemetrySample.measurement_key == measurement_key)
    return [as_dict(item) for item in db.scalars(query.limit(5000))]


@app.get("/api/analytics/timeseries")
def analytics_timeseries(
    device_id: str | None = None,
    measurement_keys: str = "electrical.active_power.total",
    hours: int = 24,
    bucket_minutes: int = 5,
    user: User = Depends(current_user), db: Session = Depends(get_db),
) -> dict:
    hours = min(max(hours, 1), 24 * 365 * 5)
    bucket_minutes = min(max(bucket_minutes, 1), 24 * 60)
    keys = [key.strip() for key in measurement_keys.split(",") if key.strip()][:24]
    if not keys: raise HTTPException(422, "At least one measurement key is required")
    since = utcnow() - timedelta(hours=hours)
    query = select(TelemetrySample).where(
        TelemetrySample.sample_at >= since,
        TelemetrySample.measurement_key.in_(keys),
        TelemetrySample.quality == "good",
        TelemetrySample.value.is_not(None),
    ).order_by(TelemetrySample.sample_at)
    if device_id: query = query.where(TelemetrySample.device_id == device_id)
    samples = list(db.scalars(query.limit(100000)))
    bucket_seconds = bucket_minutes * 60
    grouped: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    units: dict[tuple[str, str], str] = {}
    for sample in samples:
        stamp = int(sample.sample_at.timestamp()) // bucket_seconds * bucket_seconds
        grouped[(sample.device_id, sample.measurement_key, stamp)].append(float(sample.value))
        units[(sample.device_id, sample.measurement_key)] = sample.unit
    series: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (owner, key, stamp), values in sorted(grouped.items(), key=lambda item: item[0][2]):
        series[(owner, key)].append({
            "time": datetime.fromtimestamp(stamp, timezone.utc), "avg": sum(values) / len(values),
            "min": min(values), "max": max(values), "count": len(values),
        })
    devices = {device.id: device for device in db.scalars(select(Device))}
    available = []
    for device in devices.values():
        profile = db.get(DeviceProfile, device.profile_id)
        definition = profile.definition if profile else {}
        for point in definition.get("points", []) + definition.get("derived_points", []):
            available.append({"device_id": device.id, "device_name": device.name, "category": definition.get("category", "device"), "key": point["key"], "label": point.get("label", point["key"]), "unit": point.get("unit", ""), "group": point.get("group", "Misure")})
    return {
        "from": since, "to": utcnow(), "bucket_minutes": bucket_minutes,
        "series": [{"device_id": owner, "device_name": devices.get(owner).name if devices.get(owner) else owner, "key": key, "unit": units.get((owner, key), ""), "points": points} for (owner, key), points in series.items()],
        "available": available, "sample_count": len(samples),
    }


@app.get("/api/storage/status")
def storage_status(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    quality_rows = db.execute(select(TelemetrySample.quality, func.count()).group_by(TelemetrySample.quality)).all()
    return {
        "persistence": "local_database",
        "retention_policy": f"automatic_{settings.telemetry_retention_days}_days",
        "samples": db.scalar(select(func.count()).select_from(TelemetrySample)) or 0,
        "oldest_sample_at": db.scalar(select(func.min(TelemetrySample.sample_at))),
        "newest_sample_at": db.scalar(select(func.max(TelemetrySample.sample_at))),
        "quality": {quality: count for quality, count in quality_rows},
        "pending_sync_events": db.scalar(select(func.count()).select_from(SyncOutbox).where(SyncOutbox.sent_at.is_(None))) or 0,
        "analytics_max_range_days": 365 * 5,
        "capacity": storage_capacity(settings),
        "backups": list_backups(settings),
    }


@app.get("/api/commissioning")
def commissioning(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if settings.mode != "edge": raise HTTPException(404)
    return commissioning_report(db, settings)


@app.post("/api/commissioning/test-all")
async def commissioning_test_all(user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    if settings.mode != "edge": raise HTTPException(404)
    results = []
    connections = list(db.scalars(select(Connection).order_by(Connection.name)))
    for connection in connections:
        devices = list(db.scalars(select(Device).where(Device.connection_id == connection.id, Device.active.is_(True)).order_by(Device.unit_id)))
        connection_samples = 0
        for device in devices:
            connection_samples += await poll_device(device.id)
        db.refresh(connection)
        connection.last_test_at = utcnow()
        connection.status = "online" if connection_samples else "offline"
        results.append({"connection_id": connection.id, "name": connection.name, "status": connection.status, "devices": len(devices), "samples": connection_samples})
    db.add(AuditEvent(actor=user.username, action="commissioning.test_all", target_type="system", target_id=None, details={"connections": len(results), "online": sum(item["status"] == "online" for item in results)}))
    db.commit()
    return {"tested_at": utcnow(), "results": results}


@app.post("/api/maintenance/backup")
def create_edge_backup(user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    if settings.mode != "edge": raise HTTPException(404)
    try: manifest = create_backup(settings)
    except RuntimeError as exc: raise HTTPException(503, str(exc)) from exc
    db.add(AuditEvent(actor=user.username, action="backup.create", target_type="system", target_id=manifest["file"], details={"sha256": manifest["sha256"], "bytes": manifest["bytes"]}))
    db.commit()
    return manifest


@app.get("/api/maintenance/backups")
def backups(user: User = Depends(require_roles("platform_admin", "technician"))) -> list[dict]:
    return list_backups(settings)


@app.get("/api/maintenance/backups/{filename}")
def download_backup(filename: str, user: User = Depends(require_roles("platform_admin", "technician"))):
    try: path = backup_file(settings, filename)
    except (ValueError, FileNotFoundError) as exc: raise HTTPException(404, "Backup not found") from exc
    return FileResponse(path, filename=path.name, media_type="application/vnd.sqlite3")


@app.post("/api/maintenance/retention")
def execute_retention(user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    result = run_retention(settings)
    db.add(AuditEvent(actor=user.username, action="retention.run", target_type="system", target_id=None, details=result)); db.commit()
    return result


@app.get("/api/kpis")
def kpis(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    devices = list(db.scalars(select(Device).order_by(Device.unit_id)))
    deltas = []
    for device in devices[:3]:
        rows = list(db.scalars(select(TelemetrySample).where(TelemetrySample.device_id == device.id, TelemetrySample.measurement_key == "electrical.energy.import_total", TelemetrySample.quality == "good").order_by(TelemetrySample.sample_at.desc()).limit(2)))
        deltas.append(counter_delta(rows[1].value, rows[0].value).__dict__ if len(rows) == 2 else {"value": None, "quality": "missing", "reason": "need two samples"})
    unassigned = unattributed_energy(deltas[0]["value"] if deltas else None, [item["value"] for item in deltas[1:3]])
    online = sum(item.status == "online" for item in devices)
    main_id = devices[0].id if devices else ""
    return {"instant_power_kw": (db.scalar(select(TelemetrySample.value).where(TelemetrySample.device_id == main_id, TelemetrySample.measurement_key == "electrical.active_power.total").order_by(TelemetrySample.sample_at.desc()))), "energy_interval": deltas, "unattributed": unassigned, "communication_availability_percent": online / len(devices) * 100 if devices else 0, "data_quality": "good" if deltas and deltas[0]["quality"] == "good" else "missing"}


@app.get("/api/kpi-definitions")
def kpi_definitions(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [as_dict(item) for item in db.scalars(select(KpiDefinition).order_by(KpiDefinition.name))]


@app.post("/api/kpi-definitions")
def create_kpi_definition(data: KpiDefinitionInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    item = KpiDefinition(**data.model_dump()); db.add(item); db.flush()
    db.add(AuditEvent(actor=user.username, action="kpi.create", target_type="kpi_definition", target_id=item.id, details={"name": item.name, "kind": item.kind}))
    db.commit(); return as_dict(item)


@app.put("/api/kpi-definitions/{definition_id}")
def update_kpi_definition(definition_id: str, data: KpiDefinitionInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    item = db.get(KpiDefinition, definition_id)
    if not item: raise HTTPException(404, "KPI definition not found")
    item.name = data.name; item.kind = data.kind; item.config = data.config
    db.add(AuditEvent(actor=user.username, action="kpi.update", target_type="kpi_definition", target_id=item.id, details={"name": item.name, "kind": item.kind}))
    db.commit(); return as_dict(item)


@app.delete("/api/kpi-definitions/{definition_id}")
def delete_kpi_definition(definition_id: str, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    item = db.get(KpiDefinition, definition_id)
    if not item: raise HTTPException(404, "KPI definition not found")
    db.delete(item); db.add(AuditEvent(actor=user.username, action="kpi.delete", target_type="kpi_definition", target_id=definition_id, details={"name": item.name})); db.commit()
    return {"deleted": definition_id}


@app.get("/api/kpis/portfolio")
def kpi_portfolio(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = list(db.scalars(select(TelemetrySample).where(TelemetrySample.quality == "good", TelemetrySample.value.is_not(None)).order_by(TelemetrySample.sample_at.desc()).limit(10000)))
    latest: dict[tuple[str, str], float] = {}
    for row in rows: latest.setdefault((row.device_id, row.measurement_key), float(row.value))
    def values(key: str, device_id: str | None = None) -> list[float]: return [value for (owner, measurement), value in latest.items() if measurement == key and (not device_id or owner == device_id)]
    results = []
    for definition in db.scalars(select(KpiDefinition).order_by(KpiDefinition.name)):
        config = definition.config; result: float | None = None; reason = None
        if definition.kind == "latest":
            candidates = values(config.get("measurement_key", ""), config.get("device_id")); result = candidates[0] if candidates else None
        elif definition.kind == "sum":
            candidates = values(config.get("measurement_key", "")); result = sum(candidates) if candidates else None
        elif definition.kind == "ratio":
            numerator = sum(values(config.get("numerator_key", ""))); denominator = sum(values(config.get("denominator_key", "")))
            result = numerator / denominator * float(config.get("scale", 100)) if denominator else None
        if result is None: reason = "missing_source_data"
        target = config.get("target"); direction = config.get("direction", "above")
        on_target = None if result is None or target is None else (result >= float(target) if direction == "above" else result <= float(target))
        results.append({"id": definition.id, "name": definition.name, "kind": definition.kind, "value": result, "unit": config.get("unit", ""), "target": target, "direction": direction, "on_target": on_target, "reason": reason})
    return {"generated_at": utcnow(), "definitions": results}


@app.get("/api/alarms")
def alarms(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [as_dict(item) for item in db.scalars(select(AlarmEvent).order_by(AlarmEvent.opened_at.desc()))]


@app.get("/api/alarm-rules")
def alarm_rules(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    result = []
    for rule in db.scalars(select(AlarmRule).order_by(AlarmRule.active.desc(), AlarmRule.name)):
        result.append({**as_dict(rule), **rule.config})
    return result


@app.post("/api/alarm-rules")
def create_alarm_rule(data: AlarmRuleInput, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    if data.device_id and not db.get(Device, data.device_id):
        raise HTTPException(422, "Unknown device")
    if data.condition in {"above", "below"} and data.threshold is None:
        raise HTTPException(422, "A threshold is required")
    if data.condition == "outside" and (data.low is None or data.high is None or data.low >= data.high):
        raise HTTPException(422, "A valid low/high interval is required")
    unsupported_channels = set(data.notification_channels) - {"in_app"}
    if unsupported_channels:
        raise HTTPException(422, f"Notification channels not configured: {', '.join(sorted(unsupported_channels))}")
    kind = {"above": "measurement_above", "below": "measurement_below", "outside": "measurement_outside"}[data.condition]
    config = {
        "device_id": data.device_id,
        "measurement_key": data.measurement_key,
        "threshold": data.threshold,
        "low": data.low,
        "high": data.high,
        "deadband": data.deadband,
        "notification_channels": data.notification_channels,
    }
    rule = AlarmRule(name=data.name, kind=kind, config=config, severity=data.severity, active=data.active)
    db.add(rule); db.flush()
    db.add(AuditEvent(actor=user.username, action="alarm_rule.create", target_type="alarm_rule", target_id=rule.id, details={"name": rule.name, "severity": rule.severity, "config": config}))
    db.commit()
    return {**as_dict(rule), **rule.config}


@app.patch("/api/alarm-rules/{rule_id}/active")
def set_alarm_rule_active(rule_id: str, active: bool = Body(embed=True), user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    rule = db.get(AlarmRule, rule_id)
    if not rule:
        raise HTTPException(404, "Alarm rule not found")
    rule.active = active
    db.add(AuditEvent(actor=user.username, action="alarm_rule.active", target_type="alarm_rule", target_id=rule.id, details={"active": active}))
    db.commit()
    return {**as_dict(rule), **rule.config}


@app.delete("/api/alarm-rules/{rule_id}")
def delete_alarm_rule(rule_id: str, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    rule = db.get(AlarmRule, rule_id)
    if not rule:
        raise HTTPException(404, "Alarm rule not found")
    event_count = db.scalar(select(func.count()).select_from(AlarmEvent).where(AlarmEvent.rule_id == rule.id)) or 0
    if event_count:
        rule.active = False
        action = "archived"
    else:
        db.delete(rule)
        action = "deleted"
    db.add(AuditEvent(actor=user.username, action=f"alarm_rule.{action}", target_type="alarm_rule", target_id=rule_id, details={"name": rule.name}))
    db.commit()
    return {"id": rule_id, "status": action}


@app.post("/api/alarms/{event_id}/acknowledge")
def acknowledge_alarm(event_id: str, user: User = Depends(require_roles("platform_admin", "technician", "operator")), db: Session = Depends(get_db)) -> dict:
    event = db.get(AlarmEvent, event_id)
    if not event:
        raise HTTPException(404, "Alarm not found")
    if event.status == "open":
        event.status = "acknowledged"
        db.add(AuditEvent(actor=user.username, action="alarm.acknowledge", target_type="alarm_event", target_id=event.id, details={"description": event.description}))
        db.commit()
    return as_dict(event)


@app.post("/api/alarms/{event_id}/close")
def close_alarm(event_id: str, user: User = Depends(require_roles("platform_admin", "technician", "operator")), db: Session = Depends(get_db)) -> dict:
    event = db.get(AlarmEvent, event_id)
    if not event: raise HTTPException(404, "Alarm not found")
    event.status = "closed"; event.closed_at = utcnow(); db.commit(); return as_dict(event)


@app.get("/api/sync/status")
def sync_status(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    pending = db.scalar(select(func.count()).select_from(SyncOutbox).where(SyncOutbox.sent_at.is_(None))) or 0
    failed = db.scalar(select(func.count()).select_from(SyncOutbox).where(SyncOutbox.sent_at.is_(None), SyncOutbox.attempts > 0)) or 0
    last_sent = db.scalar(select(func.max(SyncOutbox.sent_at)))
    return {"pending": pending, "failed": failed, "last_sent_at": last_sent, "control_room_url": settings.control_room_url}


@app.post("/api/sync/run")
async def run_sync(user: User = Depends(require_roles("platform_admin", "technician"))) -> dict:
    return await sync_once()


@app.post("/api/ingest/batches")
def ingest_batch(payload: dict = Body(...), authorization: str = Header(default=""), db: Session = Depends(get_db)) -> dict:
    if settings.mode != "control-room": raise HTTPException(404)
    edge = db.get(Edge, payload.get("edge_id"))
    token = authorization.removeprefix("Bearer ").strip()
    if not edge or not token or not verify_password(token, edge.token_hash): raise HTTPException(401, "Invalid edge token")
    if batch_already_ingested(db, payload.get("batch_id")): return {"accepted": True, "duplicate": True, "batch_id": payload["batch_id"]}
    for item in payload.get("samples", []):
        if not item.get("sample_id"): continue
        db.add(TelemetrySample(device_id=item["device_id"], measurement_key=item["measurement_key"], value=item.get("value"), unit=item.get("unit", ""), sample_at=datetime.fromisoformat(item["sample_at"]), received_at=datetime.fromisoformat(item["received_at"]), quality=item.get("quality", "good"), origin=f"edge:{edge.id}", source_sample_id=item["sample_id"]))
    db.add(IngestedBatch(id=payload["batch_id"], edge_id=edge.id)); edge.status = "online"; edge.last_seen_at = utcnow(); db.commit()
    return {"accepted": True, "duplicate": False, "batch_id": payload["batch_id"], "count": len(payload.get("samples", []))}


@app.get("/api/fleet")
def fleet(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    if settings.mode != "control-room": raise HTTPException(404)
    query = select(Edge, Site, Tenant).join(Site, Edge.site_id == Site.id).join(Tenant, Site.tenant_id == Tenant.id)
    if user.role not in {"platform_admin", "technician"}:
        if not user.tenant_id: return []
        query = query.where(Tenant.id == user.tenant_id)
    rows = db.execute(query).all()
    return [{**as_dict(edge), "site": site.name, "tenant": tenant.name} for edge, site, tenant in rows]


@app.post("/api/edges/{edge_id}/activation")
def create_activation(edge_id: str, request: Request, expires_minutes: int = 30, user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> dict:
    sensitive_rate_limit(request)
    if not db.get(Edge, edge_id): raise HTTPException(404, "Edge not found")
    code = secrets.token_urlsafe(18)
    item = EdgeActivation(edge_id=edge_id, code_hash=hash_password(code), expires_at=utcnow() + timedelta(minutes=min(expires_minutes, 1440)))
    db.add(item); db.commit(); return {"activation_id": item.id, "code": code, "expires_at": item.expires_at}


@app.post("/api/activate")
async def activate(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    sensitive_rate_limit(request)
    candidates = list(db.scalars(select(EdgeActivation).where(EdgeActivation.used_at.is_(None), EdgeActivation.expires_at > utcnow())))
    activation = next((item for item in candidates if verify_password(payload.get("code", ""), item.code_hash)), None)
    if not activation: raise HTTPException(401, "Invalid or expired activation code")
    edge = db.get(Edge, activation.edge_id); edge.hostname = payload.get("hostname", edge.hostname); activation.used_at = utcnow()
    auth_key = await tailscale_provider.create_auth_key(["tag:em-edge"], reusable=False)
    db.commit(); return {"edge_id": edge.id, "tailscale_auth_key": auth_key, "provider": "fake", "control_room_url": str(request.base_url).rstrip("/")}


@app.get("/api/tailscale/diagnostics")
def tailscale_diagnostics(user: User = Depends(current_user)) -> dict:
    return NetworkAgent(dry_run=True).diagnostics()


@app.get("/api/tailscale/nodes")
async def tailscale_nodes(user: User = Depends(current_user)) -> list[dict]:
    return [node_dict(node) for node in await tailscale_provider.list_nodes()]


@app.post("/api/tailscale/webhook")
async def tailscale_webhook(request: Request, x_webhook_signature: str = Header(default=""), db: Session = Depends(get_db)) -> dict:
    body = await request.body()
    if not webhook_signature_valid(body, x_webhook_signature, settings.webhook_secret): raise HTTPException(401, "Invalid webhook signature")
    payload = json.loads(body)
    allowed = {"nodeCreated", "nodeDeleted", "nodeApproved", "nodeNeedsApproval", "nodeKeyExpired", "policyUpdate"}
    if payload.get("type") not in allowed: raise HTTPException(422, "Unsupported event")
    db.add(AuditEvent(actor="tailscale-webhook", action=payload["type"], target_type="tailscale_node", target_id=payload.get("nodeId"), details=payload)); db.commit()
    return {"accepted": True}


@app.get("/api/audit")
def audit(user: User = Depends(require_roles("platform_admin", "technician")), db: Session = Depends(get_db)) -> list[dict]:
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(500)
    if user.role != "platform_admin" and user.tenant_id:
        query = query.where(AuditEvent.tenant_id == user.tenant_id)
    return [as_dict(item) for item in db.scalars(query)]


@app.get("/api/users")
def users(user: User = Depends(require_roles("platform_admin", "customer_admin")), db: Session = Depends(get_db)) -> list[dict]:
    query = select(User).order_by(User.username)
    if user.role == "customer_admin": query = query.where(User.tenant_id == user.tenant_id)
    return [{"id": item.id, "username": item.username, "role": item.role, "active": item.active, "created_at": item.created_at, "updated_at": item.updated_at, "is_current": item.id == user.id} for item in db.scalars(query)]


@app.post("/api/users")
def create_user(data: UserCreateInput, user: User = Depends(require_roles("platform_admin", "customer_admin")), db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(User).where(User.username == data.username)): raise HTTPException(409, "Username already exists")
    if user.role == "customer_admin" and data.role in {"platform_admin", "technician"}: raise HTTPException(403, "Role cannot be assigned")
    item = User(username=data.username, password_hash=hash_password(data.password), role=data.role, active=data.active, tenant_id=user.tenant_id)
    db.add(item); db.flush()
    db.add(AuditEvent(actor=user.username, action="user.create", target_type="user", target_id=item.id, details={"username": item.username, "role": item.role}))
    db.commit(); return {"id": item.id, "username": item.username, "role": item.role, "active": item.active}


@app.put("/api/users/{user_id}")
def update_user(user_id: str, data: UserUpdateInput, user: User = Depends(require_roles("platform_admin", "customer_admin")), db: Session = Depends(get_db)) -> dict:
    item = db.get(User, user_id)
    if not item: raise HTTPException(404, "User not found")
    if user.role == "customer_admin" and (item.tenant_id != user.tenant_id or data.role in {"platform_admin", "technician"}): raise HTTPException(403, "User outside tenant scope")
    if item.id == user.id and not data.active: raise HTTPException(409, "You cannot deactivate your current account")
    if item.id == user.id and data.role != item.role: raise HTTPException(409, "You cannot change your current role")
    item.role = data.role; item.active = data.active
    if data.password: item.password_hash = hash_password(data.password)
    db.add(AuditEvent(actor=user.username, action="user.update", target_type="user", target_id=item.id, details={"username": item.username, "role": item.role, "active": item.active, "password_changed": bool(data.password)}))
    db.commit(); return {"id": item.id, "username": item.username, "role": item.role, "active": item.active}
