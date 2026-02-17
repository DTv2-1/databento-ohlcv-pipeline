"""
Position model — broker fact, no derived math.

PA 2.0: Position is a pure data container for what the broker tells us.
market_value and unrealized_pnl belong downstream (MIC), not here.
"""

from dataclasses import dataclass


@dataclass
class Position:
    """
    Represents a trading position (broker fact).
    
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
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0
    
    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0
    
    @property
    def is_flat(self) -> bool:
        """Check if position is flat (zero)."""
        return self.quantity == 0
    
    def __repr__(self) -> str:
        direction = "LONG" if self.is_long else "SHORT" if self.is_short else "FLAT"
        return f"Position({self.symbol}: {direction} {abs(self.quantity)} @ ${self.avg_cost:.2f})"
