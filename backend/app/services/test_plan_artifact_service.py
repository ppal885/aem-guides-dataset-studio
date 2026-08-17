"""Shared filesystem storage for team-visible AEM Guides test plans."""

from __future__ import annotations

import re
import subprocess
import sys
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEST_PLANS_DIR = PROJECT_ROOT / "output" / "test-plans"
QE_REVIEWS_DIR = TEST_PLANS_DIR / ".qe-reviews"
REVISIONS_DIR = TEST_PLANS_DIR / ".revisions"
PIPELINE_MEMORY_DIR = TEST_PLANS_DIR / ".pipeline-memory"
PIPELINE_MEMORY_INDEX = PIPELINE_MEMORY_DIR / "index.json"
JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
REVIEW_STATUS_RE = re.compile(r"\*\*Review status:\*\*\s*(.+)", re.I)
VALIDATOR = PROJECT_ROOT / "claude-skills" / "aem-guides-test-scenario-generator" / "scripts" / "validate_test_plan.py"


def _normalize_jira_key(value: str) -> str:
    match = re.search(r"[A-Z][A-Z0-9]+-\d+", (value or "").strip().upper())
    if not match:
        raise ValueError("Expected a Jira key such as GUIDES-36430.")
    return match.group(0)


def _plan_path(jira_key: str) -> Path:
    key = _normalize_jira_key(jira_key)
    return TEST_PLANS_DIR / f"{key}-test-plan.md"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _review_path(jira_key: str) -> Path:
    key = _normalize_jira_key(jira_key)
    return QE_REVIEWS_DIR / f"{key}-qe-review.json"


def _revision_dir(jira_key: str) -> Path:
    return REVISIONS_DIR / _normalize_jira_key(jira_key)


def _pipeline_memory_dir(jira_key: str) -> Path:
    return PIPELINE_MEMORY_DIR / _normalize_jira_key(jira_key)


def _parse_review_status(markdown: str) -> str:
    match = REVIEW_STATUS_RE.search(markdown or "")
    if not match:
        return "Unknown"
    return match.group(1).strip().split("\n", 1)[0].strip()


def _stat_entry(path: Path) -> dict[str, Any]:
    stat = path.stat()
    text = path.read_text(encoding="utf-8")
    jira_key = path.name.split("-test-plan.md", 1)[0]
    return {
        "jira_key": jira_key,
        "filename": path.name,
        "title": _extract_title(text),
        "review_status": _parse_review_status(text),
        "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "size_bytes": stat.st_size,
        "view_url": f"/test-plans?jira={jira_key}",
        "api_url": f"/api/v1/test-plans/{jira_key}",
    }


def _extract_title(markdown: str) -> str:
    for line in (markdown or "").splitlines():
        if line.startswith("# Test Plan:"):
            return line.replace("# Test Plan:", "", 1).strip()
    return ""


def list_test_plans() -> list[dict[str, Any]]:
    TEST_PLANS_DIR.mkdir(parents=True, exist_ok=True)
    entries = [_stat_entry(path) for path in TEST_PLANS_DIR.glob("*-test-plan.md")]
    entries.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return entries


def get_test_plan(jira_key: str) -> dict[str, Any]:
    path = _plan_path(jira_key)
    if not path.is_file():
        raise FileNotFoundError(f"No shared test plan found for {_normalize_jira_key(jira_key)}.")
    text = path.read_text(encoding="utf-8")
    stat = path.stat()
    key = _normalize_jira_key(jira_key)
    return {
        "jira_key": key,
        "filename": path.name,
        "title": _extract_title(text),
        "review_status": _parse_review_status(text),
        "markdown": text,
        "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "view_url": f"/test-plans?jira={key}",
    }


def save_test_plan(jira_key: str, markdown: str) -> dict[str, Any]:
    key = _normalize_jira_key(jira_key)
    content = (markdown or "").strip()
    if not content:
        raise ValueError("markdown must not be empty.")
    if not content.lstrip().startswith("# Test Plan:"):
        content = f"# Test Plan: {key}\n\n{content}"
    TEST_PLANS_DIR.mkdir(parents=True, exist_ok=True)
    path = _plan_path(key)
    if path.exists():
        _preserve_revision(key, path, reason="save_test_plan_overwrite")
    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    return get_test_plan(key)


def _preserve_revision(jira_key: str, path: Path, *, reason: str) -> str:
    if not path.exists():
        return ""
    revision_dir = _revision_dir(jira_key)
    revision_dir.mkdir(parents=True, exist_ok=True)
    target = revision_dir / f"{_utc_stamp()}-{reason}-{path.name}"
    shutil.copy2(path, target)
    return str(target)


def _replace_review_status(markdown: str, status: str) -> str:
    if REVIEW_STATUS_RE.search(markdown or ""):
        return REVIEW_STATUS_RE.sub(f"**Review status:** {status}", markdown, count=1)
    return (markdown.rstrip() + f"\n\n**Review status:** {status}\n") if markdown else f"**Review status:** {status}\n"


def _read_review_record(jira_key: str) -> dict[str, Any]:
    path = _review_path(jira_key)
    if not path.exists():
        return {
            "jira_key": _normalize_jira_key(jira_key),
            "current_status": "Draft",
            "decisions": [],
            "revision_history": [],
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "jira_key": _normalize_jira_key(jira_key),
            "current_status": "Review record unreadable",
            "decisions": [],
            "revision_history": [],
        }


