from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Protocol


def minute_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _short_id(tenant_id: str) -> str:
    return tenant_id.removeprefix("tenant-")


def _k(*parts: str) -> str:
    """One hash tag so ElastiCache Serverless (cluster mode) accepts MGET."""
    return "{q}:" + ":".join(parts)


class CounterStore(Protocol):
    def get_int(self, key: str) -> int: ...
    def mget_int(self, keys: list[str]) -> list[int]: ...
    def incr(self, key: str, amount: int = 1, ttl_s: int = 120) -> int: ...
    def incrby(self, key: str, amount: int, ttl_s: int = 120) -> int: ...
    def incr_many(self, ops: list[tuple[str, int, int]]) -> None: ...


class MemoryCounters:
    """In-process fallback so unit tests and local runs do not need Redis."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, tuple[int, float]] = {}
        self._raw: dict[str, tuple[str, float]] = {}

    def _read(self, key: str, now: float) -> int:
        value = self._values.get(key)
        if value is None or value[1] <= now:
            self._values.pop(key, None)
            return 0
        return value[0]

    def get_int(self, key: str) -> int:
        now = time.time()
        with self._lock:
            return self._read(key, now)

    def mget_int(self, keys: list[str]) -> list[int]:
        now = time.time()
        with self._lock:
            return [self._read(key, now) for key in keys]

    def incr(self, key: str, amount: int = 1, ttl_s: int = 120) -> int:
        return self.incrby(key, amount, ttl_s)

    def incrby(self, key: str, amount: int, ttl_s: int = 120) -> int:
        now = time.time()
        with self._lock:
            current = self._read(key, now)
            next_value = current + amount
            self._values[key] = (next_value, now + ttl_s)
            return next_value

    def incr_many(self, ops: list[tuple[str, int, int]]) -> None:
        now = time.time()
        with self._lock:
            for key, amount, ttl_s in ops:
                current = self._read(key, now)
                self._values[key] = (current + amount, now + ttl_s)

    def get_raw(self, key: str) -> str | None:
        now = time.time()
        with self._lock:
            value = self._raw.get(key)
            if value is None or value[1] <= now:
                self._raw.pop(key, None)
                return None
            return value[0]

    def set_raw(self, key: str, value: str, ttl_s: int = 120) -> None:
        now = time.time()
        with self._lock:
            self._raw[key] = (value, now + ttl_s)


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

    def mget_int(self, keys: list[str]) -> list[int]:
        # Per-key GET is valid on cluster even if a caller omits the hash tag.
        pipe = self._client.pipeline(transaction=False)
        for key in keys:
            pipe.get(key)
        return [0 if value is None else int(value) for value in pipe.execute()]

    def incr(self, key: str, amount: int = 1, ttl_s: int = 120) -> int:
        return self.incrby(key, amount, ttl_s)

    def incrby(self, key: str, amount: int, ttl_s: int = 120) -> int:
        pipe = self._client.pipeline(transaction=False)
        pipe.incrby(key, amount)
        pipe.expire(key, ttl_s)
        return int(pipe.execute()[0])

    def incr_many(self, ops: list[tuple[str, int, int]]) -> None:
        pipe = self._client.pipeline(transaction=False)
        for key, amount, ttl_s in ops:
            pipe.incrby(key, amount)
            pipe.expire(key, ttl_s)
        pipe.execute()

    def bucket_op(self, key: str, cap: float, now: float, cost: float) -> float:
        result = self._client.eval(_BUCKET_LUA, 1, key, cap, now, cost)
        return float(result)

    def bucket_ops(self, ops: list[tuple[str, float, float, float]]) -> list[float]:
        pipe = self._client.pipeline(transaction=False)
        for key, cap, now, cost in ops:
            pipe.eval(_BUCKET_LUA, 1, key, cap, now, cost)
        return [float(value) for value in pipe.execute()]

    def get_raw(self, key: str) -> str | None:
        value = self._client.get(key)
        return None if value is None else str(value)

    def set_raw(self, key: str, value: str, ttl_s: int = 120) -> None:
        self._client.set(key, value, ex=ttl_s)


_BUCKET_LUA = """
local key = KEYS[1]
local cap = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local rate = cap / 60.0
local tokens = tonumber(redis.call('HGET', key, 'tokens'))
local ts = tonumber(redis.call('HGET', key, 'ts'))
if tokens == nil then
  tokens = cap
  ts = now
end
tokens = math.min(cap, tokens + (now - ts) * rate)
if cost > 0 and tokens < cost then
  redis.call('HSET', key, 'tokens', tostring(tokens), 'ts', tostring(now))
  redis.call('EXPIRE', key, 180)
  return -1
end
if cost > 0 then
  tokens = tokens - cost
