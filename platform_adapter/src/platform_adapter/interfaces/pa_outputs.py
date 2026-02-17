"""
PA Output Contracts — facts PA streams to downstream consumers.

PA 2.0 rule: PA only emits broker FACTS. Zero derived math, zero strategy.
Every event is an immutable snapshot of what the broker told us.

PA r2 additions: KillStateEvent, FailsafeEvent, PacingEvent, ReconciliationEvent

Consumers:
    - MIC (Market Intelligence Center)
    - OE (Order Execution / Strategy layer)
    - Any listener registered via PAOutputStream
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol


# ============================================================================
# ENUMS
# ============================================================================

class ConnectionStatus(str, Enum):
    """Broker connection status."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class OrderStatusValue(str, Enum):
    """Order status values (mirrors IB API)."""
    PENDING_SUBMIT = "PendingSubmit"
    PENDING_CANCEL = "PendingCancel"
    PRE_SUBMITTED = "PreSubmitted"
    SUBMITTED = "Submitted"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    INACTIVE = "Inactive"
    API_CANCELLED = "ApiCancelled"


# ============================================================================
# OUTPUT EVENTS — immutable broker facts
# ============================================================================

@dataclass(frozen=True)
class QuoteEvent:
    """
    Real-time quote from broker.

    Fields:
        symbol:    str   — instrument symbol (e.g. "AAPL", "ES")          REQUIRED
        timestamp: datetime — when broker emitted this tick               REQUIRED
        bid:       float | None — best bid price
        ask:       float | None — best ask price
        bid_size:  int   | None — bid depth
        ask_size:  int   | None — ask depth
        last:      float | None — last trade price
        last_size: int   | None — last trade size
        volume:    int   | None — session volume
    """
    symbol: str
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None
    last: Optional[float] = None
    last_size: Optional[int] = None
    volume: Optional[int] = None


@dataclass(frozen=True)
class BarEvent:
    """
    Historical OHLCV bar from broker.

    Fields:
        symbol:    str      — instrument symbol                            REQUIRED
        timestamp: datetime — bar open time                                REQUIRED
        open:      float    — open price                                   REQUIRED
        high:      float    — high price                                   REQUIRED
        low:       float    — low price                                    REQUIRED
        close:     float    — close price                                  REQUIRED
        volume:    int      — bar volume                                   REQUIRED
        count:     int      — trade count in bar (0 if unavailable)
        wap:       float    — weighted avg price (0.0 if unavailable)
    """
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    count: int = 0
    wap: float = 0.0


@dataclass(frozen=True)
class OrderUpdateEvent:
    """
    Order status update from broker.

    Fields:
        order_id:       int    — PA-assigned order ID                      REQUIRED
        symbol:         str    — instrument symbol                         REQUIRED
        status:         str    — current status (OrderStatusValue)         REQUIRED
        action:         str    — "BUY" or "SELL"                           REQUIRED
        quantity:       int    — total order quantity                       REQUIRED
        order_type:     str    — "MKT", "LMT", "STP", "STP LMT"          REQUIRED
        filled:         int    — shares filled so far                      REQUIRED
        remaining:      int    — shares remaining                          REQUIRED
        avg_fill_price: float  — average fill price                        REQUIRED
        limit_price:    float | None — limit price if applicable
        stop_price:     float | None — stop price if applicable
        timestamp:      datetime — when this update was received           REQUIRED
    """
    order_id: int
    symbol: str
    status: str
    action: str
    quantity: int
    order_type: str
    filled: int
    remaining: int
    avg_fill_price: float
    timestamp: datetime
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None


@dataclass(frozen=True)
class FillEvent:
    """
    Execution / fill report from broker.

    Fields:
        order_id:   int      — PA order ID this fill belongs to            REQUIRED
        exec_id:    str      — broker execution ID (unique)                REQUIRED
        symbol:     str      — instrument symbol                           REQUIRED
        side:       str      — "BOT" or "SLD"                              REQUIRED
        shares:     int      — shares in this fill                         REQUIRED
        price:      float    — execution price                             REQUIRED
        commission: float    — commission charged (0.0 if unknown yet)
        timestamp:  datetime — execution timestamp                         REQUIRED
    """
    order_id: int
    exec_id: str
    symbol: str
    side: str
    shares: int
    price: float
    timestamp: datetime
    commission: float = 0.0


