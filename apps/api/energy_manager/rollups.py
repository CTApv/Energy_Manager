from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .contracts import SyncEvent
from .models import TelemetryRollup


def minute_bucket(value: datetime) -> datetime:
    stamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).replace(second=0, microsecond=0)


def update_minute_rollups(db: Session, edge_id: str, events: list[SyncEvent]) -> None:
    groups: dict[tuple[str, str, datetime], list[SyncEvent]] = defaultdict(list)
    for event in events:
        groups[(event.device_id, event.measurement_key, minute_bucket(event.sample_at))].append(event)
    for (device_id, key, bucket), rows in groups.items():
        item = db.scalar(select(TelemetryRollup).where(
            TelemetryRollup.edge_id == edge_id,
            TelemetryRollup.device_id == device_id,
            TelemetryRollup.measurement_key == key,
            TelemetryRollup.resolution == "1m",
            TelemetryRollup.bucket_start == bucket,
        ))
        values = [float(row.value) for row in rows if row.value is not None]
        good_values = [float(row.value) for row in rows if row.value is not None and row.quality == "good"]
        if not item:
            item = TelemetryRollup(edge_id=edge_id, device_id=device_id, measurement_key=key, resolution="1m", bucket_start=bucket, sample_count=0, good_count=0)
            db.add(item)
        previous_total = (item.average or 0.0) * (item.sample_count or 0)
        item.sample_count += len(values)
        item.good_count += len(good_values)
        if values:
            item.minimum = min(values) if item.minimum is None else min(item.minimum, *values)
            item.maximum = max(values) if item.maximum is None else max(item.maximum, *values)
            item.average = (previous_total + sum(values)) / item.sample_count
            item.last_value = values[-1]
            item.unit = rows[-1].unit
