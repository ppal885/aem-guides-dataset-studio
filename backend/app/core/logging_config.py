"""Logging configuration for the application."""
import logging
import os
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from backend.app.core.structured_logging import StructuredJSONFormatter

# Create logs directory if it doesn't exist
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Log file paths
LOG_FILE = LOG_DIR / "app.log"
ERROR_LOG_FILE = LOG_DIR / "error.log"
STRUCTURED_LOG_FILE = LOG_DIR / "app.json.log"
STRUCTURED_ERROR_LOG_FILE = LOG_DIR / "error.json.log"

# Log format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging(log_level: str = "INFO", structured: bool = None) -> logging.Logger:
    """
    Set up logging configuration for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        structured: Enable structured JSON logging. If None, reads from STRUCTURED_LOGGING env var
    
    Returns:
        Configured logger instance
    """
    if structured is None:
        structured = os.getenv("STRUCTURED_LOGGING", "false").lower() in ("true", "1", "yes")
    
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create root logger
    logger = logging.getLogger("app")
    logger.setLevel(numeric_level)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    if structured:
        json_formatter = StructuredJSONFormatter()
        
        # Console handler with JSON output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(json_formatter)
        logger.addHandler(console_handler)
        
        # Structured JSON file handler for all logs
        structured_file_handler = RotatingFileHandler(
            STRUCTURED_LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        structured_file_handler.setLevel(logging.DEBUG)
        structured_file_handler.setFormatter(json_formatter)
        logger.addHandler(structured_file_handler)
        
        # Structured JSON error file handler (only errors and above)
        structured_error_handler = RotatingFileHandler(
            STRUCTURED_ERROR_LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        structured_error_handler.setLevel(logging.ERROR)
        structured_error_handler.setFormatter(json_formatter)
        logger.addHandler(structured_error_handler)
        
        log_files = f"{STRUCTURED_LOG_FILE}, {STRUCTURED_ERROR_LOG_FILE}"
    else:
        # Console handler with formatted output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # File handler for all logs
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Error file handler (only errors and above)
        error_handler = RotatingFileHandler(
            ERROR_LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        logger.addHandler(error_handler)
        
        log_files = f"{LOG_FILE}, {ERROR_LOG_FILE}"
    
    # Set levels for third-party loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    logger.info(f"Logging configured. Log level: {log_level}, Structured: {structured}")
    logger.info(f"Log files: {log_files}")
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(f"app.{name}")
