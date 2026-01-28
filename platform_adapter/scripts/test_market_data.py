"""
Test script for Market Data Adapter
Tests real-time market data subscription
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.platform_adapter.core.connection_manager import ConnectionManager
from src.platform_adapter.adapters.market_data_adapter import MarketDataAdapter
from src.platform_adapter.models.contract import Contract
from loguru import logger

# Configure logger
logger.remove()
logger.add(sys.stdout, level="INFO")


def on_quote_update(quote):
    """Callback for quote updates"""
    if quote.bid or quote.ask or quote.last:
        print(f"📊 {quote}")


def main():
    print("=" * 60)
    print("Market Data Adapter Test")
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
    
    # Subscribe to SPY
    print("📈 Subscribing to SPY market data...")
    spy_contract = Contract.stock("SPY", "SMART", "USD")
    req_id = mda.subscribe_market_data(spy_contract, callback=on_quote_update)
    print(f"✅ Subscribed (req_id={req_id})\n")
    
    # Wait for data - give it more time for initial connection
    print("⏱️  Receiving market data for 20 seconds...\n")
    time.sleep(20)
    
    # Check quote
    print("\n📊 Current Quote:")
    quote = mda.get_quote("SPY")
    if quote:
        print(f"  Symbol:     {quote.symbol}")
        print(f"  Bid:        {quote.bid} x {quote.bid_size}")
        print(f"  Ask:        {quote.ask} x {quote.ask_size}")
        print(f"  Last:       {quote.last} x {quote.last_size}")
        print(f"  Volume:     {quote.volume}")
        print(f"  Timestamp:  {quote.timestamp}")
    else:
        print("  No quote data available")
    
    # Unsubscribe
    print(f"\n🛑 Unsubscribing...")
    mda.unsubscribe_market_data(req_id)
    
    # Disconnect
    print("\n🔌 Disconnecting...")
    cm.disconnect_from_ib(clear_params=True)
    
    print("\n✅ Market data test completed!")
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
