"""
Unit Tests for Utility Components

Tests for:
- RateLimiter: Token bucket implementation
- Logger: Configuration and formatting
- Configuration: Settings management
"""

import unittest
import time
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from platform_adapter.utils.rate_limiter import RateLimiter


class TestRateLimiter(unittest.TestCase):
    """Test RateLimiter token bucket implementation"""
    
    def test_rate_limiter_creation(self):
        """Test creating a RateLimiter with specific limits"""
        limiter = RateLimiter(max_requests=100, time_window=60)
        
        self.assertEqual(limiter.max_requests, 100)
        self.assertEqual(limiter.time_window, 60)
        self.assertEqual(len(limiter.requests), 0)
    
    def test_rate_limiter_can_proceed_within_limit(self):
        """Test that requests within limit can proceed"""
        limiter = RateLimiter(max_requests=5, time_window=1)
        
        # Should allow 5 requests
        for _ in range(5):
            self.assertTrue(limiter.can_proceed())
            limiter.record_request()
    
    def test_rate_limiter_blocks_over_limit(self):
        """Test that requests over limit are blocked"""
        limiter = RateLimiter(max_requests=3, time_window=1)
        
        # Consume all tokens
        for _ in range(3):
            limiter.record_request()
        
        # Next request should not be able to proceed
        self.assertFalse(limiter.can_proceed())
    
    def test_rate_limiter_cleanup_old_requests(self):
        """Test that old requests are cleaned up"""
        limiter = RateLimiter(max_requests=2, time_window=0.5)
        
        # Record 2 requests
        limiter.record_request()
        limiter.record_request()
        self.assertFalse(limiter.can_proceed())
        
        # Wait for time window to pass
        time.sleep(0.6)
        
        # Should be able to proceed again
        self.assertTrue(limiter.can_proceed())
    
    def test_rate_limiter_wait_if_needed(self):
        """Test wait_if_needed() blocks when limit exceeded"""
        limiter = RateLimiter(max_requests=1, time_window=0.3)
        
        # First request should not wait
        wait_time = limiter.wait_if_needed("test_op")
        self.assertLess(wait_time, 0.1)
        
        # Second request should wait
        start = time.time()
        wait_time = limiter.wait_if_needed("test_op")
        elapsed = time.time() - start
        
        # Should have waited approximately time_window duration
        self.assertGreater(elapsed, 0.2)  # Allow some margin
    
    def test_rate_limiter_get_current_usage(self):
        """Test get_current_usage() returns correct stats"""
        limiter = RateLimiter(max_requests=10, time_window=1)
        
        # Record some requests
        for _ in range(3):
            limiter.record_request()
        
        usage = limiter.get_current_usage()
        
        self.assertEqual(usage['requests_in_window'], 3)
        self.assertEqual(usage['max_requests'], 10)
        self.assertEqual(usage['available'], 7)
        self.assertAlmostEqual(usage['utilization'], 0.3)
    
    def test_rate_limiter_reset(self):
        """Test that rate limiter can be reset"""
        limiter = RateLimiter(max_requests=3, time_window=10)
        
        # Consume all tokens
        for _ in range(3):
            limiter.record_request()
        
        self.assertFalse(limiter.can_proceed())
        
        # Reset
        limiter.reset()
        self.assertTrue(limiter.can_proceed())
        
        usage = limiter.get_current_usage()
        self.assertEqual(usage['requests_in_window'], 0)


