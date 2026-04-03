"""Main FastAPI application entry point."""
import os
from pathlib import Path

# Load .env: project root first, then backend (backend overrides). Matches MCP / common IDEs.
_backend_dir = Path(__file__).resolve().parent.parent
_project_root = _backend_dir.parent
if (_project_root / ".env").exists() or (_backend_dir / ".env").exists():
    from dotenv import load_dotenv

    for _env_path in (_project_root / ".env", _backend_dir / ".env"):
        if _env_path.exists():
            load_dotenv(_env_path, override=True, encoding="utf-8-sig")
import logging
import hashlib
import time
from typing import Dict, Tuple
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.responses import Response
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.api.v1.router import api_router as v1_router
from app.core.structured_logging import get_structured_logger, LoggingContext
from app.services.cleaning_service import clean_old_data

# Initialize structured logger
logger = get_structured_logger(__name__)

# Request deduplication cache: {request_hash: (status_code, headers, body_bytes, timestamp)}
_request_cache: Dict[str, Tuple[int, dict, bytes, float]] = {}
CACHE_TTL = 5.0  # Cache responses for 5 seconds
MAX_CACHE_BODY_SIZE = 1024 * 1024  # 1MB - skip caching larger responses

app = FastAPI(
    title="AEM Guides Dataset Studio API",
    description="API for generating and managing AEM Guides datasets",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request context and logging middleware
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Set up request context for structured logging."""
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    user_id = None
    
    try:
        if hasattr(request.state, "user") and request.state.user:
            user_id = getattr(request.state.user, "id", None)
    except Exception:
        pass
    
    with LoggingContext(request_id=request_id, user_id=user_id):
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

# Request deduplication middleware
# Body restoration: read body once, create Request with receive that returns cached body
# so FastAPI Body() and downstream handlers can read it.
@app.middleware("http")
async def deduplicate_requests(request: Request, call_next):
    """Deduplicate identical requests within a time window to prevent race conditions."""
    body = b""
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
        # Create new Request with receive that returns cached body (body restoration for FastAPI Body())
        async def cached_receive():
            return {"type": "http.request", "body": body}
        request = Request(request.scope, receive=cached_receive)

    # Build request hash (include body for POST/PUT/PATCH; large bodies get unique hash to skip deduplication)
    hash_input = f"{request.method}:{request.url.path}:{str(request.query_params)}"
    if body:
        if len(body) <= MAX_CACHE_BODY_SIZE:
            hash_input += f":{body!r}"
        else:
            hash_input += f":{uuid4()}"  # Unique per request - no deduplication for large bodies
    request_hash = hashlib.sha256(hash_input.encode()).hexdigest()

    # Never deduplicate or cache DELETE — avoids any chance of reusing a prior response for
    # session mutations (e.g. clear-all vs delete-one) if path normalization ever collides.
    # Skip all /api/v1/chat traffic: POST streams and PATCH edits must always hit handlers; caching
    # identical prompts or edits within the TTL caused wrong or 404-like behavior for clients.
    chat_path = str(request.url.path).startswith("/api/v1/chat")
    skip_dedup = request.method == "DELETE" or chat_path

    current_time = time.time()
    if not skip_dedup and request_hash in _request_cache:
        cached_status, cached_headers, cached_body, cache_time = _request_cache[request_hash]
        if current_time - cache_time < CACHE_TTL:
            logger.debug_structured(
                "Request deduplicated",
                extra_fields={
                    "method": request.method,
                    "path": str(request.url.path),
                    "deduplicated": True
                }
            )
            request_id = request.headers.get("X-Request-ID") or str(uuid4())
            headers = dict(cached_headers)
            headers["X-Request-ID"] = request_id
            return Response(content=cached_body, status_code=cached_status, headers=headers)
        else:
            del _request_cache[request_hash]
    
    start_time = time.time()
    try:
        logger.info_structured(
            "Incoming request",
            extra_fields={
                "method": request.method,
                "path": str(request.url.path),
                "client_host": request.client.host if request.client else None,
                "query_params": dict(request.query_params) if request.query_params else None
            }
        )
    except Exception:
        pass
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        if (
            not skip_dedup
            and response.status_code < 400
            and len(body) <= MAX_CACHE_BODY_SIZE
        ):
            headers = dict(response.headers)
            _request_cache[request_hash] = (response.status_code, headers, body, current_time)
            _cleanup_cache()

        try:
            logger.info_structured(
                "Request completed",
                extra_fields={
                    "method": request.method,
                    "path": str(request.url.path),
                    "status_code": response.status_code,
                    "duration_ms": round(process_time, 2)
                }
            )
        except Exception:
            pass
        return Response(content=body, status_code=response.status_code, headers=dict(response.headers))
    except Exception as e:
        process_time = (time.time() - start_time) * 1000
        try:
            logger.error_structured(
                "Request failed",
                extra_fields={
                    "method": request.method,
                    "path": str(request.url.path),
                    "duration_ms": round(process_time, 2),
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                },
                exc_info=True
            )
        except Exception:
            pass
        raise


def _cleanup_cache():
    """Remove expired cache entries."""
    current_time = time.time()
    expired_keys = [
        key for key, (_, _, _, cache_time) in _request_cache.items()
        if current_time - cache_time >= CACHE_TTL
    ]
    for key in expired_keys:
        del _request_cache[key]
    if expired_keys:
        logger.debug_structured(
            "Cache cleanup completed",
            extra_fields={"expired_entries": len(expired_keys)}
        )

# Request validation error handler (422)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors with detailed messages."""
    try:
        errors = []
        for error in exc.errors():
            field_path = " -> ".join(str(loc) for loc in error["loc"])
            error_msg = error.get("msg", "Validation error")
            error_type = error.get("type", "unknown")
            errors.append({
                "field": field_path,
                "message": error_msg,
                "type": error_type,
                "input": error.get("input")
            })
        
        logger.warning_structured(
            "Request validation failed",
            extra_fields={
                "method": request.method,
                "path": str(request.url.path),
                "error_count": len(errors),
                "errors": errors
            }
        )
    except Exception:
        pass
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": [
                {
                    "field": " -> ".join(str(loc) for loc in error["loc"]),
                    "message": error.get("msg", "Validation error"),
                    "type": error.get("type", "unknown")
                }
                for error in exc.errors()
            ]
        }
    )

