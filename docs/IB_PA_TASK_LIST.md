# Platform Adapter - Interactive Brokers
## Task List Detallada con Estimaciones

**Fecha:** Enero 21, 2026  
**Cliente:** Pete Davis / RaptorTrade  
**Proyecto:** PA MVP - IB Integration  
**Estimación Total:** 18-24 horas (2.5-3 días)

---

## RESUMEN EJECUTIVO

### Distribución de Tiempo

| Fase | Tareas | Horas Estimadas | % del Total |
|------|--------|-----------------|-------------|
| **Setup & Config** | 5 tareas | 2-3 horas | 11-13% |
| **Core Development** | 11 tareas | 10-12 horas | 53-55% |
| **Testing** | 6 tareas | 3-4 horas | 16-18% |
| **Documentation** | 4 tareas | 2-3 horas | 11-13% |
| **Buffer** | - | 1-2 horas | 5-9% |
| **TOTAL** | **26 tareas** | **18-24 horas** | **100%** |

### Cronograma Recomendado

**Día 1 (8 horas):**
- Setup & Configuration completo
- Connection Manager
- Market Data Adapter (inicio)

**Día 2 (8 horas):**
- Market Data Adapter (finalización)
- Order Execution Adapter
- Account Manager

**Día 3 (6-8 horas):**
- State Manager
- Testing completo
- Documentation
- Buffer para ajustes

---

## FASE 1: SETUP & CONFIGURATION
**Estimación Total:** 2-3 horas

### Task 1.1: Project Structure Setup
**Duración:** 30-45 minutos  
**Prioridad:** Alta  
**Dependencies:** Ninguna

**Subtareas:**
- [ ] Crear estructura de directorios según spec
- [ ] Inicializar repositorio Git (si no existe)
- [ ] Crear archivos `__init__.py` en todos los packages
- [ ] Setup `.gitignore` con patterns de Python

**Archivos a crear:**
```
platform_adapter/
├── src/platform_adapter/
│   ├── __init__.py
│   ├── config/
│   ├── core/
│   ├── adapters/
│   ├── models/
│   └── utils/
├── tests/
├── scripts/
└── logs/
```

**Criterio de completitud:**
- ✓ Estructura de directorios completa
- ✓ Git inicializado y primer commit hecho
- ✓ `.gitignore` configurado

---

### Task 1.2: Environment & Dependencies
**Duración:** 45-60 minutos  
**Prioridad:** Alta  
**Dependencies:** Task 1.1

**Subtareas:**
- [ ] Crear entorno virtual Python 3.11+
- [ ] Crear `requirements.txt` con dependencias principales
- [ ] Crear `requirements-dev.txt` con dependencias de desarrollo
- [ ] Instalar TWS API desde `~/IBJts/source/pythonclient`
- [ ] Instalar todas las dependencias
- [ ] Verificar instalación con `pip list`

**Dependencias principales:**
```
# requirements.txt
pandas>=2.1.0
numpy>=1.24.0
python-dotenv>=1.0.0
pyyaml>=6.0
loguru>=0.7.0
```

**Dependencias desarrollo:**
```
# requirements-dev.txt
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
black>=23.7.0
pylint>=2.17.5
mypy>=1.4.1
```

**Criterio de completitud:**
- ✓ Entorno virtual activado
- ✓ `ibapi` instalado correctamente
- ✓ Todas las dependencias instaladas sin errores
- ✓ `import ibapi` funciona

---

### Task 1.3: Configuration Files
**Duración:** 30-45 minutos  
**Prioridad:** Alta  
**Dependencies:** Task 1.2

**Subtareas:**
- [ ] Crear `config/config.yaml` con configuración base
- [ ] Crear `.env.example` con template
- [ ] Crear `.env` con valores reales (no commitear)
- [ ] Crear `config/settings.py` para cargar configuración
- [ ] Validar que configuración se carga correctamente

**config.yaml:**
```yaml
ib_connection:
  host: "127.0.0.1"
  port: 7497
  client_id: 1
  timeout: 30
  auto_reconnect: true
  reconnect_max_attempts: 5
```

