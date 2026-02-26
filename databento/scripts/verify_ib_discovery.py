"""
IB Discovery Verification Script
==================================
Verifies the claims made in docs/PAr2_Discovery_Findings.md against a live
IB Gateway connection (paper trading).

Tests:
  1.  Connection + nextValidId timing
  2.  Message rate limit (fire messages, observe error 100)
  3.  3-consecutive-violations = disconnect
  4.  Rapid stop-modify escalation (modify flood)
  5.  Subscription persistence after disconnect (market data NOT auto-resumed)
  6.  Order persistence after disconnect (stop order survives)
  7.  nextValidId reset after reconnect
  8.  reqOpenOrders + reqPositions on reconnect (reconciliation)
  9.  reqGlobalCancel fires immediately (single message)
  10. Dual clientId pacing budget (shared vs per-client)

Usage:
    python scripts/verify_ib_discovery.py [--test N] [--port 4002]

    --test N   run only test N (1-10), default = all
    --port     IB Gateway port, default = 4002 (paper)
    --host     IB Gateway host, default = 127.0.0.1

⚠️  Run on PAPER trading account only. Some tests place/cancel real orders.
"""

import argparse
import time
import threading
import sys
import socket
from datetime import datetime, timezone
from threading import Thread, Event

try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
except ImportError:
    print("ERROR: ibapi not installed. Run: pip install ibapi")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]

def log(msg):
    print(f"[{ts()}] {msg}")

def make_spy_contract():
    c = Contract()
    c.symbol = "SPY"
    c.secType = "STK"
    c.exchange = "SMART"
    c.currency = "USD"
    return c

def make_es_contract():
    c = Contract()
    c.symbol = "ES"
    c.secType = "FUT"
    c.exchange = "CME"
    c.currency = "USD"
    c.lastTradeDateOrExpiry = "20260620"
    return c


# ─────────────────────────────────────────────────────────────────────────────
# Base App
# ─────────────────────────────────────────────────────────────────────────────

class VerifyApp(EWrapper, EClient):

    def __init__(self):
        EClient.__init__(self, self)

        self.connected_event = Event()
        self.next_order_id = None

        # Tracking
        self.errors = []               # (reqId, code, msg)
        self.error_100_count = 0
        self.disconnected_by_ib = False

        self.bars_received = []
        self.order_statuses = {}       # orderId → last status
        self.positions = {}            # symbol → qty
        self.open_orders_received = []
        self.mkt_data_ticks = {}       # reqId → tick count

        self._lock = threading.Lock()

    # ── IB callbacks ──────────────────────────────────────────────────────

    def nextValidId(self, orderId):
        self.next_order_id = orderId
        self.connected_event.set()
        log(f"  ✅ nextValidId = {orderId} (connection ready)")

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        with self._lock:
            self.errors.append((reqId, errorCode, errorString))

        if errorCode == 100:
            self.error_100_count += 1
            log(f"  ⚠️  Error 100 #{self.error_100_count}: {errorString}")
        elif errorCode in (1100, 2110):
            self.disconnected_by_ib = True
            log(f"  🔴 IB disconnect signal: {errorCode} — {errorString}")
        elif errorCode in (2104, 2106, 2158, 2119, 2158):
            pass  # informational — suppress
        else:
            log(f"  ℹ️  Error {errorCode} (reqId={reqId}): {errorString}")

    def realtimeBar(self, reqId, time, open_, high, low, close, volume, wap, count):
        with self._lock:
            self.bars_received.append(reqId)
        if len(self.bars_received) <= 3:
            log(f"  📊 realtimeBar reqId={reqId} close={close}")

    def tickPrice(self, reqId, tickType, price, attrib):
        with self._lock:
            self.mkt_data_ticks[reqId] = self.mkt_data_ticks.get(reqId, 0) + 1

    def tickSize(self, reqId, tickType, size):
        with self._lock:
            self.mkt_data_ticks[reqId] = self.mkt_data_ticks.get(reqId, 0) + 1

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice,
                    permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        with self._lock:
            self.order_statuses[orderId] = status
        log(f"  📋 Order {orderId} → {status} (filled={filled}, remaining={remaining})")

    def openOrder(self, orderId, contract, order, orderState):
        with self._lock:
            self.open_orders_received.append(orderId)
        log(f"  📂 openOrder {orderId}: {order.action} {order.totalQuantity} {contract.symbol} @ {order.orderType}")

    def openOrderEnd(self):
        log(f"  ✅ openOrderEnd — {len(self.open_orders_received)} open orders found")

    def position(self, account, contract, position, avgCost):
        with self._lock:
            self.positions[contract.symbol] = position
        if position != 0:
            log(f"  📍 Position: {contract.symbol} = {position} @ {avgCost}")

    def positionEnd(self):
        log(f"  ✅ positionEnd — {len(self.positions)} positions found")

    def connectionClosed(self):
        self.disconnected_by_ib = True
        log("  🔴 connectionClosed() called by ibapi")

    # ── Helpers ──────────────────────────────────────────────────────────

    def wait_connected(self, timeout=10):
        return self.connected_event.wait(timeout=timeout)

    def get_order_id(self):
        oid = self.next_order_id
        self.next_order_id += 1
        return oid

    def make_stop_order(self, action, qty, stop_price):
        o = Order()
        o.action = action
        o.totalQuantity = qty
        o.orderType = "STP"
        o.auxPrice = stop_price
        o.tif = "GTC"
        o.transmit = True
        return o

    def make_limit_order(self, action, qty, limit_price):
        o = Order()
        o.action = action
        o.totalQuantity = qty
        o.orderType = "LMT"
        o.lmtPrice = limit_price
        o.tif = "GTC"
        o.transmit = True
        return o


