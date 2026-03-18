"""
PAr2 IB Adapter
================
Core execution boundary between SniperZero runtime and Interactive Brokers.

Wires together:
  OrderQueue        — dual-lane command queue + idempotency
  ChannelRateLimiter — token bucket per channel
  StopModifyThrottler — 75ms + min-delta enforcement
  KillStateMachine  — safety state machine
  ReconciliationRoutine — reconnect reconciliation

Public interface (only Dispatcher may call order methods):

  Connection:
    connect() / disconnect() / status()

  Market data:
    subscribe_bars(symbol, bar_size, source) / unsubscribe_bars(symbol)
    subscribe_quote(symbol) / unsubscribe_quote(symbol)

  Orders:
    send_command(cmd: PACommand) → dequeued and dispatched in drain loop
    cancel_order(order_id)

  Kills:
    set_softkill(enabled, reason) / hardkill(reason) / set_lockout(enabled, reason)

  Failsafe / heartbeat:
    heartbeat_from_dispatcher(ts)

  Reconciliation:
    reconcile_state(local_order_ids, local_symbols) → ReconciliationResult

  Events:
    register_event_handler(fn: Callable[[PAEvent], None])

LAW: Commands are not truth. Truth comes from IB callbacks and is emitted as PAEvents.
"""

from __future__ import annotations

import time
import logging
import threading
from typing import Callable, Dict, List, Optional

from .config import PAr2Config
from .models import (
    PACommand,
    PAEvent,
    PAEventType,
    KillState,
    TradingMode,
    Channel,
    Priority,
    Action,
    IntentType,
    make_kill_event,
    make_connection_event,
    make_command_rejected_event,
)
from .queue import OrderQueue
from .rate_limiter import ChannelRateLimiter
from .stop_throttler import StopModifyThrottler
from .kill_state import KillStateMachine
from .reconciliation import (
    ReconciliationRoutine,
    ReconciliationResult,
    IBOrderSnapshot,
    IBPositionSnapshot,
)

logger = logging.getLogger(__name__)


# ── IB API import (optional at import time — lazy connect) ────────────────────

try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    _IB_AVAILABLE = True
except ImportError:
    # Allow module import in environments without ibapi (e.g., testing)
    EClient = object
    EWrapper = object
    _IB_AVAILABLE = False
    logger.warning("ibapi not installed — PAr2Adapter will not connect to IB")


# ── IB contract builder helpers ───────────────────────────────────────────────

def _make_contract(symbol: str, sec_type: str = "FUT", exchange: str = "CME",
                   currency: str = "USD") -> "Contract":
    c = Contract()
    c.symbol   = symbol
    c.secType  = sec_type
    c.exchange = exchange
    c.currency = currency
    return c


def _make_equity_contract(symbol: str) -> "Contract":
    c = Contract()
    c.symbol   = symbol
    c.secType  = "STK"
    c.exchange = "SMART"
    c.currency = "USD"
    return c


def _make_forex_contract(pair: str) -> "Contract":
    """e.g. pair='EURUSD' → EUR.USD forex"""
    c = Contract()
    c.symbol   = pair[:3]
    c.secType  = "CASH"
    c.exchange = "IDEALPRO"
    c.currency = pair[3:]
    return c


# ── PAr2Adapter ───────────────────────────────────────────────────────────────

class _IBWrapper(EWrapper):
    """Thin EWrapper — callbacks routed to PAr2Adapter."""
    def __init__(self, adapter: "PAr2Adapter"):
        super().__init__()
        self._adapter = adapter


class _IBClient(EClient):
    def __init__(self, wrapper: _IBWrapper):
        super().__init__(wrapper)


