# enterprise/circuit_breaker.py
"""
Enterprise Circuit Breaker implementation for fault tolerance.

The circuit breaker pattern prevents cascading failures by failing fast
when a service is experiencing issues.
"""

import asyncio
import functools
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Optional, TypeVar, Any, Dict
from dataclasses import dataclass, field

from logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Failing fast, requests are rejected
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    
    failure_threshold: int = 5
    """Number of failures before opening circuit"""
    
    success_threshold: int = 2
    """Number of successes in half-open before closing circuit"""
    
    timeout: float = 30.0
    """Time in seconds before attempting recovery from OPEN state"""
    
    half_open_max_calls: int = 3
    """Maximum concurrent calls allowed in half-open state"""
    
    excluded_exceptions: tuple = field(default_factory=lambda: ())
    """Exceptions that should not count toward failure threshold"""


class CircuitBreaker:
    """
    Circuit breaker for fault tolerance.
    
    Implements the circuit breaker pattern to prevent cascading failures
    when external services are experiencing issues.
    
    States:
        - CLOSED: Normal operation, requests pass through
        - OPEN: Service is failing, requests are rejected immediately
        - HALF_OPEN: Testing recovery, limited requests allowed
        
    Usage:
        breaker = CircuitBreaker("external_api", failure_threshold=5)
        
        @breaker
        def call_external_api():
            ...
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        on_state_change: Optional[Callable[['CircuitBreaker', CircuitState, CircuitState], None]] = None
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.on_state_change = on_state_change
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = threading.RLock()
        
        # Statistics
        self._total_calls = 0
        self._total_failures = 0
        self._total_successes = 0
        self._rejected_calls = 0
        self._state_change_times: Dict[CircuitState, float] = {
            CircuitState.CLOSED: time.monotonic()
        }
    
    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if timeout has elapsed to transition to half-open
                if self._last_failure_time:
                    elapsed = time.monotonic() - self._last_failure_time
                    if elapsed >= self.config.timeout:
                        self._transition_to(CircuitState.HALF_OPEN)
            return self._state
    
    @property
    def is_closed(self) -> bool:
        """Whether circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Whether circuit is open (failing fast)."""
        return self.state == CircuitState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        """Whether circuit is half-open (testing recovery)."""
        return self.state == CircuitState.HALF_OPEN
    
    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        
        if old_state == new_state:
            return
        
        self._state = new_state
        self._state_change_times[new_state] = time.monotonic()
        
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        
        logger.info(
            f"Circuit breaker '{self.name}' state change: {old_state.value} -> {new_state.value}",
            extra_fields={
                "circuit_breaker": self.name,
                "old_state": old_state.value,
                "new_state": new_state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count
            }
        )
        
        if self.on_state_change:
            try:
                self.on_state_change(self, old_state, new_state)
            except Exception as e:
                logger.error(f"Error in circuit breaker state change callback: {e}")
    
    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self._total_calls += 1
            self._total_successes += 1
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls = max(0, self._half_open_calls - 1)
                
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            
            # Reset failure count on success in closed state
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0
    
    def record_failure(self, exception: Optional[Exception] = None) -> None:
        """Record a failed call."""
        with self._lock:
            self._total_calls += 1
            self._total_failures += 1
            self._last_failure_time = time.monotonic()
            
            # Don't count excluded exceptions
            if exception and self.config.excluded_exceptions:
                if isinstance(exception, self.config.excluded_exceptions):
                    return
            
            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately opens the circuit
                self._transition_to(CircuitState.OPEN)
            
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
    
    def can_execute(self) -> bool:
        """Check if a call can be executed."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.OPEN:
                # Check if timeout has elapsed
                if self._last_failure_time:
                    elapsed = time.monotonic() - self._last_failure_time
                    if elapsed >= self.config.timeout:
                        self._transition_to(CircuitState.HALF_OPEN)
                        return True
                self._rejected_calls += 1
                return False
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                self._rejected_calls += 1
                return False
            
            return False
    
    def get_retry_after(self) -> Optional[float]:
        """Get seconds until next retry is allowed (for 503 responses)."""
        with self._lock:
            if self._state == CircuitState.OPEN and self._last_failure_time:
                elapsed = time.monotonic() - self._last_failure_time
                remaining = self.config.timeout - elapsed
                return max(0.0, remaining)
            return None
    
    def allow_request(self) -> bool:
        """Alias for can_execute() for clearer usage."""
        return self.can_execute()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "total_calls": self._total_calls,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "rejected_calls": self._rejected_calls,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure_time": self._last_failure_time,
                "uptime_seconds": time.monotonic() - self._state_change_times.get(CircuitState.CLOSED, time.monotonic())
            }
    
    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._last_failure_time = None
    
    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """
        Decorator to wrap a function with circuit breaker protection.
        
        Usage:
            @circuit_breaker
            def my_function():
                ...
        """
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            if not self.can_execute():
                from enterprise.exceptions import CircuitBreakerOpenError
                retry_after = self.get_retry_after()
                raise CircuitBreakerOpenError(
                    service_name=self.name,
                    failure_reason=f"Circuit is {self.state.value}",
                    retry_after_seconds=retry_after
                )
            
            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure(e)
                raise
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            if not self.can_execute():
                from enterprise.exceptions import CircuitBreakerOpenError
                retry_after = self.get_retry_after()
                raise CircuitBreakerOpenError(
                    service_name=self.name,
                    failure_reason=f"Circuit is {self.state.value}",
                    retry_after_seconds=retry_after
                )
            
            try:
                result = await func(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure(e)
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    def __repr__(self) -> str:
        return f"CircuitBreaker(name={self.name!r}, state={self.state.value})"


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.
    
    Provides a centralized way to manage circuit breakers across
    the application.
    """
    
    _instance: Optional['CircuitBreakerRegistry'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._breakers = {}
                    cls._instance._registry_lock = threading.RLock()
        return cls._instance
    
    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """
        Get an existing circuit breaker or create a new one.
        
        Args:
            name: Name of the circuit breaker
            config: Optional configuration for new circuit breaker
            
        Returns:
            CircuitBreaker instance
        """
        with self._registry_lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        with self._registry_lock:
            return self._breakers.get(name)
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        with self._registry_lock:
            return {name: cb.get_stats() for name, cb in self._breakers.items()}
    
    def reset_all(self) -> None:
        """Reset all circuit breakers to closed state."""
        with self._registry_lock:
            for cb in self._breakers.values():
                cb.reset()
    
    def remove(self, name: str) -> bool:
        """Remove a circuit breaker from the registry."""
        with self._registry_lock:
            if name in self._breakers:
                del self._breakers[name]
                return True
            return False


# Global registry instance
registry = CircuitBreakerRegistry()


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """Get a circuit breaker from the global registry."""
    return registry.get_or_create(name, config)


def circuit_breaker(
    name: Optional[str] = None,
    config: Optional[CircuitBreakerConfig] = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to add circuit breaker protection to a function.
    
    Args:
        name: Name for the circuit breaker (defaults to function name)
        config: Optional circuit breaker configuration
        
    Usage:
        @circuit_breaker(name="external_api")
        def call_external_api():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cb_name = name or f"{func.__module__}.{func.__name__}"
        breaker = get_circuit_breaker(cb_name, config)
        return breaker(func)
    
    return decorator
