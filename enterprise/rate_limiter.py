# enterprise/rate_limiter.py
"""
Enterprise Rate Limiter implementation.

Provides token bucket and sliding window rate limiting for
controlling API request rates and resource consumption.
"""

import asyncio
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field

from logger import get_logger

logger = get_logger(__name__)


class RateLimitStrategy(Enum):
    """Rate limiting strategies."""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    
    requests_per_second: float = 100.0
    """Maximum requests per second"""
    
    requests_per_minute: Optional[float] = None
    """Maximum requests per minute (alternative to per second)"""
    
    requests_per_hour: Optional[float] = None
    """Maximum requests per hour"""
    
    burst_size: int = 10
    """Maximum burst size (token bucket)"""
    
    strategy: RateLimitStrategy = RateLimitStrategy.TOKEN_BUCKET
    """Rate limiting strategy to use"""
    
    block_duration: float = 60.0
    """How long to block when limit is exceeded (seconds)"""


class TokenBucketRateLimiter:
    """
    Token bucket algorithm for rate limiting.
    
    Allows bursts up to bucket size while enforcing average rate limit.
    """
    
    def __init__(self, rate: float, capacity: int):
        self.rate = rate  # tokens per second
        self.capacity = capacity  # max tokens
        self._tokens = float(capacity)
        self._last_update = time.monotonic()
        self._lock = threading.RLock()
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update
        
        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self.rate
        self._tokens = min(self.capacity, self._tokens + tokens_to_add)
        self._last_update = now
    
    def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens were acquired, False otherwise
        """
        with self._lock:
            self._refill()
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False
    
    async def acquire_async(self, tokens: int = 1) -> bool:
        """Async version of acquire."""
        return self.acquire(tokens)
    
    def try_wait(self, tokens: int = 1, timeout: float = 5.0) -> bool:
        """
        Wait up to timeout seconds to acquire tokens.
        
        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum time to wait
            
        Returns:
            True if tokens acquired, False if timeout
        """
        start = time.monotonic()
        
        while True:
            if self.acquire(tokens):
                return True
            
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                return False
            
            # Wait a bit before retrying
            wait_time = min(0.1, remaining)
            time.sleep(wait_time)
    
    async def try_wait_async(self, tokens: int = 1, timeout: float = 5.0) -> bool:
        """Async version of try_wait."""
        start = time.monotonic()
        
        while True:
            if self.acquire(tokens):
                return True
            
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                return False
            
            wait_time = min(0.1, remaining)
            await asyncio.sleep(wait_time)
    
    @property
    def available_tokens(self) -> float:
        """Current available tokens."""
        with self._lock:
            self._refill()
            return self._tokens
    
    @property
    def fill_level(self) -> float:
        """Fill level as percentage (0.0 to 1.0)."""
        with self._lock:
            self._refill()
            return self._tokens / self.capacity


class SlidingWindowRateLimiter:
    """
    Sliding window algorithm for rate limiting.
    
    More accurate than fixed window but uses more memory.
    """
    
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: list = []
        self._lock = threading.RLock()
    
    def _clean_old_requests(self) -> None:
        """Remove requests outside the window."""
        cutoff = time.monotonic() - self.window_seconds
        self._requests = [t for t in self._requests if t > cutoff]
    
    def acquire(self) -> bool:
        """
        Try to record a request.
        
        Returns:
            True if request recorded, False if limit exceeded
        """
        with self._lock:
            self._clean_old_requests()
            
            if len(self._requests) < self.max_requests:
                self._requests.append(time.monotonic())
                return True
            return False
    
    async def acquire_async(self) -> bool:
        """Async version of acquire."""
        return self.acquire()
    
    @property
    def current_count(self) -> int:
        """Current requests in window."""
        with self._lock:
            self._clean_old_requests()
            return len(self._requests)
    
    @property
    def remaining(self) -> int:
        """Remaining requests in current window."""
        return max(0, self.max_requests - self.current_count)
    
    @property
    def oldest_request_age(self) -> Optional[float]:
        """Age of oldest request in window, or None if empty."""
        with self._lock:
            self._clean_old_requests()
            if not self._requests:
                return None
            return time.monotonic() - self._requests[0]


class RateLimiter:
    """
    Unified rate limiter supporting multiple strategies.
    
    Provides consistent interface for rate limiting across the application.
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[RateLimitConfig] = None,
        on_limit_exceeded: Optional[Callable[['RateLimiter'], None]] = None
    ):
        self.name = name
        self.config = config or RateLimitConfig()
        self.on_limit_exceeded = on_limit_exceeded
        
        # Determine rates
        rate = self.config.requests_per_second
        if self.config.requests_per_minute:
            rate = min(rate, self.config.requests_per_minute / 60.0)
        if self.config.requests_per_hour:
            rate = min(rate, self.config.requests_per_hour / 3600.0)
        
        self._rate = rate
        self._burst_size = self.config.burst_size
        
        # Create limiters based on strategy
        if self.config.strategy == RateLimitStrategy.TOKEN_BUCKET:
            self._limiter = TokenBucketRateLimiter(rate, self._burst_size)
        elif self.config.strategy == RateLimitStrategy.SLIDING_WINDOW:
            # For sliding window, use a window of 1 second with max_requests
            window_size = 1.0
            max_req = max(1, int(rate * window_size))
            self._limiter = SlidingWindowRateLimiter(max_req, window_size)
        else:  # FIXED_WINDOW
            window_size = 1.0
            max_req = max(1, int(rate * window_size))
            self._limiter = SlidingWindowRateLimiter(max_req, window_size)
        
        self._total_requests = 0
        self._rejected_requests = 0
        self._blocked_until: Optional[float] = None
        self._lock = threading.RLock()
    
    def acquire(self) -> bool:
        """
        Try to acquire permission for a request.
        
        Returns:
            True if request allowed, False if rate limited
        """
        with self._lock:
            # Check if blocked
            if self._blocked_until:
                if time.monotonic() < self._blocked_until:
                    self._rejected_requests += 1
                    return False
                else:
                    self._blocked_until = None
            
            if self._limiter.acquire():
                self._total_requests += 1
                return True
            else:
                self._rejected_requests += 1
                
                # Block for configured duration
                self._blocked_until = time.monotonic() + self.config.block_duration
                
                if self.on_limit_exceeded:
                    try:
                        self.on_limit_exceeded(self)
                    except Exception as e:
                        logger.error(f"Error in rate limit callback: {e}")
                
                return False
    
    async def acquire_async(self) -> bool:
        """Async version of acquire."""
        return self.acquire()
    
    def try_acquire(self, timeout: float = 0.0) -> bool:
        """
        Try to acquire with optional wait.
        
        Args:
            timeout: Max seconds to wait (0 = no wait)
            
        Returns:
            True if acquired, False if timeout/limited
        """
        if timeout <= 0:
            return self.acquire()
        
        if isinstance(self._limiter, TokenBucketRateLimiter):
            return self._limiter.try_wait(1, timeout)
        else:
            # For sliding window, just check if we can acquire immediately
            return self.acquire()
    
    async def try_acquire_async(self, timeout: float = 0.0) -> bool:
        """Async version of try_acquire."""
        if timeout <= 0:
            return self.acquire_async()
        
        if isinstance(self._limiter, TokenBucketRateLimiter):
            return await self._limiter.try_wait_async(1, timeout)
        else:
            return self.acquire_async()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current rate limiter status."""
        with self._lock:
            return {
                "name": self.name,
                "rate_limit": self._rate,
                "burst_size": self._burst_size,
                "strategy": self.config.strategy.value,
                "total_requests": self._total_requests,
                "rejected_requests": self._rejected_requests,
                "is_blocked": self._blocked_until is not None and time.monotonic() < self._blocked_until,
                "blocked_until": self._blocked_until,
                "available_tokens": (
                    self._limiter.available_tokens 
                    if hasattr(self._limiter, 'available_tokens') 
                    else self._limiter.remaining
                )
            }
    
    def reset(self) -> None:
        """Reset the rate limiter."""
        with self._lock:
            self._total_requests = 0
            self._rejected_requests = 0
            self._blocked_until = None


class RateLimiterRegistry:
    """
    Registry for managing multiple rate limiters.
    """
    
    _instance: Optional['RateLimiterRegistry'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._limiters = {}
                    cls._instance._registry_lock = threading.RLock()
        return cls._instance
    
    def get_or_create(
        self,
        name: str,
        config: Optional[RateLimitConfig] = None
    ) -> RateLimiter:
        """Get or create a rate limiter."""
        with self._registry_lock:
            if name not in self._limiters:
                self._limiters[name] = RateLimiter(name, config)
            return self._limiters[name]
    
    def get(self, name: str) -> Optional[RateLimiter]:
        """Get a rate limiter by name."""
        with self._registry_lock:
            return self._limiters.get(name)
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all rate limiters."""
        with self._registry_lock:
            return {name: lr.get_status() for name, lr in self._limiters.items()}
    
    def reset_all(self) -> None:
        """Reset all rate limiters."""
        with self._registry_lock:
            for lr in self._limiters.values():
                lr.reset()


# Global registry
registry = RateLimiterRegistry()


def get_rate_limiter(
    name: str,
    config: Optional[RateLimitConfig] = None
) -> RateLimiter:
    """Get a rate limiter from the global registry."""
    return registry.get_or_create(name, config)


def rate_limit(
    name: Optional[str] = None,
    requests_per_second: float = 100.0,
    burst_size: int = 10
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to add rate limiting to a function.
    
    Usage:
        @rate_limit(name="my_api", requests_per_second=50)
        def my_function():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        limiter_name = name or f"{func.__module__}.{func.__name__}"
        config = RateLimitConfig(
            requests_per_second=requests_per_second,
            burst_size=burst_size
        )
        limiter = get_rate_limiter(limiter_name, config)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not limiter.acquire():
                from enterprise.exceptions import APIRateLimitError
                raise APIRateLimitError(
                    api_name=limiter_name,
                    retry_after_seconds=config.block_duration
                )
            return func(*args, **kwargs)
        
        # Attach limiter for inspection
        wrapper.rate_limiter = limiter
        
        return wrapper
    
    return decorator


import functools
from typing import TypeVar
T = TypeVar('T')