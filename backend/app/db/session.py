import os
import time
from functools import wraps
from typing import Generator, Callable, TypeVar, Any

from fastapi.exceptions import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from app.core.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar('T')

# Use SQLite for local development, PostgreSQL for production
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./dataset_studio.db"  # SQLite for local development
)

logger.info(f"Database URL: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")

# SQLite doesn't support pool_size and max_overflow
if DATABASE_URL.startswith("sqlite"):
    # Extract file path from SQLite URL
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    
    # Handle different path formats
    if db_path == ":memory:":
        # In-memory database
        db_dir = None
    elif not db_path.startswith("/") and not db_path.startswith("\\") and ":" not in db_path[:2]:
        # Relative path - make it absolute
        # In Docker, use /app/data directory; locally use backend directory
        if os.path.exists("/app"):
            # Running in Docker
            base_dir = "/app/data"
        else:
            # Running locally
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        db_path = os.path.join(base_dir, db_path)
        db_path = os.path.abspath(db_path)
        db_dir = os.path.dirname(db_path)
    else:
        # Absolute path
        db_dir = os.path.dirname(db_path) if os.path.dirname(db_path) else None
    
    # Ensure directory exists and is writable
    if db_dir:
        try:
            os.makedirs(db_dir, exist_ok=True)
            # Test write permissions
            test_file = os.path.join(db_dir, ".write_test")
            try:
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
            except Exception as e:
                logger.warning(f"Directory {db_dir} may not be writable: {e}")
        except Exception as e:
            logger.error(f"Failed to create database directory {db_dir}: {e}")
            raise
    
    logger.info(f"SQLite database path: {db_path}")
    
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={
            "check_same_thread": False,  # Needed for SQLite with threads
            "timeout": 30.0,  # Increase timeout for locked database (30 seconds)
        },
        poolclass=NullPool,  # New connection per request; avoids QueuePool exhaustion with threads
        echo=False,  # Set to True for SQL query logging
    )
    
    def log_pool_status():
        """Log database connection pool status for monitoring."""
        try:
            pool = engine.pool
            if hasattr(pool, 'size'):
                logger.debug(
                    f"Database pool status - Size: {pool.size()}, "
                    f"Checked out: {pool.checkedout()}, "
                    f"Overflow: {pool.overflow()}, "
                    f"Checked in: {pool.checkedin()}"
                )
            else:
                logger.debug("Database pool monitoring not available for SQLite")
        except Exception as e:
            logger.debug(f"Could not log pool status: {e}")
    
    import atexit
    atexit.register(log_pool_status)
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def retry_db_operation(max_attempts: int = 3, base_delay: float = 0.1, max_delay: float = 2.0):
    """
    Decorator to retry database operations with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 0.1)
        max_delay: Maximum delay in seconds (default: 2.0)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    last_exception = e
                    error_str = str(e).lower()
                    if "locked" in error_str or "database is locked" in error_str:
                        if attempt < max_attempts - 1:
                            delay = min(base_delay * (2 ** attempt), max_delay)
                            logger.warning(
                                f"Database lock detected in {func.__name__}, "
                                f"retrying in {delay:.2f}s (attempt {attempt + 1}/{max_attempts})"
                            )
                            time.sleep(delay)
                            continue
                    raise
                except Exception as e:
                    raise
            
            if last_exception:
                logger.error(
                    f"Database operation {func.__name__} failed after {max_attempts} attempts",
                    exc_info=True
                )
                raise last_exception
            raise RuntimeError(f"Unexpected error in {func.__name__}")
        return wrapper
    return decorator


@retry_db_operation(max_attempts=3, base_delay=0.1, max_delay=2.0)
def _create_session() -> Session:
    """Create a new database session with retry logic."""
    return SessionLocal()


def get_db() -> Generator[Session, None, None]:
    """Get database session with retry logic for lock errors."""
    db = None
    try:
        db = _create_session()
        logger.debug("Database session created")
        yield db
    except OperationalError as e:
        error_str = str(e).lower()
        if "locked" in error_str or "database is locked" in error_str:
            logger.warning(f"Database lock detected, will retry on next operation: {e}")
        if db:
            db.rollback()
        raise
    except HTTPException:
        if db:
            db.rollback()
        raise
    except Exception as e:
        logger.error(f"Database session error: {e}", exc_info=True)
        if db:
            db.rollback()
        raise
    finally:
        if db:
            logger.debug("Closing database session")
            db.close()


db_session = get_db
