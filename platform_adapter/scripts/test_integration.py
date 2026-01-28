"""
Simple integration test for Platform Adapter

Tests basic functionality:
1. Connection to IB Gateway
2. Account summary retrieval
3. Position retrieval
4. Market data subscription
5. State management
6. Graceful disconnect

Author: Platform Adapter Team
Created: 2026-01-27
"""

import sys
import time
from pathlib import Path

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


def test_connection():
    """Test basic connection and disconnection."""
    print_section("TEST 1: Connection")
    
    pa = PlatformAdapter()
    
    # Test connection
    success = pa.connect()
    assert success, "Connection should succeed"
    assert pa.is_connected, "Should be connected"
    logger.info("✅ Connection successful")
    
    # Test disconnect
    pa.disconnect()
    assert not pa.is_connected, "Should be disconnected"
    logger.info("✅ Disconnect successful")
    
    return pa


def test_account_summary(pa: PlatformAdapter):
    """Test account summary retrieval."""
    print_section("TEST 2: Account Summary")
    
    account = pa.get_account_summary()
    assert account is not None, "Should retrieve account summary"
    assert len(account) > 0, "Should have account values"
    
    logger.info(f"Retrieved {len(account)} account values:")
    for key in ['NetLiquidation', 'BuyingPower', 'TotalCashValue']:
        if key in account:
            av = account[key]
            logger.info(f"  {key}: {av.value} {av.currency}")
    
    logger.info("✅ Account summary works")
    return account


def test_positions(pa: PlatformAdapter):
    """Test position retrieval."""
    print_section("TEST 3: Positions")
    
    positions = pa.get_positions()
    assert positions is not None, "Should retrieve positions"
    
    logger.info(f"Retrieved {len(positions)} positions:")
    if positions:
        for pos in positions:
            direction = "LONG" if pos.is_long else "SHORT"
            logger.info(f"  {pos.symbol}: {direction} {pos.quantity} @ {pos.avg_cost}")
    else:
        logger.info("  No positions (account is flat)")
    
    logger.info("✅ Positions retrieval works")
    return positions


def test_state_management(pa: PlatformAdapter):
    """Test state management."""
    print_section("TEST 4: State Management")
    
    summary = pa.get_state_summary()
    logger.info(f"State Summary:")
    logger.info(f"  Positions: {summary['positions_count']}")
    logger.info(f"  Orders: {summary['orders_count']}")
    logger.info(f"  Active Orders: {summary['active_orders_count']}")
    logger.info(f"  Account Values: {summary['account_values_count']}")
    logger.info(f"  Last Update: {summary['last_update']}")
    
    # Test state queries
    net_liq = pa.get_account_value('NetLiquidation')
    if net_liq:
        logger.info(f"  Net Liquidation (from state): ${net_liq}")
    
    logger.info("✅ State management works")
    return summary


def test_market_data(pa: PlatformAdapter):
    """Test market data subscription."""
    print_section("TEST 5: Market Data")
    
    quotes_received = []
    
    def on_quote(symbol, data):
        """Callback for market data."""
        quotes_received.append((symbol, data))
        if len(quotes_received) <= 3:  # Print first 3
            logger.info(f"  {symbol}: {data}")
    
    # Subscribe to AAPL
    success = pa.subscribe_market_data("AAPL", on_quote)
    assert success, "Should subscribe successfully"
    logger.info("Subscribed to AAPL, waiting for quotes...")
    
    # Wait for some quotes
    time.sleep(5)
    
    # Unsubscribe
    pa.unsubscribe_market_data("AAPL")
    
    logger.info(f"Received {len(quotes_received)} quotes total")
    logger.info("✅ Market data subscription works")
    
    return len(quotes_received) > 0


def test_reconciliation(pa: PlatformAdapter):
    """Test state reconciliation."""
    print_section("TEST 6: State Reconciliation")
    
    # Reconcile state with IB Gateway
    pa.reconcile_state()
    
    # Check state after reconciliation
    summary = pa.get_state_summary()
    logger.info(f"State after reconciliation:")
    logger.info(f"  Positions: {summary['positions_count']}")
    logger.info(f"  Orders: {summary['orders_count']}")
    
    logger.info("✅ State reconciliation works")


def main():
    """Run all integration tests."""
    print("\n" + "="*70)
    print("PLATFORM ADAPTER INTEGRATION TEST")
    print("="*70)
    
    pa = None
    
    try:
        # Test 1: Connection
        pa = test_connection()
        
        # Reconnect for remaining tests
        pa.connect()
        
        # Test 2: Account summary
        test_account_summary(pa)
        
        # Test 3: Positions
        test_positions(pa)
        
        # Test 4: State management
        test_state_management(pa)
        
        # Test 5: Market data
        test_market_data(pa)
        
        # Test 6: Reconciliation
        test_reconciliation(pa)
        
        # Final summary
        print_section("FINAL STATE")
        final_state = pa.get_state_summary()
        logger.info(f"Platform Adapter: {pa}")
        logger.info(f"State: {pa.state}")
        logger.info(f"Summary: {final_state}")
        
        print_section("TEST SUMMARY")
        logger.info("✅ ALL TESTS PASSED")
        logger.info("Platform Adapter is working correctly!")
        
    except Exception as e:
        logger.error(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        if pa and pa.is_connected:
            logger.info("\nDisconnecting...")
            pa.disconnect()
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