**.env:**
```bash
IB_HOST=127.0.0.1
IB_PORT=7497
IB_CLIENT_ID=1
IB_ACCOUNT_ID=DU123456
LOG_LEVEL=INFO
ENVIRONMENT=development
```

**Criterio de completitud:**
- ✓ Archivos de configuración creados
- ✓ Settings loader funciona
- ✓ Valores se cargan desde .env y config.yaml

---

### Task 1.4: IB Gateway Setup & Test
**Duración:** 30-45 minutos  
**Prioridad:** Alta  
**Dependencies:** Task 1.3

**Subtareas:**
- [ ] Instalar IB Gateway (si no está instalado)
- [ ] Configurar IB Gateway para API access
- [ ] Habilitar socket clients en settings
- [ ] Configurar puerto 7497 (paper trading)
- [ ] Login con credenciales de paper trading
- [ ] Crear script de test básico de conexión
- [ ] Verificar que conexión funciona

**Script de test:**
```python
# scripts/test_connection.py
from ibapi.client import EClient
from ibapi.wrapper import EWrapper

class TestApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
    
    def nextValidId(self, orderId):
        print(f"✓ Connected! Next Order ID: {orderId}")
        self.disconnect()

app = TestApp()
app.connect("127.0.0.1", 7497, 0)
app.run()
```

**Criterio de completitud:**
- ✓ IB Gateway instalado y configurado
- ✓ API access habilitado
- ✓ Script de test se conecta exitosamente
- ✓ Callback `nextValidId` recibido

---

### Task 1.5: Logging Setup
**Duración:** 30 minutos  
**Prioridad:** Media  
**Dependencies:** Task 1.2

**Subtareas:**
- [ ] Crear `utils/logger.py` con configuración de loguru
- [ ] Configurar rotación de logs
- [ ] Configurar niveles de logging
- [ ] Configurar formato de logs
- [ ] Crear función helper para logging
- [ ] Test de logging básico

**logger.py:**
```python
from loguru import logger
import sys

def setup_logger(log_dir="logs", level="INFO"):
    logger.remove()
    
    # Console
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
    )
    
    # File
    logger.add(
        f"{log_dir}/pa_{{time:YYYY-MM-DD}}.log",
        rotation="00:00",
        retention="7 days",
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )
    
    return logger
```

**Criterio de completitud:**
- ✓ Logger configurado
- ✓ Logs se escriben en consola y archivo
- ✓ Rotación funciona
- ✓ Niveles de logging funcionan

---

## FASE 2: CORE DEVELOPMENT
**Estimación Total:** 10-12 horas

### Task 2.1: Base Models
**Duración:** 60-90 minutos  
**Prioridad:** Alta  
**Dependencies:** Task 1.5

**Subtareas:**
- [ ] Crear `models/contract.py` con clase Contract
- [ ] Crear `models/order.py` con clase Order
- [ ] Crear `models/position.py` con clase Position
- [ ] Crear `models/account.py` con clase AccountSummary
- [ ] Crear métodos de conversión desde/hacia ibapi objects
- [ ] Agregar type hints completos
- [ ] Agregar docstrings

**contract.py:**
```python
from dataclasses import dataclass
from ibapi.contract import Contract as IBContract

@dataclass
class Contract:
    symbol: str
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"
    
    def to_ib_contract(self) -> IBContract:
        contract = IBContract()
        contract.symbol = self.symbol
        contract.secType = self.sec_type
        contract.exchange = self.exchange
        contract.currency = self.currency
        return contract
```

**Criterio de completitud:**
- ✓ Todos los modelos creados
- ✓ Type hints completos
- ✓ Conversiones to/from ibapi funcionan
- ✓ Docstrings completos

---

### Task 2.2: Connection Manager - Core
**Duración:** 2-3 horas  
**Prioridad:** Crítica  
**Dependencies:** Task 2.1

**Subtareas:**
- [ ] Crear `core/connection_manager.py`
- [ ] Implementar clase `IBApp` heredando de EClient y EWrapper
- [ ] Implementar método `connect()`
- [ ] Implementar método `disconnect()`
- [ ] Implementar callback `nextValidId()`
- [ ] Implementar callback `error()`
- [ ] Implementar callback `connectionClosed()`
- [ ] Agregar threading para message processing
- [ ] Agregar health check básico

