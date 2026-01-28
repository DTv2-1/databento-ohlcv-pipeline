"""
Order Execution Adapter
Handles order placement, cancellation, and tracking with IB

Author: Platform Adapter Team
Date: January 27, 2026
"""

from typing import Optional, Dict, Callable, List
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

from ibapi.order import Order as IBOrder
from ibapi.contract import Contract as IBContract
from ibapi.execution import Execution

from ..core.connection_manager import ConnectionManager
from ..models.contract import Contract
from ..models.order import Order, OrderStatus
from ..utils.rate_limiter import IBRateLimiters


class OrderType(str, Enum):
    """Supported order types"""
    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    STOP_LIMIT = "STP LMT"


class OrderAction(str, Enum):
    """Order actions"""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class OrderExecution:
    """Order execution details"""
    order_id: int
    exec_id: str
    timestamp: datetime
    symbol: str
    side: str
    shares: int
    price: float
    commission: float = 0.0
    
    def __repr__(self) -> str:
        return (f"Execution(order={self.order_id} {self.side} {self.shares}@{self.price:.2f} "
                f"comm=${self.commission:.2f})")


@dataclass
class OrderUpdate:
    """Order status update"""
    order_id: int
    status: str
    filled: int
    remaining: int
    avg_fill_price: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __repr__(self) -> str:
        return (f"OrderUpdate(id={self.order_id} status={self.status} "
                f"filled={self.filled}/{self.filled + self.remaining} @ {self.avg_fill_price:.2f})")


