# tests/test_enterprise.py
"""
Tests for enterprise module components.

Tests cover:
- Exception hierarchy
- Retry policies
- Circuit breaker
- Rate limiter
"""

import pytest
import asyncio
import threading
import time
from unittest.mock import Mock, patch

from enterprise import (
    GreekNNException,
    ConfigurationError,
    ServiceUnavailableError,
    APIRateLimitError,
    RiskLimitExceededError,
    RetryPolicy,
    RetryContext,
    RETRY_POLICIES,
    retry,
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreaker,
    get_circuit_breaker,
    CircuitBreakerRegistry,
    RateLimitStrategy,
    RateLimitConfig,
    TokenBucketRateLimiter,
    SlidingWindowRateLimiter,
    RateLimiter,
    get_rate_limiter,
)


# ==================== Exception Tests ====================

class TestExceptions:
    """Tests for exception hierarchy."""
    
    def test_exception_to_dict(self):
        """Test exception serialization to dictionary."""
        exc = GreekNNException(
            message="Test error",
            error_code="TEST_ERROR",
            details={"key": "value"},
            cause=ValueError("original")
        )
        
        result = exc.to_dict()
        
        assert result["error_code"] == "TEST_ERROR"
        assert result["message"] == "Test error"
        assert result["details"]["key"] == "value"
        assert "cause" in result
    
    def test_risk_limit_exceeded_error(self):
        """Test RiskLimitExceededError contains correct fields."""
        exc = RiskLimitExceededError(
            risk_type="vega",
            current_value=150000.0,
            limit_value=100000.0,
            portfolio_id="PORT-001"
        )
        
        assert exc.risk_type == "vega"
        assert exc.current_value == 150000.0
        assert exc.limit_value == 100000.0
        assert exc.portfolio_id == "PORT-001"
        assert "limit exceeded" in exc.message.lower()
    
    def test_service_unavailable_error(self):
        """Test ServiceUnavailableError formatting."""
        exc = ServiceUnavailableError(
            service_name="NewsService",
            reason="Connection timeout"
        )
        
        assert exc.service_name == "NewsService"
        assert "unavailable" in exc.message.lower()
        assert "timeout" in exc.message.lower()
    
    def test_api_rate_limit_error(self):
        """Test APIRateLimitError with retry info."""
        exc = APIRateLimitError(
            api_name="AlphaVantage",
            retry_after_seconds=60.0
        )
        
        assert exc.api_name == "AlphaVantage"
        assert exc.retry_after_seconds == 60.0
        assert exc.error_code == "RATE_LIMIT_EXCEEDED"


# ==================== Retry Policy Tests ====================

class TestRetryPolicy:
    """Tests for retry policy and decorator."""
    
    def test_retry_policy_calculation(self):
        """Test exponential backoff calculation."""
        policy = RetryPolicy(
            max_attempts=3,
            base_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0,
            jitter=False
        )
        
        # First retry: 1.0 * 2^0 = 1.0
        assert policy.calculate_delay(1) == 1.0
        # Second retry: 1.0 * 2^1 = 2.0
        assert policy.calculate_delay(2) == 2.0
        # Third retry: 1.0 * 2^2 = 4.0
        assert policy.calculate_delay(3) == 4.0
    
    def test_retry_policy_caps_at_max_delay(self):
        """Test delay is capped at max_delay."""
        policy = RetryPolicy(
            max_attempts=5,
            base_delay=1.0,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=False
        )
        
        # All delays should be capped at 5.0
        assert policy.calculate_delay(1) == 1.0
        assert policy.calculate_delay(2) == 2.0
        assert policy.calculate_delay(3) == 4.0
        assert policy.calculate_delay(4) == 5.0  # capped
        assert policy.calculate_delay(5) == 5.0  # capped
    
    def test_retry_policy_with_jitter(self):
        """Test jitter is added to delays."""
        policy = RetryPolicy(
            base_delay=1.0,
            jitter=True,
            jitter_factor=0.1
        )
        
        delays = [policy.calculate_delay(1) for _ in range(10)]
        
        # With jitter, delays should vary
        assert len(set(delays)) > 1
        # All should be within reasonable range
        for delay in delays:
            assert 0.9 <= delay <= 1.1
    
    def test_should_retry_respects_max_attempts(self):
        """Test should_retry returns False after max_attempts."""
        policy = RetryPolicy(max_attempts=3)
        
        assert policy.should_retry(Exception("test"), 1) is True
        assert policy.should_retry(Exception("test"), 2) is True
        assert policy.should_retry(Exception("test"), 3) is False
    
    def test_retry_decorator_success(self):
        """Test retry decorator succeeds without exception."""
        call_count = 0
        
        @retry(max_attempts=3, base_delay=0.1)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = successful_func()
        
        assert result == "success"
        assert call_count == 1
    
    def test_retry_decorator_retries_on_failure(self):
        """Test retry decorator retries on recoverable failure."""
        call_count = 0
        
        @retry(max_attempts=3, base_delay=0.1, retryable_exceptions=(ValueError,))
        def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success after retry"
        
        result = failing_func()
        
        assert result == "success after retry"
        assert call_count == 3
    
    def test_retry_decorator_raises_after_max_attempts(self):
        """Test retry decorator raises after max_attempts exhausted."""
        call_count = 0
        
        @retry(max_attempts=3, base_delay=0.1)
        def always_failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Permanent error")
        
        with pytest.raises(ValueError):
            always_failing_func()
        
        assert call_count == 3
    
    def test_retry_decorator_async(self):
        """Test retry decorator works with async functions."""
        call_count = 0
        
        @retry(max_attempts=3, base_delay=0.1)
        async def async_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Temporary")
            return "success"
        
        result = asyncio.run(async_func())
        
        assert result == "success"
        assert call_count == 2


