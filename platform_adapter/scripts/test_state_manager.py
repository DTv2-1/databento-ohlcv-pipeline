"""
Test script for State Manager

Tests:
1. Position management (add, update, query, remove)
2. Order management (add, update, query, remove, active filtering)
3. Account value management (add, update, query)
4. Thread safety (concurrent updates)
5. Reconciliation (positions and orders)
6. State summary and clearing

Author: Platform Adapter Team
Created: 2026-01-27
"""

import sys
import time
import threading
from pathlib import Path
from datetime import datetime

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from platform_adapter.core.state_manager import StateManager
from platform_adapter.models.position import Position
from platform_adapter.models.order import Order, OrderStatus
from platform_adapter.adapters.order_execution_adapter import OrderType, OrderAction
from platform_adapter.adapters.account_manager import AccountValue


def print_test_header(test_name: str):
    """Print test header."""
    print(f"\n{'='*70}")
    print(f"TEST: {test_name}")
    print(f"{'='*70}")


def print_result(passed: bool, message: str = ""):
    """Print test result."""
    status = "✅ PASSED" if passed else "❌ FAILED"
    print(f"\n{status}")
    if message:
        print(f"Details: {message}")


def test_position_management():
    """Test position management functionality."""
    print_test_header("Position Management")
    
    state = StateManager()
    
    # Test 1: Add single position
    pos1 = Position(
        symbol="AAPL",
        quantity=100,
        avg_cost=150.50,
        account="U23992509",
        sec_type="STK",
        exchange="SMART",
        currency="USD"
    )
    state.update_position(pos1)
    
    assert state.get_positions_count() == 1, "Should have 1 position"
    retrieved_pos = state.get_position("AAPL")
    assert retrieved_pos is not None, "Should retrieve AAPL position"
    assert retrieved_pos.quantity == 100, "Quantity should match"
    print("✓ Single position add/retrieve works")
    
    # Test 2: Batch update positions
    pos2 = Position("TSLA", 50, 200.00, "U23992509", "STK", "SMART", "USD")
    pos3 = Position("MSFT", 75, 300.00, "U23992509", "STK", "SMART", "USD")
    state.update_positions([pos2, pos3])
    
    assert state.get_positions_count() == 3, "Should have 3 positions"
    all_positions = state.get_all_positions()
    assert len(all_positions) == 3, "get_all_positions should return 3"
    print("✓ Batch position update works")
    
    # Test 3: Update existing position
    pos1_updated = Position("AAPL", 150, 152.00, "U23992509", "STK", "SMART", "USD")
    state.update_position(pos1_updated)
    
    assert state.get_positions_count() == 3, "Should still have 3 positions"
    updated_pos = state.get_position("AAPL")
    assert updated_pos.quantity == 150, "Quantity should be updated"
    assert updated_pos.avg_cost == 152.00, "Avg cost should be updated"
    print("✓ Position update works")
    
    # Test 4: Remove position
    state.remove_position("TSLA")
    assert state.get_positions_count() == 2, "Should have 2 positions after removal"
    assert state.get_position("TSLA") is None, "TSLA should be removed"
    print("✓ Position removal works")
    
    # Test 5: Clear all positions
    state.clear_positions()
    assert state.get_positions_count() == 0, "Should have 0 positions after clear"
    print("✓ Clear positions works")
    
    print_result(True, "All position management tests passed")
    return True


def test_order_management():
    """Test order management functionality."""
    print_test_header("Order Management")
    
    state = StateManager()
    
    # Test 1: Add single order
    order1 = Order(
        order_id=1001,
        symbol="AAPL",
        action=OrderAction.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=150.00,
        status=OrderStatus.SUBMITTED
    )
    state.update_order(order1)
    
    assert state.get_orders_count() == 1, "Should have 1 order"
    retrieved_order = state.get_order(1001)
    assert retrieved_order is not None, "Should retrieve order 1001"
    assert retrieved_order.symbol == "AAPL", "Symbol should match"
    print("✓ Single order add/retrieve works")
    
    # Test 2: Batch update orders
    order2 = Order(1002, "TSLA", OrderAction.BUY, 50, OrderType.MARKET, status=OrderStatus.PENDING_SUBMIT)
    order3 = Order(1003, "MSFT", OrderAction.SELL, 75, OrderType.LIMIT, limit_price=310.00, status=OrderStatus.SUBMITTED)
    state.update_orders([order2, order3])
    
    assert state.get_orders_count() == 3, "Should have 3 orders"
    print("✓ Batch order update works")
    
    # Test 3: Get active orders
    active_orders = state.get_active_orders()
    assert len(active_orders) == 3, "Should have 3 active orders"
    print("✓ Active orders query works")
    
    # Test 4: Update order status to filled
    order1_filled = Order(
        1001, "AAPL", OrderAction.BUY, 100, OrderType.LIMIT,
        limit_price=150.00, status=OrderStatus.FILLED,
        filled=100, avg_fill_price=149.95
    )
    state.update_order(order1_filled)
    
    active_orders = state.get_active_orders()
    assert len(active_orders) == 2, "Should have 2 active orders after one filled"
    filled_order = state.get_order(1001)
    assert filled_order.status == OrderStatus.FILLED, "Order should be filled"
    print("✓ Order status update works")
    
    # Test 5: Get orders by symbol
    aapl_orders = state.get_orders_by_symbol("AAPL")
    assert len(aapl_orders) == 1, "Should have 1 AAPL order"
    assert aapl_orders[0].order_id == 1001, "Should be order 1001"
    print("✓ Orders by symbol query works")
    
    # Test 6: Remove order
    state.remove_order(1002)
    assert state.get_orders_count() == 2, "Should have 2 orders after removal"
    print("✓ Order removal works")
    
    # Test 7: Clear all orders
    state.clear_orders()
    assert state.get_orders_count() == 0, "Should have 0 orders after clear"
    print("✓ Clear orders works")
    
    print_result(True, "All order management tests passed")
    return True


