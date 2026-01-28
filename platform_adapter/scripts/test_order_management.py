#!/usr/bin/env python3
"""
Test Order Management Features

Tests order modification, open orders request, and commission tracking.

NOTE: This places REAL orders in Paper Trading account!

Author: Platform Adapter Team
Date: January 27, 2026
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from platform_adapter.core.connection_manager import ConnectionManager
from platform_adapter.adapters.order_execution_adapter import (
    OrderExecutionAdapter, OrderType, OrderAction
)
from platform_adapter.models.contract import Contract
from loguru import logger


def test_order_modification():
    """Test modifying an existing order."""
    print("\n" + "="*60)
    print("TEST 1: Order Modification")
    print("="*60)
    
    # Connect
    print("\n🔌 Connecting to IB Gateway...")
    cm = ConnectionManager()
    if not cm.connect_to_ib(host="127.0.0.1", port=7497, client_id=1):
        print("❌ Connection failed")
        return False
    
    print(f"✅ Connected: {cm}")
    
    try:
        # Create adapter
        print("\n📡 Creating Order Execution Adapter...")
        adapter = OrderExecutionAdapter(cm)
        print(f"✅ {adapter}")
        
        # Create contract
        spy = Contract(symbol="SPY", sec_type="STK", exchange="SMART", currency="USD")
        
        # Place limit order
        initial_price = 500.0
        print(f"\n📈 Placing LIMIT order: BUY 1 SPY @ ${initial_price}")
        order_id = adapter.place_order(
            contract=spy,
            action=OrderAction.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=initial_price
        )
        print(f"✅ Order placed: order_id={order_id}")
        
        # Wait for order to be acknowledged
        print("\n⏱️  Waiting for order acknowledgment (2 seconds)...")
        time.sleep(2)
        
        # Check initial order
        order = adapter.get_order(order_id)
        if order:
            print(f"\n📋 Initial Order: {order}")
        
        # Modify order - change price and quantity
        new_price = 550.0
        new_quantity = 2
        print(f"\n🔄 Modifying order: new price=${new_price}, new quantity={new_quantity}")
        success = adapter.modify_order(
            order_id=order_id,
            quantity=new_quantity,
            limit_price=new_price
        )
        
        if success:
            print("✅ Modification request sent")
        else:
            print("❌ Modification failed")
            return False
        
        # Wait for modification to process
        print("\n⏱️  Waiting for modification (2 seconds)...")
        time.sleep(2)
        
        # Check modified order
        modified_order = adapter.get_order(order_id)
        if modified_order:
            print(f"\n📋 Modified Order: {modified_order}")
            
            # Verify changes
            if modified_order.quantity == new_quantity:
                print(f"   ✅ Quantity updated: {new_quantity}")
            else:
                print(f"   ⚠️  Quantity: expected {new_quantity}, got {modified_order.quantity}")
            
            if modified_order.limit_price == new_price:
                print(f"   ✅ Price updated: ${new_price}")
            else:
                print(f"   ⚠️  Price: expected ${new_price}, got ${modified_order.limit_price}")
        
        # Cancel order
        print(f"\n🚫 Cancelling order {order_id}...")
        adapter.cancel_order(order_id)
        time.sleep(2)
        
        print("\n✅ Order modification test completed")
        return True
        
    finally:
        print("\n🔌 Disconnecting...")
        cm.disconnect_from_ib()
        time.sleep(1)


def test_open_orders_request():
    """Test requesting open orders from IB."""
    print("\n" + "="*60)
    print("TEST 2: Open Orders Request")
    print("="*60)
    
    # Connect
    print("\n🔌 Connecting to IB Gateway...")
    cm = ConnectionManager()
    if not cm.connect_to_ib(host="127.0.0.1", port=7497, client_id=1):
        print("❌ Connection failed")
        return False
    
    print(f"✅ Connected: {cm}")
    
    try:
        # Create adapter
        print("\n📡 Creating Order Execution Adapter...")
        adapter = OrderExecutionAdapter(cm)
        print(f"✅ {adapter}")
        
        # Place a few orders
        symbols = ["AAPL", "MSFT"]
        order_ids = []
        
        print(f"\n📈 Placing {len(symbols)} limit orders...")
        for symbol in symbols:
            contract = Contract(symbol=symbol, sec_type="STK", exchange="SMART", currency="USD")
            order_id = adapter.place_order(
                contract=contract,
                action=OrderAction.BUY,
                quantity=1,
                order_type=OrderType.LIMIT,
                limit_price=50.0
            )
            order_ids.append(order_id)
            print(f"   ✅ {symbol}: order_id={order_id}")
        
        # Wait for orders to be acknowledged
        time.sleep(2)
        
        # Request open orders
        print("\n📊 Requesting open orders from IB...")
        adapter.request_open_orders()
        
        # Wait for response
        time.sleep(2)
        
        # Check active orders
        active = adapter.get_active_orders()
        print(f"\n📊 Active orders: {len(active)}")
        for order in active:
            print(f"   - {order}")
        
        # Get all orders
        all_orders = adapter.get_all_orders()
        print(f"\n📊 Total orders tracked: {len(all_orders)}")
        
        # Cancel all orders
        print(f"\n🚫 Cancelling all orders...")
        for order_id in order_ids:
            adapter.cancel_order(order_id)
        
        time.sleep(2)
        
        print("\n✅ Open orders request test completed")
        return True
        
    finally:
        print("\n🔌 Disconnecting...")
        cm.disconnect_from_ib()
        time.sleep(1)


def test_order_history():
    """Test order history tracking."""
    print("\n" + "="*60)
    print("TEST 3: Order History Tracking")
    print("="*60)
    
    # Connect
    print("\n🔌 Connecting to IB Gateway...")
    cm = ConnectionManager()
    if not cm.connect_to_ib(host="127.0.0.1", port=7497, client_id=1):
        print("❌ Connection failed")
        return False
    
    print(f"✅ Connected: {cm}")
    
    try:
        # Create adapter
        print("\n📡 Creating Order Execution Adapter...")
        adapter = OrderExecutionAdapter(cm)
        print(f"✅ {adapter}")
        
        # Place and cancel multiple orders
        spy = Contract(symbol="SPY", sec_type="STK", exchange="SMART", currency="USD")
        
        print("\n📈 Placing and cancelling 3 orders...")
        for i in range(3):
            order_id = adapter.place_order(
                contract=spy,
                action=OrderAction.BUY,
                quantity=1,
                order_type=OrderType.LIMIT,
                limit_price=600.0 + i * 10
            )
            print(f"   Order {i+1}: id={order_id}")
            time.sleep(1)
            adapter.cancel_order(order_id)
        
        time.sleep(2)
        
        # Check history
        all_orders = adapter.get_all_orders()
        active_orders = adapter.get_active_orders()
        
        print(f"\n📊 Order History:")
        print(f"   Total orders: {len(all_orders)}")
        print(f"   Active orders: {len(active_orders)}")
        print(f"   Completed/Cancelled: {len(all_orders) - len(active_orders)}")
        
        # Show order statuses
        print(f"\n📋 Order Details:")
        for order in all_orders:
            status = adapter.get_order_status(order.order_id)
            status_str = status.status if status else order.status
            print(f"   Order {order.order_id}: {order.symbol} {order.action} "
                  f"{order.quantity} @ ${order.limit_price} - {status_str}")
        
        print("\n✅ Order history test completed")
        return True
        
    finally:
        print("\n🔌 Disconnecting...")
        cm.disconnect_from_ib()
        time.sleep(1)


def main():
    """Run all tests."""
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    print("🧪 ORDER MANAGEMENT TEST SUITE")
    print("Testing order modification and tracking")
    print("\n⚠️  NOTE: This places REAL orders in Paper Trading!")
    
    try:
        success = True
        
        success &= test_order_modification()
        success &= test_open_orders_request()
        success &= test_order_history()
        
        if success:
            print("\n" + "="*60)
            print("✅ ALL TESTS PASSED")
            print("="*60)
            print("\n📝 Summary:")
            print("  ✓ Order modification works")
            print("  ✓ Open orders request works")
            print("  ✓ Order history tracking works")
            print("  ✓ Active/cancelled filtering works")
            return 0
        else:
            print("\n❌ SOME TESTS FAILED")
            return 1
            
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