# ==================== Circuit Breaker Tests ====================

class TestCircuitBreaker:
    """Tests for circuit breaker implementation."""
    
    def test_circuit_starts_closed(self):
        """Test circuit breaker starts in closed state."""
        cb = CircuitBreaker("test_service")
        
        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed
        assert not cb.is_open
    
    def test_circuit_opens_after_failures(self):
        """Test circuit opens after reaching failure threshold."""
        cb = CircuitBreaker(
            "test_service",
            config=CircuitBreakerConfig(failure_threshold=3)
        )
        
        # Record failures
        cb.record_failure()
        cb.record_failure()
        
        assert cb.state == CircuitState.CLOSED  # Not yet at threshold
        
        cb.record_failure()  # Third failure
        
        assert cb.state == CircuitState.OPEN
        assert cb.is_open
    
    def test_circuit_resets_on_success(self):
        """Test success resets failure counter in closed state."""
        cb = CircuitBreaker(
            "test_service",
            config=CircuitBreakerConfig(failure_threshold=3)
        )
        
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()  # Circuit now open
        
        # If we succeed in half-open, it should close
        # But we need to transition to half-open first by waiting for timeout
        cb._last_failure_time = time.monotonic() - cb.config.timeout - 1
        cb._transition_to(CircuitState.HALF_OPEN)
        
        cb.record_success()
        cb.record_success()  # success_threshold = 2
        
        assert cb.state == CircuitState.CLOSED
    
    def test_circuit_rejects_when_open(self):
        """Test circuit rejects requests when open."""
        cb = CircuitBreaker(
            "test_service",
            config=CircuitBreakerConfig(failure_threshold=2, timeout=30)
        )
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        
        assert cb.is_open
        assert not cb.can_execute()
    
    def test_circuit_half_open_allows_limited_requests(self):
        """Test circuit half-open state allows limited requests."""
        cb = CircuitBreaker(
            "test_service",
            config=CircuitBreakerConfig(
                failure_threshold=2,
                timeout=0.1,  # Very short for testing
                half_open_max_calls=2
            )
        )
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        
        # Wait for timeout
        time.sleep(0.2)
        
        # Should transition to half-open
        assert cb.is_half_open
        
        # Should allow up to half_open_max_calls
        assert cb.can_execute()  # First call
        assert cb.can_execute()  # Second call
        assert not cb.can_execute()  # Third should be rejected
    
    def test_circuit_stats(self):
        """Test circuit breaker statistics."""
        cb = CircuitBreaker("test_service")
        
        cb.record_success()
        cb.record_success()
        cb.record_failure()
        
        stats = cb.get_stats()
        
        assert stats["name"] == "test_service"
        assert stats["total_calls"] == 3
        assert stats["total_successes"] == 2
        assert stats["total_failures"] == 1
        assert stats["failure_count"] == 1
    
    def test_circuit_breaker_decorator(self):
        """Test circuit breaker decorator."""
        cb = get_circuit_breaker("decorated_service")
        
        call_count = 0
        
        @cb
        def func_that_succeeds():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = func_that_succeeds()
        
        assert result == "success"
        assert call_count == 1
    
    def test_circuit_breaker_decorator_opens_on_error(self):
        """Test circuit breaker opens when wrapped function fails."""
        cb = get_circuit_breaker("decorated_failing_service", CircuitBreakerConfig(failure_threshold=2))
        
        call_count = 0
        
        @cb
        def func_that_fails():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError("Temporary")
            return "success"
        
        # Should retry twice, then fail
        with pytest.raises(ValueError):
            func_that_fails()
        
        assert call_count == 2  # Stopped at threshold


# ==================== Rate Limiter Tests ====================

