# enterprise/exceptions.py
"""
Enterprise exception classes for the GreekNN Risk System.

Provides a hierarchical exception structure for precise error handling
and categorization across all system components.
"""

from typing import Optional, Dict, Any


class GreekNNException(Exception):
    """
    Base exception for all GreekNN system exceptions.
    
    All custom exceptions should inherit from this class to ensure
    proper exception hierarchy and consistent error handling.
    """
    
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "GREEK_NN_ERROR"
        self.details = details or {}
        self.cause = cause
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        result = {
            "error_code": self.error_code,
            "message": self.message
        }
        if self.details:
            result["details"] = self.details
        if self.cause:
            result["cause"] = str(self.cause)
        return result


# ==================== Configuration Exceptions ====================

class ConfigurationError(GreekNNException):
    """Raised when configuration is invalid or missing."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="CONFIG_ERROR", **kwargs)


class EnvironmentError(ConfigurationError):
    """Raised when environment configuration is invalid."""
    pass


class ValidationError(ConfigurationError):
    """Raised when configuration validation fails."""
    pass


# ==================== Data/Model Exceptions ====================

class DataError(GreekNNException):
    """Base class for data-related errors."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="DATA_ERROR", **kwargs)


class SchemaValidationError(DataError):
    """Raised when data fails schema validation."""
    
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.error_code = "SCHEMA_VALIDATION_ERROR"
        self.field = field


class ModelError(GreekNNException):
    """Base class for model-related errors."""
    
    def __init__(self, message: str, model_name: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="MODEL_ERROR", **kwargs)
        self.model_name = model_name


class ModelNotFoundError(ModelError):
    """Raised when a required model cannot be found."""
    
    def __init__(self, model_path: str, **kwargs):
        super().__init__(f"Model not found: {model_path}", model_name=model_path, **kwargs)
        self.error_code = "MODEL_NOT_FOUND"
        self.model_path = model_path


class ModelLoadError(ModelError):
    """Raised when a model fails to load."""
    
    def __init__(self, model_path: str, cause: Optional[Exception] = None, **kwargs):
        super().__init__(f"Failed to load model: {model_path}", model_name=model_path, cause=cause, **kwargs)
        self.error_code = "MODEL_LOAD_ERROR"


class PredictionError(ModelError):
    """Raised when model prediction fails."""
    
    def __init__(self, message: str, model_name: Optional[str] = None, **kwargs):
        super().__init__(message, model_name=model_name, **kwargs)
        self.error_code = "PREDICTION_ERROR"


# ==================== Service Exceptions ====================

class ServiceError(GreekNNException):
    """Base class for service-related errors."""
    
    def __init__(self, message: str, service_name: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="SERVICE_ERROR", **kwargs)
        self.service_name = service_name


class ServiceUnavailableError(ServiceError):
    """Raised when a required service is unavailable."""
    
    def __init__(self, service_name: str, reason: Optional[str] = None, **kwargs):
        super().__init__(
            f"Service unavailable: {service_name}" + (f" - {reason}" if reason else ""),
            service_name=service_name,
            **kwargs
        )
        self.error_code = "SERVICE_UNAVAILABLE"


class ServiceTimeoutError(ServiceError):
    """Raised when a service operation times out."""
    
    def __init__(self, service_name: str, timeout_seconds: float, **kwargs):
        super().__init__(
            f"Service timeout: {service_name} after {timeout_seconds}s",
            service_name=service_name,
            **kwargs
        )
        self.error_code = "SERVICE_TIMEOUT"
        self.timeout_seconds = timeout_seconds


class CircuitBreakerOpenError(ServiceError):
    """Raised when circuit breaker is open and request cannot proceed."""
    
    def __init__(
        self, 
        service_name: str, 
        failure_reason: Optional[str] = None,
        retry_after_seconds: Optional[float] = None,
        **kwargs
    ):
        super().__init__(
            f"Circuit breaker open for {service_name}" + 
            (f": {failure_reason}" if failure_reason else ""),
            service_name=service_name,
            **kwargs
        )
        self.error_code = "CIRCUIT_BREAKER_OPEN"
        self.retry_after_seconds = retry_after_seconds


# ==================== External API Exceptions ====================

class ExternalAPIError(GreekNNException):
    """Base class for external API errors."""
    
    def __init__(self, message: str, api_name: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="EXTERNAL_API_ERROR", **kwargs)
        self.api_name = api_name


