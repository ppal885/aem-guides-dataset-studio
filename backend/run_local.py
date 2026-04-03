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

# Allow `from backend.app...` imports used across services (repo root must be on path)
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.append(str(_repo_root))

import uvicorn
from app.core.logging_config import setup_logging

if __name__ == "__main__":
    # Set up logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    structured = os.getenv("STRUCTURED_LOGGING", "false").lower() in ("true", "1", "yes")
    logger = setup_logging(log_level, structured=structured)
    
    port = int(os.getenv("PORT", "8000"))
    logger.info("=" * 60)
    logger.info("Starting AEM Guides Dataset Studio Backend")
    logger.info("=" * 60)
    logger.info(f"Server will be available at http://0.0.0.0:{port}")
    logger.info(f"API docs available at http://0.0.0.0:{port}/docs")
    logger.info(f"Health check: http://0.0.0.0:{port}/health")
    logger.info(f"Log level: {log_level}")
    logger.info(f"Structured logging: {structured}")
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
