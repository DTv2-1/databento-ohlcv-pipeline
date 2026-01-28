# Platform Adapter - Interactive Brokers TWS API
## Technical Specification

**Date:** January 21, 2026  
**Client:** Pete Davis / RaptorTrade  
**Project:** PA MVP - Interactive Brokers Integration  
**Version:** 1.0 - Limited MVP

---

## 1. EXECUTIVE SUMMARY

### 1.1 Project Objective

Build a limited **Platform Adapter (PA)** that connects exclusively with the Interactive Brokers API for algorithmic trading. This MVP version **DOES NOT include** integration with other system modules (U - data provider, OE - order engine).

### 1.2 Limited Scope

**INCLUDES:**
- ✅ Connection with Interactive Brokers TWS API
- ✅ Market data streaming (real-time quotes)
- ✅ Historical data retrieval
- ✅ Order placement and management
- ✅ Account information and position tracking
- ✅ Error handling and reconnection logic

**DOES NOT INCLUDE (Future Phase):**
- ❌ Integration with U module (data provider)
- ❌ Integration with OE module (order engine)
- ❌ Inter-process communication (ZMQ/pipes)
- ❌ Message queuing between modules
- ❌ Integrated backtesting system

### 1.3 API Decision

**Selected API:** TWS API (Trader Workstation API)

**Justification:**
- Full feature access - complete access to all functionalities
- Market data streaming optimized for large volumes
- Complete order execution with advanced orders
- Official Python support with `ibapi` library
- Mature architecture proven in production

**Alternative evaluated:** Web API (discarded due to throughput and features limitations)

---

## 2. PLATFORM ADAPTER ARCHITECTURE

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Platform Adapter (PA)                     │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │           Connection Manager                        │    │
│  │  - TWS/Gateway connection                          │    │
│  │  - Auto-reconnection logic                         │    │
│  │  - Health monitoring                               │    │
│  └────────────────────────────────────────────────────┘    │
│                           │                                  │
│  ┌────────────────────────┼────────────────────────────┐   │
│  │                        │                             │   │
│  ▼                        ▼                             ▼   │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │  Market  │    │    Order      │    │   Account    │     │
│  │   Data   │    │  Execution    │    │  Manager     │     │
│  │ Adapter  │    │   Adapter     │    │              │     │
│  └──────────┘    └──────────────┘    └──────────────┘     │
│       │                 │                     │             │
│       │                 │                     │             │
│  ┌────▼─────────────────▼─────────────────────▼──────┐    │
│  │              State Manager                         │    │
│  │  - Positions tracking                             │    │
│  │  - Orders tracking                                │    │
│  │  - Account values cache                           │    │
│  └────────────────────────────────────────────────────┘   │
│                           │                                 │
│  ┌────────────────────────▼────────────────────────────┐  │
│  │              Logging & Monitoring                   │  │
│  │  - API logs                                         │  │
│  │  - Error logs                                       │  │
│  │  - Performance metrics                              │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ TCP Socket (Port 7497)
                           │
                           ▼
              ┌────────────────────────┐
              │  IB Gateway / TWS      │
              │  (Paper Trading)       │
              └────────────────────────┘
```

### 2.2 Main Components

#### 2.2.1 Connection Manager
**Responsibility:** Manage connection with TWS/Gateway

**Functions:**
- Establish initial connection with TWS/Gateway
- Detect disconnections
- Auto-reconnection with exponential backoff
- Periodic health checks
- Thread management for message processing

**Interface:**
```python
class ConnectionManager:
    def connect(host: str, port: int, client_id: int) -> bool
    def disconnect() -> None
    def is_connected() -> bool
    def reconnect() -> bool
    def get_connection_status() -> ConnectionStatus
```

#### 2.2.2 Market Data Adapter
**Responsibility:** Streaming and retrieval of market data

**Functions:**
- Subscribe/unsubscribe to real-time quotes
- Request historical data (OHLCV)
- Request real-time bars (5-second)
- Tick-by-tick data (optional)
- Rate limiting for pacing violations

**Interface:**
```python
class MarketDataAdapter:
    def subscribe_quotes(symbols: List[str], callback: Callable) -> None
    def unsubscribe_quotes(symbols: List[str]) -> None
    def get_historical_data(symbol: str, duration: str, bar_size: str) -> pd.DataFrame
    def subscribe_real_time_bars(symbol: str, callback: Callable) -> None