# Global exception handler - must be last to catch all unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    from fastapi import HTTPException as FastAPIHTTPException
    
    # If it's already an HTTPException, let FastAPI handle it
    if isinstance(exc, FastAPIHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    try:
        logger.error_structured(
            "Unhandled exception",
            extra_fields={
                "method": request.method,
                "path": str(request.url.path),
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            },
            exc_info=True
        )
    except Exception:
        pass
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

# Include API router
try:
    logger.info_structured("Registering API routes", extra_fields={"router": "v1"})
except Exception:
    print("Registering API routes...")
app.include_router(v1_router, prefix="/api/v1")
try:
    logger.info_structured("API routes registered successfully", extra_fields={"router": "v1"})
except Exception:
    print("API routes registered successfully")


scheduler = AsyncIOScheduler()


def run_cleaning_job():
    """Run the data cleaning job."""
    try:
        days_old = int(os.getenv("CLEANUP_DAYS_OLD", "7"))
        logger.info_structured(
            "Starting scheduled data cleaning job",
            extra_fields={"days_old": days_old}
        )
        stats = clean_old_data(days_old=days_old)
        logger.info_structured(
            "Scheduled data cleaning job completed",
            extra_fields=stats
        )
    except Exception as e:
        logger.error_structured(
            "Scheduled data cleaning job failed",
            extra_fields={"error": str(e)},
            exc_info=True
        )


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    try:
        environment = os.getenv("ENVIRONMENT", "development")
        logger.info_structured(
            "Application starting up",
            extra_fields={"environment": environment, "version": "1.0.0"}
        )

        # Enable LangSmith tracing when API key is present (LangChain PyPDFLoader, WebBaseLoader, etc.)
        if os.getenv("LANGSMITH_API_KEY"):
            os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
            logger.info_structured(
                "LangSmith tracing enabled",
                extra_fields={"hint": "Set LANGCHAIN_TRACING_V2=false to disable"},
            )
        
        # Initialize database tables
        try:
            from app.db.session import DATABASE_URL, engine
            from app.db.base import Base
            from app.db.chat_models import ChatSession, ChatMessage, ChatMessageFeedback  # noqa: F401 - register for create_all
            from app.db.llm_models import LLMRun  # noqa: F401 - register for create_all
            
            if DATABASE_URL and DATABASE_URL.startswith("sqlite"):
                logger.info_structured(
                    "Initializing SQLite database tables",
                    extra_fields={"database_url": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL}
                )
                Base.metadata.create_all(bind=engine)
                from app.db.migrations import run_migrations
                run_migrations()
                logger.info_structured("Database tables initialized", extra_fields={})
            elif DATABASE_URL and DATABASE_URL.startswith("postgresql"):
                # In development, create tables automatically; in production, use migrations
                if environment == "development":
                    logger.info_structured(
                        "Initializing PostgreSQL database tables (development mode)",
                        extra_fields={"database_url": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "postgresql://..."}
                    )
                    Base.metadata.create_all(bind=engine)
                    from app.db.migrations import run_migrations
                    run_migrations()
                    logger.info_structured("Database tables initialized", extra_fields={})
                else:
                    logger.info_structured(
                        "Using PostgreSQL - tables should be created via migrations",
                        extra_fields={"database_url": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "postgresql://..."}
                    )
            else:
                logger.warning_structured(
                    "Unknown database type - skipping table initialization",
                    extra_fields={"database_url": DATABASE_URL if DATABASE_URL else "not set"}
                )
        except Exception as e:
            logger.error_structured(
                "Failed to initialize database tables",
                extra_fields={"error": str(e)},
                exc_info=True
            )
            # Don't fail startup if database init fails - might be migration issue
        
        # Log Jira config status (agentic pipeline: Index One, Plan, Generate)
        jira_url = os.getenv("JIRA_BASE_URL") or os.getenv("JIRA_URL", "")
        jira_user = os.getenv("JIRA_USERNAME", "")
        jira_api_ver = os.getenv("JIRA_API_VERSION", "2")
        jira_configured = bool(jira_url and (jira_user and os.getenv("JIRA_PASSWORD")) or (os.getenv("JIRA_EMAIL") and os.getenv("JIRA_API_TOKEN")))
        logger.info_structured(
            "Jira config",
            extra_fields={
                "configured": jira_configured,
                "base_url": jira_url.split("//")[-1][:50] if jira_url else "not set",
                "api_version": jira_api_ver,
                "hint": "Set JIRA_API_VERSION=2 for corporate Jira (e.g. jira.corp.adobe.com)" if not jira_configured else None,
            },
        )

        jira_indexing_enabled = os.getenv("JIRA_INDEXING_ENABLED", "false").lower() == "true"
        if jira_indexing_enabled:
            bootstrap_on_startup = os.getenv("JIRA_INDEXING_BOOTSTRAP_ON_STARTUP", "false").lower() == "true"
            if bootstrap_on_startup:
                try:
                    from app.db.session import SessionLocal
                    from app.services.jira_index_service import index_recent_issues
                    project = os.getenv("JIRA_PROJECT_KEY", "GUIDES")
                    jql = os.getenv("JIRA_INDEXING_BOOTSTRAP_JQL", f"project = {project} AND updated >= -90d")
                    limit = int(os.getenv("JIRA_INDEXING_BOOTSTRAP_LIMIT", "1000"))
                    db = SessionLocal()
                    try:
                        stats = index_recent_issues(db, jql, limit=limit)
                        db.commit()
                        logger.info_structured("Jira bootstrap indexing completed", extra_fields=stats)
                    finally:
                        db.close()
                except Exception as e:
                    logger.warning_structured(
                        "Jira bootstrap indexing failed (non-fatal)",
                        extra_fields={"error": str(e)},
                        exc_info=True,
                    )
            schedule_enabled = os.getenv("JIRA_INDEXING_SCHEDULE_ENABLED", "true").lower() == "true"
            if schedule_enabled:
                cron_expr = os.getenv("JIRA_INDEXING_SCHEDULE_CRON", "0 */6 * * *")
                project = os.getenv("JIRA_PROJECT_KEY", "GUIDES")
                schedule_jql = os.getenv("JIRA_INDEXING_SCHEDULE_JQL", f"project = {project} AND updated >= -7d")
                schedule_limit = int(os.getenv("JIRA_INDEXING_SCHEDULE_LIMIT", "300"))

                def run_jira_index_job():
                    try:
                        from app.db.session import SessionLocal
                        from app.services.jira_index_service import index_recent_issues
                        db = SessionLocal()
                        try:
                            stats = index_recent_issues(db, schedule_jql, limit=schedule_limit)
                            db.commit()
                            logger.info_structured("Jira scheduled indexing completed", extra_fields=stats)
                        finally:
                            db.close()
                    except Exception as e:
                        logger.error_structured(
                            "Jira scheduled indexing failed",
                            extra_fields={"error": str(e)},
                            exc_info=True,
                        )

                scheduler.add_job(
                    run_jira_index_job,
                    trigger=CronTrigger.from_crontab(cron_expr),
                    id="jira_indexing_job",
                    name="Jira Indexing Job",
                    replace_existing=True,
                )
                logger.info_structured(
                    "Jira indexing schedule added",
                    extra_fields={"cron": cron_expr},
                )

        dita_index_enabled = os.getenv("DITA_SPEC_INDEX_ENABLED", "false").lower() == "true"
        dita_index_on_startup = os.getenv("DITA_SPEC_INDEX_ON_STARTUP", "false").lower() == "true"
        if dita_index_enabled and dita_index_on_startup:
            try:
                from app.db.session import SessionLocal
                from app.db.dita_spec_models import DitaSpecChunk
                from app.services.dita_spec_index_service import index_oasis_spec, load_seed_into_db
                db = SessionLocal()
                try:
                    count = db.query(DitaSpecChunk).count()
                    if count == 0:
                        try:
                            result = index_oasis_spec(db)
                            db.commit()
                            logger.info_structured("DITA spec bootstrap completed", extra_fields=result)
                        except Exception:
                            db.rollback()
                            result = load_seed_into_db(db)
                            db.commit()
                            logger.info_structured("DITA spec seed loaded", extra_fields=result)
                finally:
                    db.close()
            except Exception as e:
                logger.warning_structured(
                    "DITA spec bootstrap failed (non-fatal)",
                    extra_fields={"error": str(e)},
                )

        aem_docs_crawl_enabled = os.getenv("AEM_DOCS_CRAWL_ENABLED", "false").lower() == "true"
        aem_docs_crawl_schedule = os.getenv("AEM_DOCS_CRAWL_SCHEDULE", "0 3 * * 0")

        def run_aem_guides_crawl_job():
            try:
                from app.services.crawl_service import crawl_and_index
                logger.info_structured("Starting scheduled AEM Guides docs crawl", extra_fields={})
                stats = crawl_and_index()
                logger.info_structured(
                    "Scheduled AEM Guides docs crawl completed",
                    extra_fields=stats,
                )
            except Exception as e:
                logger.error_structured(
                    "Scheduled AEM Guides docs crawl failed",
                    extra_fields={"error": str(e)},
                    exc_info=True,
                )

        if aem_docs_crawl_enabled:
            scheduler.add_job(
                run_aem_guides_crawl_job,
                trigger=CronTrigger.from_crontab(aem_docs_crawl_schedule),
                id="aem_guides_crawl_job",
                name="AEM Guides Docs Crawl Job",
                replace_existing=True,
            )
            logger.info_structured(
                "AEM Guides docs crawl schedule added",
                extra_fields={"cron": aem_docs_crawl_schedule},
            )

        dita_pdf_index_enabled = os.getenv("DITA_PDF_INDEX_ENABLED", "false").lower() == "true"
        dita_pdf_index_schedule = os.getenv("DITA_PDF_INDEX_SCHEDULE", "0 4 * * 0")

        def run_dita_pdf_index_job():
            try:
                from app.services.dita_pdf_index_service import index_dita_pdf
                logger.info_structured("Starting scheduled DITA 1.2 PDF index", extra_fields={})
                stats = index_dita_pdf()
                logger.info_structured(
                    "Scheduled DITA 1.2 PDF index completed",
                    extra_fields=stats,
                )
            except Exception as e:
                logger.error_structured(
                    "Scheduled DITA 1.2 PDF index failed",
                    extra_fields={"error": str(e)},
                    exc_info=True,
                )

        if dita_pdf_index_enabled:
            scheduler.add_job(
                run_dita_pdf_index_job,
                trigger=CronTrigger.from_crontab(dita_pdf_index_schedule),
                id="dita_pdf_index_job",
                name="DITA 1.2 PDF Index Job",
                replace_existing=True,
            )
            logger.info_structured(
                "DITA PDF index schedule added",
                extra_fields={"cron": dita_pdf_index_schedule},
            )

        cleanup_enabled = os.getenv("CLEANUP_ENABLED", "true").lower() == "true"
        cleanup_schedule = os.getenv("CLEANUP_SCHEDULE", "0 2 * * *")
        
        if cleanup_enabled:
            scheduler.add_job(
                run_cleaning_job,
                trigger=CronTrigger.from_crontab(cleanup_schedule),
                id="data_cleaning_job",
                name="Data Cleaning Job",
                replace_existing=True
            )
            logger.info_structured(
                "Scheduled data cleaning job added",
                extra_fields={
                    "schedule": cleanup_schedule,
                    "enabled": cleanup_enabled
                }
            )
        else:
            logger.info_structured(
                "Data cleaning job disabled",
                extra_fields={"enabled": False}
            )

        if cleanup_enabled or jira_indexing_enabled or aem_docs_crawl_enabled or dita_pdf_index_enabled:
            scheduler.start()
            logger.info_structured("Scheduler started", extra_fields={})
        
        logger.info_structured(
            "Application startup complete",
            extra_fields={"environment": environment}
        )
    except Exception:
        print("Application starting up...")
        print(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
        print("Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    try:
        if scheduler.running:
            scheduler.shutdown()
            logger.info_structured(
                "Scheduled jobs stopped",
                extra_fields={}
            )
    except Exception:
        pass
    
    logger.info_structured("Application shutting down", extra_fields={})


@app.get("/")
def root():
    """Root endpoint."""
    logger.debug_structured("Root endpoint accessed", extra_fields={"endpoint": "/"})
    return {"message": "AEM Guides Dataset Studio API", "version": "1.0.0"}


@app.get("/health")
def health():
    """Health check endpoint with disk space monitoring and resource information."""
    from app.utils.disk_monitor import get_disk_usage, get_storage_size
    from app.db.session import engine
    from sqlalchemy import text, func
    from app.jobs.models import Job
    
    health_status = {
        "status": "healthy",
        "database": "unknown",
        "storage": "unknown",
        "disk_space": {},
        "storage_stats": {},
        "resources": {},
        "jobs": {}
    }
    
    # Database health check
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health_status["database"] = "healthy"
    except Exception as e:
        health_status["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"
    
    # Storage health check
    try:
        from app.storage import get_storage
        storage = get_storage()
        if storage.base_path.exists():
            health_status["storage"] = "healthy"
            health_status["disk_space"] = get_disk_usage()
            health_status["storage_stats"] = get_storage_size()
        else:
            health_status["storage"] = "unhealthy: storage path does not exist"
    except Exception as e:
        health_status["storage"] = f"unhealthy: {str(e)}"
    
    # Resource monitoring (memory, CPU)
    try:
        import psutil
        import os
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        cpu_percent = process.cpu_percent(interval=0.1)
        system_memory = psutil.virtual_memory()
        
        health_status["resources"] = {
            "process_memory_mb": round(memory_info.rss / 1024 / 1024, 2),
            "process_cpu_percent": round(cpu_percent, 2),
            "system_memory_total_mb": round(system_memory.total / 1024 / 1024, 2),
            "system_memory_available_mb": round(system_memory.available / 1024 / 1024, 2),
            "system_memory_percent": round(system_memory.percent, 2)
        }
    except Exception as e:
        health_status["resources"] = {"error": f"Could not get resource info: {str(e)}"}
    
    # Job statistics
    try:
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            # Get job counts by status (all users)
            running_count = db.query(func.count(Job.id)).filter(Job.status == "running").scalar() or 0
            pending_count = db.query(func.count(Job.id)).filter(Job.status == "pending").scalar() or 0
            completed_count = db.query(func.count(Job.id)).filter(Job.status == "completed").scalar() or 0
            
            health_status["jobs"] = {
                "running": running_count,
                "pending": pending_count,
                "completed": completed_count,
                "concurrent_limit": 20
            }
        finally:
            db.close()
    except Exception as e:
        health_status["jobs"] = {"error": f"Could not get job stats: {str(e)}"}

    # LLM readiness (informational; does not affect status)
    try:
        from app.services.llm_service import is_llm_available
        health_status["llm_ready"] = is_llm_available()
    except Exception as e:
        health_status["llm_ready"] = False
        health_status["llm_error"] = str(e)

    # RAG readiness (informational; does not affect status)
    try:
        from app.services.doc_retriever_service import check_rag_readiness
        rag = check_rag_readiness()
        health_status["rag_ready"] = rag.get("any_ready", False)
        health_status["rag"] = {
            "aem_guides_ready": rag.get("aem_guides_ready", False),
            "dita_spec_ready": rag.get("dita_spec_ready", False),
        }
    except Exception as e:
        health_status["rag_ready"] = False
        health_status["rag"] = {"error": str(e)}

    logger.debug_structured(
        "Health check endpoint accessed",
        extra_fields={"endpoint": "/health", "status": health_status["status"]}
    )
    
    return health_status
