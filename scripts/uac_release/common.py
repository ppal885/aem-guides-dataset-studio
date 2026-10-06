"""Shared pieces for the UAC release automation: config, env, lock, Jira REST, logging.

Standard library only, so the scripts run on a VM without the backend's
dependencies. Jira settings use the same variable names as the backend:
JIRA_BASE_URL (or JIRA_URL), JIRA_PAT (or JIRA_BEARER_TOKEN), JIRA_SSL_VERIFY.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = REPO_ROOT / ".claude" / "skills" / "test-plan-generation" / "scripts"
STATUS_FILE = "status.json"
UAC_FILE = "UAC.md"
PLAN_FILE = "test-plan.md"
DECISIONS_FILE = "DECISIONS.md"
DECISION_BODY_FILE = "decision-body.txt"
DOC_RESEARCH_FILE = "DOC_RESEARCH.json"
SOURCE_COVERAGE_FILE = "SOURCE_COVERAGE.json"
SURFACE_INVENTORY_FILE = "SURFACE_INVENTORY.json"
JIRA_SOURCE_FILE = "jira-source.json"
HOTFIX_SCOPE_FILE = "HOTFIX_SCOPE.json"
EVIDENCE_FILE = "UAC_EVIDENCE.json"
RUNTIME_FALLBACK_FILE = "RUNTIME_FALLBACK.json"
# The UAC is in the Acceptance Criteria field, but Jira did not render it as wiki markup:
# no comment or done label was added, and the ticket is never generated again.
WRITTEN_UNRENDERED = "WRITTEN_UNRENDERED"
FINAL_STATES = {"POSTED", "FIELD_KEPT", WRITTEN_UNRENDERED}


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding values already set."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    for required in ("jql", "output_dir", "labels", "acceptance_criteria_field"):
        if required not in config:
            raise ValueError(f"config is missing '{required}'")
    return config


def setup_logging(log_dir: Path, name: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(fmt)
        logfile = logging.FileHandler(log_dir / f"{name}-{time.strftime('%Y%m%d')}.log", encoding="utf-8")
        logfile.setFormatter(fmt)
        logger.addHandler(stream)
        logger.addHandler(logfile)
    return logger


class RunLock:
    """Single-run lock so two scheduled runs never overlap. A lock older than
    max_age_seconds is treated as left behind by a crashed run."""

    def __init__(self, path: Path, max_age_seconds: int) -> None:
        self.path = path
        self.max_age = max_age_seconds
        self.acquired = False

    def __enter__(self) -> "RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and time.time() - self.path.stat().st_mtime > self.max_age:
            self.path.unlink()
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError(f"another run holds {self.path}") from exc
        with os.fdopen(fd, "w") as handle:
            handle.write(str(os.getpid()))
        self.acquired = True
        return self

    def __exit__(self, *exc: object) -> None:
        if self.acquired and self.path.exists():
            self.path.unlink()


POSTED_BODIES_FILE = "posted-bodies.txt"


def text_key(text: str) -> str:
    """Hash of a field text with all whitespace runs collapsed, so Jira's line endings do not matter."""
    return hashlib.sha256(" ".join((text or "").split()).encode("utf-8")).hexdigest()


def remember_posted_body(ticket_dir: Path, field_body: str) -> None:
    """Keep a hash of every text the runner wrote into the field (field-body.txt keeps only the last one)."""
    with (ticket_dir / POSTED_BODIES_FILE).open("a", encoding="utf-8") as handle:
        handle.write(text_key(field_body) + "\n")


