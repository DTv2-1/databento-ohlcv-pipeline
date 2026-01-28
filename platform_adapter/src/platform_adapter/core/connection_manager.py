"""
Connection Manager for Interactive Brokers TWS/Gateway
Handles connection, disconnection, and message processing
"""

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from typing import Optional, Callable
import threading
import time
from loguru import logger


class ConnectionManager(EWrapper, EClient):
    """
    Manages connection to IB Gateway/TWS.
    
    Inherits from both EWrapper (callbacks) and EClient (requests).
    Handles connection lifecycle and error handling.
    """
    
    def __init__(self, auto_reconnect: bool = True, max_reconnect_attempts: int = 5):
        EClient.__init__(self, self)
        
        # Connection state
        self.host: Optional[str] = None
        self.port: Optional[int] = None
        self.client_id: Optional[int] = None
        self.is_connected: bool = False
        self.next_valid_order_id: Optional[int] = None
        self.managed_accounts: list = []
        
        # Reconnection settings
        self.auto_reconnect: bool = auto_reconnect
        self.max_reconnect_attempts: int = max_reconnect_attempts
        self.reconnect_count: int = 0
        self.is_reconnecting: bool = False
        
        # Threading
        self.api_thread: Optional[threading.Thread] = None
        self.connection_event = threading.Event()
        
        # Callbacks
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_reconnecting: Optional[Callable] = None
        self.on_reconnect_failed: Optional[Callable] = None
        
    def connect_to_ib(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        timeout: int = 10
    ) -> bool:
        """
        Connect to IB Gateway/TWS.
        
        Args:
            host: IB Gateway host (default: 127.0.0.1)
            port: IB Gateway port (default: 7497 for paper trading)
            client_id: Client ID for this connection
            timeout: Connection timeout in seconds
            
        Returns:
            bool: True if connected successfully, False otherwise
        """
        if self.is_connected:
            logger.warning("Already connected to IB Gateway")
            return True
        
        logger.info(f"Connecting to IB Gateway at {host}:{port} (client_id={client_id})...")
        
        self.host = host
        self.port = port
        self.client_id = client_id
        
        try:
            # Establish connection
            self.connect(host, port, client_id)
            
            # Start message processing thread
            self.api_thread = threading.Thread(target=self.run, daemon=True, name="IB-API")
            self.api_thread.start()
            
            # Wait for connection confirmation
            if self.connection_event.wait(timeout=timeout):
                logger.info(f"✅ Connected successfully! Next Order ID: {self.next_valid_order_id}")
                self.is_connected = True
                
                # Call user callback
                if self.on_connected:
                    self.on_connected()
                
                return True
            else:
                logger.error(f"❌ Connection timeout after {timeout} seconds")
                self.disconnect_from_ib()
                return False
                
        except Exception as e:
            logger.error(f"❌ Connection failed: {str(e)}")
            self.is_connected = False
            return False
    
    def disconnect_from_ib(self, clear_params: bool = False):
        """
        Disconnect from IB Gateway/TWS.
        
        Args:
            clear_params: If True, clear connection parameters (host, port, client_id).
                         Set to False to preserve parameters for reconnection.
        """
        if not self.is_connected:
            logger.warning("Not connected to IB Gateway")
            return
        
        logger.info("Disconnecting from IB Gateway...")
        
        try:
            # Save connection parameters before disconnect (EClient.disconnect() clears them)
            saved_host = self.host
            saved_port = self.port
            saved_client_id = self.client_id
            
            self.disconnect()  # This clears self.host and self.port internally
            self.is_connected = False
            self.connection_event.clear()
            
            # Wait for thread to finish
            if self.api_thread and self.api_thread.is_alive():
                self.api_thread.join(timeout=2)
            
            # Restore connection parameters unless explicitly cleared
            if not clear_params:
                self.host = saved_host
                self.port = saved_port
                self.client_id = saved_client_id
            else:
                self.host = None
                self.port = None
                self.client_id = None
            
            logger.info("✅ Disconnected successfully")
            
            # Call user callback
            if self.on_disconnected:
                self.on_disconnected()
                
        except Exception as e:
            logger.error(f"Error during disconnection: {str(e)}")
    
    def is_ready(self) -> bool:
        """
        Check if connection is ready for trading.
        
        Returns:
            bool: True if connected and have valid order ID
        """
        return self.is_connected and self.next_valid_order_id is not None
    
    def get_next_order_id(self) -> Optional[int]:
        """
        Get next valid order ID and increment for next use.
        
        Returns:
            int: Next valid order ID or None if not connected
        """
        if not self.is_ready():
            logger.error("Cannot get order ID - not connected or no valid ID available")
            return None
        
        order_id = self.next_valid_order_id
        self.next_valid_order_id += 1
        return order_id
    
    # ==================== EWrapper Callbacks ====================
    
    def connectAck(self):
        """Called when connection is acknowledged by IB."""
        logger.debug("Connection acknowledged by IB Gateway")
    
    def nextValidId(self, orderId: int):
        """
        Called when connection is established and provides next valid order ID.
        
        Args:
            orderId: Next valid order ID
        """
        logger.info(f"Received next valid order ID: {orderId}")
        self.next_valid_order_id = orderId
        self.connection_event.set()
    
    def connectionClosed(self):
        """Called when connection is closed."""
        logger.warning("Connection closed by IB Gateway")
        self.is_connected = False
        self.connection_event.clear()
        
        # Call user callback
        if self.on_disconnected:
            self.on_disconnected()
        
        # Attempt reconnection if enabled and not already reconnecting
        if self.auto_reconnect and not self.is_reconnecting:
            self._attempt_reconnection()
    
    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson: str = ""):
        """
        Handle errors and messages from IB.
        
        Args:
            reqId: Request ID (-1 for system messages)
            errorCode: Error code
            errorString: Error description
            advancedOrderRejectJson: Advanced order rejection info
        """
        # Filter informational messages (codes 2104, 2106, 2158)
        if errorCode in [2104, 2106, 2158]:
            logger.debug(f"Info [{errorCode}]: {errorString}")
            return
        
        # Warning messages (2100-2999)
        if 2100 <= errorCode < 3000:
            logger.warning(f"Warning [{errorCode}]: {errorString}")
        # System errors (1100-1300)
        elif 1100 <= errorCode < 1300:
            logger.error(f"System Error [{errorCode}]: {errorString}")
            
            # Handle connection loss
            if errorCode in [1100, 1101, 1102]:
                self.is_connected = False
                self.connection_event.clear()
                
                # Attempt reconnection for error 1100 (connection lost)
                if errorCode == 1100 and self.auto_reconnect and not self.is_reconnecting:
                    logger.info("Connection lost - attempting automatic reconnection...")
                    self._attempt_reconnection()
        # Client/TWS errors
        else:
            logger.error(f"Error [{errorCode}] (ReqId: {reqId}): {errorString}")
        
        # Call user callback
        if self.on_error:
            self.on_error(reqId, errorCode, errorString)
    
    def managedAccounts(self, accountsList: str):
        """
        Called when managed accounts list is received.
        
        Args:
            accountsList: Comma-separated list of account IDs
        """
        self.managed_accounts = accountsList.split(",")
        logger.info(f"Managed accounts: {self.managed_accounts}")
    
    # ==================== Health Check ====================
    
    def health_check(self) -> dict:
        """
        Perform health check on connection.
        
        Returns:
            dict: Health status information
        """
        return {
            "connected": self.is_connected,
            "ready": self.is_ready(),
            "host": self.host,
            "port": self.port,
            "client_id": self.client_id,
            "next_order_id": self.next_valid_order_id,
            "thread_alive": self.api_thread.is_alive() if self.api_thread else False,
            "reconnecting": self.is_reconnecting,
            "reconnect_count": self.reconnect_count
        }
    
    # ==================== Reconnection ====================
    
    def _get_backoff_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay.
        
        Args:
            attempt: Reconnection attempt number (0-indexed)
            
        Returns:
            float: Delay in seconds
        """
        base_delay = 2.0
        max_delay = 60.0
        delay = base_delay * (2 ** attempt)
        return min(delay, max_delay)
    
    def _attempt_reconnection(self):
        """Attempt to reconnect with exponential backoff."""
        if self.is_reconnecting:
            logger.warning("Reconnection already in progress")
            return
        
        self.is_reconnecting = True
        self.reconnect_count = 0
        
        # Run reconnection in separate thread
        reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            daemon=True,
            name="IB-Reconnect"
        )
        reconnect_thread.start()
    
    def _reconnect_loop(self):
        """Reconnection loop with exponential backoff."""
        logger.info(f"Starting reconnection loop (max attempts: {self.max_reconnect_attempts})")
        
        while self.reconnect_count < self.max_reconnect_attempts and not self.is_connected:
            delay = self._get_backoff_delay(self.reconnect_count)
            
            logger.info(
                f"Reconnection attempt {self.reconnect_count + 1}/{self.max_reconnect_attempts} "
                f"in {delay:.1f} seconds..."
            )
            
            # Call user callback
            if self.on_reconnecting:
                self.on_reconnecting(self.reconnect_count + 1, self.max_reconnect_attempts)
            
            time.sleep(delay)
            
            # Attempt reconnection
            if self._reconnect_attempt():
                logger.info("✅ Reconnection successful!")
                self.reconnect_count = 0
                self.is_reconnecting = False
                return
            
            self.reconnect_count += 1
        
        # All attempts failed
        logger.error(f"❌ Reconnection failed after {self.max_reconnect_attempts} attempts")
        self.is_reconnecting = False
        
        # Call user callback
        if self.on_reconnect_failed:
            self.on_reconnect_failed()
    
    def _reconnect_attempt(self) -> bool:
        """
        Single reconnection attempt.
        
        Returns:
            bool: True if reconnection successful
        """
        if not self.host or not self.port or self.client_id is None:
            logger.error("Cannot reconnect - missing connection parameters")
            return False
        
        try:
            # Clear previous connection state (but keep parameters)
            if self.is_connected:
                self.disconnect()
                time.sleep(0.5)
            
            # Attempt new connection
            return self.connect_to_ib(
                host=self.host,
                port=self.port,
                client_id=self.client_id,
                timeout=10
            )
        except Exception as e:
            logger.error(f"Reconnection attempt failed: {str(e)}")
            return False
    
    def manual_reconnect(self) -> bool:
        """
        Manually trigger reconnection.
        
        Returns:
            bool: True if reconnection initiated successfully
        """
        if self.is_connected:
            logger.warning("Already connected - disconnecting first")
            self.disconnect_from_ib(clear_params=False)  # Keep params for reconnection
            time.sleep(1)
        
        if self.is_reconnecting:
            logger.warning("Reconnection already in progress")
            return False
        
        logger.info("Manual reconnection triggered")
        self._attempt_reconnection()
        return True
    
    def __repr__(self) -> str:
        """String representation"""
        status = "CONNECTED" if self.is_connected else "DISCONNECTED"
        return f"ConnectionManager({status} @ {self.host}:{self.port})"
