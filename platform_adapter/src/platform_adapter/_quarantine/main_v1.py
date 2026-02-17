"""
Platform Adapter Main Application

Integrates all components into a unified trading platform adapter:
- Connection management
- Market data streaming
- Order execution
- Account management
- State management

Author: Platform Adapter Team
Created: 2026-01-27
"""

import sys
import time
import signal
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import yaml

from src.platform_adapter.core.connection_manager import ConnectionManager
from src.platform_adapter.core.state_manager import StateManager
from src.platform_adapter.adapters.market_data_adapter import MarketDataAdapter
from src.platform_adapter.adapters.order_execution_adapter import OrderExecutionAdapter
from src.platform_adapter.adapters.account_manager import AccountManager
from src.platform_adapter.utils.logger import setup_logger
from loguru import logger


class PlatformAdapter:
    """
    Main Platform Adapter class integrating all components.
    
    Provides unified interface for:
    - IB Gateway connection management
    - Real-time market data
    - Historical market data
    - Order placement and management
    - Account information and positions
    - Unified state management
    """
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialize Platform Adapter with configuration.
        
        Args:
            config_path: Path to YAML configuration file
        """
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Setup logging
        log_config = self.config.get('logging', {})
        setup_logger(
            log_dir=log_config.get('log_dir', 'logs'),
            level=log_config.get('level', 'INFO'),
            rotation=log_config.get('rotation', '00:00'),
            retention_days=log_config.get('retention_days', 7),
            console=True
        )
        
        logger.info("Initializing Platform Adapter")
        
        # Core components
        self._connection: Optional[ConnectionManager] = None
        self._state: Optional[StateManager] = None
        
        # Adapters
        self._market_data: Optional[MarketDataAdapter] = None
        self._orders: Optional[OrderExecutionAdapter] = None
        self._account: Optional[AccountManager] = None
        
        # Connection state
        self._connected = False
        self._shutdown_requested = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("Platform Adapter initialized")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Configuration dictionary
        """
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        return config
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.warning(f"Received signal {signum}, initiating graceful shutdown...")
        self._shutdown_requested = True
        self.disconnect()
        sys.exit(0)
    
    def connect(self, 
                host: Optional[str] = None,
                port: Optional[int] = None,
                client_id: Optional[int] = None) -> bool:
        """
        Connect to IB Gateway and initialize all components.
        
        Args:
            host: IB Gateway host (overrides config)
            port: IB Gateway port (overrides config)
            client_id: Client ID (overrides config)
            
        Returns:
            True if connected successfully, False otherwise
        """
        if self._connected:
            logger.warning("Already connected")
            return True
        
        try:
            # Get connection parameters
            conn_config = self.config['ib_connection']
            host = host or conn_config['host']
            port = port or conn_config['port']
            client_id = client_id or conn_config['client_id']
            timeout = conn_config.get('timeout', 30)
            
            logger.info(f"Connecting to IB Gateway at {host}:{port} (client_id={client_id})")
            
            # Initialize core components
            self._connection = ConnectionManager()
            self._state = StateManager()
            
            # Initialize adapters
            self._market_data = MarketDataAdapter(self._connection)
            self._orders = OrderExecutionAdapter(self._connection)
            self._account = AccountManager(self._connection)
            
            # Connect to IB Gateway
            success = self._connection.connect_to_ib(host, port, client_id, timeout)
            
            if success:
                self._connected = True
                logger.info("✅ Platform Adapter connected successfully")
                
                # Setup state update callbacks
                self._setup_state_callbacks()
                
                return True
            else:
                logger.error("❌ Failed to connect to IB Gateway")
                return False
                
        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            return False
    
    def _setup_state_callbacks(self):
        """Setup callbacks to update unified state from adapters."""
        # Account callbacks
        def on_position_update(position):
            self._state.update_position(position)
        
        def on_account_value_update(account_value):
            self._state.update_account_value(account_value)
        
        self._account.add_position_callback(on_position_update)
        self._account.add_account_callback(on_account_value_update)
        
        logger.debug("State update callbacks configured")
    
    def disconnect(self):
        """Disconnect from IB Gateway and cleanup resources."""
        if not self._connected:
            logger.warning("Not connected")
            return
        
        logger.info("Disconnecting Platform Adapter...")
        
        try:
            # Unsubscribe from real-time updates
            if self._account:
                self._account.subscribe_account_updates(subscribe=False)
            
            # Disconnect connection manager
            if self._connection:
                self._connection.disconnect_from_ib()
            
            self._connected = False
            logger.info("✅ Platform Adapter disconnected successfully")
            
        except Exception as e:
            logger.error(f"❌ Error during disconnect: {e}")
    
    # ============================================================================
    # MARKET DATA INTERFACE
    # ============================================================================
    
    def subscribe_market_data(self, symbol: str, callback: Callable) -> bool:
        """
        Subscribe to real-time market data for a symbol.
        
        Args:
            symbol: Symbol to subscribe to
            callback: Callback function(symbol, quote) - receives symbol and Quote object
            
        Returns:
            True if subscription successful
        """
        self._ensure_connected()
        from src.platform_adapter.models.contract import Contract
        
        # Create contract for symbol
        contract = Contract(symbol=symbol, sec_type="STK", exchange="SMART", currency="USD")
        
        # Wrap callback to provide both symbol and quote
        def wrapped_callback(quote):
            callback(symbol, quote)
        
        # Subscribe
        req_id = self._market_data.subscribe_market_data(contract, wrapped_callback)
        return req_id is not None
    
    def unsubscribe_market_data(self, symbol: str):
        """
        Unsubscribe from real-time market data.
        
        Args:
            symbol: Symbol to unsubscribe from
        """
        self._ensure_connected()
        # Note: Need to track req_ids by symbol to properly unsubscribe
        # For now, this is a simplified implementation
        logger.warning("Unsubscribe not yet implemented with symbol tracking")
    
    def get_historical_data(self, symbol: str, duration: str = "1 D", 
                           bar_size: str = "1 min") -> list:
        """
        Get historical market data.
        
        Args:
            symbol: Symbol to get data for
            duration: Duration string (e.g., "1 D", "1 W")
            bar_size: Bar size (e.g., "1 min", "5 mins", "1 hour")
            
        Returns:
            List of historical bars
        """
        self._ensure_connected()
        return self._market_data.request_historical_data(
            symbol=symbol,
            duration=duration,
            bar_size=bar_size,
            what_to_show="TRADES"
        )
    
    # ============================================================================
    # ORDER EXECUTION INTERFACE
    # ============================================================================
    
    def place_market_order(self, symbol: str, action: str, quantity: int) -> int:
        """
        Place a market order.
        
        Args:
            symbol: Symbol to trade
            action: "BUY" or "SELL"
            quantity: Number of shares
            
        Returns:
            Order ID
        """
        self._ensure_connected()
        from src.platform_adapter.adapters.order_execution_adapter import OrderAction, OrderType
        
        order_id = self._orders.place_order(
            symbol=symbol,
            action=OrderAction(action),
            quantity=quantity,
            order_type=OrderType.MARKET
        )
        
        # Update state
        if order_id:
            time.sleep(0.5)  # Wait for order status
            order = self._orders.get_order(order_id)
            if order:
                self._state.update_order(order)
        
        return order_id
    
    def place_limit_order(self, symbol: str, action: str, quantity: int, 
                         limit_price: float) -> int:
        """
        Place a limit order.
        
        Args:
            symbol: Symbol to trade
            action: "BUY" or "SELL"
            quantity: Number of shares
            limit_price: Limit price
            
        Returns:
            Order ID
        """
        self._ensure_connected()
        from src.platform_adapter.adapters.order_execution_adapter import OrderAction, OrderType
        
        order_id = self._orders.place_order(
            symbol=symbol,
            action=OrderAction(action),
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price
        )
        
        # Update state
        if order_id:
            time.sleep(0.5)
            order = self._orders.get_order(order_id)
            if order:
                self._state.update_order(order)
        
        return order_id
    
    def cancel_order(self, order_id: int) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancellation successful
        """
        self._ensure_connected()
        success = self._orders.cancel_order(order_id)
        
        # Update state
        if success:
            time.sleep(0.5)
            order = self._orders.get_order(order_id)
            if order:
                self._state.update_order(order)
        
        return success
    
    def get_order_status(self, order_id: int) -> Optional[str]:
        """
        Get order status.
        
        Args:
            order_id: Order ID to query
            
        Returns:
            Order status string or None
        """
        self._ensure_connected()
        return self._orders.get_order_status(order_id)
    
    def get_all_orders(self) -> list:
        """
        Get all orders from state.
        
        Returns:
            List of Order objects
        """
        return self._state.get_all_orders()
    
    def get_active_orders(self) -> list:
        """
        Get all active orders from state.
        
        Returns:
            List of active Order objects
        """
        return self._state.get_active_orders()
    
    # ============================================================================
    # ACCOUNT INTERFACE
    # ============================================================================
    
    def get_account_summary(self) -> Dict[str, Any]:
        """
        Get account summary with all values.
        
        Returns:
            Dictionary of account values
        """
        self._ensure_connected()
        account_values = self._account.get_account_summary(block=True, timeout=5.0)
        
        # Update state
        if account_values:
            self._state.update_account_values(list(account_values.values()))
        
        return account_values
    
    def get_positions(self) -> list:
        """
        Get all current positions.
        
        Returns:
            List of Position objects
        """
        self._ensure_connected()
        positions = self._account.get_positions(block=True, timeout=5.0)
        
        # Update state
        if positions:
            self._state.update_positions(positions)
        
        return positions
    
    def get_account_value(self, key: str) -> Optional[str]:
        """
        Get specific account value from state.
        
        Args:
            key: Account value key (e.g., 'NetLiquidation')
            
        Returns:
            Account value or None
        """
        av = self._state.get_account_value(key)
        return av.value if av else None
    
    def get_position(self, symbol: str):
        """
        Get specific position from state.
        
        Args:
            symbol: Symbol to query
            
        Returns:
            Position object or None
        """
        return self._state.get_position(symbol)
    
    def subscribe_account_updates(self):
        """Subscribe to real-time account updates."""
        self._ensure_connected()
        self._account.subscribe_account_updates(subscribe=True)
        logger.info("Subscribed to real-time account updates")
    
    # ============================================================================
    # STATE INTERFACE
    # ============================================================================
    
    def get_state_summary(self) -> Dict[str, Any]:
        """
        Get complete state summary.
        
        Returns:
            Dictionary with state counts and metadata
        """
        return self._state.get_state_summary()
    
    def reconcile_state(self):
        """
        Reconcile cached state with IB Gateway.
        
        Syncs positions and orders with authoritative source.
        """
        self._ensure_connected()
        
        logger.info("Reconciling state with IB Gateway...")
        
        # Reconcile positions
        positions = self._account.get_positions(block=True, timeout=5.0)
        if positions:
            pos_result = self._state.reconcile_positions(positions)
            logger.info(f"Positions reconciled: {pos_result}")
        
        # Reconcile orders
        self._orders.request_open_orders()
        time.sleep(1.0)  # Wait for orders
        orders = self._orders.get_all_orders()
        if orders:
            ord_result = self._state.reconcile_orders(orders)
            logger.info(f"Orders reconciled: {ord_result}")
    
    # ============================================================================
    # UTILITY METHODS
    # ============================================================================
    
    def _ensure_connected(self):
        """Ensure platform is connected, raise exception if not."""
        if not self._connected:
            raise RuntimeError("Platform Adapter not connected. Call connect() first.")
    
    @property
    def is_connected(self) -> bool:
        """Check if platform is connected."""
        return self._connected
    
    @property
    def connection(self) -> ConnectionManager:
        """Get connection manager."""
        return self._connection
    
    @property
    def state(self) -> StateManager:
        """Get state manager."""
        return self._state
    
    @property
    def market_data(self) -> MarketDataAdapter:
        """Get market data adapter."""
        return self._market_data
    
    @property
    def orders(self) -> OrderExecutionAdapter:
        """Get order execution adapter."""
        return self._orders
    
    @property
    def account(self) -> AccountManager:
        """Get account manager."""
        return self._account
    
    def __repr__(self) -> str:
        """String representation."""
        status = "connected" if self._connected else "disconnected"
        return f"PlatformAdapter(status={status})"


def main():
    """Example usage of Platform Adapter."""
    # Initialize
    pa = PlatformAdapter()
    
    # Connect
    if not pa.connect():
        logger.error("Failed to connect")
        return
    
    try:
        # Get account summary
        logger.info("\n=== Account Summary ===")
        account = pa.get_account_summary()
        for key, av in account.items():
            logger.info(f"{key}: {av.value} {av.currency}")
        
        # Get positions
        logger.info("\n=== Positions ===")
        positions = pa.get_positions()
        if positions:
            for pos in positions:
                logger.info(f"{pos.symbol}: {pos.quantity} @ {pos.avg_cost}")
        else:
            logger.info("No positions")
        
        # Subscribe to real-time data
        logger.info("\n=== Market Data ===")
        def on_quote(symbol, data):
            logger.info(f"{symbol}: {data}")
        
        pa.subscribe_market_data("AAPL", on_quote)
        
        # Subscribe to account updates
        pa.subscribe_account_updates()
        
        # Keep running
        logger.info("\n=== Running (Ctrl+C to stop) ===")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    finally:
        pa.disconnect()


if __name__ == "__main__":
    main()