def test_account_value_management():
    """Test account value management functionality."""
    print_test_header("Account Value Management")
    
    state = StateManager()
    
    # Test 1: Add single account value
    av1 = AccountValue(
        key="NetLiquidation",
        value="2000.00",
        currency="USD",
        account="U23992509"
    )
    state.update_account_value(av1)
    
    assert len(state.get_all_account_values()) == 1, "Should have 1 account value"
    retrieved = state.get_account_value("NetLiquidation")
    assert retrieved is not None, "Should retrieve NetLiquidation"
    assert retrieved.value == "2000.00", "Value should match"
    print("✓ Single account value add/retrieve works")
    
    # Test 2: Batch update account values
    av2 = AccountValue("BuyingPower", "8000.00", "USD", "U23992509")
    av3 = AccountValue("TotalCashValue", "2000.00", "USD", "U23992509")
    state.update_account_values([av2, av3])
    
    assert len(state.get_all_account_values()) == 3, "Should have 3 account values"
    print("✓ Batch account value update works")
    
    # Test 3: Get account values as dict
    values_dict = state.get_account_values_dict()
    assert "NetLiquidation" in values_dict, "Dict should contain NetLiquidation"
    assert values_dict["BuyingPower"] == "8000.00", "BuyingPower should be correct"
    print("✓ Account values dict works")
    
    # Test 4: Update existing account value
    av1_updated = AccountValue("NetLiquidation", "2100.00", "USD", "U23992509")
    state.update_account_value(av1_updated)
    
    updated = state.get_account_value("NetLiquidation")
    assert updated.value == "2100.00", "Value should be updated"
    print("✓ Account value update works")
    
    # Test 5: Clear all account values
    state.clear_account_values()
    assert len(state.get_all_account_values()) == 0, "Should have 0 account values"
    print("✓ Clear account values works")
    
    print_result(True, "All account value management tests passed")
    return True


def test_thread_safety():
    """Test thread safety of state manager."""
    print_test_header("Thread Safety")
    
    state = StateManager()
    errors = []
    
    def add_positions(thread_id: int):
        """Add positions in a thread."""
        try:
            for i in range(10):
                pos = Position(
                    symbol=f"SYM{thread_id}_{i}",
                    quantity=100 + i,
                    avg_cost=100.0 + i,
                    account="U23992509",
                    sec_type="STK",
                    exchange="SMART",
                    currency="USD"
                )
                state.update_position(pos)
                time.sleep(0.001)  # Small delay
        except Exception as e:
            errors.append(f"Thread {thread_id}: {e}")
    
    # Create 5 threads
    threads = []
    for i in range(5):
        t = threading.Thread(target=add_positions, args=(i,))
        threads.append(t)
        t.start()
    
    # Wait for all threads
    for t in threads:
        t.join()
    
    # Check results
    if errors:
        print_result(False, f"Errors occurred: {errors}")
        return False
    
    assert state.get_positions_count() == 50, f"Should have 50 positions, got {state.get_positions_count()}"
    print(f"✓ Successfully added 50 positions from 5 threads concurrently")
    
    print_result(True, "Thread safety test passed")
    return True


