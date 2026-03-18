"""
PAr2 Kill State Machine
========================
Enforces runtime safety states at the PAr2 boundary.

States (from runtime state machine spec v0):
    NORMAL           → standard operation
    SOFTKILL         → block OPEN/ADD; allow CLOSE + tighten stops
    FAILSAFE_FREEZE  → heartbeat loss stage 1 (T_freeze default 15s)
    FAILSAFE_AUTOEXIT → heartbeat loss stage 2 (T_flatten default 180s) → flatten + lockout
    HARDKILL         → panic flatten immediately
    LOCKOUT          → everything blocked; human reset required

Transition rules:
    NORMAL → SOFTKILL           : OPERATOR_SOFTKILL or RISK_SOFTKILL
    SOFTKILL → NORMAL           : OPERATOR_SOFTKILL_DISABLE
    NORMAL/SOFTKILL → FREEZE    : heartbeat loss > T_freeze
    FREEZE → AUTOEXIT           : heartbeat loss > T_flatten
    AUTOEXIT → LOCKOUT          : after flatten completes (if autoexit_implies_lockout=True)
    ANY → HARDKILL              : OPERATOR_HARDKILL or RISK_HARDKILL
    HARDKILL → LOCKOUT          : after flatten completes
    LOCKOUT → NORMAL            : OPERATOR_RESET_LOCKOUT only

LAW: AutoExit implies LOCKOUT (default=true).
     PAr2 must emit LOCKOUT_ENABLED after FAILSAFE_STAGE_CHANGED(AUTOEXIT).
"""

from __future__ import annotations

import time
import threading
import logging
from typing import Callable, Optional

from .models import (
    KillState,
    PAEvent,
    PAEventType,
    TradingMode,
    make_kill_event,
)

logger = logging.getLogger(__name__)