```

#### 2.2.3 Order Execution Adapter
**Responsibility:** Order placement and management

**Functions:**
- Place orders (Market, Limit, Stop, Stop-Limit)
- Cancel orders
- Modify orders
- Track order status
- Execution reports

**Interface:**
```python
class OrderExecutionAdapter:
    def place_order(symbol: str, action: str, quantity: int, order_type: str, **kwargs) -> int
    def cancel_order(order_id: int) -> bool
    def modify_order(order_id: int, **kwargs) -> bool
    def get_order_status(order_id: int) -> OrderStatus
    def get_open_orders() -> List[Order]
```

#### 2.2.4 Account Manager
**Responsibility:** Account information and positions

**Functions:**
- Account summary (balance, buying power, etc.)
- Position tracking
- P&L tracking (realized/unrealized)
- Account updates subscription

**Interface:**
```python
class AccountManager:
    def get_account_summary() -> AccountSummary
    def get_positions() -> List[Position]
    def get_pnl() -> PnL
    def subscribe_account_updates(callback: Callable) -> None
```

#### 2.2.5 State Manager
**Responsibility:** Maintain synchronized internal state

**Functions:**
- Cache positions
- Cache orders
- Cache account values
- Periodic reconciliation with IB

**Interface:**
```python
class StateManager:
    def update_position(position: Position) -> None
    def update_order(order: Order) -> None
    def update_account_value(key: str, value: Any) -> None
    def get_cached_positions() -> List[Position]
    def get_cached_orders() -> List[Order]
```

---

## 3. TECHNOLOGIES AND TECHNICAL STACK

### 3.1 Programming Language

**Python 3.11+**
- Minimum requirement for TWS API
- Compatible with existing stack
- Excellent for algorithmic trading

### 3.2 Main Libraries

#### TWS API Integration
```python
ibapi==10.25.0  # Official Interactive Brokers library
```

**Installation:**
```bash
# From TWS API installation
cd ~/IBJts/source/pythonclient
python setup.py install
```

#### Data Processing
```python
pandas==2.1.0      # Data manipulation
numpy==1.24.0      # Numerical operations
```

#### Configuration & Environment
```python
python-dotenv==1.0.0  # Environment variables
pyyaml==6.0          # Configuration files
```

#### Logging & Monitoring
```python
loguru==0.7.0        # Advanced logging
```

### 3.3 Development Tools

```python
pytest==7.4.0           # Testing
pytest-asyncio==0.21.0  # Async testing
pytest-cov==4.1.0       # Coverage
black==23.7.0           # Code formatting
pylint==2.17.5          # Linting
mypy==1.4.1             # Type checking
```

---

## 4. PROJECT STRUCTURE

```
platform_adapter/
├── src/
│   └── platform_adapter/
│       ├── __init__.py
│       ├── main.py                    # Entry point
│       ├── config/
│       │   ├── __init__.py
│       │   ├── settings.py            # Configuration loader
│       │   └── config.yaml            # Configuration file
│       ├── core/
│       │   ├── __init__.py
│       │   ├── connection_manager.py
│       │   ├── state_manager.py
│       │   └── base_adapter.py
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── market_data.py
│       │   ├── order_execution.py
│       │   └── account_manager.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── contract.py
│       │   ├── order.py
│       │   ├── position.py
│       │   └── account.py
│       └── utils/
│           ├── __init__.py
│           ├── logger.py
│           ├── rate_limiter.py
│           └── validators.py
├── tests/
│   ├── __init__.py
│   ├── test_connection.py
│   ├── test_market_data.py
│   ├── test_orders.py
│   └── test_account.py
├── scripts/
│   ├── setup_paper_account.py
│   └── test_live_connection.py
├── logs/
│   └── .gitkeep
├── requirements.txt
├── requirements-dev.txt
├── setup.py
├── pytest.ini
├── .env.example
├── .env
├── .gitignore
└── README.md
```

---

## 5. CONFIGURATION AND SETUP

### 5.1 Prerequisites

**Software:**
- [x] Python 3.11+ installed
- [x] IB Gateway or TWS installed (build 952.x+)
- [x] TWS API installed (v9.72+)
- [x] IBKR Pro account with paper trading enabled

**Network:**
- [x] Port 7497 (paper) or 7496 (live) accessible
- [x] Firewall configured for localhost

### 5.2 Installation

**Step 1: Clone repository**
```bash
cd /Users/1di/DataBento
mkdir platform_adapter
cd platform_adapter
```

**Step 2: Create virtual environment**
```bash
python3.11 -m venv venv
source venv/bin/activate  # macOS/Linux
```

**Step 3: Install dependencies**
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

**Step 4: Install TWS API**
```bash
cd ~/IBJts/source/pythonclient
python setup.py install
```

**Step 5: Configure credentials**
```bash
cp .env.example .env
# Edit .env with configuration
```

### 5.3 Configuration File

**config.yaml:**
```yaml
ib_connection:
  host: "127.0.0.1"
  port: 7497  # Paper trading
  client_id: 1
  timeout: 30
  auto_reconnect: true
  reconnect_max_attempts: 5
  reconnect_backoff: 2.0

