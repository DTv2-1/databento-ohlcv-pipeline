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

## 2. ARQUITECTURA DEL PLATFORM ADAPTER

### 2.1 Diagrama de Componentes

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

### 2.2 Componentes Principales

#### 2.2.1 Connection Manager
**Responsabilidad:** Gestionar la conexión con TWS/Gateway

**Funciones:**
- Establecer conexión inicial con TWS/Gateway
- Detectar desconexiones
- Auto-reconexión con backoff exponencial
- Health checks periódicos
- Thread management para message processing

**Interfaz:**
```python
class ConnectionManager:
    def connect(host: str, port: int, client_id: int) -> bool
    def disconnect() -> None
    def is_connected() -> bool
    def reconnect() -> bool
    def get_connection_status() -> ConnectionStatus
```

#### 2.2.2 Market Data Adapter
**Responsabilidad:** Streaming y retrieval de market data

**Funciones:**
- Subscribe/unsubscribe to real-time quotes
- Request historical data (OHLCV)
- Request real-time bars (5-second)
- Tick-by-tick data (opcional)
- Rate limiting para pacing violations

**Interfaz:**
```python
class MarketDataAdapter:
    def subscribe_quotes(symbols: List[str], callback: Callable) -> None
    def unsubscribe_quotes(symbols: List[str]) -> None
    def get_historical_data(symbol: str, duration: str, bar_size: str) -> pd.DataFrame
    def subscribe_real_time_bars(symbol: str, callback: Callable) -> None
```

#### 2.2.3 Order Execution Adapter
**Responsabilidad:** Colocación y gestión de órdenes

**Funciones:**
- Place orders (Market, Limit, Stop, Stop-Limit)
- Cancel orders
- Modify orders
- Track order status
- Execution reports

**Interfaz:**
```python
class OrderExecutionAdapter:
    def place_order(symbol: str, action: str, quantity: int, order_type: str, **kwargs) -> int
    def cancel_order(order_id: int) -> bool
    def modify_order(order_id: int, **kwargs) -> bool
    def get_order_status(order_id: int) -> OrderStatus
    def get_open_orders() -> List[Order]
```

#### 2.2.4 Account Manager
**Responsabilidad:** Información de cuenta y posiciones

**Funciones:**
- Account summary (balance, buying power, etc.)
- Position tracking
- P&L tracking (realized/unrealized)
- Account updates subscription

**Interfaz:**
```python
class AccountManager:
    def get_account_summary() -> AccountSummary
    def get_positions() -> List[Position]
    def get_pnl() -> PnL
    def subscribe_account_updates(callback: Callable) -> None
```

#### 2.2.5 State Manager
**Responsabilidad:** Mantener estado interno sincronizado

**Funciones:**
- Cache de positions
- Cache de orders
- Cache de account values
- Reconciliación periódica con IB

**Interfaz:**
```python
class StateManager:
    def update_position(position: Position) -> None
    def update_order(order: Order) -> None
    def update_account_value(key: str, value: Any) -> None
    def get_cached_positions() -> List[Position]
    def get_cached_orders() -> List[Order]
```

---

## 3. TECNOLOGÍAS Y STACK TÉCNICO

### 3.1 Lenguaje de Programación

**Python 3.11+**
- Requisito mínimo de TWS API
- Compatible con todo el stack existente
- Excelente para trading algorítmico

### 3.2 Librerías Principales

#### TWS API Integration
```python
ibapi==10.25.0  # Librería oficial de Interactive Brokers
```

