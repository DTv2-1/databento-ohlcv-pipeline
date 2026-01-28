# Análisis Detallado de Documentación TWS API

**Fecha:** Enero 21, 2026  
**Objetivo:** Analizar TWS API para implementación de trading algorítmico

---

## 1. RESUMEN EJECUTIVO

La TWS API es un protocolo TCP Socket que permite comunicación bidireccional con TWS o IB Gateway para trading automatizado. Versión actual: **9.72+**

**Componentes Principales:**
- **EClient**: Envía requests a TWS
- **EWrapper**: Recibe responses de TWS
- **EReader**: Lee mensajes del socket y los encola

---

## 2. PROCESO DE AUTENTICACIÓN

### 2.1 Requisitos Previos

**Obligatorios:**
1. **Cuenta IBKR Pro fondeada y aprobada**
2. **TWS o IB Gateway instalado** (versión 952.x o superior)
3. **TWS API instalado** (versión 9.72+ recomendada)
4. **Python 3.11.0** o superior

**Market Data:**
- Suscripciones activas para instrumentos específicos
- Cuenta fondeada (excepto forex y bonds)
- Permisos de trading configurados

### 2.2 Configuración de TWS/Gateway

**Paso 1: Habilitar API**
```
TWS/Gateway → File/Edit → Global Configuration → API → Settings
✓ Enable "ActiveX and Socket Clients"
✗ Disable "Read-Only API"
✓ Socket Port: 7496 (live) / 7497 (paper)
✓ Trusted IPs: 127.0.0.1 (localhost)
```

**Paso 2: Configuraciones Recomendadas**

**Lock and Exit:**
- ✓ Never lock Trader Workstation
- ✓ Auto restart (disponible desde v974+)
- Permite correr Lunes-Sábado sin re-autenticación
- Domingo requiere re-login después de server reset

**Memory Allocation:**
- Recomendado: 4000 MB para API users
- Ajustar según memoria disponible

**API Precautions:**
- Enable "Bypass Order Precautions for API orders"
- Enable "Bypass US Stocks market data in shares warning for API orders"
- Bypass otros warnings según necesidad

**API Logging:**
```
✓ Create API message log file
✓ Logging Level: Detail
✓ Include Market Data in API Log (opcional)
```

### 2.3 Proceso de Conexión

**Arquitectura de Conexión:**
```python
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from threading import Thread

class IBApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        print(f"Error {errorCode}: {errorString}")
        
    def nextValidId(self, orderId):
        # Esta callback indica que la conexión está completa
        print(f"Connection successful. Next valid order ID: {orderId}")
        self.nextOrderId = orderId

# Crear instancia y conectar
app = IBApp()
app.connect("127.0.0.1", 7497, clientId=0)

# Iniciar thread de mensajes
api_thread = Thread(target=app.run, daemon=True)
api_thread.start()
```

**Flujo de Conexión:**
1. `eConnect()` establece socket TCP
2. Handshake de versiones TWS ↔ API
3. TWS envía información inicial:
   - Account number(s)
   - Next valid order ID
   - Connection time
4. `nextValidId()` callback confirma conexión lista
5. Crear EReader thread para procesar mensajes

**IMPORTANTE:** No enviar requests hasta recibir `nextValidId()` callback

### 2.4 Autenticación y Seguridad

**No hay API keys:** La autenticación es manual a través del TWS/Gateway GUI
- Login con username y password
- 2FA si está configurado
- Por razones de seguridad, NO existe auto-login headless

**Sesión Única:**
- Solo una sesión activa por username
- Si ya está logueado en TWS, API no puede conectar con mismo username
- Solución: Crear múltiples usernames en Account Management

**Auto-restart (v974+):**
```
Configuración → Lock and Exit → Auto restart
- Permite correr 6 días seguidos sin re-autenticación
- Domingo requiere re-login manual
```

---

## 3. ENDPOINTS/FUNCIONES CLAVE

### 3.1 Market Data Subscription

#### reqMktData - Real-Time Market Data (L1)

**Propósito:** Streaming de market data (Top of Book)

**Función:**
```python
def reqMktData(self, reqId, contract, genericTickList, snapshot, 
               regulatorySnapshot, mktDataOptions):
    """
    reqId: Identificador único para el request
    contract: Contract object (símbolo, tipo, exchange, etc.)
    genericTickList: String de tick types adicionales ("233,236")
    snapshot: True para snapshot único, False para streaming
    regulatorySnapshot: True para regulatory snapshot
    mktDataOptions: Lista de TagValue para opciones adicionales
    """
```

**Callbacks Recibidos:**
```python
def tickPrice(self, reqId, tickType, price, attrib):
    # Precios: bid, ask, last, close, etc.
    pass

def tickSize(self, reqId, tickType, size):
    # Tamaños: bid size, ask size, volume, etc.
    pass

def tickString(self, reqId, tickType, value):
    # Data string: last timestamp, RT volume, etc.
    pass
```

**Generic Tick Types Importantes:**
- `233`: RT Volume (Time & Sales)
- `236`: Shortable shares
- `258`: Fundamental ratios
- `293`: Trade count
- `294`: Trade rate
- `295`: Volume rate

**Ejemplo Completo:**
```python
from ibapi.contract import Contract

# Crear contrato
contract = Contract()
contract.symbol = "AAPL"
contract.secType = "STK"
contract.exchange = "SMART"
contract.currency = "USD"

# Solicitar market data
reqId = 1001
app.reqMktData(reqId, contract, "", False, False, [])

# Callbacks procesarán data automáticamente
# Para cancelar:
app.cancelMktData(reqId)
```

