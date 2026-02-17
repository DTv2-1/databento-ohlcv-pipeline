"""
PA Input Contracts — commands PA accepts from the Order Execution layer.

PA 2.0 rule: PA receives commands ONLY from OE. No strategy, no decisions.
PA validates the command shape, translates to broker API, and sends.

PA r2 additions: SoftKillCommand, HardKillCommand, HeartbeatCommand,
                 SetFailsafePolicyCommand, ReconcileCommand, SetLockoutCommand,
                 SwitchModeCommand

Producers:
    - OE (Order Execution / Strategy layer) — the ONLY command source
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Literal, Optional, Protocol


# ============================================================================
# COMMAND DATACLASSES — what OE sends to PA
# ============================================================================

@dataclass(frozen=True)
class PlaceOrderCommand:
    """
    Place a new order.

    Fields:
        symbol:        str   — instrument symbol                           REQUIRED
        action:        str   — "BUY" or "SELL"                             REQUIRED
        quantity:      int   — number of shares/contracts                  REQUIRED
        order_type:    str   — "MKT", "LMT", "STP", "STP LMT"            REQUIRED
        limit_price:   float | None — required for LMT / STP LMT
        stop_price:    float | None — required for STP / STP LMT
        sec_type:      str   — security type (default "STK")
        exchange:      str   — exchange (default "SMART")
        currency:      str   — currency (default "USD")
        tif:           str   — time-in-force (default "DAY")
        outside_rth:   bool  — allow outside regular hours

    Validation:
        - action must be "BUY" or "SELL"
        - quantity must be > 0
        - LMT / STP LMT requires limit_price
        - STP / STP LMT requires stop_price
    """
    symbol: str
    action: str
    quantity: int
    order_type: str = "MKT"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"
    tif: str = "DAY"
    outside_rth: bool = False

    def __post_init__(self):
        if self.action not in ("BUY", "SELL"):
            raise ValueError(f"Invalid action: {self.action}. Must be BUY or SELL")
        if self.quantity <= 0:
            raise ValueError(f"Invalid quantity: {self.quantity}. Must be > 0")
        if self.order_type in ("LMT", "STP LMT") and self.limit_price is None:
            raise ValueError(f"{self.order_type} requires limit_price")
        if self.order_type in ("STP", "STP LMT") and self.stop_price is None:
            raise ValueError(f"{self.order_type} requires stop_price")


@dataclass(frozen=True)
class CancelOrderCommand:
    """
    Cancel an existing order.

    Fields:
        order_id: int — PA order ID to cancel                             REQUIRED
    """
    order_id: int


@dataclass(frozen=True)
class ModifyOrderCommand:
    """
    Modify an existing order. At least one of quantity/limit_price/stop_price required.

    Fields:
        order_id:    int        — PA order ID to modify                    REQUIRED
        quantity:    int | None — new quantity
        limit_price: float | None — new limit price
        stop_price:  float | None — new stop price
    """
    order_id: int
    quantity: Optional[int] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None

    def __post_init__(self):
        if self.quantity is None and self.limit_price is None and self.stop_price is None:
            raise ValueError("ModifyOrderCommand requires at least one field to change")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError(f"Invalid quantity: {self.quantity}. Must be > 0")


@dataclass(frozen=True)
class FlattenCommand:
    """
    Close all positions for a symbol (market order to flatten).

    Fields:
        symbol:   str — instrument to flatten                              REQUIRED
        sec_type: str — security type (default "STK")
        exchange: str — exchange (default "SMART")
        currency: str — currency (default "USD")
    """
    symbol: str
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"


@dataclass(frozen=True)
class SubscribeMarketDataCommand:
    """
    Subscribe to real-time market data for a symbol.

    Fields:
        symbol:   str  — instrument symbol                                 REQUIRED
        sec_type: str  — security type (default "STK")
        exchange: str  — exchange (default "SMART")
        currency: str  — currency (default "USD")
        snapshot: bool — one-time snapshot vs streaming
    """
    symbol: str
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"
    snapshot: bool = False


@dataclass(frozen=True)
class UnsubscribeMarketDataCommand:
    """
    Unsubscribe from real-time market data.

    Fields:
        symbol: str — instrument symbol to unsubscribe                     REQUIRED
    """
    symbol: str


@dataclass(frozen=True)
class HistoricalDataCommand:
    """
    Request historical bars.

    Fields:
        symbol:       str — instrument symbol                              REQUIRED
        duration:     str — IB duration string (e.g. "1 D", "1 W")        REQUIRED
        bar_size:     str — IB bar size (e.g. "1 min", "5 mins")          REQUIRED
        what_to_show: str — data type ("TRADES", "MIDPOINT", "BID", …)
        use_rth:      bool — regular trading hours only
        end_datetime: str — end time (empty = now)
        sec_type:     str — security type
        exchange:     str — exchange
        currency:     str — currency
    """
    symbol: str
    duration: str = "1 D"
    bar_size: str = "1 min"
    what_to_show: str = "TRADES"
    use_rth: bool = True
    end_datetime: str = ""
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"


# ============================================================================
# PA r2 — NEW COMMANDS
# ============================================================================

@dataclass(frozen=True)
class SoftKillCommand:
    """
    Activate SoftKill — blocks OPEN/ADD, allows REDUCE/CLOSE/CANCEL.

    Fields:
        reason: str — why SoftKill is being activated
    """
    reason: str = ""


@dataclass(frozen=True)
class HardKillCommand:
    """
    Activate HardKill — cancel all orders, flatten all positions, then LOCKOUT.

    Fields:
        reason: str — why HardKill is being activated
    """
    reason: str = ""


@dataclass(frozen=True)
class ResumeNormalCommand:
    """
    Resume NORMAL state from SoftKill or FailsafeFreeze.

    Fields:
        reason: str — why resuming
    """
    reason: str = ""


@dataclass(frozen=True)
class SetLockoutCommand:
    """
    Force LOCKOUT — everything blocked until human reset.

    Fields:
        reason: str — why lockout is being set
    """
    reason: str = ""


@dataclass(frozen=True)
class HeartbeatCommand:
    """
    Exec sends this periodically to prove it's alive.
    If PA doesn't receive heartbeats, failsafe escalates.
    """
    pass


@dataclass(frozen=True)
class ReconcileCommand:
    """
    Request manual reconciliation of local state vs broker truth.
    """
    pass


@dataclass(frozen=True)
class SwitchModeCommand:
    """
    Switch between Live and Paper trading mode.
    
    Disconnects from current session, reconnects on new port.
    Full reconciliation runs after reconnect.

    Fields:
        mode: str — "live" or "paper"
    """
    mode: str  # "live" or "paper"

    def __post_init__(self):
        if self.mode not in ("live", "paper"):
            raise ValueError(f"Invalid mode: {self.mode}. Must be 'live' or 'paper'")


# ============================================================================
# INPUT STREAM — command handler protocol
# ============================================================================

class PAInputStream(Protocol):
    """
    Protocol that PA implements to accept commands from OE.

    OE calls these methods. PA translates to broker API and sends.
    PA never returns strategy data — only ack/order_id/success.

    Every method returns immediately (fire-and-forget for async broker).
    Results come back through PAOutputStream events.
    """

    def handle_place_order(self, cmd: PlaceOrderCommand) -> int:
        """Place order → returns PA order_id. Results via OrderUpdateEvent/FillEvent."""
        ...

    def handle_cancel_order(self, cmd: CancelOrderCommand) -> bool:
        """Cancel order → returns True if cancel request sent."""
        ...

    def handle_modify_order(self, cmd: ModifyOrderCommand) -> bool:
        """Modify order → returns True if modify request sent."""
        ...

    def handle_flatten(self, cmd: FlattenCommand) -> Optional[int]:
        """Flatten position → returns order_id of closing order, or None if flat."""
        ...

    def handle_subscribe_market_data(self, cmd: SubscribeMarketDataCommand) -> int:
        """Subscribe to market data → returns req_id."""
        ...

    def handle_unsubscribe_market_data(self, cmd: UnsubscribeMarketDataCommand) -> None:
        """Unsubscribe from market data."""
        ...

    def handle_historical_data(self, cmd: HistoricalDataCommand) -> int:
        """Request historical data → returns req_id. Bars come via BarEvent."""
        ...

    # PA r2 methods
    def set_softkill(self, cmd: SoftKillCommand) -> bool:
        """Activate SoftKill."""
        ...

    def hardkill(self, cmd: HardKillCommand) -> bool:
        """Activate HardKill → cancel all + flatten all → LOCKOUT."""
        ...

    def resume_normal(self, cmd: ResumeNormalCommand) -> bool:
        """Resume NORMAL state."""
        ...

    def set_lockout(self, cmd: SetLockoutCommand) -> bool:
        """Force LOCKOUT."""
        ...

    def heartbeat_from_exec(self, cmd: HeartbeatCommand) -> None:
        """Exec heartbeat — resets failsafe timer."""
        ...

    def reconcile_state(self, cmd: ReconcileCommand) -> None:
        """Trigger reconciliation."""
        ...

    def switch_mode(self, cmd: SwitchModeCommand) -> bool:
        """Switch Live/Paper mode."""
        ...
