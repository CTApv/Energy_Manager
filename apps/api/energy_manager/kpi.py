from dataclasses import dataclass


@dataclass(frozen=True)
class CounterDelta:
    value: float | None
    quality: str
    reason: str | None = None


def counter_delta(previous: float | None, current: float | None, overflow_at: float | None = None) -> CounterDelta:
    if previous is None or current is None:
        return CounterDelta(None, "missing", "missing counter endpoint")
    if current >= previous:
        return CounterDelta(current - previous, "good")
    if overflow_at and previous > overflow_at * 0.8 and current < overflow_at * 0.2:
        return CounterDelta((overflow_at - previous) + current, "good", "counter overflow")
    if current >= 0:
        return CounterDelta(current, "estimated", "counter reset")
    return CounterDelta(None, "invalid", "negative counter")


def unattributed_energy(upstream: float | None, children: list[float | None]) -> dict:
    if upstream is None or any(value is None for value in children):
        return {"value": None, "percentage": None, "quality": "missing", "reason": "incomplete interval"}
    child_total = sum(value for value in children if value is not None)
    difference = upstream - child_total
    percentage = difference / upstream * 100 if upstream else None
    quality = "good" if difference >= 0 else "invalid"
    return {"value": difference, "percentage": percentage, "quality": quality, "reason": None if quality == "good" else "children exceed upstream"}