**Limitaciones:**
- Requiere market data subscriptions activas
- Máximo de líneas simultáneas según plan (default: 100)
- Data no es tick-by-tick, son snapshots agregados varias veces por segundo
- Stocks: snapshot cada 250ms
- Options: snapshot cada 100ms

#### reqHistoricalData - Historical Market Data

**Propósito:** Datos históricos en formato candlestick

**Función:**
```python
def reqHistoricalData(self, reqId, contract, endDateTime, durationStr,
                      barSizeSetting, whatToShow, useRTH, formatDate,
                      keepUpToDate, chartOptions):
    """
    reqId: Identificador único
    contract: Contract object
    endDateTime: Fecha/hora final ("20230101 23:59:59" o "" para ahora)
    durationStr: Período ("1 D", "1 W", "1 M", "1 Y")
    barSizeSetting: Tamaño barra ("1 min", "5 mins", "1 hour", "1 day")
    whatToShow: Tipo de data ("TRADES", "MIDPOINT", "BID", "ASK")
    useRTH: 1=Regular Trading Hours, 0=All hours
    formatDate: 1=yyyyMMdd HH:mm:ss, 2=epoch seconds
    keepUpToDate: True=streaming updates, False=one-time
    chartOptions: Lista de TagValue para opciones
    """
```

**Callback:**
```python
def historicalData(self, reqId, bar):
    """
    bar contiene:
    - date: Timestamp
    - open, high, low, close: Precios
    - volume: Volumen
    - average: Precio promedio
    - barCount: Número de trades
    """
    print(f"{bar.date}: O={bar.open} H={bar.high} L={bar.low} C={bar.close} V={bar.volume}")

def historicalDataEnd(self, reqId, start, end):
    # Indica fin de transmisión histórica
    print(f"Historical data complete: {start} to {end}")
```

**Bar Sizes Disponibles:**
- Segundos: 1 secs, 5 secs, 10 secs, 15 secs, 30 secs
- Minutos: 1 min, 2 mins, 3 mins, 5 mins, 10 mins, 15 mins, 20 mins, 30 mins
- Horas: 1 hour, 2 hours, 3 hours, 4 hours, 8 hours
- Días: 1 day
- Semanas: 1 week
- Meses: 1 month

**Duration Strings:**
- Segundos: S (ej: "1800 S" = 30 minutos)
- Días: D (ej: "5 D" = 5 días)
- Semanas: W (ej: "2 W" = 2 semanas)
- Meses: M (ej: "6 M" = 6 meses)
- Años: Y (ej: "1 Y" = 1 año)

**What to Show Options:**
- `TRADES`: Trade data
- `MIDPOINT`: Midpoint entre bid/ask
- `BID`: Bid prices
- `ASK`: Ask prices
- `BID_ASK`: Bid y Ask
- `ADJUSTED_LAST`: Adjusted for splits/dividends
- `HISTORICAL_VOLATILITY`: Historical volatility
- `OPTION_IMPLIED_VOLATILITY`: Implied volatility

**Ejemplo:**
```python
# Solicitar 1 año de datos diarios
from datetime import datetime

contract = Contract()
contract.symbol = "AAPL"
contract.secType = "STK"
contract.exchange = "SMART"
contract.currency = "USD"

endDateTime = ""  # Ahora
durationStr = "1 Y"
barSize = "1 day"
whatToShow = "TRADES"

app.reqHistoricalData(
    reqId=4001,
    contract=contract,
    endDateTime=endDateTime,
    durationStr=durationStr,
    barSizeSetting=barSize,
    whatToShow=whatToShow,
    useRTH=1,
    formatDate=1,
    keepUpToDate=False,
    chartOptions=[]
)
```

**Pacing Limitations:**
- Máximo 60 requests en 600 segundos (10 minutos)
- Violaciones resultan en pacing violations y posible desconexión
- Para bars ≤30 secs, restricciones más estrictas

#### reqRealTimeBars - Real-Time 5-Second Bars

**Propósito:** Barras de 5 segundos en tiempo real

**Función:**
```python
def reqRealTimeBars(self, reqId, contract, barSize, whatToShow, useRTH, 
                    realTimeBarsOptions):
    """
    barSize: Siempre 5 (segundos)
    whatToShow: "TRADES", "MIDPOINT", "BID", "ASK"
    """
```

**Callback:**
```python
def realtimeBar(self, reqId, time, open, high, low, close, volume, wap, count):
    print(f"{time}: O={open} H={high} L={low} C={close} V={volume}")
```

**Limitación:** Solo 5 segundos disponibles actualmente

#### reqTickByTickData - Tick-by-Tick Data

**Propósito:** Data tick por tick más granular

**Función:**
```python
def reqTickByTickData(self, reqId, contract, tickType, numberOfTicks, 
                      ignoreSize):
    """
    tickType: "Last", "AllLast", "BidAsk", "MidPoint"
    numberOfTicks: Número de ticks históricos (0 para streaming)
    ignoreSize: True para ignorar size updates
    """
```

**Callbacks:**
```python
def tickByTickAllLast(self, reqId, tickType, time, price, size, 
                      tickAttribLast, exchange, specialConditions):
    # Todos los trades
    pass

def tickByTickBidAsk(self, reqId, time, bidPrice, askPrice, 
                     bidSize, askSize, tickAttribBidAsk):
    # Bid/Ask updates
    pass

def tickByTickMidPoint(self, reqId, time, midPoint):
    # Midpoint updates
    pass
```

