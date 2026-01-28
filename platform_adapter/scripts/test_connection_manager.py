"""
Test script for Connection Manager
Verifies connection, callbacks, and error handling
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


def on_connected():
    """Callback when connected"""
    print("✅ User callback: Connected!")


def on_disconnected():
    """Callback when disconnected"""
    print("⚠️  User callback: Disconnected!")


def on_error(req_id, error_code, error_string):
    """Callback for errors"""
    print(f"❌ User callback: Error {error_code}: {error_string}")


def main():
    print("=" * 60)
    print("Connection Manager Test")
    print("=" * 60)
    
    # Create connection manager
    cm = ConnectionManager()
    
    # Set callbacks
    cm.on_connected = on_connected
    cm.on_disconnected = on_disconnected
    cm.on_error = on_error
    
    print(f"\nInitial state: {cm}")
    print(f"Is ready: {cm.is_ready()}")
    
    # Test connection
    print("\n🔌 Testing connection...")
    success = cm.connect_to_ib(host="127.0.0.1", port=7497, client_id=1)
    
    if not success:
        print("\n❌ Connection test FAILED")
        return False
    
    print(f"\nConnected state: {cm}")
    print(f"Is ready: {cm.is_ready()}")
    
    # Test health check
    print("\n🏥 Health check:")
    health = cm.health_check()
    for key, value in health.items():
        print(f"  {key}: {value}")
    
    # Test order ID generation
    print("\n🔢 Testing order ID generation:")
    for i in range(3):
        order_id = cm.get_next_order_id()
        print(f"  Order ID {i+1}: {order_id}")
    
    # Keep connection alive for a moment
    print("\n⏱️  Keeping connection alive for 3 seconds...")
    time.sleep(3)
    
    # Test disconnection
    print("\n🔌 Testing disconnection...")
    cm.disconnect_from_ib()
    
    print(f"\nDisconnected state: {cm}")
    print(f"Is ready: {cm.is_ready()}")
    
    print("\n✅ Connection Manager test completed successfully!")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