**connection_manager.py (estructura):**
```python
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from threading import Thread
import time

class ConnectionManager(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.next_order_id = None
        self.connected = False
        
    def connect(self, host: str, port: int, client_id: int) -> bool:
        super().connect(host, port, client_id)
        
        # Start message thread
        thread = Thread(target=self.run, daemon=True)
        thread.start()
        
        # Wait for connection
        timeout = 10
        start = time.time()
        while not self.connected and (time.time() - start) < timeout:
            time.sleep(0.1)
        
        return self.connected
    
    def nextValidId(self, orderId: int):
        self.next_order_id = orderId
        self.connected = True
        logger.info(f"Connected! Next Order ID: {orderId}")
    
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        logger.error(f"Error {errorCode}: {errorString}")
```

**Criterio de completitud:**
- ✓ Conexión se establece correctamente
- ✓ Threading funciona
- ✓ nextValidId recibido
- ✓ Disconnect funciona
- ✓ Error handling básico implementado

---

### Task 2.3: Connection Manager - Reconnection
**Duración:** 60-90 minutos  
**Prioridad:** Alta  
**Dependencies:** Task 2.2

**Subtareas:**
- [ ] Implementar detección de desconexión
- [ ] Implementar reconnection logic con backoff exponencial
- [ ] Agregar max_attempts configurable
- [ ] Agregar callback de reconnection status
- [ ] Test de reconnection manual

**Reconnection logic:**
```python
def reconnect(self) -> bool:
    for attempt in range(self.max_reconnect_attempts):
        delay = self._get_backoff_delay(attempt)
        logger.info(f"Reconnection attempt {attempt+1}/{self.max_reconnect_attempts} in {delay}s")
        time.sleep(delay)
        
        if self.connect(self.host, self.port, self.client_id):
            logger.info("Reconnection successful")
            return True
    
    logger.error("Reconnection failed after max attempts")
    return False

def _get_backoff_delay(self, attempt: int) -> float:
    base_delay = 2.0
    max_delay = 60.0
    delay = base_delay * (2 ** attempt)
    return min(delay, max_delay)
```

**Criterio de completitud:**
- ✓ Desconexión detectada automáticamente
- ✓ Reconnection se ejecuta automáticamente
- ✓ Backoff exponencial funciona
- ✓ Max attempts respetado

---

### Task 2.4: Market Data Adapter - Basic
**Duración:** 2-3 horas  
**Prioridad:** Alta  
**Dependencies:** Task 2.3

**Subtareas:**
- [ ] Crear `adapters/market_data.py`
- [ ] Implementar `subscribe_quotes()`
- [ ] Implementar `unsubscribe_quotes()`
- [ ] Implementar callbacks: `tickPrice()`, `tickSize()`, `tickString()`
- [ ] Agregar tracking de subscriptions activas
- [ ] Agregar user callbacks
- [ ] Implementar basic data caching

**market_data.py:**
```python
class MarketDataAdapter:
    def __init__(self, connection_manager):
        self.conn = connection_manager
        self.subscriptions = {}
        self.next_req_id = 1000
        
    def subscribe_quotes(self, symbols: List[str], callback: Callable):
        for symbol in symbols:
            req_id = self.next_req_id
            self.next_req_id += 1
            
            contract = Contract(symbol=symbol).to_ib_contract()
            self.conn.reqMktData(req_id, contract, "", False, False, [])
            
            self.subscriptions[req_id] = {
                'symbol': symbol,
                'callback': callback
            }
    
    def on_tick_price(self, req_id, tick_type, price, attrib):
        if req_id in self.subscriptions:
            callback = self.subscriptions[req_id]['callback']
            callback(self.subscriptions[req_id]['symbol'], {
                'type': 'price',
                'tick_type': tick_type,
                'value': price
            })
```

**Criterio de completitud:**
- ✓ Subscribe funciona
- ✓ Unsubscribe funciona
- ✓ Callbacks recibidos correctamente
- ✓ User callbacks ejecutados
- ✓ Multiple symbols supported

---

