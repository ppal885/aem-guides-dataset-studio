"""Structured logging support with JSON formatting and context."""
import json
import logging
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar
from uuid import uuid4

REQUEST_ID_CONTEXT: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
USER_ID_CONTEXT: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
CORRELATION_ID_CONTEXT: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class StructuredJSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def __init__(self, include_extra_fields: bool = True):
        """
        Initialize JSON formatter.
        
        Args:
            include_extra_fields: Whether to include extra fields from log record
        """
        super().__init__()
        self.include_extra_fields = include_extra_fields
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        
        Args:
            record: Log record to format
            
        Returns:
            JSON string representation of log entry
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        request_id = REQUEST_ID_CONTEXT.get()
        if request_id:
            log_data["request_id"] = request_id
        
        user_id = USER_ID_CONTEXT.get()
        if user_id:
            log_data["user_id"] = user_id
        
        correlation_id = CORRELATION_ID_CONTEXT.get()
        if correlation_id:
            log_data["correlation_id"] = correlation_id
        
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info) if record.exc_info else None,
            }
        
        if self.include_extra_fields and hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)
        
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        
        if hasattr(record, "status_code"):
            log_data["status_code"] = record.status_code
        
        return json.dumps(log_data, default=str, ensure_ascii=False)


class StructuredLoggerAdapter(logging.LoggerAdapter):
    """Adapter for structured logging with context support."""
    
    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        """
        Initialize structured logger adapter.
        
        Args:
            logger: Base logger instance
            extra: Additional context to include in all log entries
        """
        super().__init__(logger, extra or {})
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """
        Process log message and add structured context.
        
        Args:
            msg: Log message
            kwargs: Additional keyword arguments
            
        Returns:
            Tuple of (message, kwargs)
        """
        extra_fields = kwargs.pop("extra_fields", {})
        
        if not hasattr(self, "extra") or not self.extra:
            self.extra = {}
        
        combined_extra = {**self.extra, **extra_fields}
        
        if combined_extra:
            kwargs["extra"] = {"extra_fields": combined_extra}
        
        return msg, kwargs
    
    def log_with_context(
        self,
        level: int,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Log message with structured context fields.
        
        Args:
            level: Log level
            message: Log message
            extra_fields: Additional structured fields to include
            **kwargs: Additional arguments passed to logger
        """
        if extra_fields:
            kwargs["extra_fields"] = extra_fields
        self.log(level, message, **kwargs)
    
    def info_structured(
        self,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Log info message with structured fields."""
        self.log_with_context(logging.INFO, message, extra_fields, **kwargs)
    
    def debug_structured(
        self,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Log debug message with structured fields."""
        self.log_with_context(logging.DEBUG, message, extra_fields, **kwargs)
    
    def warning_structured(
        self,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Log warning message with structured fields."""
        self.log_with_context(logging.WARNING, message, extra_fields, **kwargs)
    
    def error_structured(
        self,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
        **kwargs
    ):
        """Log error message with structured fields."""
        if exc_info:
            kwargs["exc_info"] = True
        self.log_with_context(logging.ERROR, message, extra_fields, **kwargs)
    
    def critical_structured(
        self,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
        **kwargs
    ):
        """Log critical message with structured fields."""
        if exc_info:
            kwargs["exc_info"] = True
        self.log_with_context(logging.CRITICAL, message, extra_fields, **kwargs)


class LoggingContext:
    """Context manager for setting logging context."""
    
    def __init__(
        self,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        correlation_id: Optional[str] = None
    ):
        """
        Initialize logging context.
        
        Args:
            request_id: Request identifier
            user_id: User identifier
            correlation_id: Correlation identifier for tracing
        """
        self.request_id = request_id or str(uuid4())
        self.user_id = user_id
        self.correlation_id = correlation_id or str(uuid4())
        self._request_token = None
        self._user_token = None
        self._correlation_token = None
    
    def __enter__(self):
        """Enter context and set context variables."""
        self._request_token = REQUEST_ID_CONTEXT.set(self.request_id)
        if self.user_id:
            self._user_token = USER_ID_CONTEXT.set(self.user_id)
        self._correlation_token = CORRELATION_ID_CONTEXT.set(self.correlation_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and reset context variables."""
        if self._request_token:
            REQUEST_ID_CONTEXT.reset(self._request_token)
        if self._user_token:
            USER_ID_CONTEXT.reset(self._user_token)
        if self._correlation_token:
            CORRELATION_ID_CONTEXT.reset(self._correlation_token)
        return False


def get_structured_logger(name: str, extra: Optional[Dict[str, Any]] = None) -> StructuredLoggerAdapter:
    """
    Get a structured logger adapter instance.
    
    Args:
        name: Logger name (usually __name__)
        extra: Additional context to include in all log entries
        
    Returns:
        StructuredLoggerAdapter instance
    """
    base_logger = logging.getLogger(f"app.{name}")
    return StructuredLoggerAdapter(base_logger, extra)
