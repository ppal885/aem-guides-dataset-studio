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
JIRA_SOURCE_FILE = "jira-source.json"


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_status(ticket_dir: Path) -> dict[str, Any]:
    path = ticket_dir / STATUS_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_status(ticket_dir: Path, status: dict[str, Any]) -> None:
    ticket_dir.mkdir(parents=True, exist_ok=True)
    status["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (ticket_dir / STATUS_FILE).write_text(json.dumps(status, indent=2), encoding="utf-8")


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
        """The ticket text a UAC must cover: description, comments and attachment names."""
        data = self._json("GET", f"/rest/api/2/issue/{key}?fields=description,comment,attachment")
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
        return {"description": fields.get("description") or "", "comments": comments, "attachments": attachments}

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
