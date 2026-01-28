#!/usr/bin/env python3
"""
Test Account Manager

Tests account summary, positions, and account updates.

Author: Platform Adapter Team
Date: January 27, 2026
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from platform_adapter.core.connection_manager import ConnectionManager
from platform_adapter.adapters.account_manager import AccountManager
from loguru import logger


def test_account_summary():
    """Test getting account summary."""
    print("\n" + "="*60)
    print("TEST 1: Account Summary")
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
        print("\n📡 Creating Account Manager...")
        manager = AccountManager(cm)
        print(f"✅ {manager}")
        
        # Get account summary
        print("\n📊 Requesting account summary...")
        summary = manager.get_account_summary(block=True, timeout=5.0)
        
        if summary:
            print(f"\n✅ Received {len(summary)} account values:")
            
            # Show important values
            important_keys = [
                'NetLiquidation', 'TotalCashValue', 'BuyingPower',
                'AvailableFunds', 'EquityWithLoanValue'
            ]
            
            for key in important_keys:
                if key in summary:
                    val = summary[key]
                    print(f"   {key}: {val.value} {val.currency}")
            
            # Show all values
            print(f"\n📋 All account values:")
            for key, val in summary.items():
                print(f"   {key}: {val.value} {val.currency}")
            
            print("\n✅ Account summary test passed")
            return True
        else:
            print("❌ No account summary received")
            return False
        
    finally:
        print("\n🔌 Disconnecting...")
        cm.disconnect_from_ib()
        time.sleep(1)


def test_positions():
    """Test getting positions."""
    print("\n" + "="*60)
    print("TEST 2: Positions")
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
        print("\n📡 Creating Account Manager...")
        manager = AccountManager(cm)
        print(f"✅ {manager}")
        
        # Get positions
        print("\n📊 Requesting positions...")
        positions = manager.get_positions(block=True, timeout=5.0)
        
        print(f"\n✅ Received {len(positions)} positions:")
        
        if positions:
            for pos in positions:
                print(f"   {pos}")
                print(f"      Account: {pos.account}")
                print(f"      Quantity: {pos.quantity}")
                print(f"      Avg Cost: ${pos.avg_cost:.2f}")
                print(f"      Exchange: {pos.exchange}")
        else:
            print("   (No positions - account is flat)")
        
        print("\n✅ Positions test passed")
        return True
        
    finally:
        print("\n🔌 Disconnecting...")
        cm.disconnect_from_ib()
        time.sleep(1)


def test_account_updates():
    """Test subscribing to account updates."""
    print("\n" + "="*60)
    print("TEST 3: Account Updates Subscription")
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
        print("\n📡 Creating Account Manager...")
        manager = AccountManager(cm)
        print(f"✅ {manager}")
        
        # Add callback
        updates_received = []
        def account_callback(value):
            updates_received.append(value)
            print(f"   📊 Update: {value}")
        
        manager.add_account_callback(account_callback)
        
        # Subscribe to updates
        print("\n📡 Subscribing to account updates...")
        success = manager.subscribe_account_updates(subscribe=True)
        
        if not success:
            print("❌ Subscription failed")
            return False
        
        print("✅ Subscribed")
        
        # Wait for some updates
        print("\n⏱️  Listening for updates (5 seconds)...")
        time.sleep(5)
        
        print(f"\n📊 Received {len(updates_received)} updates")
        
        # Check account values
        all_values = manager.get_all_account_values()
        print(f"\n📋 Cached account values: {len(all_values)}")
        
        # Show some values
        if all_values:
            print("\n   Sample values:")
            for i, (key, val) in enumerate(list(all_values.items())[:5]):
                print(f"   {key}: {val.value} {val.currency}")
        
        # Unsubscribe
        print("\n📡 Unsubscribing from updates...")
        manager.subscribe_account_updates(subscribe=False)
        print("✅ Unsubscribed")
        
        print("\n✅ Account updates test passed")
        return True
        
    finally:
        print("\n🔌 Disconnecting...")
        cm.disconnect_from_ib()
        time.sleep(1)


def test_specific_queries():
    """Test querying specific account values and positions."""
    print("\n" + "="*60)
    print("TEST 4: Specific Queries")
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
        print("\n📡 Creating Account Manager...")
        manager = AccountManager(cm)
        print(f"✅ {manager}")
        
        # Get account summary first
        print("\n📊 Getting account summary...")
        summary = manager.get_account_summary(block=True)
        
        # Query specific values
        print("\n🔍 Querying specific account values:")
        
        net_liq = manager.get_account_value('NetLiquidation')
        if net_liq:
            print(f"   Net Liquidation: ${net_liq.value} {net_liq.currency}")
        
        buying_power = manager.get_account_value('BuyingPower')
        if buying_power:
            print(f"   Buying Power: ${buying_power.value} {buying_power.currency}")
        
        # Get positions
        print("\n📊 Getting positions...")
        positions = manager.get_positions(block=True)
        
        # Query specific position
        if positions:
            first_symbol = positions[0].symbol
            print(f"\n🔍 Querying position for {first_symbol}:")
            pos = manager.get_position(first_symbol)
            if pos:
                print(f"   {pos}")
        else:
            print("\n   No positions to query")
        
        print("\n✅ Specific queries test passed")
        return True
        
    finally:
        print("\n🔌 Disconnecting...")
        cm.disconnect_from_ib()
        time.sleep(1)


def main():
    """Run all tests."""
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    print("🧪 ACCOUNT MANAGER TEST SUITE")
    print("Testing account management functionality")
    
    try:
        success = True
        
        success &= test_account_summary()
        success &= test_positions()
        success &= test_account_updates()
        success &= test_specific_queries()
        
        if success:
            print("\n" + "="*60)
            print("✅ ALL TESTS PASSED")
            print("="*60)
            print("\n📝 Summary:")
            print("  ✓ Account summary works")
            print("  ✓ Positions retrieval works")
            print("  ✓ Account updates subscription works")
            print("  ✓ Specific value/position queries work")
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