def record_qe_review_decision(
    jira_key: str,
    *,
    action: str,
    reviewer: str = "",
    comments: str = "",
) -> dict[str, Any]:
    """Record a provider-neutral QE review decision and preserve the prior plan revision."""
    key = _normalize_jira_key(jira_key)
    normalized = (action or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in {"approve", "request_changes"}:
        raise ValueError("action must be approve or request_changes.")
    plan = get_test_plan(key)
    plan_path = _plan_path(key)
    revision_path = _preserve_revision(key, plan_path, reason=f"qe_{normalized}")
    status = "QE Approved" if normalized == "approve" else "QE Changes Requested"
    updated_markdown = _replace_review_status(plan["markdown"], status)
    plan_path.write_text(updated_markdown if updated_markdown.endswith("\n") else updated_markdown + "\n", encoding="utf-8")

    record = _read_review_record(key)
    decision = {
        "decision": "QE_APPROVED" if normalized == "approve" else "QE_CHANGES_REQUESTED",
        "review_status": status,
        "reviewer": reviewer.strip() or "QE / QA owner",
        "comments": comments.strip(),
        "revision_path": revision_path,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    record["current_status"] = status
    record.setdefault("decisions", []).append(decision)
    if revision_path:
        record.setdefault("revision_history", []).append(
            {
                "revision_path": revision_path,
                "reason": f"qe_{normalized}",
                "created_at": decision["decided_at"],
            }
        )
    QE_REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    _review_path(key).write_text(json.dumps(record, indent=2), encoding="utf-8")
    return {
        **get_test_plan(key),
        "qe_review": record,
        "decision": decision,
    }


def record_pipeline_memory(result: Any) -> dict[str, Any]:
    """Persist one immutable pipeline run snapshot for later recall/comparison."""
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result or {})
    key = _normalize_jira_key(str(payload.get("jira_key") or ""))
    correlation_id = str(payload.get("correlation_id") or _utc_stamp())
    created_at = datetime.now(timezone.utc).isoformat()
    memory_dir = _pipeline_memory_dir(key)
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_path = memory_dir / f"{_utc_stamp()}-{correlation_id}.json"
    payload["memory_record"] = {
        "jira_key": key,
        "correlation_id": correlation_id,
        "created_at": created_at,
        "memory_path": str(memory_path),
    }
    memory_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    entry = _pipeline_memory_entry(memory_path, payload)
    index = _read_pipeline_memory_index()
    rows = [
        row for row in index.get("runs", [])
        if row.get("memory_path") != entry["memory_path"]
    ]
    rows.append(entry)
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    index = {
        "updated_at": created_at,
        "runs": rows[:500],
    }
    PIPELINE_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    PIPELINE_MEMORY_INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def list_pipeline_memory(jira_key: str | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
    """List retained pipeline runs, newest first."""
    key = _normalize_jira_key(jira_key) if jira_key else ""
    rows = list(_read_pipeline_memory_index().get("runs") or [])
    if key:
        rows = [row for row in rows if row.get("jira_key") == key]
        if not rows:
            rows = _scan_pipeline_memory_for_key(key)
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return rows[: max(1, min(int(limit or 50), 200))]


def get_pipeline_memory(
    jira_key: str,
    *,
    correlation_id: str | None = None,
    latest: bool = True,
) -> dict[str, Any]:
    """Load a retained pipeline run snapshot."""
    key = _normalize_jira_key(jira_key)
    rows = list_pipeline_memory(key, limit=200)
    if correlation_id:
        rows = [row for row in rows if row.get("correlation_id") == correlation_id]
    if not rows:
        raise FileNotFoundError(f"No pipeline memory found for {key}.")
    selected = rows[0] if latest else rows[-1]
    path = Path(str(selected.get("memory_path") or ""))
    if not path.is_file():
        raise FileNotFoundError(f"Pipeline memory file is missing for {key}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_pipeline_memory_index() -> dict[str, Any]:
    if not PIPELINE_MEMORY_INDEX.exists():
        return {"updated_at": "", "runs": []}
    try:
        return json.loads(PIPELINE_MEMORY_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {"updated_at": "", "runs": []}


def _pipeline_memory_entry(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    qe = payload.get("qe_handoff") if isinstance(payload.get("qe_handoff"), dict) else {}
    brief = payload.get("ticket_brief") if isinstance(payload.get("ticket_brief"), dict) else {}
    return {
        "jira_key": payload.get("jira_key") or brief.get("jira_key") or "",
        "correlation_id": payload.get("correlation_id") or "",
        "created_at": (payload.get("memory_record") or {}).get("created_at") or datetime.now(timezone.utc).isoformat(),
        "summary": brief.get("summary") or "",
        "score": score.get("overall"),
        "routing_status": score.get("routing_status"),
        "review_status": qe.get("review_status"),
        "stages_completed": payload.get("stages_completed") or [],
        "has_draft_test_plan": bool(payload.get("draft_test_plan_markdown")),
        "memory_path": str(path),
    }


def _scan_pipeline_memory_for_key(jira_key: str) -> list[dict[str, Any]]:
    memory_dir = _pipeline_memory_dir(jira_key)
    if not memory_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in memory_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows.append(_pipeline_memory_entry(path, payload))
        except Exception:
            continue
    return rows


def validate_saved_test_plan(jira_key: str) -> dict[str, Any]:
    plan = get_test_plan(jira_key)
    if not VALIDATOR.is_file():
        return {"valid": False, "errors": ["Validator script not found on server."]}
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR), str(_plan_path(jira_key))],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    errors = [line.replace("ERROR: ", "").strip() for line in output.splitlines() if line.startswith("ERROR:")]
    return {
        "valid": completed.returncode == 0,
        "errors": errors,
        "output": output.strip(),
        "jira_key": plan["jira_key"],
    }