def posted_body_keys(ticket_dir: Path) -> set[str]:
    """Hashes of every text the runner wrote into this ticket's field, plus the current field-body.txt."""
    keys = set()
    path = ticket_dir / POSTED_BODIES_FILE
    if path.is_file():
        keys.update(line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    body = ticket_dir / "field-body.txt"
    if body.is_file():
        keys.add(text_key(body.read_text(encoding="utf-8")))
    return keys


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_status(ticket_dir: Path) -> dict[str, Any]:
    path = ticket_dir / STATUS_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_status(ticket_dir: Path, status: dict[str, Any]) -> None:
    ticket_dir.mkdir(parents=True, exist_ok=True)
    status["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (ticket_dir / STATUS_FILE).write_text(json.dumps(status, indent=2), encoding="utf-8")


RUNS_FILE = "runs.jsonl"
ALERT_STATE_FILE = "alerts-state.json"
ATTEMPTS_DIR = "attempts"
ATTEMPT_FILES = (STATUS_FILE, "copilot-transcript.md", "copilot-output.txt")


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def prune_logs(log_dir: Path, retention_days: int, logger: logging.Logger | None = None) -> list[str]:
    """Delete daily log files older than retention_days (0 keeps everything)."""
    if retention_days <= 0 or not log_dir.is_dir():
        return []
    cutoff = time.time() - retention_days * 86400
    removed = []
    for path in log_dir.glob("*.log"):
        if path.stat().st_mtime < cutoff:
            try:
                path.unlink()
                removed.append(path.name)
            except OSError as exc:
                if logger:
                    logger.warning("could not delete old log %s: %s", path, exc)
    if removed and logger:
        logger.info("deleted %d log file(s) older than %d days", len(removed), retention_days)
    return removed


def archive_attempt(ticket_dir: Path, keep: int) -> Path | None:
    """Move the previous run's status and Copilot output into attempts/<stamp>/ so a
    re-run never erases what happened before. Keeps the newest `keep` attempts."""
    present = [name for name in ATTEMPT_FILES if (ticket_dir / name).is_file()]
    if not present or keep <= 0:
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime((ticket_dir / present[0]).stat().st_mtime))
    target = ticket_dir / ATTEMPTS_DIR / stamp
    suffix = 1
    while target.exists():
        suffix += 1
        target = ticket_dir / ATTEMPTS_DIR / f"{stamp}-{suffix}"
    target.mkdir(parents=True)
    for name in present:
        if name == STATUS_FILE:
            shutil.copy2(ticket_dir / name, target / name)
        else:
            (ticket_dir / name).replace(target / name)
    old = sorted(p for p in (ticket_dir / ATTEMPTS_DIR).iterdir() if p.is_dir())
    for stale in old[:-keep]:
        shutil.rmtree(stale, ignore_errors=True)
    return target


def run_each(keys: list[str], handle, logger: logging.Logger, output_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Run handle(key) for every key. One ticket raising never stops the others: the
    traceback goes to the log, the ticket's status.json records the error, and the
    result for that ticket is ERROR."""
    results: dict[str, str] = {}
    errors: dict[str, str] = {}
    for key in keys:
        try:
            results[key] = handle(key)
        except Exception as exc:  # noqa: BLE001 - isolate every ticket
            logger.exception("%s: unexpected error", key)
            message = f"{type(exc).__name__}: {exc}"
            results[key] = "ERROR"
            errors[key] = message
            try:
                ticket_dir = output_dir / key
                status = read_status(ticket_dir)
                status["last_error"] = message
                if status.get("state") not in FINAL_STATES:
                    status["state"] = "ERROR"
                write_status(ticket_dir, status)
            except Exception:  # noqa: BLE001 - never let status bookkeeping hide the real error
                logger.exception("%s: could not record the error in status.json", key)
    return results, errors


def append_run_record(output_dir: Path, record: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / RUNS_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def send_alert(config: dict, jira, logger: logging.Logger, tool: str, run_id: str, lines: list[str]) -> str:
    """Post one Jira comment listing what went wrong, on the configured alert ticket,
    mentioning the configured people. The same alert is not repeated within
    alerts.repeat_hours, so a repeated failure does not flood the ticket."""
    settings = config.get("alerts") or {}
    state_file = Path(config["output_dir"]) / ALERT_STATE_FILE
    try:
        state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {}
    except (OSError, ValueError):
        state = {}
    if not lines:
        if state.pop(tool, None) is not None:  # healthy again: the next problem alerts at once
            state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return "NONE"
    ticket = settings.get("ticket")
    if not ticket:
        logger.warning("alert not sent: no alerts.ticket in the config")
        return "NOT_CONFIGURED"
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    previous = state.get(tool) or {}
    repeat_seconds = float(settings.get("repeat_hours", 24)) * 3600
    if previous.get("hash") == digest and time.time() - float(previous.get("at", 0)) < repeat_seconds:
        logger.info("alert unchanged since the last one; not posted again")
        return "SUPPRESSED"
    mentions = " ".join(f"[~{name}]" for name in settings.get("mention", []))
    head = f"*UAC automation alert* ({tool}, run {run_id}, host {socket.gethostname()})"
    log_dir = Path(config["output_dir"]) / "logs"
    body = "\n".join([f"{mentions} {head}".strip(), ""] + [f"* {line}" for line in lines]
                     + ["", f"Logs: {{{{{log_dir}}}}} and {{{{{Path(config['output_dir']) / RUNS_FILE}}}}}"])
    try:
        comment_id = jira.add_comment(ticket, body)
    except Exception:  # noqa: BLE001 - Jira itself may be the problem
        logger.exception("alert could not be posted to %s", ticket)
        return "FAILED"
    state[tool] = {"hash": digest, "at": time.time(), "comment_id": comment_id}
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    logger.info("alert posted to %s (comment %s)", ticket, comment_id)
    return "POSTED"


def import_skill_module(name: str):
    if str(SKILL_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SKILL_SCRIPTS))
    return __import__(name)


@dataclass
class JiraClient:
    """Minimal Jira Server/Data Center REST v2 client (Bearer PAT)."""

    base_url: str
    token: str
    verify_ssl: bool = True
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "JiraClient":
        base = (os.getenv("JIRA_BASE_URL") or os.getenv("JIRA_URL") or "").rstrip("/")
        token = os.getenv("JIRA_PAT") or os.getenv("JIRA_BEARER_TOKEN") or ""
        if not base or not token:
            raise RuntimeError("JIRA_BASE_URL and JIRA_PAT must be set (environment or env file)")
        verify = os.getenv("JIRA_SSL_VERIFY", "true").strip().lower() not in {"false", "0", "no"}
        return cls(base, token, verify)

    def _context(self) -> ssl.SSLContext | None:
        if self.verify_ssl:
            return None
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _call(self, method: str, path: str, body: bytes | None = None,
              headers: dict[str, str] | None = None) -> Any:
        req = urllib.request.Request(self.base_url + path, data=body, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/json")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._context()) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "replace")
            raise RuntimeError(f"Jira {method} {path} failed: HTTP {exc.code} {detail}") from None
        return json.loads(data) if data else {}

    def _json(self, method: str, path: str, payload: Any = None) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        return self._call(method, path, body, {"Content-Type": "application/json"})

    def myself(self) -> dict[str, Any]:
        return self._json("GET", "/rest/api/2/myself")

    def search_keys(self, jql: str, max_results: int = 100) -> list[str]:
        query = urllib.parse.urlencode({"jql": jql, "fields": "summary", "maxResults": max_results})
        data = self._json("GET", f"/rest/api/2/search?{query}")
        return [issue["key"] for issue in data.get("issues", [])]

    def get_field(self, key: str, field: str, rendered: bool = False) -> Any:
        query = urllib.parse.urlencode({"fields": field, **({"expand": "renderedFields"} if rendered else {})})
        data = self._json("GET", f"/rest/api/2/issue/{key}?{query}")
        section = data.get("renderedFields" if rendered else "fields") or {}
        return section.get(field)

    def get_people(self, key: str) -> dict[str, str]:
        """Usernames of the issue's assignee and reporter (empty when unset)."""
        data = self._json("GET", f"/rest/api/2/issue/{key}?fields=assignee,reporter")
        fields = data.get("fields") or {}
        return {role: str((fields.get(role) or {}).get("name") or "") for role in ("assignee", "reporter")}

    def get_source(self, key: str) -> dict[str, Any]:
        """The ticket text a UAC must cover: summary, description, comments and attachment names."""
        data = self._json("GET", f"/rest/api/2/issue/{key}?fields=summary,description,comment,attachment")
        fields = data.get("fields") or {}
        comments = [
            {"id": str(c.get("id") or ""), "author": str((c.get("author") or {}).get("name") or ""),
             "body": c.get("body") or ""}
            for c in (fields.get("comment") or {}).get("comments") or []
        ]
        attachments = [
            {"filename": str(a.get("filename") or ""), "author": str((a.get("author") or {}).get("name") or "")}
            for a in fields.get("attachment") or []
        ]
        return {"summary": fields.get("summary") or "", "description": fields.get("description") or "",
                "comments": comments, "attachments": attachments}

    def set_field(self, key: str, field: str, value: str) -> None:
        self._json("PUT", f"/rest/api/2/issue/{key}", {"fields": {field: value}})

    def update_labels(self, key: str, add: list[str] = (), remove: list[str] = ()) -> None:
        ops = [{"add": name} for name in add] + [{"remove": name} for name in remove]
        if ops:
            self._json("PUT", f"/rest/api/2/issue/{key}", {"update": {"labels": ops}})

    def add_comment(self, key: str, body: str) -> str:
        return str(self._json("POST", f"/rest/api/2/issue/{key}/comment", {"body": body}).get("id", ""))

    def attach_file(self, key: str, path: Path) -> str:
        boundary = uuid.uuid4().hex
        payload = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            "Content-Type: text/markdown\r\n\r\n"
        ).encode("utf-8") + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
        result = self._call("POST", f"/rest/api/2/issue/{key}/attachments", payload, {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Atlassian-Token": "no-check",
        })
        return str(result[0].get("id", "")) if isinstance(result, list) and result else ""


def check_url(url: str, timeout: float = 10.0) -> tuple[bool, str]:
    """Health check for an HTTP endpoint (the Dataset Studio MCP health URL)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 300, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except OSError as exc:
        return False, type(exc).__name__ + ": " + str(exc)[:120]
