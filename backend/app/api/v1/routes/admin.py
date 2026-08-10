"""Admin and maintenance endpoints."""
import os
import json
import subprocess
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from app.core.auth import AdminUser, UserIdentity
from app.services.cleaning_service import clean_old_data
from app.core.structured_logging import get_structured_logger

router = APIRouter(prefix="/admin", tags=["admin"])

logger = get_structured_logger(__name__)


class EvidenceGraphRebuildRequest(BaseModel):
    dry_run: bool = True
    sources: list[str] = Field(default_factory=lambda: ["jira", "docs", "dita"])
    batch_size: int = Field(default=500, ge=10, le=5000)


class EvidenceGraphSyncRequest(BaseModel):
    max_events: int = Field(default=500, ge=1, le=5000)
    max_retries: int = Field(default=5, ge=1, le=20)
    batch_size: int = Field(default=500, ge=10, le=5000)


class EvidenceGraphEventReplayRequest(BaseModel):
    event_ids: list[str] = Field(default_factory=list)
    source_kind: str = ""
    confirm_all_failed: bool = False


@router.get("/evidence-graph/status")
def evidence_graph_status(user: UserIdentity = AdminUser):
    del user
    from app.db.session import SessionLocal
    from app.services.evidence_graph_store import graph_status

    session = SessionLocal()
    try:
        return graph_status(session)
    finally:
        session.close()


@router.get("/evidence-graph/audit")
def evidence_graph_audit(generation_id: str = "", user: UserIdentity = AdminUser):
    del user
    from app.db.session import SessionLocal
    from app.services.evidence_graph_store import active_generation, audit_generation

    session = SessionLocal()
    try:
        selected = generation_id.strip()
        if not selected:
            generation = active_generation(session)
            if generation is None:
                raise HTTPException(status_code=404, detail="No active evidence graph generation")
            selected = generation.id
        result = audit_generation(session, selected)
        if result.get("errors") == ["Generation does not exist."]:
            raise HTTPException(status_code=404, detail=result)
        return result
    finally:
        session.close()


@router.post("/evidence-graph/rebuild")
def rebuild_evidence_graph_endpoint(
    request: EvidenceGraphRebuildRequest,
    user: UserIdentity = AdminUser,
):
    from app.services.evidence_graph_build_service import rebuild_evidence_graph

    result = rebuild_evidence_graph(
        dry_run=request.dry_run,
        sources=request.sources,
        batch_size=request.batch_size,
        created_by=user.id,
    )
    if not result.get("valid"):
        raise HTTPException(status_code=409, detail=result)
    return result


@router.post("/evidence-graph/sync")
def sync_evidence_graph_endpoint(
    request: EvidenceGraphSyncRequest,
    user: UserIdentity = AdminUser,
):
    from app.services.evidence_graph_sync_service import drain_evidence_graph_events

    result = drain_evidence_graph_events(
        max_events=request.max_events,
        max_retries=request.max_retries,
        batch_size=request.batch_size,
        created_by=user.id,
    )
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result)
    return result


@router.get("/evidence-graph/events")
def evidence_graph_events(
    status: str = "failed",
    source_kind: str = "",
    limit: int = 100,
    user: UserIdentity = AdminUser,
):
    del user
    from app.db.session import SessionLocal
    from app.services.evidence_graph_store import list_source_events

    normalized_status = status.strip().lower()
    if normalized_status and normalized_status not in {"pending", "retry", "failed", "completed"}:
        raise HTTPException(status_code=400, detail="Unsupported evidence graph event status")
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
    session = SessionLocal()
    try:
        events = list_source_events(
            session,
            status=normalized_status or None,
            source_kind=source_kind.strip() or None,
            limit=limit,
        )
        return {"count": len(events), "events": events}
    finally:
        session.close()


