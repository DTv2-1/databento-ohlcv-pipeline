"""
Contract model for representing financial instruments
Provides conversion to/from IB API Contract objects
"""

from dataclasses import dataclass
from typing import Optional
from ibapi.contract import Contract as IBContract


@dataclass
class Contract:
    """
    Represents a financial instrument contract.
    
    Attributes:
        symbol: Trading symbol (e.g., "AAPL", "SPY")
        sec_type: Security type (STK=Stock, OPT=Option, FUT=Future, etc.)
        exchange: Exchange code (SMART for smart routing)
        currency: Currency code (USD, EUR, etc.)
        primary_exchange: Primary exchange (optional, for stocks)
        last_trade_date: Expiration date for derivatives (YYYYMMDD format)
        strike: Strike price for options
        right: Option right (C=Call, P=Put)
        multiplier: Contract multiplier
        local_symbol: Local exchange symbol
        con_id: IB contract ID
    """
    
    symbol: str
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"
    primary_exchange: Optional[str] = None
    last_trade_date: Optional[str] = None
    strike: Optional[float] = None
    right: Optional[str] = None
    multiplier: Optional[str] = None
    local_symbol: Optional[str] = None
    con_id: Optional[int] = None
    
    def to_ib_contract(self) -> IBContract:
        """
        Convert to IB API Contract object.
        
        Returns:
            IBContract: IB API contract object
        """
        contract = IBContract()
        contract.symbol = self.symbol
        contract.secType = self.sec_type
        contract.exchange = self.exchange
        contract.currency = self.currency
        
        if self.primary_exchange:
            contract.primaryExchange = self.primary_exchange
        if self.last_trade_date:
            contract.lastTradeDateOrContractMonth = self.last_trade_date
        if self.strike is not None:
            contract.strike = self.strike
        if self.right:
            contract.right = self.right
        if self.multiplier:
            contract.multiplier = self.multiplier
        if self.local_symbol:
            contract.localSymbol = self.local_symbol
        if self.con_id:
            contract.conId = self.con_id
            
        return contract
    
    @classmethod
    def from_ib_contract(cls, ib_contract: IBContract) -> "Contract":
        """
        Create Contract from IB API Contract object.
        
        Args:
            ib_contract: IB API contract object
            
        Returns:
            Contract: Platform adapter contract object
        """
        return cls(
            symbol=ib_contract.symbol,
            sec_type=ib_contract.secType,
            exchange=ib_contract.exchange,
            currency=ib_contract.currency,
            primary_exchange=ib_contract.primaryExchange if ib_contract.primaryExchange else None,
            last_trade_date=ib_contract.lastTradeDateOrContractMonth if ib_contract.lastTradeDateOrContractMonth else None,
            strike=ib_contract.strike if ib_contract.strike else None,
            right=ib_contract.right if ib_contract.right else None,
            multiplier=ib_contract.multiplier if ib_contract.multiplier else None,
            local_symbol=ib_contract.localSymbol if ib_contract.localSymbol else None,
            con_id=ib_contract.conId if ib_contract.conId else None
        )
    
    @classmethod
    def stock(cls, symbol: str, exchange: str = "SMART", currency: str = "USD") -> "Contract":
        """
        Create a stock contract.
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            exchange: Exchange (default: SMART)
            currency: Currency (default: USD)
            
        Returns:
            Contract: Stock contract
        """
        return cls(symbol=symbol, sec_type="STK", exchange=exchange, currency=currency)
    
    def __repr__(self) -> str:
        """String representation"""
        if self.sec_type == "STK":
            return f"Contract(STK: {self.symbol} @ {self.exchange})"
        elif self.sec_type == "OPT":
            return f"Contract(OPT: {self.symbol} {self.strike}{self.right} {self.last_trade_date})"
        elif self.sec_type == "FUT":
            return f"Contract(FUT: {self.symbol} {self.last_trade_date})"
        else:
            return f"Contract({self.sec_type}: {self.symbol})"