class KillStateMachine:
    """
    Runtime safety state machine for PAr2.

    Thread-safe. Heartbeat monitor runs in a background thread.

    Usage:
        ksm = KillStateMachine(on_event=emit_fn, on_flatten=flatten_fn)
        ksm.start()
        ksm.heartbeat()                          # called by Dispatcher ping
        ksm.set_softkill(True, "risk limit")
        ksm.hardkill("operator panic")
        ksm.reset_lockout()                      # operator reset
        ksm.stop()
    """

    def __init__(
        self,
        on_event:   Callable[[PAEvent], None],
        on_flatten: Callable[[str], None],        # called with reason on AUTOEXIT/HARDKILL
        trading_mode:             TradingMode = TradingMode.PAPER,
        freeze_after_ms:          float = 15_000.0,
        autoexit_after_ms:        float = 180_000.0,
        autoexit_implies_lockout: bool  = True,
        heartbeat_check_interval_ms: float = 1_000.0,
    ):
        self._on_event   = on_event
        self._on_flatten = on_flatten
        self._mode       = trading_mode

        self._freeze_after_ms          = freeze_after_ms
        self._autoexit_after_ms        = autoexit_after_ms
        self._autoexit_implies_lockout = autoexit_implies_lockout
        self._hb_check_interval        = heartbeat_check_interval_ms / 1000.0

        self._state: KillState     = KillState.NORMAL
        self._last_heartbeat: float = time.monotonic()
        self._lock = threading.Lock()

        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._last_heartbeat = time.monotonic()
        self._monitor_thread = threading.Thread(
            target=self._heartbeat_monitor,
            daemon=True,
            name="PAr2-HeartbeatMonitor",
        )
        self._monitor_thread.start()
        logger.info("PAr2 KillStateMachine started — state=NORMAL")

    def stop(self) -> None:
        self._running = False

    # ── Heartbeat (called by Dispatcher ping) ─────────────────────────────────

    def heartbeat(self, ts: Optional[float] = None) -> None:
        """
        Record heartbeat from Dispatcher.
        Resets failsafe countdown. Recovers FREEZE → NORMAL if heartbeat resumes.
        """
        with self._lock:
            self._last_heartbeat = ts or time.monotonic()
            # Auto-recover from FREEZE if heartbeat resumes
            if self._state == KillState.FAILSAFE_FREEZE:
                self._transition_to(KillState.NORMAL, "heartbeat resumed")

    # ── Operator / RiskGov triggers ───────────────────────────────────────────

    def set_softkill(self, enabled: bool, reason: str = "") -> None:
        with self._lock:
            if enabled:
                if self._state == KillState.NORMAL:
                    self._transition_to(KillState.SOFTKILL, reason)
            else:
                if self._state == KillState.SOFTKILL:
                    self._transition_to(KillState.NORMAL, reason)

    def hardkill(self, reason: str = "OPERATOR_PANIC") -> None:
        with self._lock:
            if self._state != KillState.LOCKOUT:
                self._transition_to(KillState.HARDKILL, reason)
                # Trigger flatten (called outside lock to avoid deadlock)
        self._on_flatten(reason)
        with self._lock:
            self._transition_to(KillState.LOCKOUT, "post-hardkill lockout")

    def reset_lockout(self, reason: str = "OPERATOR_RESET") -> None:
        with self._lock:
            if self._state == KillState.LOCKOUT:
                self._transition_to(KillState.NORMAL, reason)
                self._last_heartbeat = time.monotonic()
            else:
                logger.warning(f"reset_lockout called but state={self._state.value}")

    # ── State access ──────────────────────────────────────────────────────────

    @property
    def state(self) -> KillState:
        with self._lock:
            return self._state

    def is_trading_allowed(self) -> bool:
        return self._state == KillState.NORMAL

    # ── Heartbeat monitor thread ──────────────────────────────────────────────

    def _heartbeat_monitor(self) -> None:
        """Background thread — checks heartbeat loss and triggers failsafe."""
        while self._running:
            time.sleep(self._hb_check_interval)
            with self._lock:
                if self._state in (
                    KillState.HARDKILL,
                    KillState.LOCKOUT,
                    KillState.FAILSAFE_AUTOEXIT,
                ):
                    continue  # already in terminal/active flatten state

                elapsed_ms = (time.monotonic() - self._last_heartbeat) * 1000

                if elapsed_ms >= self._autoexit_after_ms:
                    if self._state != KillState.FAILSAFE_AUTOEXIT:
                        self._transition_to(
                            KillState.FAILSAFE_AUTOEXIT,
                            f"heartbeat lost {elapsed_ms:.0f}ms > {self._autoexit_after_ms}ms",
                        )
                        # Flatten triggered outside lock
                        threading.Thread(
                            target=self._autoexit_sequence,
                            daemon=True,
                            name="PAr2-AutoExit",
                        ).start()

                elif elapsed_ms >= self._freeze_after_ms:
                    if self._state not in (
                        KillState.FAILSAFE_FREEZE,
                        KillState.FAILSAFE_AUTOEXIT,
                    ):
                        self._transition_to(
                            KillState.FAILSAFE_FREEZE,
                            f"heartbeat lost {elapsed_ms:.0f}ms > {self._freeze_after_ms}ms",
                        )

    def _autoexit_sequence(self) -> None:
        """Flatten positions, then optionally lock out."""
        reason = "FAILSAFE_AUTOEXIT"
        self._on_flatten(reason)
        if self._autoexit_implies_lockout:
            with self._lock:
                self._transition_to(KillState.LOCKOUT, "autoexit_implies_lockout=True")

    # ── Internal transition ───────────────────────────────────────────────────

    def _transition_to(self, new_state: KillState, reason: str) -> None:
        """Must be called with self._lock held."""
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state
        logger.info(f"KillState: {old_state.value} → {new_state.value} | {reason}")

        # Emit corresponding PAEvent
        event_type = self._state_to_event_type(new_state)
        if event_type:
            evt = make_kill_event(
                event_type=event_type,
                kill_state=new_state,
                reason=reason,
                trading_mode=self._mode,
            )
            # Emit outside lock to avoid deadlock — post to thread-safe callback
            threading.Thread(
                target=self._on_event,
                args=(evt,),
                daemon=True,
            ).start()

        # LAW: AUTOEXIT must also emit LOCKOUT_ENABLED (handled in _autoexit_sequence)
        # LAW: FAILSAFE_STAGE_CHANGED must emit for FREEZE and AUTOEXIT
        if new_state in (KillState.FAILSAFE_FREEZE, KillState.FAILSAFE_AUTOEXIT):
            stage_evt = PAEvent(
                type=PAEventType.FAILSAFE_STAGE_CHANGED,
                trading_mode=self._mode,
                payload={
                    "stage":      new_state.value,
                    "prev_stage": old_state.value,
                    "reason":     reason,
                },
            )
            threading.Thread(
                target=self._on_event,
                args=(stage_evt,),
                daemon=True,
            ).start()

    @staticmethod
    def _state_to_event_type(state: KillState) -> Optional[PAEventType]:
        return {
            KillState.SOFTKILL:          PAEventType.SOFTKILL_ENABLED,
            KillState.NORMAL:            PAEventType.SOFTKILL_DISABLED,
            KillState.HARDKILL:          PAEventType.HARDKILL_EXECUTED,
            KillState.LOCKOUT:           PAEventType.LOCKOUT_ENABLED,
        }.get(state)