### 3.2 Order Placement/Management

#### placeOrder - Place or Modify Order

**Propósito:** Colocar o modificar órdenes

**Función:**
```python
def placeOrder(self, orderId, contract, order):
    """
    orderId: Unique order ID (obtener de nextValidId)
    contract: Contract object
    order: Order object con detalles de orden
    """
```

**Order Object:**
```python
from ibapi.order import Order

order = Order()
order.action = "BUY"  # o "SELL"
order.totalQuantity = 100
order.orderType = "LMT"  # "MKT", "LMT", "STP", "STP LMT", etc.
order.lmtPrice = 150.0  # Para limit orders
order.auxPrice = 145.0  # Para stop orders (stop price)
order.tif = "GTC"  # "DAY", "GTC", "IOC", "GTD"
order.outsideRth = False  # True para trading fuera de horas
order.transmit = True  # True para enviar, False para staging
```

**Order Types Disponibles:**
- `MKT`: Market order
- `LMT`: Limit order
- `STP`: Stop order
- `STP LMT`: Stop limit order
- `TRAIL`: Trailing stop
- `TRAIL LIMIT`: Trailing stop limit
- `MOC`: Market on close
- `LOC`: Limit on close
- `MIT`: Market if touched
- `LIT`: Limit if touched
- Y muchos más...

**Callbacks:**
```python
def openOrder(self, orderId, contract, order, orderState):
    # Detalles de orden abierta
    print(f"Open Order ID: {orderId}, Status: {orderState.status}")

def orderStatus(self, orderId, status, filled, remaining, avgFillPrice,
                permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
    # Status updates: "PendingSubmit", "Submitted", "Filled", "Cancelled", etc.
    print(f"Order {orderId} Status: {status}, Filled: {filled}/{filled+remaining}")

def execDetails(self, reqId, contract, execution):
    # Detalles de ejecución
    print(f"Executed: {execution.shares} @ {execution.price}")

def commissionReport(self, commissionReport):
    # Reporte de comisiones
    print(f"Commission: {commissionReport.commission}")
```

**Ejemplo Completo:**
```python
# Crear contrato
contract = Contract()
contract.symbol = "AAPL"
contract.secType = "STK"
contract.exchange = "SMART"
contract.currency = "USD"

# Crear orden limit
order = Order()
order.action = "BUY"
order.totalQuantity = 100
order.orderType = "LMT"
order.lmtPrice = 150.00
order.tif = "GTC"

# Colocar orden
orderId = app.nextOrderId
app.placeOrder(orderId, contract, order)
app.nextOrderId += 1
```

#### cancelOrder - Cancel Order

**Función:**
```python
def cancelOrder(self, orderId, manualCancelOrderTime=""):
    # manualCancelOrderTime: Time for manual cancel in format "yyyyMMdd HH:mm:ss"
```

#### reqOpenOrders - Request Open Orders

**Función:**
```python
def reqOpenOrders(self):
    # Solicita todas las órdenes abiertas de este cliente API
```

#### reqAllOpenOrders - Request All Open Orders

**Función:**
```python
def reqAllOpenOrders(self):
    # Solicita TODAS las órdenes abiertas (incluyendo TWS manual)
```

#### reqAutoOpenOrders - Auto-bind Open Orders

**Función:**
```python
def reqAutoOpenOrders(self, autoBind):
    """
    autoBind: True para recibir updates de órdenes existentes
    """
```

#### reqGlobalCancel - Cancel All Orders

**Función:**
```python
def reqGlobalCancel(self):
    # Cancela TODAS las órdenes activas (incluyendo TWS manual)
```

#### reqCompletedOrders - Request Completed Orders

**Función:**
```python
def reqCompletedOrders(self, apiOnly):
    """
    apiOnly: True para solo órdenes de API, False para todas
    """
```

**Callback:**
```python
def completedOrder(self, contract, order, orderState):
    print(f"Completed: {order.action} {order.totalQuantity} {contract.symbol}")

def completedOrdersEnd(self):
    print("Completed orders transmission complete")
```

### 3.3 Account Information

#### reqAccountSummary - Account Summary

**Propósito:** Información resumida de cuenta(s)

**Función:**
```python
def reqAccountSummary(self, reqId, groupName, tags):
    """
    reqId: Identificador único
    groupName: "All" para todas las cuentas, o nombre específico
    tags: String de tags separados por coma, o AccountSummaryTags.AllTags
    """
```

**Tags Disponibles:**
```python
from ibapi.common import AccountSummaryTags

# Tags individuales
"AccountType,NetLiquidation,TotalCashValue,SettledCash,AccruedCash,\
BuyingPower,EquityWithLoanValue,PreviousEquityWithLoanValue,\
GrossPositionValue,RegTEquity,RegTMargin,SMA,InitMarginReq,\
MaintMarginReq,AvailableFunds,ExcessLiquidity,Cushion,\
FullInitMarginReq,FullMaintMarginReq,FullAvailableFunds,\
FullExcessLiquidity,LookAheadNextChange,LookAheadInitMarginReq,\
LookAheadMaintMarginReq,LookAheadAvailableFunds,\
LookAheadExcessLiquidity,HighestSeverity,DayTradesRemaining,Leverage"

# O usar todas
AccountSummaryTags.AllTags
```

