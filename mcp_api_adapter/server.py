"""FastMCP server: tools are thin wrappers around Dataset Studio /api/v1 REST."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_api_adapter.http_client import DatasetStudioApiClient

mcp = FastMCP("dataset-studio-api")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
for candidate in (PROJECT_ROOT, BACKEND_DIR):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

_client: DatasetStudioApiClient | None = None


def _api() -> DatasetStudioApiClient:
    global _client
    if _client is None:
        _client = DatasetStudioApiClient()
    return _client


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _uuid(label: str, value: str) -> str:
    try:
        return str(uuid.UUID((value or "").strip()))
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid UUID string") from exc


def _run_local_python_script(args: list[str], timeout_sec: int = 1800) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=str(PROJECT_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_sec,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _resolve_project_path(user_path: str) -> Path:
    raw = Path((user_path or "").strip())
    path = raw if raw.is_absolute() else PROJECT_ROOT / raw
    resolved = path.resolve()
    allowed_roots = [
        PROJECT_ROOT.resolve(),
        (PROJECT_ROOT / "output").resolve(),
        (PROJECT_ROOT / "incoming_archives").resolve(),
        (PROJECT_ROOT / "tmp").resolve(),
    ]
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise ValueError(f"Refusing path outside allowed project roots: {resolved}")
    return resolved


def _find_generated_zip(*, source_path: str = "", job_id: str = "", latest: bool = False) -> Path:
    if source_path:
        return _resolve_project_path(source_path)
    candidates: list[Path] = []
    search_roots = [
        PROJECT_ROOT / "output",
        PROJECT_ROOT / "backend" / "storage" / "zips",
        PROJECT_ROOT / "backend" / "storage",
        PROJECT_ROOT / "tmp",
    ]
    clean_job = (job_id or "").strip()
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.zip"):
            if clean_job and clean_job not in str(path):
                continue
            candidates.append(path)
    if not candidates:
        qualifier = f" for job_id={clean_job}" if clean_job else ""
        raise FileNotFoundError(f"No generated ZIP found{qualifier}. Pass source_path explicitly.")
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    if latest or clean_job:
        return candidates[0].resolve()
    raise ValueError("Pass source_path, job_id, or latest=True to choose which generated ZIP to upload.")


def _extract_zip_for_aem_upload(source: Path) -> Path:
    import hashlib
    import shutil
    import zipfile

    short_name = f"{source.stem[:24]}-{hashlib.sha256(str(source).encode('utf-8')).hexdigest()[:10]}"
    extract_root = PROJECT_ROOT / "tmp" / "aem_upload_extract" / short_name
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)
    root_resolved = extract_root.resolve()
    with zipfile.ZipFile(source, "r") as archive:
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Refusing unsafe ZIP entry: {member.filename}")
            destination = (extract_root / member_path).resolve()
            if destination != root_resolved and root_resolved not in destination.parents:
                raise ValueError(f"Refusing unsafe ZIP entry: {member.filename}")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    children = [child for child in extract_root.iterdir()]
    return children[0] if len(children) == 1 and children[0].is_dir() else extract_root


@mcp.tool()
def list_presets() -> str:
    """List recipe presets from the API (GET /api/v1/presets)."""
    return _dump(_api().request_json("GET", "/api/v1/presets"))


@mcp.tool()
def create_job(config: dict) -> str:
    """Create and run a dataset job immediately (POST /api/v1/jobs). Body: { \"config\": <job config dict> }."""
    return _dump(_api().request_json("POST", "/api/v1/jobs", json_body={"config": config}))


@mcp.tool()
def get_job(job_id: str) -> str:
    """Get one job by id (GET /api/v1/jobs/{job_id})."""
    jid = _uuid("job_id", job_id)
    return _dump(_api().request_json("GET", f"/api/v1/jobs/{jid}"))


@mcp.tool()
def schedule_job(config: dict, scheduled_at: str, timezone: str = "UTC") -> str:
    """Schedule a future job (POST /api/v1/jobs/schedule). scheduled_at: ISO-8601 string."""
    body = {"config": config, "scheduled_at": scheduled_at, "timezone": timezone}
    return _dump(_api().request_json("POST", "/api/v1/jobs/schedule", json_body=body))


@mcp.tool()
def search_dataset_files(job_id: str, query: str, file_type: str = "") -> str:
    """Search files inside a completed dataset (GET /api/v1/datasets/{job_id}/search)."""
    jid = _uuid("job_id", job_id)
    params: dict[str, str] = {"query": query}
    if file_type.strip():
        params["file_type"] = file_type.strip()
    return _dump(_api().request_json("GET", f"/api/v1/datasets/{jid}/search", params=params))


@mcp.tool()
def save_recipe(
    name: str,
    recipe_config: dict,
    description: str = "",
    is_public: bool = False,
    tags: list | None = None,
) -> str:
    """Save a reusable recipe (POST /api/v1/recipes/save)."""
    body: dict[str, Any] = {
        "name": name,
        "recipe_config": recipe_config,
        "is_public": is_public,
        "tags": tags or [],
    }
    if description.strip():
        body["description"] = description.strip()
    return _dump(_api().request_json("POST", "/api/v1/recipes/save", json_body=body))


@mcp.tool()
def preview_conref_recipe(
    topic_count: int = 50,
    reusable_elements_per_topic: int = 3,
    conref_density: float = 0.3,
    include_map: bool = True,
    pretty_print: bool = True,
) -> str:
    """Preview conref pack recipe estimates (POST /api/v1/aem-recipes/conref/preview)."""
    body = {
        "topic_count": topic_count,
        "reusable_elements_per_topic": reusable_elements_per_topic,
        "conref_density": conref_density,
        "include_map": include_map,
        "pretty_print": pretty_print,
    }
    return _dump(_api().request_json("POST", "/api/v1/aem-recipes/conref/preview", json_body=body))


@mcp.tool()
def preview_glossary_recipe(
    entry_count: int = 100,
    include_acronyms: bool = True,
    include_map: bool = True,
) -> str:
    """Preview glossary pack recipe estimates (POST /api/v1/specialized/glossary/preview)."""
    body = {
        "entry_count": entry_count,
        "include_acronyms": include_acronyms,
        "include_map": include_map,
    }
    return _dump(_api().request_json("POST", "/api/v1/specialized/glossary/preview", json_body=body))


@mcp.tool()
def get_rag_status(tenant_id: str = "default") -> str:
    """RAG / vector index status (GET /api/v1/ai/rag-status)."""
    return _dump(
        _api().request_json("GET", "/api/v1/ai/rag-status", params={"tenant_id": tenant_id})
    )


@mcp.tool()
def guides_test_plan_generator(jira_key: str, tenant_id: str = "kone", evidence_k: int = 8) -> str:
    """Build the evidence packet for `/guides-test-plan-generator GUIDES-12345`."""
    body = {
        "jira_key": jira_key,
        "tenant_id": tenant_id,
        "evidence_k": evidence_k,
    }
    return _dump(_api().request_json("POST", "/api/v1/mcp/guides-test-plan-generator", json_body=body))


@mcp.tool()
def publishing_ticket_dita_qa_packet(jira_key: str, tenant_id: str = "kone", evidence_k: int = 8) -> str:
    """Claude MCP-only helper for publishing/PDF2/HTML/HTML5 Jira tickets with DITA-OT evidence."""
    try:
        from app.services.guides_test_plan_generator_service import (
            build_guides_test_plan_packet,
            is_publishing_transform_ticket,
            render_guides_test_plan_packet_markdown,
        )

        packet = build_guides_test_plan_packet(jira_key, tenant_id=tenant_id, evidence_k=evidence_k)
        if not is_publishing_transform_ticket(packet.get("issue") or {}):
            return _dump(
                {
                    "refused": True,
                    "reason": "Only publishing/PDF2/HTML/HTML5/DITA-OT transformation Jira tickets are allowed.",
                    "jira_key": packet.get("jira_key"),
                    "detected_labels": (packet.get("issue") or {}).get("labels", []),
                    "fallback_tool": "guides_test_plan_generator",
                }
            )
        return render_guides_test_plan_packet_markdown(packet)
    except Exception:
        body = {"jira_key": jira_key, "tenant_id": tenant_id, "evidence_k": evidence_k}
        return _dump(_api().request_json("POST", "/api/v1/mcp/guides-test-plan-generator", json_body=body))


@mcp.tool()
async def generate_dita_ot_output(
    prompt: str = "DITA-OT PDF smoke test",
    input_map: str = "",
    output_format: str = "pdf",
    package_name: str = "",
    timeout_seconds: int = 180,
) -> str:
    """
    Generate or publish DITA content with DITA-OT and return rich QA guidance.

    This REST-adapter MCP tool intentionally reuses the backend publishing
    service so teammates see the same dataset summary, expected behavior,
    QA checklist, and PDF/HTML inspection areas as the chatbot UI.
    """
    try:
        from app.services.dita_ot_publish_service import publish_with_dita_ot

        result = await publish_with_dita_ot(
            input_map=input_map or None,
            prompt=prompt,
            output_format=output_format,
            package_name=package_name,
            timeout_seconds=max(1, int(timeout_seconds)),
        )
        return _dump(result)
    except Exception as exc:
        return f"DITA-OT output generation failed: {exc}"


@mcp.tool()
def upload_dataset_to_aem(
    source_path: str,
    target_path: str,
    aem_base_url: str = "",
    username: str = "",
    password: str = "",
    access_token: str = "",
    max_concurrent: int = 20,
    max_upload_files: int = 70000,
) -> str:
    """Upload a project-local generated dataset directory or ZIP to AEM /content/dam."""
    import os

    try:
        source = _resolve_project_path(source_path)
        if not source.exists():
            return f"Source path does not exist: {source}"
        target = (target_path or "").strip()
        if not target.startswith("/content/dam/") and not target.startswith("content/dam/"):
            return "Refusing upload: target_path must start with /content/dam/."

        upload_source = source
        if source.is_file():
            if source.suffix.lower() != ".zip":
                return "source_path must be a directory or .zip file."
            upload_source = _extract_zip_for_aem_upload(source)

        base_url = (aem_base_url or os.getenv("AEM_BASE_URL") or os.getenv("AEM_AUTHOR_URL") or "").strip()
        user = username or os.getenv("AEM_USERNAME") or ""
        pwd = password or os.getenv("AEM_PASSWORD") or ""
        token = access_token or os.getenv("AEM_ACCESS_TOKEN") or ""
        if not base_url:
            return "Missing AEM base URL. Pass aem_base_url or set AEM_BASE_URL/AEM_AUTHOR_URL."
        if not token and not (user and pwd):
            return "Missing AEM auth. Pass access_token or username/password, or set AEM_ACCESS_TOKEN or AEM_USERNAME/AEM_PASSWORD."

        from app.services.aem_upload_service import get_upload_service

        result = get_upload_service().upload_dataset(
            source_path=str(upload_source),
            aem_base_url=base_url,
            target_path=target,
            username=user,
            password=pwd,
            access_token=token,
            max_concurrent=max(1, min(int(max_concurrent), 100)),
            max_upload_files=max(1, int(max_upload_files)),
        )
        safe_result = dict(result)
        for secret_key in ("password", "accessToken", "access_token", "token"):
            if secret_key in safe_result:
                safe_result[secret_key] = "***"
        return _dump(safe_result)
    except Exception as exc:
        return f"AEM upload failed: {exc}"


@mcp.tool()
def upload_mcp_generated_data_to_aem(
    target_path: str,
    source_path: str = "",
    job_id: str = "",
    latest: bool = False,
    aem_base_url: str = "",
    username: str = "",
    password: str = "",
    access_token: str = "",
    max_concurrent: int = 20,
    max_upload_files: int = 70000,
) -> str:
    """Upload an MCP-generated ZIP/folder to AEM Assets by source_path, job_id, or latest=True."""
    try:
        generated = _find_generated_zip(source_path=source_path, job_id=job_id, latest=latest)
    except Exception as exc:
        return f"Could not resolve generated MCP data: {exc}"
    return upload_dataset_to_aem(
        source_path=str(generated),
        target_path=target_path,
        aem_base_url=aem_base_url,
        username=username,
        password=password,
        access_token=access_token,
        max_concurrent=max_concurrent,
        max_upload_files=max_upload_files,
    )


@mcp.tool()
def build_dita_ot_issue_corpus(
    input_url: str = "https://github.com/dita-ot/dita-ot/issues?q=is%3Aissue%20state%3Aclosed",
    output_dir: str = "dita-ot-closed-issue-corpus",
    max_pages: int = 0,
) -> str:
    """Build local DITA topics from DITA-OT GitHub issues. Requires GITHUB_TOKEN for full large-repo pagination."""
    safe_output = (output_dir or "dita-ot-closed-issue-corpus").strip()
    if Path(safe_output).is_absolute() or ".." in Path(safe_output).parts:
        return "Refusing unsafe output_dir. Use a relative folder name inside the project."
    args = [
        "scripts/convert_dita_ot_issues_to_dita.py",
        "--input",
        input_url,
        "--output-dir",
        safe_output,
        "--reset",
    ]
    if max_pages > 0:
        args.extend(["--max-pages", str(max_pages)])
    code, stdout, stderr = _run_local_python_script(args)
    if code != 0:
        return f"DITA-OT issue corpus build failed (exit {code}).\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
    return f"DITA-OT issue corpus built successfully.\n\n{stdout}"


@mcp.tool()
def index_dita_ot_issue_corpus(
    corpus_root: str = "dita-ot-closed-issue-corpus/topics",
    output_json: str = "backend/storage/dita_ot_issue_behavior_chunks.json",
    upsert_chroma: bool = False,
) -> str:
    """Index converted DITA-OT issue topics into retrieval JSON; Chroma upsert is opt-in."""
    corpus_path = PROJECT_ROOT / corpus_root
    output_path = PROJECT_ROOT / output_json
    if not corpus_path.exists():
        return f"Corpus root does not exist: {corpus_path}. Run build_dita_ot_issue_corpus first."
    if PROJECT_ROOT not in output_path.resolve().parents:
        return "Refusing unsafe output_json outside the project."
    args = [
        "scripts/index_dita_behavior_corpus.py",
        "--corpus-root",
        str(corpus_path),
        "--output",
        str(output_path),
    ]
    if upsert_chroma:
        args.append("--upsert-chroma")
    code, stdout, stderr = _run_local_python_script(args)
    if code != 0:
        return f"DITA-OT issue corpus indexing failed (exit {code}).\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
    return f"DITA-OT issue corpus indexed successfully.\n\n{stdout}"


@mcp.tool()
def show_mcp_rag_corpus_status() -> str:
    """Show local JSON corpus counts used by MCP/test-plan retrieval fallback."""
    checks = [
        ("AEM Guides behavior chunks", PROJECT_ROOT / "backend/storage/aem_guides_behavior_chunks.json"),
        ("DITA-OT issue behavior chunks", PROJECT_ROOT / "backend/storage/dita_ot_issue_behavior_chunks.json"),
        ("Manual AEM Guides chunks", PROJECT_ROOT / "backend/storage/manual_aem_guides_doc_chunks.json"),
        ("Primary AEM Guides chunks", PROJECT_ROOT / "backend/storage/aem_guides_doc_chunks.json"),
    ]
    rows: dict[str, Any] = {}
    for label, path in checks:
        if not path.exists():
            rows[label] = {"status": "missing", "path": str(path)}
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows[label] = {
                "status": "ok",
                "records": len(data) if isinstance(data, list) else "non-list",
                "bytes": path.stat().st_size,
                "path": str(path),
            }
        except Exception as exc:
            rows[label] = {"status": "error", "error": str(exc), "path": str(path)}
    topic_dir = PROJECT_ROOT / "dita-ot-closed-issue-corpus/topics"
    rows["Converted DITA-OT issue topics"] = {
        "status": "ok" if topic_dir.exists() else "missing",
        "files": len(list(topic_dir.glob("*.dita"))) if topic_dir.exists() else 0,
        "path": str(topic_dir),
    }
    return _dump(rows)


@mcp.tool()
def generate_from_text(
    text: str,
    instructions: str = "",
    async_mode: bool = False,
    skip_rag_check: bool = True,
) -> str:
    """Generate DITA from raw text via API (POST /api/v1/ai/generate-from-text)."""
    body: dict[str, str] = {"text": text}
    if instructions.strip():
        body["instructions"] = instructions.strip()
    params = {"async": async_mode, "skip_rag_check": skip_rag_check}
    return _dump(_api().request_json("POST", "/api/v1/ai/generate-from-text", params=params, json_body=body))


@mcp.tool()
def create_chat_session() -> str:
    """Create a new chat session (POST /api/v1/chat/sessions)."""
    return _dump(_api().request_json("POST", "/api/v1/chat/sessions", json_body={}))


@mcp.tool()
def send_chat_message(
    session_id: str,
    content: str,
    context: dict | None = None,
    human_prompts: bool | None = None,
) -> str:
    """Send a chat message; aggregates SSE chunks into assistant_text (POST /api/v1/chat/sessions/{id}/messages)."""
    sid = _uuid("session_id", session_id)
    body: dict[str, Any] = {"content": content}
    if context is not None:
        body["context"] = context
    if human_prompts is not None:
        body["human_prompts"] = human_prompts
    return _dump(_api().post_sse_chat(f"/api/v1/chat/sessions/{sid}/messages", body))


@mcp.tool()
def regenerate_chat_response(
    session_id: str,
    context: dict | None = None,
    human_prompts: bool | None = None,
) -> str:
    """Regenerate last assistant reply; aggregates SSE (POST /api/v1/chat/sessions/{id}/regenerate)."""
    sid = _uuid("session_id", session_id)
    body: dict[str, Any] = {}
    if context is not None:
        body["context"] = context
    if human_prompts is not None:
        body["human_prompts"] = human_prompts
    return _dump(_api().post_sse_chat(f"/api/v1/chat/sessions/{sid}/regenerate", body))
