"""
DEMO + TEST: PA 2.0 — Verificación completa
Prueba que todo funciona: comandos, eventos, validación, stream, inmutabilidad.

Correr: python demo_pa2.py
"""

from src.platform_adapter.interfaces.pa_inputs import (
    PlaceOrderCommand, CancelOrderCommand, ModifyOrderCommand,
    FlattenCommand, SubscribeMarketDataCommand, UnsubscribeMarketDataCommand,
    HistoricalDataCommand,
)
from src.platform_adapter.interfaces.pa_outputs import (
    PAOutputStream, QuoteEvent, BarEvent, FillEvent, OrderUpdateEvent,
    PositionEvent, AccountValueEvent, ConnectionEvent, ConnectionStatus,
)
from src.platform_adapter.models.contract import Contract
from src.platform_adapter.models.order import Order, OrderStatus
from src.platform_adapter.models.position import Position
from datetime import datetime

passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"   ✅ {name}")
    else:
        failed += 1
        print(f"   ❌ {name}")


# =============================================================
print("=" * 60)
print("PA 2.0 — TEST COMPLETO")
print("=" * 60)

# =============================================================
# 1. COMANDOS VÁLIDOS
# =============================================================
print("\n── 1. Comandos válidos ──")

cmd_mkt = PlaceOrderCommand(symbol="AAPL", action="BUY", quantity=100)
check("Market order BUY 100 AAPL", cmd_mkt.symbol == "AAPL" and cmd_mkt.quantity == 100)

cmd_lmt = PlaceOrderCommand(symbol="MSFT", action="SELL", quantity=50, order_type="LMT", limit_price=400.0)
check("Limit order SELL 50 MSFT @ 400", cmd_lmt.limit_price == 400.0)

cmd_stp = PlaceOrderCommand(symbol="TSLA", action="BUY", quantity=10, order_type="STP", stop_price=200.0)
check("Stop order BUY 10 TSLA stop@200", cmd_stp.stop_price == 200.0)

cmd_stplmt = PlaceOrderCommand(symbol="AMZN", action="SELL", quantity=5, order_type="STP LMT", limit_price=180.0, stop_price=175.0)
check("Stop-limit order SELL 5 AMZN", cmd_stplmt.limit_price == 180.0 and cmd_stplmt.stop_price == 175.0)

cmd_cancel = CancelOrderCommand(order_id=1001)
check("Cancel order 1001", cmd_cancel.order_id == 1001)

cmd_modify = ModifyOrderCommand(order_id=1002, quantity=200)
check("Modify order 1002 qty→200", cmd_modify.quantity == 200)

cmd_flatten = FlattenCommand(symbol="AAPL")
check("Flatten AAPL", cmd_flatten.symbol == "AAPL")

cmd_sub = SubscribeMarketDataCommand(symbol="SPY")
check("Subscribe market data SPY", cmd_sub.symbol == "SPY" and not cmd_sub.snapshot)

cmd_unsub = UnsubscribeMarketDataCommand(symbol="SPY")
check("Unsubscribe SPY", cmd_unsub.symbol == "SPY")

cmd_hist = HistoricalDataCommand(symbol="QQQ", duration="1 W", bar_size="5 mins")
check("Historical data QQQ 1W 5min", cmd_hist.duration == "1 W" and cmd_hist.bar_size == "5 mins")

# =============================================================
# 2. VALIDACIÓN — PA rechaza basura
# =============================================================
print("\n── 2. Validación (rechaza basura) ──")

try:
    PlaceOrderCommand(symbol="X", action="HOLD", quantity=100)
    check("Rechaza action=HOLD", False)
except ValueError:
    check("Rechaza action=HOLD", True)

try:
    PlaceOrderCommand(symbol="X", action="BUY", quantity=0)
    check("Rechaza quantity=0", False)
except ValueError:
    check("Rechaza quantity=0", True)

try:
    PlaceOrderCommand(symbol="X", action="BUY", quantity=-5)
    check("Rechaza quantity negativa", False)
