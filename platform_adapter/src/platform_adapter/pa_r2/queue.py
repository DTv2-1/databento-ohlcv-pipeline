"""
PAr2 Order Queue — Single ingress with priority lanes
=====================================================
All place/modify/cancel go through this queue.
Drained by the rate limiter before dispatch to IB.

Two lanes (per spec):
    EXIT   lane — CLOSE / FLATTEN / HARDKILL / CANCEL
    NORMAL lane — everything else

Drain order: EXIT lane is always drained first within each tick.

Idempotency:
    - Each command has a unique command_id
    - Duplicate command_ids are silently dropped
    - Processed IDs are tracked in a bounded set (last 10k)

Single-net-position enforcement:
    - PAr2 tracks one open position per symbol per instance
    - OPEN/ADD rejected if position already open for that symbol
    - Rejection emits COMMAND_REJECTED PAEvent
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from typing import Optional, Callable

from .models import (
    PACommand,
    PAEvent,
    PAEventType,
    IntentType,
    Priority,
    KillState,
    make_command_rejected_event,
)


class OrderQueue:
    """
    Dual-lane command queue with idempotency and position enforcement.

    Usage:
        q = OrderQueue(on_event=emit_fn)
        q.enqueue(cmd)
        cmd = q.dequeue(block=True, timeout=0.1)
    """

    _DEDUP_MAX = 10_000  # max command_ids to track

    def __init__(
        self,
        on_event: Optional[Callable[[PAEvent], None]] = None,
        kill_state_fn: Optional[Callable[[], KillState]] = None,
    ):
        """
        Args:
            on_event:      callback to emit PAEvents (COMMAND_REJECTED etc)
            kill_state_fn: callable that returns current KillState (for enforcement)
        """
        self._exit_q:   queue.Queue[PACommand] = queue.Queue()
        self._normal_q: queue.Queue[PACommand] = queue.Queue()

        self._seen_ids: deque[str] = deque(maxlen=self._DEDUP_MAX)
        self._seen_set: set[str]   = set()

        # symbol → bool (True = position open)
        self._positions: dict[str, bool] = {}
        self._lock = threading.Lock()

        self._on_event      = on_event or (lambda e: None)
        self._kill_state_fn = kill_state_fn or (lambda: KillState.NORMAL)

    # ── Public API ────────────────────────────────────────────────────────────

    def enqueue(self, cmd: PACommand) -> bool:
        """
        Add command to queue.

        Returns True if enqueued, False if rejected (duplicate / position
        violation / kill state block). Emits PAEvent on rejection.
        """
        # 1. Idempotency check
        if self._is_duplicate(cmd.command_id):
            return False

        # 2. Kill state enforcement
        kill_state = self._kill_state_fn()
        reject_reason = self._check_kill_state(cmd, kill_state)
        if reject_reason:
            self._emit_rejected(cmd, reject_reason, kill_state)
            return False

        # 3. Single-net-position enforcement
        if cmd.is_open_or_add():
            with self._lock:
                if self._positions.get(cmd.symbol, False):
                    self._emit_rejected(
                        cmd,
                        f"Position already open for {cmd.symbol} — single-net-position rule",
                        kill_state,
                    )
                    return False

        # 4. Route to correct lane
        self._mark_seen(cmd.command_id)
        if cmd.priority == Priority.EXIT:
            self._exit_q.put(cmd)
        else:
            self._normal_q.put(cmd)
        return True

    def dequeue(self, block: bool = True, timeout: float = 0.05) -> Optional[PACommand]:
        """
        Get next command. EXIT lane is always drained first.

        Returns None if both queues empty (or timeout).
        """
        # Always drain EXIT first
        try:
            return self._exit_q.get_nowait()
        except queue.Empty:
            pass

        try:
            return self._normal_q.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def notify_position_opened(self, symbol: str) -> None:
        """Called by adapter when IB confirms an order is filled (opening)."""
        with self._lock:
            self._positions[symbol] = True

    def notify_position_closed(self, symbol: str) -> None:
        """Called by adapter when position is fully closed."""
        with self._lock:
            self._positions[symbol] = False

    def has_position(self, symbol: str) -> bool:
        with self._lock:
            return self._positions.get(symbol, False)

    def depth(self) -> dict[str, int]:
        return {
            "exit":   self._exit_q.qsize(),
            "normal": self._normal_q.qsize(),
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _is_duplicate(self, command_id: str) -> bool:
        with self._lock:
            return command_id in self._seen_set

    def _mark_seen(self, command_id: str) -> None:
        with self._lock:
            if len(self._seen_ids) == self._DEDUP_MAX:
                oldest = self._seen_ids[0]
                self._seen_set.discard(oldest)
            self._seen_ids.append(command_id)
            self._seen_set.add(command_id)

    def _check_kill_state(
        self, cmd: PACommand, kill_state: KillState
    ) -> Optional[str]:
        """
        Returns rejection reason string, or None if allowed.

        Enforcement table (from runtime state machine spec v0):
          NORMAL          → all allowed
          SOFTKILL        → OPEN/ADD blocked
          FAILSAFE_FREEZE → OPEN/ADD blocked
          FAILSAFE_AUTOEXIT → OPEN/ADD blocked; non-EXIT blocked
          HARDKILL        → OPEN/ADD blocked; non-EXIT blocked
          LOCKOUT         → everything blocked (except CANCEL if tighten_only)
        """
        if kill_state == KillState.NORMAL:
            return None

        if kill_state == KillState.LOCKOUT:
            return f"PAr2 is in LOCKOUT — human reset required"

        if kill_state in (KillState.HARDKILL, KillState.FAILSAFE_AUTOEXIT):
            if not cmd.is_exit():
                return f"Command blocked — kill state is {kill_state.value}"
            return None

        # SOFTKILL or FAILSAFE_FREEZE
        if cmd.is_open_or_add():
            return f"OPEN/ADD blocked — kill state is {kill_state.value}"

        return None

    def _emit_rejected(
        self, cmd: PACommand, reason: str, kill_state: KillState
    ) -> None:
        evt = make_command_rejected_event(cmd, reason, kill_state)
        self._on_event(evt)
