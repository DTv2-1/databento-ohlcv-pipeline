"""
Rate Limiter Utility for IB API

Implements token bucket algorithm to prevent exceeding IB API rate limits.

IB API Rate Limits (approximate):
- Market data requests: ~60 per 10 minutes
- Historical data requests: ~60 per 10 minutes
- Order requests: Higher limit, ~50 per second

Author: Platform Adapter Team
Date: January 27, 2026
"""

from collections import deque
import time
from threading import Lock
from typing import Optional
from loguru import logger


class RateLimiter:
    """
    Token bucket rate limiter for API requests.
    
    Thread-safe implementation that tracks requests within a time window
    and blocks when rate limit is exceeded.
    """
    
    def __init__(self, max_requests: int, time_window: int):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum number of requests allowed
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: deque = deque()
        self.lock = Lock()
        
        logger.debug(
            f"RateLimiter initialized: {max_requests} requests per {time_window}s"
        )
    
    def can_proceed(self) -> bool:
        """
        Check if a new request can proceed without waiting.
        
        Returns:
            True if request can proceed, False otherwise
        """
        with self.lock:
            self._cleanup_old_requests()
            return len(self.requests) < self.max_requests
    
    def wait_if_needed(self, operation: Optional[str] = None) -> float:
        """
        Wait if rate limit is exceeded, then record the request.
        
        Args:
            operation: Optional name of operation for logging
            
        Returns:
            Time waited in seconds
        """
        wait_time = 0.0
        start_wait = time.time()
        
        with self.lock:
            self._cleanup_old_requests()
            
            # If rate limit exceeded, wait
            if len(self.requests) >= self.max_requests:
                # Calculate how long to wait
                oldest_request = self.requests[0]
                time_to_wait = (oldest_request + self.time_window) - time.time()
                
                if time_to_wait > 0:
                    op_str = f" for {operation}" if operation else ""
                    logger.warning(
                        f"Rate limit reached{op_str}. "
                        f"Waiting {time_to_wait:.2f}s..."
                    )
        
        # Wait outside the lock
        while not self.can_proceed():
            time.sleep(0.1)
        
        wait_time = time.time() - start_wait
        
        # Record the request
        with self.lock:
            self.record_request()
        
        if wait_time > 0.1:
            logger.debug(f"Resumed after {wait_time:.2f}s wait")
        
        return wait_time
    
    def record_request(self):
        """Record a new request timestamp."""
        self.requests.append(time.time())
    
    def _cleanup_old_requests(self):
        """Remove requests outside the time window."""
        now = time.time()
        cutoff = now - self.time_window
        
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()
    
    def get_current_usage(self) -> dict:
        """
        Get current rate limiter statistics.
        
        Returns:
            Dict with usage stats
        """
        with self.lock:
            self._cleanup_old_requests()
            return {
                'requests_in_window': len(self.requests),
                'max_requests': self.max_requests,
                'time_window': self.time_window,
                'utilization': len(self.requests) / self.max_requests,
                'available': self.max_requests - len(self.requests)
            }
    
    def reset(self):
        """Clear all recorded requests."""
        with self.lock:
            self.requests.clear()
            logger.debug("Rate limiter reset")


# Pre-configured rate limiters for common IB API operations
class IBRateLimiters:
    """Pre-configured rate limiters for IB API operations."""
    
    # Market data subscriptions: ~60 per 10 minutes
    MARKET_DATA = RateLimiter(max_requests=50, time_window=600)
    
    # Historical data requests: ~60 per 10 minutes
    HISTORICAL_DATA = RateLimiter(max_requests=50, time_window=600)
    
    # Order requests: ~50 per second (conservative)
    ORDERS = RateLimiter(max_requests=40, time_window=1)
    
    # Account/position requests: ~10 per minute
    ACCOUNT = RateLimiter(max_requests=8, time_window=60)