class TestTokenBucketRateLimiter:
    """Tests for token bucket rate limiter."""
    
    def test_token_bucket_acquire(self):
        """Test token bucket allows requests when tokens available."""
        limiter = TokenBucketRateLimiter(rate=10.0, capacity=5)
        
        # Should be able to acquire up to capacity
        for i in range(5):
            assert limiter.acquire(1) is True
        
        # Should fail when exhausted
        assert limiter.acquire(1) is False
    
    def test_token_bucket_refills(self):
        """Test token bucket refills over time."""
        limiter = TokenBucketRateLimiter(rate=100.0, capacity=1)
        
        # Exhaust the bucket
        assert limiter.acquire(1) is True
        assert limiter.acquire(1) is False
        
        # Wait for refill
        time.sleep(0.05)  # Should get ~5 tokens
        
        assert limiter.available_tokens > 0
    
    def test_token_bucket_burst(self):
        """Test token bucket allows burst."""
        limiter = TokenBucketRateLimiter(rate=1.0, capacity=10)
        
        # Should allow burst up to capacity
        for _ in range(10):
            assert limiter.acquire(1) is True


class TestSlidingWindowRateLimiter:
    """Tests for sliding window rate limiter."""
    
    def test_sliding_window_allows_within_limit(self):
        """Test sliding window allows requests within limit."""
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=1.0)
        
        assert limiter.acquire() is True
        assert limiter.acquire() is True
        assert limiter.acquire() is True
        assert limiter.acquire() is False
    
    def test_sliding_window_resets_after_window(self):
        """Test sliding window resets after window expires."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.1)
        
        assert limiter.acquire() is True
        assert limiter.acquire() is True
        assert limiter.acquire() is False
        
        # Wait for window to expire
        time.sleep(0.15)
        
        assert limiter.acquire() is True


class TestRateLimiter:
    """Tests for unified rate limiter."""
    
    def test_rate_limiter_blocks_when_limited(self):
        """Test rate limiter blocks when limit exceeded."""
        config = RateLimitConfig(
            requests_per_second=1.0,
            burst_size=1,
            block_duration=0.5
        )
        limiter = RateLimiter("test_limiter", config)
        
        # First request should succeed
        assert limiter.acquire() is True
        
        # Second request should fail (burst exhausted)
        assert limiter.acquire() is False
    
    def test_rate_limiter_unblocks_after_duration(self):
        """Test rate limiter unblocks after block duration."""
        config = RateLimitConfig(
            requests_per_second=1.0,
            burst_size=1,
            block_duration=0.1
        )
        limiter = RateLimiter("test_limiter", config)
        
        # Exhaust and get blocked
        limiter.acquire()
        limiter.acquire()  # Should block
        
        # Wait for block duration
        time.sleep(0.15)
        
        # Should be able to acquire again
        assert limiter.acquire() is True


# ==================== Registry Tests ====================

class TestRegistries:
    """Tests for service registries."""
    
    def test_circuit_breaker_registry_singleton(self):
        """Test circuit breaker registry is singleton."""
        registry1 = CircuitBreakerRegistry()
        registry2 = CircuitBreakerRegistry()
        
        assert registry1 is registry2
    
    def test_get_or_create_circuit_breaker(self):
        """Test getting or creating circuit breaker."""
        cb = get_circuit_breaker("test_registry_service")
        
        assert cb is not None
        assert cb.name == "test_registry_service"
        
        # Getting same name returns same instance
        cb2 = get_circuit_breaker("test_registry_service")
        assert cb is cb2
    
    def test_get_circuit_breaker_stats(self):
        """Test getting stats from registry."""
        get_circuit_breaker("stats_test_service")
        
        stats = CircuitBreakerRegistry().get_all_stats()
        
        assert "stats_test_service" in stats


# ==================== Integration Tests ====================

class TestEnterpriseIntegration:
    """Integration tests for enterprise components."""
    
    def test_combined_retry_and_circuit_breaker(self):
        """Test retry and circuit breaker working together."""
        cb = get_circuit_breaker("combined_service", CircuitBreakerConfig(failure_threshold=5))
        
        call_count = 0
        
        @cb
        @retry(max_attempts=3, base_delay=0.1)
        def combined_func():
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise ValueError("Temporary")
            return "success"
        
        # Should eventually succeed with retries
        result = combined_func()
        assert result == "success"
        assert call_count == 4
    
    def test_circuit_breaker_prevents_further_calls_when_open(self):
        """Test circuit breaker prevents calls when open."""
        cb = get_circuit_breaker("prevent_test", CircuitBreakerConfig(failure_threshold=2))
        
        call_count = 0
        
        @cb
        def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Error")
        
        # First two calls should fail and open circuit
        try:
            failing_func()
        except ValueError:
            pass
        
        try:
            failing_func()
        except ValueError:
            pass
        
        # Circuit should now be open
        assert cb.is_open
        
        # Further calls should be rejected without executing
        try:
            failing_func()
        except Exception as e:
            # Should be CircuitBreakerOpenError
            assert "Circuit breaker open" in str(e) or "CIRCUIT_BREAKER_OPEN" in str(e)
        
        # But the function should NOT have been called again
        # (circuit breaker rejected before function was called)
        assert call_count == 2