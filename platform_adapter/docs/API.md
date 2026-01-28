# API Documentation - Platform Adapter

Complete API reference for all components of the Platform Adapter.

## Table of Contents

1. [PlatformAdapter](#platformadapter) - Main interface
2. [ConnectionManager](#connectionmanager) - Connection handling
3. [MarketDataAdapter](#marketdataadapter) - Market data streaming
4. [OrderExecutionAdapter](#orderexecutionadapter) - Order management
5. [AccountManager](#accountmanager) - Account monitoring
6. [StateManager](#statemanager) - State persistence
7. [Data Models](#data-models) - Contract, Order, Position
8. [Utilities](#utilities) - RateLimiter, Logger

---

## PlatformAdapter

Main entry point for the Platform Adapter. Provides a unified interface to all components.

### Constructor

```python
PlatformAdapter(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 1,
    auto_reconnect: bool = True,
    state_file: str = "logs/state.json"
)
```

**Parameters:**
- `host`: IB Gateway/TWS host address
- `port`: IB Gateway/TWS port (7497=paper, 7496=live)
- `client_id`: Unique client identifier
- `auto_reconnect`: Enable automatic reconnection
- `state_file`: Path to state persistence file

**Example:**
```python
adapter = PlatformAdapter(
    host="localhost",
    port=7497,
    client_id=1
)
```

### Methods

#### connect()

Connect to IB Gateway/TWS.

```python
def connect(timeout: int = 10) -> bool
```

**Parameters:**
- `timeout`: Connection timeout in seconds

**Returns:**
- `bool`: True if connected successfully

**Example:**
```python
if adapter.connect():
    print("Connected!")
```

---

#### disconnect()

Disconnect from IB Gateway/TWS.

```python
def disconnect() -> None
```

**Example:**
```python
adapter.disconnect()
```

---

#### subscribe_market_data()

Subscribe to real-time market data for a symbol.

```python
def subscribe_market_data(
    symbol: str,
    callback: Optional[Callable[[str, Quote], None]] = None
) -> int
```

**Parameters:**
- `symbol`: Stock symbol (e.g., "AAPL")
- `callback`: Optional callback function for quote updates

**Returns:**
- `int`: Request ID for this subscription

**Example:**
```python
def on_quote(symbol, quote):
    print(f"{symbol}: {quote.last}")

req_id = adapter.subscribe_market_data("AAPL", on_quote)
```

---

#### place_market_order()

Place a market order.

```python
def place_market_order(
    symbol: str,
    quantity: int,
    action: str
) -> int
```

**Parameters:**
- `symbol`: Stock symbol
- `quantity`: Number of shares
- `action`: "BUY" or "SELL"

**Returns:**
- `int`: Order ID

**Example:**
```python
order_id = adapter.place_market_order("AAPL", 100, "BUY")
```

---

#### place_limit_order()

Place a limit order.

```python
def place_limit_order(
    symbol: str,
    quantity: int,
    action: str,
    limit_price: float
) -> int
```

**Parameters:**
- `symbol`: Stock symbol
- `quantity`: Number of shares
- `action`: "BUY" or "SELL"
- `limit_price`: Limit price

**Returns:**
- `int`: Order ID

**Example:**
```python
order_id = adapter.place_limit_order("AAPL", 100, "SELL", 155.00)
```

---

#### cancel_order()

Cancel an open order.

```python
def cancel_order(order_id: int) -> None
```

**Parameters:**
- `order_id`: ID of order to cancel

**Example:**
```python
adapter.cancel_order(1)
```

---

### Properties

#### connection

Access to ConnectionManager.

```python
@property
def connection(self) -> ConnectionManager
```

**Example:**
```python
if adapter.connection.is_connected:
    print("Connected")
```

---

#### market_data

Access to MarketDataAdapter.

```python
@property
def market_data(self) -> MarketDataAdapter
```

**Example:**
```python
quote = adapter.market_data.get_latest_quote("AAPL")
```

---

#### orders

Access to OrderExecutionAdapter.

```python
@property
def orders(self) -> OrderExecutionAdapter
```

**Example:**
```python
open_orders = adapter.orders.get_open_orders()
```

---

#### account

Access to AccountManager.

```python
@property
def account(self) -> AccountManager
```

**Example:**
```python
balance = adapter.account.get_summary()
```

---

#### state

Access to StateManager.

```python
@property
def state(self) -> StateManager
```

**Example:**
```python
adapter.state.save()
```

---

## ConnectionManager

Manages connection to IB Gateway/TWS with automatic reconnection.

### Constructor

```python
ConnectionManager(
    auto_reconnect: bool = True,
    max_reconnect_attempts: int = 5
)
```

### Methods

#### connect_to_ib()

```python
def connect_to_ib(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 1,
    timeout: int = 10
) -> bool
```

**Returns:** True if connected successfully

---

#### disconnect_from_ib()

```python
def disconnect_from_ib() -> None
```

Disconnect from IB Gateway.

---

### Properties

- `is_connected: bool` - Connection status
- `next_valid_order_id: int` - Next valid order ID
- `managed_accounts: list` - List of managed account IDs

---

## MarketDataAdapter

Handles market data subscriptions and requests.

### Methods

#### subscribe_market_data()

```python
def subscribe_market_data(
    symbol: str,
    callback: Optional[Callable] = None
) -> int
```

Subscribe to real-time quotes.

**Returns:** Request ID

---

#### unsubscribe_market_data()

```python
def unsubscribe_market_data(req_id: int) -> None
```

Cancel market data subscription.

---

#### get_historical_data()

```python
def get_historical_data(
    symbol: str,
    duration: str = "1 D",
    bar_size: str = "5 mins",
    what_to_show: str = "TRADES"
) -> List[Bar]
```

Request historical bar data.

**Parameters:**
- `symbol`: Stock symbol
- `duration`: Duration string (e.g., "1 D", "1 W")
- `bar_size`: Bar size (e.g., "1 min", "5 mins", "1 hour")
- `what_to_show`: Data type ("TRADES", "MIDPOINT", "BID", "ASK")

**Returns:** List of Bar objects

---

#### get_latest_quote()

```python
def get_latest_quote(symbol: str) -> Optional[Quote]
```

Get most recent cached quote.

**Returns:** Quote object or None

---

## OrderExecutionAdapter

Manages order lifecycle and execution.

### Methods

#### place_market_order()

```python
def place_market_order(
    symbol: str,
    quantity: int,
    action: str
) -> int
```

**Returns:** Order ID

---

#### place_limit_order()

```python
def place_limit_order(
    symbol: str,
    quantity: int,
    action: str,
    limit_price: float
) -> int
```

**Returns:** Order ID

---

#### place_stop_order()

```python
def place_stop_order(
    symbol: str,
    quantity: int,
    action: str,
    stop_price: float
) -> int
```

**Returns:** Order ID

---

#### place_bracket_order()

```python
def place_bracket_order(
    symbol: str,
    quantity: int,
    action: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float
) -> Dict[str, int]
```

Place bracket order (entry + stop loss + take profit).

**Returns:** Dict with 'parent', 'stop_loss', 'take_profit' order IDs

---

#### cancel_order()

```python
def cancel_order(order_id: int) -> None
```

Cancel an order.

---

#### modify_order()

```python
def modify_order(
    order_id: int,
    quantity: Optional[int] = None,
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None
) -> None
```

Modify an existing order.

---

#### get_order()

```python
def get_order(order_id: int) -> Optional[Order]
```

Get order by ID.

**Returns:** Order object or None

---

#### get_open_orders()

```python
def get_open_orders() -> List[Order]
```

Get all open orders.

**Returns:** List of Order objects

---

### Callbacks

Set callbacks to receive order updates:

```python
# Order status updates
adapter.orders.on_order_status = lambda order_id, status, filled, remaining, avg_fill_price: ...

# Execution reports
adapter.orders.on_execution = lambda order_id, contract, execution: ...

# Commission reports
adapter.orders.on_commission = lambda order_id, commission, currency: ...
```

---

## AccountManager

Monitors account values and positions.

### Methods

#### get_summary()

```python
def get_summary() -> Dict[str, Any]
```

Get account summary.

**Returns:** Dict with keys:
- `net_liquidation`: Total account value
- `total_cash`: Available cash
- `available_funds`: Funds available for trading
- `buying_power`: Buying power
- `gross_position_value`: Total position value
- `unrealized_pnl`: Unrealized P&L
- `realized_pnl`: Realized P&L

---

#### get_positions()

```python
def get_positions() -> List[Position]
```

Get all positions.

**Returns:** List of Position objects

---

#### get_position()

```python
def get_position(symbol: str) -> Optional[Position]
```

Get position for specific symbol.

**Returns:** Position object or None

---

### Callbacks

```python
# Account value updates
adapter.account.on_account_update = lambda key, value, currency: ...

# Position updates
adapter.account.on_position_update = lambda position: ...
```

---

## StateManager

Manages persistent state with reconciliation.

### Constructor

```python
StateManager(state_file: str = "logs/state.json")
```

### Methods

#### save()

```python
def save() -> None
```

Save current state to file.

---

#### load()

```python
def load() -> None
```

Load state from file.

---

#### update_connection_state()

```python
def update_connection_state(is_connected: bool) -> None
```

Update connection state.

---

#### add_position()

```python
def add_position(
    symbol: str,
    quantity: int,
    avg_cost: float
) -> None
```

Add or update position.

---

#### add_order()

```python
def add_order(order: Order) -> None
```

Add or update order.

---

#### reconcile_with_broker()

```python
def reconcile_with_broker(
    account_manager: AccountManager,
    order_manager: OrderExecutionAdapter
) -> Dict[str, Any]
```

Reconcile state with broker.

**Returns:** Dict with reconciliation results

---

## Data Models

### Contract

```python
@dataclass
class Contract:
    symbol: str
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"
    primary_exchange: Optional[str] = None
    
    def to_ib(self) -> IBContract
    @classmethod
    def from_ib(cls, ib_contract: IBContract) -> 'Contract'
```

---

### Order

```python
@dataclass
class Order:
    order_id: int
    contract: Contract
    action: str  # "BUY" or "SELL"
    quantity: int
    order_type: str  # "MKT", "LMT", "STP", etc.
    status: OrderStatus
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    filled: int = 0
    remaining: int = 0
    avg_fill_price: Optional[float] = None
    timestamp: Optional[datetime] = None
    
    def to_ib(self) -> IBOrder
    @classmethod
    def from_ib(cls, ib_order: IBOrder, contract: Contract, order_id: int) -> 'Order'
```

---

### Position

```python
@dataclass
class Position:
    contract: Contract
    quantity: int
    avg_cost: float
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    def is_long(self) -> bool
    def is_short(self) -> bool
    def is_flat(self) -> bool
```

---

### Quote

```python
@dataclass
class Quote:
    symbol: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    timestamp: Optional[datetime] = None
```

---

## Utilities

### RateLimiter

```python
class RateLimiter:
    def __init__(self, max_requests: int, time_window: int)
    def can_proceed(self) -> bool
    def wait_if_needed(self, operation: Optional[str] = None) -> float
    def get_current_usage(self) -> Dict[str, Any]
    def reset(self) -> None
```

**Pre-configured limiters:**
```python
from platform_adapter.utils.rate_limiter import IBRateLimiters

IBRateLimiters.MARKET_DATA  # 50 req / 10 min
IBRateLimiters.HISTORICAL_DATA  # 50 req / 10 min
IBRateLimiters.ORDERS  # 40 req / 1 sec
IBRateLimiters.ACCOUNT  # 8 req / 1 min
```

---

### Logger

```python
from platform_adapter.utils.logger import logger

logger.info("Message")
logger.debug("Debug message")
logger.warning("Warning")
logger.error("Error")
logger.exception("Exception with traceback")
```

---

## Error Handling

All exceptions inherit from `PlatformAdapterException`:

```python
from platform_adapter.exceptions import (
    ConnectionError,
    OrderError,
    DataError,
    StateError
)

try:
    adapter.connect()
except ConnectionError as e:
    logger.error(f"Connection failed: {e}")
```

---

## Rate Limits

Interactive Brokers imposes rate limits:

| Operation | Limit |
|-----------|-------|
| Market Data Subscriptions | 60 per 10 minutes |
| Historical Data Requests | 60 per 10 minutes |
| Order Requests | 50 per second |
| Account Requests | 10 per minute |

The Platform Adapter automatically handles these limits using the RateLimiter utility.

---

**Last Updated**: January 27, 2026  
**Version**: 1.0.0