@dataclass(frozen=True)
class PositionEvent:
    """
    Position snapshot from broker.

    Fields:
        symbol:    str   — instrument symbol                               REQUIRED
        quantity:  int   — signed quantity (+ long, − short, 0 flat)       REQUIRED
        avg_cost:  float — average cost per unit                           REQUIRED
        account:   str   — broker account ID                               REQUIRED
        sec_type:  str   — security type ("STK", "FUT", "OPT", …)
        exchange:  str   — exchange
        currency:  str   — currency code
    """
    symbol: str
    quantity: int
    avg_cost: float
    account: str
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"


@dataclass(frozen=True)
class AccountValueEvent:
    """
    Account value update from broker.

    Fields:
        key:      str — value key (e.g. "NetLiquidation")                  REQUIRED
        value:    str — value as string (broker sends strings)             REQUIRED
        currency: str — currency code                                      REQUIRED
        account:  str — broker account ID                                  REQUIRED
    """
    key: str
    value: str
    currency: str
    account: str


@dataclass(frozen=True)
class ConnectionEvent:
    """
    Connection lifecycle event.

    Fields:
        status:  ConnectionStatus — current status                         REQUIRED
        message: str — human-readable description
    """
    status: ConnectionStatus
    message: str = ""


# ============================================================================
# PA r2 — NEW EVENTS
# ============================================================================

@dataclass(frozen=True)
class KillStateEvent:
    """
    Kill state change event.

    Fields:
        from_state: str — previous kill state
        to_state:   str — new kill state
        reason:     str — why the transition happened
        source:     str — who triggered it ("exec", "failsafe", "human", "system")
        timestamp:  datetime
    """
    from_state: str
    to_state: str
    reason: str
    source: str
    timestamp: datetime


@dataclass(frozen=True)
class FailsafeStageEvent:
    """
    Failsafe heartbeat monitor stage change.

    Fields:
        stage:                   int — 0=NORMAL, 1=WARN, 2=FREEZE, 3=FLATTEN
        seconds_since_heartbeat: float
        message:                 str
        timestamp:               datetime
    """
    stage: int
    seconds_since_heartbeat: float
    message: str
    timestamp: datetime


@dataclass(frozen=True)
class PacingStateEvent:
    """
    Pacing recovery state change.

    Fields:
        in_recovery:     bool
        error_code:      int — IB error code that triggered recovery (0 if ending)
        cooldown_sec:    float — current cooldown period
        violation_count: int — consecutive violations
        message:         str
        timestamp:       datetime
    """
    in_recovery: bool
    error_code: int
    cooldown_sec: float
    violation_count: int
    message: str
    timestamp: datetime


@dataclass(frozen=True)
class ReconciliationReportEvent:
    """
    Reconciliation completed event.

    Fields:
        success:             bool
        duration_sec:        float
        positions_broker:    int
        positions_local:     int
        orders_broker:       int
        orders_local:        int
        orders_orphaned:     int
        positions_mismatches: int
        actions_taken:       list
        message:             str
        timestamp:           datetime
    """
    success: bool
    duration_sec: float
    positions_broker: int
    positions_local: int
    orders_broker: int
    orders_local: int
    orders_orphaned: int
    positions_mismatches: int
    actions_taken: List[str]
    message: str
    timestamp: datetime


# ============================================================================
# OUTPUT STREAM — callback registry for downstream consumers
# ============================================================================