@router.post("/evidence-graph/events/replay")
def replay_evidence_graph_events_endpoint(
    request: EvidenceGraphEventReplayRequest,
    user: UserIdentity = AdminUser,
):
    del user
    from app.db.session import SessionLocal
    from app.services.evidence_graph_store import replay_source_events

    event_ids = list(dict.fromkeys(value.strip() for value in request.event_ids if value.strip()))
    source_kind = request.source_kind.strip()
    if len(event_ids) > 1000:
        raise HTTPException(status_code=400, detail="At most 1000 event IDs can be replayed at once")
    if not event_ids and not source_kind and not request.confirm_all_failed:
        raise HTTPException(
            status_code=400,
            detail="Select event_ids/source_kind or explicitly set confirm_all_failed=true",
        )
    session = SessionLocal()
    try:
        result = replay_source_events(
            session,
            event_ids=event_ids,
            source_kind=source_kind or None,
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.post("/evidence-graph/rollback")
def rollback_evidence_graph_endpoint(user: UserIdentity = AdminUser):
    from app.db.session import SessionLocal
    from app.services.evidence_graph_store import rollback_generation

    session = SessionLocal()
    try:
        try:
            result = rollback_generation(session)
            session.commit()
            return result
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        session.close()


@router.post("/jira-rag/import-csv")
async def import_jira_csv(
    response: Response,
    files: list[UploadFile] = File(...),
    customer_assignments_json: str = Form("{}"),
    dry_run: bool = False,
    user: UserIdentity = AdminUser,
):
    """Preview or asynchronously ingest one or more Jira CSV exports."""
    from app.services.jira_csv_import_service import (
        MAX_CSV_BYTES,
        create_import_run,
        preview_jira_csv_files,
        start_import,
    )

    if not files or len(files) > 10:
        raise HTTPException(status_code=400, detail="Upload between 1 and 10 Jira CSV files")
    payloads: list[tuple[str, bytes]] = []
    try:
        for upload in files:
            filename = upload.filename or "jira-export.csv"
            data = await upload.read(MAX_CSV_BYTES + 1)
            if len(data) > MAX_CSV_BYTES:
                raise ValueError(f"{filename} exceeds the 25 MB limit")
            payloads.append((filename, data))
        try:
            customer_assignments = json.loads(customer_assignments_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("customer_assignments_json must be a JSON object keyed by file hash") from exc
        if not isinstance(customer_assignments, dict):
            raise ValueError("customer_assignments_json must be a JSON object keyed by file hash")
        customer_assignments = {str(key): str(value) for key, value in customer_assignments.items()}
        preview = preview_jira_csv_files(payloads, customer_assignments)
        if dry_run:
            return preview
        run_id, paths = create_import_run(
            payloads,
            created_by=user.id,
            customer_assignments=customer_assignments,
        )
        start_import(run_id, paths)
        response.status_code = 202
        return {
            "import_id": run_id,
            "status": "pending",
            "status_url": f"/api/v1/admin/jira-rag/imports/{run_id}",
            "preview": preview,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        for upload in files:
            await upload.close()


@router.get("/jira-rag/imports/{import_id}")
def jira_csv_import_status(import_id: str, user: UserIdentity = AdminUser):
    """Return progress and final statistics for a Jira CSV import."""
    del user
    from app.services.jira_csv_import_service import get_import_run

    result = get_import_run(import_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Jira CSV import not found")
    return result


@router.post("/jira-rag/learning-chunks/rebuild")
def rebuild_jira_learning_chunks(
    source_type: str = "jira_csv",
    limit: int = 10_000,
    user: UserIdentity = AdminUser,
):
    """Build high-signal historical learning chunks from indexed resolved Jira evidence."""
    del user
    from app.services.jira_learning_chunk_service import backfill_jira_learning_chunks

    result = backfill_jira_learning_chunks(
        source_type=source_type.strip()[:80],
        limit=max(1, min(limit, 100_000)),
    )
    if result.get("error"):
        raise HTTPException(status_code=503, detail=str(result["error"]))
    return result


@router.get("/jira-rag/uac-chunks/audit")
def audit_historical_uac_chunks(
    source_type: str = "jira_csv",
    limit: int = 100_000,
    page_size: int = 200,
    closed_only: bool = True,
    user: UserIdentity = AdminUser,
):
    del user
    from app.services.jira_uac_backfill_service import backfill_historical_uac_chunks

    return backfill_historical_uac_chunks(
        source_type=source_type.strip()[:80],
        limit=max(1, min(limit, 500_000)),
        page_size=max(1, min(page_size, 1000)),
        closed_only=closed_only,
        dry_run=True,
    )


@router.post("/jira-rag/uac-chunks/rebuild")
def rebuild_historical_uac_chunks(
    source_type: str = "jira_csv",
    limit: int = 100_000,
    page_size: int = 200,
    closed_only: bool = True,
    dry_run: bool = True,
    refresh_learning: bool = True,
    user: UserIdentity = AdminUser,
):
    del user
    from app.services.jira_uac_backfill_service import backfill_historical_uac_chunks

    result = backfill_historical_uac_chunks(
        source_type=source_type.strip()[:80],
        limit=max(1, min(limit, 500_000)),
        page_size=max(1, min(page_size, 1000)),
        closed_only=closed_only,
        dry_run=dry_run,
    )
    if result.get("error"):
        raise HTTPException(status_code=503, detail=str(result["error"]))
    if not dry_run and result.get("valid") and refresh_learning:
        from app.services.jira_learning_chunk_service import backfill_jira_learning_chunks

        learning = backfill_jira_learning_chunks(
            source_type=source_type.strip()[:80],
            limit=min(limit, 100_000),
        )
        result["learning_refresh"] = learning
        if learning.get("error") or learning.get("failed_issues"):
            result["valid"] = False
    if not dry_run and not result.get("valid"):
        raise HTTPException(status_code=500, detail=result)
    return result


@router.post("/jira-rag/reconcile")
def reconcile_jira_rag(
    dry_run: bool = True,
    limit: int = 10_000,
    user: UserIdentity = AdminUser,
):
    """Repair Jira keys present in SQL but absent from Chroma."""
    del user
    from app.services.jira_rag_reconciliation_service import reconcile_jira_sql_chroma

    result = reconcile_jira_sql_chroma(
        dry_run=dry_run,
        limit=max(1, min(limit, 100_000)),
    )
    if result.get("error"):
        raise HTTPException(status_code=503, detail=str(result["error"]))
    return result


@router.post("/jira-rag/customer-profiles/rebuild")
def rebuild_jira_customer_profiles(customers: str = "", user: UserIdentity = AdminUser):
    """Rebuild aggregate customer workflow profiles from distinct SQL Jira keys."""
    del user
    from app.services.jira_customer_profile_service import rebuild_customer_profiles

    selected = [value.strip() for value in customers.split(",") if value.strip()]
    return rebuild_customer_profiles(selected or None)


@router.get("/jira-rag/customer-profiles/{customer}")
def jira_customer_profile(customer: str, user: UserIdentity = AdminUser):
    """Return one aggregate profile with its explicit evidence boundary."""
    del user
    from app.services.jira_customer_profile_service import get_customer_profile

    result = get_customer_profile(customer)
    if result is None:
        raise HTTPException(status_code=404, detail="Customer Jira profile not found")
    return result


class CustomerProfileApprovalRequest(BaseModel):
    status: str
    notes: str = ""


@router.post("/jira-rag/customer-profiles/{customer}/approval")
def approve_jira_customer_profile(
    customer: str,
    request: CustomerProfileApprovalRequest,
    user: UserIdentity = AdminUser,
):
    """Record reviewer approval without converting aggregate context into direct behavior proof."""
    from app.services.jira_customer_profile_service import set_customer_profile_approval

    try:
        result = set_customer_profile_approval(
            customer,
            status=request.status,
            reviewer=user.id,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Customer Jira profile not found")
    return result


@router.post("/env-check")
def check_env(user: UserIdentity = AdminUser):
    """Check which env vars are set (values redacted for secrets)."""
    keys = ["JIRA_URL", "JIRA_BASE_URL", "JIRA_USERNAME", "JIRA_PASSWORD", "LLM_PROVIDER",
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
    _esc = _re.escape(request.key)
    repo_dir = os.environ.get("REPO_DIR", "/root/aem-guides-dataset-studio")
    env_file = os.path.join(repo_dir, "backend", ".env.docker")
    try:
        existing = open(env_file).read() if os.path.exists(env_file) else ""
        key_exists = bool(_re.search(rf"^{_esc}=", existing, _re.MULTILINE))
        if key_exists and not request.force:
            return {"success": True, "action": "already_set", "key": request.key}
        if key_exists and request.force:
            new_content = _re.sub(
                rf"^{_esc}=.*$",
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
        # Apply to running process immediately via os.environ (lives until next SIGTERM restart)
        # DO NOT touch admin.py here — uvicorn reload would lose the os.environ change.
        # The value is already written to .env.docker so it survives the next systemd restart.
        os.environ[request.key] = request.value
        return {"success": True, "action": action, "key": request.key, "live": True,
                "note": "Value set in .env.docker (persistent) and os.environ (live). Survives restarts."}
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

    On every deploy, ensures required env vars (Jira, Azure) are written to
    .env.docker so they survive systemd restarts without manual re-entry.
    Tries systemctl first, falls back to SIGTERM. Does NOT do uvicorn reload
    when SIGTERM is used — systemd restart re-reads .env.docker automatically.
    """
    import signal, re as _re
    try:
        repo_dir = os.environ.get("REPO_DIR", "/root/aem-guides-dataset-studio")
        results: dict = {}

        # Persist env vars that are currently live but might not be in .env.docker yet
        env_file = os.path.join(repo_dir, "backend", ".env.docker")
        try:
            existing = open(env_file).read() if os.path.exists(env_file) else ""
            for key in ("JIRA_URL", "JIRA_BASE_URL", "JIRA_USERNAME", "JIRA_PASSWORD", "JIRA_API_VERSION",
                        "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
                        "AZURE_OPENAI_API_VERSION", "AZURE_OPENAI_MODEL",
                        "LLM_PROVIDER", "ALLOW_DEV_AUTH_BYPASS"):
                val = os.environ.get(key, "")
                if not val:
                    continue
                if f"{key}=" in existing:
                    # Update
                    existing = _re.sub(rf"^{_re.escape(key)}=.*$", f"{key}={val}", existing, flags=_re.MULTILINE)
                else:
                    existing += f"\n{key}={val}\n"
            with open(env_file, "w") as f:
                f.write(existing)
            results["env_persisted"] = "ok"
        except Exception as ep:
            results["env_persist_error"] = str(ep)

        # git pull
        pull = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        results["git_pull"] = (pull.stdout.strip() or pull.stderr.strip())[-500:]

        # Keep the host nginx proxy aligned with the API's 10 files x 25 MB validation.
        try:
            nginx_limit = "/etc/nginx/conf.d/aem-guides-upload-limit.conf"
            with open(nginx_limit, "w", encoding="utf-8") as nginx_file:
                nginx_file.write("client_max_body_size 260m;\n")
            nginx_test = subprocess.run(
                ["nginx", "-t"], capture_output=True, text=True, timeout=15
            )
            if nginx_test.returncode != 0:
                raise RuntimeError((nginx_test.stderr or nginx_test.stdout).strip())
            nginx_reload = subprocess.run(
                ["systemctl", "reload", "nginx"], capture_output=True, text=True, timeout=15
            )
            if nginx_reload.returncode != 0:
                raise RuntimeError((nginx_reload.stderr or nginx_reload.stdout).strip())
            results["nginx_upload_limit"] = "260 MB configured and nginx reloaded"
        except Exception as nginx_exc:
            results["nginx_upload_limit_error"] = str(nginx_exc)

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

        # Only touch admin.py for uvicorn reload when SIGTERM/systemctl didn't happen.
        # When SIGTERM IS scheduled, DO NOT also touch admin.py — the new process
        # started by systemd reads .env.docker via run_local.py, so env vars
        # persist. An extra uvicorn reload would create workers WITHOUT re-reading
        # .env.docker, losing credentials.
        if not restarted:
            try:
                trigger_file = os.path.join(repo_dir, "backend", "app", "api", "v1", "routes", "admin.py")
                os.utime(trigger_file, None)
                results["uvicorn_reload"] = "touched admin.py — uvicorn will reload (no SIGTERM available)"
            except Exception as ute:
                results["uvicorn_reload"] = f"touch failed: {ute}"
        else:
            results["note"] = "SIGTERM restart scheduled — systemd will re-read .env.docker automatically"

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


# ---------------------------------------------------------------------------
# Jira RAG Indexing Endpoints
# ---------------------------------------------------------------------------

class JiraBulkIndexRequest(BaseModel):
    jql: str = "project = GUIDES ORDER BY updated DESC"
    limit: int = Field(default=1000, ge=1, le=10000)
    force_reindex: bool = False


class JiraRagSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)


@router.post("/index-jira/{issue_key}")
def index_single_jira(issue_key: str, force_reindex: bool = False, user: UserIdentity = AdminUser):
    """Index a single Jira issue into ChromaDB for RAG retrieval."""
    from app.services.jira_qa_index_service import (
        index_jql_to_chroma, _jira_configured, is_chroma_available, is_embedding_available,
    )
    from app.services.jira_client import JiraClient
    client = JiraClient()
    if not _jira_configured(client):
        raise HTTPException(status_code=400, detail="Jira not configured.")
    if not is_chroma_available():
        raise HTTPException(status_code=400, detail="ChromaDB not available.")
    if not is_embedding_available():
        raise HTTPException(status_code=400, detail="Embedding model not available.")
    try:
        result = index_jql_to_chroma(
            f'issue = "{issue_key}"',
            limit=1,
            force_reindex=force_reindex,
            jira_client=client,
        )
        chunks = result.get("chunks_upserted") or result.get("chunks", 0)
        errors = result.get("errors") or ([] if not result.get("error") else [result["error"]])
        return {
            "success": not result.get("error") and not errors,
            "issue_key": issue_key,
            "chunks_indexed": chunks,
            "error": result.get("error"),
            "errors": errors[:5] if errors else [],
            "message": result.get("message"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index-jira-bulk")
def bulk_index_jira(request: JiraBulkIndexRequest, user: UserIdentity = AdminUser):
    """Bulk-index Jira issues matching a JQL query into ChromaDB."""
    from app.services.jira_qa_index_service import (
        index_jql_to_chroma, _jira_configured, is_chroma_available, is_embedding_available,
    )
    from app.services.jira_client import JiraClient
    client = JiraClient()
    if not _jira_configured(client):
        raise HTTPException(status_code=400, detail="Jira not configured.")
    if not is_chroma_available():
        raise HTTPException(status_code=400, detail="ChromaDB not available.")
    if not is_embedding_available():
        raise HTTPException(status_code=400, detail="Embedding model not available.")
    try:
        result = index_jql_to_chroma(
            request.jql,
            limit=request.limit,
            force_reindex=request.force_reindex,
            jira_client=client,
        )
        return {
            "success": not result.get("error"),
            "issues_indexed": result.get("issues_indexed", 0),
            "chunks_upserted": result.get("chunks_upserted", 0),
            "error": result.get("error"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search-jira-rag")
def search_jira_rag(request: JiraRagSearchRequest, user: UserIdentity = AdminUser):
    """Semantic search over indexed Jira issues in ChromaDB."""
    from app.services.jira_qa_retrieval_service import semantic_search_jira_qa
    try:
        hits = semantic_search_jira_qa(request.query, top_k=request.limit)
        return {
            "query": request.query,
            "hits": [
                {
                    "jira_key": h.get("jira_key", ""),
                    "summary": h.get("summary", "")[:200],
                    "score": round(float(h.get("score", 0)), 3),
                    "component": h.get("component", ""),
                }
                for h in (hits or [])
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag-collections")
def rag_collections_status(user: UserIdentity = AdminUser):
    """Report chunk counts for all RAG collections."""
    try:
        from app.services.vector_store_service import (
            CHROMA_COLLECTION_AEM_GUIDES, CHROMA_COLLECTION_DITA_SPEC,
            CHROMA_COLLECTION_JIRA_QA, CHROMA_COLLECTION_DITA_OT_GITHUB,
            get_collection_count,
        )
        collections = {
            "jira_qa": CHROMA_COLLECTION_JIRA_QA,
            "aem_guides": CHROMA_COLLECTION_AEM_GUIDES,
            "dita_spec": CHROMA_COLLECTION_DITA_SPEC,
            "dita_ot_github": CHROMA_COLLECTION_DITA_OT_GITHUB,
        }
        result = {}
        for label, name in collections.items():
            try:
                result[label] = {"collection": name, "chunks": get_collection_count(name)}
            except Exception as e:
                result[label] = {"collection": name, "error": str(e)}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jira-rag-status")
def jira_rag_status(user: UserIdentity = AdminUser):
    """Report how many Jira issues are indexed in ChromaDB."""
    from app.services.jira_qa_index_service import is_chroma_available, is_embedding_available, CHROMA_COLLECTION_JIRA_QA
    from app.services.vector_store_service import get_collection_count
    if not is_chroma_available():
        return {"available": False, "reason": "ChromaDB not available"}
    try:
        count = get_collection_count(CHROMA_COLLECTION_JIRA_QA)
        return {
            "available": True,
            "embedding_available": is_embedding_available(),
            "collection": CHROMA_COLLECTION_JIRA_QA,
            "chunk_count": count,
        }
    except Exception as e:
        return {"available": True, "error": str(e)}


@router.get("/jira-rag/corpus-audit")
def jira_rag_corpus_audit(
    duplicate_sample_limit: int = 20,
    top_components_per_customer: int = 10,
    user: UserIdentity = AdminUser,
):
    """Audit unique-issue customer, component, date, metadata, and duplicate coverage in Chroma."""
    del user
    from app.services.jira_corpus_audit_service import audit_jira_corpus

    try:
        return audit_jira_corpus(
            duplicate_sample_limit=max(0, min(int(duplicate_sample_limit), 100)),
            top_components_per_customer=max(1, min(int(top_components_per_customer), 50)),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Jira corpus audit failed: {exc}") from exc


class JiraSyncCursorBootstrapRequest(BaseModel):
    project_key: str = Field("", max_length=30)
    sync_state_id: str = Field("", max_length=120)
    dry_run: bool = True
    force: bool = False


@router.post("/jira-rag/sync-cursor/bootstrap")
def bootstrap_jira_rag_sync_cursor(
    request: JiraSyncCursorBootstrapRequest,
    user: UserIdentity = AdminUser,
):
    """Preview or repair the incremental cursor from searchable Jira metadata."""
    del user
    from app.services.jira_sync_cursor_service import bootstrap_jira_sync_cursor

    try:
        result = bootstrap_jira_sync_cursor(
            request.project_key or None,
            sync_state_id=request.sync_state_id or None,
            dry_run=request.dry_run,
            force=request.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.get("available"):
        raise HTTPException(status_code=409, detail=result)
    return result


@router.get("/rag/knowledge-audit")
def rag_knowledge_audit(
    duplicate_sample_limit: int = 10,
    user: UserIdentity = AdminUser,
):
    """Audit authoritative topic and metadata coverage in product and DITA knowledge corpora."""
    del user
    from app.services.knowledge_corpus_audit_service import audit_knowledge_corpora

    try:
        return audit_knowledge_corpora(
            duplicate_sample_limit=max(0, min(int(duplicate_sample_limit), 100))
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Knowledge corpus audit failed: {exc}") from exc


@router.post("/init-embedding")
def init_embedding_model(user: UserIdentity = AdminUser):
    """Force-initialize the embedding model (downloads from HuggingFace if needed).

    Call this once on a fresh VM to download all-MiniLM-L6-v2 before indexing.
    """
    try:
        from app.services.embedding_service import (
            _load_model, is_embedding_available, get_embedding_diagnostics,
            reset_embedding_runtime_state,
        )
        # Reset state to force a fresh load attempt
        reset_embedding_runtime_state()
        model = _load_model()
        diag = get_embedding_diagnostics()
        if model is not None:
            return {"success": True, "available": True, "model": diag.get("active_model_identifier"), "mode": diag.get("load_mode")}
        return {"success": False, "available": False, "error": diag.get("error"), "reason": diag.get("load_mode")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-azure-embedding")
def test_azure_embedding(user: UserIdentity = AdminUser):
    """Directly test the Azure OpenAI embedding API call and return raw response or error."""
    import requests as _req
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    model = os.environ.get("AZURE_EMBEDDING_MODEL", "text-embedding-ada-002")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01")
    if not endpoint or not api_key:
        return {"error": "AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY not set", "endpoint_len": len(endpoint), "key_len": len(api_key)}
    url = f"{endpoint}/openai/deployments/{model}/embeddings?api-version={api_version}"
    try:
        r = _req.post(url, headers={"api-key": api_key, "Content-Type": "application/json"},
                      json={"input": ["test embedding"], "model": model}, timeout=15, verify=False)
        return {"status": r.status_code, "ok": r.ok, "url": url[:80], "model": model,
                "response_preview": r.text[:300] if not r.ok else "OK",
                "dimensions": len(r.json()["data"][0]["embedding"]) if r.ok else None}
    except Exception as e:
        return {"error": str(e), "url": url[:80], "model": model}


@router.post("/index-all-rag")
def index_all_rag(user: UserIdentity = AdminUser):
    """Trigger all RAG indexing: AEM Guides crawl + Jira bulk index.

    Use this once on a fresh VM to populate all RAG collections.
    Returns immediately — crawl runs synchronously (takes several minutes).
    """
    import asyncio
    results: dict = {}

    # 1. Init embedding model first
    try:
        from app.services.embedding_service import _load_model, is_embedding_available, reset_embedding_runtime_state
        reset_embedding_runtime_state()
        _load_model()
        results["embedding"] = "ok" if is_embedding_available() else "failed"
    except Exception as e:
        results["embedding"] = f"error: {e}"
        return {"success": False, "results": results, "error": "Embedding model failed to load"}

    if results["embedding"] != "ok":
        return {"success": False, "results": results, "error": "Embedding not available — install sentence-transformers"}

    # 2. Crawl AEM Guides (first 50 priority pages synchronously)
    try:
        from app.services.crawl_service import crawl_and_index, _load_crawl_urls
        urls = _load_crawl_urls()[:50]
        stats = crawl_and_index(urls=urls)
        results["aem_guides"] = {"pages": stats.get("pages_crawled", 0), "chunks": stats.get("chunks_stored", 0)}
    except Exception as e:
        results["aem_guides"] = {"error": str(e)}

    # 3. Index Jira issues into Chroma jira_qa RAG
    try:
        from app.services.jira_qa_index_service import (
            _jira_configured,
            default_jira_qa_backfill_limit,
            resolve_jira_qa_project_key,
            run_jira_qa_rag_backfill,
        )
        from app.services.jira_client import JiraClient
        client = JiraClient()
        if _jira_configured(client):
            pk = resolve_jira_qa_project_key()
            lim = default_jira_qa_backfill_limit()
            r = run_jira_qa_rag_backfill(project_key=pk, limit=lim, jira_client=client)
            results["jira"] = {
                "project_key": pk,
                "limit": lim,
                "indexed": r.get("issues_indexed", 0),
                "chunks": r.get("chunks", 0),
                "error": r.get("error"),
            }
        else:
            results["jira"] = {"error": "Jira not configured"}
    except Exception as e:
        results["jira"] = {"error": str(e)}

    return {"success": True, "results": results}


@router.post("/pip-install")
def pip_install(user: UserIdentity = AdminUser):
    """Install/upgrade key Python dependencies needed for RAG indexing."""
    import sys
    results = {}
    packages = [
        "sentence-transformers>=2.2.0",
        "torch>=2.0.0",
        "transformers>=4.30.0",
        "langchain-community>=0.0.1",
        "langchain-text-splitters>=0.0.1",
    ]
    for pkg in packages:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            capture_output=True, text=True, timeout=120,
        )
        results[pkg.split(">=")[0]] = "ok" if r.returncode == 0 else r.stderr.strip()[-200:]
    # Reset embedding state so it retries after install
    try:
        from app.services.embedding_service import reset_embedding_runtime_state
        reset_embedding_runtime_state()
    except Exception:
        pass
    return {"success": True, "results": results}


@router.post("/reset-embedding-cache")
def reset_embedding_cache(user: UserIdentity = AdminUser):
    """Clear HuggingFace model cache and force fresh model download + load."""
    import shutil, sys
    from pathlib import Path
    results = {}

    # Clear HuggingFace cache
    hf_cache = Path.home() / ".cache" / "huggingface"
    if hf_cache.exists():
        try:
            shutil.rmtree(hf_cache)
            results["hf_cache_cleared"] = str(hf_cache)
        except Exception as e:
            results["hf_cache_error"] = str(e)
    else:
        results["hf_cache"] = "not found"

    # Also clear sentence_transformers cache
    st_cache = Path.home() / ".cache" / "torch" / "sentence_transformers"
    if st_cache.exists():
        try:
            shutil.rmtree(st_cache)
            results["st_cache_cleared"] = str(st_cache)
        except Exception as e:
            results["st_cache_error"] = str(e)

    # Reinstall sentence-transformers cleanly
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--force-reinstall",
         "sentence-transformers>=2.2.0", "torch>=2.0.0", "transformers>=4.30.0",
         "--quiet"],
        capture_output=True, text=True, timeout=300,
    )
    results["reinstall"] = "ok" if r.returncode == 0 else r.stderr[-300:]

    # Reset embedding state
    try:
        from app.services.embedding_service import reset_embedding_runtime_state
        reset_embedding_runtime_state()
    except Exception:
        pass

    return {"success": True, "results": results, "note": "Restart backend, then call /admin/init-embedding"}


@router.get("/env-docker-keys")
def env_docker_keys(user: UserIdentity = AdminUser):
    """Show which keys exist in .env.docker (without values) to debug persistence."""
    import re as _re
    repo_dir = os.environ.get("REPO_DIR", "/root/aem-guides-dataset-studio")
    env_file = os.path.join(repo_dir, "backend", ".env.docker")
    if not os.path.exists(env_file):
        return {"exists": False, "path": env_file}
    keys_found = []
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key = line.split("=", 1)[0].strip()
                if key:
                    keys_found.append(key)
    # Show only key names (no values) + first char hint of value
    result = {}
    text = open(env_file).read()
    for key in set(keys_found):
        val = os.environ.get(key, "")
        # Just show length of value (not the actual value)
        m = _re.search(rf"^{_re.escape(key)}=(.*)$", text, _re.MULTILINE)
        file_val_len = len(m.group(1)) if m else 0
        result[key] = {"in_file": True, "file_val_len": file_val_len, "in_env": bool(val), "env_val_len": len(val)}
    return {"exists": True, "path": env_file, "keys": result}


@router.get("/test-jira-raw")
def test_jira_raw(user: UserIdentity = AdminUser):
    """Raw Jira connectivity test — shows exact HTTP status and error."""
    import requests as _req
    url = os.environ.get("JIRA_BASE_URL") or os.environ.get("JIRA_URL", "")
    username = os.environ.get("JIRA_USERNAME", "")
    password = os.environ.get("JIRA_PASSWORD", "")
    if not url:
        return {"error": "JIRA_URL not set", "url": "", "user": username}
    test_url = f"{url}/rest/api/2/issue/GUIDES-48304?fields=summary"
    try:
        r = _req.get(test_url, auth=(username, password), verify=False, timeout=10)
        return {
            "status": r.status_code,
            "ok": r.ok,
            "url_used": test_url[:60],
            "user": username,
            "pass_len": len(password),
            "response": r.text[:200] if not r.ok else r.json().get("fields", {}).get("summary", "")[:80],
        }
    except Exception as e:
        return {"error": str(e), "url_used": test_url[:60]}


@router.get("/process-info")
def process_info(user: UserIdentity = AdminUser):
    """Show how the backend process was started (cmdline, env file loading)."""
    import sys
    from pathlib import Path
    return {
        "python": sys.executable,
        "argv": sys.argv[:5],
        "run_local_py_loaded": any("run_local" in str(a) for a in sys.argv),
        "jira_username_in_env": os.environ.get("JIRA_USERNAME", "")[:20],
        "dotenv_loaded": os.environ.get("_DOTENV_LOADED", ""),
        "env_docker_path": str(Path(sys.executable).parent.parent / "backend" / ".env.docker"),
    }
