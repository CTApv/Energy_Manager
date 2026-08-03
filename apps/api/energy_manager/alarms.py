from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AlarmEvent, AlarmRule, Device, TelemetrySample


def _is_active(kind: str, value: float, config: dict[str, Any]) -> bool:
    if kind == "measurement_above":
        return value > float(config["threshold"])
    if kind == "measurement_below":
        return value < float(config["threshold"])
    if kind == "measurement_outside":
        return value < float(config["low"]) or value > float(config["high"])
    return False


def _is_clear(kind: str, value: float, config: dict[str, Any]) -> bool:
    deadband = max(0.0, float(config.get("deadband", 0)))
    if kind == "measurement_above":
        return value <= float(config["threshold"]) - deadband
    if kind == "measurement_below":
        return value >= float(config["threshold"]) + deadband
    if kind == "measurement_outside":
        return float(config["low"]) + deadband <= value <= float(config["high"]) - deadband
    return True


def evaluate_alarm_rules(db: Session, device: Device, samples: list[TelemetrySample], now: datetime) -> None:
    """Evaluate normalized measurements with hysteresis and a single active event per rule/device."""
    values = {sample.measurement_key: sample for sample in samples if sample.value is not None}
    rules = list(db.scalars(select(AlarmRule).where(AlarmRule.active.is_(True))))
    for rule in rules:
        measurement_key = rule.config.get("measurement_key")
        sample = values.get(measurement_key)
        if not sample:
            continue
        restricted_device = rule.config.get("device_id")
        if restricted_device and restricted_device != device.id:
            continue
        event = db.scalar(
            select(AlarmEvent).where(
                AlarmEvent.rule_id == rule.id,
                AlarmEvent.device_id == device.id,
                AlarmEvent.status.in_(["open", "acknowledged"]),
            ).limit(1)
        )
        value = float(sample.value)
        if _is_active(rule.kind, value, rule.config) and not event:
            operator = {"measurement_above": ">", "measurement_below": "<", "measurement_outside": "fuori intervallo"}.get(rule.kind, "")
            threshold = rule.config.get("threshold")
            threshold_text = threshold if threshold is not None else f"{rule.config.get('low')}–{rule.config.get('high')}"
            db.add(AlarmEvent(
                rule_id=rule.id,
                severity=rule.severity,
                status="open",
                opened_at=now,
                device_id=device.id,
                measurement_key=measurement_key,
                value=value,
                threshold=float(threshold) if threshold is not None else None,
                description=f"{rule.name}: {value:g} {sample.unit} {operator} {threshold_text}",
            ))
        elif event and _is_clear(rule.kind, value, rule.config):
            event.status = "closed"
            event.closed_at = now


def evaluate_device_health(db: Session, device: Device, now: datetime, error: str | None, bad_keys: list[str]) -> None:
    """Open system alarms after repeated failures and close them automatically on recovery."""
    states = [
        ("system.communication.available", bool(error), "Comunicazione Modbus interrotta", error or ""),
        ("system.data_quality.valid", bool(bad_keys), "Qualità dati degradata", ", ".join(bad_keys[:8])),
    ]
    for key, active, title, detail in states:
        event = db.scalar(select(AlarmEvent).where(
            AlarmEvent.rule_id.is_(None),
            AlarmEvent.device_id == device.id,
            AlarmEvent.measurement_key == key,
            AlarmEvent.status.in_(["open", "acknowledged"]),
        ).limit(1))
        repeated = device.consecutive_errors >= 3
        if active and repeated and not event:
            db.add(AlarmEvent(
                rule_id=None,
                severity="high" if error else "warning",
                status="open",
                opened_at=now,
                device_id=device.id,
                measurement_key=key,
                value=0,
                threshold=1,
                description=f"{title} su {device.name}: {detail}"[:1000],
            ))
        elif not active and event:
            event.status = "closed"
            event.closed_at = now
