"""
Test script for Historical Data
Tests historical bar data retrieval
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.platform_adapter.core.connection_manager import ConnectionManager
from src.platform_adapter.adapters.market_data_adapter import MarketDataAdapter
from src.platform_adapter.models.contract import Contract
from loguru import logger

# Configure logger
logger.remove()
logger.add(sys.stdout, level="INFO")


def on_historical_data(bars):
    """Callback for historical data completion"""
    print(f"\n📊 Received {len(bars)} bars")
    if bars:
        print(f"First bar: {bars[0]}")
        print(f"Last bar:  {bars[-1]}")


def main():
    print("=" * 60)
    print("Historical Data Test")
    print("=" * 60)
    
    # Connect to IB Gateway
    print("\n🔌 Connecting to IB Gateway...")
    cm = ConnectionManager(auto_reconnect=True)
    
    if not cm.connect_to_ib(host="127.0.0.1", port=7497, client_id=1):
        print("\n❌ Connection failed")
        return False
    
    print(f"✅ Connected: {cm}\n")
    
    # Create market data adapter
    print("📡 Creating Market Data Adapter...")
    mda = MarketDataAdapter(cm)
    print(f"✅ {mda}\n")
    
    # Request historical data for SPY
    print("📈 Requesting historical data for SPY...")
    print("   Duration: 1 day")
    print("   Bar size: 5 mins")
    print("   Data type: TRADES\n")
    
    spy_contract = Contract.stock("SPY", "SMART", "USD")
    req_id = mda.request_historical_data(
        contract=spy_contract,
        duration="1 D",
        bar_size="5 mins",
        what_to_show="TRADES",
        use_rth=True,
        callback=on_historical_data
    )
    print(f"✅ Request sent (req_id={req_id})\n")
    
    # Wait for data
    print("⏱️  Waiting for historical data (10 seconds)...\n")
    time.sleep(10)
    
    # Check data
    bars = mda.get_historical_data(req_id)
    if bars:
        print(f"\n📊 Total bars received: {len(bars)}")
        print(f"\nFirst 3 bars:")
        for bar in bars[:3]:
            print(f"  {bar}")
        
        if len(bars) > 3:
            print(f"\nLast 3 bars:")
            for bar in bars[-3:]:
                print(f"  {bar}")
    else:
        print("\n⚠️  No historical data received")
    
    # Disconnect
    print("\n🔌 Disconnecting...")
    cm.disconnect_from_ib(clear_params=True)
    
    print("\n✅ Historical data test completed!")
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Test failed: {e}")
        sys.exit(1)