**Callbacks:**
```python
def accountSummary(self, reqId, account, tag, value, currency):
    print(f"Account {account}: {tag} = {value} {currency}")

def accountSummaryEnd(self, reqId):
    print("Account summary complete")
```

**Ejemplo:**
```python
# Solicitar todas las métricas para todas las cuentas
from ibapi.common import AccountSummaryTags

app.reqAccountSummary(9001, "All", AccountSummaryTags.AllTags)

# O específicas
app.reqAccountSummary(9001, "All", "NetLiquidation,BuyingPower")

# Cancelar
app.cancelAccountSummary(9001)
```

**IMPORTANTE:**
- Solo 2 suscripciones simultáneas permitidas
- Updates cada 3 minutos
- IBrokers con >50 subaccounts no pueden usar "All"

#### reqAccountUpdates - Account Updates

**Propósito:** Updates detallados de cuenta específica

**Función:**
```python
def reqAccountUpdates(self, subscribe, acctCode):
    """
    subscribe: True para iniciar, False para parar
    acctCode: Número de cuenta (vacío para single account)
    """
```

**Callbacks:**
```python
def updateAccountValue(self, key, val, currency, accountName):
    # Account values: NetLiquidation, AvailableFunds, etc.
    print(f"{accountName}: {key} = {val} {currency}")

def updatePortfolio(self, contract, position, marketPrice, marketValue,
                    averageCost, unrealizedPNL, realizedPNL, accountName):
    # Portfolio positions
    print(f"{contract.symbol}: Pos={position}, Price={marketPrice}, PnL={unrealizedPNL}")

def updateAccountTime(self, timeStamp):
    # Timestamp del último update
    print(f"Account time: {timeStamp}")

def accountDownloadEnd(self, accountName):
    # Fin de transmisión inicial
    print(f"Account download complete: {accountName}")
```

**Ejemplo:**
```python
# Iniciar subscription
app.reqAccountUpdates(True, "")  # Vacío para default account

# Parar subscription
app.reqAccountUpdates(False, "")
```

**Limitación:**
- Solo una cuenta a la vez
- Updates cada 3 minutos (o si hay cambio en posiciones)

### 3.4 Position Tracking

#### reqPositions - Request All Positions

**Propósito:** Todas las posiciones de todas las cuentas

**Función:**
```python
def reqPositions(self):
    # No requiere parámetros
```

**Callbacks:**
```python
def position(self, account, contract, position, avgCost):
    print(f"{account}: {contract.symbol} - Pos={position}, AvgCost={avgCost}")

def positionEnd(self):
    print("Position data complete")
```

**Ejemplo:**
```python
# Solicitar positions
app.reqPositions()

# Cancelar
app.cancelPositions()
```

#### reqPositionsMulti - Request Positions by Account/Model

**Propósito:** Posiciones filtradas por cuenta o modelo

**Función:**
```python
def reqPositionsMulti(self, reqId, account, modelCode):
    """
    reqId: Identificador único
    account: Número de cuenta o "" para todas
    modelCode: Código de modelo o "" para todos
    """
```

**Callbacks:**
```python
def positionMulti(self, reqId, account, modelCode, contract, pos, avgCost):
    print(f"{account}/{modelCode}: {contract.symbol} = {pos} @ {avgCost}")

def positionMultiEnd(self, reqId):
    print("Position multi complete")
```

#### reqPnL - P&L for Account

**Propósito:** Profit & Loss en tiempo real por cuenta

**Función:**
```python
def reqPnL(self, reqId, account, modelCode):
    """
    reqId: Identificador único
    account: Número de cuenta
    modelCode: Código de modelo (opcional)
    """
```

**Callback:**
```python
def pnl(self, reqId, dailyPnL, unrealizedPnL, realizedPnL):
    print(f"PnL: Daily={dailyPnL}, Unrealized={unrealizedPnL}, Realized={realizedPnL}")
```

#### reqPnLSingle - P&L for Individual Position

**Propósito:** P&L para posición específica

**Función:**
```python
def reqPnLSingle(self, reqId, account, modelCode, conid):
    """
    reqId: Identificador único
    account: Número de cuenta
    modelCode: Código de modelo
    conid: Contract ID de la posición
    """
```

**Callback:**
```python
def pnlSingle(self, reqId, pos, dailyPnL, unrealizedPnL, realizedPnL, value):
    print(f"Position PnL: Pos={pos}, Daily={dailyPnL}, Unrealized={unrealizedPnL}")
```

---

## 4. BIBLIOTECAS PYTHON DISPONIBLES

### 4.1 ibapi (Oficial)

**Descripción:** Librería oficial de Interactive Brokers

**Instalación:**
```bash
# Opción 1: Desde TWS API installation
cd ~/TWS API/source/pythonclient
python setup.py install

# Opción 2: Direct pip (NO RECOMENDADO - no es oficial)
# pip install ibapi
```

**Pros:**
- ✅ Oficial y mantenida por IB
- ✅ Completa - todas las funciones disponibles
- ✅ Documentación oficial
- ✅ Versión sync con TWS releases

**Contras:**
- ❌ API de bajo nivel - más verboso
- ❌ Requiere manejo manual de threads
- ❌ Arquitectura asíncrona compleja
- ❌ Curva de aprendizaje pronunciada