end
redis.call('HSET', key, 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', key, 180)
return tokens
"""


class QuotaCounters:
    def __init__(self, store: CounterStore) -> None:
        self.store = store
        self._mem_lock = threading.Lock()
        self._mem_buckets: dict[str, tuple[float, float]] = {}

    def snapshot(
        self,
        tenant_id: str,
        *,
        tenant_tpm_limit: int = 0,
        platform_tpm_budget: int = 0,
        use_buckets: bool = True,
    ) -> dict[str, int | float]:
        window = minute_key()
        short = _short_id(tenant_id)
        keys = [
            _k("platform", "tpm", window),
            _k("tenant", short, "tpm", window),
            _k("tenant", short, "rpm", window),
            _k("tenant", short, "concurrency"),
            _k("platform", "queue_depth"),
        ]
        platform_tpm, tenant_tpm, tenant_rpm, tenant_concurrency, queue_depth = self.store.mget_int(keys)
        tenant_bucket = 0.0
        platform_bucket = 0.0
        if use_buckets and tenant_tpm_limit > 0 and platform_tpm_budget > 0:
            now = time.time()
            tenant_bucket, platform_bucket = self._bucket_ops(
                [
                    (_k("bucket", "tenant", short), float(tenant_tpm_limit), now, 0.0),
                    (_k("bucket", "platform"), float(platform_tpm_budget), now, 0.0),
                ]
            )
        elif use_buckets and tenant_tpm_limit > 0:
            tenant_bucket = self._bucket_op(_k("bucket", "tenant", short), float(tenant_tpm_limit), time.time(), 0.0)
        return {
            "platform_tpm": platform_tpm,
            "tenant_tpm": tenant_tpm,
            "tenant_rpm": tenant_rpm,
            "tenant_concurrency": tenant_concurrency,
            "queue_depth": queue_depth,
            "tenant_bucket": tenant_bucket,
            "platform_bucket": platform_bucket,
        }

    def record_admit(
        self,
        tenant_id: str,
        estimated_tokens: int,
        *,
        tenant_tpm_limit: int = 0,
        platform_tpm_budget: int = 0,
        use_buckets: bool = True,
    ) -> None:
        window = minute_key()
        short = _short_id(tenant_id)
        self.store.incr_many(
            [
                (_k("platform", "tpm", window), estimated_tokens, 120),
                (_k("tenant", short, "tpm", window), estimated_tokens, 120),
                (_k("tenant", short, "rpm", window), 1, 120),
                (_k("tenant", short, "admitted"), 1, 86400),
                (_k("tenant", short, "concurrency"), 1, 3600),
            ]
        )
        if use_buckets and tenant_tpm_limit > 0:
            now = time.time()
            ops = [(_k("bucket", "tenant", short), float(tenant_tpm_limit), now, float(estimated_tokens))]
            if platform_tpm_budget > 0:
                ops.append((_k("bucket", "platform"), float(platform_tpm_budget), now, float(estimated_tokens)))
            self._bucket_ops(ops)

    def release_concurrency(self, tenant_id: str) -> None:
        self.store.incr(_k("tenant", _short_id(tenant_id), "concurrency"), amount=-1, ttl_s=3600)

    def record_reject(self, tenant_id: str) -> None:
        self.store.incr(_k("tenant", _short_id(tenant_id), "rejected"), ttl_s=86400)

    def record_slo_violation(self, tenant_id: str) -> None:
        self.store.incr(_k("tenant", _short_id(tenant_id), "slo_violations"), ttl_s=86400)

    def adjust_queue(self, delta: int) -> None:
        self.store.incr(_k("platform", "queue_depth"), amount=delta, ttl_s=3600)

    def _bucket_op(self, key: str, cap: float, now: float, cost: float) -> float:
        return self._bucket_ops([(key, cap, now, cost)])[0]

    def _bucket_ops(self, ops: list[tuple[str, float, float, float]]) -> list[float]:
        if isinstance(self.store, RedisCounters):
            return self.store.bucket_ops(ops)
        with self._mem_lock:
            out: list[float] = []
            for key, cap, now, cost in ops:
                tokens, ts = self._mem_buckets.get(key, (cap, now))
                tokens = min(cap, tokens + (now - ts) * (cap / 60.0))
                if cost > 0 and tokens < cost:
                    self._mem_buckets[key] = (tokens, now)
                    out.append(-1.0)
                    continue
                if cost > 0:
                    tokens -= cost
                self._mem_buckets[key] = (tokens, now)
                out.append(tokens)
            return out


def build_counters(redis_url: str) -> QuotaCounters:
    store: CounterStore = RedisCounters(redis_url) if redis_url else MemoryCounters()
    return QuotaCounters(store)
