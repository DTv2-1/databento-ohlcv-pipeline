"""
PAr2 Models — PACommand + PAEvent wire contract shapes
======================================================
Wire contract version: PAWire.v0

Source: sniperZero-devBundle/6-PAr2 WireContract v0 Template 2026-03-02.md

Rules:
- PACommand: inbound from Dispatcher only. Intent, not truth.
- PAEvent:   outbound from PAr2 only. IB-derived execution truth.
- All events must include event_id, ts_utc_ms, trading_mode, type.
- All lifecycle events derived from a PACommand must carry command_id.
"""

from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class TradingMode(str, Enum):
    LIVE  = "LIVE"
    PAPER = "PAPER"


class Channel(str, Enum):
    ORDER_PLACE      = "order_place"
    ORDER_MODIFY     = "order_modify"
    ORDER_CANCEL     = "order_cancel"
    MARKET_DATA      = "market_data_subscribe"
    MISC             = "misc"


class Priority(str, Enum):
    EXIT   = "EXIT"
    NORMAL = "NORMAL"


class Action(str, Enum):
    PLACE  = "PLACE"
    MODIFY = "MODIFY"
    CANCEL = "CANCEL"


class IntentType(str, Enum):
    OPEN        = "OPEN"
    ADD         = "ADD"
    CLOSE       = "CLOSE"
    FLATTEN     = "FLATTEN"
    PLACE_STOP  = "PLACE_STOP"
    MODIFY_STOP = "MODIFY_STOP"
    SOFTKILL    = "SOFTKILL"
    HARDKILL    = "HARDKILL"
    CANCEL      = "CANCEL"


class KillState(str, Enum):
    """Runtime safety states — enforced at PAr2 boundary."""
    NORMAL           = "NORMAL"
    SOFTKILL         = "SOFTKILL"
    FAILSAFE_FREEZE  = "FAILSAFE_FREEZE"
    FAILSAFE_AUTOEXIT = "FAILSAFE_AUTOEXIT"
    HARDKILL         = "HARDKILL"
    LOCKOUT          = "LOCKOUT"


# Alias used in PipelineContext.exec.kill_state
SafetyState = KillState


class PAEventType(str, Enum):
    # Market feed
    MARKET_BAR              = "MARKET_BAR"

    # Order lifecycle
    ORDER_SUBMITTED         = "ORDER_SUBMITTED"
    ORDER_ACCEPTED          = "ORDER_ACCEPTED"
    ORDER_REJECTED          = "ORDER_REJECTED"
    ORDER_STATUS            = "ORDER_STATUS"
    ORDER_CANCELLED         = "ORDER_CANCELLED"
    FILL                    = "FILL"

    # Position / account truth
    POSITION_SNAPSHOT       = "POSITION_SNAPSHOT"
    ACCOUNT_SNAPSHOT        = "ACCOUNT_SNAPSHOT"

    # Reconciliation
    RECONCILIATION_REPORT   = "RECONCILIATION_REPORT"

    # Pacing
    PACING_WARNING          = "PACING_WARNING"
    PACING_COOLDOWN_STARTED = "PACING_COOLDOWN_STARTED"
    PACING_COOLDOWN_ENDED   = "PACING_COOLDOWN_ENDED"

    # Kill / failsafe
    SOFTKILL_ENABLED        = "SOFTKILL_ENABLED"
    SOFTKILL_DISABLED       = "SOFTKILL_DISABLED"
    FAILSAFE_STAGE_CHANGED  = "FAILSAFE_STAGE_CHANGED"
    HARDKILL_EXECUTED       = "HARDKILL_EXECUTED"
    LOCKOUT_ENABLED         = "LOCKOUT_ENABLED"
    LOCKOUT_DISABLED        = "LOCKOUT_DISABLED"

    # Connection
    CONNECTION_UP           = "CONNECTION_UP"
    CONNECTION_DOWN         = "CONNECTION_DOWN"

    # Command rejected by PAr2 (safety enforcement)
    COMMAND_REJECTED        = "COMMAND_REJECTED"


# ─────────────────────────────────────────────────────────────────────────────
# PACommand — inbound from Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OrderConstraints:
    tighten_only: bool = False