market_data:
  max_simultaneous_subscriptions: 50
  rate_limit_requests_per_second: 40
  historical_data_max_requests_per_10min: 50

orders:
  default_time_in_force: "GTC"
  validate_before_submit: true
  
account:
  update_frequency_seconds: 180  # 3 minutes

logging:
  level: "INFO"
  format: "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}"
  rotation: "10 MB"
  retention: "7 days"
  log_dir: "logs"

monitoring:
  health_check_interval_seconds: 30
  metrics_enabled: true
```

**.env:**
```bash
# IB Configuration
IB_HOST=127.0.0.1
IB_PORT=7497
IB_CLIENT_ID=1

# Paper Trading Account
IB_ACCOUNT_ID=DU123456

# Logging
LOG_LEVEL=INFO
LOG_DIR=logs

# Environment
ENVIRONMENT=development  # development, staging, production
```

---

## 6. DATA FLOW AND OPERATION

### 6.1 Startup Sequence

```
1. Load Configuration
   ├─> Parse config.yaml
   ├─> Load .env variables
   └─> Validate settings

2. Initialize Components
   ├─> Logger setup
   ├─> State Manager initialization
   ├─> Connection Manager creation
   └─> Adapters initialization

3. Connect to IB Gateway
   ├─> Establish TCP socket connection
   ├─> Wait for nextValidId callback
   ├─> Subscribe to account updates
   └─> Load initial positions

4. Start Event Loop
   ├─> Process incoming messages
   ├─> Handle callbacks
   └─> Execute user commands

5. Ready for Operations
```

### 6.2 Market Data Flow

```
User Request
    │
    ├─> MarketDataAdapter.subscribe_quotes(["AAPL", "MSFT"])
    │
    ├─> Rate Limiter check
    │
    ├─> TWS API: reqMktData(reqId, contract, ...)
    │
    ├─> [IB Gateway processes request]
    │
    ├─> Callbacks received:
    │   ├─> tickPrice(reqId, tickType, price, attrib)
    │   ├─> tickSize(reqId, tickType, size)
    │   └─> tickString(reqId, tickType, value)
    │
    ├─> State Manager updates cache
    │
    └─> User callback executed with data
```

### 6.3 Order Execution Flow

```
User Request
    │
    ├─> OrderExecutionAdapter.place_order(
    │       symbol="AAPL",
    │       action="BUY",
    │       quantity=100,
    │       order_type="LMT",
    │       limit_price=150.00
    │   )
    │
    ├─> Validation
    │   ├─> Symbol exists
    │   ├─> Sufficient buying power
    │   └─> Order parameters valid
    │
    ├─> Create Order object
    │
    ├─> TWS API: placeOrder(orderId, contract, order)
    │
    ├─> [IB Gateway processes order]
    │
    ├─> Callbacks received:
    │   ├─> openOrder(orderId, contract, order, orderState)
    │   ├─> orderStatus(orderId, status, filled, ...)
    │   ├─> execDetails(reqId, contract, execution)
    │   └─> commissionReport(commissionReport)
    │
    ├─> State Manager updates order cache
    │
    └─> Return orderId to user