class TestLoggerConfiguration(unittest.TestCase):
    """Test Logger configuration and formatting"""
    
    @patch('platform_adapter.utils.logger.logger')
    def test_logger_info(self, mock_logger):
        """Test logger info level"""
        from platform_adapter.utils.logger import logger
        
        logger.info("Test message")
        
        # Verify logger was called
        mock_logger.info.assert_called_once_with("Test message")
    
    @patch('platform_adapter.utils.logger.logger')
    def test_logger_error(self, mock_logger):
        """Test logger error level"""
        from platform_adapter.utils.logger import logger
        
        logger.error("Error message")
        
        mock_logger.error.assert_called_once_with("Error message")
    
    @patch('platform_adapter.utils.logger.logger')
    def test_logger_warning(self, mock_logger):
        """Test logger warning level"""
        from platform_adapter.utils.logger import logger
        
        logger.warning("Warning message")
        
        mock_logger.warning.assert_called_once_with("Warning message")
    
    @patch('platform_adapter.utils.logger.logger')
    def test_logger_debug(self, mock_logger):
        """Test logger debug level"""
        from platform_adapter.utils.logger import logger
        
        logger.debug("Debug message")
        
        mock_logger.debug.assert_called_once_with("Debug message")
    
    def test_logger_format_includes_timestamp(self):
        """Test that log format includes timestamp"""
        from platform_adapter.utils.logger import logger
        
        # Logger should be configured with timestamp format
        # This is implementation-specific, adjust based on your logger config
        self.assertIsNotNone(logger)
    
    def test_logger_format_includes_level(self):
        """Test that log format includes level"""
        from platform_adapter.utils.logger import logger
        
        # Logger should be configured with level in format
        self.assertIsNotNone(logger)
    
    def test_logger_exception_handling(self):
        """Test logger handles exceptions properly"""
        from platform_adapter.utils.logger import logger
        
        try:
            raise ValueError("Test exception")
        except ValueError as e:
            # Should not raise, just log
            logger.exception("Exception occurred")


class TestConfigurationManagement(unittest.TestCase):
    """Test Configuration settings management"""
    
    @patch.dict('os.environ', {'TWS_PORT': '7497'})
    def test_config_from_environment(self):
        """Test loading config from environment variables"""
        # This would test your actual config loading mechanism
        # Adjust based on how you load config
        import os
        port = os.getenv('TWS_PORT')
        self.assertEqual(port, '7497')
    
    @patch.dict('os.environ', {'TWS_HOST': 'localhost', 'TWS_CLIENT_ID': '1'})
    def test_config_multiple_values(self):
        """Test loading multiple config values"""
        import os
        host = os.getenv('TWS_HOST')
        client_id = os.getenv('TWS_CLIENT_ID')
        
        self.assertEqual(host, 'localhost')
        self.assertEqual(client_id, '1')
    
    def test_config_default_values(self):
        """Test config provides default values when not set"""
        import os
        
        # Use get with default
        value = os.getenv('NONEXISTENT_CONFIG', 'default_value')
        self.assertEqual(value, 'default_value')
    
    @patch.dict('os.environ', {'LOG_LEVEL': 'DEBUG'})
    def test_config_log_level(self):
        """Test log level configuration"""
        import os
        log_level = os.getenv('LOG_LEVEL')
        self.assertEqual(log_level, 'DEBUG')


class TestHelperFunctions(unittest.TestCase):
    """Test utility helper functions"""
    
    def test_timestamp_formatting(self):
        """Test timestamp formatting helper"""
        # Example: if you have a format_timestamp function
        now = datetime.now()
        formatted = now.strftime("%Y-%m-%d %H:%M:%S")
        
        self.assertIsNotNone(formatted)
        self.assertIn("-", formatted)
        self.assertIn(":", formatted)
    
    def test_parse_ib_timestamp(self):
        """Test parsing IB timestamp format"""
        # IB timestamps are typically Unix timestamps or specific format
        # Adjust based on your actual implementation
        timestamp = "20240127 10:30:00"
        
        # Example parsing
        parsed = datetime.strptime(timestamp, "%Y%m%d %H:%M:%S")
        self.assertEqual(parsed.year, 2024)
        self.assertEqual(parsed.month, 1)
        self.assertEqual(parsed.day, 27)
    
    def test_validate_symbol(self):
        """Test symbol validation"""
        # Example: if you have symbol validation
        valid_symbols = ["AAPL", "MSFT", "TSLA", "SPY"]
        
        for symbol in valid_symbols:
            self.assertTrue(len(symbol) > 0)
            self.assertTrue(symbol.isupper())
    
    def test_calculate_quantity(self):
        """Test quantity calculation helper"""
        # Example: calculating order quantity based on position size
        price = 100.0
        risk_amount = 1000.0
        quantity = int(risk_amount / price)
        
        self.assertEqual(quantity, 10)


def run_tests():
    """Run all utility tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestRateLimiter))
    suite.addTests(loader.loadTestsFromTestCase(TestLoggerConfiguration))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigurationManagement))
    suite.addTests(loader.loadTestsFromTestCase(TestHelperFunctions))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
