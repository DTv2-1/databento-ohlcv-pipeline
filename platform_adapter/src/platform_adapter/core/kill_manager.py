"""
PA r2 — Kill State Machine

Manages the kill state lifecycle:
  NORMAL → SOFTKILL → HARDKILL → LOCKOUT
  NORMAL → HARDKILL → LOCKOUT
  Any → FAILSAFE_FREEZE → HARDKILL → LOCKOUT

Kill states control which commands PA will accept:
  NORMAL:          All commands allowed
  SOFTKILL:        Block OPEN/ADD. Allow REDUCE/CLOSE/CANCEL.
  HARDKILL:        Cancel all orders, flatten all positions, then LOCKOUT.
  FAILSAFE_FREEZE: No new orders. Existing orders remain.
  LOCKOUT:         Everything blocked. Human reset required.

Author: PA r2
Date: 2026-02-16
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

from loguru import logger


class KillState(str, Enum):
    """PA kill states."""
    NORMAL = "NORMAL"
    SOFTKILL = "SOFTKILL"
    HARDKILL = "HARDKILL"
    FAILSAFE_FREEZE = "FAILSAFE_FREEZE"
    LOCKOUT = "LOCKOUT"


class CommandIntent(str, Enum):
    """Classifies what a command intends to do for kill-state gating."""
    OPEN = "OPEN"           # New position / add to position
    ADD = "ADD"             # Same as OPEN (increase exposure)
    REDUCE = "REDUCE"       # Reduce position
    CLOSE = "CLOSE"         # Close/flatten position
    CANCEL = "CANCEL"       # Cancel open order
    MODIFY_STOP = "MODIFY_STOP"  # Modify a stop (protective)
    MARKET_DATA = "MARKET_DATA"  # Market data subscription
    ACCOUNT = "ACCOUNT"     # Account/position queries
    ADMIN = "ADMIN"         # Kill/lockout/reconcile commands


# Which intents are allowed in each state
_ALLOWED_INTENTS: Dict[KillState, set] = {
    KillState.NORMAL: {
        CommandIntent.OPEN, CommandIntent.ADD, CommandIntent.REDUCE,
        CommandIntent.CLOSE, CommandIntent.CANCEL, CommandIntent.MODIFY_STOP,
        CommandIntent.MARKET_DATA, CommandIntent.ACCOUNT, CommandIntent.ADMIN,
    },
    KillState.SOFTKILL: {
        CommandIntent.REDUCE, CommandIntent.CLOSE, CommandIntent.CANCEL,
        CommandIntent.MODIFY_STOP, CommandIntent.MARKET_DATA,
        CommandIntent.ACCOUNT, CommandIntent.ADMIN,
    },
    KillState.HARDKILL: {
        # HardKill only allows the auto-flatten/cancel sequence + admin
        CommandIntent.CLOSE, CommandIntent.CANCEL, CommandIntent.ADMIN,
        CommandIntent.ACCOUNT,
    },
    KillState.FAILSAFE_FREEZE: {
        # Freeze: no new orders, but allow cancel and close (for auto-exit)
        CommandIntent.CLOSE, CommandIntent.CANCEL, CommandIntent.MODIFY_STOP,
        CommandIntent.MARKET_DATA, CommandIntent.ACCOUNT, CommandIntent.ADMIN,
    },
    KillState.LOCKOUT: {
        # Nothing except admin (for reset) and account queries
        CommandIntent.ADMIN, CommandIntent.ACCOUNT,
    },
}

# Valid state transitions
_VALID_TRANSITIONS: Dict[KillState, set] = {
    KillState.NORMAL: {KillState.SOFTKILL, KillState.HARDKILL, KillState.FAILSAFE_FREEZE},
    KillState.SOFTKILL: {KillState.NORMAL, KillState.HARDKILL, KillState.FAILSAFE_FREEZE},
    KillState.HARDKILL: {KillState.LOCKOUT},
    KillState.FAILSAFE_FREEZE: {KillState.NORMAL, KillState.HARDKILL},
    KillState.LOCKOUT: {KillState.NORMAL},  # Only via human reset
}


@dataclass
class KillStateChange:
    """Record of a kill state transition."""
    from_state: KillState
    to_state: KillState
    reason: str
    timestamp: datetime
    source: str  # "exec", "failsafe", "human", "system"


class KillManager:
    """
    Kill State Machine for PA r2.
    
    Thread-safe state machine that controls which commands PA accepts.
    Emits state change events for journal/telemetry.
    """
    
    def __init__(
        self,
        on_state_changed: Optional[Callable[[KillStateChange], None]] = None,
        on_hardkill_triggered: Optional[Callable[[], None]] = None,
        lockout_requires_human: bool = True,
    ):
        """
        Args:
            on_state_changed: Callback fired on every state transition
            on_hardkill_triggered: Callback to execute hardkill sequence (cancel all + flatten)
            lockout_requires_human: If True, LOCKOUT can only be reset by human
        """
        self._state = KillState.NORMAL
        self._lock = threading.Lock()
        self._history: List[KillStateChange] = []
        self._on_state_changed = on_state_changed
        self._on_hardkill_triggered = on_hardkill_triggered
        self._lockout_requires_human = lockout_requires_human
        self._lockout_reset_key: Optional[str] = None
        
        logger.info("KillManager initialized — state=NORMAL")
    
    @property
    def state(self) -> KillState:
        """Current kill state (thread-safe read)."""
        with self._lock:
            return self._state
    
    @property
    def history(self) -> List[KillStateChange]:
        """History of state changes."""
        with self._lock:
            return list(self._history)
    
    def is_command_allowed(self, intent: CommandIntent) -> bool:
        """
        Check if a command with the given intent is allowed in current state.
        
        Args:
            intent: The intent classification of the command
            
        Returns:
            True if the command is allowed
        """
        with self._lock:
            allowed = intent in _ALLOWED_INTENTS.get(self._state, set())
            if not allowed:
                logger.warning(
                    f"Command blocked: intent={intent.value} "
                    f"not allowed in state={self._state.value}"
                )
            return allowed
    
    def set_softkill(self, reason: str = "", source: str = "exec") -> bool:
        """
        Activate SoftKill — blocks OPEN/ADD, allows REDUCE/CLOSE/CANCEL.
        
        Args:
            reason: Why SoftKill was activated
            source: Who triggered it ("exec", "system")
        
        Returns:
            True if transition succeeded
        """
        return self._transition(KillState.SOFTKILL, reason, source)
    
    def hardkill(self, reason: str = "", source: str = "exec") -> bool:
        """
        Activate HardKill — cancel all orders, flatten all positions, then LOCKOUT.
        
        The actual cancel/flatten is done by the callback. KillManager
        only manages the state transition.
        
        Args:
            reason: Why HardKill was activated
            source: Who triggered it
            
        Returns:
            True if transition succeeded
        """
        success = self._transition(KillState.HARDKILL, reason, source)
        if success and self._on_hardkill_triggered:
            try:
                self._on_hardkill_triggered()
            except Exception as e:
                logger.error(f"Error in hardkill callback: {e}")
            # After hardkill sequence, transition to LOCKOUT
            self._transition(KillState.LOCKOUT, "HardKill sequence complete", "system")
        return success
    
    def set_failsafe_freeze(self, reason: str = "", source: str = "failsafe") -> bool:
        """
        Activate Failsafe Freeze — no new orders, existing orders remain.
        
        Args:
            reason: Why freeze was activated
            source: Who triggered it
            
        Returns:
            True if transition succeeded
        """
        return self._transition(KillState.FAILSAFE_FREEZE, reason, source)
    
    def resume_normal(self, reason: str = "", source: str = "exec", 
                      reset_key: Optional[str] = None) -> bool:
        """
        Return to NORMAL state.
        
        If current state is LOCKOUT and lockout_requires_human is True,
        a reset_key must be provided.
        
        Args:
            reason: Why resuming normal
            source: Who triggered it
            reset_key: Required if resetting from LOCKOUT
            
        Returns:
            True if transition succeeded
        """
        with self._lock:
            if self._state == KillState.LOCKOUT and self._lockout_requires_human:
                if source != "human":
                    logger.error("LOCKOUT reset requires source='human'")
                    return False
                if self._lockout_reset_key and reset_key != self._lockout_reset_key:
                    logger.error("Invalid LOCKOUT reset key")
                    return False
        
        return self._transition(KillState.NORMAL, reason, source)
    
    def set_lockout(self, reason: str = "", source: str = "system") -> bool:
        """
        Force LOCKOUT state — everything blocked until human reset.
        
        Args:
            reason: Why lockout was activated
            source: Who triggered it
            
        Returns:
            True if transition succeeded
        """
        # Direct lockout from any state
        with self._lock:
            old_state = self._state
            self._state = KillState.LOCKOUT
            change = KillStateChange(
                from_state=old_state,
                to_state=KillState.LOCKOUT,
                reason=reason,
                timestamp=datetime.now(),
                source=source,
            )
            self._history.append(change)
            logger.critical(f"LOCKOUT activated: {reason} (from {old_state.value})")
        
        if self._on_state_changed:
            try:
                self._on_state_changed(change)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")
        return True
    
    def _transition(self, target: KillState, reason: str, source: str) -> bool:
        """
        Execute a state transition if valid.
        
        Args:
            target: Target kill state
            reason: Reason for transition
            source: Who triggered it
            
        Returns:
            True if transition succeeded
        """
        with self._lock:
            current = self._state
            
            if target == current:
                logger.debug(f"Already in state {current.value}")
                return True
            
            valid = _VALID_TRANSITIONS.get(current, set())
            if target not in valid:
                logger.error(
                    f"Invalid kill state transition: {current.value} → {target.value}. "
                    f"Valid targets: {[s.value for s in valid]}"
                )
                return False
            
            self._state = target
            change = KillStateChange(
                from_state=current,
                to_state=target,
                reason=reason,
                timestamp=datetime.now(),
                source=source,
            )
            self._history.append(change)
            
            logger.warning(
                f"Kill state: {current.value} → {target.value} "
                f"(reason={reason}, source={source})"
            )
        
        # Fire callback outside lock
        if self._on_state_changed:
            try:
                self._on_state_changed(change)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")
        
        return True
    
    def get_status(self) -> dict:
        """Get current kill manager status."""
        with self._lock:
            return {
                "state": self._state.value,
                "transition_count": len(self._history),
                "last_change": self._history[-1] if self._history else None,
            }
    
    def __repr__(self) -> str:
        return f"KillManager(state={self._state.value})"
