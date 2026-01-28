"""
Test script to verify connection to IB Gateway
This script will attempt to connect and retrieve the next valid order ID
"""

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
import time
import threading


class TestApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.connected_event = threading.Event()
        self.next_order_id = None
        
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        """Handle errors from IB Gateway"""
        print(f"❌ Error {errorCode}: {errorString}")
        
    def connectAck(self):
        """Connection acknowledged"""
        print("✅ Connection acknowledged by IB Gateway")
        
    def nextValidId(self, orderId: int):
        """Receive next valid order ID - means connection is successful"""
        super().nextValidId(orderId)
        print(f"✅ Connected successfully! Next valid order ID: {orderId}")
        self.next_order_id = orderId
        self.connected_event.set()
        
    def connectionClosed(self):
        """Connection closed"""
        print("⚠️  Connection closed")


def test_connection():
    """Test connection to IB Gateway"""
    print("=" * 60)
    print("IB Gateway Connection Test")
    print("=" * 60)
    
    # Create app instance
    app = TestApp()
    
    # Connection parameters
    host = "127.0.0.1"
    port = 7497  # Paper Trading port
    client_id = 1
    
    print(f"\n🔌 Attempting to connect to IB Gateway...")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   Client ID: {client_id}")
    print()
    
    try:
        # Connect
        app.connect(host, port, client_id)
        
        # Start message processing thread
        api_thread = threading.Thread(target=app.run, daemon=True)
        api_thread.start()
        
        # Wait for connection (timeout 10 seconds)
        if app.connected_event.wait(timeout=10):
            print("\n✅ CONNECTION TEST PASSED")
            print(f"   Next Order ID: {app.next_order_id}")
            print(f"   Status: Ready to trade")
        else:
            print("\n❌ CONNECTION TEST FAILED")
            print("   Timeout waiting for connection")
            return False
        
        # Keep alive for a moment
        time.sleep(2)
        
        # Disconnect
        print("\n🔌 Disconnecting...")
        app.disconnect()
        time.sleep(1)
        
        print("\n✅ Test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ CONNECTION TEST FAILED")
        print(f"   Error: {str(e)}")
        return False
    
    finally:
        print("=" * 60)


if __name__ == "__main__":
    success = test_connection()
    exit(0 if success else 1)