### Task 2.5: Market Data Adapter - Historical Data
**Duración:** 60-90 minutos  
**Prioridad:** Media  
**Dependencies:** Task 2.4

**Subtareas:**
- [ ] Implementar `get_historical_data()`
- [ ] Implementar callbacks: `historicalData()`, `historicalDataEnd()`
- [ ] Agregar validación de parámetros
- [ ] Convertir resultados a pandas DataFrame
- [ ] Agregar rate limiting básico

**get_historical_data():**
```python
def get_historical_data(
    self,
    symbol: str,
    duration: str = "1 D",
    bar_size: str = "5 mins",
    what_to_show: str = "TRADES"
) -> pd.DataFrame:
    req_id = self.next_req_id
    self.next_req_id += 1
    
    self.historical_data[req_id] = []
    self.historical_complete[req_id] = False
    
    contract = Contract(symbol=symbol).to_ib_contract()
    self.conn.reqHistoricalData(
        req_id, contract, "", duration, bar_size,
        what_to_show, 1, 1, False, []
    )
    
    # Wait for completion
    timeout = 30
    start = time.time()
    while not self.historical_complete[req_id] and (time.time() - start) < timeout:
        time.sleep(0.1)
    
    df = pd.DataFrame(self.historical_data[req_id])
    return df
```

**Criterio de completitud:**
- ✓ Historical data request funciona
- ✓ Data se recibe completamente
- ✓ Convertido a DataFrame correctamente
- ✓ Timeout implementado

---

### Task 2.6: Rate Limiter Utility
**Duración:** 45-60 minutos  
**Prioridad:** Media  
**Dependencies:** Task 2.4

**Subtareas:**
- [ ] Crear `utils/rate_limiter.py`
- [ ] Implementar token bucket algorithm
- [ ] Agregar método `can_proceed()`
- [ ] Agregar método `wait_if_needed()`
- [ ] Integrar con Market Data Adapter

**rate_limiter.py:**
```python
from collections import deque
import time

class RateLimiter:
    def __init__(self, max_requests: int, time_window: int):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
    
    def can_proceed(self) -> bool:
        self._cleanup_old_requests()
        return len(self.requests) < self.max_requests
    
    def wait_if_needed(self):
        while not self.can_proceed():
            time.sleep(0.1)
        self.record_request()
    
    def record_request(self):
        self.requests.append(time.time())
    
    def _cleanup_old_requests(self):
        now = time.time()
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()
```

**Criterio de completitud:**
- ✓ Rate limiting funciona
- ✓ Requests bloqueados cuando límite alcanzado
- ✓ Cleanup de requests antiguos funciona
- ✓ Integrado con Market Data Adapter

---

### Task 2.7: Order Execution Adapter - Basic
**Duración:** 2-3 horas  
**Prioridad:** Alta  
**Dependencies:** Task 2.3

**Subtareas:**
- [ ] Crear `adapters/order_execution.py`
- [ ] Implementar `place_order()` para Market y Limit orders
- [ ] Implementar `cancel_order()`
- [ ] Implementar callbacks: `openOrder()`, `orderStatus()`, `execDetails()`
- [ ] Agregar order tracking
- [ ] Agregar validación de parámetros

**order_execution.py:**
```python
from ibapi.order import Order as IBOrder

class OrderExecutionAdapter:
    def __init__(self, connection_manager):
        self.conn = connection_manager
        self.orders = {}
        
    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str,
        **kwargs
    ) -> int:
        # Validación
        assert action in ["BUY", "SELL"]
        assert order_type in ["MKT", "LMT", "STP", "STP LMT"]
        
        # Crear contract
        contract = Contract(symbol=symbol).to_ib_contract()
        
        # Crear order
        order = IBOrder()
        order.action = action
        order.totalQuantity = quantity
        order.orderType = order_type
        
        if order_type == "LMT":
            order.lmtPrice = kwargs.get('limit_price')
        
        # Place order
        order_id = self.conn.next_order_id
        self.conn.next_order_id += 1
        
        self.conn.placeOrder(order_id, contract, order)
        
        self.orders[order_id] = {
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'status': 'SUBMITTED'
        }
        
        return order_id
```