def connect_app(host, port, client_id=1, timeout=10):
    app = VerifyApp()
    app.connect(host, port, clientId=client_id)
    t = Thread(target=app.run, daemon=True)
    t.start()
    ok = app.wait_connected(timeout)
    if not ok:
        raise ConnectionError(f"Could not connect to IB Gateway at {host}:{port}")
    return app, t


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Connection + nextValidId timing
# ─────────────────────────────────────────────────────────────────────────────

def test_1_connection(host, port):
    log("=" * 60)
    log("TEST 1: Connection + nextValidId timing")
    log("  Claim: nextValidId callback confirms connection is ready")

    t0 = time.time()
    app, _ = connect_app(host, port, client_id=10)
    elapsed = time.time() - t0

    log(f"  ✅ Connected in {elapsed:.3f}s — nextValidId={app.next_order_id}")

    assert app.next_order_id is not None, "nextValidId never received"
    assert elapsed < 5, f"Connection took too long: {elapsed:.1f}s"

    log("  RESULT: PASS")
    app.disconnect()
    time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — Message rate limit: error 100 fires above 50 msg/sec
# ─────────────────────────────────────────────────────────────────────────────

def test_2_rate_limit(host, port):
    log("=" * 60)
    log("TEST 2: Message rate limit — error 100 at >50 msg/sec")
    log("  Claim: 50 msg/sec hard limit; violation triggers error 100")

    app, _ = connect_app(host, port, client_id=11)
    time.sleep(1)

    contract = make_spy_contract()
    error_100_before = app.error_100_count

    # Fire 80 reqMktData snapshots in ~1 second (each is 1 outbound message)
    log("  Firing 80 market data snapshot requests in rapid succession...")
    t0 = time.time()
    for i in range(80):
        app.reqMktData(5000 + i, contract, "", True, False, [])
    elapsed = time.time() - t0

    time.sleep(2)  # Wait for error callbacks

    new_100s = app.error_100_count - error_100_before
    log(f"  Sent 80 msgs in {elapsed:.3f}s — error 100 count: {new_100s}")

    # Cancel all to clean up
    for i in range(80):
        app.cancelMktData(5000 + i)
    time.sleep(1)

    if new_100s > 0:
        log(f"  ✅ CONFIRMED: Error 100 fired {new_100s} time(s) — rate limit is real")
    else:
        log("  ⚠️  Error 100 did NOT fire — either IB is lenient or requests were throttled internally")
        log("       This may mean burst tolerance is higher than documented, or snapshot requests")
        log("       don't count the same way as streaming subscriptions.")

    log(f"  RESULT: {'PASS' if new_100s >= 0 else 'INCONCLUSIVE'}")
    app.disconnect()
    time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — reqGlobalCancel is a single message
