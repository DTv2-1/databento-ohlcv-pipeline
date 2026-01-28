"""
Order model for representing trading orders
Provides conversion to/from IB API Order objects
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum
from ibapi.order import Order as IBOrder


class OrderStatus(str, Enum):
    """Order status values from IB API"""
    PENDING_SUBMIT = "PendingSubmit"
    PENDING_CANCEL = "PendingCancel"
    PRE_SUBMITTED = "PreSubmitted"
    SUBMITTED = "Submitted"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    INACTIVE = "Inactive"
    API_CANCELLED = "ApiCancelled"


@dataclass
class Order:
    """
    Represents a trading order.
    
    Attributes:
        order_id: IB order ID
        symbol: Symbol being traded
        action: BUY or SELL
        quantity: Number of shares/contracts
        order_type: MKT, LMT, STP, STP LMT, etc.
        status: Current order status
        filled: Number of shares filled
        remaining: Number of shares remaining
        avg_fill_price: Average fill price
        limit_price: Limit price (for limit orders)
        stop_price: Stop price (for stop orders)
        tif: Time in force (DAY, GTC, IOC, GTD)
        account: Account to place order for
        transmit: Whether to transmit order immediately
        outside_rth: Allow trading outside regular hours
    """
    
    order_id: int
    symbol: str
    action: str  # BUY or SELL
    quantity: int
    order_type: str = "MKT"
    status: str = OrderStatus.PENDING_SUBMIT
    filled: int = 0
    remaining: int = 0
    avg_fill_price: float = 0.0
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    tif: str = "DAY"
    account: Optional[str] = None
    transmit: bool = True
    outside_rth: bool = False
    
    def to_ib_order(self) -> IBOrder:
        """
        Convert to IB API Order object.
        
        Returns:
            IBOrder: IB API order object
            
        Raises:
            ValueError: If order parameters are invalid
        """
        # Validate action
        if self.action not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid action: {self.action}. Must be BUY or SELL")
        
        # Validate quantity
        if self.quantity <= 0:
            raise ValueError(f"Invalid quantity: {self.quantity}. Must be positive")
        
        # Validate limit/stop prices
        if self.order_type == "LMT" and self.limit_price is None:
            raise ValueError("Limit price required for LMT orders")
        if self.order_type == "STP" and self.stop_price is None:
            raise ValueError("Stop price required for STP orders")
        if self.order_type == "STP LMT" and (self.limit_price is None or self.stop_price is None):
            raise ValueError("Both limit and stop prices required for STP LMT orders")
        
        order = IBOrder()
        order.action = self.action
        order.totalQuantity = self.quantity
        order.orderType = self.order_type
        order.tif = self.tif
        order.transmit = self.transmit
        order.outsideRth = self.outside_rth
        
        if self.limit_price is not None:
            order.lmtPrice = self.limit_price
        
        if self.stop_price is not None:
            order.auxPrice = self.stop_price
        
        if self.account is not None:
            order.account = self.account
        
        return order
    
    @classmethod
    def from_ib_order(cls, ib_order: IBOrder, order_id: int, symbol: str) -> 'Order':
        """
        Create Order from IB API Order object.
        
        Args:
            ib_order: IB API order object
            order_id: Order ID
            symbol: Symbol
            
        Returns:
            Order: Order object
        """
        return cls(
            order_id=order_id,
            symbol=symbol,
            action=ib_order.action,
            quantity=int(ib_order.totalQuantity),
            order_type=ib_order.orderType,
            limit_price=ib_order.lmtPrice if hasattr(ib_order, 'lmtPrice') and ib_order.lmtPrice else None,
            stop_price=ib_order.auxPrice if hasattr(ib_order, 'auxPrice') and ib_order.auxPrice else None,
            tif=ib_order.tif if hasattr(ib_order, 'tif') else "DAY",
            account=ib_order.account if hasattr(ib_order, 'account') and ib_order.account else None,
            transmit=ib_order.transmit if hasattr(ib_order, 'transmit') else True,
            outside_rth=ib_order.outsideRth if hasattr(ib_order, 'outsideRth') else False
        )
    
    def __repr__(self) -> str:
        price_info = ""
        if self.limit_price:
            price_info = f" @ ${self.limit_price:.2f}"
        if self.stop_price:
            price_info += f" stop ${self.stop_price:.2f}"
        
        fill_info = ""
        if self.filled > 0:
            fill_info = f" (filled {self.filled}/{self.quantity} @ ${self.avg_fill_price:.2f})"
        
        return (f"Order(id={self.order_id} {self.action} {self.quantity} {self.symbol} "
                f"{self.order_type}{price_info} status={self.status}{fill_info})")
