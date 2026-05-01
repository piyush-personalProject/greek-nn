# logger.py
"""
Structured logging with distributed tracing support.
Provides correlation IDs, context propagation, and modular trace hierarchy.

Usage:
    from logger import get_logger, log_entry_exit, TracedContext
    
    logger = get_logger(__name__)
    
    @log_entry_exit
    def my_function():
        logger.info("Processing", extra_fields={"key": "value"})
        
    with TracedContext("operation", entity_id="123") as ctx:
        ctx.log("Step 1 completed")
        # do work
"""

import logging
import json
import sys
import uuid
import functools
from typing import Any, Dict, Optional, Union, Callable
from datetime import datetime
from contextvars import ContextVar
from functools import wraps
import time
import threading
import asyncio

from config import config

# Thread-safe ID generation
_counter_lock = threading.Lock()
_counter = 0

def _get_next_counter() -> int:
    """Thread-safe counter for additional uniqueness."""
    global _counter
    with _counter_lock:
        _counter += 1
        return _counter


# Context variables for distributed tracing
_trace_id: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
_span_id: ContextVar[Optional[str]] = ContextVar('span_id', default=None)
_parent_span_id: ContextVar[Optional[str]] = ContextVar('parent_span_id', default=None)
_request_context: ContextVar[Dict[str, Any]] = ContextVar('request_context', default=None)


def generate_id() -> str:
    """Generate a short unique ID."""
    return uuid.uuid4().hex[:12]


def get_trace_id() -> Optional[str]:
    """Get current trace ID."""
    return _trace_id.get()


def get_span_id() -> Optional[str]:
    """Get current span ID."""
    return _span_id.get()


def get_request_context() -> Dict[str, Any]:
    """Get current request context."""
    ctx = _request_context.get()
    return ctx if ctx else {}


class StructuredLogRecord(logging.LogRecord):
    """Enhanced log record with tracing fields."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trace_id = _trace_id.get()
        self.span_id = _span_id.get()
        self.parent_span_id = _parent_span_id.get()
        self._context = _request_context.get() or {}


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging with trace context."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add trace context
        if hasattr(record, 'trace_id') and record.trace_id:
            log_data["trace_id"] = record.trace_id
        if hasattr(record, 'span_id') and record.span_id:
            log_data["span_id"] = record.span_id
        if hasattr(record, 'parent_span_id') and record.parent_span_id:
            log_data["parent_span_id"] = record.parent_span_id
            
        # Add request context (position_id, event_id, etc.)
        if hasattr(record, '_context') and record._context:
            log_data["context"] = record._context
            
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            log_data["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        
        return json.dumps(log_data, default=str)


class ColoredFormatter(logging.Formatter):
    """Colored formatter for development with trace context."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        
        # Build trace prefix
        trace_parts = []
        if hasattr(record, 'trace_id') and record.trace_id:
            trace_parts.append(f"[{record.trace_id[:8]}]")
        if hasattr(record, 'span_id') and record.span_id:
            trace_parts.append(f"[span:{record.span_id[:6]}]")
        
        trace_prefix = ' '.join(trace_parts) + " " if trace_parts else ""
        
        # Build context suffix
        context_str = ""
        if hasattr(record, '_context') and record._context:
            ctx = record._context
            ctx_parts = [f"{k}={v}" for k, v in ctx.items() if v is not None]
            if ctx_parts:
                context_str = " | " + " ".join(ctx_parts[:5])  # Limit context items
        
        return (
            f"{color}[{record.levelname}]{self.RESET}{trace_prefix}"
            f"{record.name}::{record.funcName}:{record.lineno} - "
            f"{record.getMessage()}{context_str}"
        )


