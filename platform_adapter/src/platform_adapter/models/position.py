"""
Position model for representing trading positions
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Position:
    """
    Represents a trading position.
    
    Attributes:
        symbol: Contract symbol
        quantity: Position size (positive=long, negative=short)
        avg_cost: Average cost per share
        account: Account ID
        sec_type: Security type (STK, FUT, OPT, etc.)
        exchange: Exchange
        currency: Currency
    """
    
    symbol: str
    quantity: int
    avg_cost: float
    account: str
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"
    
    @property
    def market_value(self) -> Optional[float]:
        """Calculate market value if current price available"""
        # This would require current market price
        # Will be implemented when market data is available
        return None
    
    @property
    def unrealized_pnl(self) -> Optional[float]:
        """Calculate unrealized P&L if current price available"""
        # This would require current market price
        # Will be implemented when market data is available
        return None
    
    @property
    def is_long(self) -> bool:
        """Check if position is long"""
        return self.quantity > 0
    
    @property
    def is_short(self) -> bool:
        """Check if position is short"""
        return self.quantity < 0
    
    @property
    def is_flat(self) -> bool:
        """Check if position is flat (zero)"""
        return self.quantity == 0
    
    def __repr__(self) -> str:
        """String representation"""
        direction = "LONG" if self.is_long else "SHORT" if self.is_short else "FLAT"
        return f"Position({self.symbol}: {direction} {abs(self.quantity)} @ ${self.avg_cost:.2f})"