**Criterio de completitud:**
- ✓ Market orders funcionan
- ✓ Limit orders funcionan
- ✓ Order ID retornado correctamente
- ✓ Tracking de orders implementado
- ✓ Callbacks recibidos

---

### Task 2.8: Order Execution Adapter - Management
**Duración:** 60-90 minutos  
**Prioridad:** Media  
**Dependencies:** Task 2.7

**Subtareas:**
- [ ] Implementar `get_order_status()`
- [ ] Implementar `get_open_orders()`
- [ ] Implementar `modify_order()`
- [ ] Implementar callback `commissionReport()`
- [ ] Agregar order history tracking

**Criterio de completitud:**
- ✓ Order status retrieval funciona
- ✓ Open orders listing funciona
- ✓ Order modification funciona
- ✓ Commission reports recibidos

---

### Task 2.9: Account Manager
**Duración:** 2-3 horas  
**Prioridad:** Media  
**Dependencies:** Task 2.3

**Subtareas:**
- [ ] Crear `adapters/account_manager.py`
- [ ] Implementar `get_account_summary()`
- [ ] Implementar `get_positions()`
- [ ] Implementar `subscribe_account_updates()`
- [ ] Implementar callbacks: `accountSummary()`, `position()`, `updateAccountValue()`
- [ ] Agregar caching de account values

**account_manager.py:**
```python
class AccountManager:
    def __init__(self, connection_manager):
        self.conn = connection_manager
        self.account_values = {}
        self.positions = {}
        
    def get_account_summary(self) -> dict:
        req_id = 9001
        from ibapi.common import AccountSummaryTags
        
        self.conn.reqAccountSummary(req_id, "All", AccountSummaryTags.AllTags)
        
        # Wait for data
        time.sleep(2)
        
        return self.account_values.copy()
    
    def get_positions(self) -> List[Position]:
        self.positions.clear()
        self.conn.reqPositions()
        
        # Wait for data
        time.sleep(2)
        
        return list(self.positions.values())
    
    def on_position(self, account, contract, position, avgCost):
        pos = Position(
            symbol=contract.symbol,
            quantity=position,
            avg_cost=avgCost,
            account=account
        )
        self.positions[contract.symbol] = pos
```

**Criterio de completitud:**
- ✓ Account summary funciona
- ✓ Positions retrieval funciona
- ✓ Account updates subscription funciona
- ✓ Caching implementado

---

### Task 2.10: State Manager
**Duración:** 60-90 minutos  
**Prioridad:** Media  
**Dependencies:** Tasks 2.7, 2.9

**Subtareas:**
- [ ] Crear `core/state_manager.py`
- [ ] Implementar cache de positions
- [ ] Implementar cache de orders
- [ ] Implementar cache de account values
- [ ] Agregar métodos de query
- [ ] Agregar reconciliación periódica

**state_manager.py:**
```python
class StateManager:
    def __init__(self):
        self.positions = {}
        self.orders = {}
        self.account_values = {}
        self.last_update = None
        
    def update_position(self, position: Position):
        self.positions[position.symbol] = position
        self.last_update = time.time()
    
    def update_order(self, order_id: int, order_data: dict):
        self.orders[order_id] = order_data
        self.last_update = time.time()
    
    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        return list(self.positions.values())
    
    def get_order(self, order_id: int) -> Optional[dict]:
        return self.orders.get(order_id)
```

**Criterio de completitud:**
- ✓ State caching funciona
- ✓ Query methods funcionan
- ✓ Updates se reflejan correctamente
- ✓ Thread-safe (opcional)

---

### Task 2.11: Main Application & Integration
**Duración:** 60-90 minutos  
**Prioridad:** Alta  
**Dependencies:** Tasks 2.3, 2.5, 2.8, 2.9, 2.10

**Subtareas:**
- [ ] Crear `main.py` con clase principal `PlatformAdapter`
- [ ] Integrar todos los componentes
- [ ] Implementar initialization sequence
- [ ] Implementar cleanup on shutdown
- [ ] Agregar CLI básico (opcional)

