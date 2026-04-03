# Structured Logging Guide

This document describes the structured logging implementation in the AEM Guides Dataset Studio backend.

## Overview

Structured logging outputs logs in JSON format, making them easier to parse, search, and analyze. Each log entry includes:

- **Timestamp**: ISO 8601 format with UTC timezone
- **Level**: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **Logger**: Logger name (module path)
- **Message**: Human-readable log message
- **Context**: Request ID, User ID, Correlation ID (when available)
- **Structured Fields**: Additional key-value pairs for context
- **Exception Info**: Stack traces for errors (when applicable)

## Enabling Structured Logging

Structured logging can be enabled via environment variable:

```bash
# Enable structured logging
export STRUCTURED_LOGGING=true

# Or disable it (default)
export STRUCTURED_LOGGING=false
```

When enabled, logs are written to:
- `logs/app.json.log` - All application logs (JSON format)
- `logs/error.json.log` - Error logs only (JSON format)

When disabled, logs use the traditional text format:
- `logs/app.log` - All application logs (text format)
- `logs/error.log` - Error logs only (text format)

## Usage

### Basic Usage

```python
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# Simple logging (works with both structured and unstructured)
logger.info("Operation completed")

# Structured logging with extra fields
logger.info_structured(
    "User logged in",
    extra_fields={
        "user_id": user.id,
        "ip_address": request.client.host,
        "user_agent": request.headers.get("user-agent")
    }
)
```

### Logging Methods

The structured logger provides several methods:

- `logger.info_structured(message, extra_fields={}, **kwargs)` - Info level with structured fields
- `logger.debug_structured(message, extra_fields={}, **kwargs)` - Debug level with structured fields
- `logger.warning_structured(message, extra_fields={}, **kwargs)` - Warning level with structured fields
- `logger.error_structured(message, extra_fields={}, exc_info=False, **kwargs)` - Error level with structured fields
- `logger.critical_structured(message, extra_fields={}, exc_info=False, **kwargs)` - Critical level with structured fields

### Context Management

The logging system automatically includes request context when available:

- **Request ID**: Automatically generated or from `X-Request-ID` header
- **User ID**: Extracted from authenticated user context
- **Correlation ID**: Generated for request tracing

You can also manually set context using the `LoggingContext` context manager:

```python
from app.core.structured_logging import LoggingContext

with LoggingContext(request_id="req-123", user_id="user-456"):
    logger.info_structured("Processing request")
    # All logs within this context will include request_id and user_id
```

## Example Log Output

### Structured (JSON) Format

```json
{
  "timestamp": "2026-01-25T10:30:45.123Z",
  "level": "INFO",
  "logger": "app.api.v1.routes.bulk",
  "message": "Bulk job creation completed",
  "module": "bulk",
  "function": "create_bulk_jobs",
  "line": 112,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-123",
  "correlation_id": "corr-789",
  "created": 5,
  "failed": 0,
  "total": 5
}
```

### Traditional (Text) Format

```
2026-01-25 10:30:45 - app.api.v1.routes.bulk - INFO - Bulk job creation completed: 5 created, 0 failed
```

## Benefits

1. **Machine Readable**: JSON format is easy to parse programmatically
2. **Searchable**: Structured fields enable efficient searching and filtering
3. **Contextual**: Request/user context automatically included
4. **Traceable**: Correlation IDs enable request tracing across services
5. **Analyzable**: Structured data enables log analytics and monitoring

## Integration with Log Aggregation Tools

Structured logging works seamlessly with log aggregation tools:

- **ELK Stack (Elasticsearch, Logstash, Kibana)**: JSON logs can be directly indexed
- **Splunk**: JSON format enables efficient field extraction
- **CloudWatch Logs**: AWS CloudWatch supports JSON log parsing
- **Datadog**: Automatic JSON parsing and field extraction
- **Grafana Loki**: JSON logs enable efficient querying

## Best Practices

1. **Use structured fields for important context**:
   ```python
   logger.info_structured(
       "Job created",
       extra_fields={
           "job_id": job.id,
           "user_id": user.id,
           "job_type": "dataset_generation"
       }
   )
   ```

2. **Include error context**:
   ```python
   logger.error_structured(
       "Failed to process request",
       extra_fields={
           "error_type": type(e).__name__,
           "error_message": str(e),
           "request_path": request.url.path
       },
       exc_info=True
   )
   ```

3. **Don't duplicate information**: The message should be human-readable, while structured fields provide machine-readable context.

4. **Use appropriate log levels**:
   - DEBUG: Detailed diagnostic information
   - INFO: General informational messages
   - WARNING: Warning messages that don't prevent operation
   - ERROR: Error conditions that prevent specific operations
   - CRITICAL: Critical errors that may cause application failure

## Migration from Traditional Logging

Existing code using `get_logger()` will continue to work. To migrate to structured logging:

1. Replace `get_logger()` with `get_structured_logger()`
2. Replace string formatting with `extra_fields`:
   ```python
   # Before
   logger.info(f"Creating job for user {user.id}")
   
   # After
   logger.info_structured(
       "Creating job",
       extra_fields={"user_id": user.id}
   )
   ```
3. Use structured methods for important operations
4. Keep simple logging for trivial messages

## Environment Variables

- `STRUCTURED_LOGGING`: Enable/disable structured logging (default: `false`)
- `LOG_LEVEL`: Set log level (default: `INFO`)

## Files

- `app/core/structured_logging.py`: Structured logging implementation
- `app/core/logging_config.py`: Logging configuration
- `logs/app.json.log`: Structured application logs (when enabled)
- `logs/error.json.log`: Structured error logs (when enabled)
