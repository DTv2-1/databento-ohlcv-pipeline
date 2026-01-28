"""
Integration Tests for Connection Management

Tests the ConnectionManager component with actual IB Gateway/TWS connection.
Requires IB Gateway or TWS running on localhost:7497.

Author: Platform Adapter Team
Date: January 27, 2026
"""

import unittest
import time
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from platform_adapter.core.connection_manager import ConnectionManager
from platform_adapter.utils.logger import logger


class TestConnectionIntegration(unittest.TestCase):
    """Integration tests for Connection Manager"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test class"""
        cls.host = "localhost"
        cls.port = 7497  # Paper trading port
        cls.client_id = 999  # Test client ID
        logger.info("Starting Connection Integration Tests")
    
    def setUp(self):
        """Set up each test"""
        self.manager = None
    
    def tearDown(self):
        """Clean up after each test"""
        if self.manager and self.manager.is_connected:
            self.manager.disconnect_from_ib()
            time.sleep(0.5)
    
    def test_connection_lifecycle(self):
        """Test complete connection lifecycle: connect, verify, disconnect"""
        logger.info("TEST: Connection Lifecycle")
        
        # Create connection manager
        self.manager = ConnectionManager()
        
        # Initially not connected
        self.assertFalse(self.manager.is_connected)
        
        # Connect
        success = self.manager.connect_to_ib(
            host=self.host,
            port=self.port,
            client_id=self.client_id
        )
        self.assertTrue(success, "Failed to connect to IB Gateway")
        
        # Wait for connection to stabilize
        time.sleep(1)
        
        # Verify connected
        self.assertTrue(self.manager.is_connected)
        
        # Disconnect
        self.manager.disconnect_from_ib()
        time.sleep(0.5)
        
        # Verify disconnected
        self.assertFalse(self.manager.is_connected)
        
        logger.info("✓ Connection lifecycle test passed")
    
    def test_connection_with_reconnect(self):
        """Test connection with automatic reconnect enabled"""
        logger.info("TEST: Connection with Reconnect")
        
        self.manager = ConnectionManager(auto_reconnect=True)
        
        # Connect
        success = self.manager.connect_to_ib(
            host=self.host,
            port=self.port,
            client_id=self.client_id + 1
        )
        self.assertTrue(success)
        time.sleep(1)
        
        # Verify auto_reconnect is enabled
        self.assertTrue(self.manager.auto_reconnect)
        
        logger.info("✓ Reconnect configuration test passed")
    
    def test_multiple_connections_different_client_ids(self):
        """Test that multiple connections can use different client IDs"""
        logger.info("TEST: Multiple Client IDs")
        
        manager1 = ConnectionManager()
        manager2 = ConnectionManager()
        
        try:
            # Connect first manager
            success1 = manager1.connect_to_ib(
                host=self.host,
                port=self.port,
                client_id=self.client_id + 10
            )
            self.assertTrue(success1)
            time.sleep(1)
            
            # Connect second manager (should work with different client_id)
            success2 = manager2.connect_to_ib(
                host=self.host,
                port=self.port,
                client_id=self.client_id + 11
            )
            self.assertTrue(success2)
            time.sleep(1)
            
            # Both should be connected
            self.assertTrue(manager1.is_connected)
            self.assertTrue(manager2.is_connected)
            
            logger.info("✓ Multiple client IDs test passed")
            
        finally:
            if manager1.is_connected:
                manager1.disconnect_from_ib()
            if manager2.is_connected:
                manager2.disconnect_from_ib()
            time.sleep(0.5)
    
    def test_connection_failure_wrong_port(self):
        """Test connection failure with wrong port"""
        logger.info("TEST: Connection Failure (Wrong Port)")
        
        self.manager = ConnectionManager(auto_reconnect=False)
        
        # Should fail to connect
        success = self.manager.connect_to_ib(
            host=self.host,
            port=9999,  # Wrong port
            client_id=self.client_id + 20,
            timeout=3
        )
        
        # Give it a moment
        time.sleep(1)
        
        # Should not be connected
        self.assertFalse(self.manager.is_connected)
        
        logger.info("✓ Connection failure test passed")
    
    def test_connection_state_tracking(self):
        """Test that connection state is properly tracked"""
        logger.info("TEST: Connection State Tracking")
        
        self.manager = ConnectionManager()
        
        # Check initial state
        self.assertFalse(self.manager.is_connected)
        
        # Connect
        self.manager.connect_to_ib(
            host=self.host,
            port=self.port,
            client_id=self.client_id + 30
        )
        time.sleep(1)
        
        # Check connected state
        self.assertTrue(self.manager.is_connected)
        
        # Check state attributes
        self.assertEqual(self.manager.host, self.host)
        self.assertEqual(self.manager.port, self.port)
        self.assertIsNotNone(self.manager.next_valid_order_id)
        
        logger.info("✓ Connection state tracking test passed")
    
    def test_connection_timeout(self):
        """Test connection with custom timeout"""
        logger.info("TEST: Connection Timeout")
        
        self.manager = ConnectionManager()
        
        # Connect with short timeout
        start = time.time()
        success = self.manager.connect_to_ib(
            host=self.host,
            port=self.port,
            client_id=self.client_id + 40,
            timeout=5
        )
        elapsed = time.time() - start
        
        # Should connect quickly (well under timeout)
        self.assertTrue(success)
        self.assertLess(elapsed, 5)
        
        time.sleep(1)
        self.assertTrue(self.manager.is_connected)
        
        logger.info("✓ Connection timeout test passed")
    
    def test_disconnect_idempotency(self):
        """Test that disconnect can be called multiple times safely"""
        logger.info("TEST: Disconnect Idempotency")
        
        self.manager = ConnectionManager()
        
        # Connect
        self.manager.connect_to_ib(
            host=self.host,
            port=self.port,
            client_id=self.client_id + 50
        )
        time.sleep(1)
        
        # Disconnect multiple times
        self.manager.disconnect_from_ib()
        time.sleep(0.3)
        self.manager.disconnect_from_ib()  # Should not raise error
        time.sleep(0.3)
        self.manager.disconnect_from_ib()  # Should not raise error
        
        # Should be disconnected
        self.assertFalse(self.manager.is_connected)
        
        logger.info("✓ Disconnect idempotency test passed")


def run_tests():
    """Run all connection integration tests"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestConnectionIntegration)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    print("\n" + "="*70)
    print("CONNECTION INTEGRATION TESTS")
    print("="*70)
    print("\nREQUIREMENTS:")
    print("  • IB Gateway or TWS running")
    print("  • Paper Trading account")
    print("  • Port 7497 available")
    print("="*70 + "\n")
    
    success = run_tests()
    
    print("\n" + "="*70)
    if success:
        print("✓ ALL CONNECTION TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED")
    print("="*70 + "\n")
    
    exit(0 if success else 1)
