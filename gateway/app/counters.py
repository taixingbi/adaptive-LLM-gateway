from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Protocol


def minute_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")


class CounterStore(Protocol):
    def get_int(self, key: str) -> int: ...
    def incr(self, key: str, amount: int = 1, ttl_s: int = 120) -> int: ...
    def incrby(self, key: str, amount: int, ttl_s: int = 120) -> int: ...


class MemoryCounters:
    """In-process fallback so unit tests and local runs do not need Redis."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, tuple[int, float]] = {}

    def _purge(self, now: float) -> None:
        expired = [k for k, (_, exp) in self._values.items() if exp <= now]
        for key in expired:
            del self._values[key]

    def get_int(self, key: str) -> int:
        now = time.time()
        with self._lock:
            self._purge(now)
            value = self._values.get(key)
            return 0 if value is None else value[0]

    def incr(self, key: str, amount: int = 1, ttl_s: int = 120) -> int:
        return self.incrby(key, amount, ttl_s)

    def incrby(self, key: str, amount: int, ttl_s: int = 120) -> int:
        now = time.time()
        with self._lock:
            self._purge(now)
            current, _ = self._values.get(key, (0, now + ttl_s))
            next_value = current + amount
            self._values[key] = (next_value, now + ttl_s)
            return next_value


class RedisCounters:
    def __init__(self, url: str) -> None:
        import redis

        kwargs = {"decode_responses": True}
        if url.startswith("rediss://"):
            kwargs["ssl_cert_reqs"] = None
        self._client = redis.from_url(url, **kwargs)

    def get_int(self, key: str) -> int:
        value = self._client.get(key)
        return 0 if value is None else int(value)

    def incr(self, key: str, amount: int = 1, ttl_s: int = 120) -> int:
        return self.incrby(key, amount, ttl_s)

    def incrby(self, key: str, amount: int, ttl_s: int = 120) -> int:
        pipe = self._client.pipeline()
        pipe.incrby(key, amount)
        pipe.expire(key, ttl_s)
        results = pipe.execute()
        return int(results[0])


class QuotaCounters:
    def __init__(self, store: CounterStore) -> None:
        self.store = store

    def snapshot(self, tenant_id: str) -> dict[str, int]:
        window = minute_key()
        short = tenant_id.replace("tenant-", "")
        return {
            "platform_tpm": self.store.get_int(f"platform:tpm:{window}"),
            "tenant_tpm": self.store.get_int(f"tenant:{short}:tpm:{window}"),
            "tenant_rpm": self.store.get_int(f"tenant:{short}:rpm:{window}"),
            "tenant_concurrency": self.store.get_int(f"tenant:{short}:concurrency"),
            "queue_depth": self.store.get_int("platform:queue_depth"),
        }

    def record_admit(self, tenant_id: str, estimated_tokens: int) -> None:
        window = minute_key()
        short = tenant_id.replace("tenant-", "")
        self.store.incrby(f"platform:tpm:{window}", estimated_tokens)
        self.store.incrby(f"tenant:{short}:tpm:{window}", estimated_tokens)
        self.store.incr(f"tenant:{short}:rpm:{window}")
        self.store.incr(f"tenant:{short}:admitted")
        self.store.incr(f"tenant:{short}:concurrency", ttl_s=3600)

    def release_concurrency(self, tenant_id: str) -> None:
        short = tenant_id.replace("tenant-", "")
        self.store.incr(f"tenant:{short}:concurrency", amount=-1, ttl_s=3600)

    def record_reject(self, tenant_id: str) -> None:
        short = tenant_id.replace("tenant-", "")
        self.store.incr(f"tenant:{short}:rejected")

    def record_slo_violation(self, tenant_id: str) -> None:
        short = tenant_id.replace("tenant-", "")
        self.store.incr(f"tenant:{short}:slo_violations")

    def adjust_queue(self, delta: int) -> None:
        self.store.incr("platform:queue_depth", amount=delta, ttl_s=3600)


def build_counters(redis_url: str) -> QuotaCounters:
    store: CounterStore = RedisCounters(redis_url) if redis_url else MemoryCounters()
    return QuotaCounters(store)
