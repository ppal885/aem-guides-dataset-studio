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
    # Generated test/report output. These are machine-written dumps of a run,
    # not source, and one run can emit thousands of near-identical files.
    "out",
    "output",
    "coverage",
    "htmlcov",
    "logs",
    "result",
    "results",
    "test-output",
    "test-results",
    "allure-report",
    "allure-results",
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
# A full text scan of each configured clone measures ~3s, so the scan is bounded
# only as a safety net against an unexpectedly large tree.  Truncating the walk
# early is what previously reduced evidence selection to directory order.
MAX_FILES_SCANNED = 40_000
# Symbols are collected from a window around the matched line so they describe
# the match rather than the file.
_SYMBOL_CONTEXT_LINES = 40
# No single directory may consume the evidence budget.  Many matches from one
# directory are one finding repeated, not independent corroboration.
_MAX_MATCHES_PER_DIR = 3


def _query_specificity(query: str) -> float:
    """Rank a query by how much evidence a hit on it actually carries.

    A hit on a multi-word phrase or an endpoint identifies real behavior.  A
    hit on one short generic token identifies almost any file in the tree.
    """

    text = query.strip()
    tokens = [token for token in re.split(r"[\s/._\-]+", text) if token]
    score = float(len(text))
    if len(tokens) > 1:
        score *= 2.0
    if "/" in text:
        score *= 1.5
    return score


def _match_pattern(query: str) -> re.Pattern[str]:
    """Compile a whole-word matcher so `map` does not match `sitemap`."""

    escaped = re.escape(query.strip().lower())
    prefix = r"\b" if query.strip()[:1].isalnum() else ""
    suffix = r"\b" if query.strip()[-1:].isalnum() else ""
    return re.compile(f"{prefix}{escaped}{suffix}")