**Instalación:**
```bash
# Desde TWS API installation
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

#### Async (Opcional para mejoras futuras)
```python
asyncio  # Built-in Python 3.11+
```

### 3.3 Development Tools

```python
pytest==7.4.0           # Testing
pytest-asyncio==0.21.0  # Async testing
black==23.7.0           # Code formatting
pylint==2.17.5          # Linting
mypy==1.4.1             # Type checking
```

---

## 4. ESTRUCTURA DEL PROYECTO

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

## 5. CONFIGURACIÓN Y SETUP

### 5.1 Requisitos Previos

**Software:**
- [x] Python 3.11+ instalado
- [x] IB Gateway o TWS instalado (build 952.x+)
- [x] TWS API instalado (v9.72+)
- [x] Cuenta IBKR Pro con paper trading habilitado

**Network:**
- [x] Puerto 7497 (paper) o 7496 (live) accesible
- [x] Firewall configurado para localhost

### 5.2 Instalación

**Paso 1: Clonar repositorio**
```bash
cd /Users/1di/DataBento
mkdir platform_adapter
cd platform_adapter
```

**Paso 2: Crear entorno virtual**
```bash
python3.11 -m venv venv
source venv/bin/activate  # macOS/Linux
```

**Paso 3: Instalar dependencias**
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

**Paso 4: Instalar TWS API**
```bash
cd ~/IBJts/source/pythonclient
python setup.py install
```

**Paso 5: Configurar credenciales**
```bash
cp .env.example .env
# Editar .env con configuración
```

### 5.3 Archivo de Configuración

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

## 6. FLUJO DE DATOS Y OPERACIÓN

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

## 7. MANEJO DE ERRORES Y RESILIENCIA

### 7.1 Error Handling Strategy

**Niveles de Errores:**
1. **Connection Errors (Critical)**
   - Auto-reconnect con backoff exponencial
   - Log de todos los intentos
   - Notificación al usuario

2. **API Errors (Warning/Error)**
   - Pacing violations → Rate limiting
   - Invalid contracts → Validation pre-request
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
    """Evitar pacing violations"""
    
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

### 8.1 Niveles de Testing

**Unit Tests:**
- Validación de modelos (Contract, Order, Position)
- Utilidades (Logger, RateLimiter, Validators)
- State Manager operations

**Integration Tests:**
- Connection Manager con mock IB Gateway
- Market Data Adapter con datos simulados
- Order Execution con paper trading account

**End-to-End Tests:**
- Full workflow con IB Gateway paper trading
- Market data → Order placement → Position tracking
- Reconnection scenarios

### 8.2 Test Coverage Target

- **Objetivo:** >80% code coverage
- **Crítico:** 100% en Connection Manager y Order Execution
- **Tool:** pytest-cov

### 8.3 Continuous Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/platform_adapter --cov-report=html

# Run specific test
pytest tests/test_connection.py -v -k test_connect
```

---

## 9. LOGGING Y MONITORING

### 9.1 Logging Levels

**DEBUG:** Información detallada para debugging
- Todos los callbacks de TWS API
- State changes detallados

**INFO:** Operaciones normales
- Connection established
- Orders placed/filled
- Positions updated

**WARNING:** Situaciones anómalas pero manejables
- Pacing violations (con rate limiting)
- Stale data
- Retries de conexión

**ERROR:** Errores que requieren atención
- Connection failures después de retries
- Order rejections
- Validation errors

**CRITICAL:** Errores fatales
- Unrecoverable connection loss
- Configuration errors

### 9.2 Log Structure

