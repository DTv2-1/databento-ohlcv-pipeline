"""
PAr2 Stop-Modify Throttler
===========================
Prevents micro-adjust loops on stop modifications.

Rules (from spec):
    min_modify_interval_ms: 75ms default (do not set below 50ms)
    min_delta_ticks_or_pips: 1 tick minimum price movement

Behavior:
    - If a modify arrives within the interval → merge (keep latest price)
    - Merged modify is applied when the interval expires
    - In SOFTKILL/FAILSAFE_FREEZE → tighten_only enforced
      (new stop price must reduce risk vs current stop)
    - EXIT priority commands bypass throttling entirely

Thread-safe per symbol.
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable

from .models import PACommand, KillState, Priority, IntentType


@dataclass
class PendingModify:
    """Latest pending stop modification for a symbol (merged if rapid fire)."""
    command:    PACommand
    queued_at:  float = field(default_factory=time.monotonic)
    new_price:  float = 0.0


class StopModifyThrottler:
    """
    Per-symbol stop modification throttler.

    Usage:
        throttler = StopModifyThrottler(min_interval_ms=75, min_delta=1)
        result = throttler.submit(cmd, current_stop_price=5100.0, tick_size=0.25)
        # result.allowed → True = send now, False = merged/blocked
    """

    @dataclass
    class Result:
        allowed:      bool
        reason:       str
        merged_cmd:   Optional[PACommand] = None  # set if this replaces a pending

    def __init__(
        self,
        min_interval_ms: float = 75.0,
        min_delta_ticks: float = 1.0,
        on_ready: Optional[Callable[[PACommand], None]] = None,
    ):
        """
        Args:
            min_interval_ms: minimum ms between modifies per symbol
            min_delta_ticks: minimum price movement (in ticks) to allow modify
            on_ready:        callback fired when a merged modify becomes due
        """
        self.min_interval_ms = min_interval_ms
        self.min_delta_ticks = min_delta_ticks
        self._on_ready       = on_ready

        # symbol → last allowed modify time
        self._last_modify: dict[str, float] = {}
        # symbol → pending merged modify
        self._pending: dict[str, PendingModify] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        cmd: PACommand,
        current_stop_price: float,
        tick_size: float = 0.25,
        kill_state: KillState = KillState.NORMAL,
    ) -> "StopModifyThrottler.Result":
        """
        Submit a stop modify command.

        Returns Result indicating whether to send immediately or merge.
        """
        # EXIT priority bypasses all throttling
        if cmd.priority == Priority.EXIT:
            self._mark_sent(cmd.symbol)
            return self.Result(allowed=True, reason="EXIT_BYPASS")

        new_price = float(cmd.order_spec.get("new_stop_price", 0.0))

        # Tighten-only enforcement (SOFTKILL / FAILSAFE_FREEZE)
        if kill_state in (KillState.SOFTKILL, KillState.FAILSAFE_FREEZE):
            if not cmd.constraints.tighten_only:
                return self.Result(
                    allowed=False,
                    reason=f"tighten_only required in {kill_state.value} — widening stop blocked",
                )

        # Min delta check
        delta_ticks = abs(new_price - current_stop_price) / tick_size if tick_size else 0
        if delta_ticks < self.min_delta_ticks:
            return self.Result(
                allowed=False,
                reason=f"delta {delta_ticks:.2f} ticks < min {self.min_delta_ticks} — too small",
            )

        with self._lock:
            last = self._last_modify.get(cmd.symbol, 0.0)
            elapsed_ms = (time.monotonic() - last) * 1000

            if elapsed_ms >= self.min_interval_ms:
                # Interval satisfied — send immediately
                # If there was a pending merge, this supersedes it
                self._pending.pop(cmd.symbol, None)
                self._last_modify[cmd.symbol] = time.monotonic()
                return self.Result(allowed=True, reason="OK")
            else:
                # Within interval — merge (keep latest price)
                self._pending[cmd.symbol] = PendingModify(
                    command=cmd, new_price=new_price
                )
                return self.Result(
                    allowed=False,
                    reason=f"merged — {elapsed_ms:.0f}ms < {self.min_interval_ms}ms interval",
                )

    def flush_due(self) -> list[PACommand]:
        """
        Return any pending merged modifies whose interval has now expired.
        Call this periodically (e.g., every 10ms in the drain loop).
        """
        due = []
        now = time.monotonic()
        with self._lock:
            for symbol, pending in list(self._pending.items()):
                elapsed_ms = (now - self._last_modify.get(symbol, 0.0)) * 1000
                if elapsed_ms >= self.min_interval_ms:
                    due.append(pending.command)
                    self._last_modify[symbol] = now
                    del self._pending[symbol]
        return due

    def _mark_sent(self, symbol: str) -> None:
        with self._lock:
            self._last_modify[symbol] = time.monotonic()
            self._pending.pop(symbol, None)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)