except ValueError:
    check("Rechaza quantity negativa", True)

try:
    PlaceOrderCommand(symbol="X", action="BUY", quantity=10, order_type="LMT")
    check("Rechaza LMT sin limit_price", False)
except ValueError:
    check("Rechaza LMT sin limit_price", True)

try:
    PlaceOrderCommand(symbol="X", action="BUY", quantity=10, order_type="STP")
    check("Rechaza STP sin stop_price", False)
except ValueError:
    check("Rechaza STP sin stop_price", True)

try:
    PlaceOrderCommand(symbol="X", action="BUY", quantity=10, order_type="STP LMT", limit_price=100.0)
    check("Rechaza STP LMT sin stop_price", False)
except ValueError:
    check("Rechaza STP LMT sin stop_price", True)

try:
    ModifyOrderCommand(order_id=1)
    check("Rechaza modify sin cambios", False)
except ValueError:
    check("Rechaza modify sin cambios", True)

try:
    ModifyOrderCommand(order_id=1, quantity=0)
    check("Rechaza modify qty=0", False)
except ValueError:
    check("Rechaza modify qty=0", True)

# =============================================================
# 3. EVENTOS DE SALIDA — todos se crean bien
# =============================================================
print("\n── 3. Eventos de salida ──")

ts = datetime.now()

q = QuoteEvent(symbol="AAPL", timestamp=ts, bid=150.0, ask=150.05, last=150.02)
check("QuoteEvent AAPL", q.symbol == "AAPL" and q.bid == 150.0)

b = BarEvent(symbol="SPY", timestamp=ts, open=450.0, high=451.0, low=449.5, close=450.5, volume=10000)
check("BarEvent SPY", b.close == 450.5 and b.volume == 10000)

ou = OrderUpdateEvent(
    order_id=1001, symbol="AAPL", status="Filled", action="BUY",
    quantity=100, order_type="MKT", filled=100, remaining=0,
    avg_fill_price=150.25, timestamp=ts,
)
check("OrderUpdateEvent filled", ou.filled == 100 and ou.status == "Filled")

f = FillEvent(
    order_id=1001, exec_id="EX001", symbol="AAPL",
    side="BOT", shares=100, price=150.25, timestamp=ts,
)
check("FillEvent AAPL", f.shares == 100 and f.price == 150.25)

p = PositionEvent(symbol="AAPL", quantity=100, avg_cost=150.25, account="U12345")
check("PositionEvent AAPL +100", p.quantity == 100)

a = AccountValueEvent(key="NetLiquidation", value="250000.00", currency="USD", account="U12345")
check("AccountValueEvent NetLiq", a.key == "NetLiquidation" and a.value == "250000.00")

c = ConnectionEvent(status=ConnectionStatus.CONNECTED, message="OK")
check("ConnectionEvent connected", c.status == ConnectionStatus.CONNECTED)

# =============================================================
# 4. INMUTABILIDAD — no se puede cambiar nada
# =============================================================
print("\n── 4. Inmutabilidad ──")

try:
    q.bid = 999.0
    check("QuoteEvent inmutable", False)
except AttributeError:
    check("QuoteEvent inmutable", True)

try:
    cmd_mkt.quantity = 999
    check("PlaceOrderCommand inmutable", False)
except AttributeError:
    check("PlaceOrderCommand inmutable", True)

try:
    p.quantity = 999
    check("PositionEvent inmutable", False)
except AttributeError:
    check("PositionEvent inmutable", True)

# =============================================================
# 5. STREAM — listeners reciben eventos
# =============================================================
print("\n── 5. Stream (PAOutputStream) ──")

stream = PAOutputStream()
recibidos = {"quotes": [], "bars": [], "fills": [], "orders": [], "positions": [], "account": [], "conn": []}

stream.on_quote(lambda e: recibidos["quotes"].append(e))
stream.on_bar(lambda e: recibidos["bars"].append(e))
stream.on_fill(lambda e: recibidos["fills"].append(e))
stream.on_order_update(lambda e: recibidos["orders"].append(e))
stream.on_position(lambda e: recibidos["positions"].append(e))
stream.on_account_value(lambda e: recibidos["account"].append(e))
stream.on_connection(lambda e: recibidos["conn"].append(e))

