"""
Unit Tests for PA 2.0 MIC Interface Contracts

Tests:
- Output event creation and immutability
- Input command creation and validation
- PAOutputStream callback registration and emission
- PAInputStream protocol compliance

Author: Platform Adapter Team
Created: 2026-02-12 (PA 2.0)
"""

import unittest
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from platform_adapter.interfaces.pa_outputs import (
    QuoteEvent,
    BarEvent,
    OrderUpdateEvent,
    FillEvent,
    PositionEvent,
    AccountValueEvent,
    ConnectionEvent,
    ConnectionStatus,
    PAOutputStream,
)
from platform_adapter.interfaces.pa_inputs import (
    PlaceOrderCommand,
    CancelOrderCommand,
    ModifyOrderCommand,
    FlattenCommand,
    SubscribeMarketDataCommand,
    UnsubscribeMarketDataCommand,
    HistoricalDataCommand,
)


# ============================================================================
# OUTPUT EVENT TESTS
# ============================================================================

class TestQuoteEvent(unittest.TestCase):
    """Test QuoteEvent output contract."""

    def test_creation_required_fields(self):
        q = QuoteEvent(symbol="AAPL", timestamp=datetime.now())
        self.assertEqual(q.symbol, "AAPL")
        self.assertIsNotNone(q.timestamp)
        self.assertIsNone(q.bid)

    def test_creation_all_fields(self):
        ts = datetime(2026, 1, 15, 10, 30, 0)
        q = QuoteEvent(
            symbol="AAPL", timestamp=ts,
            bid=150.0, ask=150.05, bid_size=100, ask_size=200,
            last=150.02, last_size=50, volume=1000000,
        )
        self.assertEqual(q.bid, 150.0)
        self.assertEqual(q.ask, 150.05)
        self.assertEqual(q.volume, 1000000)

    def test_immutability(self):
        q = QuoteEvent(symbol="AAPL", timestamp=datetime.now())
        with self.assertRaises(AttributeError):
            q.symbol = "MSFT"


class TestBarEvent(unittest.TestCase):
    """Test BarEvent output contract."""

    def test_creation(self):
        b = BarEvent(
            symbol="SPY", timestamp=datetime.now(),
            open=450.0, high=451.0, low=449.5, close=450.5, volume=10000,
        )
        self.assertEqual(b.symbol, "SPY")
        self.assertEqual(b.close, 450.5)
        self.assertEqual(b.count, 0)  # default
        self.assertEqual(b.wap, 0.0)  # default

    def test_immutability(self):
        b = BarEvent(
            symbol="SPY", timestamp=datetime.now(),
            open=1, high=2, low=0.5, close=1.5, volume=100,
        )
        with self.assertRaises(AttributeError):
            b.close = 999.0


class TestOrderUpdateEvent(unittest.TestCase):
    """Test OrderUpdateEvent output contract."""

    def test_creation(self):
        o = OrderUpdateEvent(
            order_id=1001, symbol="AAPL", status="Submitted",
            action="BUY", quantity=100, order_type="MKT",
            filled=0, remaining=100, avg_fill_price=0.0,
            timestamp=datetime.now(),
        )
        self.assertEqual(o.order_id, 1001)
        self.assertEqual(o.status, "Submitted")
        self.assertIsNone(o.limit_price)


class TestFillEvent(unittest.TestCase):
    """Test FillEvent output contract."""

    def test_creation(self):
        f = FillEvent(
            order_id=1001, exec_id="EX001", symbol="AAPL",
            side="BOT", shares=50, price=150.25,
            timestamp=datetime.now(),
        )
        self.assertEqual(f.shares, 50)
        self.assertEqual(f.price, 150.25)
        self.assertEqual(f.commission, 0.0)  # default


class TestPositionEvent(unittest.TestCase):
    """Test PositionEvent output contract."""

    def test_creation(self):
        p = PositionEvent(
            symbol="AAPL", quantity=100, avg_cost=150.0, account="U12345",
        )
        self.assertEqual(p.symbol, "AAPL")
        self.assertEqual(p.sec_type, "STK")  # default

    def test_immutability(self):
        p = PositionEvent(
            symbol="AAPL", quantity=100, avg_cost=150.0, account="U12345",
        )
        with self.assertRaises(AttributeError):
            p.quantity = 200


class TestAccountValueEvent(unittest.TestCase):
    """Test AccountValueEvent output contract."""

    def test_creation(self):
        a = AccountValueEvent(
            key="NetLiquidation", value="100000.00",
            currency="USD", account="U12345",
        )
        self.assertEqual(a.key, "NetLiquidation")
        self.assertEqual(a.value, "100000.00")


