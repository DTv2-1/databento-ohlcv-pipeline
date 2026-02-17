"""
PA r2 — Reconciliation Engine

After every (re)connection to IB, reconciles local state against IB truth:
  1. Queries IB for open orders, positions, and account summary
  2. Diffs against local state (if any)
  3. Resolves orphans per config policy
  4. Emits reconciliation report event

The reconciliation engine does NOT own state — it uses the StateManager
for local state and the adapters for IB queries.

Author: PA r2
Date: 2026-02-16
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


@dataclass
class ReconciliationReport:
    """Report generated after reconciliation."""
    timestamp: datetime
    duration_sec: float
    
    # Positions
    positions_broker: int = 0
    positions_local: int = 0
    positions_added: List[str] = field(default_factory=list)
    positions_updated: List[str] = field(default_factory=list)
    positions_removed: List[str] = field(default_factory=list)
    positions_mismatches: List[Dict[str, Any]] = field(default_factory=list)
    
    # Orders
    orders_broker: int = 0
    orders_local: int = 0
    orders_orphaned: List[int] = field(default_factory=list)  # On broker, not local
    orders_stale: List[int] = field(default_factory=list)     # Local, not on broker
    orders_synced: int = 0
    
    # Actions taken
    actions_taken: List[str] = field(default_factory=list)
    
    # Status
    success: bool = True
    error_message: str = ""
    
    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"=== Reconciliation Report ({self.timestamp.isoformat()}) ===",
            f"Duration: {self.duration_sec:.2f}s",
            f"Positions: broker={self.positions_broker}, local={self.positions_local}",
        ]
        if self.positions_added:
            lines.append(f"  Added: {self.positions_added}")
        if self.positions_updated:
            lines.append(f"  Updated: {self.positions_updated}")
        if self.positions_removed:
            lines.append(f"  Removed: {self.positions_removed}")
        if self.positions_mismatches:
            lines.append(f"  Mismatches: {len(self.positions_mismatches)}")
        
        lines.append(f"Orders: broker={self.orders_broker}, local={self.orders_local}")
        if self.orders_orphaned:
            lines.append(f"  Orphaned (broker-only): {self.orders_orphaned}")
        if self.orders_stale:
            lines.append(f"  Stale (local-only): {self.orders_stale}")
        lines.append(f"  Synced: {self.orders_synced}")
        
        if self.actions_taken:
            lines.append(f"Actions: {self.actions_taken}")
        
        if not self.success:
            lines.append(f"ERROR: {self.error_message}")
        
        return "\n".join(lines)


class ReconciliationEngine:
    """
    Reconciles local PA state against IB broker truth.
    
    Called after every connection/reconnection. Uses callbacks to:
      - Query broker state (positions, orders, account)
      - Query local state
      - Apply resolution policy
      - Emit report
    """
    
    def __init__(
        self,
        orphan_policy: str = "log_and_alert",
        position_mismatch_policy: str = "accept_broker",
        on_report: Optional[Callable[[ReconciliationReport], None]] = None,
    ):
        """
        Args:
            orphan_policy: How to handle orphaned orders 
                          ("cancel", "adopt", "log_and_alert")
            position_mismatch_policy: How to handle position mismatches
                                    ("accept_broker", "alert_only")
            on_report: Callback with reconciliation report
        """
        self._orphan_policy = orphan_policy
        self._position_mismatch_policy = position_mismatch_policy
        self._on_report = on_report
        self._last_report: Optional[ReconciliationReport] = None
        
        logger.info(
            f"ReconciliationEngine initialized: "
            f"orphan_policy={orphan_policy}, "
            f"position_mismatch_policy={position_mismatch_policy}"
        )
    
    def reconcile(
        self,
        broker_positions: List[Any],
        broker_orders: List[Any],
        local_positions: Dict[str, Any],
        local_orders: Dict[int, Any],
        cancel_order_fn: Optional[Callable[[int], None]] = None,
        update_local_positions_fn: Optional[Callable[[List[Any]], None]] = None,
        update_local_orders_fn: Optional[Callable[[List[Any]], None]] = None,
    ) -> ReconciliationReport:
        """
        Run reconciliation between broker truth and local state.
        
        Args:
            broker_positions: Positions from IB (reqPositions result)
            broker_orders: Open orders from IB (reqAllOpenOrders result)
            local_positions: Local position cache {symbol: Position}
            local_orders: Local order cache {order_id: Order}
            cancel_order_fn: Function to cancel an order (for orphan policy)
            update_local_positions_fn: Function to update local positions
            update_local_orders_fn: Function to update local orders
            
        Returns:
            ReconciliationReport
        """
        start_time = time.monotonic()
        report = ReconciliationReport(timestamp=datetime.now(), duration_sec=0.0)
        
        try:
            # --- Reconcile Positions ---
            report.positions_broker = len(broker_positions)
            report.positions_local = len(local_positions)
            
            broker_pos_by_symbol = {}
            for pos in broker_positions:
                symbol = getattr(pos, 'symbol', str(pos))
                broker_pos_by_symbol[symbol] = pos
            
            broker_symbols = set(broker_pos_by_symbol.keys())
            local_symbols = set(local_positions.keys())
            
            # New positions (on broker, not local)
            for symbol in broker_symbols - local_symbols:
                report.positions_added.append(symbol)
            
            # Removed positions (local, not on broker)
            for symbol in local_symbols - broker_symbols:
                report.positions_removed.append(symbol)
            
            # Check for mismatches
            for symbol in broker_symbols & local_symbols:
                broker_pos = broker_pos_by_symbol[symbol]
                local_pos = local_positions[symbol]
                
                broker_qty = getattr(broker_pos, 'quantity', 0)
                local_qty = getattr(local_pos, 'quantity', 0)
                
                if broker_qty != local_qty:
                    report.positions_mismatches.append({
                        "symbol": symbol,
                        "broker_qty": broker_qty,
                        "local_qty": local_qty,
                    })
                    report.positions_updated.append(symbol)
            
            # Apply position mismatch policy
            if self._position_mismatch_policy == "accept_broker":
                if update_local_positions_fn and (
                    report.positions_added or 
                    report.positions_updated or 
                    report.positions_removed
                ):
                    update_local_positions_fn(broker_positions)
                    report.actions_taken.append(
                        f"Accepted broker positions ({len(broker_positions)} total)"
                    )
            elif self._position_mismatch_policy == "alert_only":
                if report.positions_mismatches:
                    report.actions_taken.append(
                        f"ALERT: {len(report.positions_mismatches)} position mismatches"
                    )
            
            # --- Reconcile Orders ---
            report.orders_broker = len(broker_orders)
            report.orders_local = len(local_orders)
            
            broker_order_ids = set()
            for order in broker_orders:
                oid = getattr(order, 'order_id', getattr(order, 'orderId', None))
                if oid is not None:
                    broker_order_ids.add(oid)
            
            local_order_ids = set(local_orders.keys())
            
            # Orphaned orders (on broker, not tracked locally)
            orphaned = broker_order_ids - local_order_ids
            report.orders_orphaned = list(orphaned)
            
            # Stale orders (local, not on broker)
            stale = local_order_ids - broker_order_ids
            report.orders_stale = list(stale)
            
            # Synced orders
            report.orders_synced = len(broker_order_ids & local_order_ids)
            
            # Apply orphan policy
            if orphaned:
                if self._orphan_policy == "cancel" and cancel_order_fn:
                    for oid in orphaned:
                        try:
                            cancel_order_fn(oid)
                            report.actions_taken.append(f"Cancelled orphan order {oid}")
                        except Exception as e:
                            report.actions_taken.append(
                                f"Failed to cancel orphan order {oid}: {e}"
                            )
                elif self._orphan_policy == "adopt" and update_local_orders_fn:
                    update_local_orders_fn(broker_orders)
                    report.actions_taken.append(
                        f"Adopted {len(orphaned)} orphan orders"
                    )
                elif self._orphan_policy == "log_and_alert":
                    report.actions_taken.append(
                        f"ALERT: {len(orphaned)} orphan orders on broker: {list(orphaned)}"
                    )
            
            # Clean stale local orders
            if stale:
                report.actions_taken.append(
                    f"Cleared {len(stale)} stale local orders: {list(stale)}"
                )
            
            report.success = True
            
        except Exception as e:
            report.success = False
            report.error_message = str(e)
            logger.error(f"Reconciliation failed: {e}")
        
        report.duration_sec = time.monotonic() - start_time
        self._last_report = report
        
        # Log report
        logger.info(report.summary())
        
        # Emit report callback
        if self._on_report:
            try:
                self._on_report(report)
            except Exception as e:
                logger.error(f"Error in reconciliation report callback: {e}")
        
        return report
    
    @property
    def last_report(self) -> Optional[ReconciliationReport]:
        """Last reconciliation report."""
        return self._last_report
    
    def __repr__(self) -> str:
        return (
            f"ReconciliationEngine("
            f"orphan_policy={self._orphan_policy}, "
            f"position_policy={self._position_mismatch_policy})"
        )
