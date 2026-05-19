"""Scan guides-ui-tests (or compatible repo) and maintain resources/ai_index/*.json."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.gqs_integration_config import INDEX_FILES, ai_index_dir, guides_repo_root

_XPATH_STRING_RE = re.compile(r'["\'](//[^"\']{2,800})["\']')
_FEATURE_STEP_RE = re.compile(r"^\s*(Given|When|Then)\b", re.I)


@dataclass
class FrameworkHealth:
    status: str
    reason: str | None
    repo_root: str | None
    index_dir: str | None
    files: dict[str, Any]
    expected_path_example: str = r"C:\ui_framework\guides-ui-tests"


def _safe_read_json(path: Path) -> Any | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _count_index_payload(data: Any, kind: str) -> int:
    if data is None:
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        if kind == "xpath" and isinstance(data.get("entries"), list):
            return len(data["entries"])
        if kind == "methods" and isinstance(data.get("methods"), list):
            return len(data["methods"])
        if kind == "steps" and isinstance(data.get("phrases"), list):
            return len(data["phrases"])
        if kind == "steps" and isinstance(data.get("steps"), list):
            return len(data["steps"])
    return 0


def read_framework_qa_health() -> dict[str, Any]:
    """Filesystem-driven framework index readiness (no env counters)."""
    root = guides_repo_root()
    if not root:
        h = FrameworkHealth(
            status="not_configured",
            reason="Set GQS_GUIDES_REPO_ROOT to the guides-ui-tests checkout.",
            repo_root=None,
            index_dir=None,
            files={},
        )
        return {
            "status": h.status,
            "reason": h.reason,
            "repo_root": h.repo_root,
            "index_dir": h.index_dir,
            "expected_path_example": h.expected_path_example,
            "index_files": {},
            "counts": {"xpath_entries": 0, "page_methods": 0, "step_phrases": 0},
            "last_indexed_at": None,
        }

    idx = ai_index_dir(root)
    assert idx is not None
    files_meta: dict[str, Any] = {}
    counts = {"xpath_entries": 0, "page_methods": 0, "step_phrases": 0}
    last_mtime: float = 0.0
    any_file = False
    all_present = True

    mapping = [
        ("xpath_library.json", "xpath", "xpath_entries"),
        ("page_methods.json", "methods", "page_methods"),
        ("step_phrases.json", "steps", "step_phrases"),
    ]
    for fname, kind, ckey in mapping:
        fp = idx / fname
        exists = fp.is_file()
        if exists:
            any_file = True
            stat = fp.stat()
            last_mtime = max(last_mtime, stat.st_mtime)
            raw = _safe_read_json(fp)
            n = _count_index_payload(raw, kind)
            counts[ckey] = n
            files_meta[fname] = {
                "path": str(fp.resolve()),
                "exists": True,
                "bytes": stat.st_size,
                "count": n,
                "mtime_utc": stat.st_mtime,
            }
        else:
            all_present = False
            files_meta[fname] = {"path": str(fp.resolve()), "exists": False, "bytes": 0, "count": 0}

    if not idx.is_dir():
        status = "not_configured"
        reason = f"Create directory {idx} or run Framework Reindex."
    elif not any_file:
        status = "needs_reindex"
        reason = "Index JSON files are missing under resources/ai_index — run Framework Reindex."
    elif not all_present:
        status = "needs_reindex"
        reason = "One or more index files are missing under resources/ai_index — run Framework Reindex."
    else:
        status = "ready"
        reason = None
        if all(v == 0 for v in counts.values()):
            reason = (
                "Index files exist but all counts are zero — last reindex found no features/XPath/methods; "
                "check repo layout or paths."
            )

    from datetime import datetime, timezone

    last_iso = None
    if last_mtime > 0:
        last_iso = datetime.fromtimestamp(last_mtime, tz=timezone.utc).isoformat()

    return {
        "status": status,
        "reason": reason,
        "repo_root": str(root),
        "index_dir": str(idx),
        "expected_path_example": FrameworkHealth.expected_path_example,
        "index_files": files_meta,
        "counts": counts,
        "last_indexed_at": last_iso,
    }


def _iter_python_files(root: Path, limit: int = 800) -> list[Path]:
    out: list[Path] = []
    skip = {"venv", ".git", "__pycache__", "node_modules", ".venv", "dist", "build"}
    for p in root.rglob("*.py"):
        if any(part in skip for part in p.parts):
            continue
        low = str(p).lower()
        if any(x in low for x in ("\\test", "/test", "tests\\", "tests/", "site-packages")):
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def _iter_feature_files(root: Path, limit: int = 400) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.feature"):
        if ".git" in p.parts:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def build_framework_indexes(repo_root: Path | None = None) -> dict[str, Any]:
    """Write xpath_library.json, page_methods.json, step_phrases.json under resources/ai_index."""
    root = repo_root or guides_repo_root()
    if not root:
        return {"ok": False, "error": "GQS_GUIDES_REPO_ROOT is not set or path is invalid."}

    idx = root / "resources" / "ai_index"
    idx.mkdir(parents=True, exist_ok=True)

    xpath_entries: list[dict[str, Any]] = []
    methods: list[dict[str, Any]] = []
    phrases_set: set[str] = set()

    for feat in _iter_feature_files(root):
        try:
            text = feat.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(feat.relative_to(root))
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if _FEATURE_STEP_RE.match(s):
                phrases_set.add(s if len(s) < 500 else s[:500])

    for pyf in _iter_python_files(root):
        try:
            src = pyf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(pyf.relative_to(root))
        for m in _XPATH_STRING_RE.finditer(src):
            xp = (m.group(1) or "").strip()
            if xp.startswith("//") and len(xp) > 2:
                xpath_entries.append({"xpath": xp[:800], "source_file": rel})
        if len(xpath_entries) > 12000:
            break

    for pyf in _iter_python_files(root):
        try:
            src = pyf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(pyf.relative_to(root))
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                cname = node.name
                if not (cname.endswith("Page") or "Page" in cname or "Panel" in cname or "Dialog" in cname):
                    continue
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                        methods.append(
                            {
                                "class": cname,
                                "method": item.name,
                                "source_file": rel,
                            }
                        )
        if len(methods) > 20000:
            break

    xpath_payload = {"version": 1, "entries": xpath_entries[:15000]}
    methods_payload = {"version": 1, "methods": methods[:25000]}
    phrases_payload = {"version": 1, "phrases": sorted(phrases_set)[:20000]}

    (idx / "xpath_library.json").write_text(json.dumps(xpath_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (idx / "page_methods.json").write_text(json.dumps(methods_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (idx / "step_phrases.json").write_text(json.dumps(phrases_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "index_dir": str(idx),
        "written": list(INDEX_FILES),
        "counts": {
            "xpath_entries": len(xpath_payload["entries"]),
            "page_methods": len(methods_payload["methods"]),
            "step_phrases": len(phrases_payload["phrases"]),
        },
    }
