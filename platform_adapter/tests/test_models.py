"""
Unit Tests for Data Models

Tests:
- Contract model creation and validation
- Contract to/from IB API conversion
- Order model creation and validation  
- Order to/from IB API conversion
- Position model creation and validation
- Quote model creation and validation

Author: Platform Adapter Team
Created: 2026-01-27
"""

import unittest
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from platform_adapter.models.contract import Contract
from platform_adapter.models.order import Order, OrderStatus
from platform_adapter.models.position import Position

from ibapi.contract import Contract as IBContract
from ibapi.order import Order as IBOrder


class TestContractModel(unittest.TestCase):
    """Test Contract model."""
    
    def test_contract_creation(self):
        """Test creating a contract."""
        contract = Contract(
            symbol="AAPL",
            sec_type="STK",
            exchange="SMART",
            currency="USD"
        )
        
        self.assertEqual(contract.symbol, "AAPL")
        self.assertEqual(contract.sec_type, "STK")
        self.assertEqual(contract.exchange, "SMART")
        self.assertEqual(contract.currency, "USD")
    
    def test_contract_to_ib(self):
        """Test converting Contract to IB API Contract."""
        contract = Contract(
            symbol="AAPL",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
            primary_exchange="NASDAQ"
        )
        
        ib_contract = contract.to_ib_contract()
        
        self.assertIsInstance(ib_contract, IBContract)
        self.assertEqual(ib_contract.symbol, "AAPL")
        self.assertEqual(ib_contract.secType, "STK")
        self.assertEqual(ib_contract.exchange, "SMART")
        self.assertEqual(ib_contract.currency, "USD")
        self.assertEqual(ib_contract.primaryExchange, "NASDAQ")
    
    def test_contract_from_ib(self):
        """Test creating Contract from IB API Contract."""
        ib_contract = IBContract()
        ib_contract.symbol = "MSFT"
        ib_contract.secType = "STK"
        ib_contract.exchange = "SMART"
        ib_contract.currency = "USD"
        ib_contract.primaryExchange = "NASDAQ"
        
        contract = Contract.from_ib_contract(ib_contract)
        
        self.assertEqual(contract.symbol, "MSFT")
        self.assertEqual(contract.sec_type, "STK")
        self.assertEqual(contract.exchange, "SMART")
        self.assertEqual(contract.currency, "USD")
        self.assertEqual(contract.primary_exchange, "NASDAQ")
    
    def test_contract_repr(self):
        """Test Contract string representation."""
        contract = Contract(
            symbol="TSLA",
            sec_type="STK",
            exchange="SMART",
            currency="USD"
        )
        
        repr_str = repr(contract)
        self.assertIn("TSLA", repr_str)
        self.assertIn("STK", repr_str)


