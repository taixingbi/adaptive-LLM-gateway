from datetime import datetime, timezone


def minute_window(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.strftime("%Y-%m-%dT%H:%M")


def ttl_epoch(now: datetime | None = None, extra_seconds: int = 180) -> int:
    current = now or datetime.now(timezone.utc)
    return int(current.timestamp()) + extra_seconds
