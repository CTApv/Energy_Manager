import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from energy_manager.db import Base
from energy_manager.main import batch_already_ingested
from energy_manager.models import IngestedBatch, SyncOutbox
from energy_manager import sync


def memory_sessions():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_batch_idempotency_marker():
    sessions = memory_sessions()
    with sessions() as db:
        db.add(IngestedBatch(id="batch-1", edge_id="edge-1")); db.commit()
        assert batch_already_ingested(db, "batch-1")
        assert not batch_already_ingested(db, "batch-2")


def test_control_room_absence_keeps_outbox(monkeypatch):
    sessions = memory_sessions()
    with sessions() as db:
        now = datetime.now(timezone.utc).isoformat()
        row = SyncOutbox(event_type="telemetry", payload={"sample_id": "11111111-1111-4111-8111-111111111111", "device_id": "22222222-2222-4222-8222-222222222222", "measurement_key": "electrical.active_power.total", "value": 10.0, "unit": "kW", "sample_at": now, "received_at": now, "quality": "good", "origin": "modbus"})
        db.add(row); db.commit(); row_id = row.id

    class BrokenClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): raise ConnectionError("control room unavailable")
        async def __aexit__(self, *args): return False

    monkeypatch.setattr(sync, "SessionLocal", sessions)
    monkeypatch.setattr(sync.httpx, "AsyncClient", BrokenClient)
    result = asyncio.run(sync.sync_once())
    with sessions() as db:
        row = db.get(SyncOutbox, row_id)
        assert result["sent"] == 0
        assert row.sent_at is None and row.attempts == 1 and row.last_error


def test_legacy_quality_is_normalized_without_blocking_outbox(monkeypatch):
    sessions = memory_sessions()
    with sessions() as db:
        now = datetime.now(timezone.utc).isoformat()
        row = SyncOutbox(event_type="telemetry", payload={"sample_id": "11111111-1111-4111-8111-111111111111", "device_id": "22222222-2222-4222-8222-222222222222", "measurement_key": "electrical.active_power.total", "value": 10.0, "unit": "kW", "sample_at": now, "received_at": now, "quality": "bad", "origin": "legacy"})
        db.add(row); db.commit(); row_id = row.id

    captured = {}
    class Response:
        def raise_for_status(self): return None
    class Client:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, content, headers):
            captured.update(json.loads(content)); return Response()

    monkeypatch.setattr(sync, "SessionLocal", sessions)
    monkeypatch.setattr(sync.httpx, "AsyncClient", Client)
    result = asyncio.run(sync.sync_once())
    with sessions() as db:
        assert result["sent"] == 1 and db.get(SyncOutbox, row_id).sent_at is not None
    assert captured["events"][0]["quality"] == "invalid"
