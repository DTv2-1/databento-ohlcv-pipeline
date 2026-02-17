"""
State Manager for Platform Adapter

Manages unified state across all components:
- Positions cache
- Orders cache  
- Account values cache
- Thread-safe operations
- Reconciliation support

Author: Platform Adapter Team
Created: 2026-01-27
"""

import time
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from ..models.position import Position
from ..models.order import Order
from ..adapters.account_manager import AccountValue
from loguru import logger


class StateManager:
    """
    Manages unified state across all platform adapter components.
    
    Provides thread-safe caching and querying of:
    - Positions
    - Orders
    - Account values
    
    Supports reconciliation and state updates from multiple sources.
    """
    
    def __init__(self):
        """Initialize state manager with empty caches."""
        self._positions: Dict[str, Position] = {}
        self._orders: Dict[int, Order] = {}
        self._account_values: Dict[str, AccountValue] = {}
        self._last_update: Optional[float] = None
        
        # Thread safety
        self._lock = threading.RLock()
        
        logger.info("StateManager initialized")
    
    # ============================================================================
    # POSITION MANAGEMENT
    # ============================================================================
    
    def update_position(self, position: Position) -> None:
        """
        Update position in cache.
        
        Args:
            position: Position object to update
        """
        with self._lock:
            self._positions[position.symbol] = position
            self._last_update = time.time()
            logger.debug(f"Position updated: {position.symbol} -> {position.quantity} @ {position.avg_cost}")
    
    def update_positions(self, positions: List[Position]) -> None:
        """
        Batch update multiple positions.
        
        Args:
            positions: List of Position objects
        """
        with self._lock:
            for position in positions:
                self._positions[position.symbol] = position
            self._last_update = time.time()
            logger.info(f"Batch updated {len(positions)} positions")
    
    def remove_position(self, symbol: str) -> None:
        """
        Remove position from cache (position closed).
        
        Args:
            symbol: Symbol of position to remove
        """
        with self._lock:
            if symbol in self._positions:
                del self._positions[symbol]
                self._last_update = time.time()
                logger.debug(f"Position removed: {symbol}")
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Symbol to query
            
        Returns:
            Position object if found, None otherwise
        """
        with self._lock:
            return self._positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """
        Get all cached positions.
        
        Returns:
            List of all Position objects
        """
        with self._lock:
            return list(self._positions.values())
    
    def get_positions_count(self) -> int:
        """
        Get count of positions in cache.
        
        Returns:
            Number of positions
        """
        with self._lock:
            return len(self._positions)
    
    def clear_positions(self) -> None:
        """Clear all positions from cache."""
        with self._lock:
            self._positions.clear()
            self._last_update = time.time()
            logger.info("All positions cleared")
    
    # ============================================================================
    # ORDER MANAGEMENT
    # ============================================================================
    
    def update_order(self, order: Order) -> None:
        """
        Update order in cache.
        
        Args:
            order: Order object to update
        """
        with self._lock:
            self._orders[order.order_id] = order
            self._last_update = time.time()
            logger.debug(f"Order updated: {order.order_id} -> {order.status}")
    
    def update_orders(self, orders: List[Order]) -> None:
        """
        Batch update multiple orders.
        
        Args:
            orders: List of Order objects
        """
        with self._lock:
            for order in orders:
                self._orders[order.order_id] = order
            self._last_update = time.time()
            logger.info(f"Batch updated {len(orders)} orders")
    
    def remove_order(self, order_id: int) -> None:
        """
        Remove order from cache.
        
        Args:
            order_id: Order ID to remove
        """
        with self._lock:
            if order_id in self._orders:
                del self._orders[order_id]
                self._last_update = time.time()
                logger.debug(f"Order removed: {order_id}")
    
    def get_order(self, order_id: int) -> Optional[Order]:
        """
        Get order by ID.
        
        Args:
            order_id: Order ID to query
            
        Returns:
            Order object if found, None otherwise
        """
        with self._lock:
            return self._orders.get(order_id)
    
    def get_all_orders(self) -> List[Order]:
        """
        Get all cached orders.
        
        Returns:
            List of all Order objects
        """
        with self._lock:
            return list(self._orders.values())
    
    def get_active_orders(self) -> List[Order]:
        """
        Get all active orders (not filled, cancelled, or inactive).
        
        Returns:
            List of active Order objects
        """
        from ..models.order import OrderStatus
        
        with self._lock:
            active_statuses = {
                OrderStatus.PENDING_SUBMIT,
                OrderStatus.SUBMITTED,
                OrderStatus.PRE_SUBMITTED,
            }
            return [
                order for order in self._orders.values()
                if order.status in active_statuses
            ]
    
    def get_orders_by_symbol(self, symbol: str) -> List[Order]:
        """
        Get all orders for a specific symbol.
        
        Args:
            symbol: Symbol to filter by
            
        Returns:
            List of Order objects for the symbol
        """
        with self._lock:
            return [
                order for order in self._orders.values()
                if order.symbol == symbol
            ]
    
    def get_orders_count(self) -> int:
        """
        Get count of orders in cache.
        
        Returns:
            Number of orders
        """
        with self._lock:
            return len(self._orders)
    
    def clear_orders(self) -> None:
        """Clear all orders from cache."""
        with self._lock:
            self._orders.clear()
            self._last_update = time.time()
            logger.info("All orders cleared")
    
    # ============================================================================
    # ACCOUNT VALUE MANAGEMENT
    # ============================================================================
    
    def update_account_value(self, account_value: AccountValue) -> None:
        """
        Update account value in cache.
        
        Args:
            account_value: AccountValue object to update
        """
        with self._lock:
            # Use key as the unique identifier
            self._account_values[account_value.key] = account_value
            self._last_update = time.time()
            logger.debug(f"Account value updated: {account_value.key} -> {account_value.value}")
    
    def update_account_values(self, account_values: List[AccountValue]) -> None:
        """
        Batch update multiple account values.
        
        Args:
            account_values: List of AccountValue objects
        """
        with self._lock:
            for av in account_values:
                self._account_values[av.key] = av
            self._last_update = time.time()
            logger.info(f"Batch updated {len(account_values)} account values")
    
    def get_account_value(self, key: str) -> Optional[AccountValue]:
        """
        Get account value by key.
        
        Args:
            key: Account value key (e.g., 'NetLiquidation')
            
        Returns:
            AccountValue object if found, None otherwise
        """
        with self._lock:
            return self._account_values.get(key)
    
    def get_all_account_values(self) -> List[AccountValue]:
        """
        Get all cached account values.
        
        Returns:
            List of all AccountValue objects
        """
        with self._lock:
            return list(self._account_values.values())
    
    def get_account_values_dict(self) -> Dict[str, Any]:
        """
        Get account values as a dictionary.
        
        Returns:
            Dictionary mapping keys to values
        """
        with self._lock:
            return {
                key: av.value
                for key, av in self._account_values.items()
            }
    
    def clear_account_values(self) -> None:
        """Clear all account values from cache."""
        with self._lock:
            self._account_values.clear()
            self._last_update = time.time()
            logger.info("All account values cleared")
    
    # ============================================================================
    # GENERAL STATE MANAGEMENT
    # ============================================================================
    
    def get_last_update(self) -> Optional[datetime]:
        """
        Get timestamp of last state update.
        
        Returns:
            Datetime of last update, or None if no updates yet
        """
        with self._lock:
            if self._last_update is None:
                return None
            return datetime.fromtimestamp(self._last_update)
    
    def get_state_summary(self) -> Dict[str, Any]:
        """
        Get summary of current state.
        
        Returns:
            Dictionary with state counts and last update time
        """
        with self._lock:
            return {
                'positions_count': len(self._positions),
                'orders_count': len(self._orders),
                'active_orders_count': len(self.get_active_orders()),
                'account_values_count': len(self._account_values),
                'last_update': self.get_last_update(),
            }
    
    def clear_all(self) -> None:
        """Clear all state (positions, orders, account values)."""
        with self._lock:
            self._positions.clear()
            self._orders.clear()
            self._account_values.clear()
            self._last_update = time.time()
            logger.info("All state cleared")
    
    # ============================================================================
    # RECONCILIATION
    # ============================================================================
    
    def reconcile_positions(self, authoritative_positions: List[Position]) -> Dict[str, Any]:
        """
        Reconcile cached positions with authoritative source.
        
        Args:
            authoritative_positions: List of positions from authoritative source
            
        Returns:
            Dictionary with reconciliation results:
                - added: List of symbols added
                - updated: List of symbols updated
                - removed: List of symbols removed
                - unchanged: List of symbols unchanged
        """
        with self._lock:
            auth_symbols = {pos.symbol for pos in authoritative_positions}
            cached_symbols = set(self._positions.keys())
            
            added = []
            updated = []
            removed = []
            unchanged = []
            
            # Check for additions and updates
            for pos in authoritative_positions:
                if pos.symbol not in cached_symbols:
                    added.append(pos.symbol)
                    self._positions[pos.symbol] = pos
                else:
                    cached_pos = self._positions[pos.symbol]
                    if (cached_pos.quantity != pos.quantity or 
                        cached_pos.avg_cost != pos.avg_cost):
                        updated.append(pos.symbol)
                        self._positions[pos.symbol] = pos
                    else:
                        unchanged.append(pos.symbol)
            
            # Check for removals
            for symbol in cached_symbols:
                if symbol not in auth_symbols:
                    removed.append(symbol)
                    del self._positions[symbol]
            
            self._last_update = time.time()
            
            result = {
                'added': added,
                'updated': updated,
                'removed': removed,
                'unchanged': unchanged,
            }
            
            logger.info(
                f"Position reconciliation: "
                f"+{len(added)} ~{len(updated)} -{len(removed)} ={len(unchanged)}"
            )
            
            return result
    
    def reconcile_orders(self, authoritative_orders: List[Order]) -> Dict[str, Any]:
        """
        Reconcile cached orders with authoritative source.
        
        Args:
            authoritative_orders: List of orders from authoritative source
            
        Returns:
            Dictionary with reconciliation results:
                - added: List of order IDs added
                - updated: List of order IDs updated
                - removed: List of order IDs removed
                - unchanged: List of order IDs unchanged
        """
        with self._lock:
            auth_ids = {order.order_id for order in authoritative_orders}
            cached_ids = set(self._orders.keys())
            
            added = []
            updated = []
            removed = []
            unchanged = []
            
            # Check for additions and updates
            for order in authoritative_orders:
                if order.order_id not in cached_ids:
                    added.append(order.order_id)
                    self._orders[order.order_id] = order
                else:
                    cached_order = self._orders[order.order_id]
                    if cached_order.status != order.status:
                        updated.append(order.order_id)
                        self._orders[order.order_id] = order
                    else:
                        unchanged.append(order.order_id)
            
            # Check for removals
            for order_id in cached_ids:
                if order_id not in auth_ids:
                    removed.append(order_id)
                    del self._orders[order_id]
            
            self._last_update = time.time()
            
            result = {
                'added': added,
                'updated': updated,
                'removed': removed,
                'unchanged': unchanged,
            }
            
            logger.info(
                f"Order reconciliation: "
                f"+{len(added)} ~{len(updated)} -{len(removed)} ={len(unchanged)}"
            )
            
            return result
    
    def __repr__(self) -> str:
        """String representation of state manager."""
        summary = self.get_state_summary()
        return (
            f"StateManager("
            f"positions={summary['positions_count']}, "
            f"orders={summary['orders_count']}, "
            f"active_orders={summary['active_orders_count']}, "
            f"account_values={summary['account_values_count']}, "
            f"last_update={summary['last_update']})"
        )
