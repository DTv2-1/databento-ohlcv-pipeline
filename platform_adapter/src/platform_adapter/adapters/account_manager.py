"""
Account Manager
Handles account information, positions, and account value updates from IB

Author: Platform Adapter Team
Date: January 27, 2026
"""

from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger

from ibapi.contract import Contract as IBContract

from ..core.connection_manager import ConnectionManager
from ..models.position import Position
from ..utils.rate_limiter import IBRateLimiters


@dataclass
class AccountValue:
    """Account value update"""
    key: str
    value: str
    currency: str
    account: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __repr__(self) -> str:
        return f"AccountValue({self.key}={self.value} {self.currency})"


class AccountManager:
    """
    Adapter for account management via IB API.
    
    Handles:
    - Account summary retrieval
    - Position tracking
    - Account value updates
    - Real-time account updates subscription
    """
    
    def __init__(self, connection_manager: ConnectionManager):
        """
        Initialize account manager.
        
        Args:
            connection_manager: Active IB connection
        """
        self.cm = connection_manager
        
        # Account data
        self._account_summary: Dict[str, AccountValue] = {}
        self._positions: Dict[str, Position] = {}
        self._account_values: Dict[str, AccountValue] = {}
        
        # Request tracking
        self._summary_complete = False
        self._positions_complete = False
        
        # Callbacks
        self._account_callbacks: List[Callable[[AccountValue], None]] = []
        self._position_callbacks: List[Callable[[Position], None]] = []
        
        # Register IB callbacks
        self._register_callbacks()
        
        logger.info("AccountManager initialized")
    
    def _register_callbacks(self):
        """Register IB API callbacks for account events."""
        
        # accountSummary callback
        original_account_summary = self.cm.accountSummary
        def account_summary_handler(reqId: int, account: str, tag: str, 
                                   value: str, currency: str):
            self._handle_account_summary(reqId, account, tag, value, currency)
            if original_account_summary:
                original_account_summary(reqId, account, tag, value, currency)
        self.cm.accountSummary = account_summary_handler
        
        # accountSummaryEnd callback
        original_account_summary_end = self.cm.accountSummaryEnd
        def account_summary_end_handler(reqId: int):
            self._handle_account_summary_end(reqId)
            if original_account_summary_end:
                original_account_summary_end(reqId)
        self.cm.accountSummaryEnd = account_summary_end_handler
        
        # position callback
        original_position = self.cm.position
        def position_handler(account: str, contract: IBContract, 
                            position: float, avgCost: float):
            self._handle_position(account, contract, position, avgCost)
            if original_position:
                original_position(account, contract, position, avgCost)
        self.cm.position = position_handler
        
        # positionEnd callback
        original_position_end = self.cm.positionEnd
        def position_end_handler():
            self._handle_position_end()
            if original_position_end:
                original_position_end()
        self.cm.positionEnd = position_end_handler
        
        # updateAccountValue callback
        original_update_account_value = self.cm.updateAccountValue
        def update_account_value_handler(key: str, val: str, currency: str, accountName: str):
            self._handle_update_account_value(key, val, currency, accountName)
            if original_update_account_value:
                original_update_account_value(key, val, currency, accountName)
        self.cm.updateAccountValue = update_account_value_handler
        
        logger.info("Account manager callbacks registered")
    
    def get_account_summary(self, block: bool = True, timeout: float = 5.0) -> Dict[str, AccountValue]:
        """
        Get account summary information.
        
        Args:
            block: Whether to block until data received
            timeout: Timeout in seconds if blocking
            
        Returns:
            Dictionary of account values by key
        """
        if not self.cm.is_ready():
            raise RuntimeError("Connection manager not ready")
        
        # Apply rate limiting
        IBRateLimiters.ACCOUNT.wait_if_needed(operation="account summary")
        
        # Request account summary
        req_id = 9001
        self._summary_complete = False
        self._account_summary.clear()
        
        # Request all tags
        tags = "AccountType,NetLiquidation,TotalCashValue,SettledCash,AccruedCash,BuyingPower,EquityWithLoanValue,GrossPositionValue,AvailableFunds,ExcessLiquidity,Cushion,FullMaintMarginReq,FullInitMarginReq"
        
        self.cm.reqAccountSummary(req_id, "All", tags)
        logger.info("Requested account summary")
        
        if block:
            # Wait for completion
            import time
            start = time.time()
            while not self._summary_complete and (time.time() - start) < timeout:
                time.sleep(0.1)
            
            if not self._summary_complete:
                logger.warning(f"Account summary request timed out after {timeout}s")
        
        return self._account_summary.copy()
    
    def get_positions(self, block: bool = True, timeout: float = 5.0) -> List[Position]:
        """
        Get current positions.
        
        Args:
            block: Whether to block until data received
            timeout: Timeout in seconds if blocking
            
        Returns:
            List of positions
        """
        if not self.cm.is_ready():
            raise RuntimeError("Connection manager not ready")
        
        # Apply rate limiting
        IBRateLimiters.ACCOUNT.wait_if_needed(operation="positions")
        
        # Request positions
        self._positions_complete = False
        self._positions.clear()
        
        self.cm.reqPositions()
        logger.info("Requested positions")
        
        if block:
            # Wait for completion
            import time
            start = time.time()
            while not self._positions_complete and (time.time() - start) < timeout:
                time.sleep(0.1)
            
            if not self._positions_complete:
                logger.warning(f"Positions request timed out after {timeout}s")
        
        return list(self._positions.values())
    
    def subscribe_account_updates(self, subscribe: bool = True) -> bool:
        """
        Subscribe to real-time account updates.
        
        Args:
            subscribe: True to subscribe, False to unsubscribe
            
        Returns:
            True if request sent successfully
        """
        if not self.cm.is_ready():
            raise RuntimeError("Connection manager not ready")
        
        # Get account name
        account = self.cm.managed_accounts[0] if self.cm.managed_accounts else ""
        
        if not account:
            logger.error("No managed accounts available")
            return False
        
        self.cm.reqAccountUpdates(subscribe, account)
        
        action = "Subscribed to" if subscribe else "Unsubscribed from"
        logger.info(f"{action} account updates for {account}")
        
        return True
    
    def add_account_callback(self, callback: Callable[[AccountValue], None]):
        """Add callback for account value updates."""
        self._account_callbacks.append(callback)
    
    def add_position_callback(self, callback: Callable[[Position], None]):
        """Add callback for position updates."""
        self._position_callbacks.append(callback)
    
    def get_account_value(self, key: str) -> Optional[AccountValue]:
        """Get specific account value by key."""
        return self._account_values.get(key)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol."""
        return self._positions.get(symbol)
    
    def get_all_account_values(self) -> Dict[str, AccountValue]:
        """Get all account values."""
        return self._account_values.copy()
    
    def _handle_account_summary(self, reqId: int, account: str, tag: str, 
                               value: str, currency: str):
        """Handle accountSummary callback from IB."""
        logger.debug(f"accountSummary: {tag}={value} {currency}")
        
        account_value = AccountValue(
            key=tag,
            value=value,
            currency=currency,
            account=account
        )
        
        self._account_summary[tag] = account_value
    
    def _handle_account_summary_end(self, reqId: int):
        """Handle accountSummaryEnd callback from IB."""
        self._summary_complete = True
        logger.info(f"Account summary complete: {len(self._account_summary)} values")
    
    def _handle_position(self, account: str, contract: IBContract, 
                        position: float, avgCost: float):
        """Handle position callback from IB."""
        pos = Position(
            symbol=contract.symbol,
            quantity=int(position),
            avg_cost=avgCost,
            account=account,
            sec_type=contract.secType,
            exchange=contract.exchange,
            currency=contract.currency
        )
        
        logger.info(f"Position: {pos}")
        
        self._positions[contract.symbol] = pos
        
        # Call user callbacks
        for callback in self._position_callbacks:
            try:
                callback(pos)
            except Exception as e:
                logger.error(f"Error in position callback: {e}")
    
    def _handle_position_end(self):
        """Handle positionEnd callback from IB."""
        self._positions_complete = True
        logger.info(f"Positions complete: {len(self._positions)} positions")
    
    def _handle_update_account_value(self, key: str, val: str, 
                                     currency: str, accountName: str):
        """Handle updateAccountValue callback from IB."""
        logger.debug(f"updateAccountValue: {key}={val} {currency}")
        
        account_value = AccountValue(
            key=key,
            value=val,
            currency=currency,
            account=accountName
        )
        
        self._account_values[key] = account_value
        
        # Call user callbacks
        for callback in self._account_callbacks:
            try:
                callback(account_value)
            except Exception as e:
                logger.error(f"Error in account callback: {e}")
    
    def __repr__(self) -> str:
        positions_count = len(self._positions)
        values_count = len(self._account_values)
        return f"AccountManager({positions_count} positions, {values_count} values)"
