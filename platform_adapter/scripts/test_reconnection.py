"""
Test script for Connection Manager Reconnection
Tests automatic reconnection with exponential backoff
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.platform_adapter.core.connection_manager import ConnectionManager
from loguru import logger

# Configure logger
logger.remove()
logger.add(sys.stdout, level="INFO")


def on_reconnecting(attempt, max_attempts):
    """Callback during reconnection"""
    print(f"🔄 Reconnecting: Attempt {attempt}/{max_attempts}")


def on_reconnect_failed():
    """Callback when reconnection fails"""
    print("❌ Reconnection failed after all attempts")


def main():
    print("=" * 60)
    print("Connection Manager Reconnection Test")
    print("=" * 60)
    
    # Create connection manager with auto-reconnect enabled
    cm = ConnectionManager(auto_reconnect=True, max_reconnect_attempts=3)
    
    # Set callbacks
    cm.on_reconnecting = on_reconnecting
    cm.on_reconnect_failed = on_reconnect_failed
    
    print("\n🔌 Connecting to IB Gateway...")
    success = cm.connect_to_ib(host="127.0.0.1", port=7497, client_id=1)
    
    if not success:
        print("\n❌ Initial connection failed")
        return False
    
    print(f"\n✅ Connected: {cm}")
    
    # Simulate connection loss by manually triggering reconnection
    print("\n⚠️  Simulating connection loss...")
    print("   (In real scenario, this would be triggered by IB Gateway disconnect)")
    print("   Manually disconnecting and triggering reconnection...\n")
    
    # Disconnect
    cm.disconnect_from_ib()
    time.sleep(1)
    
    # Manually trigger reconnection
    print("\n🔄 Triggering manual reconnection...")
    cm.manual_reconnect()
    
    # Wait for reconnection attempts
    print("\n⏱️  Waiting for reconnection attempts...")
    for i in range(15):
        time.sleep(1)
        health = cm.health_check()
        
        if health['connected']:
            print(f"\n✅ Reconnected successfully after {health['reconnect_count']} attempts!")
            break
        
        if not health['reconnecting'] and not health['connected']:
            print(f"\n❌ Reconnection failed")
            break
    
    # Final health check
    print("\n🏥 Final health check:")
    health = cm.health_check()
    for key, value in health.items():
        print(f"  {key}: {value}")
    
    # Clean disconnect
    if cm.is_connected:
        print("\n🔌 Disconnecting...")
        cm.disconnect_from_ib()
    
    print("\n✅ Reconnection test completed!")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
