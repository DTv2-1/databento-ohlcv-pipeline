"""
Account model for representing account information
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class AccountSummary:
    """
    Represents account summary information.
    
    Attributes:
        account_id: Account ID
        net_liquidation: Net liquidation value
        total_cash: Total cash balance
        buying_power: Buying power
        gross_position_value: Gross position value
        available_funds: Available funds
        excess_liquidity: Excess liquidity
        equity_with_loan: Equity with loan value
        cushion: Cushion percentage
        leverage: Leverage ratio
        values: Dictionary of all account values
    """
    
    account_id: str
    net_liquidation: Optional[float] = None
    total_cash: Optional[float] = None
    buying_power: Optional[float] = None
    gross_position_value: Optional[float] = None
    available_funds: Optional[float] = None
    excess_liquidity: Optional[float] = None
    equity_with_loan: Optional[float] = None
    cushion: Optional[float] = None
    leverage: Optional[float] = None
    values: Dict[str, str] = field(default_factory=dict)
    
    def update_value(self, key: str, value: str, currency: str = "USD"):
        """
        Update an account value.
        
        Args:
            key: Account value key
            value: Account value
            currency: Currency code
        """
        self.values[key] = value
        
        # Update specific attributes for commonly used values
        try:
            float_value = float(value)
            
            if key == "NetLiquidation":
                self.net_liquidation = float_value
            elif key == "TotalCashValue":
                self.total_cash = float_value
            elif key == "BuyingPower":
                self.buying_power = float_value
            elif key == "GrossPositionValue":
                self.gross_position_value = float_value
            elif key == "AvailableFunds":
                self.available_funds = float_value
            elif key == "ExcessLiquidity":
                self.excess_liquidity = float_value
            elif key == "EquityWithLoanValue":
                self.equity_with_loan = float_value
            elif key == "Cushion":
                self.cushion = float_value
            elif key == "Leverage":
                self.leverage = float_value
        except (ValueError, TypeError):
            # Some values might not be numeric
            pass
    
    def get_value(self, key: str) -> Optional[str]:
        """
        Get an account value by key.
        
        Args:
            key: Account value key
            
        Returns:
            Account value or None if not found
        """
        return self.values.get(key)
    
    def __repr__(self) -> str:
        """String representation"""
        return f"AccountSummary({self.account_id}: NetLiq=${self.net_liquidation:.2f}, Cash=${self.total_cash:.2f})"


@dataclass
class AccountValue:
    """
    Represents a single account value update.
    
    Attributes:
        key: Value key (e.g., "NetLiquidation")
        value: Value as string
        currency: Currency code
        account: Account ID
    """
    
    key: str
    value: str
    currency: str
    account: str
    
    def __repr__(self) -> str:
        """String representation"""
        return f"AccountValue({self.key}={self.value} {self.currency} [{self.account}])"
