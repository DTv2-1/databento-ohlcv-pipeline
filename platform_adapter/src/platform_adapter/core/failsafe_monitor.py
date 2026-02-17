"""
PA r2 — Failsafe Heartbeat Monitor

Monitors heartbeats from the Execution layer (Exec).
If Exec stops sending heartbeats, the failsafe escalates through 3 stages:

  Stage 1 (T_warn):    Log warning. No action.
  Stage 2 (T_freeze):  Freeze new orders (SoftKill-like).
  Stage 3 (T_flatten): Auto-flatten all positions (HardKill).

Exec calls `heartbeat_from_exec()` periodically.
If silence exceeds the configured thresholds, PA self-protects.

Author: PA r2
Date: 2026-02-16
"""

from __future__ import annotations

import threading
import time
from enum import IntEnum
from typing import Callable, Optional
from dataclasses import dataclass
from datetime import datetime

from loguru import logger


class FailsafeStage(IntEnum):
    """Failsafe escalation stages."""
    NORMAL = 0
    WARN = 1
    FREEZE = 2
    FLATTEN = 3


@dataclass
class FailsafeEvent:
    """Emitted on failsafe stage changes."""
    stage: FailsafeStage
    seconds_since_heartbeat: float
    timestamp: datetime
    message: str


class FailsafeMonitor:
    """
    Monitors Exec heartbeats and escalates through failsafe stages.
    
    Runs a background thread that checks time since last heartbeat.
    Thread-safe: heartbeat_from_exec() can be called from any thread.
    """
    
    def __init__(
        self,
        t_warn_sec: float = 10.0,
        t_freeze_sec: float = 15.0,
        t_flatten_sec: float = 180.0,
        check_interval_sec: float = 1.0,
        on_stage_changed: Optional[Callable[[FailsafeEvent], None]] = None,
        on_freeze: Optional[Callable[[], None]] = None,
        on_flatten: Optional[Callable[[], None]] = None,
    ):
        """
        Args:
            t_warn_sec: Seconds of silence before Stage 1 (warning)
            t_freeze_sec: Seconds of silence before Stage 2 (freeze orders)
            t_flatten_sec: Seconds of silence before Stage 3 (auto-flatten)
            check_interval_sec: How often the monitor thread checks
            on_stage_changed: Callback for stage change events
            on_freeze: Callback to freeze new orders (typically set_softkill)
            on_flatten: Callback to flatten all (typically hardkill)
        """
        if not (t_warn_sec < t_freeze_sec < t_flatten_sec):
            raise ValueError(
                f"Failsafe timers must be t_warn < t_freeze < t_flatten, "
                f"got {t_warn_sec} < {t_freeze_sec} < {t_flatten_sec}"
            )
        
        self._t_warn = t_warn_sec
        self._t_freeze = t_freeze_sec
        self._t_flatten = t_flatten_sec
        self._check_interval = check_interval_sec
        
        self._on_stage_changed = on_stage_changed
        self._on_freeze = on_freeze
        self._on_flatten = on_flatten
        
        self._last_heartbeat: float = time.monotonic()
        self._stage = FailsafeStage.NORMAL
        self._lock = threading.Lock()
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        logger.info(
            f"FailsafeMonitor initialized: "
            f"warn={t_warn_sec}s, freeze={t_freeze_sec}s, flatten={t_flatten_sec}s"
        )
    
    @property
    def stage(self) -> FailsafeStage:
        """Current failsafe stage."""
        with self._lock:
            return self._stage
    
    @property
    def seconds_since_heartbeat(self) -> float:
        """Seconds since last heartbeat from Exec."""
        with self._lock:
            return time.monotonic() - self._last_heartbeat
    
    def heartbeat_from_exec(self) -> None:
        """
        Called by Exec to signal it's alive.
        
        Resets the failsafe timer. If currently in an escalated stage,
        de-escalates back to NORMAL.
        """
        with self._lock:
            self._last_heartbeat = time.monotonic()
            old_stage = self._stage
            
            if old_stage != FailsafeStage.NORMAL:
                self._stage = FailsafeStage.NORMAL
                logger.info(
                    f"Failsafe de-escalated: {old_stage.name} → NORMAL "
                    f"(heartbeat received)"
                )
                event = FailsafeEvent(
                    stage=FailsafeStage.NORMAL,
                    seconds_since_heartbeat=0.0,
                    timestamp=datetime.now(),
                    message="Heartbeat received — de-escalated to NORMAL",
                )
        
        # Emit outside lock
        if old_stage != FailsafeStage.NORMAL and self._on_stage_changed:
            try:
                self._on_stage_changed(event)
            except Exception as e:
                logger.error(f"Error in failsafe stage callback: {e}")
    
    def start(self) -> None:
        """Start the failsafe monitor background thread."""
        if self._running:
            logger.warning("FailsafeMonitor already running")
            return
        
        self._running = True
        self._last_heartbeat = time.monotonic()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="PA-Failsafe",
        )
        self._thread.start()
        logger.info("FailsafeMonitor started")
    
    def stop(self) -> None:
        """Stop the failsafe monitor."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        logger.info("FailsafeMonitor stopped")
    
    def _monitor_loop(self) -> None:
        """Background loop that checks heartbeat timing."""
        while self._running:
            try:
                self._check_heartbeat()
            except Exception as e:
                logger.error(f"Error in failsafe monitor: {e}")
            time.sleep(self._check_interval)
    
    def _check_heartbeat(self) -> None:
        """Check elapsed time since last heartbeat and escalate if needed."""
        with self._lock:
            elapsed = time.monotonic() - self._last_heartbeat
            old_stage = self._stage
            new_stage = old_stage
            
            if elapsed >= self._t_flatten and old_stage < FailsafeStage.FLATTEN:
                new_stage = FailsafeStage.FLATTEN
            elif elapsed >= self._t_freeze and old_stage < FailsafeStage.FREEZE:
                new_stage = FailsafeStage.FREEZE
            elif elapsed >= self._t_warn and old_stage < FailsafeStage.WARN:
                new_stage = FailsafeStage.WARN
            
            if new_stage == old_stage:
                return
            
            self._stage = new_stage
        
        # Build event and fire callbacks outside lock
        messages = {
            FailsafeStage.WARN: f"No heartbeat for {elapsed:.1f}s — WARNING",
            FailsafeStage.FREEZE: f"No heartbeat for {elapsed:.1f}s — FREEZING new orders",
            FailsafeStage.FLATTEN: f"No heartbeat for {elapsed:.1f}s — AUTO-FLATTEN triggered",
        }
        
        event = FailsafeEvent(
            stage=new_stage,
            seconds_since_heartbeat=elapsed,
            timestamp=datetime.now(),
            message=messages.get(new_stage, ""),
        )
        
        # Log at appropriate level
        if new_stage == FailsafeStage.WARN:
            logger.warning(event.message)
        elif new_stage == FailsafeStage.FREEZE:
            logger.error(event.message)
        elif new_stage == FailsafeStage.FLATTEN:
            logger.critical(event.message)
        
        # Stage change callback
        if self._on_stage_changed:
            try:
                self._on_stage_changed(event)
            except Exception as e:
                logger.error(f"Error in failsafe stage callback: {e}")
        
        # Action callbacks
        if new_stage == FailsafeStage.FREEZE and self._on_freeze:
            try:
                self._on_freeze()
            except Exception as e:
                logger.error(f"Error in failsafe freeze callback: {e}")
        
        if new_stage == FailsafeStage.FLATTEN and self._on_flatten:
            try:
                self._on_flatten()
            except Exception as e:
                logger.error(f"Error in failsafe flatten callback: {e}")
    
    def get_status(self) -> dict:
        """Get failsafe monitor status."""
        with self._lock:
            return {
                "stage": self._stage.name,
                "seconds_since_heartbeat": round(
                    time.monotonic() - self._last_heartbeat, 1
                ),
                "running": self._running,
                "t_warn_sec": self._t_warn,
                "t_freeze_sec": self._t_freeze,
                "t_flatten_sec": self._t_flatten,
            }
    
    def __repr__(self) -> str:
        return (
            f"FailsafeMonitor(stage={self._stage.name}, "
            f"running={self._running})"
        )