class PAOutputStream:
    """
    Registry for downstream listeners.

    Consumers (MIC, OE, etc.) register callbacks here.
    PA fires events through this stream — never holds state.

    Usage:
        stream = PAOutputStream()
        stream.on_quote(my_quote_handler)
        stream.on_fill(my_fill_handler)
        # PA internally calls:
        stream.emit_quote(QuoteEvent(...))
    """

    def __init__(self):
        self._quote_listeners: List[Callable[[QuoteEvent], None]] = []
        self._bar_listeners: List[Callable[[BarEvent], None]] = []
        self._order_update_listeners: List[Callable[[OrderUpdateEvent], None]] = []
        self._fill_listeners: List[Callable[[FillEvent], None]] = []
        self._position_listeners: List[Callable[[PositionEvent], None]] = []
        self._account_value_listeners: List[Callable[[AccountValueEvent], None]] = []
        self._connection_listeners: List[Callable[[ConnectionEvent], None]] = []
        # PA r2 listeners
        self._kill_state_listeners: List[Callable[[KillStateEvent], None]] = []
        self._failsafe_listeners: List[Callable[[FailsafeStageEvent], None]] = []
        self._pacing_listeners: List[Callable[[PacingStateEvent], None]] = []
        self._reconciliation_listeners: List[Callable[[ReconciliationReportEvent], None]] = []

    # ---- registration ----

    def on_quote(self, cb: Callable[[QuoteEvent], None]) -> None:
        self._quote_listeners.append(cb)

    def on_bar(self, cb: Callable[[BarEvent], None]) -> None:
        self._bar_listeners.append(cb)

    def on_order_update(self, cb: Callable[[OrderUpdateEvent], None]) -> None:
        self._order_update_listeners.append(cb)

    def on_fill(self, cb: Callable[[FillEvent], None]) -> None:
        self._fill_listeners.append(cb)

    def on_position(self, cb: Callable[[PositionEvent], None]) -> None:
        self._position_listeners.append(cb)

    def on_account_value(self, cb: Callable[[AccountValueEvent], None]) -> None:
        self._account_value_listeners.append(cb)

    def on_connection(self, cb: Callable[[ConnectionEvent], None]) -> None:
        self._connection_listeners.append(cb)

    # PA r2 registrations
    def on_kill_state(self, cb: Callable[[KillStateEvent], None]) -> None:
        self._kill_state_listeners.append(cb)

    def on_failsafe(self, cb: Callable[[FailsafeStageEvent], None]) -> None:
        self._failsafe_listeners.append(cb)

    def on_pacing(self, cb: Callable[[PacingStateEvent], None]) -> None:
        self._pacing_listeners.append(cb)

    def on_reconciliation(self, cb: Callable[[ReconciliationReportEvent], None]) -> None:
        self._reconciliation_listeners.append(cb)

    # ---- emission (PA calls these) ----

    def emit_quote(self, event: QuoteEvent) -> None:
        for cb in self._quote_listeners:
            try:
                cb(event)
            except Exception:
                pass  # PA never crashes for downstream errors

    def emit_bar(self, event: BarEvent) -> None:
        for cb in self._bar_listeners:
            try:
                cb(event)
            except Exception:
                pass

    def emit_order_update(self, event: OrderUpdateEvent) -> None:
        for cb in self._order_update_listeners:
            try:
                cb(event)
            except Exception:
                pass

    def emit_fill(self, event: FillEvent) -> None:
        for cb in self._fill_listeners:
            try:
                cb(event)
            except Exception:
                pass

    def emit_position(self, event: PositionEvent) -> None:
        for cb in self._position_listeners:
            try:
                cb(event)
            except Exception:
                pass

    def emit_account_value(self, event: AccountValueEvent) -> None:
        for cb in self._account_value_listeners:
            try:
                cb(event)
            except Exception:
                pass

    def emit_connection(self, event: ConnectionEvent) -> None:
        for cb in self._connection_listeners:
            try:
                cb(event)
            except Exception:
                pass

    # PA r2 emissions
    def emit_kill_state(self, event: KillStateEvent) -> None:
        for cb in self._kill_state_listeners:
            try:
                cb(event)
            except Exception:
                pass

    def emit_failsafe(self, event: FailsafeStageEvent) -> None:
        for cb in self._failsafe_listeners:
            try:
                cb(event)
            except Exception:
                pass

    def emit_pacing(self, event: PacingStateEvent) -> None:
        for cb in self._pacing_listeners:
            try:
                cb(event)
            except Exception:
                pass

    def emit_reconciliation(self, event: ReconciliationReportEvent) -> None:
        for cb in self._reconciliation_listeners:
            try:
                cb(event)
            except Exception:
                pass