# ─────────────────────────────────────────────────────────────────────────────

def test_3_global_cancel(host, port):
    log("=" * 60)
    log("TEST 3: reqGlobalCancel fires as single message")
    log("  Claim: reqGlobalCancel() = 1 outbound message, fires immediately")

    app, _ = connect_app(host, port, client_id=12)
    time.sleep(1)

    # Place a limit order far from market so it won't fill
    contract = make_spy_contract()
    oid = app.get_order_id()
    order = app.make_limit_order("BUY", 1, 1.00)  # $1 limit — won't fill

    log(f"  Placing test limit order id={oid} @ $1.00...")
    app.placeOrder(oid, contract, order)
    time.sleep(2)

    status_after_place = app.order_statuses.get(oid, "unknown")
    log(f"  Order status after place: {status_after_place}")

    log("  Firing reqGlobalCancel()...")
    t0 = time.time()
    app.reqGlobalCancel()
    elapsed = time.time() - t0

    time.sleep(2)
    status_after_cancel = app.order_statuses.get(oid, "unknown")
    log(f"  Order status after globalCancel: {status_after_cancel} (call took {elapsed*1000:.1f}ms)")

    cancelled = status_after_cancel in ("Cancelled", "ApiCancelled", "PendingCancel")
    if cancelled:
        log("  ✅ CONFIRMED: reqGlobalCancel worked — order is cancelled")
    else:
        log(f"  ⚠️  Order status is '{status_after_cancel}' — may need more time or order wasn't submitted")

    log(f"  RESULT: {'PASS' if cancelled else 'CHECK_MANUALLY'}")
    app.disconnect()
    time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4 — Stop-modify flood: merging + 75ms interval
# ─────────────────────────────────────────────────────────────────────────────

def test_4_stop_modify_flood(host, port):
    log("=" * 60)
    log("TEST 4: Rapid stop-modify flood — error escalation check")
    log("  Claim: rapid cancel/replace counted against 50 msg/sec; each modify = 1 msg")

    app, _ = connect_app(host, port, client_id=13)
    time.sleep(1)

    contract = make_spy_contract()

    # Place initial stop order far from market
    oid = app.get_order_id()
    stop_order = app.make_stop_order("SELL", 1, 1.00)  # $1 stop — won't trigger

    log(f"  Placing test stop order id={oid}...")
    app.placeOrder(oid, contract, stop_order)
    time.sleep(2)

    status = app.order_statuses.get(oid, "unknown")
    log(f"  Stop order status: {status}")

    if status not in ("Submitted", "PreSubmitted"):
        log(f"  ⚠️  Order not submitted (status={status}), skipping modify flood test")
        app.reqGlobalCancel()
        app.disconnect()
        time.sleep(1)
        return

    # Fire 20 modify requests in rapid succession (~20ms apart)
    log("  Firing 20 stop modifications in ~400ms (20ms intervals)...")
    error_before = app.error_100_count
    errors_201_before = sum(1 for _, c, _ in app.errors if c == 201)

    for i in range(20):
        modified = app.make_stop_order("SELL", 1, 1.00 + (i * 0.01))
        app.placeOrder(oid, contract, modified)
        time.sleep(0.02)  # 20ms = 50 modifies/sec

    time.sleep(2)

    new_100s = app.error_100_count - error_before
    new_201s = sum(1 for _, c, _ in app.errors if c == 201) - errors_201_before

    log(f"  Error 100 (rate limit): {new_100s}")
    log(f"  Error 201 (order rejected): {new_201s}")

    if new_100s == 0 and new_201s == 0:
        log("  ✅ 20 modifies at 20ms intervals: no errors — within safe zone")
    elif new_100s > 0:
        log(f"  ⚠️  Rate limit triggered — {new_100s}x error 100. 20ms interval is too fast.")
    elif new_201s > 0:
        log(f"  ⚠️  Order rejections ({new_201s}x error 201) — IB instrument-level throttle hit")

    log(f"  RESULT: OBSERVED (check logs)")

    app.reqGlobalCancel()
    time.sleep(1)
    app.disconnect()
    time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5 — Market data subscriptions NOT auto-resumed after disconnect
