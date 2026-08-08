#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnose and repair Jira QA RAG indexing on the VM.

Run with the backend venv from repo root:

    backend/.venv/bin/python scripts/repair_jira_rag_on_vm.py --check
    backend/.venv/bin/python scripts/repair_jira_rag_on_vm.py --issue GUIDES-12345 --force
    backend/.venv/bin/python scripts/repair_jira_rag_on_vm.py --recent-days 7 --limit 300 --force
    backend/.venv/bin/python scripts/repair_jira_rag_on_vm.py --incremental --limit 100

This script intentionally bypasses HTTP auth/curl confusion and loads the same
systemd EnvironmentFile (`.env.docker`) used by `aem-backend.service`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env.docker"

for candidate in (BACKEND_DIR, PROJECT_ROOT):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)


SECRET_KEY_PATTERN = re.compile(r"(PASSWORD|TOKEN|SECRET|KEY)$", re.I)
JIRA_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--project", default="", help="Jira project key; defaults to env or GUIDES")
    parser.add_argument("--issue", default="", help="Index one Jira issue key, e.g. GUIDES-12345")
    parser.add_argument("--recent-days", type=int, default=0, help="Index project issues updated in the last N days")
    parser.add_argument("--incremental", action="store_true", help="Run project incremental indexing")
    parser.add_argument("--backfill", action="store_true", help="Run project backfill indexing")
    parser.add_argument("--jql", default="", help="Run explicit JQL indexing")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--force", action="store_true", help="Force reindex existing issue chunks")
    parser.add_argument("--check", action="store_true", help="Only print configuration and service readiness")
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    if not path.exists():
        print_json({"warning": f"env file not found: {path}"})
        return
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        if " " in name:
            print_json({"warning": f"ignored malformed env name at line {line_number}: {name!r}"})
            continue
        value = strip_env_quotes(value)
        os.environ[name] = value


def strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def masked_env(keys: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in keys:
        value = os.getenv(key, "")
        if not value:
            out[key] = ""
        elif SECRET_KEY_PATTERN.search(key):
            out[key] = "***SET***"
        else:
            out[key] = value
    return out


def readiness() -> dict[str, Any]:
    from app.services.embedding_service import is_embedding_available
    from app.services.jira_client import JiraClient
    from app.services.jira_qa_index_service import _jira_configured, resolve_jira_qa_project_key
    from app.services.jira_sync_state import load_jira_qa_sync_state, sync_cursor_health
    from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, get_collection_count, is_chroma_available

    client = JiraClient()
    chroma_ok = bool(is_chroma_available())
    embedding_ok = bool(is_embedding_available())
    count = get_collection_count(CHROMA_COLLECTION_JIRA_QA) if chroma_ok else 0
    project = resolve_jira_qa_project_key()
    sync_state_id = f"project:{project}"
    sync_state = load_jira_qa_sync_state(sync_state_id)
    cursor_health = sync_cursor_health(sync_state, project_key=project)
    return {
        "env": masked_env(
            [
                "JIRA_URL",
                "JIRA_BASE_URL",
                "JIRA_USERNAME",
                "JIRA_PASSWORD",
                "JIRA_EMAIL",
                "JIRA_API_TOKEN",
                "JIRA_PAT",
                "JIRA_BEARER_TOKEN",
                "JIRA_PROJECT_KEY",
                "JIRA_QA_RAG_PROJECT_KEY",
                "JIRA_API_VERSION",
                "JIRA_SSL_VERIFY",
                "CHROMA_DB_PATH",
                "CHROMA_PERSIST_DIRECTORY",
                "DITA_EMBEDDING_MODEL_PATH",
            ]
        ),
        "jira_configured": bool(_jira_configured(client)),
        "jira_base_url": client.base_url,
        "jira_user": client.username or client.email,
        "jira_auth_mode": getattr(client, "auth_mode", "unknown"),
        "resolved_project": project,
        "chroma_available": chroma_ok,
        "embedding_available": embedding_ok,
        "jira_qa_collection_count": count,
        "incremental_sync_cursor": {
            "sync_state_id": sync_state_id,
            "valid": bool(cursor_health["valid"]),
            "health": cursor_health,
            "state": sync_state.model_dump(mode="json"),
            "repair_command": (
                f"bash scripts/bootstrap_jira_sync_cursor_vm.sh --project {project} --apply"
            ),
        },
    }


def smoke_jira(issue_key: str) -> dict[str, Any]:
    from app.services.jira_client import JiraClient

    client = JiraClient()
    fetch_mode = "filtered_fields"
    try:
        issue = client.get_issue(issue_key, fields="summary,status,issuetype,updated")
    except Exception as exc:
        if getattr(getattr(exc, "response", None), "status_code", None) != 403:
            raise
        issue = client.get_issue_legacy(issue_key)
        fetch_mode = "legacy_full_issue_fallback"
    fields = issue.get("fields") or {}
    status = fields.get("status") or {}
    issue_type = fields.get("issuetype") or {}
    return {
        "key": issue.get("key") or issue_key,
        "fetch_mode": fetch_mode,
        "summary": str(fields.get("summary") or "")[:240],
        "status": status.get("name") if isinstance(status, dict) else "",
        "issue_type": issue_type.get("name") if isinstance(issue_type, dict) else "",
        "updated": fields.get("updated") or "",
    }


def build_jql(args: argparse.Namespace, project: str) -> str:
    if args.jql.strip():
        return args.jql.strip()
    if args.issue.strip():
        issue = args.issue.strip().upper()
        if not JIRA_KEY_PATTERN.match(issue):
            raise SystemExit(f"Invalid --issue value: {issue}")
        return f'issue = "{issue}"'
    if args.recent_days > 0:
        return f"project = {project} AND updated >= -{args.recent_days}d ORDER BY updated ASC"
    return ""


def run_index(args: argparse.Namespace, project: str) -> dict[str, Any]:
    from app.services.jira_qa_index_service import (
        index_jira_project_backfill,
        index_jira_project_incremental,
        index_jql_to_chroma,
    )

    if args.incremental:
        return index_jira_project_incremental(project, limit=args.limit, force_reindex=args.force)
    if args.backfill:
        return index_jira_project_backfill(project, limit=args.limit, force_reindex=args.force)

    jql = build_jql(args, project)
    if not jql:
        raise SystemExit("No indexing action selected. Use --issue, --recent-days, --incremental, --backfill, or --jql.")
    return index_jql_to_chroma(
        jql,
        limit=args.limit,
        force_reindex=args.force,
        persist_sync_state=not bool(args.issue.strip()),
        sync_state_id=f"project:{project}",
    )


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def index_result_failure_reasons(result: dict[str, Any]) -> list[str]:
    """Classify structured index failures that must produce a nonzero process exit."""
    reasons: list[str] = []
    if result.get("error"):
        reasons.append("top_level_error")

    errors_count = _positive_int(result.get("errors_count"))
    if errors_count:
        reasons.append(f"errors_count={errors_count}")
    elif result.get("errors"):
        reasons.append("errors_present")

    issues_failed = _positive_int(result.get("issues_failed"))
    if issues_failed:
        reasons.append(f"issues_failed={issues_failed}")
    if result.get("sync_state_error"):
        reasons.append("sync_state_persistence_failed")
    return reasons


def safe_jira_error(exc: Exception) -> dict[str, Any]:
    message = str(exc)
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    guidance = []
    if status_code == 401 or "401" in message:
        guidance = [
            "Jira rejected authentication. Network and Chroma are OK; fix credentials/token.",
            "For Jira Data Center/corp SSO, prefer a PAT: set JIRA_PAT or JIRA_BEARER_TOKEN in .env.docker.",
            "If using basic auth, verify JIRA_USERNAME/JIRA_PASSWORD by logging in with the same account and ensure special characters are quoted in .env.docker.",
            "After editing .env.docker, run: sudo systemctl restart aem-backend.service",
        ]
    elif status_code == 403 or "403" in message:
        guidance = [
            "Jira authentication succeeded but the user cannot browse this issue/project.",
            "Grant Browse Project permission or use a Jira account/token with GUIDES access.",
        ]
    return {"error": message, "status_code": status_code, "guidance": guidance}


def main() -> int:
    args = parse_args()
    load_env_file(args.env_file)

    from app.services.jira_qa_index_service import resolve_jira_qa_project_key

    project = (args.project or resolve_jira_qa_project_key()).strip().upper() or "GUIDES"
    before = readiness()
    print_json({"phase": "readiness_before", **before})

    if args.issue:
        try:
            print_json({"phase": "jira_smoke", "issue": smoke_jira(args.issue.strip().upper())})
        except Exception as exc:
            print_json({"phase": "jira_smoke_failed", **safe_jira_error(exc)})
            return 2

    if args.check:
        return 0

    result = run_index(args, project)
    failure_reasons = index_result_failure_reasons(result)
    exit_code = 1 if failure_reasons else 0
    print_json(
        {
            "phase": "index_result",
            "success": not failure_reasons,
            "exit_code": exit_code,
            "failure_reasons": failure_reasons,
            "result": result,
        }
    )
    after = readiness()
    print_json({"phase": "readiness_after", **after})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
