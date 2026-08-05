from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .catalog import expand_catalog_document, validate_profile
from .config import Settings
from .models import (
    AlarmEvent, AlarmRule, AssetNode, CatalogProfile, CatalogProfileVersion, Connection,
    Device, DeviceProfile, Edge, EnergySettings, KpiDefinition, LocalSite, MeasurementBinding, MeasurementDefinition,
    RegisterDefinition, Role, Site, Tenant, User,
)


SEMANTIC_KEYS = [
    ("electrical.voltage.l1n", "Tensione L1-N", "V"), ("electrical.voltage.l2n", "Tensione L2-N", "V"),
    ("electrical.voltage.l3n", "Tensione L3-N", "V"), ("electrical.current.l1", "Corrente L1", "A"),
    ("electrical.current.l2", "Corrente L2", "A"), ("electrical.current.l3", "Corrente L3", "A"),
    ("electrical.active_power.total", "Potenza attiva totale", "kW"), ("electrical.reactive_power.total", "Potenza reattiva totale", "kvar"),
    ("electrical.apparent_power.total", "Potenza apparente totale", "kVA"), ("electrical.power_factor.total", "Fattore di potenza", ""),
    ("electrical.frequency", "Frequenza", "Hz"), ("electrical.energy.import_total", "Energia importata", "kWh"),
    ("electrical.energy.export_total", "Energia esportata", "kWh"), ("machine.state", "Stato macchina", ""),
    ("machine.production.total", "Produzione totale", "pcs"), ("machine.temperature", "Temperatura", "°C"),
    ("machine.pressure", "Pressione", "bar"), ("machine.flow", "Portata", "m³/h"),
]


def _profiles_directory() -> Path:
    container = Path("/packages/modbus-catalog/profiles")
    if container.exists(): return container
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "packages" / "modbus-catalog" / "profiles"
        if candidate.exists(): return candidate
    return container


