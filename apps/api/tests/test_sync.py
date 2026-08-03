import asyncio

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
        row = SyncOutbox(event_type="telemetry", payload={"sample_id": "sample-1"})
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
