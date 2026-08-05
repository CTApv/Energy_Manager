from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import EnergyTariff


def price_increments(db: Session, increments: list[tuple[datetime, float]], zone: ZoneInfo, default_price: float, direction: str = "import") -> dict:
    tariffs = list(db.scalars(select(EnergyTariff).where(EnergyTariff.active.is_(True)).order_by(EnergyTariff.priority.desc(), EnergyTariff.valid_from.desc())))
    total = 0.0
    by_tariff: dict[str, float] = {}
    for stamp, energy in increments:
        local = stamp.astimezone(zone)
        minute = local.hour * 60 + local.minute
        selected = next((tariff for tariff in tariffs if (tariff.valid_from.replace(tzinfo=timezone.utc) if tariff.valid_from.tzinfo is None else tariff.valid_from) <= stamp and (tariff.valid_to is None or stamp < (tariff.valid_to.replace(tzinfo=timezone.utc) if tariff.valid_to.tzinfo is None else tariff.valid_to)) and local.weekday() in tariff.weekdays and tariff.start_minute <= minute < tariff.end_minute), None)
        price = getattr(selected, f"{direction}_price_per_kwh") if selected else default_price
        amount = energy * price
        total += amount
        label = selected.name if selected else "Tariffa predefinita"
        by_tariff[label] = by_tariff.get(label, 0.0) + amount
    return {"total": total, "breakdown": [{"tariff": name, "amount": value} for name, value in by_tariff.items()], "tariff_count": len(tariffs)}