class TestOrderModel(unittest.TestCase):
    """Test Order model."""
    
    def test_order_creation(self):
        """Test creating an order."""
        order = Order(
            order_id=1001,
            symbol="AAPL",
            action="BUY",
            quantity=100,
            order_type="MKT",
            status=OrderStatus.SUBMITTED
        )
        
        self.assertEqual(order.order_id, 1001)
        self.assertEqual(order.symbol, "AAPL")
        self.assertEqual(order.action, "BUY")
        self.assertEqual(order.quantity, 100)
        self.assertEqual(order.order_type, "MKT")
        self.assertEqual(order.status, OrderStatus.SUBMITTED)
    
    def test_order_with_limit_price(self):
        """Test creating a limit order."""
        order = Order(
            order_id=1002,
            symbol="MSFT",
            action="SELL",
            quantity=50,
            order_type="LMT",
            limit_price=350.00,
            status=OrderStatus.SUBMITTED
        )
        
        self.assertEqual(order.limit_price, 350.00)
        self.assertEqual(order.order_type, "LMT")
    
    def test_order_with_stop_price(self):
        """Test creating a stop order."""
        order = Order(
            order_id=1003,
            symbol="TSLA",
            action="BUY",
            quantity=25,
            order_type="STP",
            stop_price=200.00,
            status=OrderStatus.SUBMITTED
        )
        
        self.assertEqual(order.stop_price, 200.00)
        self.assertEqual(order.order_type, "STP")
    
    def test_order_to_ib(self):
        """Test converting Order to IB API Order."""
        order = Order(
            order_id=1004,
            symbol="AAPL",
            action="BUY",
            quantity=100,
            order_type="LMT",
            limit_price=150.00,
            status=OrderStatus.SUBMITTED
        )
        
        ib_order = order.to_ib_order()
        
        self.assertIsInstance(ib_order, IBOrder)
        self.assertEqual(ib_order.action, "BUY")
        self.assertEqual(ib_order.totalQuantity, 100)
        self.assertEqual(ib_order.orderType, "LMT")
        self.assertEqual(ib_order.lmtPrice, 150.00)
    
    def test_order_status_enum(self):
        """Test OrderStatus enum values."""
        self.assertEqual(OrderStatus.PENDING_SUBMIT.value, "PendingSubmit")
        self.assertEqual(OrderStatus.SUBMITTED.value, "Submitted")
        self.assertEqual(OrderStatus.FILLED.value, "Filled")
        self.assertEqual(OrderStatus.CANCELLED.value, "Cancelled")
    
    def test_order_fill_tracking(self):
        """Test order fill tracking."""
        order = Order(
            order_id=1005,
            symbol="AAPL",
            action="BUY",
            quantity=100,
            order_type="MKT",
            status=OrderStatus.FILLED,
            filled=100,
            remaining=0,
            avg_fill_price=149.95
        )
        
        self.assertEqual(order.filled, 100)
        self.assertEqual(order.remaining, 0)
        self.assertEqual(order.avg_fill_price, 149.95)


class TestPositionModel(unittest.TestCase):
    """Test Position model."""
    
    def test_position_creation(self):
        """Test creating a position."""
        position = Position(
            symbol="AAPL",
            quantity=100,
            avg_cost=150.00,
            account="U23992509",
            sec_type="STK",
            exchange="SMART",
            currency="USD"
        )
        
        self.assertEqual(position.symbol, "AAPL")
        self.assertEqual(position.quantity, 100)
        self.assertEqual(position.avg_cost, 150.00)
        self.assertEqual(position.account, "U23992509")
    
    def test_position_is_long(self):
        """Test long position detection."""
        position = Position(
            symbol="AAPL",
            quantity=100,
            avg_cost=150.00,
            account="U23992509",
            sec_type="STK",
            exchange="SMART",
            currency="USD"
        )
        
        self.assertTrue(position.is_long)
        self.assertFalse(position.is_short)
        self.assertFalse(position.is_flat)
    
    def test_position_is_short(self):
        """Test short position detection."""
        position = Position(
            symbol="TSLA",
            quantity=-50,
            avg_cost=200.00,
            account="U23992509",
            sec_type="STK",
            exchange="SMART",
            currency="USD"
        )
        
        self.assertFalse(position.is_long)
        self.assertTrue(position.is_short)
        self.assertFalse(position.is_flat)
    
    def test_position_is_flat(self):
        """Test flat position detection."""
        position = Position(
            symbol="MSFT",
            quantity=0,
            avg_cost=0.00,
            account="U23992509",
            sec_type="STK",
            exchange="SMART",
            currency="USD"
        )
        
        self.assertFalse(position.is_long)
        self.assertFalse(position.is_short)
        self.assertTrue(position.is_flat)
    
    def test_position_repr(self):
        """Test Position string representation."""
        position = Position(
            symbol="AAPL",
            quantity=100,
            avg_cost=150.00,
            account="U23992509",
            sec_type="STK",
            exchange="SMART",
            currency="USD"
        )
        
        repr_str = repr(position)
        self.assertIn("AAPL", repr_str)
        self.assertIn("LONG", repr_str)
        self.assertIn("100", repr_str)


def run_tests():
    """Run all model tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestContractModel))
    suite.addTests(loader.loadTestsFromTestCase(TestOrderModel))
    suite.addTests(loader.loadTestsFromTestCase(TestPositionModel))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return success status
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