```python
from loguru import logger

# Configure logger
logger.add(
    "logs/pa_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="7 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}"
)

# Usage
logger.info("Connected to IB Gateway")
logger.warning("Rate limit approaching: {}/{}", current, max)
logger.error("Order rejected: {}", error_msg)
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

**Performance:**
- Callback processing time
- Message queue length
- Memory usage

---

## 10. DEPLOYMENT

### 10.1 Deployment Environments

**Development:**
- Local machine
- Paper trading account
- Full logging enabled

**Staging (Futuro):**
- Dedicated server
- Paper trading account
- Production-like configuration

**Production (Futuro):**
- Dedicated server
- Live trading account
- Optimized logging

### 10.2 Pre-Deployment Checklist

- [ ] All tests passing
- [ ] Code coverage >80%
- [ ] Configuration reviewed
- [ ] IB Gateway configured correctly
- [ ] Paper trading tested successfully
- [ ] Error handling verified
- [ ] Logging validated
- [ ] Documentation updated

---

## 11. LIMITACIONES CONOCIDAS

### 11.1 TWS API Limitations

**Rate Limits:**
- 50 requests/segundo (con 100 market data lines)
- 60 historical data requests / 10 minutos
- Pacing violations → desconexión temporal

**Market Data:**
- Snapshots cada 250ms (stocks)
- No es tick-by-tick real (son agregados)
- Requiere suscripciones activas

**Connection:**
- Requiere IB Gateway/TWS corriendo
- Login manual (no headless)
- Restart diario requerido

### 11.2 MVP Limitations

**No Incluido en Esta Versión:**
- Integración con otros módulos
- Backtesting engine
- Advanced order types (Algos, Combos)
- Multi-account support
- Real-time P&L calculations avanzadas

---

## 12. ROADMAP FUTURO

### Phase 2: Integration (Post-MVP)
- [ ] Integración con módulo U (data provider)
- [ ] Integración con módulo OE (order engine)
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

## 13. ESTIMACIÓN DE HORAS

### Desarrollo (Total: 18-24 horas)

**Setup & Configuration (2-3 horas):**
- [ ] Project structure setup
- [ ] Dependencies installation
- [ ] Configuration files
- [ ] IB Gateway setup

**Core Development (10-12 horas):**
- [ ] Connection Manager (2-3 horas)
- [ ] Market Data Adapter (3-4 horas)
- [ ] Order Execution Adapter (3-4 horas)
- [ ] Account Manager (2-3 horas)
- [ ] State Manager (1-2 horas)

**Testing (3-4 horas):**
- [ ] Unit tests (1-2 horas)
- [ ] Integration tests (1-2 horas)
- [ ] End-to-end testing (1 hora)

**Documentation (2-3 horas):**
- [ ] Code documentation
- [ ] README
- [ ] User guide
- [ ] API reference

**Buffer/Contingency (1-2 horas):**
- [ ] Bug fixes
- [ ] Refinements
- [ ] Unexpected issues

### Total Estimado: **18-24 horas** de desarrollo

**Distribución por días (8 horas/día):**
- Día 1: Setup + Connection Manager + Market Data (8 horas)
- Día 2: Order Execution + Account Manager (8 horas)
- Día 3: Testing + Documentation + Buffer (6-8 horas)

**Total: 2.5-3 días de trabajo**

---

## 14. RIESGOS Y MITIGACIÓN

### 14.1 Riesgos Técnicos

**Riesgo 1: IB Gateway/TWS inestabilidad**
- **Probabilidad:** Media
- **Impacto:** Alto
- **Mitigación:** Auto-reconnection logic robusto

**Riesgo 2: Pacing violations**
- **Probabilidad:** Media
- **Impacto:** Medio
- **Mitigación:** Rate limiting implementado

**Riesgo 3: Data quality issues**
- **Probabilidad:** Baja
- **Impacto:** Medio
- **Mitigación:** Validation y logging extensivo

### 14.2 Riesgos de Proyecto

**Riesgo 1: Cuenta IB no disponible**
- **Probabilidad:** Baja
- **Impacto:** Alto
- **Mitigación:** Paper trading account ya confirmado

**Riesgo 2: API changes incompatibles**
- **Probabilidad:** Muy baja
- **Impacto:** Alto
- **Mitigación:** Pin versión TWS API

---

## 15. CONCLUSIONES

### 15.1 Resumen

Este Platform Adapter MVP proporcionará una **base sólida y funcional** para trading algorítmico con Interactive Brokers. La arquitectura modular permite **fácil expansión** en fases futuras para integración con otros módulos del sistema.

### 15.2 Ventajas de Este Diseño

✅ **Modular:** Componentes independientes y reutilizables  
✅ **Testeable:** Architecture permite unit y integration testing  
✅ **Mantenible:** Código limpio con separación de concerns  
✅ **Resiliente:** Error handling y reconnection logic robustos  
✅ **Escalable:** Preparado para extensiones futuras  

### 15.3 Próximos Pasos Inmediatos

1. **Aprobación de esta spec** por Pete Davis
2. **Creación de task list detallada** (Tarea 4)
3. **Setup de entorno** y dependencias
4. **Inicio de desarrollo** siguiendo la arquitectura propuesta

---

## APÉNDICE A: Interfaces de Usuario

### CLI Interface (Ejemplo)

```python
# Start PA
python -m platform_adapter.main --env development

# Commands (future interactive mode)
> connect
Connected to IB Gateway on 127.0.0.1:7497

> subscribe AAPL MSFT TSLA
Subscribed to 3 symbols

> place_order AAPL BUY 100 LMT 150.00
Order placed: ID 1001

> get_positions
AAPL: 100 shares @ $149.50

> disconnect
Disconnected
```

---

## APÉNDICE B: Ejemplo de Uso

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

**Documento creado:** Enero 21, 2026  
**Versión:** 1.0  
**Status:** ✅ Listo para revisión  
**Estimación:** 18-24 horas (2.5-3 días)