class TestConnectionEvent(unittest.TestCase):
    """Test ConnectionEvent output contract."""

    def test_creation(self):
        c = ConnectionEvent(status=ConnectionStatus.CONNECTED, message="OK")
        self.assertEqual(c.status, ConnectionStatus.CONNECTED)
        self.assertEqual(c.message, "OK")

    def test_status_enum(self):
        self.assertEqual(ConnectionStatus.CONNECTED.value, "connected")
        self.assertEqual(ConnectionStatus.DISCONNECTED.value, "disconnected")
        self.assertEqual(ConnectionStatus.RECONNECTING.value, "reconnecting")
        self.assertEqual(ConnectionStatus.ERROR.value, "error")


# ============================================================================
# INPUT COMMAND TESTS
# ============================================================================

class TestPlaceOrderCommand(unittest.TestCase):
    """Test PlaceOrderCommand input contract."""

    def test_market_order(self):
        cmd = PlaceOrderCommand(symbol="AAPL", action="BUY", quantity=100)
        self.assertEqual(cmd.symbol, "AAPL")
        self.assertEqual(cmd.order_type, "MKT")
        self.assertIsNone(cmd.limit_price)

    def test_limit_order(self):
        cmd = PlaceOrderCommand(
            symbol="AAPL", action="SELL", quantity=50,
            order_type="LMT", limit_price=155.0,
        )
        self.assertEqual(cmd.limit_price, 155.0)

    def test_stop_order(self):
        cmd = PlaceOrderCommand(
            symbol="AAPL", action="BUY", quantity=25,
            order_type="STP", stop_price=145.0,
        )
        self.assertEqual(cmd.stop_price, 145.0)

    def test_invalid_action(self):
        with self.assertRaises(ValueError):
            PlaceOrderCommand(symbol="AAPL", action="HOLD", quantity=100)

    def test_invalid_quantity_zero(self):
        with self.assertRaises(ValueError):
            PlaceOrderCommand(symbol="AAPL", action="BUY", quantity=0)

    def test_invalid_quantity_negative(self):
        with self.assertRaises(ValueError):
            PlaceOrderCommand(symbol="AAPL", action="BUY", quantity=-10)

    def test_limit_without_price(self):
        with self.assertRaises(ValueError):
            PlaceOrderCommand(
                symbol="AAPL", action="BUY", quantity=100, order_type="LMT",
            )

    def test_stop_without_price(self):
        with self.assertRaises(ValueError):
            PlaceOrderCommand(
                symbol="AAPL", action="BUY", quantity=100, order_type="STP",
            )

    def test_stop_limit_requires_both_prices(self):
        with self.assertRaises(ValueError):
            PlaceOrderCommand(
                symbol="AAPL", action="BUY", quantity=100,
                order_type="STP LMT", limit_price=150.0,
            )

    def test_immutability(self):
        cmd = PlaceOrderCommand(symbol="AAPL", action="BUY", quantity=100)
        with self.assertRaises(AttributeError):
            cmd.quantity = 200

    def test_defaults(self):
        cmd = PlaceOrderCommand(symbol="AAPL", action="BUY", quantity=100)
        self.assertEqual(cmd.sec_type, "STK")
        self.assertEqual(cmd.exchange, "SMART")
        self.assertEqual(cmd.currency, "USD")
        self.assertEqual(cmd.tif, "DAY")
        self.assertFalse(cmd.outside_rth)


class TestCancelOrderCommand(unittest.TestCase):
    """Test CancelOrderCommand input contract."""

    def test_creation(self):
        cmd = CancelOrderCommand(order_id=1001)
        self.assertEqual(cmd.order_id, 1001)


class TestModifyOrderCommand(unittest.TestCase):
    """Test ModifyOrderCommand input contract."""

    def test_modify_quantity(self):
        cmd = ModifyOrderCommand(order_id=1001, quantity=200)
        self.assertEqual(cmd.quantity, 200)

    def test_modify_limit_price(self):
        cmd = ModifyOrderCommand(order_id=1001, limit_price=155.0)
        self.assertEqual(cmd.limit_price, 155.0)

    def test_no_changes_raises(self):
        with self.assertRaises(ValueError):
            ModifyOrderCommand(order_id=1001)

    def test_invalid_quantity(self):
        with self.assertRaises(ValueError):
            ModifyOrderCommand(order_id=1001, quantity=0)


class TestFlattenCommand(unittest.TestCase):
    """Test FlattenCommand input contract."""

    def test_creation(self):
        cmd = FlattenCommand(symbol="AAPL")
        self.assertEqual(cmd.symbol, "AAPL")
        self.assertEqual(cmd.sec_type, "STK")


class TestSubscribeMarketDataCommand(unittest.TestCase):
    """Test SubscribeMarketDataCommand input contract."""

    def test_creation(self):
        cmd = SubscribeMarketDataCommand(symbol="AAPL")
        self.assertEqual(cmd.symbol, "AAPL")
        self.assertFalse(cmd.snapshot)

    def test_snapshot_mode(self):
        cmd = SubscribeMarketDataCommand(symbol="AAPL", snapshot=True)
        self.assertTrue(cmd.snapshot)