def setup_logging() -> None:
    """Setup logging for the application."""
    # Create custom record factory
    logging.setLogRecordFactory(StructuredLogRecord)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(config.log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    
    if config.environment == "production":
        formatter = JSONFormatter()
    else:
        formatter = ColoredFormatter()
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


def get_logger(name: str) -> 'BoundLogger':
    """Get a bound logger instance with trace context support."""
    base_logger = logging.getLogger(name)
    return BoundLogger(base_logger)


class BoundLogger:
    """
    Logger wrapper that automatically includes trace context.
    Provides structured logging with correlation IDs.
    """
    
    def __init__(self, logger: logging.Logger):
        self._logger = logger
        self._module = logger.name.split('.')[-1] if '.' in logger.name else logger.name
    
    def _make_record(self, level: int, msg: str, *args, **kwargs) -> None:
        """Create a log record with context."""
        extra_fields = kwargs.pop('extra_fields', {})
        request_ctx = get_request_context()
        
        # Merge request context with extra fields
        context = {**request_ctx, **extra_fields}
        
        if context:
            record = self._logger.makeRecord(
                self._logger.name, level, "(unknown)", 0, msg, args, None
            )
            record._context = context
            self._logger.handle(record)
        else:
            self._logger.log(level, msg, *args, **kwargs)
    
    def debug(self, msg: str, *args, **kwargs) -> None:
        self._make_record(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs) -> None:
        self._make_record(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs) -> None:
        self._make_record(logging.WARNING, msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs) -> None:
        self._make_record(logging.ERROR, msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs) -> None:
        self._make_record(logging.CRITICAL, msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs) -> None:
        kwargs['exc_info'] = True
        self._make_record(logging.ERROR, msg, *args, **kwargs)
    
    def log(self, level: int, msg: str, *args, **kwargs) -> None:
        """Log at the specified level."""
        self._make_record(level, msg, *args, **kwargs)


class TracedContext:
    """
    Context manager for creating trace spans.
    Automatically propagates trace_id and records timing.
    Usage:
        with TracedContext("process_position", position_id="ABC123") as ctx:
            # work
            ctx.log("step completed")
    """
    
    def __init__(self, name: str, parent: Optional[str] = None, **context_kwargs):
        self.name = name
        self.parent = parent or get_span_id()
        self.context_kwargs = context_kwargs
        self.span_id = generate_id()
        self.start_time: Optional[datetime] = None
        self._bound_logger: Optional[BoundLogger] = None
        self._token = None
    
    def __enter__(self) -> 'TracedContext':
        self.start_time = datetime.utcnow()
        
        # Set context variables
        self._token = _span_id.set(self.span_id)
        if self.parent:
            _parent_span_id.set(self.parent)
        
        # Set request context
        current_ctx = get_request_context()
        new_ctx = {**current_ctx, **self.context_kwargs}
        _request_context.set(new_ctx)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration_ms = None
        if self.start_time:
            duration_ms = (datetime.utcnow() - self.start_time).total_seconds() * 1000
        
        if exc_type:
            log_level = logging.ERROR
            status = "error"
        else:
            log_level = logging.DEBUG
            status = "success"
        
        # Log span completion
        logger = get_logger("tracing")
        extra = {
            "span_name": self.name,
            "span_id": self.span_id,
            "status": status,
            "duration_ms": round(duration_ms, 2) if duration_ms else None,
            **self.context_kwargs
        }
        
        # Reset context
        if self._token:
            _span_id.reset(self._token)
        
        if exc_type:
            logger.error(
                f"Span '{self.name}' failed: {exc_val}",
                extra_fields=extra
            )
        else:
            logger.debug(
                f"Span '{self.name}' completed",
                extra_fields=extra
            )
    
    def log(self, msg: str, level: int = logging.INFO, **kwargs) -> None:
        """Log a message within this span context."""
        logger = get_logger(self.name)
        logger.log(
            level, msg,
            extra_fields={
                "span_id": self.span_id,
                "span_step": msg,
                **self.context_kwargs,
                **kwargs
            }
        )


class TraceManager:
    """
    Manages trace context for a request lifecycle.
    Provides methods to create child spans and propagate context.
    """
    
    def __init__(self, name: Optional[str] = None, trace_id: Optional[str] = None):
        self.name = name
        self.trace_id = trace_id or generate_id()
        self.spans: list = []
        self._token = None
    
    def __enter__(self) -> 'TraceManager':
        # Set trace ID
        self._token = _trace_id.set(self.trace_id)
        return self
    
    def __exit__(self, *args) -> None:
        if self._token:
            _trace_id.reset(self._token)
        self.spans.clear()
    
    def start_span(self, name: str, **context) -> TracedContext:
        """Start a new child span."""
        parent = get_span_id()
        span = TracedContext(name, parent=parent, **context)
        self.spans.append(span)
        return span
    
    def inject_context(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Inject trace context into headers for propagation."""
        headers['X-Trace-ID'] = self.trace_id
        return headers


def create_trace(name: Optional[str] = None, trace_id: Optional[str] = None) -> TraceManager:
    """Create a new trace context."""
    return TraceManager(name=name, trace_id=trace_id)


def log_entry_exit(func):
    """
    Decorator to automatically log function entry/exit with timing.
    
    Usage:
        @log_entry_exit
        def my_function(arg1, arg2):
            ...
    
    Note: Prefer using @log_performance decorator for better structured logging.
    """
    return log_performance(func.__name__)(func)


def log_async_entry_exit(func):
    """
    Decorator for async functions to log entry/exit with timing.
    
    Note: Prefer using @log_performance decorator for better structured logging.
    """
    return log_performance(func.__name__)(func)


# Additional context keys for common operations
class ContextKeys:
    """Standard context key names for consistent logging."""
    PORTFOLIO_ID = "portfolio_id"
    POSITION_ID = "position_id"
    EVENT_ID = "event_id"
    SHOCK_ID = "shock_id"
    TENOR = "tenor"
    INSTRUMENT = "instrument"
    USER_ID = "user_id"
    REQUEST_ID = "request_id"
    OPERATION = "operation"


class PerformanceLogger:
    """
    Context manager for logging operation performance.
    
    Usage:
        with PerformanceLogger("model_inference", logger) as perf:
            # do work
            perf.add_metric("input_size", len(data))
            
        # Automatically logs duration and any custom metrics
    """
    
    def __init__(
        self, 
        operation: str, 
        logger: 'BoundLogger' = None,
        **initial_metrics
    ):
        self.operation = operation
        self.logger = logger or get_logger("performance")
        self.metrics: Dict[str, Any] = dict(initial_metrics)
        self.start_time: float = time.monotonic()
        self._token = None
    
    def __enter__(self) -> 'PerformanceLogger':
        self.start_time = time.monotonic()
        self.logger.debug(
            f"START {self.operation}",
            extra_fields={"operation": self.operation, "status": "started"}
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.monotonic() - self.start_time) * 1000
        
        if exc_type:
            self.logger.error(
                f"FAIL {self.operation}: {exc_val}",
                extra_fields={
                    "operation": self.operation,
                    "duration_ms": round(duration_ms, 2),
                    "status": "error",
                    "error_type": exc_type.__name__,
                    **self.metrics
                }
            )
        else:
            self.logger.info(
                f"END {self.operation}",
                extra_fields={
                    "operation": self.operation,
                    "duration_ms": round(duration_ms, 2),
                    "status": "completed",
                    **self.metrics
                }
            )
    
    def add_metric(self, name: str, value: Any) -> None:
        """Add a metric to be logged at end of operation."""
        self.metrics[name] = value
    
    def add_metrics(self, **kwargs) -> None:
        """Add multiple metrics."""
        self.metrics.update(kwargs)


def log_performance(operation: str = None):
    """
    Decorator for automatic performance logging.
    
    Usage:
        @log_performance("database_query")
        def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation or func.__name__
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            start = time.monotonic()
            
            logger.debug(
                f"ENTRY {op_name}",
                extra_fields={
                    "function": op_name,
                    "args_count": len(args),
                    "kwargs_keys": list(kwargs.keys())
                }
            )
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.monotonic() - start) * 1000
                
                logger.info(
                    f"EXIT {op_name}",
                    extra_fields={
                        "function": op_name,
                        "duration_ms": round(duration_ms, 2),
                        "status": "success"
                    }
                )
                return result
            except Exception as e:
                duration_ms = (time.monotonic() - start) * 1000
                logger.error(
                    f"EXCEPTION {op_name}: {e}",
                    extra_fields={
                        "function": op_name,
                        "duration_ms": round(duration_ms, 2),
                        "status": "error",
                        "error_type": type(e).__name__
                    }
                )
                raise
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            start = time.monotonic()
            
            logger.debug(
                f"ENTRY {op_name}",
                extra_fields={
                    "function": op_name,
                    "args_count": len(args),
                    "kwargs_keys": list(kwargs.keys())
                }
            )
            
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.monotonic() - start) * 1000
                
                logger.info(
                    f"EXIT {op_name}",
                    extra_fields={
                        "function": op_name,
                        "duration_ms": round(duration_ms, 2),
                        "status": "success"
                    }
                )
                return result
            except Exception as e:
                duration_ms = (time.monotonic() - start) * 1000
                logger.error(
                    f"EXCEPTION {op_name}: {e}",
                    extra_fields={
                        "function": op_name,
                        "duration_ms": round(duration_ms, 2),
                        "status": "error",
                        "error_type": type(e).__name__
                    }
                )
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper


# Export for convenience
_tracer_instance = None

def get_tracer() -> TraceManager:
    """Get the trace manager instance for external use."""
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = TraceManager()
    return _tracer_instance