**Estructura Básica:**
```python
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order

class IBApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.nextOrderId = None
        
    def nextValidId(self, orderId):
        self.nextOrderId = orderId
        print(f"Next order ID: {orderId}")
        
    def tickPrice(self, reqId, tickType, price, attrib):
        print(f"Tick Price. Req: {reqId}, Type: {tickType}, Price: {price}")

app = IBApp()
app.connect("127.0.0.1", 7497, clientId=0)
app.run()  # Blocking call - procesa mensajes
```

**Threading Requerido:**
```python
from threading import Thread
import time

app = IBApp()
app.connect("127.0.0.1", 7497, clientId=0)

# Thread para procesamiento de mensajes
api_thread = Thread(target=app.run, daemon=True)
api_thread.start()

# Esperar conexión
time.sleep(1)

# Ahora se pueden hacer requests
if app.nextOrderId:
    # Listo para operar
    pass
```

### 4.2 ib_insync (Third-Party - DEPRECATED)

**⚠️ IMPORTANTE:** La librería original `ib_insync` está **DEPRECATED** y no recibe updates

**Último Update:** Compatible con TWS API legacy (pre-974)

**Status:** NO recomendado para nuevos proyectos

### 4.3 ib_async (Third-Party - Recomendado)

**Descripción:** Fork modernizado de ib_insync por uno de sus creadores originales

**Instalación:**
```bash
pip install ib_async
```

**Pros:**
- ✅ API de alto nivel - más Pythonic
- ✅ Manejo automático de threads
- ✅ Soporte asyncio nativo
- ✅ Métodos bloqueantes y async disponibles
- ✅ Estado sincronizado automáticamente
- ✅ Documentación extensa

**Contras:**
- ❌ Third-party - no oficial de IB
- ❌ Puede retrasarse vs API oficial
- ❌ IB Support no puede ayudar con problemas

**Estructura Básica:**
```python
from ib_async import IB, Stock, MarketOrder

ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)

# Crear contrato
contract = Stock('AAPL', 'SMART', 'USD')

# Request market data (bloqueante)
ticker = ib.reqMktData(contract)
ib.sleep(2)  # Esperar data
print(f"Bid: {ticker.bid}, Ask: {ticker.ask}")

# Place order (bloqueante)
order = MarketOrder('BUY', 100)
trade = ib.placeOrder(contract, order)

print(f"Order status: {trade.orderStatus.status}")

ib.disconnect()
```

**Async Version:**
```python
import asyncio
from ib_async import IB, Stock

async def main():
    ib = IB()
    await ib.connectAsync('127.0.0.1', 7497, clientId=1)
    
    contract = Stock('AAPL', 'SMART', 'USD')
    ticker = ib.reqMktData(contract)
    
    await asyncio.sleep(2)
    print(f"Price: {ticker.last}")
    
    ib.disconnect()

asyncio.run(main())
```

**State Management:**
```python
# ib_async mantiene estado automáticamente
print(ib.accountValues())  # Valores de cuenta
print(ib.positions())  # Posiciones actuales
print(ib.openOrders())  # Órdenes abiertas
print(ib.trades())  # Todos los trades
```

### 4.4 Comparación de Librerías

| Feature | ibapi (Oficial) | ib_async (Third-Party) |
|---------|----------------|------------------------|
| **Mantenimiento** | Oficial IB | Comunidad |
| **Updates** | Sync con TWS | Puede retrasarse |
| **API Level** | Bajo nivel | Alto nivel |
| **Threading** | Manual | Automático |
| **Asyncio** | No nativo | Nativo |
| **Estado** | Manual | Automático |
| **Curva aprendizaje** | Alta | Media |
| **Support IB** | ✅ Sí | ❌ No |
| **Documentación** | Oficial | Excelente (community) |
| **Best for** | Producción crítica | Rapid development |

### 4.5 Recomendación

**Para Producción:**
- Usar **ibapi** (oficial) para máxima compatibilidad y support
- Implementar abstracciones propias sobre ibapi

**Para Prototipado:**
- Usar **ib_async** para desarrollo rápido
- Migrar a ibapi para producción si es necesario

**Nunca Usar:**
- ❌ `ib_insync` (deprecated)
- ❌ `pip install ibapi` (no es oficial)

---

## 5. REQUISITOS PREVIOS DETALLADOS

### 5.1 Software Requirements

**Sistema Operativo:**
- ✅ Windows 10/11
- ✅ macOS 10.14+
- ✅ Linux (Ubuntu 20.04+, otras distribuciones)

**Python:**
- **Versión Mínima:** 3.11.0
- **Recomendada:** 3.11.x o 3.12.x
- **No Soportado:** Python 2.x, Python 3.10 o inferior

**TWS o IB Gateway:**
- **Versión Mínima:** Build 952.x
- **Recomendada:** Última versión stable
- **Offline vs Online:** Usar Offline para evitar auto-updates

**TWS API:**
- **Versión Mínima:** 9.72+
- **Recomendada:** Última versión (10.25+ a Enero 2026)
- **Importante:** TWS version debe ser compatible con API version

**Java (para IB Gateway):**
- **Versión Mínima:** Java 8 update 192
- **Recomendada:** Java 11 o superior
- Verificar: `java -version`

### 5.2 Account Requirements

**Tipo de Cuenta:**
- ✅ **IBKR Pro** (requerido)
- ❌ IBKR Lite (NO soporta API)

**Estado de Cuenta:**
- ✅ Abierta y aprobada
- ✅ Fondeada (monto depende de productos)
- ✅ Trading permissions configuradas

**Paper Trading:**
- ✅ Gratuito para testing
- ✅ Se crea desde Account Management
- ✅ Usa mismo API que live
- ⚠️ Comportamiento puede variar (simulado)