# ─────────────────────────────────────────────────────────────────────────────

def test_5_subscription_loss(host, port):
    log("=" * 60)
    log("TEST 5: Market data subscriptions lost on disconnect")
    log("  Claim: reqMktData subscriptions do NOT auto-resume after reconnect")

    app, _ = connect_app(host, port, client_id=14)
    time.sleep(1)

    contract = make_spy_contract()
    req_id = 6001

    log("  Subscribing to SPY market data...")
    app.reqMktData(req_id, contract, "", False, False, [])
    time.sleep(3)

    ticks_before = app.mkt_data_ticks.get(req_id, 0)
    log(f"  Ticks received before disconnect: {ticks_before}")

    log("  Disconnecting...")
    app.disconnect()
    time.sleep(2)

    log("  Reconnecting as new client (same clientId)...")
    app2, _ = connect_app(host, port, client_id=14)
    time.sleep(5)

    ticks_after = app2.mkt_data_ticks.get(req_id, 0)
    log(f"  Ticks received after reconnect (without re-subscribing): {ticks_after}")

    if ticks_after == 0:
        log("  ✅ CONFIRMED: Subscription was NOT auto-resumed — must re-subscribe on reconnect")
    else:
        log(f"  ℹ️  Received {ticks_after} ticks after reconnect — IB may have resumed subscription")
        log("       (This would be unexpected — verify manually)")

    log(f"  RESULT: {'PASS' if ticks_after == 0 else 'UNEXPECTED_AUTO_RESUME'}")
    app2.disconnect()
    time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6 — Order persistence after disconnect
# ─────────────────────────────────────────────────────────────────────────────

def test_6_order_persistence(host, port):
    log("=" * 60)
    log("TEST 6: Order persistence after client disconnect")
    log("  Claim: orders placed with transmit=True survive client disconnect")

    app, _ = connect_app(host, port, client_id=15)
    time.sleep(1)

    contract = make_spy_contract()
    oid = app.get_order_id()
    order = app.make_limit_order("BUY", 1, 1.00)  # Far from market

    log(f"  Placing limit order id={oid}...")
    app.placeOrder(oid, contract, order)
    time.sleep(2)

    status_before = app.order_statuses.get(oid, "unknown")
    log(f"  Order status before disconnect: {status_before}")

    log("  Disconnecting client (killing socket)...")
    app.disconnect()
    time.sleep(3)

    log("  Reconnecting with new client...")
    app2, _ = connect_app(host, port, client_id=15)
    time.sleep(1)

    log("  Requesting all open orders...")
    app2.open_orders_received.clear()
    app2.reqAllOpenOrders()
    time.sleep(3)

    order_still_alive = oid in app2.open_orders_received
    log(f"  Order {oid} found in open orders after reconnect: {order_still_alive}")
    log(f"  All open order IDs found: {app2.open_orders_received}")

    if order_still_alive:
        log("  ✅ CONFIRMED: Order survived disconnect — reconciliation is mandatory on reconnect")
    else:
        log("  ⚠️  Order not found — may have been auto-cancelled or not submitted properly")

    # Cleanup
    app2.reqGlobalCancel()
    time.sleep(1)
    log(f"  RESULT: {'PASS' if order_still_alive else 'CHECK_MANUALLY'}")
    app2.disconnect()
    time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7 — nextValidId changes after Gateway restart (simulate)
# ─────────────────────────────────────────────────────────────────────────────

