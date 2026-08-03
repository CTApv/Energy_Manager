from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import SyncOutbox


async def sync_once() -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        rows = list(db.scalars(select(SyncOutbox).where(SyncOutbox.sent_at.is_(None)).where((SyncOutbox.next_attempt_at.is_(None)) | (SyncOutbox.next_attempt_at <= now)).order_by(SyncOutbox.created_at).limit(200)))
        payloads = [{"event_id": row.id, **row.payload} for row in rows]
    if not rows:
        return {"sent": 0, "pending": 0}
    batch_id = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{settings.control_room_url}/api/ingest/batches", json={"batch_id": batch_id, "edge_id": "00000000-0000-4000-8000-000000000001", "samples": payloads}, headers={"Authorization": f"Bearer {settings.edge_token}"})
            response.raise_for_status()
        with SessionLocal() as db:
            for row_id in [row.id for row in rows]:
                current = db.get(SyncOutbox, row_id)
                if current: current.sent_at = now
            db.commit()
        return {"sent": len(rows), "batch_id": batch_id}
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
