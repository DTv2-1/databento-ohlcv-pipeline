# User Guide - Platform Adapter

Comprehensive guide for using the Platform Adapter for Interactive Brokers.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Basic Usage](#basic-usage)
3. [Advanced Features](#advanced-features)
4. [Best Practices](#best-practices)
5. [Common Patterns](#common-patterns)
6. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Prerequisites

Before starting, ensure you have:

1. **IB Account**: Paper trading account recommended for testing
2. **IB Gateway or TWS**: Version 10.19 or higher
3. **Python 3.11+**: With pip installed
4. **API Access Enabled**: In IB Gateway/TWS settings

### Installation Steps

```bash
# 1. Clone the repository
git clone <repository-url>
cd platform_adapter

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment template
cp .env.example .env

# 5. Edit .env with your settings
nano .env
```

### IB Gateway Setup

1. **Launch IB Gateway**
   - Open IB Gateway or TWS application
   - Login with paper trading credentials

2. **Enable API Access**
   - Navigate to: **Configuration → API → Settings**
   - Check "Enable ActiveX and Socket Clients"
   - Set Socket Port: `7497` (paper) or `7496` (live)
   - Check "Read-Only API" for testing (optional)
   - Click "OK" to save

3. **Configure Trusted IPs**
   - Add `127.0.0.1` to trusted IP addresses
   - Allow connections from localhost

---

## Basic Usage

### Example 1: Connect and Check Status

```python
from platform_adapter import PlatformAdapter

# Initialize adapter
adapter = PlatformAdapter(
    host="localhost",
    port=7497,  # Paper trading
    client_id=1
)

# Connect to IB Gateway
if adapter.connect():
    print("✅ Connected successfully!")
    
    # Check connection status
    if adapter.connection.is_connected:
        print(f"Next Order ID: {adapter.connection.next_valid_order_id}")
        print(f"Managed Accounts: {adapter.connection.managed_accounts}")
    
    # Disconnect when done
    adapter.disconnect()
else:
    print("❌ Connection failed")
```

### Example 2: Get Account Information

```python
from platform_adapter import PlatformAdapter

adapter = PlatformAdapter()
adapter.connect()

# Get account summary
account = adapter.account.get_summary()

print(f"Net Liquidation: ${account['net_liquidation']:,.2f}")
print(f"Available Funds: ${account['available_funds']:,.2f}")
print(f"Buying Power: ${account['buying_power']:,.2f}")
print(f"Unrealized P&L: ${account['unrealized_pnl']:,.2f}")

# Get positions
positions = adapter.account.get_positions()
if positions:
    print("\nCurrent Positions:")
    for pos in positions:
        pnl_pct = (pos.unrealized_pnl / (pos.avg_cost * abs(pos.quantity))) * 100
        print(f"  {pos.contract.symbol}: {pos.quantity:+d} @ ${pos.avg_cost:.2f} "
              f"(P&L: ${pos.unrealized_pnl:+.2f} / {pnl_pct:+.2f}%)")
else:
    print("\nNo open positions")

adapter.disconnect()
```

### Example 3: Subscribe to Market Data

```python
from platform_adapter import PlatformAdapter
import time

adapter = PlatformAdapter()
adapter.connect()

# Define callback for quote updates
def on_quote(symbol, quote):
    if quote.last is not None:
        print(f"{symbol}: ${quote.last:.2f} | Bid: ${quote.bid:.2f} | Ask: ${quote.ask:.2f} | Vol: {quote.volume:,}")

# Subscribe to multiple symbols
symbols = ["AAPL", "MSFT", "GOOGL", "TSLA"]
for symbol in symbols:
    adapter.subscribe_market_data(symbol, on_quote)
    print(f"Subscribed to {symbol}")

# Keep receiving updates
try:
    print("\n📊 Streaming market data (Ctrl+C to stop)...\n")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping...")
    adapter.disconnect()
```

### Example 4: Place a Simple Order

```python
from platform_adapter import PlatformAdapter
import time

adapter = PlatformAdapter()
adapter.connect()

# Place market order
symbol = "AAPL"
quantity = 10
action = "BUY"

order_id = adapter.place_market_order(symbol, quantity, action)
print(f"✅ Order placed: {order_id}")
print(f"Action: {action} {quantity} shares of {symbol}")

# Monitor order status
def on_order_status(order_id, status, filled, remaining, avg_fill_price):
    print(f"\n📋 Order {order_id} Update:")
    print(f"   Status: {status}")
    print(f"   Filled: {filled}/{filled + remaining}")
    if avg_fill_price and avg_fill_price > 0:
        print(f"   Avg Fill Price: ${avg_fill_price:.2f}")

adapter.orders.on_order_status = on_order_status

# Wait for order to fill
print("Waiting for order to fill...")
time.sleep(10)

adapter.disconnect()
```

---

## Advanced Features

### Market Orders with Position Tracking

```python
from platform_adapter import PlatformAdapter
import time

adapter = PlatformAdapter()
adapter.connect()

# Check current position
symbol = "AAPL"
current_pos = adapter.account.get_position(symbol)
if current_pos:
    print(f"Current position: {current_pos.quantity} shares @ ${current_pos.avg_cost:.2f}")
else:
    print("No current position")

# Place order
order_id = adapter.place_market_order(symbol, 100, "BUY")

# Wait for fill
time.sleep(5)

# Check updated position
new_pos = adapter.account.get_position(symbol)
if new_pos:
    print(f"New position: {new_pos.quantity} shares @ ${new_pos.avg_cost:.2f}")

adapter.disconnect()
```

### Limit Orders with Price Monitoring

```python
from platform_adapter import PlatformAdapter
import time

adapter = PlatformAdapter()
adapter.connect()

symbol = "AAPL"

# Get current market price
def wait_for_quote():
    quote = adapter.market_data.get_latest_quote(symbol)
    if quote and quote.last:
        return quote.last
    # Subscribe and wait
    adapter.subscribe_market_data(symbol)
    time.sleep(2)
    return adapter.market_data.get_latest_quote(symbol).last

current_price = wait_for_quote()
print(f"Current {symbol} price: ${current_price:.2f}")

# Place limit order 1% below market
limit_price = current_price * 0.99
order_id = adapter.place_limit_order(
    symbol=symbol,
    quantity=100,
    action="BUY",
    limit_price=limit_price
)

print(f"Limit order placed at ${limit_price:.2f}")
print(f"Order ID: {order_id}")

# Monitor order
def on_status(order_id, status, filled, remaining, avg_fill_price):
    if status == "Filled":
        print(f"✅ Order filled at ${avg_fill_price:.2f}")
    elif status == "Cancelled":
        print("❌ Order cancelled")

adapter.orders.on_order_status = on_status

# Wait 30 seconds
time.sleep(30)

# Cancel if not filled
order = adapter.orders.get_order(order_id)
if order and order.status.value not in ["Filled", "Cancelled"]:
    print("Order not filled, cancelling...")
    adapter.cancel_order(order_id)

adapter.disconnect()
```

### Bracket Orders (Entry + Stop Loss + Take Profit)

```python
from platform_adapter import PlatformAdapter

adapter = PlatformAdapter()
adapter.connect()

# Define bracket order parameters
symbol = "AAPL"
quantity = 100
entry_price = 150.00
stop_loss = 148.00    # 1.33% risk
take_profit = 155.00  # 3.33% profit

# Place bracket order
orders = adapter.place_bracket_order(
    symbol=symbol,
    quantity=quantity,
    action="BUY",
    entry_price=entry_price,
    stop_loss=stop_loss,
    take_profit=take_profit
)

print("Bracket Order Created:")
print(f"  Parent (Entry):   {orders['parent']} @ ${entry_price:.2f}")
print(f"  Stop Loss:        {orders['stop_loss']} @ ${stop_loss:.2f}")
print(f"  Take Profit:      {orders['take_profit']} @ ${take_profit:.2f}")
print(f"  Risk:             ${(entry_price - stop_loss) * quantity:.2f}")
print(f"  Potential Profit: ${(take_profit - entry_price) * quantity:.2f}")

adapter.disconnect()
```

### Historical Data Analysis

```python
from platform_adapter import PlatformAdapter
import pandas as pd

adapter = PlatformAdapter()
adapter.connect()

# Request historical data
symbol = "AAPL"
bars = adapter.market_data.get_historical_data(
    symbol=symbol,
    duration="5 D",      # 5 days of data
    bar_size="5 mins",   # 5-minute bars
    what_to_show="TRADES"
)

# Convert to DataFrame
df = pd.DataFrame([
    {
        'timestamp': bar.timestamp,
        'open': bar.open,
        'high': bar.high,
        'low': bar.low,
        'close': bar.close,
        'volume': bar.volume
    }
    for bar in bars
])

# Calculate simple moving average
df['sma_20'] = df['close'].rolling(window=20).mean()

# Print summary
print(f"\n{symbol} Historical Data Summary:")
print(f"  Bars: {len(df)}")
print(f"  Date Range: {df['timestamp'].min()} to {df['timestamp'].max()}")
print(f"  High: ${df['high'].max():.2f}")
print(f"  Low: ${df['low'].min():.2f}")
print(f"  Last Close: ${df['close'].iloc[-1]:.2f}")
print(f"  SMA(20): ${df['sma_20'].iloc[-1]:.2f}")

adapter.disconnect()
```

---

## Best Practices

### 1. Connection Management

```python
# ✅ GOOD: Use context manager pattern
class TradingSession:
    def __init__(self):
        self.adapter = PlatformAdapter()
    
    def __enter__(self):
        self.adapter.connect()
        return self.adapter
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.adapter.disconnect()

# Usage
with TradingSession() as adapter:
    # Your trading logic here
    adapter.place_market_order("AAPL", 10, "BUY")
# Automatically disconnects
```

### 2. Error Handling

```python
from platform_adapter import PlatformAdapter
from platform_adapter.exceptions import ConnectionError, OrderError

adapter = PlatformAdapter()

try:
    if not adapter.connect(timeout=10):
        raise ConnectionError("Failed to connect")
    
    # Trading logic
    order_id = adapter.place_market_order("AAPL", 100, "BUY")
    
except ConnectionError as e:
    print(f"Connection error: {e}")
    # Handle connection issues
    
except OrderError as e:
    print(f"Order error: {e}")
    # Handle order issues
    
except Exception as e:
    print(f"Unexpected error: {e}")
    
finally:
    # Always disconnect
    if adapter.connection.is_connected:
        adapter.disconnect()
```

### 3. Rate Limiting

```python
from platform_adapter import PlatformAdapter
from platform_adapter.utils.rate_limiter import IBRateLimiters

adapter = PlatformAdapter()
adapter.connect()

symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "META"]

# Subscribe with rate limiting
for symbol in symbols:
    # Wait if rate limit would be exceeded
    IBRateLimiters.MARKET_DATA.wait_if_needed(f"subscribe_{symbol}")
    adapter.subscribe_market_data(symbol)
    print(f"Subscribed to {symbol}")

adapter.disconnect()
```

### 4. State Persistence

```python
from platform_adapter import PlatformAdapter

adapter = PlatformAdapter(state_file="logs/my_strategy_state.json")
adapter.connect()

# Load previous state
adapter.state.load()

# Your trading logic
# ...

# Save state periodically
adapter.state.save()

# Reconcile with broker on startup
if adapter.state.config.reconcile_on_start:
    results = adapter.state.reconcile_with_broker(
        adapter.account,
        adapter.orders
    )
    print(f"Reconciliation: {results}")

adapter.disconnect()
```

---

## Common Patterns

### Pattern 1: Mean Reversion Strategy

```python
from platform_adapter import PlatformAdapter
import time

adapter = PlatformAdapter()
adapter.connect()

symbol = "AAPL"
lookback = 20
std_dev = 2

# Get historical data
bars = adapter.market_data.get_historical_data(
    symbol=symbol,
    duration="1 D",
    bar_size="5 mins"
)

# Calculate bands
closes = [bar.close for bar in bars]
mean = sum(closes) / len(closes)
variance = sum((x - mean) ** 2 for x in closes) / len(closes)
std = variance ** 0.5

upper_band = mean + (std_dev * std)
lower_band = mean - (std_dev * std)

print(f"Mean: ${mean:.2f}")
print(f"Upper Band: ${upper_band:.2f}")
print(f"Lower Band: ${lower_band:.2f}")

# Subscribe to real-time data
def on_quote(symbol, quote):
    if quote.last:
        if quote.last < lower_band:
            print(f"Price ${quote.last:.2f} below lower band - BUY signal")
            # adapter.place_limit_order(symbol, 100, "BUY", quote.last)
        elif quote.last > upper_band:
            print(f"Price ${quote.last:.2f} above upper band - SELL signal")
            # adapter.place_limit_order(symbol, 100, "SELL", quote.last)

adapter.subscribe_market_data(symbol, on_quote)

# Run for 1 hour
time.sleep(3600)
adapter.disconnect()
```

### Pattern 2: Portfolio Rebalancing

```python
from platform_adapter import PlatformAdapter

adapter = PlatformAdapter()
adapter.connect()

# Target portfolio allocation
target_allocation = {
    "AAPL": 0.25,
    "MSFT": 0.25,
    "GOOGL": 0.25,
    "TSLA": 0.25
}

# Get account value
account = adapter.account.get_summary()
total_value = account['net_liquidation']
print(f"Total Portfolio Value: ${total_value:,.2f}")

# Get current positions
current_positions = {
    pos.contract.symbol: pos.quantity * pos.avg_cost
    for pos in adapter.account.get_positions()
}

# Calculate rebalancing trades
for symbol, target_pct in target_allocation.items():
    target_value = total_value * target_pct
    current_value = current_positions.get(symbol, 0)
    diff_value = target_value - current_value
    
    # Get current price
    adapter.subscribe_market_data(symbol)
    time.sleep(1)
    quote = adapter.market_data.get_latest_quote(symbol)
    
    if quote and quote.last:
        shares_to_trade = int(diff_value / quote.last)
        
        if abs(shares_to_trade) > 0:
            action = "BUY" if shares_to_trade > 0 else "SELL"
            quantity = abs(shares_to_trade)
            
            print(f"{symbol}: {action} {quantity} shares (${diff_value:+,.2f})")
            # adapter.place_market_order(symbol, quantity, action)

adapter.disconnect()
```

### Pattern 3: Stop Loss Management

```python
from platform_adapter import PlatformAdapter
import time

adapter = PlatformAdapter()
adapter.connect()

# Get all positions
positions = adapter.account.get_positions()

# Set stop losses for all positions
STOP_LOSS_PCT = 0.02  # 2% stop loss

for pos in positions:
    if pos.is_long():
        # Calculate stop price
        stop_price = pos.avg_cost * (1 - STOP_LOSS_PCT)
        
        # Place stop order
        order_id = adapter.place_stop_order(
            symbol=pos.contract.symbol,
            quantity=pos.quantity,
            action="SELL",
            stop_price=stop_price
        )
        
        print(f"{pos.contract.symbol}: Stop loss at ${stop_price:.2f} (Order {order_id})")

adapter.disconnect()
```

---

## Troubleshooting

### Problem: Cannot Connect to IB Gateway

**Symptoms:**
```
ConnectionError: Failed to connect after 10 seconds
```

**Solutions:**

1. **Check IB Gateway is running**
   ```bash
   # Verify process is running (macOS/Linux)
   ps aux | grep -i "ibgateway\|tws"
   ```

2. **Verify API settings**
   - Configuration → API → Settings
   - "Enable ActiveX and Socket Clients" must be checked
   - Port must match (7497 for paper, 7496 for live)

3. **Check firewall**
   ```bash
   # Test connection (macOS/Linux)
   nc -zv localhost 7497
   ```

4. **Try different client ID**
   ```python
   adapter = PlatformAdapter(client_id=999)  # Try different ID
   ```

### Problem: Market Data Not Updating

**Symptoms:**
- Quotes are None or stale
- Callback not being called

**Solutions:**

1. **Check market hours**
   ```python
   from datetime import datetime
   now = datetime.now()
   print(f"Current time: {now}")
   # Market hours: 9:30 AM - 4:00 PM ET
   ```

2. **Verify subscription**
   ```python
   # Wait for initial quote
   adapter.subscribe_market_data("AAPL")
   time.sleep(2)  # Give time for first quote
   quote = adapter.market_data.get_latest_quote("AAPL")
   ```

3. **Check data permissions**
   - Verify account has market data subscriptions
   - Paper trading has delayed data

### Problem: Orders Not Filling

**Symptoms:**
- Order stays in "Submitted" status
- No fills received

**Solutions:**

1. **Check order parameters**
   ```python
   # Verify order was placed correctly
   order = adapter.orders.get_order(order_id)
   print(f"Order: {order}")
   ```

2. **Use market orders for testing**
   ```python
   # Market orders fill immediately (during market hours)
   order_id = adapter.place_market_order("AAPL", 1, "BUY")
   ```

3. **Check account permissions**
   - Verify trading permissions are enabled
   - Check buying power

### Problem: Rate Limit Exceeded

**Symptoms:**
```
WARNING: Rate limit reached. Waiting 120.5s...
```

**Solutions:**

1. **Use rate limiters**
   ```python
   from platform_adapter.utils.rate_limiter import IBRateLimiters
   
   IBRateLimiters.MARKET_DATA.wait_if_needed("subscription")
   adapter.subscribe_market_data("AAPL")
   ```

2. **Reduce request frequency**
   ```python
   # Add delays between requests
   for symbol in symbols:
       adapter.subscribe_market_data(symbol)
       time.sleep(1)  # 1 second delay
   ```

---

## Getting Help

- **Documentation**: [API.md](API.md)
- **Examples**: `scripts/` directory
- **Tests**: `tests/` directory
- **Issues**: GitHub Issues
- **IB API Docs**: [Interactive Brokers API](https://interactivebrokers.github.io/tws-api/)

---

**Last Updated**: January 27, 2026  
**Version**: 1.0.0