class PAr2Adapter(_IBWrapper, _IBClient):
    """
    PAr2 IB Adapter — the single execution boundary.

    Instantiate once per session. One mode (LIVE or PAPER) per instance.
    """

    def __init__(self, config: Optional[PAr2Config] = None):
        self._cfg = config or PAr2Config()
        self._mode = TradingMode(self._cfg.ib.trading_mode)

        # IB client init
        wrapper = self  # self IS the wrapper (MRO)
        _IBClient.__init__(self, self)
        _IBWrapper.__init__(self, self)

        # Components
        self._event_handlers: List[Callable[[PAEvent], None]] = []

        self._rate_limiter = ChannelRateLimiter(
            sustained_per_sec=self._cfg.pacing.sustained_msgs_per_sec,
            burst_max=self._cfg.pacing.burst_msgs_per_sec,
        )

        self._kill_state = KillStateMachine(
            on_event=self._emit,
            on_flatten=self._flatten_all,
            trading_mode=self._mode,
            freeze_after_ms=self._cfg.failsafe.freeze_after_ms,
            autoexit_after_ms=self._cfg.failsafe.autoexit_after_ms,
            autoexit_implies_lockout=self._cfg.failsafe.autoexit_implies_lockout,
        )

        self._queue = OrderQueue(
            kill_state_fn=lambda: self._kill_state.state,
            on_event=self._emit,
            trading_mode=self._mode,
        )

        self._throttler = StopModifyThrottler(
            min_interval_ms=self._cfg.stop_modify.min_modify_interval_ms,
            min_delta_ticks=self._cfg.stop_modify.min_delta_ticks_or_pips,
        )

        self._reconciliation = ReconciliationRoutine(
            ib_client=self,
            on_event=self._emit,
            on_lockout=lambda reason: self._kill_state.hardkill(reason),  # lockout via hardkill path
            on_cancel_order=self._cancel_order_direct,
            on_flatten_symbol=self._flatten_symbol,
            trading_mode=self._mode,
            timeout_sec=self._cfg.reconciliation.timeout_sec,
        )

        # State
        self._connected      = False
        self._next_order_id  = 0
        self._order_id_lock  = threading.Lock()
        self._drain_thread: Optional[threading.Thread] = None
        self._running        = False

        # Active subscriptions: req_id → symbol
        self._bar_req_ids:   Dict[int, str] = {}
        self._quote_req_ids: Dict[int, str] = {}
        self._req_id_counter = 1000
        self._req_id_lock    = threading.Lock()

        # Open orders tracking (for reconciliation)
        self._open_order_ids:   List[int] = []
        self._open_symbols:     List[str] = []

        logger.info("PAr2Adapter created — mode=%s host=%s port=%d",
                    self._mode.value, self._cfg.ib.host, self._cfg.ib.port)

    # ── Event registration ────────────────────────────────────────────────────

    def register_event_handler(self, fn: Callable[[PAEvent], None]) -> None:
        self._event_handlers.append(fn)

    def _emit(self, evt: PAEvent) -> None:
        for fn in self._event_handlers:
            try:
                fn(evt)
            except Exception as exc:
                logger.error("PAr2Adapter: event handler error: %s", exc)

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> None:
        if not _IB_AVAILABLE:
            raise RuntimeError("ibapi not installed")
        logger.info("PAr2Adapter: connecting to %s:%d", self._cfg.ib.host, self._cfg.ib.port)
        super().connect(self._cfg.ib.host, self._cfg.ib.port, self._cfg.ib.client_id)

        # Start IB message loop in background
        self._ib_thread = threading.Thread(target=self.run, daemon=True, name="PAr2-IBLoop")
        self._ib_thread.start()

        # Start kill state monitor
        self._kill_state.start()

        # Start drain loop
        self._running = True
        self._drain_thread = threading.Thread(
            target=self._drain_loop, daemon=True, name="PAr2-DrainLoop"
        )
        self._drain_thread.start()

    def disconnect(self) -> None:
        self._running = False
        self._kill_state.stop()
        super().disconnect()
        logger.info("PAr2Adapter: disconnected")

    def status(self) -> dict:
        return {
            "connected":           self._connected,
            "kill_state":          self._kill_state.state.value,
            "mode":                self._mode.value,
            "host":                self._cfg.ib.host,
            "port":                self._cfg.ib.port,
            "queue_exit_size":     self._queue._exit_q.qsize(),
            "queue_normal_size":   self._queue._normal_q.qsize(),
        }

    # ── EWrapper callbacks — connection ───────────────────────────────────────

    def connectAck(self) -> None:
        self._connected = True
        logger.info("PAr2Adapter: connectAck — requesting nextValidId")

    def nextValidId(self, orderId: int) -> None:
        with self._order_id_lock:
            self._next_order_id = orderId
        logger.info("PAr2Adapter: nextValidId=%d", orderId)
        self._connected = True
        self._emit(make_connection_event(True, "nextValidId received", self._mode))

        # Auto-reconcile on (re)connect
        if self._cfg.reconciliation.run_on_reconnect:
            threading.Thread(
                target=self._run_reconciliation,
                daemon=True,
                name="PAr2-Reconcile",
            ).start()

    def connectionClosed(self) -> None:
        self._connected = False
        logger.warning("PAr2Adapter: connection closed")
        self._emit(make_connection_event(False, "connectionClosed", self._mode))

    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderReject: str = "") -> None:
        logger.error("PAr2Adapter IB error: reqId=%d code=%d msg=%s", reqId, errorCode, errorString)

        # Pacing warnings
        if errorCode in (100, 101, 102, 103, 162, 200, 201, 203):
            self._emit(PAEvent(
                type=PAEventType.PACING_WARNING,
                trading_mode=self._mode,
                payload={
                    "req_id":      reqId,
                    "error_code":  errorCode,
                    "error_msg":   errorString,
                },
            ))

        # Order rejected
        if errorCode in (201, 203, 321, 10268):
            self._emit(PAEvent(
                type=PAEventType.ORDER_REJECTED,
                trading_mode=self._mode,
                payload={
                    "req_id":     reqId,
                    "error_code": errorCode,
                    "reason":     errorString,
                },
            ))

    # ── EWrapper callbacks — orders ───────────────────────────────────────────

    def orderStatus(self, orderId: int, status: str, filled: float, remaining: float,
                    avgFillPrice: float, permId: int, parentId: int,
                    lastFillPrice: float, clientId: int, whyHeld: str, mktCapPrice: float) -> None:
        logger.debug("PAr2Adapter: orderStatus id=%d status=%s filled=%.2f", orderId, status, filled)

        event_type = {
            "Submitted":    PAEventType.ORDER_ACCEPTED,
            "PreSubmitted": PAEventType.ORDER_ACCEPTED,
            "Filled":       PAEventType.FILL,
            "Cancelled":    PAEventType.ORDER_CANCELLED,
            "Inactive":     PAEventType.ORDER_REJECTED,
        }.get(status, PAEventType.ORDER_STATUS)

        self._emit(PAEvent(
            type=event_type,
            trading_mode=self._mode,
            payload={
                "order_id":       orderId,
                "status":         status,
                "filled":         filled,
                "remaining":      remaining,
                "avg_fill_price": avgFillPrice,
                "perm_id":        permId,
            },
        ))

        if status in ("Filled",):
            self._queue.notify_position_opened("unknown")  # symbol updated via execDetails

        if status in ("Cancelled", "Inactive"):
            if orderId in self._open_order_ids:
                self._open_order_ids.remove(orderId)

    def execDetails(self, reqId: int, contract, execution) -> None:
        sym = contract.symbol
        self._emit(PAEvent(
            type=PAEventType.FILL,
            trading_mode=self._mode,
            symbol=sym,
            payload={
                "order_id":  execution.orderId,
                "symbol":    sym,
                "side":      execution.side,
                "qty":       execution.shares,
                "price":     execution.price,
                "exec_id":   execution.execId,
                "ts_utc_ms": int(time.time() * 1000),
            },
        ))

    def openOrder(self, orderId: int, contract, order, orderState) -> None:
        snap = IBOrderSnapshot(
            order_id=orderId,
            symbol=contract.symbol,
            side=order.action,
            order_type=order.orderType,
            qty=order.totalQuantity,
            filled_qty=0.0,
            status=orderState.status,
            perm_id=order.permId,
        )
        self._reconciliation.inject_open_order(snap)

    def openOrderEnd(self) -> None:
        self._reconciliation.inject_orders_end()

    def position(self, account: str, contract, position: float, avgCost: float) -> None:
        snap = IBPositionSnapshot(
            symbol=contract.symbol,
            account=account,
            position=position,
            avg_cost=avgCost,
        )
        self._reconciliation.inject_position(snap)

    def positionEnd(self) -> None:
        self._reconciliation.inject_positions_end()

    # ── Market data subscription ──────────────────────────────────────────────

    def subscribe_bars(self, symbol: str, bar_size: str = "5 secs",
                       source: str = "TRADES") -> int:
        req_id = self._next_req_id()
        contract = _make_equity_contract(symbol)
        self._rate_limiter.acquire(Channel.MARKET_DATA_SUBSCRIBE, Priority.NORMAL, block=True)
        self.reqRealTimeBars(req_id, contract, 5, source, False, [])
        self._bar_req_ids[req_id] = symbol
        logger.info("PAr2Adapter: subscribe_bars %s req_id=%d", symbol, req_id)
        return req_id

    def unsubscribe_bars(self, symbol: str) -> None:
        for req_id, sym in list(self._bar_req_ids.items()):
            if sym == symbol:
                self.cancelRealTimeBars(req_id)
                del self._bar_req_ids[req_id]
                logger.info("PAr2Adapter: unsubscribe_bars %s req_id=%d", symbol, req_id)

    def subscribe_quote(self, symbol: str) -> int:
        req_id = self._next_req_id()
        contract = _make_equity_contract(symbol)
        self._rate_limiter.acquire(Channel.MARKET_DATA_SUBSCRIBE, Priority.NORMAL, block=True)
        self.reqMktData(req_id, contract, "", False, False, [])
        self._quote_req_ids[req_id] = symbol
        logger.info("PAr2Adapter: subscribe_quote %s req_id=%d", symbol, req_id)
        return req_id

    def unsubscribe_quote(self, symbol: str) -> None:
        for req_id, sym in list(self._quote_req_ids.items()):
            if sym == symbol:
                self.cancelMktData(req_id)
                del self._quote_req_ids[req_id]

    def realtimeBar(self, reqId: int, time_: int, open_: float, high: float,
                    low: float, close: float, volume: int, wap: float, count: int) -> None:
        symbol = self._bar_req_ids.get(reqId, "UNKNOWN")
        self._emit(PAEvent(
            type=PAEventType.MARKET_BAR,
            trading_mode=self._mode,
            symbol=symbol,
            payload={
                "ts_utc_ms": time_ * 1000,
                "open":      open_,
                "high":      high,
                "low":       low,
                "close":     close,
                "volume":    volume,
                "wap":       wap,
                "bar_size":  "5s",
            },
        ))

    # ── Command ingestion (from Dispatcher) ───────────────────────────────────

    def send_command(self, cmd: PACommand) -> None:
        """Enqueue a PACommand for execution. Non-blocking. Thread-safe."""
        self._queue.enqueue(cmd)

    # ── Kill controls ─────────────────────────────────────────────────────────

    def set_softkill(self, enabled: bool, reason: str = "") -> None:
        self._kill_state.set_softkill(enabled, reason)
        # Queue reads kill state dynamically via lambda — no setter needed

    def hardkill(self, reason: str = "OPERATOR_HARDKILL") -> None:
        self._kill_state.hardkill(reason)

    def set_lockout(self, enabled: bool, reason: str = "") -> None:
        if enabled:
            self._kill_state.hardkill(reason or "OPERATOR_LOCKOUT")
        else:
            self._kill_state.reset_lockout(reason)

    def heartbeat_from_dispatcher(self, ts: Optional[float] = None) -> None:
        self._kill_state.heartbeat(ts)

    # ── Reconciliation ────────────────────────────────────────────────────────

    def reconcile_state(
        self,
        local_order_ids: Optional[List[int]] = None,
        local_symbols:   Optional[List[str]]  = None,
    ) -> ReconciliationResult:
        return self._reconciliation.run_sync(
            local_order_ids=local_order_ids or self._open_order_ids,
            local_symbols=local_symbols or self._open_symbols,
        )

    # ── Drain loop ────────────────────────────────────────────────────────────

    def _drain_loop(self) -> None:
        """
        Polls queue + flushes stop throttler. Runs every drain_interval_ms.
        Dispatches PACommand objects to IB.
        """
        interval = self._cfg.drain_interval_ms / 1000.0
        logger.info("PAr2Adapter: drain loop started (interval=%.0fms)", self._cfg.drain_interval_ms)

        while self._running:
            try:
                # 1. Flush pending stop-modify merges
                for merged_cmd in self._throttler.flush_due():
                    self._dispatch_command(merged_cmd)

                # 2. Drain command queue (one per cycle to keep loop responsive)
                cmd = self._queue.dequeue(block=False)
                if cmd is not None:
                    if cmd.action == Action.MODIFY and cmd.intent_type in (
                        IntentType.MODIFY_STOP,
                    ):
                        # Route through stop throttler
                        result = self._throttler.submit(
                            cmd=cmd,
                            current_stop_price=cmd.order_spec.get("stop_price", 0.0),
                            tick_size=cmd.order_spec.get("tick_size", 0.25),
                            kill_state=self._kill_state.state,
                        )
                        if result.allowed:
                            self._dispatch_command(result.merged_cmd or cmd)
                        # else: throttled / merged — will surface via flush_due()
                    else:
                        self._dispatch_command(cmd)

            except Exception as exc:
                logger.exception("PAr2Adapter: drain loop error: %s", exc)

            time.sleep(interval)

    def _dispatch_command(self, cmd: PACommand) -> None:
        """Acquire rate limit slot then send to IB."""
        channel  = cmd.channel
        priority = cmd.priority

        # Rate limiter acquire (EXIT never blocks)
        acquired = self._rate_limiter.acquire(channel, priority, block=True, timeout=5.0)
        if not acquired and priority != Priority.EXIT:
            logger.warning("PAr2Adapter: rate limit timeout, command dropped: %s", cmd.command_id)
            self._emit(make_command_rejected_event(cmd, "RATE_LIMIT_TIMEOUT", self._mode))
            return

        action = cmd.action
        spec   = cmd.order_spec or {}

        try:
            if action == Action.PLACE:
                self._place_order(cmd, spec)
            elif action == Action.MODIFY:
                self._modify_order(cmd, spec)
            elif action == Action.CANCEL:
                oid = spec.get("order_id")
                if oid:
                    self._cancel_order_direct(oid)
        except Exception as exc:
            logger.error("PAr2Adapter: dispatch error cmd=%s: %s", cmd.command_id, exc)
            self._emit(make_command_rejected_event(cmd, repr(exc), self._mode))

    # ── IB order helpers ──────────────────────────────────────────────────────

    def _place_order(self, cmd: PACommand, spec: dict) -> None:
        with self._order_id_lock:
            oid = self._next_order_id
            self._next_order_id += 1

        contract = _make_equity_contract(cmd.symbol)

        o = Order()
        o.action        = spec.get("side", "BUY")
        o.totalQuantity = spec.get("qty", 1)
        o.eTradeOnly    = False
        o.firmQuoteOnly = False

        order_kind = spec.get("order_kind", "MKT").upper()
        if order_kind == "MKT":
            o.orderType = "MKT"
        elif order_kind == "LMT":
            o.orderType  = "LMT"
            o.lmtPrice   = spec.get("limit_price", 0.0)
        elif order_kind in ("STP", "STOP"):
            o.orderType  = "STP"
            o.auxPrice   = spec.get("stop_price", 0.0)

        o.tif = spec.get("tif", "GTC")

        self.placeOrder(oid, contract, o)
        self._open_order_ids.append(oid)
        logger.info("PAr2Adapter: placed order id=%d %s %s %s qty=%.0f",
                    oid, cmd.symbol, o.action, o.orderType, o.totalQuantity)

        self._emit(PAEvent(
            type=PAEventType.ORDER_ACCEPTED,
            trading_mode=self._mode,
            symbol=cmd.symbol,
            payload={"order_id": oid, "command_id": cmd.command_id},
        ))

    def _modify_order(self, cmd: PACommand, spec: dict) -> None:
        oid = spec.get("order_id")
        if not oid:
            logger.warning("PAr2Adapter: modify_order missing order_id")
            return

        contract = _make_equity_contract(cmd.symbol)
        o = Order()
        o.action        = spec.get("side", "BUY")
        o.totalQuantity = spec.get("qty", 1)
        o.orderType     = "STP"
        o.auxPrice      = spec.get("stop_price", 0.0)
        o.tif           = spec.get("tif", "GTC")
        o.eTradeOnly    = False
        o.firmQuoteOnly = False

        self.placeOrder(oid, contract, o)
        logger.info("PAr2Adapter: modified order id=%d %s stop=%.4f", oid, cmd.symbol, o.auxPrice)

    def _cancel_order_direct(self, order_id: int) -> None:
        self.cancelOrder(order_id, "")
        if order_id in self._open_order_ids:
            self._open_order_ids.remove(order_id)
        logger.info("PAr2Adapter: cancelled order id=%d", order_id)

    def _flatten_symbol(self, symbol: str) -> None:
        """Market order to close all positions for symbol."""
        logger.warning("PAr2Adapter: flattening %s", symbol)
        with self._order_id_lock:
            oid = self._next_order_id
            self._next_order_id += 1

        contract = _make_equity_contract(symbol)
        o = Order()
        o.action        = "SELL"    # simplified; real impl checks net direction
        o.totalQuantity = 0         # qty=0 with CLOSE action closes entire position
        o.orderType     = "MKT"
        o.tif           = "GTC"
        o.eTradeOnly    = False
        o.firmQuoteOnly = False

        self.placeOrder(oid, contract, o)

    def _flatten_all(self, reason: str) -> None:
        """Cancel all open orders + flatten all known positions (for HardKill / AutoExit)."""
        logger.warning("PAr2Adapter: flatten_all — reason=%s", reason)

        # Cancel all open orders first
        for oid in list(self._open_order_ids):
            try:
                self._cancel_order_direct(oid)
            except Exception as exc:
                logger.error("PAr2Adapter: cancel error oid=%d: %s", oid, exc)

        # Flatten all known positions
        for sym in list(self._open_symbols):
            try:
                self._flatten_symbol(sym)
            except Exception as exc:
                logger.error("PAr2Adapter: flatten error sym=%s: %s", sym, exc)

    # ── Reconciliation (background) ───────────────────────────────────────────

    def _run_reconciliation(self) -> None:
        logger.info("PAr2Adapter: running reconciliation")
        result = self._reconciliation.run_sync(
            local_order_ids=list(self._open_order_ids),
            local_symbols=list(self._open_symbols),
        )
        if not result.is_clean:
            logger.warning("PAr2Adapter: reconciliation unsafe — lockout engaged")

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _next_req_id(self) -> int:
        with self._req_id_lock:
            self._req_id_counter += 1
            return self._req_id_counter