def test_reconciliation():
    """Test reconciliation functionality."""
    print_test_header("Reconciliation")
    
    state = StateManager()
    
    # Setup initial state
    pos1 = Position("AAPL", 100, 150.00, "U23992509", "STK", "SMART", "USD")
    pos2 = Position("TSLA", 50, 200.00, "U23992509", "STK", "SMART", "USD")
    pos3 = Position("MSFT", 75, 300.00, "U23992509", "STK", "SMART", "USD")
    state.update_positions([pos1, pos2, pos3])
    
    # Test 1: Position reconciliation
    # Authoritative source has: AAPL (updated), TSLA (unchanged), GOOGL (new), MSFT (removed)
    auth_positions = [
        Position("AAPL", 150, 155.00, "U23992509", "STK", "SMART", "USD"),  # Updated
        Position("TSLA", 50, 200.00, "U23992509", "STK", "SMART", "USD"),   # Unchanged
        Position("GOOGL", 25, 2500.00, "U23992509", "STK", "SMART", "USD"), # Added
    ]
    
    result = state.reconcile_positions(auth_positions)
    
    assert len(result['added']) == 1, "Should have 1 added"
    assert "GOOGL" in result['added'], "GOOGL should be added"
    
    assert len(result['updated']) == 1, "Should have 1 updated"
    assert "AAPL" in result['updated'], "AAPL should be updated"
    
    assert len(result['removed']) == 1, "Should have 1 removed"
    assert "MSFT" in result['removed'], "MSFT should be removed"
    
    assert len(result['unchanged']) == 1, "Should have 1 unchanged"
    assert "TSLA" in result['unchanged'], "TSLA should be unchanged"
    
    assert state.get_positions_count() == 3, "Should have 3 positions after reconciliation"
    print("✓ Position reconciliation works")
    
    # Test 2: Order reconciliation
    state.clear_orders()
    
    order1 = Order(1001, "AAPL", OrderAction.BUY, 100, OrderType.LIMIT, status=OrderStatus.SUBMITTED)
    order2 = Order(1002, "TSLA", OrderAction.BUY, 50, OrderType.MARKET, status=OrderStatus.SUBMITTED)
    state.update_orders([order1, order2])
    
    # Authoritative source has: 1001 (filled), 1003 (new), 1002 (removed)
    auth_orders = [
        Order(1001, "AAPL", OrderAction.BUY, 100, OrderType.LIMIT, status=OrderStatus.FILLED),  # Updated
        Order(1003, "MSFT", OrderAction.SELL, 75, OrderType.LIMIT, status=OrderStatus.SUBMITTED),  # Added
    ]
    
    result = state.reconcile_orders(auth_orders)
    
    assert len(result['added']) == 1, "Should have 1 added"
    assert 1003 in result['added'], "Order 1003 should be added"
    
    assert len(result['updated']) == 1, "Should have 1 updated"
    assert 1001 in result['updated'], "Order 1001 should be updated"
    
    assert len(result['removed']) == 1, "Should have 1 removed"
    assert 1002 in result['removed'], "Order 1002 should be removed"
    
    assert state.get_orders_count() == 2, "Should have 2 orders after reconciliation"
    print("✓ Order reconciliation works")
    
    print_result(True, "All reconciliation tests passed")
    return True


def test_state_summary():
    """Test state summary and metadata."""
    print_test_header("State Summary and Metadata")
    
    state = StateManager()
    
    # Test 1: Empty state summary
    summary = state.get_state_summary()
    assert summary['positions_count'] == 0, "Should have 0 positions"
    assert summary['orders_count'] == 0, "Should have 0 orders"
    assert summary['account_values_count'] == 0, "Should have 0 account values"
    assert summary['last_update'] is None, "Should have no last update"
    print("✓ Empty state summary works")
    
    # Test 2: Add data and check summary
    pos1 = Position("AAPL", 100, 150.00, "U23992509", "STK", "SMART", "USD")
    state.update_position(pos1)
    
    order1 = Order(1001, "AAPL", OrderAction.BUY, 100, OrderType.LIMIT, status=OrderStatus.SUBMITTED)
    order2 = Order(1002, "TSLA", OrderAction.BUY, 50, OrderType.MARKET, status=OrderStatus.FILLED)
    state.update_orders([order1, order2])
    
    av1 = AccountValue("NetLiquidation", "2000.00", "USD", "U23992509")
    state.update_account_value(av1)
    
    summary = state.get_state_summary()
    assert summary['positions_count'] == 1, "Should have 1 position"
    assert summary['orders_count'] == 2, "Should have 2 orders"
    assert summary['active_orders_count'] == 1, "Should have 1 active order"
    assert summary['account_values_count'] == 1, "Should have 1 account value"
    assert summary['last_update'] is not None, "Should have last update"
    print("✓ Populated state summary works")
    
    # Test 3: Last update timestamp
    last_update = state.get_last_update()
    assert isinstance(last_update, datetime), "Last update should be datetime"
    print(f"✓ Last update: {last_update}")
    
    # Test 4: String representation
    state_str = str(state)
    assert "StateManager" in state_str, "String should contain StateManager"
    assert "positions=1" in state_str, "String should show position count"
    print(f"✓ String representation: {state_str}")
    
    # Test 5: Clear all state
    state.clear_all()
    summary = state.get_state_summary()
    assert summary['positions_count'] == 0, "Should have 0 positions after clear"
    assert summary['orders_count'] == 0, "Should have 0 orders after clear"
    assert summary['account_values_count'] == 0, "Should have 0 account values after clear"
    print("✓ Clear all state works")
    
    print_result(True, "All state summary tests passed")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("STATE MANAGER TEST SUITE")
    print("="*70)
    
    tests = [
        ("Position Management", test_position_management),
        ("Order Management", test_order_management),
        ("Account Value Management", test_account_value_management),
        ("Thread Safety", test_thread_safety),
        ("Reconciliation", test_reconciliation),
        ("State Summary", test_state_summary),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ FAILED: {test_name}")
            print(f"Exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Total Tests: {len(tests)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success Rate: {passed/len(tests)*100:.1f}%")
    print("="*70)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