class OrderExecutionAdapter:
    """
    Adapter for order execution via IB API.
    
    Handles:
    - Order placement (Market, Limit, Stop orders)
    - Order cancellation
    - Order status tracking
    - Execution reports
    """
    
    def __init__(self, connection_manager: ConnectionManager):
        """
        Initialize order execution adapter.
        
        Args:
            connection_manager: Active IB connection
        """
        self.cm = connection_manager
        
        # Order tracking
        self._orders: Dict[int, Order] = {}
        self._order_status: Dict[int, OrderUpdate] = {}
        self._executions: Dict[int, List[OrderExecution]] = {}
        self._commissions: Dict[int, float] = {}  # order_id -> commission
        
        # Callbacks
        self._order_callbacks: Dict[int, Callable[[OrderUpdate], None]] = {}
        self._execution_callbacks: Dict[int, Callable[[OrderExecution], None]] = {}
        
        # Register IB callbacks
        self._register_callbacks()
        
        logger.info("OrderExecutionAdapter initialized")
    
    def _register_callbacks(self):
        """Register IB API callbacks for order events."""
        
        # openOrder callback
        original_open_order = self.cm.openOrder
        def open_order_handler(orderId: int, contract: IBContract, order: IBOrder, orderState):
            self._handle_open_order(orderId, contract, order, orderState)
            if original_open_order:
                original_open_order(orderId, contract, order, orderState)
        self.cm.openOrder = open_order_handler
        
        # orderStatus callback
        original_order_status = self.cm.orderStatus
        def order_status_handler(orderId: int, status: str, filled: float, 
                                remaining: float, avgFillPrice: float, permId: int,
                                parentId: int, lastFillPrice: float, clientId: int,
                                whyHeld: str, mktCapPrice: float):
            self._handle_order_status(orderId, status, filled, remaining, avgFillPrice)
            if original_order_status:
                original_order_status(orderId, status, filled, remaining, avgFillPrice,
                                    permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)
        self.cm.orderStatus = order_status_handler
        
        # execDetails callback
        original_exec_details = self.cm.execDetails
        def exec_details_handler(reqId: int, contract: IBContract, execution: Execution):
            self._handle_exec_details(reqId, contract, execution)
            if original_exec_details:
                original_exec_details(reqId, contract, execution)
        self.cm.execDetails = exec_details_handler
        
        # commissionReport callback
        original_commission_report = self.cm.commissionReport
        def commission_report_handler(commissionReport):
            self._handle_commission_report(commissionReport)
            if original_commission_report:
                original_commission_report(commissionReport)
        self.cm.commissionReport = commission_report_handler
        
        logger.info("Order execution callbacks registered")
    
    def place_order(
        self,
        contract: Contract,
        action: OrderAction,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        callback: Optional[Callable[[OrderUpdate], None]] = None
    ) -> int:
        """
        Place an order.
        
        Args:
            contract: Contract to trade
            action: BUY or SELL
            quantity: Number of shares/contracts
            order_type: Market, Limit, Stop, or Stop Limit
            limit_price: Limit price (required for LMT and STP LMT orders)
            stop_price: Stop price (required for STP and STP LMT orders)
            callback: Optional callback for order updates
            
        Returns:
            Order ID
            
        Raises:
            RuntimeError: If connection not ready
            ValueError: If invalid parameters
        """
        if not self.cm.is_ready():
            raise RuntimeError("Connection manager not ready")
        
        # Validate parameters
        if order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and limit_price is None:
            raise ValueError(f"{order_type} order requires limit_price")
        
        if order_type in [OrderType.STOP, OrderType.STOP_LIMIT] and stop_price is None:
            raise ValueError(f"{order_type} order requires stop_price")
        
        # Apply rate limiting
        IBRateLimiters.ORDERS.wait_if_needed(operation=f"place {action.value} {contract.symbol}")
        
        # Get order ID
        order_id = self.cm.next_valid_order_id
        self.cm.next_valid_order_id += 1
        
        # Create IB order
        ib_order = IBOrder()
        ib_order.action = action.value
        ib_order.totalQuantity = quantity
        ib_order.orderType = order_type.value
        
        if limit_price is not None:
            ib_order.lmtPrice = limit_price
        
        if stop_price is not None:
            ib_order.auxPrice = stop_price
        
        # Create internal order record
        order = Order(
            order_id=order_id,
            symbol=contract.symbol,
            action=action.value,
            quantity=quantity,
            order_type=order_type.value,
            limit_price=limit_price,
            stop_price=stop_price,
            status=OrderStatus.PENDING_SUBMIT,
            filled=0,
            remaining=quantity,
            avg_fill_price=0.0
        )
        
        self._orders[order_id] = order
        self._executions[order_id] = []
        
        if callback:
            self._order_callbacks[order_id] = callback
        
        # Place order with IB
        ib_contract = contract.to_ib_contract()
        self.cm.placeOrder(order_id, ib_contract, ib_order)
        
        logger.info(
            f"Placed order: {order_type.value} {action.value} {quantity} {contract.symbol} "
            f"(order_id={order_id})"
        )
        
        return order_id
    
    def cancel_order(self, order_id: int) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancel request sent successfully
        """
        if not self.cm.is_ready():
            raise RuntimeError("Connection manager not ready")
        
        if order_id not in self._orders:
            logger.warning(f"Cannot cancel unknown order: {order_id}")
            return False
        
        # Apply rate limiting
        IBRateLimiters.ORDERS.wait_if_needed(operation=f"cancel order {order_id}")
        
        self.cm.cancelOrder(order_id)
        logger.info(f"Sent cancel request for order {order_id}")
        
        return True
    
    def modify_order(
        self,
        order_id: int,
        quantity: Optional[int] = None,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None
    ) -> bool:
        """
        Modify an existing order.
        
        Args:
            order_id: Order ID to modify
            quantity: New quantity (optional)
            limit_price: New limit price (optional)
            stop_price: New stop price (optional)
            
        Returns:
            True if modification request sent successfully
            
        Note:
            At least one parameter must be provided to modify.
            Order is re-submitted with updated parameters.
        """
        if not self.cm.is_ready():
            raise RuntimeError("Connection manager not ready")
        
        if order_id not in self._orders:
            logger.warning(f"Cannot modify unknown order: {order_id}")
            return False
        
        order = self._orders[order_id]
        
        # Check if any modification requested
        if quantity is None and limit_price is None and stop_price is None:
            logger.warning("No modifications specified for order")
            return False
        
        # Apply rate limiting
        IBRateLimiters.ORDERS.wait_if_needed(operation=f"modify order {order_id}")
        
        # Update order parameters
        if quantity is not None:
            order.quantity = quantity
            order.remaining = quantity - order.filled
        
        if limit_price is not None:
            order.limit_price = limit_price
        
        if stop_price is not None:
            order.stop_price = stop_price
        
        # Create IB order with updated parameters
        ib_order = IBOrder()
        ib_order.action = order.action
        ib_order.totalQuantity = order.quantity
        ib_order.orderType = order.order_type
        ib_order.tif = order.tif
        ib_order.transmit = order.transmit
        ib_order.outsideRth = order.outside_rth
        
        if order.limit_price is not None:
            ib_order.lmtPrice = order.limit_price
        
        if order.stop_price is not None:
            ib_order.auxPrice = order.stop_price
        
        # Re-submit order with same ID
        contract = Contract(symbol=order.symbol, sec_type="STK", exchange="SMART", currency="USD")
        ib_contract = contract.to_ib_contract()
        self.cm.placeOrder(order_id, ib_contract, ib_order)
        
        logger.info(f"Modified order {order_id}: qty={order.quantity}, "
                   f"lmt={order.limit_price}, stp={order.stop_price}")
        
        return True
    
    def request_open_orders(self):
        """
        Request all open orders from IB.
        
        This will trigger openOrder callbacks for all open orders.
        Useful for syncing state after connection.
        """
        if not self.cm.is_ready():
            raise RuntimeError("Connection manager not ready")
        
        self.cm.reqOpenOrders()
        logger.info("Requested open orders from IB")
    
    def get_commission(self, order_id: int) -> Optional[float]:
        """Get commission paid for an order."""
        return self._commissions.get(order_id)
    
    def get_order(self, order_id: int) -> Optional[Order]:
        """Get order by ID."""
        return self._orders.get(order_id)
    
    def get_order_status(self, order_id: int) -> Optional[OrderUpdate]:
        """Get latest status update for an order."""
        return self._order_status.get(order_id)
    
    def get_executions(self, order_id: int) -> List[OrderExecution]:
        """Get all executions for an order."""
        return self._executions.get(order_id, [])
    
    def get_all_orders(self) -> List[Order]:
        """Get all orders."""
        return list(self._orders.values())
    
    def get_active_orders(self) -> List[Order]:
        """Get all active (not filled/cancelled) orders."""
        return [
            order for order in self._orders.values()
            if order.status not in [OrderStatus.FILLED, OrderStatus.CANCELLED]
        ]
    
    def _handle_open_order(self, orderId: int, contract: IBContract, 
                          order: IBOrder, orderState):
        """Handle openOrder callback from IB."""
        logger.debug(f"openOrder: {orderId} {contract.symbol} {order.action} "
                    f"{order.totalQuantity} status={orderState.status}")
        
        # Update order if we're tracking it
        if orderId in self._orders:
            self._orders[orderId].status = orderState.status
    
    def _handle_order_status(self, orderId: int, status: str, filled: float,
                            remaining: float, avgFillPrice: float):
        """Handle orderStatus callback from IB."""
        logger.info(f"orderStatus: {orderId} status={status} filled={filled:.0f} "
                   f"remaining={remaining:.0f} avgPrice={avgFillPrice:.2f}")
        
        # Create status update
        update = OrderUpdate(
            order_id=orderId,
            status=status,
            filled=int(filled),
            remaining=int(remaining),
            avg_fill_price=avgFillPrice
        )
        
        self._order_status[orderId] = update
        
        # Update tracked order
        if orderId in self._orders:
            order = self._orders[orderId]
            order.status = status
            order.filled = int(filled)
            order.remaining = int(remaining)
            order.avg_fill_price = avgFillPrice
        
        # Call user callback
        if orderId in self._order_callbacks:
            try:
                self._order_callbacks[orderId](update)
            except Exception as e:
                logger.error(f"Error in order callback: {e}")
    
    def _handle_exec_details(self, reqId: int, contract: IBContract, execution: Execution):
        """Handle execDetails callback from IB."""
        order_id = execution.orderId
        
        exec_record = OrderExecution(
            order_id=order_id,
            exec_id=execution.execId,
            timestamp=datetime.strptime(execution.time, "%Y%m%d  %H:%M:%S"),
            symbol=contract.symbol,
            side=execution.side,
            shares=int(execution.shares),
            price=execution.price
        )
        
        logger.info(f"Execution: {exec_record}")
        
        # Store execution
        if order_id not in self._executions:
            self._executions[order_id] = []
        self._executions[order_id].append(exec_record)
        
        # Call user callback
        if order_id in self._execution_callbacks:
            try:
                self._execution_callbacks[order_id](exec_record)
            except Exception as e:
                logger.error(f"Error in execution callback: {e}")
    
    def _handle_commission_report(self, commissionReport):
        """Handle commissionReport callback from IB."""
        exec_id = commissionReport.execId
        commission = commissionReport.commission
        
        # Find order_id from execution records
        order_id = None
        for oid, execs in self._executions.items():
            for exec_record in execs:
                if exec_record.exec_id == exec_id:
                    order_id = oid
                    exec_record.commission = commission
                    break
            if order_id:
                break
        
        if order_id:
            # Update total commission for order
            if order_id not in self._commissions:
                self._commissions[order_id] = 0.0
            self._commissions[order_id] += commission
            
            logger.info(f"Commission: order {order_id}, exec {exec_id}, ${commission:.2f}")
        else:
            logger.warning(f"Received commission for unknown execution: {exec_id}")
    
    def __repr__(self) -> str:
        active = len(self.get_active_orders())
        total = len(self._orders)
        return f"OrderExecutionAdapter({active} active / {total} total orders)"
