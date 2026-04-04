import atexit
import os
import time
from functools import wraps
from typing import Generator, Callable, TypeVar, Any

from fastapi.exceptions import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from app.core.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar('T')

# SQLite file under backend/storage (local) or /app/data (Docker) when URL path is relative.
DEFAULT_SQLITE_URL = "sqlite:///storage/app.db"


def _backend_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _sqlite_file_path_from_url(database_url: str) -> tuple[str, str | None]:
    """Return (absolute_db_path, parent_dir_or_none)."""
    db_path = database_url.replace("sqlite:///", "").replace("sqlite://", "")
    if db_path == ":memory:":
        return ":memory:", None
    if not db_path.startswith("/") and not db_path.startswith("\\") and ":" not in db_path[:2]:
        if os.path.exists("/app"):
            base_dir = "/app/data"
        else:
            base_dir = _backend_root()
        db_path = os.path.join(base_dir, db_path)
        db_path = os.path.abspath(db_path)
        db_dir = os.path.dirname(db_path)
    else:
        db_dir = os.path.dirname(db_path) if os.path.dirname(db_path) else None
    return db_path, db_dir


def _ensure_sqlite_dir(db_dir: str | None) -> None:
    if not db_dir:
        return
    try:
        os.makedirs(db_dir, exist_ok=True)
        test_file = os.path.join(db_dir, ".write_test")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
        except OSError as e:
            logger.warning("Directory %s may not be writable: %s", db_dir, e)
    except OSError as e:
        logger.error("Failed to create database directory %s: %s", db_dir, e)
        raise


def _create_sqlite_engine(database_url: str) -> Engine:
    """Create SQLite engine with FK pragma and NullPool."""
    db_path, db_dir = _sqlite_file_path_from_url(database_url)
    if db_path != ":memory:":
        _ensure_sqlite_dir(db_dir)
        logger.info("SQLite database path: %s", db_path)
        connect_url = f"sqlite:///{db_path}"
    else:
        connect_url = "sqlite:///:memory:"
        logger.info("SQLite in-memory database")

    engine = create_engine(
        connect_url,
        connect_args={
            "check_same_thread": False,
            "timeout": 30.0,
        },
        poolclass=NullPool,
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_set_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def log_pool_status():
        try:
            pool = engine.pool
            if hasattr(pool, "size"):
                logger.debug(
                    "Database pool status - Size: %s, Checked out: %s, Overflow: %s, Checked in: %s",
                    pool.size(),
                    pool.checkedout(),
                    pool.overflow(),
                    pool.checkedin(),
                )
            else:
                logger.debug("Database pool monitoring not available for SQLite")
        except Exception as e:
            logger.debug("Could not log pool status: %s", e)

    atexit.register(log_pool_status)
    return engine


def _is_sqlite_url(url: str) -> bool:
    return url.strip().lower().startswith("sqlite")


def _postgres_engine_or_fallback(url: str) -> tuple[Engine, str]:
    """Build PostgreSQL engine; on missing driver or dialect errors, fall back to SQLite."""
    eng: Engine | None = None
    try:
        eng = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
        # Load dialect / DBAPI (e.g. psycopg2) without requiring a live server.
        _ = eng.dialect.name
        return eng, url
    except Exception as e:
        err = str(e).lower()
        if eng is not None:
            try:
                eng.dispose()
            except Exception:
                pass
        if (
            "psycopg2" in err
            or "psycopg" in err
            or "no module named" in err
            or isinstance(e, ImportError)
            or isinstance(e, ModuleNotFoundError)
        ):
            logger.warning(
                "DATABASE_URL points to PostgreSQL but the driver or engine setup failed (%s); "
                "falling back to SQLite (%s)",
                e,
                DEFAULT_SQLITE_URL,
            )
        else:
            logger.warning(
                "DATABASE_URL is not SQLite but engine creation failed (%s); falling back to SQLite (%s)",
                e,
                DEFAULT_SQLITE_URL,
            )
        return _create_sqlite_engine(DEFAULT_SQLITE_URL), DEFAULT_SQLITE_URL


# Resolve URL: unset -> default SQLite under storage/; PostgreSQL -> engine with fallback.
_raw_database_url = os.getenv("DATABASE_URL", "").strip()
if not _raw_database_url:
    DATABASE_URL = DEFAULT_SQLITE_URL
else:
    DATABASE_URL = _raw_database_url

logger.info(
    "Database URL: %s",
    DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL,
)

if _is_sqlite_url(DATABASE_URL):
    engine = _create_sqlite_engine(DATABASE_URL)
else:
    engine, DATABASE_URL = _postgres_engine_or_fallback(DATABASE_URL)
    if _is_sqlite_url(DATABASE_URL):
        logger.info(
            "Using SQLite after fallback: %s",
            DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL,
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
                            delay = min(base_delay * (2**attempt), max_delay)
                            logger.warning(
                                "Database lock detected in %s, retrying in %.2fs (attempt %s/%s)",
                                func.__name__,
                                delay,
                                attempt + 1,
                                max_attempts,
                            )
                            time.sleep(delay)
                            continue
                    raise
                except Exception as e:
                    raise

            if last_exception:
                logger.error(
                    "Database operation %s failed after %s attempts",
                    func.__name__,
                    max_attempts,
                    exc_info=True,
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
            logger.warning("Database lock detected, will retry on next operation: %s", e)
        if db:
            db.rollback()
        raise
    except HTTPException:
        if db:
            db.rollback()
        raise
    except Exception as e:
        logger.error("Database session error: %s", e, exc_info=True)
        if db:
            db.rollback()
        raise
    finally:
        if db:
            logger.debug("Closing database session")
            db.close()


db_session = get_db
