"""
PA r2 — Stop-Modify Throttler

Prevents excessive stop-order modifications from overwhelming IB pacing.

Rules:
  - min_interval: Minimum time between successive stop modifies for the same order
  - min_delta: Minimum price change (in ticks) to justify sending a modify
  - merge_window: If multiple modifies arrive within this window, only the LAST one is sent

When a stop-modify arrives too soon or with insufficient price change,
it is held and merged with the next request. The latest price always wins.

Author: PA r2
Date: 2026-02-16
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, Optional

from loguru import logger


@dataclass
class PendingStopModify:
    """A stop modification waiting to be sent."""
    order_id: int
    new_stop_price: float
    received_at: float  # monotonic time
    send_after: float   # monotonic time (earliest send time)
    executor: Callable[[], None]  # The actual modify call


class StopModifyThrottler:
    """
    Throttles stop-order modifications.
    
    For each order_id, tracks the last modification time and price.
    If a new modification arrives within min_interval or with less than
    min_delta price change, it is merged/deferred.
    
    A background thread sends deferred modifications when their
    send_after time arrives.
    """
    
    def __init__(
        self,
        min_interval_ms: int = 250,
        min_delta_ticks: int = 1,
        tick_size: float = 0.25,
        merge_window_ms: int = 100,
    ):
        """
        Args:
            min_interval_ms: Minimum ms between stop modifies per order
            min_delta_ticks: Minimum tick change to send a modify
            tick_size: Size of one tick in price units (default 0.25 for ES)
            merge_window_ms: Merge modifies within this window
        """
        self._min_interval = min_interval_ms / 1000.0
        self._min_delta = min_delta_ticks * tick_size
        self._merge_window = merge_window_ms / 1000.0
        self._tick_size = tick_size
        
        # State per order_id
        self._last_sent_time: Dict[int, float] = {}    # order_id → monotonic time
        self._last_sent_price: Dict[int, float] = {}   # order_id → stop price
        self._pending: Dict[int, PendingStopModify] = {}
        
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Metrics
        self._sent_count = 0
        self._merged_count = 0
        self._dropped_count = 0
        
        logger.info(
            f"StopModifyThrottler initialized: "
            f"min_interval={min_interval_ms}ms, "
            f"min_delta={min_delta_ticks} ticks ({self._min_delta}), "
            f"merge_window={merge_window_ms}ms"
        )
    
    def submit_stop_modify(
        self,
        order_id: int,
        new_stop_price: float,
        executor: Callable[[], None],
    ) -> str:
        """
        Submit a stop modification request.
        
        Returns:
            "sent" — modification sent immediately
            "deferred" — modification deferred (will be sent later)
            "merged" — modification merged with existing pending
            "dropped" — modification dropped (no meaningful change)
        """
        now = time.monotonic()
        
        with self._lock:
            # Check min_delta
            last_price = self._last_sent_price.get(order_id)
            if last_price is not None:
                delta = abs(new_stop_price - last_price)
                if delta < self._min_delta:
                    self._dropped_count += 1
                    logger.debug(
                        f"Stop modify dropped: order={order_id}, "
                        f"delta={delta:.4f} < min_delta={self._min_delta}"
                    )
                    return "dropped"
            
            # Check min_interval
            last_sent = self._last_sent_time.get(order_id, 0.0)
            time_since_last = now - last_sent
            
            if time_since_last >= self._min_interval:
                # Can send immediately
                self._last_sent_time[order_id] = now
                self._last_sent_price[order_id] = new_stop_price
                self._sent_count += 1
        
                # Execute outside lock
                try:
                    executor()
                    logger.debug(
                        f"Stop modify sent: order={order_id}, "
                        f"price={new_stop_price}"
                    )
                except Exception as e:
                    logger.error(f"Stop modify execution failed: {e}")
                return "sent"
            
            else:
                # Must defer
                send_after = last_sent + self._min_interval
                
                if order_id in self._pending:
                    # Merge: replace pending with latest price
                    self._pending[order_id].new_stop_price = new_stop_price
                    self._pending[order_id].executor = executor
                    self._pending[order_id].received_at = now
                    self._merged_count += 1
                    logger.debug(
                        f"Stop modify merged: order={order_id}, "
                        f"price={new_stop_price}"
                    )
                    return "merged"
                else:
                    # New pending
                    self._pending[order_id] = PendingStopModify(
                        order_id=order_id,
                        new_stop_price=new_stop_price,
                        received_at=now,
                        send_after=send_after,
                        executor=executor,
                    )
                    logger.debug(
                        f"Stop modify deferred: order={order_id}, "
                        f"price={new_stop_price}, "
                        f"send_in={send_after - now:.3f}s"
                    )
                    return "deferred"
    
    def start(self) -> None:
        """Start the background thread that sends deferred modifications."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._drain_loop,
            daemon=True,
            name="PA-StopThrottle",
        )
        self._thread.start()
        logger.info("StopModifyThrottler started")
    
    def stop(self) -> None:
        """Stop the throttler. Pending modifications are discarded."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        logger.info(
            f"StopModifyThrottler stopped. "
            f"Sent={self._sent_count}, Merged={self._merged_count}, "
            f"Dropped={self._dropped_count}"
        )
    
    def _drain_loop(self) -> None:
        """Background: send deferred modifications when ready."""
        while self._running:
            try:
                self._process_pending()
            except Exception as e:
                logger.error(f"Error in stop throttle drain: {e}")
            time.sleep(0.050)  # 50ms check interval
    
    def _process_pending(self) -> None:
        """Check and send any pending modifications whose time has come."""
        now = time.monotonic()
        to_send = []
        
        with self._lock:
            for order_id, pending in list(self._pending.items()):
                if now >= pending.send_after:
                    to_send.append(pending)
                    del self._pending[order_id]
                    self._last_sent_time[order_id] = now
                    self._last_sent_price[order_id] = pending.new_stop_price
                    self._sent_count += 1
        
        # Execute outside lock
        for pending in to_send:
            try:
                pending.executor()
                logger.debug(
                    f"Deferred stop modify sent: order={pending.order_id}, "
                    f"price={pending.new_stop_price}"
                )
            except Exception as e:
                logger.error(
                    f"Deferred stop modify failed: order={pending.order_id}, "
                    f"error={e}"
                )
    
    def clear_order(self, order_id: int) -> None:
        """Remove tracking state for an order (order filled/cancelled)."""
        with self._lock:
            self._last_sent_time.pop(order_id, None)
            self._last_sent_price.pop(order_id, None)
            self._pending.pop(order_id, None)
    
    def set_tick_size(self, tick_size: float) -> None:
        """Update tick size (e.g., when switching symbols)."""
        with self._lock:
            self._tick_size = tick_size
            self._min_delta = (self._min_delta / self._tick_size) * tick_size
    
    def get_status(self) -> dict:
        """Get throttler status."""
        with self._lock:
            return {
                "pending_count": len(self._pending),
                "sent": self._sent_count,
                "merged": self._merged_count,
                "dropped": self._dropped_count,
                "running": self._running,
            }
    
    def __repr__(self) -> str:
        return (
            f"StopModifyThrottler("
            f"sent={self._sent_count}, "
            f"merged={self._merged_count}, "
            f"dropped={self._dropped_count})"
        )