### 5.3 Market Data Subscriptions

**Requerido para Trading:**
- Suscripciones activas para instrumentos específicos
- Configurar en Account Management → Market Data

**Costo Típico:**
- US Stocks: ~$10-30/mes por exchange
- Forex: Gratuito
- Futures: Varía por exchange
- Options: Incluido con underlying

**Market Data Lines:**
- **Default:** 100 líneas simultáneas
- **Booster Packs:** +100 líneas por ~$30/mes
- **Fórmula API Pacing:** Max requests/sec = (lines / 2)

### 5.4 Network Requirements

**Ports:**
- **TWS Production:** 7496
- **TWS Paper Trading:** 7497
- **IB Gateway Production:** 4001
- **IB Gateway Paper Trading:** 4002

**Firewall:**
- Permitir outbound connections a IB servers
- Localhost (127.0.0.1) para conexión local

**Trusted IPs (para conexiones remotas):**
- Configurar en TWS → Global Configuration → API → Settings
- Agregar IPs permitidas

### 5.5 Development Environment

**IDE Recomendados:**
- PyCharm
- VS Code
- Spyder
- Jupyter Notebook (para testing)

**Librerías Python Adicionales:**
```bash
pip install pandas  # Data analysis
pip install numpy  # Numerical operations
pip install matplotlib  # Plotting
pip install asyncio  # Async operations (built-in Python 3.11+)
```

**Git (Recomendado):**
```bash
git clone https://github.com/InteractiveBrokers/tws-api-public.git
```

### 5.6 Installation Checklist

- [ ] Python 3.11+ instalado
- [ ] TWS o IB Gateway descargado
- [ ] TWS API descargado
- [ ] ibapi instalado (`python setup.py install`)
- [ ] Cuenta IBKR Pro creada y fondeada
- [ ] Paper trading account creado
- [ ] Market data subscriptions configuradas
- [ ] TWS API settings habilitadas
- [ ] API logging habilitado (para debugging)
- [ ] Socket ports configurados correctamente
- [ ] Firewall rules configuradas

---

## 6. ARQUITECTURA Y PATRONES

### 6.1 Request/Response Pattern

**Flujo Típico:**
```
1. Client (EClient) → Request → TWS
2. TWS procesa request
3. TWS → Response(s) → EWrapper callbacks
4. Application procesa callbacks
```

**Importante:**
- Casi todos los requests son **asíncronos**
- Un request puede generar múltiples callbacks
- Callbacks pueden llegar en cualquier orden
- Usar reqId para correlacionar requests/responses

### 6.2 Threading Model

**ibapi Requiere Mínimo 2 Threads:**

**Thread 1: Main Application**
- Lógica de negocio
- Envío de requests (EClient methods)

**Thread 2: Message Processing**
- EReader thread
- Procesa mensajes del socket
- Invoca callbacks en EWrapper

**Ejemplo Threading:**
```python
from threading import Thread
import time

class IBApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.data = {}
        
    def tickPrice(self, reqId, tickType, price, attrib):
        self.data[reqId] = price

# Crear app
app = IBApp()
app.connect("127.0.0.1", 7497, 0)

# Thread para procesar mensajes
def run_loop():
    app.run()

api_thread = Thread(target=run_loop, daemon=True)
api_thread.start()

# Main thread puede continuar
time.sleep(1)  # Wait for connection

# Hacer requests desde main thread
app.reqMktData(1001, contract, "", False, False, [])
```

### 6.3 Error Handling

**Error Callback:**
```python
def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
    """
    reqId: Request ID relacionado (o -1 si es general)
    errorCode: Código de error
    errorString: Descripción del error
    """
    if errorCode in [2104, 2106, 2158]:
        # Mensajes informativos, no errores
        print(f"Info: {errorString}")
    elif errorCode < 1000:
        # Sistema errors
        print(f"System Error {errorCode}: {errorString}")
    elif errorCode < 2000:
        # Warning messages
        print(f"Warning {errorCode}: {errorString}")
    else:
        # Notification messages
        print(f"Notification {errorCode}: {errorString}")
```

**Error Codes Comunes:**
- `100`: Max rate of messages per second exceeded
- `162`: Historical data pacing violation
- `200`: No security definition found
- `201`: Order rejected
- `321`: Error validating request
- `502`: Couldn't connect to TWS
- `504`: Not connected
- `2104`: Market data farm connection OK
- `2106`: HMDS data farm connection OK
- `2158`: Sec-def data farm connection OK

### 6.4 State Management

**Best Practice: Track State Manually**
```python
class IBApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        
        # State tracking
        self.nextOrderId = None
        self.connected = False
        self.positions = {}
        self.orders = {}
        self.account_values = {}
        
    def nextValidId(self, orderId):
        self.nextOrderId = orderId
        self.connected = True
        
    def position(self, account, contract, position, avgCost):
        key = f"{account}_{contract.conId}"
        self.positions[key] = {
            'symbol': contract.symbol,
            'position': position,
            'avgCost': avgCost
        }
        
    def updateAccountValue(self, key, val, currency, accountName):
        self.account_values[key] = {
            'value': val,
            'currency': currency,
            'account': accountName
        }
```

---

## 7. EJEMPLOS PRÁCTICOS COMPLETOS

### 7.1 Ejemplo: Conexión Básica