**main.py:**
```python
class PlatformAdapter:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)
        self.logger = setup_logger()
        
        self.connection = ConnectionManager()
        self.state = StateManager()
        self.market_data = MarketDataAdapter(self.connection)
        self.orders = OrderExecutionAdapter(self.connection)
        self.account = AccountManager(self.connection)
        
    def connect(self) -> bool:
        host = self.config['ib_connection']['host']
        port = self.config['ib_connection']['port']
        client_id = self.config['ib_connection']['client_id']
        
        return self.connection.connect(host, port, client_id)
    
    def disconnect(self):
        self.connection.disconnect()

if __name__ == "__main__":
    pa = PlatformAdapter()
    pa.connect()
    
    # Example usage
    pa.market_data.subscribe_quotes(["AAPL"], lambda s, d: print(f"{s}: {d}"))
    
    time.sleep(10)
    pa.disconnect()
```

**Criterio de completitud:**
- ✓ Todos los componentes integrados
- ✓ Initialization funciona
- ✓ Shutdown limpio funciona
- ✓ Example usage funciona

---

## FASE 3: TESTING
**Estimación Total:** 3-4 horas

### Task 3.1: Unit Tests - Models
**Duración:** 30-45 minutos  
**Prioridad:** Media  
**Dependencies:** Task 2.1

**Subtareas:**
- [ ] Crear `tests/test_models.py`
- [ ] Test Contract model y conversión to/from ibapi
- [ ] Test Order model y conversión
- [ ] Test Position model
- [ ] Test AccountSummary model

**Criterio de completitud:**
- ✓ Todos los modelos tienen tests
- ✓ Conversiones to/from ibapi tested
- ✓ Tests pasan

---

### Task 3.2: Unit Tests - Utilities
**Duración:** 30-45 minutos  
**Prioridad:** Baja  
**Dependencies:** Tasks 1.5, 2.6

**Subtareas:**
- [ ] Crear `tests/test_utils.py`
- [ ] Test RateLimiter
- [ ] Test Logger configuration
- [ ] Test Validators (si existen)

**Criterio de completitud:**
- ✓ RateLimiter tested completamente
- ✓ Tests pasan

---

### Task 3.3: Integration Test - Connection
**Duración:** 30-45 minutos  
**Prioridad:** Alta  
**Dependencies:** Task 2.3

**Subtareas:**
- [ ] Crear `tests/test_connection.py`
- [ ] Test conexión exitosa
- [ ] Test desconexión
- [ ] Test reconnection logic
- [ ] Test error handling

**test_connection.py:**
```python
import pytest
from platform_adapter.core.connection_manager import ConnectionManager

def test_connect():
    conn = ConnectionManager()
    result = conn.connect("127.0.0.1", 7497, 0)
    assert result == True
    assert conn.connected == True
    conn.disconnect()

def test_reconnect():
    conn = ConnectionManager()
    conn.connect("127.0.0.1", 7497, 0)
    conn.disconnect()
    result = conn.reconnect()
    assert result == True
```

**Criterio de completitud:**
- ✓ Connection tests pasan con IB Gateway
- ✓ Reconnection tested
- ✓ Error cases tested

---

### Task 3.4: Integration Test - Market Data
**Duración:** 45-60 minutos  
**Prioridad:** Alta  
**Dependencies:** Task 2.5

**Subtareas:**
- [ ] Crear `tests/test_market_data.py`
- [ ] Test subscribe_quotes()
- [ ] Test unsubscribe_quotes()
- [ ] Test get_historical_data()
- [ ] Test con múltiples symbols
- [ ] Test callbacks

**Criterio de completitud:**
- ✓ Market data tests pasan
- ✓ Historical data tested
- ✓ Callbacks verified

---

### Task 3.5: Integration Test - Orders
**Duración:** 45-60 minutos  
**Prioridad:** Alta  
**Dependencies:** Task 2.8

**Subtareas:**
- [ ] Crear `tests/test_orders.py`
- [ ] Test place_order() Market
- [ ] Test place_order() Limit
- [ ] Test cancel_order()
- [ ] Test get_order_status()
- [ ] Test con Paper Trading account

**⚠️ IMPORTANTE:** Solo usar Paper Trading account para tests

**Criterio de completitud:**
- ✓ Order placement tested
- ✓ Order cancellation tested
- ✓ Status tracking verified
- ✓ Solo en Paper Trading

