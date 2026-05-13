# enterprise/retry.py
"""
Enterprise retry logic with exponential backoff and jitter.

Provides decorators and utilities for implementing robust retry
policies with configurable backoff strategies.
"""

import asyncio
import functools
import random
import time
from typing import Callable, Optional, Type, Tuple, TypeVar, Any, Set
from datetime import datetime, timedelta

from logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class RetryPolicy:
    """
    Configuration for retry behavior.
    
    Attributes:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add random jitter to delays
        jitter_factor: Factor for random jitter (0.0 to 1.0)
        retryable_exceptions: Tuple of exception types that should trigger retry
    """
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        jitter_factor: float = 0.1,
        retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
        timeout_seconds: Optional[float] = None
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.jitter_factor = jitter_factor
        self.retryable_exceptions = retryable_exceptions or (Exception,)
        self.timeout_seconds = timeout_seconds
    
    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay before next retry attempt.
        
        Args:
            attempt: The current attempt number (1-based)
            
        Returns:
            Delay in seconds before next retry
        """
        # Exponential backoff: base_delay * (exponential_base ^ (attempt - 1))
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        
        # Cap at max_delay
        delay = min(delay, self.max_delay)
        
        # Add jitter to prevent thundering herd
        if self.jitter:
            jitter_range = delay * self.jitter_factor
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0.0, delay)
    
    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """
        Determine if an exception should trigger a retry.
        
        Args:
            exception: The exception that was raised
            attempt: The current attempt number (1-based)
            
        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.max_attempts:
            return False
        
        # Check if exception type is retryable
        return isinstance(exception, self.retryable_exceptions)


# Default retry policies for common scenarios
RETRY_POLICIES = {
    "default": RetryPolicy(
        max_attempts=3,
        base_delay=1.0,
        max_delay=10.0,
        jitter=True,
        jitter_factor=0.1
    ),
    "aggressive": RetryPolicy(
        max_attempts=5,
        base_delay=0.5,
        max_delay=30.0,
        jitter=True,
        jitter_factor=0.2
    ),
    "conservative": RetryPolicy(
        max_attempts=2,
        base_delay=2.0,
        max_delay=60.0,
        jitter=True,
        jitter_factor=0.05
    ),
    "external_api": RetryPolicy(
        max_attempts=4,
        base_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
        jitter_factor=0.15
    ),
    "database": RetryPolicy(
        max_attempts=3,
        base_delay=0.5,
        max_delay=10.0,
        exponential_base=1.5,
        jitter=True,
        jitter_factor=0.1
    )
}


