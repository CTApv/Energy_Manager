from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from .kpi import counter_delta
from .models import AssetNode, Device, DeviceProfile, EnergySettings, MeasurementBinding, TelemetrySample
from .tariffs import price_increments


IMPORT_KEY = "electrical.energy.import_total"
EXPORT_KEY = "electrical.energy.export_total"
POWER_KEY = "electrical.active_power.total"
PV_ENERGY_KEY = "pv.energy.total"


def safe_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


def period_bounds(period: str, zone_name: str, now: datetime | None = None) -> tuple[datetime, datetime, datetime, datetime]:
    zone = safe_zone(zone_name)
    local_now = (now or datetime.now(timezone.utc)).astimezone(zone)
    if period == "day":
        start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
    elif period == "week":
        start_local = (local_now - timedelta(days=local_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=7)
    elif period == "month":
        start_local = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start_local.month == 12:
            end_local = start_local.replace(year=start_local.year + 1, month=1)
        else:
            end_local = start_local.replace(month=start_local.month + 1)
    elif period == "year":
        start_local = local_now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local.replace(year=start_local.year + 1)
    else:
        raise ValueError("Period must be day, week, month or year")
    effective_end = min(local_now, end_local)
    if period == "month":
        previous_start = (start_local.replace(day=1) - timedelta(days=1)).replace(day=1)
    elif period == "year":
        previous_start = start_local.replace(year=start_local.year - 1)
    else:
        previous_start = start_local - (end_local - start_local)
    previous_period_end = start_local
    elapsed = effective_end.astimezone(timezone.utc) - start_local.astimezone(timezone.utc)
    previous_end = min(previous_start.astimezone(timezone.utc) + elapsed, previous_period_end.astimezone(timezone.utc))
    return (
        start_local.astimezone(timezone.utc),
        effective_end.astimezone(timezone.utc),
        previous_start.astimezone(timezone.utc),
        previous_end,
    )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def counter_samples(db: Session, device_id: str, key: str, start: datetime, end: datetime) -> list[TelemetrySample]:
    previous = db.scalar(select(TelemetrySample).where(
        TelemetrySample.device_id == device_id,
        TelemetrySample.measurement_key == key,
        TelemetrySample.quality == "good",
        TelemetrySample.value.is_not(None),
        TelemetrySample.sample_at < start,
    ).order_by(TelemetrySample.sample_at.desc()).limit(1))
    rows = list(db.scalars(select(TelemetrySample).where(
        TelemetrySample.device_id == device_id,
        TelemetrySample.measurement_key == key,
        TelemetrySample.quality == "good",
        TelemetrySample.value.is_not(None),
        TelemetrySample.sample_at >= start,
        TelemetrySample.sample_at <= end,
    ).order_by(TelemetrySample.sample_at)))
    return ([previous] if previous else []) + rows


def counter_usage(samples: list[TelemetrySample], start: datetime, end: datetime) -> dict[str, Any]:
    if len(samples) < 2:
        return {"value": None, "quality": "missing", "samples": len(samples), "resets": 0, "increments": []}
    total = 0.0
    resets = 0
    increments = []
    for previous, current in zip(samples, samples[1:]):
        stamp = _aware(current.sample_at)
        if stamp < start or stamp > end:
            continue
        delta = counter_delta(previous.value, current.value)
        if delta.value is None:
            continue
        total += float(delta.value)
        resets += delta.quality == "estimated"
        increments.append((stamp, float(delta.value)))
    quality = "estimated" if resets else "good"
    return {"value": total if increments else None, "quality": quality if increments else "missing", "samples": len(samples), "resets": resets, "increments": increments}


def _counter(db: Session, device_id: str | None, key: str, start: datetime, end: datetime) -> dict[str, Any]:
    if not device_id:
        return {"value": None, "quality": "missing", "samples": 0, "resets": 0, "increments": []}
    return counter_usage(counter_samples(db, device_id, key, start, end), start, end)


def _profile_category(db: Session, device: Device) -> str:
    profile = db.get(DeviceProfile, device.profile_id)
    return profile.definition.get("category", "device") if profile else "device"


def _primary_source(db: Session) -> tuple[Device | None, AssetNode | None]:
    rows = db.execute(select(MeasurementBinding, AssetNode, Device)
        .join(AssetNode, MeasurementBinding.asset_id == AssetNode.id)
        .join(Device, MeasurementBinding.device_id == Device.id)
        .where(MeasurementBinding.role == "primary", MeasurementBinding.measurement_key == IMPORT_KEY, Device.active.is_(True))
        .order_by(MeasurementBinding.created_at)).all()
    preferred = next(((device, asset) for _, asset, device in rows if asset.category == "meter"), None)
    return preferred or ((rows[0][2], rows[0][1]) if rows else (None, None))


def _power_stats(db: Session, device_id: str | None, start: datetime, end: datetime) -> dict[str, Any]:
    if not device_id:
        return {"average_kw": None, "peak_kw": None, "minimum_kw": None, "samples": 0, "coverage_percent": 0.0}
    rows = list(db.scalars(select(TelemetrySample).where(
        TelemetrySample.device_id == device_id,
        TelemetrySample.measurement_key == POWER_KEY,
        TelemetrySample.quality == "good",
        TelemetrySample.value.is_not(None),
        TelemetrySample.sample_at >= start,
        TelemetrySample.sample_at <= end,
    ).order_by(TelemetrySample.sample_at)))
    values = [float(row.value) for row in rows]
    covered = 0.0
    for previous, current in zip(rows, rows[1:]):
        covered += min((_aware(current.sample_at) - _aware(previous.sample_at)).total_seconds(), 30)
    duration = max((end - start).total_seconds(), 1)
    return {
        "average_kw": sum(values) / len(values) if values else None,
        "peak_kw": max(values) if values else None,
        "minimum_kw": min(values) if values else None,
        "samples": len(values),
        "coverage_percent": round(min(100, covered / duration * 100), 1),
    }


def _bucket_label(stamp: datetime, start: datetime, end: datetime, zone: ZoneInfo) -> str:
    local = stamp.astimezone(zone)
    days = (end - start).total_seconds() / 86400
    if days <= 2:
        return local.replace(minute=0, second=0, microsecond=0).isoformat()
    if days <= 100:
        return local.date().isoformat()
    return f"{local.year:04d}-{local.month:02d}"


def _timeline(increments: list[tuple[datetime, float]], start: datetime, end: datetime, zone: ZoneInfo) -> list[dict[str, Any]]:
    buckets: dict[str, float] = defaultdict(float)
    for stamp, value in increments:
        buckets[_bucket_label(stamp, start, end, zone)] += value
    return [{"time": label, "energy_kwh": round(value, 4)} for label, value in sorted(buckets.items())]


def _change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in {None, 0}:
        return None
    return (current - previous) / abs(previous) * 100


def build_energy_report(db: Session, configuration: EnergySettings, period: str, now: datetime | None = None) -> dict[str, Any]:
    start, end, previous_start, previous_end = period_bounds(period, configuration.timezone, now)
    zone = safe_zone(configuration.timezone)
    meter, primary_asset = _primary_source(db)
    meter_id = meter.id if meter else None
    imported = _counter(db, meter_id, IMPORT_KEY, start, end)
    exported = _counter(db, meter_id, EXPORT_KEY, start, end)
    previous_imported = _counter(db, meter_id, IMPORT_KEY, previous_start, previous_end)
    power = _power_stats(db, meter_id, start, end)

    pv_devices = [device for device in db.scalars(select(Device).where(Device.active.is_(True))) if _profile_category(db, device) == "pv_inverter"]
    pv_results = [_counter(db, device.id, PV_ENERGY_KEY, start, end) for device in pv_devices]
    produced = sum(item["value"] for item in pv_results if item["value"] is not None) if any(item["value"] is not None for item in pv_results) else None
    import_value = imported["value"]
    export_value = exported["value"] or 0.0
    self_consumed = max(0.0, produced - export_value) if produced is not None else None
    total_consumption = (import_value or 0.0) + (self_consumed or 0.0) if import_value is not None or self_consumed is not None else None
    self_consumption_percent = self_consumed / produced * 100 if produced not in {None, 0} and self_consumed is not None else None
    self_sufficiency_percent = self_consumed / total_consumption * 100 if total_consumption not in {None, 0} and self_consumed is not None else None
    priced_import = price_increments(db, imported["increments"], zone, configuration.import_price_per_kwh, "import")
    priced_export = price_increments(db, exported["increments"], zone, configuration.export_price_per_kwh, "export")
    energy_cost = priced_import["total"] if import_value is not None else None
    export_revenue = priced_export["total"] if exported["value"] is not None else 0.0
    net_cost = energy_cost - export_revenue if energy_cost is not None else None
    emissions = import_value * configuration.co2_kg_per_kwh if import_value is not None else None

    off_hours = 0.0
    start_hour, start_minute = map(int, configuration.workday_start.split(":"))
    end_hour, end_minute = map(int, configuration.workday_end.split(":"))
    for stamp, value in imported["increments"]:
        local = stamp.astimezone(zone)
        minutes = local.hour * 60 + local.minute
        if local.weekday() not in configuration.working_days or not (start_hour * 60 + start_minute <= minutes < end_hour * 60 + end_minute):
            off_hours += value

    breakdown = []
    bindings = db.execute(select(MeasurementBinding, AssetNode, Device)
        .join(AssetNode, MeasurementBinding.asset_id == AssetNode.id)
        .join(Device, MeasurementBinding.device_id == Device.id)
        .where(MeasurementBinding.measurement_key == IMPORT_KEY, Device.active.is_(True))
        .order_by(AssetNode.sort_order, AssetNode.name)).all()
    assets_by_id = {asset.id: asset for asset in db.scalars(select(AssetNode))}
    metered_assets = {asset.id for _, asset, device in bindings if device.id != meter_id}
    seen: set[tuple[str, str]] = set()
    for binding, asset, device in bindings:
        identity = (asset.id, device.id)
        if identity in seen or device.id == meter_id:
            continue
        ancestor_id = asset.parent_id
        shadowed = False
        visited: set[str] = set()
        while ancestor_id and ancestor_id not in visited and ancestor_id != (primary_asset.id if primary_asset else None):
            visited.add(ancestor_id)
            if ancestor_id in metered_assets:
                shadowed = True
                break
            ancestor_id = assets_by_id.get(ancestor_id).parent_id if assets_by_id.get(ancestor_id) else None
        if shadowed:
            continue
        seen.add(identity)
        usage = _counter(db, device.id, IMPORT_KEY, start, end)
        if usage["value"] is not None:
            breakdown.append({"asset_id": asset.id, "asset_name": asset.name, "device_id": device.id, "device_name": device.name, "energy_kwh": usage["value"], "quality": usage["quality"]})
    breakdown.sort(key=lambda item: item["energy_kwh"], reverse=True)
    attributed = sum(item["energy_kwh"] for item in breakdown)
    unattributed = import_value - attributed if import_value is not None else None

    projected_energy = projected_cost = None
    if period == "month" and import_value is not None:
        local_end = end.astimezone(zone)
        elapsed_days = max(local_end.day - 1 + (local_end.hour * 60 + local_end.minute) / 1440, 1 / 24)
        days_in_month = calendar.monthrange(local_end.year, local_end.month)[1]
        projected_energy = import_value / elapsed_days * days_in_month
        projected_cost = projected_energy * configuration.import_price_per_kwh

    return {
        "period": {"kind": period, "from": start, "to": end, "previous_from": previous_start, "previous_to": previous_end, "timezone": configuration.timezone},
        "source": {"device_id": meter_id, "device_name": meter.name if meter else None, "measurement_key": IMPORT_KEY},
        "energy": {
            "import_kwh": import_value, "export_kwh": exported["value"], "production_kwh": produced,
            "self_consumed_kwh": self_consumed, "total_consumption_kwh": total_consumption,
            "off_hours_kwh": off_hours if import_value is not None else None,
            "unattributed_kwh": unattributed,
            "self_consumption_percent": self_consumption_percent, "self_sufficiency_percent": self_sufficiency_percent,
            "quality": imported["quality"], "counter_resets": imported["resets"],
        },
        "power": {**power, "contracted_kw": configuration.contracted_power_kw, "contract_exceeded": power["peak_kw"] > configuration.contracted_power_kw if power["peak_kw"] is not None and configuration.contracted_power_kw is not None else None},
        "economics": {"currency": configuration.currency, "energy_cost": energy_cost, "export_revenue": export_revenue, "net_cost": net_cost, "projected_month_cost": projected_cost, "monthly_cost_budget": configuration.monthly_cost_budget, "import_tariffs": priced_import["breakdown"], "export_tariffs": priced_export["breakdown"]},
        "environment": {"co2_kg": emissions, "factor_kg_per_kwh": configuration.co2_kg_per_kwh},
        "comparison": {"previous_import_kwh": previous_imported["value"], "energy_change_percent": _change(import_value, previous_imported["value"])},
        "budget": {"monthly_energy_budget_kwh": configuration.monthly_energy_budget_kwh, "projected_month_energy_kwh": projected_energy, "projected_energy_percent": projected_energy / configuration.monthly_energy_budget_kwh * 100 if projected_energy is not None and configuration.monthly_energy_budget_kwh else None},
        "timeline": _timeline(imported["increments"], start, end, zone),
        "breakdown": breakdown[:20],
        "generated_at": datetime.now(timezone.utc),
    }
