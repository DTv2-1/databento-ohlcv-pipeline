"""
PAr2 Rate Limiter — Token Bucket per channel
============================================
Enforces per-channel message rate limits against IB Gateway.

IB hard limit: 50 msg/sec (Gateway-level, shared across all clientIds)
PAr2 soft limits (configurable):
    sustained: 20 msg/sec per channel
    burst:     40 msg/sec per channel

Algorithm: token bucket
    - Tokens refill at `sustained` rate
    - Bucket capacity = `burst` (max burst size)
    - Each acquire() consumes 1 token
    - If no token available → caller must wait or be denied

Channels (from WireContract):
    order_place / order_modify / order_cancel / market_data_subscribe / misc
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokenBucket:
    """
    Single token bucket for one channel.

    Thread-safe. Uses a lock per bucket.
    """
    sustained_per_sec: float  # refill rate (tokens/sec)
    burst_max: float          # bucket capacity
    _tokens: float            = field(init=False)
    _last_refill: float       = field(init=False)
    _lock: threading.Lock     = field(init=False, repr=False)

    def __post_init__(self):
        self._tokens      = self.burst_max
        self._last_refill = time.monotonic()
        self._lock        = threading.Lock()

    def _refill(self) -> None:
        now     = time.monotonic()
        elapsed = now - self._last_refill
        gained  = elapsed * self.sustained_per_sec
        self._tokens      = min(self.burst_max, self._tokens + gained)
        self._last_refill = now

    def acquire(self, block: bool = True, timeout: float = 5.0) -> bool:
        """
        Try to consume 1 token.

        Args:
            block:   if True, wait until token available (up to timeout)
            timeout: max seconds to wait if block=True

        Returns:
            True if token consumed, False if timed out / denied
        """
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
            if not block or time.monotonic() >= deadline:
                return False
            # Sleep a short interval and retry
            time.sleep(1.0 / self.sustained_per_sec / 2)

    def available(self) -> float:
        """Current token count (approximate, for monitoring)."""
        with self._lock:
            self._refill()
            return self._tokens


class ChannelRateLimiter:
    """
    Per-channel token bucket rate limiter.

    One bucket per channel. EXIT-priority commands bypass the limiter
    (they still consume a token but never block — consistent with spec:
    'maintain global rate safety, but always service exits first').
    """

    CHANNELS = [
        "order_place",
        "order_modify",
        "order_cancel",
        "market_data_subscribe",
        "misc",
    ]

    def __init__(
        self,
        sustained_per_sec: float = 20.0,
        burst_max: float          = 40.0,
    ):
        self.sustained_per_sec = sustained_per_sec
        self.burst_max         = burst_max
        self._buckets: dict[str, TokenBucket] = {
            ch: TokenBucket(sustained_per_sec=sustained_per_sec, burst_max=burst_max)
            for ch in self.CHANNELS
        }

    def acquire(
        self,
        channel: str,
        priority: str = "NORMAL",
        block: bool   = True,
        timeout: float = 5.0,
    ) -> bool:
        """
        Acquire a slot for the given channel.

        EXIT priority commands never block (bypass wait, but still
        consume a token to keep accounting accurate).

        Returns True if slot acquired, False if timed out.
        """
        bucket = self._buckets.get(channel)
        if bucket is None:
            # Unknown channel — fall through (don't block PAr2)
            return True

        if priority == "EXIT":
            # Best-effort consume — do not block even if empty
            bucket.acquire(block=False)
            return True

        return bucket.acquire(block=block, timeout=timeout)

    def available(self, channel: str) -> float:
        bucket = self._buckets.get(channel)
        return bucket.available() if bucket else 0.0

    def stats(self) -> dict[str, float]:
        return {ch: b.available() for ch, b in self._buckets.items()}
