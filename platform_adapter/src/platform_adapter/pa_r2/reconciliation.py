"""
PAr2 Reconciliation Routine
============================
On every reconnect (and on explicit trigger), PAr2 must:
  1. reqOpenOrders     → discover all open orders at IB
  2. reqPositions      → discover all positions at IB
  3. reqAccountSummary → net liquidation value (optional; for snapshot completeness)
  4. Compare IB truth vs local state
  5. Act on mismatches:
       - Unknown order (IB has it, we don't) → cancel it at IB
       - Unexpected position (IB has it, local net=0) → flatten + lockout
  6. Emit RECONCILIATION_REPORT PAEvent (always, even if clean)

LAW (from state machine spec v0 §5.2):
  RECONCILIATION_UNSAFE_MISMATCH → LOCKOUT (any state → LOCKOUT)
  LOCKOUT + OPERATOR_RESET_LOCKOUT → run reconciliation before resuming

IB API notes:
  reqOpenOrders (reqId not needed — returns orders for this session)
  reqPositions  (no reqId; account arg is empty for all accounts)
  Callbacks: openOrder / orderStatus / position / positionEnd / accountSummary / accountSummaryEnd

Usage:
    rec = ReconciliationRoutine(ib_client=..., on_event=emit_fn, on_lockout=lockout_fn)
    await rec.run(local_orders=..., local_positions=...)  # or call run_sync()
"""

from __future__ import annotations

import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .models import (
    PAEvent,
    PAEventType,
    TradingMode,
)

logger = logging.getLogger(__name__)


# ── Snapshot types ────────────────────────────────────────────────────────────

@dataclass
class IBOrderSnapshot:
    order_id:    int
    symbol:      str
    side:        str          # "BUY" | "SELL"
    order_type:  str          # "MKT" | "STP" | "LMT" etc.
    qty:         float
    filled_qty:  float
    status:      str          # "Submitted" | "PreSubmitted" | etc.
    perm_id:     int = 0      # IB permanent order id


@dataclass
class IBPositionSnapshot:
    symbol:       str
    account:      str
    position:     float       # net position (positive = long, negative = short)
    avg_cost:     float = 0.0


@dataclass
class ReconciliationResult:
    ts_utc_ms:            int
    is_clean:             bool
    ib_orders:            List[IBOrderSnapshot]      = field(default_factory=list)
    ib_positions:         List[IBPositionSnapshot]   = field(default_factory=list)
    local_order_ids:      List[int]                  = field(default_factory=list)
    local_symbols:        List[str]                  = field(default_factory=list)
    unknown_orders:       List[IBOrderSnapshot]      = field(default_factory=list)  # IB has, local doesn't
    unexpected_positions: List[IBPositionSnapshot]   = field(default_factory=list)  # IB has pos, local=0
    actions_taken:        List[str]                  = field(default_factory=list)
    error:                Optional[str]              = None


# ── IB response collector (used with EWrapper callbacks) ─────────────────────

class _IBResponseCollector:
    """
    Collects IB API responses for open orders and positions.
    Designed for synchronous use via threading.Event.

    The adapter injects callbacks into EWrapper methods and calls
    collector.on_open_order / collector.on_position / collector.on_end.
    """

    def __init__(self, timeout_sec: float = 10.0):
        self._timeout      = timeout_sec
        self._orders:    List[IBOrderSnapshot]    = []
        self._positions: List[IBPositionSnapshot] = []
        self._orders_done   = threading.Event()
        self._positions_done = threading.Event()

    # Called by EWrapper.openOrder
    def on_open_order(self, snap: IBOrderSnapshot) -> None:
        self._orders.append(snap)

    # Called by EWrapper.openOrderEnd
    def on_orders_end(self) -> None:
        self._orders_done.set()

    # Called by EWrapper.position
    def on_position(self, snap: IBPositionSnapshot) -> None:
        self._positions.append(snap)

    # Called by EWrapper.positionEnd
    def on_positions_end(self) -> None:
        self._positions_done.set()

    def wait_orders(self) -> bool:
        return self._orders_done.wait(timeout=self._timeout)

    def wait_positions(self) -> bool:
        return self._positions_done.wait(timeout=self._timeout)

    @property
    def orders(self) -> List[IBOrderSnapshot]:
        return self._orders

    @property
    def positions(self) -> List[IBPositionSnapshot]:
        return self._positions


