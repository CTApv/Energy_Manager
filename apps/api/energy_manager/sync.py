from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import platform
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select

from .config import get_settings
from .db import SessionLocal
from .contracts import EdgeStatusSnapshot, IngestBatchEnvelope, RemoteDeviceSnapshot, SyncEvent
from .maintenance import storage_capacity
from .models import Device, DeviceProfile, SyncOutbox


SYNC_QUALITIES = {"good", "stale", "invalid", "communication_error", "estimated", "missing"}


async def sync_once() -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        rows = list(db.scalars(select(SyncOutbox).where(SyncOutbox.sent_at.is_(None)).where((SyncOutbox.next_attempt_at.is_(None)) | (SyncOutbox.next_attempt_at <= now)).order_by(SyncOutbox.created_at).limit(200)))
        pending = db.scalar(select(func.count()).select_from(SyncOutbox).where(SyncOutbox.sent_at.is_(None))) or 0
        devices = list(db.scalars(select(Device).where(Device.status != "removed")))
        profiles = {profile.id: profile for profile in db.scalars(select(DeviceProfile))}
    if not rows:
        return {"sent": 0, "pending": 0}
    valid_rows: list[SyncOutbox] = []
    events: list[SyncEvent] = []
    rejected: list[tuple[str, str]] = []
    for row in rows:
        raw = {"event_id": row.id, **row.payload}
        if raw.get("quality") not in SYNC_QUALITIES:
            raw["quality"] = "invalid"
            raw["error"] = raw.get("error") or "Legacy or unsupported quality value"
        try:
            events.append(SyncEvent.model_validate(raw))
            valid_rows.append(row)
        except Exception as exc:
            rejected.append((row.id, str(exc)[:500]))
    if rejected:
        with SessionLocal() as db:
            for row_id, error in rejected:
                current = db.get(SyncOutbox, row_id)
                if current:
                    current.attempts += 1
                    current.last_error = f"Invalid outbox event: {error}"
                    current.next_attempt_at = now + timedelta(hours=24)
            db.commit()
    rows = valid_rows
    if not rows:
        return {"sent": 0, "pending": pending, "rejected": len(rejected)}
    batch_id = hashlib.sha256("|".join(row.id for row in rows).encode()).hexdigest()
    capacity = storage_capacity(settings)
    snapshots = []
    for device in devices:
        profile_definition = profiles.get(device.profile_id).definition if profiles.get(device.profile_id) else {}
        snapshots.append(RemoteDeviceSnapshot(
            id=device.id, name=device.name, category=profile_definition.get("category", "device"),
            manufacturer=profile_definition.get("manufacturer", ""), model=profile_definition.get("model", ""),
            profile_id=device.profile_id, profile_version=profiles.get(device.profile_id).version if profiles.get(device.profile_id) else "",
            status=device.status,
        ))
    configuration_version = hashlib.sha256(
        json.dumps(
            [snapshot.model_dump(mode="json") for snapshot in sorted(snapshots, key=lambda item: item.id)],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()[:16]
    envelope = IngestBatchEnvelope(
        batch_id=batch_id,
        edge_id=settings.edge_id,
        created_at=now,
        status=EdgeStatusSnapshot(
            hostname=platform.node(), app_version=settings.release, configuration_version=configuration_version, backlog_count=pending,
            disk_free_percent=capacity["free_percent"], devices=snapshots,
        ),
        events=events,
    )
    body = json.dumps(envelope.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.control_room_url}/api/ingest/batches", content=body,
                headers={"Authorization": f"Bearer {settings.edge_token}", "Content-Type": "application/json", "X-Edge-Signature": signature},
            )
            response.raise_for_status()
        with SessionLocal() as db:
            for row_id in [row.id for row in rows]:
                current = db.get(SyncOutbox, row_id)
                if current: current.sent_at = now
            db.commit()
        return {"sent": len(rows), "batch_id": batch_id, "rejected": len(rejected)}
    except Exception as exc:
        with SessionLocal() as db:
            for row_id in [row.id for row in rows]:
                current = db.get(SyncOutbox, row_id)
                if current:
                    current.attempts += 1
                    current.last_error = str(exc)[:500]
                    current.next_attempt_at = now + timedelta(seconds=min(300, 2 ** min(current.attempts, 8)))
            db.commit()
        return {"sent": 0, "error": str(exc), "pending": len(rows)}


async def sync_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await sync_once()
        try:
            await asyncio.wait_for(stop.wait(), timeout=10)
        except TimeoutError:
            pass
