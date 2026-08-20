"""AIMD adaptive platform capacity estimate for adaptive-slo admission.

Static slo-aware uses a fixed synthetic budget C. On an elastic Bedrock backend
that budget often underestimates available capacity and causes over-shedding.
This controller raises C_hat when recent admitted traffic is healthy (no 429,
low SLO-fail rate) and multiplicatively decreases when unhealthy.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from app.counters import _k

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveSnapshot:
    capacity: int
    window_admits: int
    window_slo_fail: int
    window_bedrock_429: int
    last_action: str
    window_s: float


class AdaptiveCapacity:
    """Shared AIMD capacity estimate (Redis-backed when available)."""

    def __init__(
        self,
        store,
        *,
        c0: int,
        alpha: float = 0.15,
        beta: float = 0.7,
        window_s: float = 15.0,
        c_min: int | None = None,
        c_max: int | None = None,
        slo_fail_threshold: float = 0.05,
    ) -> None:
        self._store = store
        self.c0 = max(int(c0), 1)
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.window_s = float(window_s)
        self.c_min = int(c_min if c_min is not None else max(self.c0 // 2, 1))
        self.c_max = int(c_max if c_max is not None else self.c0 * 20)
        self.slo_fail_threshold = float(slo_fail_threshold)
        self._lock = threading.Lock()
        self._local_capacity = float(self.c0)
        self._local_last_update = time.time()
        self._local_last_action = "init"
        self._cap_key = _k("adaptive", "capacity")
        self._action_key = _k("adaptive", "last_action")
        self._updated_key = _k("adaptive", "updated_at")
        # Seed shared clock so the first window is a full control interval.
        if hasattr(self._store, "set_raw"):
            self._store.set_raw(self._updated_key, str(self._local_last_update), ttl_s=86400)
            self._store.set_raw(self._cap_key, str(int(self.c0)), ttl_s=86400)
            self._store.set_raw(self._action_key, "init", ttl_s=86400)

    def current_budget(self) -> int:
        self._maybe_update()
        return int(self._read_capacity())

    def snapshot(self) -> AdaptiveSnapshot:
        self._maybe_update()
        bucket = self._window_bucket()
        admits = self._get(self._win_key(bucket, "admits"))
        fails = self._get(self._win_key(bucket, "slo_fail"))
        r429 = self._get(self._win_key(bucket, "bedrock_429"))
        return AdaptiveSnapshot(
            capacity=int(self._read_capacity()),
            window_admits=admits,
            window_slo_fail=fails,
            window_bedrock_429=r429,
            last_action=self._read_action(),
            window_s=self.window_s,
        )

    def observe(
        self,
        *,
        admitted: bool,
        slo_met: bool | None,
        bedrock_429: bool,
        ttft_ms: float | None = None,
    ) -> None:
        del ttft_ms  # reserved for richer controllers / traces
        if not admitted and not bedrock_429:
            return
        bucket = self._window_bucket()
        ttl = max(int(self.window_s * 4), 120)
        if admitted:
            self._incr(self._win_key(bucket, "admits"), 1, ttl)
            if slo_met is False:
                self._incr(self._win_key(bucket, "slo_fail"), 1, ttl)
            elif slo_met is True:
                self._incr(self._win_key(bucket, "slo_ok"), 1, ttl)
        if bedrock_429:
            self._incr(self._win_key(bucket, "bedrock_429"), 1, ttl)
        self._maybe_update()

    def _maybe_update(self) -> None:
        now = time.time()
        with self._lock:
            last = self._read_updated_at()
            if now - last < self.window_s:
                return
            # Claim this window update.
            self._set_updated_at(now)
            prev_bucket = self._window_bucket(now - self.window_s)
            admits = self._get(self._win_key(prev_bucket, "admits"))
            fails = self._get(self._win_key(prev_bucket, "slo_fail"))
            r429 = self._get(self._win_key(prev_bucket, "bedrock_429"))
            capacity = self._read_capacity()
            fail_rate = (fails / admits) if admits > 0 else 0.0
            unhealthy = r429 > 0 or (admits >= 5 and fail_rate > self.slo_fail_threshold)
            if unhealthy:
                next_c = max(self.c_min, capacity * self.beta)
                action = "decrease"
            else:
                # Grow when healthy; grow faster if we observed demand (admits>0).
                step = self.alpha * self.c0
                next_c = min(self.c_max, capacity + step)
                action = "increase" if next_c > capacity + 1 else "hold"
            self._write_capacity(next_c)
            self._write_action(action)
            logger.info(
                "adaptive AIMD action=%s capacity=%.0f->%.0f admits=%s slo_fail=%s 429=%s",
                action,
                capacity,
                next_c,
                admits,
                fails,
                r429,
            )

    def _window_bucket(self, ts: float | None = None) -> int:
        t = time.time() if ts is None else ts
        return int(t // self.window_s)

    def _win_key(self, bucket: int, name: str) -> str:
        return _k("adaptive", "w", str(bucket), name)

    def _get(self, key: str) -> int:
        return int(self._store.get_int(key))

    def _incr(self, key: str, amount: int, ttl_s: int) -> None:
        self._store.incrby(key, amount, ttl_s)

    def _read_capacity(self) -> float:
        if hasattr(self._store, "get_raw"):
            raw = self._store.get_raw(self._cap_key)
            if raw is not None:
                return float(raw)
        value = self._store.get_int(self._cap_key)
        if value <= 0:
            return float(self._local_capacity or self.c0)
        return float(value)

    def _write_capacity(self, value: float) -> None:
        self._local_capacity = float(value)
        if hasattr(self._store, "set_raw"):
            self._store.set_raw(self._cap_key, str(int(value)), ttl_s=86400)
        else:
            # Memory store: encode as int TPM via incr reset pattern.
            current = self._store.get_int(self._cap_key)
            delta = int(value) - current
            if delta != 0:
                self._store.incrby(self._cap_key, delta, 86400)
            elif current == 0:
                self._store.incrby(self._cap_key, int(value), 86400)

    def _read_action(self) -> str:
        if hasattr(self._store, "get_raw"):
            raw = self._store.get_raw(self._action_key)
            if raw:
                return str(raw)
        return self._local_last_action

    def _write_action(self, action: str) -> None:
        self._local_last_action = action
        if hasattr(self._store, "set_raw"):
            self._store.set_raw(self._action_key, action, ttl_s=86400)

    def _read_updated_at(self) -> float:
        if hasattr(self._store, "get_raw"):
            raw = self._store.get_raw(self._updated_key)
            if raw is not None:
                return float(raw)
        return self._local_last_update

    def _set_updated_at(self, ts: float) -> None:
        self._local_last_update = ts
        if hasattr(self._store, "set_raw"):
            self._store.set_raw(self._updated_key, str(ts), ttl_s=86400)