def retry(
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    exponential_base: Optional[float] = None,
    jitter: Optional[bool] = None,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    timeout_seconds: Optional[float] = None,
    policy_name: Optional[str] = None,
    on_retry: Optional[Callable[[Exception, int, float], None]] = None
):
    """
    Decorator to add retry logic to a function.
    
    Usage:
        @retry(max_attempts=3, base_delay=1.0)
        def my_function():
            ...
    
    Args:
        max_attempts: Maximum retry attempts (overrides policy)
        base_delay: Initial delay in seconds (overrides policy)
        max_delay: Maximum delay in seconds (overrides policy)
        exponential_base: Exponential backoff base (overrides policy)
        jitter: Whether to add jitter (overrides policy)
        retryable_exceptions: Exception types to retry on
        timeout_seconds: Overall timeout for all retries
        policy_name: Name of predefined policy to use
        on_retry: Callback function(exception, attempt, delay) called on each retry
    
    Example:
        @retry(policy_name="external_api")
        async def fetch_data():
            return await api.get()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Build policy
        if policy_name and policy_name in RETRY_POLICIES:
            policy = RETRY_POLICIES[policy_name]
        else:
            policy = RetryPolicy()
        
        if max_attempts is not None:
            policy.max_attempts = max_attempts
        if base_delay is not None:
            policy.base_delay = base_delay
        if max_delay is not None:
            policy.max_delay = max_delay
        if exponential_base is not None:
            policy.exponential_base = exponential_base
        if jitter is not None:
            policy.jitter = jitter
        if retryable_exceptions is not None:
            policy.retryable_exceptions = retryable_exceptions
        if timeout_seconds is not None:
            policy.timeout_seconds = timeout_seconds
        
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                start_time = time.monotonic()
                last_exception = None
                
                for attempt in range(1, policy.max_attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        
                        if not policy.should_retry(e, attempt):
                            raise
                        
                        # Check timeout
                        if policy.timeout_seconds:
                            elapsed = time.monotonic() - start_time
                            if elapsed >= policy.timeout_seconds:
                                logger.warning(
                                    f"Retry timeout reached after {elapsed:.2f}s",
                                    extra_fields={"function": func.__name__, "attempts": attempt}
                                )
                                raise
                        
                        delay = policy.calculate_delay(attempt)
                        
                        logger.warning(
                            f"Retry {attempt}/{policy.max_attempts} for {func.__name__} "
                            f"after {delay:.2f}s delay. Error: {e}",
                            extra_fields={
                                "function": func.__name__,
                                "attempt": attempt,
                                "delay": delay,
                                "error_type": type(e).__name__
                            }
                        )
                        
                        if on_retry:
                            on_retry(e, attempt, delay)
                        
                        await asyncio.sleep(delay)
                
                # If we get here, all retries failed
                if last_exception:
                    raise last_exception
                raise RuntimeError(f"All {policy.max_attempts} retry attempts failed")
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                start_time = time.monotonic()
                last_exception = None
                
                for attempt in range(1, policy.max_attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        
                        if not policy.should_retry(e, attempt):
                            raise
                        
                        # Check timeout
                        if policy.timeout_seconds:
                            elapsed = time.monotonic() - start_time
                            if elapsed >= policy.timeout_seconds:
                                logger.warning(
                                    f"Retry timeout reached after {elapsed:.2f}s",
                                    extra_fields={"function": func.__name__, "attempts": attempt}
                                )
                                raise
                        
                        delay = policy.calculate_delay(attempt)
                        
                        logger.warning(
                            f"Retry {attempt}/{policy.max_attempts} for {func.__name__} "
                            f"after {delay:.2f}s delay. Error: {e}",
                            extra_fields={
                                "function": func.__name__,
                                "attempt": attempt,
                                "delay": delay,
                                "error_type": type(e).__name__
                            }
                        )
                        
                        if on_retry:
                            on_retry(e, attempt, delay)
                        
                        time.sleep(delay)
                
                if last_exception:
                    raise last_exception
                raise RuntimeError(f"All {policy.max_attempts} retry attempts failed")
            
            return sync_wrapper
    
    return decorator


class RetryContext:
    """
    Context manager for retry operations with state tracking.
    
    Useful when retry behavior needs to be dynamic or stateful.
    
    Usage:
        async with RetryContext(max_attempts=3) as ctx:
            for attempt in ctx:
                try:
                    return await operation()
                except Exception as e:
                    ctx.record_failure(e)
    """
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        
        self._attempt = 0
        self._failures: list = []
        self._policy = RetryPolicy(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=max_delay,
            exponential_base=exponential_base,
            jitter=jitter
        )
    
    def __enter__(self) -> 'RetryContext':
        self._attempt = 0
        self._failures = []
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def __iter__(self):
        return self
    
    def __next__(self) -> int:
        self._attempt += 1
        if self._attempt > self.max_attempts:
            raise StopIteration
        return self._attempt
    
    @property
    def attempt(self) -> int:
        """Current attempt number (1-based)."""
        return self._attempt
    
    @property
    def can_retry(self) -> bool:
        """Whether more retries are allowed."""
        return self._attempt < self.max_attempts
    
    @property
    def next_delay(self) -> float:
        """Calculate delay before next retry."""
        return self._policy.calculate_delay(self._attempt)
    
    def record_failure(self, exception: Exception) -> bool:
        """
        Record a failure and return whether retry should continue.
        
        Args:
            exception: The exception that was raised
            
        Returns:
            True if should continue retrying, False otherwise
        """
        self._failures.append(exception)
        return self.can_retry and self._policy.should_retry(exception, self._attempt)
    
    @property
    def failures(self) -> list:
        """List of recorded failures."""
        return self._failures.copy()


async def retry_async(
    coro: Callable[..., Any],
    *args,
    policy: Optional[RetryPolicy] = None,
    **kwargs
) -> Any:
    """
    Retry an async coroutine with a given policy.
    
    Args:
        coro: Async coroutine to execute
        *args: Arguments to pass to coroutine
        policy: Retry policy to use
        **kwargs: Keyword arguments to pass to coroutine
        
    Returns:
        Result of successful coroutine execution
        
    Raises:
        The last exception if all retries fail
    """
    policy = policy or RETRY_POLICIES["default"]
    
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await coro(*args, **kwargs)
        except Exception as e:
            if not policy.should_retry(e, attempt):
                raise
            
            delay = policy.calculate_delay(attempt)
            logger.debug(f"Retrying after {delay:.2f}s (attempt {attempt}/{policy.max_attempts})")
            await asyncio.sleep(delay)
    
    raise RuntimeError(f"All {policy.max_attempts} retry attempts failed")