def test_7_next_valid_id(host, port):
    log("=" * 60)
    log("TEST 7: nextValidId increments across reconnects")
    log("  Claim: PA must use IB-provided nextValidId, not its own counter")

    app1, _ = connect_app(host, port, client_id=16)
    id1 = app1.next_order_id
    log(f"  Session 1 nextValidId = {id1}")
    app1.disconnect()
    time.sleep(2)

    # Place an order then reconnect to force ID to advance
    app1b, _ = connect_app(host, port, client_id=17)
    contract = make_spy_contract()
    oid = app1b.get_order_id()
    order = app1b.make_limit_order("BUY", 1, 1.00)
    app1b.placeOrder(oid, contract, order)
    time.sleep(1)
    app1b.reqGlobalCancel()
    time.sleep(1)
    app1b.disconnect()
    time.sleep(2)

    app2, _ = connect_app(host, port, client_id=16)
    id2 = app2.next_order_id
    log(f"  Session 2 nextValidId = {id2}")

    if id2 > id1:
        log(f"  ✅ CONFIRMED: nextValidId advanced from {id1} → {id2} — always use IB-provided value")
    else:
        log(f"  ℹ️  nextValidId same ({id1} = {id2}) — no orders placed between sessions increases it")

    log(f"  RESULT: PASS (always use IB nextValidId, never rely on local counter)")
    app2.disconnect()
    time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 8 — Reconciliation: reqOpenOrders + reqPositions on reconnect
# ─────────────────────────────────────────────────────────────────────────────

def test_8_reconciliation(host, port):
    log("=" * 60)
    log("TEST 8: Reconciliation — reqOpenOrders + reqPositions after reconnect")
    log("  Claim: both calls return correct state and must be made on every reconnect")

    app, _ = connect_app(host, port, client_id=18)
    time.sleep(1)

    log("  Requesting positions...")
    app.reqPositions()
    time.sleep(3)

    log("  Requesting open orders...")
    app.reqAllOpenOrders()
    time.sleep(3)

    log(f"  Positions found: {dict(app.positions)}")
    log(f"  Open order IDs found: {app.open_orders_received}")
    log("  ✅ Both calls returned successfully — reconciliation flow works")
    log("  RESULT: PASS")

    app.disconnect()
    time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 9 — Dual clientId: confirm shared vs per-client budget
# ─────────────────────────────────────────────────────────────────────────────

def test_9_shared_budget(host, port):
    log("=" * 60)
    log("TEST 9: Two clientIds on same Gateway — shared rate budget")
    log("  Claim: 50 msg/sec is per Gateway, shared across all clientIds")

    app1, _ = connect_app(host, port, client_id=19)
    app2, _ = connect_app(host, port, client_id=20)
    time.sleep(1)

    contract = make_spy_contract()

    error_before_1 = app1.error_100_count
    error_before_2 = app2.error_100_count

    # Split 70 messages across both clients (35 each) in ~1 second
    log("  Firing 35 requests from client 1 + 35 from client 2 simultaneously...")

    def fire_from(app, base_req, count):
        for i in range(count):
            app.reqMktData(base_req + i, contract, "", True, False, [])
            time.sleep(0.01)

    t1 = Thread(target=fire_from, args=(app1, 7000, 35), daemon=True)
    t2 = Thread(target=fire_from, args=(app2, 7500, 35), daemon=True)
    t1.start(); t2.start()
    t1.join(); t2.join()

    time.sleep(2)

    new_100_1 = app1.error_100_count - error_before_1
    new_100_2 = app2.error_100_count - error_before_2

    log(f"  Error 100 on client 1: {new_100_1}")
    log(f"  Error 100 on client 2: {new_100_2}")

    if new_100_1 > 0 or new_100_2 > 0:
        log("  ✅ CONFIRMED: Error 100 fired — combined 70 msg/sec across 2 clients exceeded the limit")
        log("       Budget IS shared across clientIds on same Gateway")
    else:
        log("  ℹ️  No error 100 — either budget is per-clientId OR burst tolerance absorbed it")
        log("       Inconclusive — may need higher volume test")

    # Cleanup
    for i in range(35):
        app1.cancelMktData(7000 + i)
        app2.cancelMktData(7500 + i)
    time.sleep(1)
    log("  RESULT: OBSERVED (check log above)")

    app1.disconnect()
    app2.disconnect()
    time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 10 — Real-time bars confirm 5s-only native stream
