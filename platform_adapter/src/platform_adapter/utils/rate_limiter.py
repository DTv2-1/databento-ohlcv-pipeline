"""
PA r2 — Per-Channel Rate Limiter

Token bucket rate limiter with:
  - Per-channel limits (market_data_subscribe, order_place, order_modify, etc.)
  - Global sustained rate cap (default 45 msg/s, under IB's 50)
  - Global burst cap (hard limit at IB's 50 msg/s)

IB API Rate Limits (confirmed from official docs):
  - Global: 50 msg/s (market data lines / 2)
  - Historical data: 60 requests per 10 minutes
  - No per-channel limits from IB — our channels are PA-internal safety

Author: PA r2
Date: 2026-02-16
"""

from collections import deque
import time
from threading import Lock
from typing import Dict, Optional
from loguru import logger


class RateLimiter:
    """
    Token bucket rate limiter for API requests.
    
    Thread-safe implementation that tracks requests within a time window
    and blocks when rate limit is exceeded.
    """
    
    def __init__(self, max_requests: int, time_window: int, name: str = ""):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum number of requests allowed
            time_window: Time window in seconds
            name: Optional name for logging
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.name = name
        self.requests: deque = deque()
        self.lock = Lock()
        
        logger.debug(
            f"RateLimiter '{name}' initialized: {max_requests} requests per {time_window}s"
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
                    channel = f"[{self.name}] " if self.name else ""
                    op_str = f" for {operation}" if operation else ""
                    logger.warning(
                        f"{channel}Rate limit reached{op_str}. "
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
            logger.debug(f"[{self.name}] Resumed after {wait_time:.2f}s wait")
        
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
                'name': self.name,
                'requests_in_window': len(self.requests),
                'max_requests': self.max_requests,
                'time_window': self.time_window,
                'utilization': len(self.requests) / self.max_requests if self.max_requests else 0,
                'available': self.max_requests - len(self.requests)
            }
    
    def reset(self):
        """Clear all recorded requests."""
        with self.lock:
            self.requests.clear()
            logger.debug(f"[{self.name}] Rate limiter reset")


class PerChannelRateLimiter:
    """
    PA r2 per-channel rate limiter with global burst protection.
    
    Manages multiple RateLimiter instances (one per channel) plus
    a global sustained-rate limiter and a burst cap.
    
    Channels:
      - market_data_subscribe
      - order_place
      - order_modify
      - order_cancel
      - account
      - misc
    """
    
    def __init__(
        self,
        channel_configs: Optional[Dict[str, dict]] = None,
        global_sustained_per_sec: int = 45,
        global_burst_cap: int = 50,
    ):
        """
        Args:
            channel_configs: Dict of channel_name → {max_requests, time_window}
            global_sustained_per_sec: Sustained global msg/sec (default 45)
            global_burst_cap: Hard burst limit (default 50 = IB limit)
        """
        # Default channel configs per r2 spec
        defaults = {
            "market_data_subscribe": {"max_requests": 50, "time_window": 600},
            "order_place": {"max_requests": 40, "time_window": 1},
            "order_modify": {"max_requests": 30, "time_window": 1},
            "order_cancel": {"max_requests": 30, "time_window": 1},
            "account": {"max_requests": 8, "time_window": 60},
            "misc": {"max_requests": 10, "time_window": 1},
        }
        
        configs = channel_configs or defaults
        
        # Create per-channel limiters
        self._channels: Dict[str, RateLimiter] = {}
        for name, cfg in configs.items():
            self._channels[name] = RateLimiter(
                max_requests=cfg["max_requests"],
                time_window=cfg["time_window"],
                name=name,
            )
        
        # Global sustained limiter
        self._global_sustained = RateLimiter(
            max_requests=global_sustained_per_sec,
            time_window=1,
            name="global_sustained",
        )
        
        # Global burst cap
        self._global_burst = RateLimiter(
            max_requests=global_burst_cap,
            time_window=1,
            name="global_burst",
        )
        
        logger.info(
            f"PerChannelRateLimiter initialized: "
            f"{len(self._channels)} channels, "
            f"sustained={global_sustained_per_sec}/s, "
            f"burst={global_burst_cap}/s"
        )
    
    def wait_if_needed(self, channel: str, operation: Optional[str] = None) -> float:
        """
        Wait if rate limit exceeded on channel or global, then record.
        
        Args:
            channel: Channel name (e.g., "order_place")
            operation: Optional description for logging
            
        Returns:
            Total time waited in seconds
        """
        total_wait = 0.0
        
        # 1. Channel limit
        ch_limiter = self._channels.get(channel)
        if ch_limiter:
            total_wait += ch_limiter.wait_if_needed(operation=operation)
        
        # 2. Global sustained limit
        total_wait += self._global_sustained.wait_if_needed(operation=operation)
        
        # 3. Global burst cap (hard limit)
        total_wait += self._global_burst.wait_if_needed(operation=operation)
        
        return total_wait
    
    def can_proceed(self, channel: str) -> bool:
        """Check if a request on this channel can proceed."""
        ch_limiter = self._channels.get(channel)
        if ch_limiter and not ch_limiter.can_proceed():
            return False
        if not self._global_sustained.can_proceed():
            return False
        if not self._global_burst.can_proceed():
            return False
        return True
    
    def get_channel(self, channel: str) -> Optional[RateLimiter]:
        """Get a specific channel's rate limiter."""
        return self._channels.get(channel)
    
    def get_all_usage(self) -> Dict[str, dict]:
        """Get usage stats for all channels + global."""
        result = {}
        for name, limiter in self._channels.items():
            result[name] = limiter.get_current_usage()
        result["global_sustained"] = self._global_sustained.get_current_usage()
        result["global_burst"] = self._global_burst.get_current_usage()
        return result
    
    def reset_all(self):
        """Reset all rate limiters."""
        for limiter in self._channels.values():
            limiter.reset()
        self._global_sustained.reset()
        self._global_burst.reset()
        logger.info("All rate limiters reset")
    
    def __repr__(self) -> str:
        return f"PerChannelRateLimiter(channels={list(self._channels.keys())})"


# ============================================================================
# BACKWARD COMPATIBILITY — IBRateLimiters (r1 API still works)
# ============================================================================

class IBRateLimiters:
    """
    Pre-configured rate limiters for IB API operations.
    
    r1 compatibility: These class-level instances still work.
    r2 recommendation: Use PerChannelRateLimiter instead.
    """
    
    # Market data subscriptions: ~50 per 10 minutes
    MARKET_DATA = RateLimiter(max_requests=50, time_window=600, name="market_data")
    
    # Historical data requests: ~60 per 10 minutes
    HISTORICAL_DATA = RateLimiter(max_requests=50, time_window=600, name="historical_data")
    
    # Order requests: ~40 per second (conservative)
    ORDERS = RateLimiter(max_requests=40, time_window=1, name="orders")
    
    # Account/position requests: ~8 per minute
    ACCOUNT = RateLimiter(max_requests=8, time_window=60, name="account")