```

---

## 7. ERROR HANDLING AND RESILIENCE

### 7.1 Error Handling Strategy

**Error Levels:**
1. **Connection Errors (Critical)**
   - Auto-reconnect with exponential backoff
   - Log all attempts
   - User notification

2. **API Errors (Warning/Error)**
   - Pacing violations → Rate limiting
   - Invalid contracts → Pre-request validation
   - Order rejections → Return error to user

3. **Data Errors (Warning)**
   - Missing data → Log warning
   - Stale data → Timestamp check

### 7.2 Reconnection Logic

```python
class ReconnectionStrategy:
    max_attempts: int = 5
    base_delay: float = 2.0  # seconds
    max_delay: float = 60.0
    
    def get_delay(attempt: int) -> float:
        delay = base_delay * (2 ** attempt)
        return min(delay, max_delay)
    
    async def reconnect(self) -> bool:
        for attempt in range(self.max_attempts):
            delay = self.get_delay(attempt)
            await asyncio.sleep(delay)
            
            if await self.connection_manager.connect():
                return True
        
        return False
```

### 7.3 Rate Limiting

```python
class RateLimiter:
    """Prevent pacing violations"""
    
    def __init__(self, max_requests: int, time_window: int):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
    
    def can_proceed(self) -> bool:
        now = time.time()
        
        # Remove old requests
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()
        
        return len(self.requests) < self.max_requests
    
    def record_request(self):
        self.requests.append(time.time())
```

---

## 8. TESTING STRATEGY

### 8.1 Testing Levels

**Unit Tests:**
- Model validation (Contract, Order, Position)
- Utilities (Logger, RateLimiter, Validators)
- State Manager operations

**Integration Tests:**
- Connection Manager with mock IB Gateway
- Market Data Adapter with simulated data
- Order Execution with paper trading account

**End-to-End Tests:**
- Full workflow with IB Gateway paper trading
- Market data → Order placement → Position tracking
- Reconnection scenarios

### 8.2 Test Coverage Target

- **Goal:** >80% code coverage
- **Critical:** 100% on Connection Manager and Order Execution
- **Tool:** pytest-cov

---

## 9. LOGGING AND MONITORING

### 9.1 Logging Levels

**DEBUG:** Detailed information for debugging  
**INFO:** Normal operations  
**WARNING:** Anomalous but manageable situations  
**ERROR:** Errors requiring attention  
**CRITICAL:** Fatal errors  

### 9.2 Log Structure

```python
from loguru import logger