@dataclass
class PACommand:
    """
    Inbound command envelope from Dispatcher → PAr2.

    LAW: Commands are intent only — not execution truth.
    Truth comes back as PAEvents from IB.

    Wire contract: PAWire.v0
    """
    command_id:   str
    ts_utc_ms:    int
    trading_mode: TradingMode
    symbol:       str
    channel:      Channel
    priority:     Priority
    action:       Action
    intent_type:  IntentType
    order_spec:   dict[str, Any]
    constraints:  OrderConstraints = field(default_factory=OrderConstraints)

    @staticmethod
    def make_id() -> str:
        return f"cmd_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def now_ms() -> int:
        return int(time.time() * 1000)

    def is_exit(self) -> bool:
        return self.priority == Priority.EXIT

    def is_open_or_add(self) -> bool:
        return self.intent_type in (IntentType.OPEN, IntentType.ADD)

    def to_dict(self) -> dict:
        return {
            "command_id":   self.command_id,
            "ts_utc_ms":    self.ts_utc_ms,
            "trading_mode": self.trading_mode.value,
            "symbol":       self.symbol,
            "channel":      self.channel.value,
            "priority":     self.priority.value,
            "action":       self.action.value,
            "intent_type":  self.intent_type.value,
            "constraints":  {"tighten_only": self.constraints.tighten_only},
            "order_spec":   self.order_spec,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PAEvent — outbound from PAr2 (IB-derived execution truth)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PAEvent:
    """
    Outbound event envelope from PAr2 → PipelineContext.exec + JournalDB.

    LAW: PAEvents are execution truth — derived from IB callbacks or PAr2
    internal safety enforcement. Downstream modules must act on these,
    never on commands alone.

    Wire contract: PAWire.v0
    """
    type:         PAEventType
    payload:      dict[str, Any]
    symbol:       Optional[str] = None
    trading_mode: TradingMode   = TradingMode.PAPER
    event_id:     str           = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    ts_utc_ms:    int           = field(default_factory=lambda: int(time.time() * 1000))
    session_id:   Optional[str] = None
    cycle_id:     Optional[int] = None

    # Wire contract version tag
    wire_version: str = "PAWire.v0"

    def to_dict(self) -> dict:
        return {
            "event_id":     self.event_id,
            "ts_utc_ms":    self.ts_utc_ms,
            "trading_mode": self.trading_mode.value,
            "type":         self.type.value,
            "symbol":       self.symbol,
            "payload":      self.payload,
            "session_id":   self.session_id,
            "cycle_id":     self.cycle_id,
            "wire_version": self.wire_version,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Event factory helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_order_rejected_event(
    command_id: str,
    symbol: str,
    ib_error_code: int,
    message: str,
    trading_mode: TradingMode = TradingMode.PAPER,
    broker_order_id: Optional[int] = None,
) -> PAEvent:
    return PAEvent(
        type=PAEventType.ORDER_REJECTED,
        symbol=symbol,
        trading_mode=trading_mode,
        payload={
            "command_id":      command_id,
            "broker_order_id": broker_order_id,
            "ib_error_code":   ib_error_code,
            "message":         message,
        },
    )


def make_command_rejected_event(
    command: PACommand,
    reason: str,
    kill_state: KillState,
) -> PAEvent:
    return PAEvent(
        type=PAEventType.COMMAND_REJECTED,
        symbol=command.symbol,
        trading_mode=command.trading_mode,
        payload={
            "command_id": command.command_id,
            "intent_type": command.intent_type.value,
            "reason":      reason,
            "kill_state":  kill_state.value,
        },
    )


def make_kill_event(
    event_type: PAEventType,
    kill_state: KillState,
    reason: str,
    trading_mode: TradingMode = TradingMode.PAPER,
) -> PAEvent:
    return PAEvent(
        type=event_type,
        trading_mode=trading_mode,
        payload={
            "kill_state": kill_state.value,
            "reason":     reason,
        },
    )


def make_connection_event(
    up: bool,
    trading_mode: TradingMode = TradingMode.PAPER,
    details: Optional[dict] = None,
) -> PAEvent:
    return PAEvent(
        type=PAEventType.CONNECTION_UP if up else PAEventType.CONNECTION_DOWN,
        trading_mode=trading_mode,
        payload=details or {},
    )