def seed_catalog(db: Session, edge_mode: bool) -> dict[str, dict]:
    definitions: dict[str, dict] = {}
    for path in sorted(_profiles_directory().rglob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for document in expand_catalog_document(raw):
            profile, errors = validate_profile(document)
            if errors: raise ValueError(f"Invalid bundled catalog {path.name}: {'; '.join(errors)}")
            definition = profile.model_dump(); definitions[profile.id] = definition
            catalog = db.get(CatalogProfile, profile.id)
            if not catalog:
                db.add(CatalogProfile(id=profile.id, manufacturer=profile.manufacturer, model=profile.model, category=profile.category, latest_version=profile.version))
            else:
                catalog.manufacturer = profile.manufacturer; catalog.model = profile.model; catalog.category = profile.category; catalog.latest_version = profile.version
            version = db.scalar(select(CatalogProfileVersion).where(CatalogProfileVersion.profile_id == profile.id, CatalogProfileVersion.version == profile.version))
            if not version: db.add(CatalogProfileVersion(profile_id=profile.id, version=profile.version, definition=definition, valid=True))
            else: version.definition = definition; version.valid = True
            if edge_mode:
                local = db.get(DeviceProfile, profile.id)
                if not local: db.add(DeviceProfile(id=profile.id, version=profile.version, definition=definition, valid=True))
                else: local.version = profile.version; local.definition = definition; local.valid = True
                rows = {row.key: row for row in db.scalars(select(RegisterDefinition).where(RegisterDefinition.profile_id == profile.id))}
                for point in definition["points"]:
                    if point["key"] in rows: rows[point["key"]].definition = point
                    else: db.add(RegisterDefinition(profile_id=profile.id, key=point["key"], definition=point))
    db.flush()
    return definitions


def seed_database(db: Session, settings: Settings) -> None:
    if not db.scalar(select(User).limit(1)):
        db.add_all([Role(name=name) for name in ["platform_admin", "technician", "customer_admin", "operator", "viewer"]])
        db.add(User(username="admin", password_hash=hash_password(settings.demo_admin_password), role="platform_admin"))
    if settings.seed_demo and settings.mode == "control-room" and not db.scalar(select(Tenant).limit(1)):
        tenant = Tenant(name="CTA Demo", slug="cta-demo")
        db.add(tenant); db.flush()
        site = Site(tenant_id=tenant.id, name="Stabilimento Demo")
        db.add(site); db.flush()
        db.add(Edge(id="00000000-0000-4000-8000-000000000001", site_id=site.id, name="EM-DEMO-001", hostname="em-demo-001", status="offline", token_hash=hash_password(settings.edge_token)))
    definitions = seed_catalog(db, settings.mode == "edge")
    if settings.mode == "edge" and not db.scalar(select(EnergySettings).limit(1)):
        db.add(EnergySettings(
            import_price_per_kwh=0.24 if settings.seed_demo else 0.0,
            export_price_per_kwh=0.08 if settings.seed_demo else 0.0,
            co2_kg_per_kwh=0.28 if settings.seed_demo else 0.0,
            contracted_power_kw=80.0 if settings.seed_demo else None,
            monthly_energy_budget_kwh=15000.0 if settings.seed_demo else None,
            monthly_cost_budget=4000.0 if settings.seed_demo else None,
        ))
    if settings.mode == "edge" and not db.scalar(select(MeasurementDefinition).limit(1)):
        for key, label, unit in SEMANTIC_KEYS:
            db.add(MeasurementDefinition(key=key, label=label, unit=unit))
    if settings.seed_demo and settings.mode == "edge" and not db.scalar(select(LocalSite).limit(1)):
        db.add(LocalSite(name="Stabilimento Demo"))
        if "generic-meter-v1" in definitions:
            definition = definitions["generic-meter-v1"]
            profile = db.get(DeviceProfile, definition["id"])
            connection = Connection(name="Simulatore Modbus TCP", kind="modbus_tcp", config={"host": settings.simulator_host, "port": 5020, "timeout": 2, "retry": 2})
            db.add(connection); db.flush()
            devices = []
            for unit_id, name in [(1, "Contatore generale"), (2, "Contatore Linea 1"), (3, "Contatore Linea 2"), (4, "Macchina industriale")]:
                device = Device(connection_id=connection.id, profile_id=profile.id, name=name, unit_id=unit_id)
                db.add(device); db.flush(); devices.append(device)
            root = AssetNode(name="Stabilimento", category="site", sort_order=0)
            db.add(root); db.flush()
            main = AssetNode(parent_id=root.id, name="Contatore generale", category="meter", sort_order=0)
            db.add(main); db.flush()
            production = AssetNode(parent_id=main.id, name="Produzione", category="branch", sort_order=0)
            services = AssetNode(parent_id=main.id, name="Servizi non monitorati", category="branch", sort_order=1)
            db.add_all([production, services]); db.flush()
            line1 = AssetNode(parent_id=production.id, name="Linea 1", category="line", sort_order=0)
            line2 = AssetNode(parent_id=production.id, name="Linea 2", category="line", sort_order=1)
            db.add_all([line1, line2]); db.flush()
            for asset, device in [(main, devices[0]), (line1, devices[1]), (line2, devices[2])]:
                db.add(MeasurementBinding(asset_id=asset.id, device_id=device.id, measurement_key="electrical.energy.import_total"))
            rule = AlarmRule(name="Potenza generale elevata", kind="measurement_above", config={"measurement_key": "electrical.active_power.total", "threshold": 95}, severity="warning")
            db.add(rule); db.flush()
            db.add(AlarmEvent(rule_id=rule.id, severity="warning", status="open", device_id=devices[0].id, measurement_key="electrical.active_power.total", value=102.4, threshold=95, description="Potenza generale oltre la soglia demo"))
    if settings.seed_demo and settings.mode == "edge" and not db.scalar(select(KpiDefinition).limit(1)):
        db.add_all([
            KpiDefinition(name="Potenza generale entro obiettivo", kind="latest", config={"measurement_key": "electrical.active_power.total", "unit": "kW", "target": 100, "direction": "below"}),
            KpiDefinition(name="Quota produzione FV sulla domanda", kind="ratio", config={"numerator_key": "pv.power.ac_total", "denominator_key": "electrical.active_power.total", "scale": 100, "unit": "%", "target": 30, "direction": "above"}),
        ])
    db.commit()