class APIRateLimitError(ExternalAPIError):
    """Raised when API rate limit is exceeded."""
    
    def __init__(
        self, 
        api_name: str, 
        retry_after_seconds: Optional[float] = None,
        **kwargs
    ):
        super().__init__(
            f"Rate limit exceeded for {api_name}",
            api_name=api_name,
            **kwargs
        )
        self.error_code = "RATE_LIMIT_EXCEEDED"
        self.retry_after_seconds = retry_after_seconds


class APIAuthenticationError(ExternalAPIError):
    """Raised when API authentication fails."""
    
    def __init__(self, api_name: str, **kwargs):
        super().__init__(
            f"Authentication failed for {api_name}",
            api_name=api_name,
            **kwargs
        )
        self.error_code = "API_AUTH_FAILED"


class APIResponseError(ExternalAPIError):
    """Raised when API returns an unexpected response."""
    
    def __init__(self, api_name: str, status_code: int, response_body: Optional[str] = None, **kwargs):
        super().__init__(
            f"API {api_name} returned error status {status_code}",
            api_name=api_name,
            **kwargs
        )
        self.error_code = "API_RESPONSE_ERROR"
        self.status_code = status_code
        self.response_body = response_body


# ==================== Risk/Trading Exceptions ====================

class RiskCalculationError(GreekNNException):
    """Raised when risk calculation fails."""
    
    def __init__(self, message: str, portfolio_id: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="RISK_CALCULATION_ERROR", **kwargs)
        self.portfolio_id = portfolio_id


class RiskLimitExceededError(RiskCalculationError):
    """Raised when a risk limit is exceeded."""
    
    def __init__(
        self, 
        risk_type: str, 
        current_value: float, 
        limit_value: float,
        portfolio_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            f"Risk limit exceeded: {risk_type} = {current_value} (limit: {limit_value})",
            portfolio_id=portfolio_id,
            **kwargs
        )
        self.error_code = "RISK_LIMIT_EXCEEDED"
        self.risk_type = risk_type
        self.current_value = current_value
        self.limit_value = limit_value


class VolSurfaceError(GreekNNException):
    """Raised when there's an error with volatility surface operations."""
    
    def __init__(self, message: str, surface_id: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="VOL_SURFACE_ERROR", **kwargs)
        self.surface_id = surface_id


class VolSurfaceNotFoundError(VolSurfaceError):
    """Raised when a volatility surface cannot be found."""
    
    def __init__(self, surface_id: str, **kwargs):
        super().__init__(f"Vol surface not found: {surface_id}", surface_id=surface_id, **kwargs)
        self.error_code = "VOL_SURFACE_NOT_FOUND"


class PortfolioError(GreekNNException):
    """Raised when there's an error with portfolio operations."""
    
    def __init__(self, message: str, portfolio_id: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="PORTFOLIO_ERROR", **kwargs)
        self.portfolio_id = portfolio_id


class PortfolioNotFoundError(PortfolioError):
    """Raised when a portfolio cannot be found."""
    
    def __init__(self, portfolio_id: str, **kwargs):
        super().__init__(f"Portfolio not found: {portfolio_id}", portfolio_id=portfolio_id, **kwargs)
        self.error_code = "PORTFOLIO_NOT_FOUND"


class PositionNotFoundError(PortfolioError):
    """Raised when a position cannot be found."""
    
    def __init__(self, position_id: str, portfolio_id: Optional[str] = None, **kwargs):
        super().__init__(
            f"Position not found: {position_id}" + 
            (f" in portfolio {portfolio_id}" if portfolio_id else ""),
            portfolio_id=portfolio_id,
            **kwargs
        )
        self.error_code = "POSITION_NOT_FOUND"
        self.position_id = position_id


# ==================== Alert Exceptions ====================

class AlertError(GreekNNException):
    """Base class for alert-related errors."""
    
    def __init__(self, message: str, alert_id: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="ALERT_ERROR", **kwargs)
        self.alert_id = alert_id


class AlertNotFoundError(AlertError):
    """Raised when an alert cannot be found."""
    
    def __init__(self, alert_id: str, **kwargs):
        super().__init__(f"Alert not found: {alert_id}", alert_id=alert_id, **kwargs)
        self.error_code = "ALERT_NOT_FOUND"


# ==================== Audit/Compliance Exceptions ====================

class AuditError(GreekNNException):
    """Raised when audit logging fails."""
    
    def __init__(self, message: str, trace_id: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="AUDIT_ERROR", **kwargs)
        self.trace_id = trace_id


class TraceNotFoundError(AuditError):
    """Raised when an audit trace cannot be found."""
    
    def __init__(self, trace_id: str, **kwargs):
        super().__init__(f"Audit trace not found: {trace_id}", trace_id=trace_id, **kwargs)
        self.error_code = "TRACE_NOT_FOUND"