# ── Main reconciliation routine ───────────────────────────────────────────────

class ReconciliationRoutine:
    """
    Reconcile local state against IB truth on reconnect.

    Args:
        ib_client:     EClient instance (for reqOpenOrders / reqPositions / reqGlobalCancel)
        on_event:      callable to emit PAEvents into PipelineContext.exec
        on_lockout:    callable to trigger LOCKOUT in KillStateMachine
        on_cancel_order: callable(order_id: int) → cancel unknown IB order
        on_flatten_symbol: callable(symbol: str) → flatten unexpected position
        trading_mode:  LIVE or PAPER
        timeout_sec:   IB API collection timeout
    """

    def __init__(
        self,
        ib_client,
        on_event:          Callable[[PAEvent], None],
        on_lockout:        Callable[[str], None],
        on_cancel_order:   Callable[[int], None],
        on_flatten_symbol: Callable[[str], None],
        trading_mode:      TradingMode = TradingMode.PAPER,
        timeout_sec:       float = 10.0,
    ):
        self._ib            = ib_client
        self._on_event      = on_event
        self._on_lockout    = on_lockout
        self._cancel_order  = on_cancel_order
        self._flatten       = on_flatten_symbol
        self._mode          = trading_mode
        self._timeout       = timeout_sec

        # Injected by adapter into EWrapper callbacks
        self._collector: Optional[_IBResponseCollector] = None

    # ── Called by EWrapper callbacks (adapter wires these) ────────────────────

    def inject_open_order(self, snap: IBOrderSnapshot) -> None:
        if self._collector:
            self._collector.on_open_order(snap)

    def inject_orders_end(self) -> None:
        if self._collector:
            self._collector.on_orders_end()

    def inject_position(self, snap: IBPositionSnapshot) -> None:
        if self._collector:
            self._collector.on_position(snap)

    def inject_positions_end(self) -> None:
        if self._collector:
            self._collector.on_positions_end()

    # ── Main reconciliation entry point ───────────────────────────────────────

    def run_sync(
        self,
        local_order_ids: Optional[List[int]] = None,
        local_symbols:   Optional[List[str]] = None,
    ) -> ReconciliationResult:
        """
        Blocking reconciliation. Call in a background thread from adapter
        immediately after connection is confirmed.

        local_order_ids: IB order IDs we believe are open
        local_symbols:   symbols we believe we hold a non-zero net position in
        """
        local_order_ids = local_order_ids or []
        local_symbols   = local_symbols   or []

        ts = int(time.time() * 1000)
        result = ReconciliationResult(
            ts_utc_ms=ts,
            is_clean=False,
            local_order_ids=list(local_order_ids),
            local_symbols=list(local_symbols),
        )

        try:
            # Step 1: collect IB open orders
            self._collector = _IBResponseCollector(timeout_sec=self._timeout)
            self._ib.reqOpenOrders()
            orders_ok = self._collector.wait_orders()
            if not orders_ok:
                result.error = "reqOpenOrders timed out"
                logger.error("ReconciliationRoutine: %s", result.error)
                return self._emit_unsafe(result)

            # Step 2: collect IB positions
            self._ib.reqPositions()
            positions_ok = self._collector.wait_positions()
            if not positions_ok:
                result.error = "reqPositions timed out"
                logger.error("ReconciliationRoutine: %s", result.error)
                return self._emit_unsafe(result)

            result.ib_orders    = self._collector.orders
            result.ib_positions = self._collector.positions
            self._collector = None

            # Step 3: detect mismatches
            local_id_set     = set(local_order_ids)
            local_symbol_set = set(s.upper() for s in local_symbols)

            for snap in result.ib_orders:
                if snap.order_id not in local_id_set:
                    result.unknown_orders.append(snap)

            for pos in result.ib_positions:
                if pos.position != 0 and pos.symbol.upper() not in local_symbol_set:
                    result.unexpected_positions.append(pos)

            # Step 4: act on mismatches
            if result.unknown_orders or result.unexpected_positions:
                for snap in result.unknown_orders:
                    logger.warning(
                        "ReconciliationRoutine: unknown IB order %d %s %s %s — cancelling",
                        snap.order_id, snap.symbol, snap.side, snap.order_type,
                    )
                    try:
                        self._cancel_order(snap.order_id)
                        result.actions_taken.append(f"CANCEL order_id={snap.order_id} symbol={snap.symbol}")
                    except Exception as exc:
                        logger.error("ReconciliationRoutine: cancel failed %s", exc)
                        result.error = str(exc)

                for pos in result.unexpected_positions:
                    logger.warning(
                        "ReconciliationRoutine: unexpected position %s qty=%.2f — flattening + lockout",
                        pos.symbol, pos.position,
                    )
                    try:
                        self._flatten(pos.symbol)
                        result.actions_taken.append(
                            f"FLATTEN symbol={pos.symbol} qty={pos.position} acct={pos.account}"
                        )
                    except Exception as exc:
                        logger.error("ReconciliationRoutine: flatten failed %s", exc)
                        result.error = str(exc)

                # RECONCILIATION_UNSAFE_MISMATCH → LOCKOUT (spec §5.2)
                return self._emit_unsafe(result)

            # Clean reconciliation
            result.is_clean = True
            logger.info("ReconciliationRoutine: clean — no mismatches found")

        except Exception as exc:
            result.error = repr(exc)
            logger.exception("ReconciliationRoutine: unexpected error")
            return self._emit_unsafe(result)

        finally:
            self._collector = None

        self._emit_report(result)
        return result

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _emit_unsafe(self, result: ReconciliationResult) -> ReconciliationResult:
        """Emit LOCKOUT_ENABLED + RECONCILIATION_REPORT."""
        result.is_clean = False

        lockout_reason = result.error or "RECONCILIATION_UNSAFE_MISMATCH"
        self._on_lockout(lockout_reason)

        self._emit_report(result)
        return result

    def _emit_report(self, result: ReconciliationResult) -> None:
        evt = PAEvent(
            type=PAEventType.RECONCILIATION_REPORT,
            trading_mode=self._mode,
            payload={
                "ts_utc_ms":            result.ts_utc_ms,
                "is_clean":             result.is_clean,
                "ib_open_orders":       [self._order_dict(o) for o in result.ib_orders],
                "ib_positions":         [self._pos_dict(p)   for p in result.ib_positions],
                "local_order_ids":      result.local_order_ids,
                "local_symbols":        result.local_symbols,
                "unknown_orders":       [self._order_dict(o) for o in result.unknown_orders],
                "unexpected_positions": [self._pos_dict(p)   for p in result.unexpected_positions],
                "actions_taken":        result.actions_taken,
                "error":                result.error,
            },
        )
        try:
            self._on_event(evt)
        except Exception as exc:
            logger.error("ReconciliationRoutine: failed to emit event: %s", exc)

    @staticmethod
    def _order_dict(o: IBOrderSnapshot) -> dict:
        return {
            "order_id":   o.order_id,
            "symbol":     o.symbol,
            "side":       o.side,
            "order_type": o.order_type,
            "qty":        o.qty,
            "filled_qty": o.filled_qty,
            "status":     o.status,
            "perm_id":    o.perm_id,
        }

    @staticmethod
    def _pos_dict(p: IBPositionSnapshot) -> dict:
        return {
            "symbol":   p.symbol,
            "account":  p.account,
            "position": p.position,
            "avg_cost": p.avg_cost,
        }