```python
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from threading import Thread
import time

class TradingApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        print(f"Error {errorCode}: {errorString}")
        
    def nextValidId(self, orderId):
        print(f"Connected! Next Order ID: {orderId}")
        self.nextOrderId = orderId

def main():
    app = TradingApp()
    app.connect("127.0.0.1", 7497, clientId=0)
    
    # Start message processing thread
    api_thread = Thread(target=app.run, daemon=True)
    api_thread.start()
    
    # Wait for connection
    time.sleep(2)
    
    print("Application running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDisconnecting...")
        app.disconnect()

if __name__ == "__main__":
    main()
```

### 7.2 Ejemplo: Market Data Streaming

```python
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from threading import Thread
import time

class MarketDataApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.data = {}
        
    def tickPrice(self, reqId, tickType, price, attrib):
        print(f"Tick Price - ReqId: {reqId}, Type: {tickType}, Price: {price}")
        self.data[reqId] = price
        
    def tickSize(self, reqId, tickType, size):
        print(f"Tick Size - ReqId: {reqId}, Type: {tickType}, Size: {size}")

def main():
    app = MarketDataApp()
    app.connect("127.0.0.1", 7497, clientId=0)
    
    Thread(target=app.run, daemon=True).start()
    time.sleep(2)
    
    # Create contract
    contract = Contract()
    contract.symbol = "AAPL"
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"
    
    # Request market data
    app.reqMktData(1001, contract, "", False, False, [])
    
    # Let it run for 10 seconds
    time.sleep(10)
    
    # Cancel market data
    app.cancelMktData(1001)
    app.disconnect()

if __name__ == "__main__":
    main()
```

### 7.3 Ejemplo: Historical Data

```python
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from threading import Thread
import time
import pandas as pd

class HistoricalDataApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.data = []
        
    def historicalData(self, reqId, bar):
        self.data.append({
            'date': bar.date,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume
        })
        
    def historicalDataEnd(self, reqId, start, end):
        print(f"Historical data complete: {start} to {end}")
        print(f"Received {len(self.data)} bars")

def main():
    app = HistoricalDataApp()
    app.connect("127.0.0.1", 7497, clientId=0)
    
    Thread(target=app.run, daemon=True).start()
    time.sleep(2)
    
    # Create contract
    contract = Contract()
    contract.symbol = "AAPL"
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"
    
    # Request 1 day of 5-minute bars
    app.reqHistoricalData(
        reqId=4001,
        contract=contract,
        endDateTime="",
        durationStr="1 D",
        barSizeSetting="5 mins",
        whatToShow="TRADES",
        useRTH=1,
        formatDate=1,
        keepUpToDate=False,
        chartOptions=[]
    )
    
    # Wait for data
    time.sleep(5)
    
    # Convert to DataFrame
    df = pd.DataFrame(app.data)
    print(df.head())
    
    app.disconnect()

if __name__ == "__main__":
    main()
```

### 7.4 Ejemplo: Place Order

```python
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from threading import Thread
import time

class OrderApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.nextOrderId = None
        
    def nextValidId(self, orderId):
        self.nextOrderId = orderId
        print(f"Next Order ID: {orderId}")
        
    def openOrder(self, orderId, contract, order, orderState):
        print(f"Open Order - ID: {orderId}, Status: {orderState.status}")
        
    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice,
                    permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        print(f"Order Status - ID: {orderId}, Status: {status}, Filled: {filled}/{filled+remaining}")
        
    def execDetails(self, reqId, contract, execution):
        print(f"Execution - {execution.shares} shares @ {execution.price}")

def main():
    app = OrderApp()
    app.connect("127.0.0.1", 7497, clientId=0)
    
    Thread(target=app.run, daemon=True).start()
    time.sleep(2)
    
    # Wait for nextValidId
    while app.nextOrderId is None:
        time.sleep(0.1)
    
    # Create contract
    contract = Contract()
    contract.symbol = "AAPL"
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"
    
    # Create order
    order = Order()
    order.action = "BUY"
    order.totalQuantity = 100
    order.orderType = "LMT"
    order.lmtPrice = 150.00
    order.tif = "GTC"
    
    # Place order
    app.placeOrder(app.nextOrderId, contract, order)
    print(f"Order placed with ID: {app.nextOrderId}")
    
    # Wait for order updates
    time.sleep(5)
    
    # Optional: Cancel order
    # app.cancelOrder(app.nextOrderId, "")
    
    app.disconnect()

if __name__ == "__main__":
    main()
```

---

## 8. LIMITACIONES Y CONSIDERACIONES

### 8.1 Rate Limits

**Pacing Limitations:**
- **Default:** 50 requests/segundo (para 100 market data lines)
- **Fórmula:** Max requests/sec = (Market Data Lines / 2)
- **Violación:** Error 100, 3 violaciones = desconexión

**Historical Data:**
- **General:** 60 requests en 600 segundos (10 minutos)
- **Bars ≤30 secs:** Más restrictivo
- **Violación:** Pacing violation message + posible ban temporal

**Message Rate:**
- **Client → TWS:** 50 mensajes/segundo
- **TWS → Client:** Sin límite

### 8.2 Market Data Limitations

**Data Frequency:**
- **Stocks:** Snapshots cada 250ms
- **Options:** Snapshots cada 100ms
- **No es tick-by-tick:** Datos agregados

**Simultaneous Subscriptions:**
- Limitado por Market Data Lines
- Default: 100 lines
- Booster packs: +100 lines cada uno

**Historical Data:**
- **Pacing:** 60 requests / 10 minutos
- **Availability:** Varía por instrumento
- **Granularity:** Limitada para períodos antiguos