def collect_repository_evidence(
    *,
    issue: dict[str, Any],
    planning_seeds: dict[str, Any],
    repo_contract: dict[str, Any],
    max_matches: int = 30,
) -> dict[str, Any]:
    """Collect per-run evidence from local clones referenced by repo_contract."""
    queries, subject_queries = _build_query_plan(issue, planning_seeds, repo_contract)
    repos = []
    for repo in repo_contract.get("required_repositories") or []:
        repo_id = str(repo.get("id") or "").strip()
        if not repo_id:
            continue
        resolved = _resolve_repo_path(repo)
        matches = (
            _search_repo(
                resolved,
                queries,
                repo_id=repo_id,
                max_matches=max_matches,
                subject_queries=subject_queries,
            )
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
    queries, _ = _build_query_plan(issue, planning_seeds, repo_contract)
    return queries


def _build_query_plan(
    issue: dict[str, Any],
    planning_seeds: dict[str, Any],
    repo_contract: dict[str, Any],
) -> tuple[list[str], frozenset[str]]:
    """Build the query list and identify which queries came from this issue.

    Configured focus queries and planner seeds describe the product in general.
    Only the terms derived from the issue itself distinguish this ticket from
    any other, so they are tracked separately and ranked ahead of the rest.
    """

    values: list[str] = []
    for key in ("issue_key", "summary", "title"):
        if issue.get(key):
            values.append(str(issue[key]))
    issue_blob = " ".join(
        str(issue.get(key) or "")
        for key in ("summary", "title", "description", "snippet")
    )
    derived = _ticket_subject_queries(_derive_query_terms(issue_blob))
    values.extend(derived)
    values.extend(str(item) for item in repo_contract.get("focus_queries") or [])
    # Planning seeds are retrieval output, not ticket scope.  Letting an
    # unrelated historical/RAG seed create a repository query admits broad
    # matches (for example, every publishing test) as if they described the
    # current issue.  Repository discovery must start with the Jira-derived
    # subject; a later, question-bound research request can widen it only when
    # its evidence contract authorizes that query.
    queries = _dedupe_queries(values)[:40]
    retained = set(queries)
    subject = frozenset(term for term in _dedupe_queries(derived) if term in retained)
    return queries, subject


_GENERIC_CODE_SEARCH_TERMS = frozenset(
    {
        "api",
        "csv",
        "download",
        "editor",
        "export",
        "guides",
        "list",
        "map",
        "maps",
        "new",
        "order",
        "output",
        "outputs",
        "report",
        "reports",
        "topic",
        "topics",
        "ui",
        "view",
    }
)


def _ticket_subject_queries(terms: list[str]) -> list[str]:
    """Keep repository searches bound to a distinctive Jira subject.

    A current issue often contains broad nouns such as ``Reports`` or
    ``topic``.  Searching a whole product clone for those nouns yields valid
    files from unrelated features, which must not become implementation
    evidence for this ticket.  Prefer exact labels, phrases, endpoints, and
    identifier-shaped terms; only fall back to a single non-generic term when
    the ticket supplies no stronger subject.
    """

    cleaned = [" ".join(str(term).split()) for term in terms if str(term).strip()]
    specific = [
        term
        for term in cleaned
        if (
            term.startswith("/")
            or " " in term
            or "_" in term
            or "-" in term
            or any(char.isupper() for char in term[1:])
            or term.casefold() not in _GENERIC_CODE_SEARCH_TERMS
        )
    ]
    selected = specific or [
        term
        for term in cleaned
        if term.casefold() not in _GENERIC_CODE_SEARCH_TERMS
    ]
    variants: list[str] = []
    for term in selected:
        variants.append(term)
        words = re.findall(r"[A-Za-z0-9]+", term)
        if 2 <= len(words) <= 4:
            variants.append("".join(word[:1].upper() + word[1:] for word in words))
            variants.append("_".join(word.casefold() for word in words))
            variants.append("-".join(word.casefold() for word in words))
    return _dedupe_queries(variants)


def _derive_query_terms(text: str) -> list[str]:
    lowered = (text or "").lower()
    terms: list[str] = []
    endpoints = re.findall(r"/bin/[A-Za-z0-9_./-]+", text or "")
    terms.extend(endpoints)
    quoted = re.findall(r'"([^"\n]{3,80})"', text or "")
    terms.extend(quoted)
    terms.extend(_derive_subject_terms(text or ""))
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


_QUERY_STOPWORDS = frozenset(
    """
    a an and are as at be been but by can cannot could did do does for from get
    given had has have how i if in into is it its may me must need needs new no
    not of on only or other our out over same should so some such than that the
    their then there these they this those to under up use used user using want
    was way we were what when where which while who why will with would you your
    able about after again all also any because before being below both each few
    more most much no nor now off once other own said same see should since still
    take then they through too very via well were will within without yet
    """.split()
)

# A UI label such as "Topic List" identifies the feature; a lone word does not.
_LABEL_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){1,3})\b")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def _derive_subject_terms(text: str) -> list[str]:
    """Derive queries from the ticket's own vocabulary.

    Without this, only a fixed ladder of historical scenarios produced terms, so
    a ticket outside that ladder contributed no searchable vocabulary and its
    evidence was selected by ticket-independent seeds instead.
    """

    if not text.strip():
        return []

    terms: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        cleaned = " ".join(candidate.split())
        key = cleaned.lower()
        if len(cleaned) < 3 or key in seen:
            return
        seen.add(key)
        terms.append(cleaned)

    for label in _LABEL_RE.findall(text):
        words = label.split()
        # A label made only of stopwords carries no subject.
        if all(word.lower() in _QUERY_STOPWORDS for word in words):
            continue
        add(label)

    significant = [
        word
        for word in _WORD_RE.findall(text)
        if len(word) >= 4 and word.lower() not in _QUERY_STOPWORDS
    ]
    for first, second in zip(significant, significant[1:]):
        add(f"{first} {second}")
    for word in significant:
        add(word)

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


