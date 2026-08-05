from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select, text

from .config import Settings
from .db import SessionLocal
from .models import SyncOutbox, TelemetrySample


logger = logging.getLogger(__name__)


def sqlite_database_path(settings: Settings) -> Path | None:
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix):
        return None
    return Path(settings.database_url.removeprefix(prefix)).resolve()


def create_backup(settings: Settings) -> dict:
    source = sqlite_database_path(settings)
    if source is None:
        raise RuntimeError("Online backup is currently supported only on the Edge SQLite database")
    if not source.exists():
        raise RuntimeError("Edge database is not available")
    destination_dir = Path(settings.backup_directory).resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = destination_dir / f"energy-manager-edge-{stamp}.db"
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as destination_db:
        source_db.backup(destination_db)
        integrity = destination_db.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"Backup integrity check failed: {integrity}")
    hasher = hashlib.sha256()
    with destination.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    manifest = {
        "file": destination.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bytes": destination.stat().st_size,
        "sha256": digest,
        "integrity": integrity,
    }
    destination.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    prune_backups(settings)
    return manifest


def list_backups(settings: Settings) -> list[dict]:
    directory = Path(settings.backup_directory).resolve()
    if not directory.exists():
        return []
    results = []
    for manifest_path in sorted(directory.glob("energy-manager-edge-*.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (directory / manifest["file"]).is_file():
                results.append(manifest)
        except (OSError, ValueError, KeyError):
            continue
    return results


def prune_backups(settings: Settings) -> None:
    directory = Path(settings.backup_directory).resolve()
    manifests = sorted(directory.glob("energy-manager-edge-*.json"), reverse=True) if directory.exists() else []
    for manifest_path in manifests[settings.backup_retention_count:]:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            (directory / manifest.get("file", "invalid")).unlink(missing_ok=True)
        finally:
            manifest_path.unlink(missing_ok=True)


def backup_file(settings: Settings, filename: str) -> Path:
    if Path(filename).name != filename or not filename.endswith(".db"):
        raise ValueError("Invalid backup filename")
    path = Path(settings.backup_directory).resolve() / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    return path


def run_retention(settings: Settings) -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        telemetry = db.execute(delete(TelemetrySample).where(TelemetrySample.sample_at < now - timedelta(days=settings.telemetry_retention_days))).rowcount
        outbox = db.execute(delete(SyncOutbox).where(SyncOutbox.sent_at.is_not(None), SyncOutbox.sent_at < now - timedelta(days=settings.sent_outbox_retention_days))).rowcount
        db.commit()
    return {"telemetry_deleted": telemetry or 0, "outbox_deleted": outbox or 0}


def database_integrity(settings: Settings) -> str:
    if not settings.database_url.startswith("sqlite"):
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return "ok"
    with SessionLocal() as db:
        return str(db.execute(text("PRAGMA integrity_check")).scalar_one())


def storage_capacity(settings: Settings) -> dict:
    database_path = sqlite_database_path(settings)
    target = database_path.parent if database_path else Path(".")
    usage = shutil.disk_usage(target)
    return {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free, "free_percent": round(usage.free / usage.total * 100, 1)}


async def maintenance_loop(stop: asyncio.Event, settings: Settings) -> None:
    last_backup: datetime | None = None
    while not stop.is_set():
        try:
            run_retention(settings)
            if settings.backup_enabled and settings.mode == "edge":
                backups = list_backups(settings)
                if backups:
                    last_backup = datetime.fromisoformat(backups[0]["created_at"])
                if last_backup is None or datetime.now(timezone.utc) - last_backup >= timedelta(hours=settings.backup_interval_hours):
                    create_backup(settings)
                    last_backup = datetime.now(timezone.utc)
        except Exception:
            logger.exception("Edge maintenance cycle failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.maintenance_interval_seconds)
        except TimeoutError:
            pass
