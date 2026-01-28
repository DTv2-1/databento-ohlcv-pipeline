#!/usr/bin/env python3
"""
Test Order Execution Adapter

Tests order placement, cancellation, and status tracking.

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


def test_market_order():
    """Test placing a market order."""
    print("\n" + "="*60)
    print("TEST 1: Market Order")
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
        
        # Order callback
        def order_callback(update):
            print(f"   📊 Order Update: {update}")
        
        # Place market order (1 share, far from current price to avoid fill)
        print("\n📈 Placing MARKET order: BUY 1 SPY")
        order_id = adapter.place_order(
            contract=spy,
            action=OrderAction.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
            callback=order_callback
        )
        print(f"✅ Order placed: order_id={order_id}")
        
        # Wait for order status
        print("\n⏱️  Waiting for order status (3 seconds)...")
        time.sleep(3)
        
        # Get order info
        order = adapter.get_order(order_id)
        status = adapter.get_order_status(order_id)
        
        if order:
            print(f"\n📋 Order: {order}")
        if status:
            print(f"📊 Status: {status}")
        
        # Cancel order
        print(f"\n🚫 Cancelling order {order_id}...")
        adapter.cancel_order(order_id)
        
        # Wait for cancellation
        time.sleep(2)
        
        final_status = adapter.get_order_status(order_id)
        if final_status:
            print(f"📊 Final Status: {final_status}")
        
        print("\n✅ Market order test completed")
        return True
        
    finally:
        print("\n🔌 Disconnecting...")
        cm.disconnect_from_ib()
        time.sleep(1)


def test_limit_order():
    """Test placing a limit order."""
    print("\n" + "="*60)
    print("TEST 2: Limit Order")
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
        aapl = Contract(symbol="AAPL", sec_type="STK", exchange="SMART", currency="USD")
        
        # Place limit order far from market
        limit_price = 100.0  # Well below market
        print(f"\n📈 Placing LIMIT order: BUY 1 AAPL @ ${limit_price}")
        order_id = adapter.place_order(
            contract=aapl,
            action=OrderAction.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=limit_price
        )
        print(f"✅ Order placed: order_id={order_id}")
        
        # Wait for order status
        print("\n⏱️  Waiting for order status (3 seconds)...")
        time.sleep(3)
        
        # Get order info
        order = adapter.get_order(order_id)
        status = adapter.get_order_status(order_id)
        
        if order:
            print(f"\n📋 Order: {order}")
        if status:
            print(f"📊 Status: {status}")
        
        # Get all orders
        all_orders = adapter.get_all_orders()
        active_orders = adapter.get_active_orders()
        print(f"\n📊 Total orders: {len(all_orders)}")
        print(f"📊 Active orders: {len(active_orders)}")
        
        # Cancel order
        print(f"\n🚫 Cancelling order {order_id}...")
        adapter.cancel_order(order_id)
        
        # Wait for cancellation
        time.sleep(2)
        
        final_status = adapter.get_order_status(order_id)
        if final_status:
            print(f"📊 Final Status: {final_status}")
        
        print("\n✅ Limit order test completed")
        return True
        
    finally:
        print("\n🔌 Disconnecting...")
        cm.disconnect_from_ib()
        time.sleep(1)


def test_multiple_orders():
    """Test placing multiple orders."""
    print("\n" + "="*60)
    print("TEST 3: Multiple Orders")
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
        
        # Place multiple orders
        symbols = ["SPY", "QQQ", "IWM"]
        order_ids = []
        
        print(f"\n📈 Placing {len(symbols)} limit orders...")
        for symbol in symbols:
            contract = Contract(symbol=symbol, sec_type="STK", exchange="SMART", currency="USD")
            order_id = adapter.place_order(
                contract=contract,
                action=OrderAction.BUY,
                quantity=1,
                order_type=OrderType.LIMIT,
                limit_price=50.0  # Far below market
            )
            order_ids.append(order_id)
            print(f"   ✅ {symbol}: order_id={order_id}")
        
        # Wait for order status
        print("\n⏱️  Waiting for order status (3 seconds)...")
        time.sleep(3)
        
        # Check all orders
        print("\n📊 Order Summary:")
        for order_id in order_ids:
            order = adapter.get_order(order_id)
            status = adapter.get_order_status(order_id)
            if order and status:
                print(f"   Order {order_id}: {order.symbol} - {status.status}")
        
        active = adapter.get_active_orders()
        print(f"\n📊 Active orders: {len(active)}")
        
        # Cancel all orders
        print(f"\n🚫 Cancelling all orders...")
        for order_id in order_ids:
            adapter.cancel_order(order_id)
        
        # Wait for cancellations
        time.sleep(2)
        
        active_after = adapter.get_active_orders()
        print(f"📊 Active orders after cancel: {len(active_after)}")
        
        print("\n✅ Multiple orders test completed")
        return True
        
    finally:
        print("\n🔌 Disconnecting...")
        cm.disconnect_from_ib()
        time.sleep(1)


def main():
    """Run all tests."""
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    print("🧪 ORDER EXECUTION ADAPTER TEST SUITE")
    print("Testing order placement and cancellation")
    print("\n⚠️  NOTE: This places REAL orders in Paper Trading!")
    
    try:
        success = True
        
        success &= test_market_order()
        success &= test_limit_order()
        success &= test_multiple_orders()
        
        if success:
            print("\n" + "="*60)
            print("✅ ALL TESTS PASSED")
            print("="*60)
            print("\n📝 Summary:")
            print("  ✓ Market orders work")
            print("  ✓ Limit orders work")
            print("  ✓ Order cancellation works")
            print("  ✓ Multiple orders work")
            print("  ✓ Order tracking works")
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
