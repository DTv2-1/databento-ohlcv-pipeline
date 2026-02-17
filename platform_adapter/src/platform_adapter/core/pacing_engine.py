"""
PA r2 — Pacing Recovery Engine

Detects IB pacing violations (Error 100, Error 162) and enters
a recovery mode with cooldown + exponential backoff.

During recovery:
  - Only critical operations (cancel, flatten) are allowed
  - Other commands are held in the queue until recovery ends
  - Cooldown increases on repeated violations

The engine hooks into ConnectionManager's error handler.

Author: PA r2
Date: 2026-02-16
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from loguru import logger


# IB pacing-related error codes
PACING_ERROR_CODES = {
    100,    # Max rate of messages per second has been exceeded
    162,    # Historical Market Data Service error (pacing violation)
}


@dataclass
class PacingEvent:
    """Emitted on pacing state changes."""
    in_recovery: bool
    error_code: int
    cooldown_sec: float
    violation_count: int
    timestamp: datetime
    message: str


class PacingEngine:
    """
    Monitors for IB pacing violations and manages recovery.
    
    When a pacing error is detected:
      1. Enter recovery mode
      2. Hold non-critical commands
      3. Wait for cooldown period
      4. Resume normal operation
    
    Repeated violations increase cooldown (exponential backoff).
    """
    
    def __init__(
        self,
        cooldown_sec: float = 5.0,
        backoff_multiplier: float = 2.0,
        max_cooldown_sec: float = 60.0,
        critical_only_during_recovery: bool = True,
        on_pacing_event: Optional[Callable[[PacingEvent], None]] = None,
    ):
        """
        Args:
            cooldown_sec: Base cooldown after pacing violation
            backoff_multiplier: Multiply cooldown on repeated violations
            max_cooldown_sec: Maximum cooldown period
            critical_only_during_recovery: If True, only allow cancel/flatten during recovery
            on_pacing_event: Callback for pacing state changes
        """
        self._base_cooldown = cooldown_sec
        self._current_cooldown = cooldown_sec
        self._backoff_multiplier = backoff_multiplier
        self._max_cooldown = max_cooldown_sec
        self._critical_only = critical_only_during_recovery
        self._on_pacing_event = on_pacing_event
        
        self._in_recovery = False
        self._recovery_until: float = 0.0  # monotonic time
        self._violation_count = 0
        self._total_violations = 0
        self._lock = threading.Lock()
        
        logger.info(
            f"PacingEngine initialized: cooldown={cooldown_sec}s, "
            f"backoff={backoff_multiplier}x, max={max_cooldown_sec}s"
        )
    
    def _check_recovery_unlocked(self) -> bool:
        """Check and update recovery state. Caller MUST hold self._lock."""
        if self._in_recovery and time.monotonic() >= self._recovery_until:
            self._in_recovery = False
            self._current_cooldown = self._base_cooldown
            self._violation_count = 0
            logger.info("Pacing recovery ended — resuming normal operations")
        return self._in_recovery

    def _remaining_unlocked(self) -> float:
        """Seconds remaining in recovery. Caller MUST hold self._lock."""
        if not self._in_recovery:
            return 0.0
        return max(0.0, self._recovery_until - time.monotonic())

    @property
    def in_recovery(self) -> bool:
        """Whether pacing recovery is active."""
        with self._lock:
            return self._check_recovery_unlocked()
    
    @property
    def recovery_remaining_sec(self) -> float:
        """Seconds remaining in recovery period."""
        with self._lock:
            return self._remaining_unlocked()
    
    def on_ib_error(self, error_code: int, error_string: str) -> bool:
        """
        Called when IB reports an error. Checks if it's a pacing violation.
        
        Args:
            error_code: IB error code
            error_string: IB error message
            
        Returns:
            True if this was a pacing violation (recovery activated)
        """
        if error_code not in PACING_ERROR_CODES:
            return False
        
        with self._lock:
            self._violation_count += 1
            self._total_violations += 1
            
            # Calculate cooldown with backoff
            if self._violation_count > 1:
                self._current_cooldown = min(
                    self._current_cooldown * self._backoff_multiplier,
                    self._max_cooldown,
                )
            
            self._in_recovery = True
            self._recovery_until = time.monotonic() + self._current_cooldown
        
        event = PacingEvent(
            in_recovery=True,
            error_code=error_code,
            cooldown_sec=self._current_cooldown,
            violation_count=self._violation_count,
            timestamp=datetime.now(),
            message=(
                f"Pacing violation detected (error {error_code}: {error_string}). "
                f"Recovery cooldown: {self._current_cooldown:.1f}s "
                f"(violation #{self._violation_count})"
            ),
        )
        
        logger.error(event.message)
        
        if self._on_pacing_event:
            try:
                self._on_pacing_event(event)
            except Exception as e:
                logger.error(f"Error in pacing event callback: {e}")
        
        return True
    
    def is_operation_allowed(self, is_critical: bool = False) -> bool:
        """
        Check if an operation is allowed given current pacing state.
        
        Args:
            is_critical: True for cancel/flatten operations
            
        Returns:
            True if the operation can proceed
        """
        with self._lock:
            if not self._check_recovery_unlocked():
                return True

        if is_critical:
            return True  # Critical operations always allowed
        
        if self._critical_only:
            return False  # Non-critical blocked during recovery
        
        return True
    
    def wait_if_needed(self, is_critical: bool = False) -> float:
        """
        Wait for recovery to end if non-critical operation.
        
        Args:
            is_critical: True for cancel/flatten operations
            
        Returns:
            Seconds waited (0 if no wait needed)
        """
        if is_critical:
            return 0.0

        with self._lock:
            if not self._check_recovery_unlocked():
                return 0.0
            remaining = self._remaining_unlocked()

        if remaining > 0:
            logger.warning(
                f"Pacing recovery active — waiting {remaining:.1f}s"
            )
            time.sleep(remaining)
            return remaining
        
        return 0.0
    
    def reset(self) -> None:
        """Reset pacing engine state."""
        with self._lock:
            self._in_recovery = False
            self._recovery_until = 0.0
            self._violation_count = 0
            self._current_cooldown = self._base_cooldown
        logger.info("PacingEngine reset")
    
    def get_status(self) -> dict:
        """Get pacing engine status."""
        with self._lock:
            self._check_recovery_unlocked()
            return {
                "in_recovery": self._in_recovery,
                "recovery_remaining_sec": round(self._remaining_unlocked(), 1),
                "current_cooldown_sec": self._current_cooldown,
                "violation_count": self._violation_count,
                "total_violations": self._total_violations,
            }
    
    def __repr__(self) -> str:
        with self._lock:
            status = "RECOVERY" if self._in_recovery else "NORMAL"
            return f"PacingEngine({status}, violations={self._total_violations})"