class TestHistoricalDataCommand(unittest.TestCase):
    """Test HistoricalDataCommand input contract."""

    def test_defaults(self):
        cmd = HistoricalDataCommand(symbol="AAPL")
        self.assertEqual(cmd.duration, "1 D")
        self.assertEqual(cmd.bar_size, "1 min")
        self.assertEqual(cmd.what_to_show, "TRADES")
        self.assertTrue(cmd.use_rth)


# ============================================================================
# OUTPUT STREAM TESTS
# ============================================================================

class TestPAOutputStream(unittest.TestCase):
    """Test PAOutputStream callback registry."""

    def setUp(self):
        self.stream = PAOutputStream()
        self.received = []

    def test_quote_listener(self):
        self.stream.on_quote(lambda q: self.received.append(q))
        event = QuoteEvent(symbol="AAPL", timestamp=datetime.now(), bid=150.0)
        self.stream.emit_quote(event)
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].symbol, "AAPL")

    def test_bar_listener(self):
        self.stream.on_bar(lambda b: self.received.append(b))
        event = BarEvent(
            symbol="SPY", timestamp=datetime.now(),
            open=1, high=2, low=0.5, close=1.5, volume=100,
        )
        self.stream.emit_bar(event)
        self.assertEqual(len(self.received), 1)

    def test_fill_listener(self):
        self.stream.on_fill(lambda f: self.received.append(f))
        event = FillEvent(
            order_id=1, exec_id="EX1", symbol="AAPL",
            side="BOT", shares=100, price=150.0, timestamp=datetime.now(),
        )
        self.stream.emit_fill(event)
        self.assertEqual(len(self.received), 1)

    def test_position_listener(self):
        self.stream.on_position(lambda p: self.received.append(p))
        event = PositionEvent(
            symbol="AAPL", quantity=100, avg_cost=150.0, account="U12345",
        )
        self.stream.emit_position(event)
        self.assertEqual(len(self.received), 1)

    def test_connection_listener(self):
        self.stream.on_connection(lambda c: self.received.append(c))
        event = ConnectionEvent(status=ConnectionStatus.CONNECTED)
        self.stream.emit_connection(event)
        self.assertEqual(len(self.received), 1)

    def test_multiple_listeners(self):
        results_a = []
        results_b = []
        self.stream.on_quote(lambda q: results_a.append(q))
        self.stream.on_quote(lambda q: results_b.append(q))
        event = QuoteEvent(symbol="AAPL", timestamp=datetime.now())
        self.stream.emit_quote(event)
        self.assertEqual(len(results_a), 1)
        self.assertEqual(len(results_b), 1)

    def test_listener_error_does_not_crash(self):
        """PA never crashes for downstream listener errors."""
        def bad_listener(q):
            raise RuntimeError("downstream crash")

        self.stream.on_quote(bad_listener)
        self.stream.on_quote(lambda q: self.received.append(q))

        event = QuoteEvent(symbol="AAPL", timestamp=datetime.now())
        # Should NOT raise, second listener should still fire
        self.stream.emit_quote(event)
        self.assertEqual(len(self.received), 1)

    def test_no_listeners_no_error(self):
        """Emitting with no listeners should be a no-op."""
        event = QuoteEvent(symbol="AAPL", timestamp=datetime.now())
        self.stream.emit_quote(event)  # Should not raise


# ============================================================================
# Runner
# ============================================================================

def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestQuoteEvent))
    suite.addTests(loader.loadTestsFromTestCase(TestBarEvent))
    suite.addTests(loader.loadTestsFromTestCase(TestOrderUpdateEvent))
    suite.addTests(loader.loadTestsFromTestCase(TestFillEvent))
    suite.addTests(loader.loadTestsFromTestCase(TestPositionEvent))
    suite.addTests(loader.loadTestsFromTestCase(TestAccountValueEvent))
    suite.addTests(loader.loadTestsFromTestCase(TestConnectionEvent))
    suite.addTests(loader.loadTestsFromTestCase(TestPlaceOrderCommand))
    suite.addTests(loader.loadTestsFromTestCase(TestCancelOrderCommand))
    suite.addTests(loader.loadTestsFromTestCase(TestModifyOrderCommand))
    suite.addTests(loader.loadTestsFromTestCase(TestFlattenCommand))
    suite.addTests(loader.loadTestsFromTestCase(TestSubscribeMarketDataCommand))
    suite.addTests(loader.loadTestsFromTestCase(TestHistoricalDataCommand))
    suite.addTests(loader.loadTestsFromTestCase(TestPAOutputStream))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