stream.emit_quote(q)
stream.emit_bar(b)
stream.emit_fill(f)
stream.emit_order_update(ou)
stream.emit_position(p)
stream.emit_account_value(a)
stream.emit_connection(c)

check("Quote listener recibió", len(recibidos["quotes"]) == 1)
check("Bar listener recibió", len(recibidos["bars"]) == 1)
check("Fill listener recibió", len(recibidos["fills"]) == 1)
check("OrderUpdate listener recibió", len(recibidos["orders"]) == 1)
check("Position listener recibió", len(recibidos["positions"]) == 1)
check("AccountValue listener recibió", len(recibidos["account"]) == 1)
check("Connection listener recibió", len(recibidos["conn"]) == 1)

# Múltiples listeners
multi = []
stream2 = PAOutputStream()
stream2.on_quote(lambda e: multi.append("A"))
stream2.on_quote(lambda e: multi.append("B"))
stream2.emit_quote(q)
check("Múltiples listeners reciben", multi == ["A", "B"])

# Listener que crashea no mata PA
stream3 = PAOutputStream()
sobrevivio = []
stream3.on_quote(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
stream3.on_quote(lambda e: sobrevivio.append(e))
stream3.emit_quote(q)
check("Listener crash no mata PA", len(sobrevivio) == 1)

# Sin listeners = no error
stream4 = PAOutputStream()
try:
    stream4.emit_quote(q)
    stream4.emit_fill(f)
    check("Sin listeners = sin error", True)
except:
    check("Sin listeners = sin error", False)

# =============================================================
# 6. MODELOS — Contract, Order, Position
# =============================================================
print("\n── 6. Modelos (Contract, Order, Position) ──")

contract = Contract(symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD")
ib_contract = contract.to_ib_contract()
check("Contract → IB Contract", ib_contract.symbol == "AAPL" and ib_contract.secType == "STK")

contract_back = Contract.from_ib_contract(ib_contract)
check("IB Contract → Contract", contract_back.symbol == "AAPL")

contract_stock = Contract.stock("MSFT")
check("Contract.stock('MSFT')", contract_stock.symbol == "MSFT" and contract_stock.sec_type == "STK")

order = Order(order_id=1, symbol="AAPL", action="BUY", quantity=100, order_type="LMT", limit_price=150.0)
ib_order = order.to_ib_order()
check("Order → IB Order", ib_order.action == "BUY" and ib_order.lmtPrice == 150.0)

pos_long = Position(symbol="AAPL", quantity=100, avg_cost=150.0, account="U12345")
check("Position long", pos_long.is_long and not pos_long.is_short and not pos_long.is_flat)

pos_short = Position(symbol="TSLA", quantity=-50, avg_cost=200.0, account="U12345")
check("Position short", pos_short.is_short and not pos_short.is_long)

pos_flat = Position(symbol="MSFT", quantity=0, avg_cost=0.0, account="U12345")
check("Position flat", pos_flat.is_flat)

# Verificar que Position YA NO tiene market_value ni unrealized_pnl (PA 2.0 los quitó)
check("Position sin market_value (PA 2.0)", not hasattr(pos_long.__class__, "market_value") or 
      not callable(getattr(type(pos_long), "market_value", None)))
check("Position sin unrealized_pnl (PA 2.0)", not hasattr(pos_long.__class__, "unrealized_pnl") or
      not callable(getattr(type(pos_long), "unrealized_pnl", None)))

# =============================================================
# RESULTADO
# =============================================================
print("\n" + "=" * 60)
total = passed + failed
print(f"RESULTADO: {passed}/{total} tests pasaron", end="")
if failed == 0:
    print(" ✅ TODO FUNCIONA")
else:
    print(f" ⚠️  {failed} fallaron")
print("=" * 60)
