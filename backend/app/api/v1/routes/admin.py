"""Admin and maintenance endpoints."""
import os
import subprocess
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.core.auth import AdminUser, UserIdentity
from app.services.cleaning_service import clean_old_data
from app.core.structured_logging import get_structured_logger

router = APIRouter(prefix="/admin", tags=["admin"])

logger = get_structured_logger(__name__)


@router.post("/env-check")
def check_env(user: UserIdentity = AdminUser):
    """Check which env vars are set (values redacted for secrets)."""
    keys = ["JIRA_URL", "JIRA_USERNAME", "JIRA_PASSWORD", "LLM_PROVIDER",
            "AZURE_OPENAI_ENDPOINT", "ALLOW_DEV_AUTH_BYPASS", "ENVIRONMENT"]
    return {k: ("SET" if os.environ.get(k) else "NOT SET") for k in keys}


class SetEnvRequest(BaseModel):
    key: str
    value: str
    force: bool = False  # overwrite existing value


@router.post("/set-env")
def set_env_var(request: SetEnvRequest, user: UserIdentity = AdminUser):
    """Append/overwrite a key=value in .env.docker and trigger uvicorn reload.

    Use force=true to replace an existing value.
    Values written only to gitignored .env.docker — never to the repo.
    """
    import re as _re
    repo_dir = os.environ.get("REPO_DIR", "/root/aem-guides-dataset-studio")
    env_file = os.path.join(repo_dir, "backend", ".env.docker")
    try:
        existing = open(env_file).read() if os.path.exists(env_file) else ""
        key_exists = bool(_re.search(rf"^{re.escape(request.key)}=", existing, _re.MULTILINE))
        if key_exists and not request.force:
            return {"success": True, "action": "already_set", "key": request.key}
        if key_exists and request.force:
            # Replace existing line
            new_content = _re.sub(
                rf"^{re.escape(request.key)}=.*$",
                f"{request.key}={request.value}",
                existing, flags=_re.MULTILINE
            )
            with open(env_file, "w") as f:
                f.write(new_content)
            action = "updated"
        else:
            with open(env_file, "a") as f:
                f.write(f"\n{request.key}={request.value}\n")
            action = "added"
        os.utime(__file__, None)  # trigger uvicorn reload
        return {"success": True, "action": action, "key": request.key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-jira/{issue_key}")
def test_jira(issue_key: str, user: UserIdentity = AdminUser):
    """Test direct Jira REST API connectivity and key resolution."""
    from app.services.jira_generate_resolve import fetch_issue_text_for_generate, _jira_client_ready
    from app.services.jira_client import JiraClient
    client = JiraClient()
    ready = _jira_client_ready(client)
    if not ready:
        return {"ready": False, "url": client.base_url, "user": client.username}
    text, err = fetch_issue_text_for_generate(issue_key)
    return {
        "ready": True,
        "url": client.base_url,
        "issue_key": issue_key,
        "fetched": bool(text),
        "preview": (text or "")[:300],
        "error": err,
    }


@router.post("/deploy")
def trigger_deploy(user: UserIdentity = AdminUser):
    """Pull latest code from git and restart the backend service (Linux VM only).

    Tries systemctl first, falls back to killing the uvicorn/python process
    so systemd can auto-restart it.
    """
    import signal
    try:
        repo_dir = os.environ.get("REPO_DIR", "/root/aem-guides-dataset-studio")
        results: dict = {}

        # git pull
        pull = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        results["git_pull"] = (pull.stdout.strip() or pull.stderr.strip())[-500:]

        # clear pyc cache so new code takes effect
        subprocess.run(
            ["bash", "-c", f"find {repo_dir}/backend/app -name '*.pyc' -delete"],
            timeout=15,
        )
        results["pyc_cleared"] = "ok"

        # Try systemctl with both known service names
        restarted = False
        for svc in ("aem-backend", "aem-studio-backend", "aem-guides-backend"):
            r = subprocess.run(
                ["systemctl", "restart", svc],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                results["restart"] = f"systemctl {svc}: ok"
                restarted = True
                break

        # Fallback: find the process on port 8001 and SIGTERM it after a delay
        # so the HTTP response is fully sent before the process exits.
        if not restarted:
            lsof = subprocess.run(
                ["bash", "-c", "lsof -ti:8001 2>/dev/null || fuser 8001/tcp 2>/dev/null || true"],
                capture_output=True, text=True, timeout=10,
            )
            pids = [p.strip() for p in lsof.stdout.strip().split() if p.strip().isdigit()]
            if pids:
                import threading
                def _delayed_kill(pids, delay=3):
                    import time, os, signal as _sig
                    time.sleep(delay)
                    for pid in pids[:3]:
                        try:
                            os.kill(int(pid), _sig.SIGTERM)
                        except Exception:
                            pass
                threading.Thread(target=_delayed_kill, args=(pids,), daemon=True).start()
                results["restart"] = f"SIGTERM scheduled for pids {pids} in 3s"
                restarted = True
            else:
                results["restart"] = "no process found on port 8001"

        # If process not restarted via systemctl/SIGTERM, trigger uvicorn --reload
        # by touching a .py file (uvicorn watches for changes on Linux)
        if not restarted or "scheduled" in results.get("restart", ""):
            try:
                trigger_file = os.path.join(repo_dir, "backend", "app", "api", "v1", "routes", "admin.py")
                os.utime(trigger_file, None)
                results["uvicorn_reload"] = "touched admin.py — uvicorn will reload"
            except Exception as ute:
                results["uvicorn_reload"] = f"touch failed: {ute}"

        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CleanupRequest(BaseModel):
    """Request model for manual cleanup."""
    days_old: int = Field(default=7, ge=1, le=365, description="Number of days after which data should be cleaned")


@router.post("/cleanup")
def trigger_cleanup(
    request: CleanupRequest = CleanupRequest(),
    user: UserIdentity = AdminUser,
):
    """Manually trigger data cleanup job.
    
    This endpoint allows administrators to manually trigger the cleanup of old data.
    By default, it cleans data older than 7 days.
    """
    try:
        logger.info_structured(
            "Manual cleanup triggered",
            extra_fields={
                "user_id": user.id,
                "days_old": request.days_old
            }
        )
        
        stats = clean_old_data(days_old=request.days_old)
        
        return {
            "success": True,
            "message": "Cleanup completed successfully",
            "stats": stats
        }
    except Exception as e:
        logger.error_structured(
            "Manual cleanup failed",
            extra_fields={
                "user_id": user.id,
                "error": str(e)
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )
