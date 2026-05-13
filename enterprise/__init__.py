# enterprise/__init__.py
"""
Enterprise features for the GreekNN Risk System.

Provides enterprise-grade components for building robust, production-ready systems:
- Exception hierarchy for precise error handling
- Retry logic with exponential backoff and jitter
- Circuit breaker pattern for fault tolerance
- Rate limiting for resource management

Usage:
    from enterprise import CircuitBreaker, RetryPolicy, rate_limit
    
    @circuit_breaker(name="external_api")
    @retry(policy_name="external_api")
    def call_api():
        ...
"""

from enterprise.exceptions import (
    GreekNNException,
    ConfigurationError,
    EnvironmentError,
    ValidationError,
    DataError,
    SchemaValidationError,
    ModelError,
    ModelNotFoundError,
    ModelLoadError,
    PredictionError,
    ServiceError,
    ServiceUnavailableError,
    ServiceTimeoutError,
    CircuitBreakerOpenError,
    ExternalAPIError,
    APIRateLimitError,
    APIAuthenticationError,
    APIResponseError,
    RiskCalculationError,
    RiskLimitExceededError,
    VolSurfaceError,
    VolSurfaceNotFoundError,
    PortfolioError,
    PortfolioNotFoundError,
    PositionNotFoundError,
    AlertError,
    AlertNotFoundError,
    AuditError,
    TraceNotFoundError,
)

from enterprise.retry import (
    RetryPolicy,
    RetryContext,
    RETRY_POLICIES,
    retry,
    retry_async,
)

from enterprise.circuit_breaker import (
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreaker,
    CircuitBreakerRegistry,
    get_circuit_breaker,
    circuit_breaker,
    registry as circuit_breaker_registry,
)

from enterprise.rate_limiter import (
    RateLimitStrategy,
    RateLimitConfig,
    TokenBucketRateLimiter,
    SlidingWindowRateLimiter,
    RateLimiter,
    RateLimiterRegistry,
    get_rate_limiter,
    rate_limit,
    registry as rate_limiter_registry,
)

__all__ = [
    # Exceptions
    "GreekNNException",
    "ConfigurationError",
    "EnvironmentError",
    "ValidationError",
    "DataError",
    "SchemaValidationError",
    "ModelError",
    "ModelNotFoundError",
    "ModelLoadError",
    "PredictionError",
    "ServiceError",
    "ServiceUnavailableError",
    "ServiceTimeoutError",
    "CircuitBreakerOpenError",
    "ExternalAPIError",
    "APIRateLimitError",
    "APIAuthenticationError",
    "APIResponseError",
    "RiskCalculationError",
    "RiskLimitExceededError",
    "VolSurfaceError",
    "VolSurfaceNotFoundError",
    "PortfolioError",
    "PortfolioNotFoundError",
    "PositionNotFoundError",
    "AlertError",
    "AlertNotFoundError",
    "AuditError",
    "TraceNotFoundError",
    # Retry
    "RetryPolicy",
    "RetryContext",
    "RETRY_POLICIES",
    "retry",
    "retry_async",
    # Circuit Breaker
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "get_circuit_breaker",
    "circuit_breaker",
    "circuit_breaker_registry",
    # Rate Limiter
    "RateLimitStrategy",
    "RateLimitConfig",
    "TokenBucketRateLimiter",
    "SlidingWindowRateLimiter",
    "RateLimiter",
    "RateLimiterRegistry",
    "get_rate_limiter",
    "rate_limit",
    "rate_limiter_registry",
]