def _search_repo(
    root: Path,
    queries: list[str],
    *,
    repo_id: str,
    max_matches: int,
    subject_queries: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    candidates = [query for query in queries if len(query.strip()) >= 3]
    if not candidates:
        return []
    # Rank queries so a file is attributed to the most specific query it
    # satisfies, rather than to whichever query happened to be listed first.
    # Provenance outranks specificity: a query derived from this issue is
    # evidence about this issue, while a configured focus query matches the
    # same generic vocabulary for every ticket and would otherwise crowd the
    # issue's own subject out of the budget.
    ranked = sorted(
        (
            (
                1 if query in subject_queries else 0,
                _query_specificity(query),
                query,
                query.lower(),
                _match_pattern(query),
            )
            for query in candidates
        ),
        key=lambda row: (row[0], row[1]),
        reverse=True,
    )
    if subject_queries:
        # A subject query was available, so a generic focus match is not
        # admissible evidence for this ticket.  Returning no match is an
        # honest evidence gap; returning an unrelated file silently widens
        # scope and produces false coverage.
        ranked = [row for row in ranked if row[0]]

    scored: list[tuple[int, float, str, dict[str, Any]]] = []
    for scanned, path in enumerate(_iter_text_files(root)):
        if scanned >= MAX_FILES_SCANNED:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lowered = text.lower()
        best: tuple[int, float, str] | None = None
        for tier, specificity, original, lowered_query, pattern in ranked:
            # The cheap substring test gates the whole-word confirmation.
            if lowered_query in lowered and pattern.search(lowered):
                best = (tier, specificity, original)
                break
        if best is None:
            continue
        tier, specificity, matched_query = best
        line_no, snippet = _line_for_match(text, matched_query)
        scored.append(
            (
                tier,
                specificity,
                path.as_posix(),
                {
                    "path": str(path),
                    "relative_path": path.relative_to(root).as_posix(),
                    "line": line_no,
                    "matched_query": matched_query,
                    "snippet": snippet,
                    "evidence_type": _classify_match(repo_id, path, text),
                    "symbols": _extract_symbols(text, around_line=line_no),
                },
            )
        )

    # Keep the most specific evidence, then order deterministically by path.
    scored.sort(key=lambda row: (-row[0], -row[1], row[2]))

    # The per-directory cap only makes sense when more than one directory
    # produced evidence.  When a single directory is the only source, capping
    # it would discard evidence without improving diversity.
    directories = {posix_path.rsplit("/", 1)[0] for _, _, posix_path, _ in scored}
    if len(directories) <= 1:
        return [match for _, _, _, match in scored[:max_matches]]

    selected: list[dict[str, Any]] = []
    per_dir: dict[str, int] = {}
    for _, _, posix_path, match in scored:
        parent = posix_path.rsplit("/", 1)[0]
        if per_dir.get(parent, 0) >= _MAX_MATCHES_PER_DIR:
            continue
        per_dir[parent] = per_dir.get(parent, 0) + 1
        selected.append(match)
        if len(selected) >= max_matches:
            break
    return selected



def _iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        # Only directories inside the repository may exclude a file. Testing the
        # absolute path would exclude an entire clone that merely happens to
        # live under a dot-directory or a directory named `build`.
        try:
            inner = path.relative_to(root).parts[:-1]
        except ValueError:
            inner = path.parts[:-1]
        if any(part in IGNORED_DIRS for part in inner):
            continue
        # Hidden directories hold tool and agent configuration, not product
        # source, and must not be cited as current implementation evidence.
        if any(part.startswith(".") for part in inner):
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


def _extract_symbols(text: str, *, around_line: int | None = None) -> list[str]:
    """Extract symbols near the match.

    Symbols taken from an entire file describe the file, not the match that
    made it evidence, so a README or POM contributed unrelated identifiers.
    """

    if around_line is not None:
        lines = text.splitlines()
        start = max(0, around_line - 1 - _SYMBOL_CONTEXT_LINES)
        window = "\n".join(lines[start : around_line - 1 + _SYMBOL_CONTEXT_LINES])
        text = window or text

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
