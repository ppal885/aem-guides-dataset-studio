#!/usr/bin/env python3
"""Run the FastAPI app locally."""
import os
import sys
from pathlib import Path

# Load .env from backend directory before any app imports
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

# `app` package lives under this directory; uvicorn loads `app.main:app`.
# Always put backend first — avoids `ModuleNotFoundError: app.core` when another `app`
# is on PYTHONPATH or when the interpreter resolves sys.path in an unexpected order.
_backend_dir = str(Path(__file__).resolve().parent)
_norm = os.path.normcase(os.path.abspath(_backend_dir))

def _path_key(p: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(p))
    except OSError:
        return p

sys.path[:] = [p for p in sys.path if _path_key(p) != _norm]
sys.path.insert(0, _backend_dir)

_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.append(_repo_root)

import uvicorn
from app.core.logging_config import setup_logging

if __name__ == "__main__":
    # Set up logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    structured = os.getenv("STRUCTURED_LOGGING", "false").lower() in ("true", "1", "yes")
    logger = setup_logging(log_level, structured=structured)
    
    port = int(os.getenv("PORT", "8001"))
    logger.info("=" * 60)
    logger.info("Starting AEM Guides Dataset Studio Backend")
    logger.info("=" * 60)
    logger.info(f"Server will be available at http://0.0.0.0:{port}")
    logger.info(f"API docs available at http://0.0.0.0:{port}/docs")
    logger.info(f"Health check: http://0.0.0.0:{port}/health")
    logger.info(f"Log level: {log_level}")
    logger.info(f"Structured logging: {structured}")
    llm_provider = (os.getenv("LLM_PROVIDER") or "anthropic").strip() or "anthropic"
    logger.info(f"LLM provider: {llm_provider}")
    screenshot_vision_provider = (os.getenv("SCREENSHOT_VISION_PROVIDER") or "inherit").strip() or "inherit"
    logger.info(f"Screenshot vision provider: {screenshot_vision_provider}")
    logger.info("=" * 60)
    
    try:
        # Disable reload on Windows to avoid OSError: [Errno 22] Invalid argument
        # Reload doesn't work well in background processes or on Windows
        import sys
        use_reload = sys.platform != "win32" and os.getenv("DISABLE_RELOAD") != "1"
        
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",  # Bind to all interfaces to allow access from network
            port=port,
            reload=use_reload,
            log_level="info",
            log_config=None  # Use our custom logging
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.critical(f"Failed to start server: {e}", exc_info=True)
        raise