### 8.3 Connection Limitations

**Single Session:**
- Solo un login por username simultáneamente
- Solución: Crear múltiples usernames

**Daily Restart:**
- TWS/Gateway diseñado para restart diario
- Auto-restart disponible (v974+)
- Domingo requiere re-autenticación manual

**API Clients:**
- Hasta 32 clientes simultáneos por TWS instance
- Cada cliente necesita clientId único

### 8.4 Order Limitations

**Order Precautions:**
- Warnings por default en TWS
- Disable via Global Configuration → API → Precautions

**Market Hours:**
- Regular Trading Hours vs Extended Hours
- Configurar en Order object: `outsideRth`

**Order Types:**
- No todos los order types disponibles para todos los instrumentos
- Verificar con TWS manualmente primero

---

## 9. DEBUGGING Y TROUBLESHOOTING

### 9.1 Habilitar Logging

**API Logs:**
```
TWS → Global Configuration → API → Settings
✓ Create API message log file
✓ Logging Level: Detail
✓ Include Market Data in API Log (opcional)
```

**Ubicación de Logs:**
- **Windows:** `C:\Jts\{username}\`
- **Mac/Linux:** `~/Jts/{username}/`
- **Formato:** `api.{clientId}.{day}.log`

**Ver Logs:**
```
Ctrl+Alt+U (Windows) o Cmd+Opt+U (Mac)
```

### 9.2 Problemas Comunes

**Cannot Connect (Error 502):**
- TWS/Gateway no está corriendo
- API no está habilitado
- Puerto incorrecto
- Firewall bloqueando conexión

**Requests Ignored:**
- Enviados antes de `nextValidId()` callback
- Esperar hasta que conexión esté completa

**No Market Data:**
- Market data subscriptions no activas
- Cuenta no fondeada
- Símbolo incorrecto
- Exchange incorrecto

**Pacing Violations:**
- Demasiados requests muy rápido
- Implementar rate limiting
- Usar queues para requests

### 9.3 Best Practices

1. **Siempre esperar `nextValidId()` antes de requests**
2. **Usar try/except para error handling**
3. **Implementar logging comprehensivo**
4. **Test en Paper Trading primero**
5. **Implementar reconexión automática**
6. **Usar queues para rate limiting**
7. **Track estado internamente**
8. **Disconnect limpiamente al cerrar**

---

## 10. RECURSOS ADICIONALES

### 10.1 Documentación Oficial

- **TWS API Doc:** https://interactivebrokers.github.io/tws-api/
- **IBKR Campus:** https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/
- **Python Course:** https://www.interactivebrokers.com/campus/trading-course/python-tws-api/
- **GitHub:** https://github.com/InteractiveBrokers/tws-api-public

### 10.2 Librerías

- **ibapi:** Incluido en TWS API installation
- **ib_async:** https://pypi.org/project/ib_async/
- **ib_async docs:** https://ib-async.readthedocs.io/

### 10.3 Comunidad

- **IB Forum:** https://groups.io/g/twsapi
- **Reddit:** r/algotrading
- **Stack Overflow:** Tag [interactive-brokers]

### 10.4 Tutoriales y Guías

- **AlgoTrading101:** https://algotrading101.com/learn/interactive-brokers-python-api-native-guide/
- **IBKR Webinars:** Recorded webinars en IBKR Campus
- **YouTube:** Múltiples tutoriales disponibles

---

## 11. PRÓXIMOS PASOS

**Setup Inicial (Completado):**
- ✅ Investigar opciones de API
- ✅ Analizar documentación TWS API

**Siguientes Tareas:**
1. ⏭️ Crear especificación rápida del PA
2. ⏭️ Crear task list con estimaciones
3. ⏭️ Instalar TWS o IB Gateway
4. ⏭️ Instalar TWS API y configurar Python
5. ⏭️ Crear Paper Trading Account
6. ⏭️ Implementar conexión básica
7. ⏭️ Testing de market data streaming
8. ⏭️ Testing de order placement
9. ⏭️ Desarrollar estrategia de trading

---

## APÉNDICE A: Quick Reference Card

### Conexión
```python
app = IBApp()
app.connect("127.0.0.1", 7497, clientId=0)
Thread(target=app.run, daemon=True).start()
```

### Market Data
```python
app.reqMktData(reqId, contract, "", False, False, [])
app.cancelMktData(reqId)
```

### Historical Data
```python
app.reqHistoricalData(reqId, contract, "", "1 D", "5 mins", 
                      "TRADES", 1, 1, False, [])
```

### Orders
```python
app.placeOrder(orderId, contract, order)
app.cancelOrder(orderId, "")
app.reqOpenOrders()
```

### Account
```python
app.reqAccountSummary(reqId, "All", AccountSummaryTags.AllTags)
app.reqPositions()
app.reqPnL(reqId, account, "")
```

### Contract Template
```python
contract = Contract()
contract.symbol = "AAPL"
contract.secType = "STK"
contract.exchange = "SMART"
contract.currency = "USD"
```

### Order Template
```python
order = Order()
order.action = "BUY"
order.totalQuantity = 100
order.orderType = "LMT"
order.lmtPrice = 150.00
order.tif = "GTC"
```

---

**Documento generado:** Enero 21, 2026  
**Basado en:** TWS API v9.72+ y Python 3.11+  
**Status:** ✅ Tarea 2 Completada  
**Tiempo invertido:** ~45 minutos