---

### Task 3.6: End-to-End Test
**Duración:** 60 minutos  
**Prioridad:** Media  
**Dependencies:** Task 2.11

**Subtareas:**
- [ ] Crear `tests/test_e2e.py`
- [ ] Test full workflow: Connect → Subscribe → Place Order → Get Position → Disconnect
- [ ] Test error recovery
- [ ] Test reconnection scenario

**e2e test:**
```python
def test_full_workflow():
    pa = PlatformAdapter()
    
    # Connect
    assert pa.connect() == True
    
    # Subscribe to market data
    quotes_received = []
    pa.market_data.subscribe_quotes(
        ["AAPL"],
        lambda s, d: quotes_received.append(d)
    )
    time.sleep(5)
    assert len(quotes_received) > 0
    
    # Place order (limit far from market)
    order_id = pa.orders.place_order("AAPL", "BUY", 1, "LMT", limit_price=50.0)
    assert order_id is not None
    
    # Cancel order
    result = pa.orders.cancel_order(order_id)
    assert result == True
    
    # Disconnect
    pa.disconnect()
```

**Criterio de completitud:**
- ✓ Full workflow funciona
- ✓ Todos los componentes integrados
- ✓ Test pasa consistentemente

---

## FASE 4: DOCUMENTATION
**Estimación Total:** 2-3 horas

### Task 4.1: Code Documentation
**Duración:** 60-90 minutos  
**Prioridad:** Media  
**Dependencies:** Task 2.11

**Subtareas:**
- [ ] Agregar docstrings a todos los métodos públicos
- [ ] Agregar type hints completos
- [ ] Agregar comentarios en código complejo
- [ ] Verificar con pylint/mypy

**Formato docstring:**
```python
def place_order(
    self,
    symbol: str,
    action: str,
    quantity: int,
    order_type: str,
    **kwargs
) -> int:
    """
    Place an order with Interactive Brokers.
    
    Args:
        symbol: Stock symbol (e.g., "AAPL")
        action: "BUY" or "SELL"
        quantity: Number of shares
        order_type: "MKT", "LMT", "STP", or "STP LMT"
        **kwargs: Additional parameters (limit_price, stop_price, etc.)
    
    Returns:
        Order ID assigned by IB
    
    Raises:
        ValueError: If parameters are invalid
        ConnectionError: If not connected to IB
    
    Example:
        >>> order_id = pa.orders.place_order("AAPL", "BUY", 100, "LMT", limit_price=150.0)
    """
```

**Criterio de completitud:**
- ✓ Todos los métodos públicos documentados
- ✓ Type hints completos
- ✓ Pylint score >8.0

---

### Task 4.2: README
**Duración:** 45-60 minutos  
**Prioridad:** Alta  
**Dependencies:** Task 4.1

**Subtareas:**
- [ ] Crear README.md completo
- [ ] Sección de instalación
- [ ] Sección de configuración
- [ ] Ejemplos de uso
- [ ] Troubleshooting

**Secciones del README:**
```markdown
# Platform Adapter - Interactive Brokers

## Installation
## Configuration
## Quick Start
## Usage Examples
## API Reference
## Testing
## Troubleshooting
## License
```

**Criterio de completitud:**
- ✓ README completo y claro
- ✓ Ejemplos funcionan
- ✓ Instalación documentada

---

### Task 4.3: User Guide
**Duración:** 30-45 minutos  
**Prioridad:** Baja  
**Dependencies:** Task 4.2

**Subtareas:**
- [ ] Crear `docs/USER_GUIDE.md`
- [ ] Documentar setup de IB Gateway
- [ ] Documentar configuración de API
- [ ] Documentar workflows comunes
- [ ] Agregar ejemplos detallados

**Criterio de completitud:**
- ✓ User guide completo
- ✓ Cubre casos de uso principales
- ✓ Screenshots/ejemplos incluidos

---

### Task 4.4: API Reference
**Duración:** 30-45 minutos  
**Prioridad:** Baja  
**Dependencies:** Task 4.1

**Subtareas:**
- [ ] Crear `docs/API_REFERENCE.md`
- [ ] Documentar todas las clases públicas
- [ ] Documentar todos los métodos públicos
- [ ] Agregar ejemplos de uso