logger.add(
    "logs/pa_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="7 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}"
)
```

### 9.3 Monitoring Metrics

**Connection Health:**
- Connection uptime
- Reconnection count
- Last heartbeat timestamp

**Market Data:**
- Active subscriptions count
- Data update frequency
- Missing ticks count

**Orders:**
- Orders placed/day
- Fill rate
- Average execution time
- Rejection rate

---

## 10. KNOWN LIMITATIONS

### 10.1 TWS API Limitations

**Rate Limits:**
- 50 requests/second (with 100 market data lines)
- 60 historical data requests / 10 minutes
- Pacing violations → temporary disconnection

**Market Data:**
- Snapshots every 250ms (stocks)
- Not real tick-by-tick (aggregated)
- Requires active subscriptions

**Connection:**
- Requires IB Gateway/TWS running
- Manual login (not headless)
- Daily restart required

### 10.2 MVP Limitations

**Not Included in This Version:**
- Integration with other modules
- Backtesting engine
- Advanced order types (Algos, Combos)
- Multi-account support
- Advanced real-time P&L calculations

---

## 11. FUTURE ROADMAP

### Phase 2: Integration (Post-MVP)
- [ ] Integration with U module (data provider)
- [ ] Integration with OE module (order engine)
- [ ] ZMQ/IPC communication
- [ ] Message queuing

### Phase 3: Advanced Features
- [ ] Advanced order types
- [ ] Multi-account support
- [ ] Risk management integration
- [ ] Performance analytics

### Phase 4: Production Optimization
- [ ] High-frequency optimizations
- [ ] Distributed deployment
- [ ] Failover mechanisms
- [ ] Advanced monitoring

---

## 12. HOURS ESTIMATION

### Development (Total: 18-24 hours)

**Setup & Configuration (2-3 hours):**
- [ ] Project structure setup
- [ ] Dependencies installation
- [ ] Configuration files
- [ ] IB Gateway setup

**Core Development (10-12 hours):**
- [ ] Connection Manager (2-3 hours)
- [ ] Market Data Adapter (3-4 hours)
- [ ] Order Execution Adapter (3-4 hours)
- [ ] Account Manager (2-3 hours)
- [ ] State Manager (1-2 hours)

**Testing (3-4 hours):**
- [ ] Unit tests (1-2 hours)
- [ ] Integration tests (1-2 hours)
- [ ] End-to-end testing (1 hour)

**Documentation (2-3 hours):**
- [ ] Code documentation
- [ ] README
- [ ] User guide
- [ ] API reference

**Buffer/Contingency (1-2 hours):**
- [ ] Bug fixes
- [ ] Refinements
- [ ] Unexpected issues

### Total Estimated: **18-24 hours** of development

**Distribution by days (8 hours/day):**
- Day 1: Setup + Connection Manager + Market Data (8 hours)
- Day 2: Order Execution + Account Manager (8 hours)
- Day 3: Testing + Documentation + Buffer (6-8 hours)

**Total: 2.5-3 days of work**

---

## 13. RISKS AND MITIGATION

### 13.1 Technical Risks

**Risk 1: IB Gateway/TWS instability**
- **Probability:** Medium
- **Impact:** High
- **Mitigation:** Robust auto-reconnection logic

**Risk 2: Pacing violations**
- **Probability:** Medium
- **Impact:** Medium
- **Mitigation:** Implemented rate limiting

**Risk 3: Data quality issues**
- **Probability:** Low
- **Impact:** Medium
- **Mitigation:** Extensive validation and logging

---

## 14. CONCLUSIONS

### 14.1 Summary

This Platform Adapter MVP will provide a **solid and functional foundation** for algorithmic trading with Interactive Brokers. The modular architecture allows for **easy expansion** in future phases for integration with other system modules.

### 14.2 Advantages of This Design

✅ **Modular:** Independent and reusable components  
✅ **Testable:** Architecture allows unit and integration testing  
✅ **Maintainable:** Clean code with separation of concerns  
✅ **Resilient:** Robust error handling and reconnection logic  
✅ **Scalable:** Ready for future extensions  

### 14.3 Immediate Next Steps

1. **Approval of this spec** by Pete Davis
2. **Creation of detailed task list** (Task 4)
3. **Environment setup** and dependencies
4. **Start development** following proposed architecture

---

## APPENDIX A: Usage Example

```python
from platform_adapter import PlatformAdapter

# Initialize
pa = PlatformAdapter(config_path="config.yaml")

# Connect
pa.connect()

# Subscribe to market data
def on_quote_update(symbol, data):
    print(f"{symbol}: Bid={data.bid}, Ask={data.ask}")

pa.market_data.subscribe_quotes(["AAPL", "MSFT"], on_quote_update)

# Place order
order_id = pa.orders.place_order(
    symbol="AAPL",
    action="BUY",
    quantity=100,
    order_type="LMT",
    limit_price=150.00
)

# Check positions
positions = pa.account.get_positions()
for pos in positions:
    print(f"{pos.symbol}: {pos.quantity} shares")

# Disconnect
pa.disconnect()
```

---

**Document created:** January 21, 2026  
**Version:** 1.0  
**Status:** ✅ Ready for review  
**Estimation:** 18-24 hours (2.5-3 days)
