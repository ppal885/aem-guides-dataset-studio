"""Local repository evidence scanner for Guides test-plan generation.

This module is intentionally read-only. It discovers configured local clones,
searches issue-derived focus queries, and returns compact evidence that Claude
can cite in test plans without indexing source code into central RAG.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "target",
    "build",
    "dist",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".gradle",
    ".idea",
}
TEXT_EXTENSIONS = {
    ".java",
    ".jsp",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".py",
    ".xml",
    ".json",
    ".yaml",
    ".yml",
    ".feature",
    ".md",
    ".html",
    ".htm",
    ".scss",
    ".css",
    ".properties",
}
MAX_FILE_BYTES = 1_000_000


def collect_repository_evidence(
    *,
    issue: dict[str, Any],
    planning_seeds: dict[str, Any],
    repo_contract: dict[str, Any],
    max_matches: int = 30,
) -> dict[str, Any]:
    """Collect per-run evidence from local clones referenced by repo_contract."""
    queries = _build_queries(issue, planning_seeds, repo_contract)
    repos = []
    for repo in repo_contract.get("required_repositories") or []:
        repo_id = str(repo.get("id") or "").strip()
        if not repo_id:
            continue
        resolved = _resolve_repo_path(repo)
        matches = (
            _search_repo(resolved, queries, repo_id=repo_id, max_matches=max_matches)
            if resolved and resolved.exists() and resolved.is_dir()
            else []
        )
        repos.append(
            {
                "id": repo_id,
                "owner_role": repo.get("owner_role") or "",
                "path_env": repo.get("path_env") or "",
                "path": str(resolved) if resolved else "",
                "available": bool(resolved and resolved.exists() and resolved.is_dir()),
                "evidence_type": _repo_evidence_type(repo_id),
                "match_count": len(matches),
                "matches": matches,
                "missing_reason": ""
                if matches
                else _missing_reason(repo, resolved),
            }
        )

    owner_gates = _evaluate_owner_gates(repo_contract, repos)
    status = _overall_status(owner_gates)
    return {
        "source": "local_repository_scan",
        "status": status,
        "repo_evidence_status": status,
        "queries_used": queries,
        "commands_used": [
            "Python recursive text scan with ignored heavy/generated directories",
        ],
        "repositories": repos,
        "owner_gates": owner_gates,
        "missing_evidence": [
            gap
            for gate in owner_gates
            for gap in gate.get("missing_evidence", [])
        ],
        "planner_instruction": (
            "Review-ready is allowed only when required owner gates are complete; "
            "otherwise keep Review status: Draft and cite missing repository evidence."
        ),
    }


def _build_queries(
    issue: dict[str, Any],
    planning_seeds: dict[str, Any],
    repo_contract: dict[str, Any],
) -> list[str]:
    values: list[str] = []
    values.extend(str(item) for item in repo_contract.get("focus_queries") or [])
    for key in ("issue_key", "summary", "title"):
        if issue.get(key):
            values.append(str(issue[key]))
    issue_blob = " ".join(
        str(issue.get(key) or "")
        for key in ("summary", "title", "description", "snippet")
    )
    values.extend(_derive_query_terms(issue_blob))
    for key in ("features", "constructs", "outputs"):
        values.extend(str(item) for item in planning_seeds.get(key) or [])
    for seed_key in ("blast_radius_seed", "bug_hypothesis_seed", "test_area_seed", "regression_risk_seed"):
        for seed in planning_seeds.get(seed_key) or []:
            if isinstance(seed, dict):
                values.extend(str(seed.get(k) or "") for k in ("id", "area", "suspected_bug", "title", "surface", "risk"))
    return _dedupe_queries(values)[:40]


def _derive_query_terms(text: str) -> list[str]:
    lowered = (text or "").lower()
    terms: list[str] = []
    endpoints = re.findall(r"/bin/[A-Za-z0-9_./-]+", text or "")
    terms.extend(endpoints)
    quoted = re.findall(r'"([^"\n]{3,80})"', text or "")
    terms.extend(quoted)
    if "broken links" in lowered:
        terms.extend(["Broken Links Report", "broken links", "Fetching details for broken links"])
    if "schematron" in lowered:
        terms.extend(["schematron", "/bin/dxml/schematron", "validate on save"])
    if "snippet" in lowered:
        terms.extend(["snippets", "/bin/fmdita/config/snippets", "URLDecoder"])
    if "pagination" in lowered or "lazy loading" in lowered:
        terms.extend(["pagination", "lazy loading", "pageSize", "offset", "limit"])
    if "%" in text or "urldecoder" in lowered:
        terms.extend(["URLDecoder", "Illegal hex", "application/x-www-form-urlencoded", "colwidth"])
    return terms


def _resolve_repo_path(repo: dict[str, Any]) -> Path | None:
    env_name = str(repo.get("path_env") or "").strip()
    if env_name:
        env_value = os.environ.get(env_name, "").strip()
        if env_value:
            return Path(env_value).expanduser().resolve()
    for hint in repo.get("fallback_path_hints") or []:
        path = Path(str(hint)).expanduser()
        candidates = [
            path,
            Path.cwd() / path,
            Path.cwd().parent / path,
        ]
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved.exists() and resolved.is_dir():
                return resolved
    return None


def _search_repo(root: Path, queries: list[str], *, repo_id: str, max_matches: int) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    lowered_queries = [(query, query.lower()) for query in queries if len(query.strip()) >= 3]
    if not lowered_queries:
        return matches
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lowered = text.lower()
        matched_query = next((original for original, lowered_query in lowered_queries if lowered_query in lowered), "")
        if not matched_query:
            continue
        line_no, snippet = _line_for_match(text, matched_query)
        matches.append(
            {
                "path": str(path),
                "relative_path": path.relative_to(root).as_posix(),
                "line": line_no,
                "matched_query": matched_query,
                "snippet": snippet,
                "evidence_type": _classify_match(repo_id, path, text),
                "symbols": _extract_symbols(text),
            }
        )
        if len(matches) >= max_matches:
            break
    return matches


def _iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def _line_for_match(text: str, query: str) -> tuple[int, str]:
    lowered_query = query.lower()
    for index, line in enumerate(text.splitlines(), start=1):
        if lowered_query in line.lower():
            return index, _compact(line)
    return 1, _compact(text[:300])


def _extract_symbols(text: str) -> list[str]:
    symbols: list[str] = []
    patterns = [
        r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\b(?:describe|it|test)\(\s*['\"]([^'\"]{3,80})",
        r"\b(?:public|private|protected)?\s*(?:static\s+)?[A-Za-z0-9_<>\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            symbols.append(_compact(str(match)))
            if len(symbols) >= 5:
                return symbols
    return symbols


def _classify_match(repo_id: str, path: Path, text: str) -> str:
    repo_lower = repo_id.lower()
    path_lower = path.as_posix().lower()
    text_lower = text[:2000].lower()
    if "guides-ui-tests" in repo_lower:
        if "page" in path_lower or "pageobject" in path_lower or "selector" in text_lower:
            return "page_object"
        return "ui_test"
    if "dxml-it-tests" in repo_lower:
        if "fixture" in path_lower or "data" in path_lower:
            return "fixture"
        return "api_test"
    if "test" in path_lower or ".feature" in path_lower:
        return "ui_test" if "ui" in repo_lower else "api_test"
    return "product_code"


def _repo_evidence_type(repo_id: str) -> str:
    if repo_id == "guides-ui-tests":
        return "ui_test"
    if repo_id == "dxml-it-tests":
        return "api_test"
    return "product_code"


def _evaluate_owner_gates(repo_contract: dict[str, Any], repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {repo["id"]: repo for repo in repos}
    gates = []
    for gate in repo_contract.get("role_based_evidence_gates") or []:
        repo_ids = _repo_ids_from_gate(gate)
        missing = []
        weak = []
        for repo_id in repo_ids:
            repo = by_id.get(repo_id)
            if not repo or not repo.get("available"):
                missing.append(f"{repo_id} clone unavailable")
            elif int(repo.get("match_count") or 0) <= 0:
                weak.append(f"{repo_id} has no matching evidence")
        gates.append(
            {
                "owner_role": gate.get("owner_role") or "",
                "required_repositories": repo_ids,
                "status": "complete" if not missing and not weak else ("missing" if missing else "partial"),
                "matched_repositories": [
                    repo_id for repo_id in repo_ids if (by_id.get(repo_id) or {}).get("match_count")
                ],
                "missing_evidence": missing + weak,
            }
        )
    return gates


def _repo_ids_from_gate(gate: dict[str, Any]) -> list[str]:
    text = f"{gate.get('primary_repo') or ''} {gate.get('automation_repo') or ''}"
    candidates = ["xmleditor", "starling", "guides-ui-tests", "dxml-it-tests"]
    return [repo_id for repo_id in candidates if repo_id in text]


def _overall_status(owner_gates: list[dict[str, Any]]) -> str:
    statuses = {gate.get("status") for gate in owner_gates}
    if not owner_gates or "missing" in statuses:
        return "missing"
    if "partial" in statuses:
        return "partial"
    return "complete"


def _missing_reason(repo: dict[str, Any], resolved: Path | None) -> str:
    if not resolved:
        return (
            f"Set {repo.get('path_env')} or clone repo near one of: "
            f"{', '.join(str(item) for item in repo.get('fallback_path_hints') or [])}"
        )
    if not resolved.exists():
        return f"Resolved path does not exist: {resolved}"
    return "Repo available but no matches found for issue-derived focus queries."


def _dedupe_queries(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _compact(value)
        if len(cleaned) < 3:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned[:120])
    return out


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())