**Criterio de completitud:**
- ✓ API reference completo
- ✓ Todos los métodos documentados
- ✓ Ejemplos incluidos

---

## FASE 5: BUFFER & REFINEMENT
**Estimación Total:** 1-2 horas

### Task 5.1: Bug Fixes
**Duración:** Variable  
**Prioridad:** Alta  
**Dependencies:** Todas las anteriores

**Subtareas:**
- [ ] Revisar todos los tests
- [ ] Corregir bugs encontrados
- [ ] Verificar edge cases
- [ ] Re-test después de fixes

---

### Task 5.2: Code Cleanup
**Duración:** 30 minutos  
**Prioridad:** Baja  
**Dependencies:** Task 5.1

**Subtareas:**
- [ ] Correr black para formatting
- [ ] Correr pylint y corregir warnings
- [ ] Remover código comentado
- [ ] Remover imports no usados

---

### Task 5.3: Final Review
**Duración:** 30 minutos  
**Prioridad:** Alta  
**Dependencies:** Task 5.2

**Subtareas:**
- [ ] Review de código completo
- [ ] Verificar que todos los tests pasan
- [ ] Verificar documentación completa
- [ ] Crear checklist de deployment

---

## RESUMEN DE DEPENDENCIAS

```
Task 1.1 (Setup)
    └─> Task 1.2 (Dependencies)
        └─> Task 1.3 (Config)
            └─> Task 1.4 (IB Gateway)
        └─> Task 1.5 (Logging)
            └─> Task 2.1 (Models)
                └─> Task 2.2 (Connection Core)
                    └─> Task 2.3 (Reconnection)
                        ├─> Task 2.4 (Market Data Basic)
                        │   └─> Task 2.5 (Historical)
                        │       └─> Task 2.6 (Rate Limiter)
                        ├─> Task 2.7 (Orders Basic)
                        │   └─> Task 2.8 (Orders Mgmt)
                        └─> Task 2.9 (Account)
                            └─> Task 2.10 (State)
                                └─> Task 2.11 (Main App)
                                    └─> PHASE 3 (Testing)
                                        └─> PHASE 4 (Docs)
```

---

## CHECKLIST FINAL DE ENTREGA

### Código
- [ ] Estructura de proyecto completa
- [ ] Todos los componentes implementados
- [ ] Type hints completos
- [ ] Docstrings completos
- [ ] Código formateado con black
- [ ] Pylint score >8.0

### Testing
- [ ] Unit tests pasan (>80% coverage)
- [ ] Integration tests pasan
- [ ] E2E test pasa
- [ ] Tested con IB Gateway Paper Trading

### Documentación
- [ ] README completo
- [ ] User Guide creado
- [ ] API Reference creado
- [ ] Code comments adecuados

### Configuración
- [ ] config.yaml creado
- [ ] .env.example creado
- [ ] requirements.txt completo
- [ ] .gitignore configurado

### Deployment Ready
- [ ] IB Gateway setup documentado
- [ ] Installation steps verificados
- [ ] Troubleshooting guide creado
- [ ] Demo script funciona

---

## NOTAS IMPORTANTES

### Priorización
Si el tiempo es limitado, priorizar en este orden:
1. **CRÍTICO:** Connection Manager, Market Data Basic, Orders Basic
2. **ALTO:** Historical Data, Account Manager, Testing básico
3. **MEDIO:** State Manager, Rate Limiter, Documentation
4. **BAJO:** Advanced features, User Guide detallado

### Tiempo de Testing
Considerar que testing con Paper Trading puede tomar más tiempo:
- Market data puede tardar en conectar
- Orders pueden tardar en procesarse
- Account updates cada 3 minutos

### Risk Mitigation
- Hacer commits frecuentes
- Testear cada componente antes de seguir
- Mantener IB Gateway corriendo durante desarrollo
- Usar Paper Trading exclusivamente

---

**Documento creado:** Enero 21, 2026  
**Total de tareas:** 26 tasks  
**Estimación total:** 18-24 horas (2.5-3 días)  
**Status:** ✅ Listo para ejecución