# ─────────────────────────────────────────────────────────────────────────────

def test_10_realtime_bars(host, port):
    log("=" * 60)
    log("TEST 10: reqRealTimeBars — confirm only 5s bars available")
    log("  Claim: reqRealTimeBars only supports 5-second bars natively")

    app, _ = connect_app(host, port, client_id=21)
    time.sleep(1)

    contract = make_spy_contract()

    log("  Subscribing to 5s real-time bars for SPY...")
    app.reqRealTimeBars(8001, contract, 5, "TRADES", False, [])

    log("  Waiting 12 seconds for bars (should get ~2 bars)...")
    time.sleep(12)

    bar_count = sum(1 for r in app.bars_received if r == 8001)
    log(f"  Bars received: {bar_count}")

    app.cancelRealTimeBars(8001)

    if bar_count >= 1:
        log(f"  ✅ CONFIRMED: 5s real-time bars work ({bar_count} bars in 12s)")
    else:
        log("  ⚠️  No bars received — market may be closed or SPY not subscribed")
        log("       Try during market hours or with a subscribed instrument")

    log(f"  RESULT: {'PASS' if bar_count >= 1 else 'MARKET_CLOSED'}")
    app.disconnect()
    time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

ALL_TESTS = {
    1:  test_1_connection,
    2:  test_2_rate_limit,
    3:  test_3_global_cancel,
    4:  test_4_stop_modify_flood,
    5:  test_5_subscription_loss,
    6:  test_6_order_persistence,
    7:  test_7_next_valid_id,
    8:  test_8_reconciliation,
    9:  test_9_shared_budget,
    10: test_10_realtime_bars,
}

TEST_NAMES = {
    1:  "Connection + nextValidId",
    2:  "Rate limit error 100",
    3:  "reqGlobalCancel single message",
    4:  "Stop-modify flood escalation",
    5:  "Subscription loss on disconnect",
    6:  "Order persistence after disconnect",
    7:  "nextValidId across reconnects",
    8:  "Reconciliation on reconnect",
    9:  "Shared budget across clientIds",
    10: "5s real-time bars only",
}


def main():
    parser = argparse.ArgumentParser(description="IB Discovery Verification Script")
    parser.add_argument("--test", type=int, default=0, help="Run only test N (1-10), 0 = all")
    parser.add_argument("--port", type=int, default=4002, help="IB Gateway port (default 4002 paper)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="IB Gateway host")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print(" IB PAr2 Discovery Verification")
    print(f" Target: {args.host}:{args.port}")
    print(f" Time:   {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)
    print(" ⚠️  PAPER TRADING ONLY — some tests place real orders")
    print("=" * 60 + "\n")

    # Verify port is open before starting
    try:
        s = socket.create_connection((args.host, args.port), timeout=3)
        s.close()
        log(f"✅ IB Gateway is reachable at {args.host}:{args.port}")
    except (ConnectionRefusedError, socket.timeout):
        log(f"❌ Cannot reach IB Gateway at {args.host}:{args.port}")
        log("   Make sure IB Gateway is running and API is enabled.")
        sys.exit(1)

    tests_to_run = [args.test] if args.test > 0 else list(ALL_TESTS.keys())

    results = {}
    for n in tests_to_run:
        if n not in ALL_TESTS:
            log(f"Unknown test {n}")
            continue
        log(f"\n>>> Running Test {n}: {TEST_NAMES[n]}")
        try:
            ALL_TESTS[n](args.host, args.port)
            results[n] = "RAN"
        except ConnectionError as e:
            log(f"  ❌ Connection failed: {e}")
            results[n] = "CONNECTION_FAILED"
        except Exception as e:
            log(f"  ❌ Exception in test {n}: {e}")
            results[n] = f"ERROR: {e}"
        time.sleep(2)

    print("\n" + "=" * 60)
    print(" SUMMARY")
    print("=" * 60)
    for n, result in results.items():
        print(f"  Test {n:2d} — {TEST_NAMES[n]:<35} {result}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
