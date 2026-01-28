"""
Interactive Live Test for Platform Adapter

Tests with live market (market hours):
1. Real-time market data streaming
2. Order placement (paper trading)
3. Order modification
4. Order cancellation
5. Position tracking
6. Account updates
7. State reconciliation

Run during market hours for full testing.

Author: Platform Adapter Team
Created: 2026-01-27
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from main import PlatformAdapter
from loguru import logger


def print_section(title: str):
    """Print section header."""
    print(f"\n{'='*70}")
    print(f"{title}")
    print(f"{'='*70}")


def test_live_market_data(pa: PlatformAdapter):
    """Test live market data streaming."""
    print_section("TEST: Live Market Data Streaming")
    
    symbols = ["AAPL", "MSFT", "TSLA"]
    quotes_received = {sym: [] for sym in symbols}
    
    def make_callback(symbol):
        def on_quote(sym, quote):
            quotes_received[symbol].append(quote)
            if len(quotes_received[symbol]) <= 3:
                bid = f"{quote.bid:.2f}" if quote.bid else "None"
                ask = f"{quote.ask:.2f}" if quote.ask else "None"
                last = f"{quote.last:.2f}" if quote.last else "None"
                logger.info(f"  {sym}: Bid={bid} Ask={ask} Last={last}")
        return on_quote
    
    # Subscribe to multiple symbols
    for symbol in symbols:
        success = pa.subscribe_market_data(symbol, make_callback(symbol))
        logger.info(f"Subscribed to {symbol}: {success}")
    
    logger.info("Streaming for 10 seconds...")
    time.sleep(10)
    
    # Report results
    for symbol in symbols:
        count = len(quotes_received[symbol])
        logger.info(f"{symbol}: {count} quotes received")
    
    logger.info("✅ Market data streaming test complete")
    return quotes_received


def test_order_lifecycle(pa: PlatformAdapter):
    """Test complete order lifecycle: place, modify, cancel."""
    print_section("TEST: Order Lifecycle (Place -> Modify -> Cancel)")
    
    # Step 1: Place limit order
    symbol = "AAPL"
    logger.info(f"\n1. Placing limit order: BUY 1 {symbol} @ $150.00")
    order_id = pa.place_limit_order(symbol, "BUY", 1, 150.00)
    
    if not order_id:
        logger.error("Failed to place order")
        return False
    
    logger.info(f"✅ Order placed: ID={order_id}")
    time.sleep(2)
    
    # Check order status
    status = pa.get_order_status(order_id)
    logger.info(f"Order status: {status}")
    
    # Step 2: Modify order
    logger.info(f"\n2. Modifying order {order_id}: Change price to $145.00")
    from src.platform_adapter.adapters.order_execution_adapter import OrderAction, OrderType
    
    success = pa.orders.modify_order(order_id, limit_price=145.00)
    logger.info(f"Modification {'successful' if success else 'failed'}")
    time.sleep(2)
    
    # Check updated status
    status = pa.get_order_status(order_id)
    logger.info(f"Updated order status: {status}")
    
    # Step 3: Cancel order
    logger.info(f"\n3. Cancelling order {order_id}")
    success = pa.cancel_order(order_id)
    logger.info(f"Cancellation {'successful' if success else 'failed'}")
    time.sleep(2)
    
    # Final status
    status = pa.get_order_status(order_id)
    logger.info(f"Final order status: {status}")
    
    logger.info("✅ Order lifecycle test complete")
    return True


def test_market_order(pa: PlatformAdapter):
    """Test market order execution."""
    print_section("TEST: Market Order Execution")
    
    symbol = "AAPL"
    quantity = 1
    
    logger.info(f"Placing market order: BUY {quantity} {symbol}")
    order_id = pa.place_market_order(symbol, "BUY", quantity)
    
    if not order_id:
        logger.error("Failed to place market order")
        return False
    
    logger.info(f"✅ Market order placed: ID={order_id}")
    
    # Wait for fill
    logger.info("Waiting for fill...")
    time.sleep(3)
    
    # Check if filled
    status = pa.get_order_status(order_id)
    logger.info(f"Order status: {status}")
    
    # Check position
    time.sleep(1)
    position = pa.get_position(symbol)
    if position:
        logger.info(f"Position: {position.symbol} {position.quantity} @ {position.avg_cost:.2f}")
    else:
        logger.info("No position yet (still processing)")
    
    # Close position with opposite market order
    logger.info(f"\nClosing position: SELL {quantity} {symbol}")
    close_order_id = pa.place_market_order(symbol, "SELL", quantity)
    logger.info(f"✅ Close order placed: ID={close_order_id}")
    
    time.sleep(3)
    
    # Final position check
    position = pa.get_position(symbol)
    if position:
        logger.info(f"Final position: {position.symbol} {position.quantity} @ {position.avg_cost:.2f}")
    else:
        logger.info("Position closed (flat)")
    
    logger.info("✅ Market order test complete")
    return True


def test_account_monitoring(pa: PlatformAdapter):
    """Test real-time account monitoring."""
    print_section("TEST: Real-time Account Monitoring")
    
    # Subscribe to account updates
    pa.subscribe_account_updates()
    logger.info("Subscribed to account updates")
    
    # Initial account summary
    logger.info("\nInitial Account Summary:")
    account = pa.get_account_summary()
    for key in ['NetLiquidation', 'BuyingPower', 'TotalCashValue', 'AvailableFunds']:
        if key in account:
            av = account[key]
            logger.info(f"  {key}: {av.value} {av.currency}")
    
    # Monitor for 10 seconds
    logger.info("\nMonitoring account for 10 seconds...")
    time.sleep(10)
    
    # Check state for updates
    state_summary = pa.get_state_summary()
    logger.info(f"\nState summary:")
    logger.info(f"  Account values cached: {state_summary['account_values_count']}")
    logger.info(f"  Last update: {state_summary['last_update']}")
    
    logger.info("✅ Account monitoring test complete")
    return True


def test_state_reconciliation_live(pa: PlatformAdapter):
    """Test state reconciliation with live data."""
    print_section("TEST: State Reconciliation (Live)")
    
    logger.info("Before reconciliation:")
    summary = pa.get_state_summary()
    logger.info(f"  Positions: {summary['positions_count']}")
    logger.info(f"  Orders: {summary['orders_count']}")
    logger.info(f"  Active orders: {summary['active_orders_count']}")
    
    # Reconcile
    logger.info("\nReconciling with IB Gateway...")
    pa.reconcile_state()
    
    # After reconciliation
    logger.info("\nAfter reconciliation:")
    summary = pa.get_state_summary()
    logger.info(f"  Positions: {summary['positions_count']}")
    logger.info(f"  Orders: {summary['orders_count']}")
    logger.info(f"  Active orders: {summary['active_orders_count']}")
    
    # Show active orders
    active_orders = pa.get_active_orders()
    if active_orders:
        logger.info(f"\nActive orders:")
        for order in active_orders:
            logger.info(f"  {order.order_id}: {order.action} {order.quantity} {order.symbol} @ {order.limit_price} [{order.status}]")
    else:
        logger.info("\nNo active orders")
    
    # Show positions
    positions = pa.get_positions()
    if positions:
        logger.info(f"\nPositions:")
        for pos in positions:
            logger.info(f"  {pos.symbol}: {pos.quantity} @ {pos.avg_cost:.2f}")
    else:
        logger.info("\nNo positions (flat)")
    
    logger.info("✅ State reconciliation test complete")
    return True


def main():
    """Run live tests."""
    print("\n" + "="*70)
    print("PLATFORM ADAPTER LIVE TEST SUITE")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Check if market is open
    now = datetime.now()
    hour = now.hour
    weekday = now.weekday()
    
    # Market hours: Mon-Fri 9:30-16:00 ET (rough check)
    is_market_hours = (weekday < 5) and (9 <= hour <= 16)
    
    if not is_market_hours:
        logger.warning("⚠️  Tests are best run during market hours (Mon-Fri 9:30-16:00 ET)")
        logger.warning("Some tests may show delayed/no data")
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            logger.info("Exiting...")
            return
    
    pa = None
    
    try:
        # Initialize and connect
        logger.info("\nInitializing Platform Adapter...")
        pa = PlatformAdapter()
        
        if not pa.connect():
            logger.error("Failed to connect to IB Gateway")
            return
        
        logger.info("✅ Connected successfully")
        
        # Run tests
        logger.info("\n" + "="*70)
        logger.info("STARTING LIVE TESTS")
        logger.info("="*70)
        
        # Test 1: Market data
        test_live_market_data(pa)
        
        # Test 2: Account monitoring
        test_account_monitoring(pa)
        
        # Test 3: State reconciliation
        test_state_reconciliation_live(pa)
        
        # Ask for order tests (involves actual orders)
        print("\n" + "="*70)
        response = input("\n⚠️  Run ORDER TESTS? This will place/modify/cancel orders in paper trading (y/n): ")
        if response.lower() == 'y':
            # Test 4: Order lifecycle
            test_order_lifecycle(pa)
            
            # Test 5: Market order
            response2 = input("\n⚠️  Run MARKET ORDER test? This will BUY and SELL 1 share (y/n): ")
            if response2.lower() == 'y':
                test_market_order(pa)
        
        # Final summary
        print_section("FINAL SUMMARY")
        logger.info(f"Platform: {pa}")
        logger.info(f"State: {pa.state}")
        
        final_summary = pa.get_state_summary()
        logger.info(f"\nFinal State:")
        logger.info(f"  Positions: {final_summary['positions_count']}")
        logger.info(f"  Orders: {final_summary['orders_count']}")
        logger.info(f"  Active Orders: {final_summary['active_orders_count']}")
        logger.info(f"  Account Values: {final_summary['account_values_count']}")
        
        logger.info("\n✅ LIVE TESTS COMPLETE")
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Tests interrupted by user")
    except Exception as e:
        logger.error(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if pa and pa.is_connected:
            logger.info("\nDisconnecting...")
            pa.disconnect()
            logger.info("✅ Disconnected")


if __name__ == "__main__":
    main()
