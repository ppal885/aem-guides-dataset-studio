"""Versioned RAG rebuild + UAC replay gate (staging only).

Why: the chunking/retrieval fixes merged in PRs #242-#247 change what is indexed, but nothing
was re-indexed and their tests used mocked embeddings. A UAC benchmark run against an index
built by older chunking/retrieval code measures that old index, not the current pipeline. This
gate makes that impossible:

  rebuild   Rebuild the evaluation collections (jira_qa, Experience League / aem_guides, PDF,
            GitHub DITA) with the current chunkers into an isolated STAGING Chroma directory,
            then write ``rag-index-manifest.json``.
  manifest  Write the manifest for an existing staging index without rebuilding (read-only).
  check     Refuse (exit 2) when the manifest is missing, malformed, not staging, built by
            different retrieval/chunking code, predates the last change to that code, used a
            different embedding model, or the index still holds stale chunk ids.
  replay    Run the fixed five-case set twice through the canonical runtime against the
            staging index and write ``retrieval-replay-report.json`` and
            ``uac-disposition-report.json``. Exit 0 only when every pass criterion holds.

Staging only: ``rebuild`` and ``replay`` require ``--staging-chroma-dir`` and refuse a remote
``CHROMA_HOST``, the production storage path, or a non-empty directory this gate did not create.
Nothing here posts to Jira, changes production collections, or tunes retrieval thresholds.

The dashboard never recalculates metrics; these reports are saved JSON like every other run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BACKEND = REPO / "backend"

MANIFEST_SCHEMA = "rag-index-manifest-v1"
REPLAY_SCHEMA = "retrieval-replay-report-v1"
DISPOSITION_SCHEMA = "uac-disposition-report-v1"
CASES_SCHEMA = "uac-replay-cases-v1"
STAGING_MARKER = ".rag-staging-index"

MANIFEST_FILE = "rag-index-manifest.json"
REPLAY_FILE = "retrieval-replay-report.json"
DISPOSITION_FILE = "uac-disposition-report.json"
DEFAULT_CASES = HERE / "replay_cases.json"

# Source files whose behaviour decides what is chunked, embedded and retrieved. Any change to
# one of them makes an index built before it stale for benchmarking.
RETRIEVAL_CODE_PATHS: tuple[str, ...] = (
    "backend/app/services/jira_chunking_service.py",
    "backend/app/services/jira_qa_chunking_service.py",
    "backend/app/services/jira_qa_index_service.py",
    "backend/app/services/jira_csv_import_service.py",
    "backend/app/services/jira_learning_chunk_service.py",
    "backend/app/services/jira_uac_analysis_service.py",
    "backend/app/services/jira_enrichment_service.py",
    "backend/app/services/jira_generate_resolve.py",
    "backend/app/services/customer_tokens.py",
    "backend/app/services/doc_pdf_index_service.py",
    "backend/app/services/github_dita_examples_service.py",
    "backend/app/services/vector_store_service.py",
    "backend/app/services/embedding_service.py",
    "backend/app/services/jira_retrieval_service.py",
    "backend/app/services/jira_qa_retrieval_service.py",
    "backend/app/services/retrieval_service.py",
    "backend/app/evidence_gateway/rag_adapter.py",
    "backend/app/rag",
)

REQUIRED_COLLECTIONS = ("jira_qa", "aem_guides")

# Runtime CoverageDisposition -> the four benchmark dispositions. A claim referenced by a
# written acceptance criterion is UAC/TBD from the Writer output itself (see final_disposition);
# this map covers claims the Writer did not render. Acceptance contracts are deliberately absent:
# an acceptance contract that never reached a written criterion was dropped, which is a defect
# the gate must report (UNROUTED), not quietly file somewhere.
_UNRENDERED_DISPOSITION: dict[str, str] = {
    "ACCEPTANCE_TBD": "TBD",
    "OPEN_QUESTION": "TBD",
    "PRODUCT_SCOPE_QUESTION": "TBD",
    "ENGINEERING_DESIGN_DECISION": "TBD",
    "SEMANTIC_REGRESSION": "TEST_PLAN",
    "STRUCTURAL_REGRESSION": "TEST_PLAN",
    "CONFIGURATION_VARIANT": "TEST_PLAN",
    "REFERENCE_REGRESSION": "TEST_PLAN",
    "GENERATED_OUTPUT_VALIDATION": "TEST_PLAN",
    "NEGATIVE_BOUNDARY": "TEST_PLAN",
    "FAILURE_RECOVERY": "TEST_PLAN",
    "CROSS_MODE_REGRESSION": "TEST_PLAN",
    "LIFECYCLE_COVERAGE": "TEST_PLAN",
    "NFR_COVERAGE": "TEST_PLAN",
    "IMPLEMENTATION_ORACLE": "TEST_PLAN",
    "TECHNICAL_NOTE": "TEST_PLAN",
    "KNOWN_LIMITATION": "OUT_OF_SCOPE",
    "INVESTIGATED_AND_REJECTED": "OUT_OF_SCOPE",
    "OUT_OF_SCOPE": "OUT_OF_SCOPE",
    "UNSUPPORTED_INFERENCE": "OUT_OF_SCOPE",
}
# The Writer's terminal projection (structured_plan.writer_projection_records[].status) is the
# runtime's own UAC-vs-test-plan decision for P0/P1 coverage, so it wins over everything else.
_WRITER_PROJECTION: dict[str, str] = {
    "STANDALONE_AC": "UAC",
    "ATTACHED_VARIANT": "UAC",
    "ATTACHED_TBD": "TBD",
    # Retained only in a non-acceptance section; not visible in the human-facing UAC.
    "RETAINED_QE_REGRESSION": "TEST_PLAN",
    "TEST_PLAN_REGRESSION": "TEST_PLAN",
    "EXPLICITLY_EXCLUDED": "OUT_OF_SCOPE",
}
FINAL_DISPOSITIONS = ("UAC", "TEST_PLAN", "TBD", "OUT_OF_SCOPE")
UNROUTED = "UNROUTED"

# requirement_authority values the runtime treats as authoritative product evidence.
AUTHORITATIVE_CLASSES = frozenset(
    {
        "ACCEPTED_PRODUCT_REQUIREMENT",
        "CONFIRMED_PRODUCT_DECISION",
        "OFFICIAL_PRODUCT_CONTRACT",
        "SPECIFICATION_AUTHORITY",
        "IMPLEMENTATION_CONFIRMED",
    }
)

CASE_SLOTS: tuple[str, ...] = (
    "new_legacy_editor",
    "configuration_on_off",
    "save_reopen",
    "indirect_reference",
    "blocked_action_negative",
)

# Given/When/Then phrasing, as a clause opener (start of text, line, sentence or list item).
_GWT_RE = re.compile(r"(?:^|[\n.;:]\s*|^\s*[-*\d.)]+\s*)(given|when|then)\b", re.IGNORECASE | re.MULTILINE)
_NEGATION_RE = re.compile(
    r"\b(?:not|cannot|can't|never|no longer|is blocked|are blocked|is disabled|are disabled|"
    r"is prevented|are prevented|is rejected|are rejected|fails? with|shows? an? error)\b",
    re.IGNORECASE,
)


class GateRefused(RuntimeError):
    """A fixed reason code plus human detail; the CLI exits 2 on it."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------------------------
# Code identity
# --------------------------------------------------------------------------------------------


def _iter_code_files(repo: Path, paths: Sequence[str]) -> list[Path]:
    files: list[Path] = []
    for rel in paths:
        target = repo / rel
        if target.is_dir():
            files.extend(sorted(p for p in target.rglob("*.py") if "__pycache__" not in p.parts))
        elif target.is_file():
            files.append(target)
    return sorted(set(files))


def code_fingerprint(repo: Path = REPO, paths: Sequence[str] = RETRIEVAL_CODE_PATHS) -> dict[str, Any]:
    """Content hash of the retrieval/chunking code (independent of git state)."""
    file_hashes: dict[str, str] = {}
    for path in _iter_code_files(repo, paths):
        file_hashes[path.relative_to(repo).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    combined = hashlib.sha256(json.dumps(file_hashes, sort_keys=True).encode("utf-8")).hexdigest()
    return {"sha256": combined, "files": file_hashes}


def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def source_commit(repo: Path = REPO) -> dict[str, Any]:
    head = _git(repo, "rev-parse", "HEAD")
    dirty = bool(_git(repo, "status", "--porcelain", "--", *RETRIEVAL_CODE_PATHS))
    return {"commit": head, "retrieval_code_dirty": dirty}


def code_last_changed_at(repo: Path = REPO, paths: Sequence[str] = RETRIEVAL_CODE_PATHS) -> str:
    """Committer time of the newest commit touching the retrieval/chunking code (ISO-8601)."""
    return _git(repo, "log", "-1", "--format=%cI", "--", *paths)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------------------------
# Corpus identity
# --------------------------------------------------------------------------------------------


def corpus_digest(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Order-independent digest of a collection: chunk count, id set hash and content hash.

    ``records`` are ``{"id", "document", "metadata"}`` rows from a full collection scan.
    """
    rows: list[tuple[str, str]] = []
    for record in records:
        doc_id = str(record.get("id") or "")
        document = str(record.get("document") or "")
        metadata = json.dumps(record.get("metadata") or {}, sort_keys=True, default=str)
        row_hash = hashlib.sha256(f"{document}\x00{metadata}".encode("utf-8")).hexdigest()
        rows.append((doc_id, row_hash))
    rows.sort()
    ids_sha = hashlib.sha256("\n".join(doc_id for doc_id, _ in rows).encode("utf-8")).hexdigest()
    corpus_sha = hashlib.sha256("\n".join(f"{i}\t{h}" for i, h in rows).encode("utf-8")).hexdigest()
    return {"chunk_count": len(rows), "ids_sha256": ids_sha, "corpus_sha256": corpus_sha}


def stale_chunk_ids(stored_ids: Iterable[str], written_ids: Iterable[str]) -> list[str]:
    """Ids present in the rebuilt collection that the rebuild itself did not write."""
    written = set(written_ids)
    return sorted(i for i in set(stored_ids) if i not in written)


# --------------------------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------------------------


def build_manifest(
    *,
    collections: Mapping[str, Mapping[str, Any]],
    embedding: Mapping[str, Any],
    config: Mapping[str, Any],
    staging_dir: str,
    rebuilt_at: str,
    repo: Path = REPO,
    sources: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fingerprint = code_fingerprint(repo)
    return {
        "schema_version": MANIFEST_SCHEMA,
        "environment": "staging",
        "staging_chroma_dir": staging_dir,
        "rebuilt_at": rebuilt_at,
        "manifest_written_at": utc_now(),
        "source": source_commit(repo),
        "retrieval_code": {
            "sha256": fingerprint["sha256"],
            "last_changed_at": code_last_changed_at(repo),
            "files": fingerprint["files"],
        },
        "embedding": dict(embedding),
        "config": dict(config),
        "sources": dict(sources or {}),
        "collections": {name: dict(value) for name, value in sorted(collections.items())},
    }


def check_manifest(
    manifest: Mapping[str, Any] | None,
    *,
    current_code_sha256: str,
    code_changed_at: str,
    current_embedding: Mapping[str, Any] | None = None,
    required_collections: Sequence[str] = REQUIRED_COLLECTIONS,
) -> list[str]:
    """Reason codes that forbid benchmarking against this index; empty means fresh."""
    if not isinstance(manifest, Mapping):
        return ["MANIFEST_MISSING"]
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        return ["MANIFEST_SCHEMA_MISMATCH"]
    reasons: list[str] = []
    if manifest.get("environment") != "staging":
        reasons.append("MANIFEST_NOT_STAGING")
    code = manifest.get("retrieval_code") or {}
    if code.get("sha256") != current_code_sha256:
        reasons.append("RETRIEVAL_CODE_CHANGED_SINCE_REBUILD")
    rebuilt = _parse_time(str(manifest.get("rebuilt_at") or ""))
    changed = _parse_time(code_changed_at)
    if rebuilt is None:
        reasons.append("MANIFEST_REBUILD_TIME_MISSING")
    elif changed is not None and rebuilt < changed:
        reasons.append("MANIFEST_PREDATES_RETRIEVAL_CODE")
    if (manifest.get("source") or {}).get("retrieval_code_dirty"):
        reasons.append("REBUILT_FROM_UNCOMMITTED_RETRIEVAL_CODE")
    for name, source in sorted((manifest.get("sources") or {}).items()):
        if isinstance(source, Mapping) and source.get("status") != "OK":
            reasons.append(f"SOURCE_REBUILD_FAILED:{name}")
    if current_embedding is not None:
        built_with = manifest.get("embedding") or {}
        for key in ("provider", "model"):
            if current_embedding.get(key) and built_with.get(key) != current_embedding.get(key):
                reasons.append("EMBEDDING_MODEL_CHANGED")
                break
    collections = manifest.get("collections") or {}
    for name in required_collections:
        entry = collections.get(name)
        if not isinstance(entry, Mapping) or int(entry.get("chunk_count") or 0) <= 0:
            reasons.append(f"COLLECTION_MISSING_OR_EMPTY:{name}")
        elif entry.get("stale_chunk_ids"):
            reasons.append(f"STALE_CHUNK_IDS:{name}")
    return reasons


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------------------------
# Staging isolation
# --------------------------------------------------------------------------------------------


def prepare_staging_dir(staging_dir: Path, *, production_dirs: Sequence[Path], create: bool) -> Path:
    """Validate (and optionally create) an isolated staging Chroma directory.

    Refuses a remote Chroma host, a production storage path, and a non-empty directory that
    this gate did not create. Must run before any backend import so the backend binds to it.
    """
    if os.getenv("CHROMA_HOST", "").strip():
        raise GateRefused(
            "REMOTE_CHROMA_REFUSED",
            "CHROMA_HOST is set; staging rebuilds only write to an embedded --staging-chroma-dir",
        )
    target = staging_dir.expanduser().resolve()
    for prod in production_dirs:
        try:
            prod_resolved = prod.expanduser().resolve()
        except OSError:
            continue
        if target == prod_resolved or prod_resolved in target.parents or target in prod_resolved.parents:
            raise GateRefused("PRODUCTION_PATH_REFUSED", f"{target} overlaps production store {prod_resolved}")
    marker = target / STAGING_MARKER
    if target.exists() and any(target.iterdir()) and not marker.exists():
        raise GateRefused("UNMARKED_DIRECTORY_REFUSED", f"{target} is not empty and was not created by this gate")
    if not target.exists():
        if not create:
            raise GateRefused("STAGING_DIR_MISSING", str(target))
        target.mkdir(parents=True)
    if not marker.exists():
        if not create:
            raise GateRefused("UNMARKED_DIRECTORY_REFUSED", str(target))
        marker.write_text(json.dumps({"created_at": utc_now(), "purpose": "rag staging index"}) + "\n")
    (target / "chroma").mkdir(exist_ok=True)
    (target / "storage").mkdir(exist_ok=True)
    bind_staging_environment(target)
    return target


def bind_staging_environment(target: Path) -> None:
    """Point every backend store at the staging root; called again after .env loading."""
    os.environ["CHROMA_PERSIST_DIR"] = str(target / "chroma")
    os.environ["STORAGE_PATH"] = str(target / "storage")
    os.environ.pop("CHROMA_HOST", None)
    # index_jql_to_chroma would otherwise upsert enriched issues/chunks into the shared SQL DB.
    os.environ["JIRA_SQL_ENRICHMENT"] = "false"


# --------------------------------------------------------------------------------------------
# Dispositions
# --------------------------------------------------------------------------------------------


def _norm(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def written_disposition_routes(written_acs: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """disposition_id -> UAC/TBD as rendered by the Writer (TBD wins over UAC on conflict)."""
    routes: dict[str, str] = {}

    def route(ids: Iterable[str], value: str) -> None:
        for disposition_id in ids or []:
            if routes.get(disposition_id) != "TBD":
                routes[disposition_id] = value

    for criterion in written_acs:
        route(criterion.get("source_disposition_ids") or [], "TBD" if criterion.get("unresolved") else "UAC")
        for sub in criterion.get("sub_points") or []:
            route(sub.get("source_disposition_ids") or [], "TBD" if sub.get("kind") == "TBD_QUESTION" else "UAC")
    return routes


def writer_projection_routes(payload: Mapping[str, Any]) -> dict[str, str]:
    """coverage_disposition_id -> final disposition from the Writer's projection records."""
    plan = payload.get("structured_plan") or {}
    routes: dict[str, str] = {}
    for record in plan.get("writer_projection_records") or []:
        mapped = _WRITER_PROJECTION.get(str(record.get("status") or ""))
        if mapped:
            routes[str(record.get("coverage_disposition_id") or "")] = mapped
    return routes


def final_disposition(
    record: Mapping[str, Any],
    routes: Mapping[str, str],
    projections: Mapping[str, str] | None = None,
) -> str:
    """Writer projection, else written-criterion reference, else the runtime lane; else UNROUTED."""
    disposition_id = str(record.get("disposition_id") or "")
    projected = (projections or {}).get(disposition_id)
    if projected:
        return projected
    rendered = routes.get(disposition_id)
    if rendered:
        return rendered
    return _UNRENDERED_DISPOSITION.get(str(record.get("disposition") or ""), UNROUTED)


def disposition_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every coverage claim with its final disposition, in a stable order."""
    routes = written_disposition_routes(payload.get("written_acceptance_criteria") or [])
    projections = writer_projection_routes(payload)
    rows: list[dict[str, Any]] = []
    for record in payload.get("coverage_dispositions") or []:
        rows.append(
            {
                "disposition_id": str(record.get("disposition_id") or ""),
                "claim": " ".join(str(record.get("candidate") or "").split()),
                "runtime_disposition": str(record.get("disposition") or ""),
                "coverage_class": str(record.get("coverage_class") or ""),
                "contract_type": str(record.get("contract_type") or ""),
                "research_derived": bool(record.get("research_derived")),
                "evidence_ids": sorted(record.get("evidence_ids") or []),
                "source_fact_ids": sorted(record.get("source_fact_ids") or []),
                "final_disposition": final_disposition(record, routes, projections),
            }
        )
    rows.sort(key=lambda row: (_norm(row["claim"]), row["runtime_disposition"], row["disposition_id"]))
    return rows


def disposition_signature(rows: Iterable[Mapping[str, Any]]) -> list[tuple[str, str, str]]:
    """Run-independent comparison key: (claim, runtime disposition, final disposition)."""
    return sorted((_norm(r["claim"]), str(r["runtime_disposition"]), str(r["final_disposition"])) for r in rows)


# --------------------------------------------------------------------------------------------
# UAC text checks
# --------------------------------------------------------------------------------------------


def written_ac_texts(written_acs: Iterable[Mapping[str, Any]]) -> list[str]:
    texts: list[str] = []
    for criterion in written_acs:
        texts.append(str(criterion.get("outcome") or ""))
        texts.extend(str(sub.get("text") or "") for sub in criterion.get("sub_points") or [])
    return [t for t in texts if t.strip()]


def uac_style_problems(texts: Sequence[str], case: "ReplayCase") -> list[str]:
    problems: list[str] = []
    joined = "\n".join(texts)
    for text in texts:
        if _GWT_RE.search(text):
            problems.append(f"GIVEN_WHEN_THEN_PHRASING: {text[:120]}")
    lowered = joined.casefold()
    for term in case.required_terms:
        if term not in joined:  # exact AEM/DITA terminology, case-sensitive
            problems.append(f"MISSING_EXACT_TERM: {term}")
    for branch in case.critical_branches:
        if branch.supported and not any(t.casefold() in lowered for t in branch.terms):
            problems.append(f"UNNAMED_BRANCH: {branch.name}")
    if case.requires_negative_contract and not any(_NEGATION_RE.search(t) for t in texts):
        problems.append("MISSING_NEGATIVE_CONTRACT")
    return problems


# --------------------------------------------------------------------------------------------
# Replay cases
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Branch:
    name: str
    terms: tuple[str, ...]
    query: str
    supported: bool  # product supports this branch, so it must not be dropped from the UAC
    benchmark_critical: bool = True


@dataclass(frozen=True)
class ReplayCase:
    slot: str
    jira_key: str
    tenant_id: str
    customer: str
    components: tuple[str, ...]
    decision_text: str  # text of the current Jira decision / accepted UAC
    newest_verification_comment: str  # distinctive text of the newest verification comment
    attachment_filename: str  # "" when the case has no applicable attachment
    critical_branches: tuple[Branch, ...]
    required_terms: tuple[str, ...]
    requires_negative_contract: bool
    notes: str = ""


def load_cases(path: Path) -> list[ReplayCase]:
    data = load_json(path)
    if not isinstance(data, Mapping) or data.get("schema_version") != CASES_SCHEMA:
        raise GateRefused("CASES_SCHEMA_MISMATCH", str(path))
    raw_cases = data.get("cases") or []
    by_slot = {str(c.get("slot") or ""): c for c in raw_cases if isinstance(c, Mapping)}
    missing = [slot for slot in CASE_SLOTS if slot not in by_slot]
    if missing or len(by_slot) != len(CASE_SLOTS):
        raise GateRefused("CASE_SET_NOT_FIXED", f"need exactly the slots {CASE_SLOTS}; missing {missing}")
    cases: list[ReplayCase] = []
    unfilled: list[str] = []
    for slot in CASE_SLOTS:
        raw = by_slot[slot]
        key = str(raw.get("jira_key") or "").strip()
        branches = tuple(
            Branch(
                name=str(b.get("name") or "").strip(),
                terms=tuple(str(t) for t in b.get("terms") or [] if str(t).strip()),
                query=str(b.get("query") or b.get("name") or "").strip(),
                supported=bool(b.get("supported")),
                benchmark_critical=bool(b.get("benchmark_critical", True)),
            )
            for b in raw.get("critical_branches") or []
        )
        if (
            not re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", key)
            or not str(raw.get("decision_text") or "").strip()
            or not str(raw.get("newest_verification_comment") or "").strip()
            or not branches
            or any(not b.name or not b.terms for b in branches)
        ):
            unfilled.append(slot)
            continue
        cases.append(
            ReplayCase(
                slot=slot,
                jira_key=key,
                tenant_id=str(raw.get("tenant_id") or "kone"),
                customer=str(raw.get("customer") or "").strip(),
                components=tuple(str(c) for c in raw.get("components") or []),
                decision_text=str(raw["decision_text"]).strip(),
                newest_verification_comment=str(raw["newest_verification_comment"]).strip(),
                attachment_filename=str(raw.get("attachment_filename") or "").strip(),
                critical_branches=branches,
                required_terms=tuple(str(t) for t in raw.get("required_terms") or [] if str(t).strip()),
                requires_negative_contract=bool(raw.get("requires_negative_contract")),
                notes=str(raw.get("notes") or ""),
            )
        )
    if unfilled:
        raise GateRefused(
            "CASE_EXPECTATIONS_UNFILLED",
            "QE must fill jira_key, decision_text, newest_verification_comment and critical_branches for: "
            + ", ".join(unfilled),
        )
    return cases


# --------------------------------------------------------------------------------------------
# Replay evaluation (pure: index access and search are injected)
# --------------------------------------------------------------------------------------------

# search(collection, query, k, where) -> ranked [{"id", "document", "metadata", "distance"?}]
SearchFn = Callable[[str, str, int, "Mapping[str, Any] | None"], list[dict[str, Any]]]
# chunks_for_key(jira_key) -> every jira_qa chunk stored for that key
ChunksFn = Callable[[str], list[dict[str, Any]]]

AUTHORITATIVE_CORPORA = frozenset({"aem_guides", "dita_spec"})
TOP_K = 5


@dataclass
class CaseRun:
    """One canonical-runtime replay of a case."""

    payload: Mapping[str, Any]  # GenerationResult.payload (coverage_dispositions, written ACs, ...)
    evidence_records: list[Mapping[str, Any]] = field(default_factory=list)


def _contains(haystack: str, needle: str) -> bool:
    return bool(needle) and _norm(needle) in _norm(haystack)


def _brief(row: Mapping[str, Any], corpus: str, rank: int) -> dict[str, Any]:
    meta = row.get("metadata") or {}
    return {
        "rank": rank,
        "corpus": corpus,
        "chunk_id": str(row.get("id") or ""),
        "jira_key": str(meta.get("jira_key") or ""),
        "chunk_type": str(meta.get("chunk_type") or ""),
        "customer": str(meta.get("customer") or ""),
        "distance": row.get("distance"),
    }


def _top(search: SearchFn, corpus: str, query: str, where: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    return list(search(corpus, query, TOP_K, where))[:TOP_K]


def evaluate_retrieval(case: ReplayCase, *, chunks_for_key: ChunksFn, search: SearchFn) -> dict[str, Any]:
    """Index- and retrieval-level checks for one case; deterministic for a fixed index."""
    failures: list[str] = []
    stored = chunks_for_key(case.jira_key)
    key_filter = {"jira_key": case.jira_key}

    def retrievable(label: str, needle: str, chunk_types: tuple[str, ...] | None = None) -> dict[str, Any]:
        in_index = [
            str(c.get("id"))
            for c in stored
            if _contains(str(c.get("document") or ""), needle)
            and (chunk_types is None or (c.get("metadata") or {}).get("chunk_type") in chunk_types)
        ]
        hits = _top(search, "jira_qa", needle, key_filter)
        in_top = [str(h.get("id")) for h in hits if _contains(str(h.get("document") or ""), needle)]
        if not in_index:
            failures.append(f"NOT_INDEXED:{label}")
        elif not in_top:
            failures.append(f"NOT_IN_TOP_{TOP_K}:{label}")
        return {
            "needle": needle,
            "indexed_chunk_ids": sorted(in_index),
            "top_k": [_brief(h, "jira_qa", i + 1) for i, h in enumerate(hits)],
            "retrieved_chunk_ids": in_top,
        }

    expected = {
        "current_decision": retrievable("current_decision", case.decision_text),
        "newest_verification_comment": retrievable("newest_verification_comment", case.newest_verification_comment),
    }
    if case.attachment_filename:
        expected["attachment"] = retrievable(
            "attachment", case.attachment_filename, chunk_types=("attachment_signal_chunk",)
        )

    customer_checks: list[dict[str, Any]] = []
    if case.customer:
        for branch in case.critical_branches:
            hits = _top(search, "jira_qa", branch.query, {"customer": case.customer})
            leaked = [
                _brief(h, "jira_qa", i + 1)
                for i, h in enumerate(hits)
                if str((h.get("metadata") or {}).get("customer") or "").strip() not in ("", case.customer)
            ]
            if leaked:
                failures.append(f"CROSS_CUSTOMER_EVIDENCE:{branch.name}")
            customer_checks.append({"branch": branch.name, "leaked": leaked, "returned": len(hits)})

    branch_evidence: list[dict[str, Any]] = []
    for branch in case.critical_branches:
        ranked: list[dict[str, Any]] = []
        authoritative: list[dict[str, Any]] = []
        for corpus in sorted(AUTHORITATIVE_CORPORA) + ["jira_qa"]:
            where = key_filter if corpus == "jira_qa" else None
            for i, hit in enumerate(_top(search, corpus, branch.query, where)):
                brief = _brief(hit, corpus, i + 1)
                ranked.append(brief)
                text = str(hit.get("document") or "")
                # jira_qa counts only for this ticket (its current decision); docs count as-is.
                if any(_contains(text, t) for t in branch.terms):
                    authoritative.append(brief)
        branch_evidence.append(
            {
                "branch": branch.name,
                "query": branch.query,
                "benchmark_critical": branch.benchmark_critical,
                "supported": branch.supported,
                "top_k": ranked,
                "authoritative_hits": authoritative,
            }
        )
    return {
        "slot": case.slot,
        "jira_key": case.jira_key,
        "indexed_chunk_count": len(stored),
        "expected_evidence": expected,
        "customer_filter": customer_checks,
        "branch_evidence": branch_evidence,
        "failures": failures,
    }


def evaluate_run(case: ReplayCase, run: CaseRun, retrieval: Mapping[str, Any]) -> dict[str, Any]:
    """Disposition- and UAC-level checks for one replay of one case."""
    rows = disposition_rows(run.payload)
    texts = written_ac_texts(run.payload.get("written_acceptance_criteria") or [])
    failures: list[str] = []

    for row in rows:
        if row["final_disposition"] == UNROUTED:
            failures.append(f"UNROUTED_CLAIM:{row['runtime_disposition']}:{row['claim'][:80]}")
        unsupported = (
            row["runtime_disposition"] == "UNSUPPORTED_INFERENCE"
            or (row["research_derived"] and not row["evidence_ids"])
            or (not row["evidence_ids"] and not row["source_fact_ids"])
        )
        if row["final_disposition"] == "UAC" and unsupported:
            failures.append(f"UNSUPPORTED_FINDING_IN_UAC:{row['claim'][:80]}")

    tbd_claims = [r["claim"] for r in rows if r["final_disposition"] == "TBD"]
    uac_text = "\n".join(texts)
    branch_results: list[dict[str, Any]] = []
    evidence_by_branch = {b["branch"]: b for b in retrieval.get("branch_evidence") or []}
    for branch in case.critical_branches:
        in_uac = any(_contains(uac_text, t) for t in branch.terms)
        as_tbd = any(_contains(claim, t) for claim in tbd_claims for t in branch.terms)
        has_authority = bool((evidence_by_branch.get(branch.name) or {}).get("authoritative_hits"))
        status = "UAC" if in_uac else "TBD" if as_tbd else "MISSING"
        if branch.benchmark_critical and not has_authority and not as_tbd:
            failures.append(f"CRITICAL_BRANCH_WITHOUT_EVIDENCE_OR_TBD:{branch.name}")
        if branch.supported and status == "MISSING":
            failures.append(f"SUPPORTED_BRANCH_REMOVED:{branch.name}")
        branch_results.append(
            {"branch": branch.name, "status": status, "authoritative_evidence_in_top_k": has_authority}
        )

    failures.extend(uac_style_problems(texts, case))
    counts = {d: sum(1 for r in rows if r["final_disposition"] == d) for d in (*FINAL_DISPOSITIONS, UNROUTED)}
    return {
        "dispositions": rows,
        "disposition_counts": counts,
        "written_acceptance_criteria": texts,
        "branches": branch_results,
        "failures": failures,
        "signature": disposition_signature(rows),
    }


def build_reports(
    cases: Sequence[ReplayCase],
    retrievals: Sequence[Sequence[Mapping[str, Any]]],
    runs: Sequence[Sequence[CaseRun]],
    *,
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Assemble both reports from N replays (retrievals[r][c], runs[r][c]); returns (replay, disposition, passed)."""
    replay_cases: list[dict[str, Any]] = []
    disposition_cases: list[dict[str, Any]] = []
    gate_failures: list[str] = []
    stale = {
        name: entry.get("stale_chunk_ids") or []
        for name, entry in (manifest.get("collections") or {}).items()
        if entry.get("stale_chunk_ids")
    }
    if stale:
        gate_failures.append("STALE_CHUNK_IDS_AFTER_REBUILD")

    for index, case in enumerate(cases):
        per_run_retrieval = [r[index] for r in retrievals]
        per_run = [evaluate_run(case, runs[r][index], per_run_retrieval[r]) for r in range(len(runs))]
        retrieval_identical = all(
            json.dumps(x, sort_keys=True, default=str) == json.dumps(per_run_retrieval[0], sort_keys=True, default=str)
            for x in per_run_retrieval[1:]
        )
        dispositions_identical = all(p["signature"] == per_run[0]["signature"] for p in per_run[1:])
        case_failures = sorted(set(per_run_retrieval[0]["failures"]))
        for p in per_run:
            case_failures.extend(f for f in p["failures"] if f not in case_failures)
        if not retrieval_identical:
            case_failures.append("RETRIEVAL_NOT_DETERMINISTIC")
        if not dispositions_identical:
            case_failures.append("DISPOSITIONS_NOT_IDENTICAL_ACROSS_REPLAYS")
        replay_cases.append(
            {
                "slot": case.slot,
                "jira_key": case.jira_key,
                "retrieval": per_run_retrieval[0],
                "retrieval_identical_across_replays": retrieval_identical,
            }
        )
        disposition_cases.append(
            {
                "slot": case.slot,
                "jira_key": case.jira_key,
                "replays": [{k: v for k, v in p.items() if k != "signature"} for p in per_run],
                "dispositions_identical_across_replays": dispositions_identical,
                "failures": case_failures,
                "passed": not case_failures,
            }
        )
        gate_failures.extend(f"{case.slot}:{f}" for f in case_failures)

    passed = not gate_failures and len(runs) >= 2
    if len(runs) < 2:
        gate_failures.append("FEWER_THAN_TWO_REPLAYS")
    header = {
        "generated_at": utc_now(),
        "replays": len(runs),
        "index_manifest": {
            "rebuilt_at": manifest.get("rebuilt_at"),
            "retrieval_code_sha256": (manifest.get("retrieval_code") or {}).get("sha256"),
            "source_commit": (manifest.get("source") or {}).get("commit"),
            "embedding": manifest.get("embedding"),
        },
    }
    replay_report = {"schema_version": REPLAY_SCHEMA, **header, "stale_chunk_ids": stale, "cases": replay_cases}
    disposition_report = {
        "schema_version": DISPOSITION_SCHEMA,
        **header,
        "passed": passed,
        "failures": gate_failures,
        "cases": disposition_cases,
    }
    return replay_report, disposition_report, passed


# --------------------------------------------------------------------------------------------
# Backend adapters (imported only after the staging environment is bound)
# --------------------------------------------------------------------------------------------

CONFIG_ENV_KEYS = (
    "JIRA_SMART_CHUNKING",
    "JIRA_SMART_CHUNK_MAX_CHARS",
    "JIRA_SMART_PROBLEM_SLICE",
    "JIRA_SMART_SLICE_OVERLAP",
    "JIRA_SMART_MAX_PARTS_PER_FIELD",
    "JIRA_QA_INDEX_ATTACHMENT_TEXT",
    "JIRA_QA_INDEX_ATTACHMENT_MAX",
    "JIRA_QA_INDEX_ATTACHMENT_BUDGET_SECONDS",
    "DOC_PDF_CHUNK_SIZE",
    "DOC_PDF_CHUNK_OVERLAP",
    "DOC_PDF_MAX_PAGES",
    "GITHUB_DITA_CHUNK_SIZE",
    "GITHUB_DITA_CHUNK_OVERLAP",
    "GITHUB_DITA_SOURCE_URL",
    "GITHUB_DITA_ALSO_MERGE_TO_AEM_RAG",
    "CHUNK_METADATA_ENABLED",
    "USE_PLAYWRIGHT_SCRAPER",
    "FLUFFYJAWS_MODE",
    "EVIDENCE_GRAPH_ENABLED",
    "EVIDENCE_GRAPH_TEST_PLAN_MODE",
)


def production_dirs() -> list[Path]:
    """Production stores to refuse, resolved from the environment *before* staging binding."""
    storage = Path(os.getenv("STORAGE_PATH", "./storage")).expanduser()
    if not storage.is_absolute():
        storage = BACKEND / storage
    dirs = [storage, BACKEND / "storage"]
    if os.getenv("CHROMA_PERSIST_DIR", "").strip():
        dirs.append(Path(os.environ["CHROMA_PERSIST_DIR"]))
    return dirs


def open_staging(staging_root: Path, *, create: bool) -> Path:
    """Bind the staging environment, load backend .env without letting it override staging."""
    target = prepare_staging_dir(staging_root, production_dirs=production_dirs(), create=create)
    if any(name == "app" or name.startswith("app.") for name in sys.modules):
        raise GateRefused("BACKEND_IMPORTED_BEFORE_STAGING", "backend modules were imported before binding")
    try:
        from dotenv import load_dotenv

        load_dotenv(BACKEND / ".env", override=False, encoding="utf-8-sig")
    except ImportError:
        pass
    bind_staging_environment(target)  # .env may have added CHROMA_HOST; staging wins
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    return target


def _config_snapshot() -> dict[str, str]:
    return {key: os.environ[key] for key in CONFIG_ENV_KEYS if key in os.environ}


def embedding_identity() -> dict[str, Any]:
    from app.services.embedding_service import get_embedding_diagnostics

    diag = get_embedding_diagnostics()
    return {
        "provider": diag.get("provider"),
        "model": diag.get("active_model_identifier") or diag.get("configured_model"),
        "configured_model": diag.get("configured_model"),
        "dimension": diag.get("last_vector_dimension"),
    }


class WriteRecorder:
    """Records every chunk id written through vector_store_service.add_documents."""

    def __init__(self) -> None:
        self.written: dict[str, set[str]] = {}
        self._patched: list[tuple[Any, str, Any]] = []

    def __enter__(self) -> "WriteRecorder":
        from app.services import vector_store_service as vss

        original = vss.add_documents
        recorder = self

        def recording_add_documents(collection_name, ids, *args, **kwargs):
            ok = original(collection_name, ids, *args, **kwargs)
            if ok:
                recorder.written.setdefault(str(collection_name), set()).update(str(i) for i in ids)
            return ok

        # Modules that did ``from ... import add_documents`` (possibly under an alias such as
        # ``chroma_add_documents``) hold their own reference; rebind every name bound to it.
        for module in list(sys.modules.values()):
            namespace = getattr(module, "__dict__", None)
            if not isinstance(namespace, dict):
                continue
            for attr, value in list(namespace.items()):
                if value is original:
                    self._patched.append((module, attr, original))
                    setattr(module, attr, recording_add_documents)
        return self

    def __exit__(self, *exc: Any) -> None:
        for module, attr, original in self._patched:
            setattr(module, attr, original)


def _import_all_writers() -> None:
    """Import every indexer first so WriteRecorder patches their add_documents references."""
    import app.services.crawl_service  # noqa: F401
    import app.services.dita_pdf_index_service  # noqa: F401
    import app.services.dita_spec_curated_chunk_service  # noqa: F401
    import app.services.doc_pdf_index_service  # noqa: F401
    import app.services.github_dita_examples_service  # noqa: F401
    import app.services.jira_qa_index_service  # noqa: F401


def scan_collections(written: Mapping[str, set[str]]) -> dict[str, Any]:
    """Full scan of every staging collection: digest plus ids this rebuild did not write."""
    from app.services import vector_store_service as vss

    client = vss._get_client()
    if client is None:
        raise GateRefused("CHROMA_UNAVAILABLE", "staging Chroma client could not be opened")
    names = sorted(c if isinstance(c, str) else c.name for c in client.list_collections())
    collections: dict[str, Any] = {}
    for name in names:
        records = list(vss.iter_collection_records(name, include_documents=True))
        stale = stale_chunk_ids((r["id"] for r in records), written.get(name, set()))
        collections[name] = {
            **corpus_digest(records),
            "written_this_rebuild": len(written.get(name, set())),
            "stale_chunk_count": len(stale),
            "stale_chunk_ids": stale[:200],
        }
    return collections


def _hash_files(paths: Iterable[Path]) -> dict[str, str]:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}


def _step(sources: dict[str, Any], name: str, fn: Callable[[], dict[str, Any]]) -> None:
    started = utc_now()
    try:
        detail = fn() or {}
        errors = detail.get("errors") or []
        status = "FAILED" if errors and not detail.get("chunks_written") else "OK"
        sources[name] = {"status": status, "started_at": started, "finished_at": utc_now(), **detail}
    except Exception as exc:  # recorded, and the freshness check then refuses the manifest
        sources[name] = {"status": "FAILED", "started_at": started, "finished_at": utc_now(), "error": str(exc)[:500]}
    print(f"  {name}: {sources[name]['status']}", flush=True)


def rebuild(args: argparse.Namespace) -> int:
    root = open_staging(Path(args.staging_chroma_dir), create=True)
    cases = load_cases(Path(args.cases))
    import asyncio
    import shutil

    _import_all_writers()
    from app.services import vector_store_service as vss

    tenant = args.tenant_id
    sources: dict[str, Any] = {}
    rebuilt_at = utc_now()
    with WriteRecorder() as recorder:

        def experience_league() -> dict[str, Any]:
            from app.services.crawl_service import crawl_and_index

            stats = crawl_and_index()
            url_config = BACKEND / "config" / "aem_guides_crawl_urls.json"
            out = {
                "pages_crawled": stats.get("pages_crawled"),
                "chunks_written": stats.get("chunks_stored"),
                "errors": [str(e)[:300] for e in stats.get("errors") or []][:50],
                "url_config": _hash_files([url_config]),
            }
            behavior = [Path(p) for p in args.behavior_chunks]
            if behavior:
                sys.path.insert(0, str(REPO / "scripts"))
                import upsert_behavior_chunks_json as behavior_upsert

                for path in behavior:
                    if behavior_upsert.main(["--input", str(path)]) != 0:
                        out["errors"].append(f"behavior chunk upsert failed: {path}")
                out["behavior_chunk_files"] = _hash_files(behavior)
            return out

        def github_dita() -> dict[str, Any]:
            from app.services.github_dita_examples_service import index_github_dita_examples

            result = asyncio.run(index_github_dita_examples(tenant_id=tenant))
            data = result.model_dump() if hasattr(result, "model_dump") else vars(result)
            return {
                "source_url": data.get("source_url"),
                "files_indexed": data.get("files_indexed"),
                "chunks_written": data.get("example_chunks_stored"),
                "errors": list(data.get("errors") or []),
            }

        def pdf() -> dict[str, Any]:
            from app.services.doc_pdf_index_service import index_pdf_directory

            pdf_dir = Path(args.pdf_dir or (production_dirs()[0] / "pdf_uploads" / tenant))
            results = asyncio.run(index_pdf_directory(pdf_dir, tenant, force=True))
            rows = [r.model_dump() if hasattr(r, "model_dump") else vars(r) for r in results]
            return {
                "pdf_dir": str(pdf_dir),
                "files": _hash_files(pdf_dir.glob("*.pdf")),
                "chunks_written": sum(len(r.get("chunk_ids") or []) for r in rows),
                "errors": [e for r in rows for e in (r.get("errors") or [])],
            }

        def dita_spec() -> dict[str, Any]:
            from app.services.dita_pdf_index_service import index_dita_pdf
            from app.services.dita_spec_curated_chunk_service import upsert_curated_dita_spec_chunks

            src = production_dirs()[0] / "dita_spec"
            dst = root / "storage" / "dita_spec"
            dst.mkdir(parents=True, exist_ok=True)
            for pdf_file in sorted(src.glob("*.pdf")):
                shutil.copy2(pdf_file, dst / pdf_file.name)
            stats = index_dita_pdf()
            curated = upsert_curated_dita_spec_chunks()
            return {
                "files": _hash_files(dst.glob("*.pdf")),
                "chunks_written": int(stats.get("chunks_stored") or 0) + int(curated or 0),
                "errors": [str(e)[:300] for e in stats.get("errors") or []][:50],
            }

        def jira_qa() -> dict[str, Any]:
            from app.services.jira_qa_index_service import index_jql_to_chroma

            keys = sorted({c.jira_key for c in cases})
            jql = "key in (" + ", ".join(f'"{k}"' for k in keys) + ")"
            if args.jira_jql:
                jql = f"({jql}) OR ({args.jira_jql})"
            out = index_jql_to_chroma(jql, limit=args.jira_limit, force_reindex=True, persist_sync_state=False)
            errors = [str(e) for e in out.get("errors") or []]
            case_failures = [e for e in errors if any(e.startswith(f"{k}:") for k in keys)]
            if out.get("error") or case_failures:
                # A replay case that is not in the index makes every later check meaningless.
                raise RuntimeError("; ".join([str(out.get("error") or ""), *case_failures]).strip("; ")[:500])
            return {
                "jql": jql,
                "case_keys": keys,
                "issues_indexed": out.get("issues_indexed"),
                "chunks_written": out.get("chunks"),
                "errors": [e[:300] for e in errors][:50],
            }

        # Order matters: crawl_and_index deletes aem_guides, so it runs before anything that
        # merges into aem_guides (behavior chunks, GitHub DITA).
        for name, fn in (
            ("experience_league", experience_league),
            ("github_dita", github_dita),
            ("pdf", pdf),
            ("dita_spec", dita_spec),
            ("jira_qa", jira_qa),
        ):
            if name in args.skip_source:
                sources[name] = {"status": "SKIPPED_BY_OPERATOR"}
                continue
            _step(sources, name, fn)

    collections = scan_collections(recorder.written)
    identity = vss.get_index_identity()
    manifest = build_manifest(
        collections=collections,
        embedding=embedding_identity(),
        config={**_config_snapshot(), "tenant_id": tenant, "storage_path": os.environ["STORAGE_PATH"]},
        staging_dir=str(root),
        rebuilt_at=rebuilt_at,
        sources=sources,
    )
    manifest["index_identity"] = {"target_fingerprint": identity.get("target_fingerprint"), "mode": identity.get("mode")}
    write_json(root / MANIFEST_FILE, manifest)
    reasons = check_manifest(
        manifest,
        current_code_sha256=code_fingerprint()["sha256"],
        code_changed_at=code_last_changed_at(),
        current_embedding=manifest["embedding"],
    )
    print(f"manifest: {root / MANIFEST_FILE}")
    if reasons:
        print("index NOT usable for benchmarking: " + ", ".join(reasons))
        return 2
    print("index fresh: rebuilt with the current retrieval/chunking code")
    return 0


def check(args: argparse.Namespace, *, with_embedding: bool = True) -> list[str]:
    manifest_path = Path(args.manifest) if getattr(args, "manifest", None) else Path(args.staging_chroma_dir) / MANIFEST_FILE
    manifest = load_json(manifest_path)
    current_embedding = None
    if with_embedding and isinstance(manifest, Mapping):
        current_embedding = embedding_identity()
        current_embedding = {k: v for k, v in current_embedding.items() if k in ("provider", "model") and v}
    return check_manifest(
        manifest,
        current_code_sha256=code_fingerprint()["sha256"],
        code_changed_at=code_last_changed_at(),
        current_embedding=current_embedding,
    )


def _search(collection: str, query: str, k: int, where: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    from app.services.embedding_service import embed_query
    from app.services.vector_store_service import query_collection

    vector = embed_query(query)
    if vector is None:
        raise GateRefused("EMBEDDING_UNAVAILABLE", "query embedding failed during replay")
    return query_collection(collection, list(vector), k=k, where=dict(where) if where else None)


def _chunks_for_key(jira_key: str) -> list[dict[str, Any]]:
    from app.services.vector_store_service import get_documents_where

    return get_documents_where("jira_qa", {"jira_key": jira_key}, limit=5000)


def _run_case(case: ReplayCase) -> CaseRun:
    from app.core.schemas_test_plan_pipeline import TestPlanPipelineRequest
    from app.services.test_plan_pipeline_service import run_test_plan_pipeline

    request = TestPlanPipelineRequest.model_validate(
        {
            "jira_key": case.jira_key,
            "tenant_id": case.tenant_id,
            "evidence_k": 8,
            "include_repository_evidence": True,
            "max_repo_matches": 30,
            "skip_uac_label_gate": True,
            "full_rag": True,
            "include_uac_intelligence": True,
            "compose_draft_plan": True,
            "write_starling_artifacts": False,
            "publish_to_team_ui": False,
        }
    )
    # benchmark_v2 runs the full canonical engine and skips every persistence path.
    result = run_test_plan_pipeline(request, entry_point="benchmark_v2").model_dump(mode="json")
    canonical = (result.get("qe_review_package") or {}).get("canonical_result") or {}
    payload = canonical.get("output_payload") or {}
    if not payload.get("coverage_dispositions") and not payload.get("written_acceptance_criteria"):
        raise GateRefused("RUNTIME_OUTPUT_MISSING", f"{case.jira_key}: no canonical output_payload")
    return CaseRun(payload=payload)


def replay(args: argparse.Namespace) -> int:
    root = open_staging(Path(args.staging_chroma_dir), create=False)
    reasons = check(args)
    if reasons:
        print("REFUSED: index manifest is not fresh for benchmarking: " + ", ".join(reasons))
        return 2
    cases = load_cases(Path(args.cases))
    manifest = load_json(root / MANIFEST_FILE) or {}
    retrievals: list[list[dict[str, Any]]] = []
    runs: list[list[CaseRun]] = []
    for replay_index in range(args.replays):
        print(f"replay {replay_index + 1}/{args.replays}", flush=True)
        retrievals.append(
            [evaluate_retrieval(c, chunks_for_key=_chunks_for_key, search=_search) for c in cases]
        )
        runs.append([_run_case(c) for c in cases])
    replay_report, disposition_report, passed = build_reports(cases, retrievals, runs, manifest=manifest)
    out_dir = Path(args.out) if args.out else root / "reports" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    write_json(out_dir / REPLAY_FILE, replay_report)
    write_json(out_dir / DISPOSITION_FILE, disposition_report)
    write_json(out_dir / MANIFEST_FILE, manifest)
    print(f"reports: {out_dir}")
    if passed:
        print("PASS: clean-index replay met every criterion")
        return 0
    print("FAIL:")
    for failure in disposition_report["failures"]:
        print(f"  - {failure}")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def staging(p: argparse.ArgumentParser) -> None:
        p.add_argument("--staging-chroma-dir", required=True, help="isolated staging root (created and marked by rebuild)")
        p.add_argument("--cases", default=str(DEFAULT_CASES), help="fixed five-case replay set")

    p_rebuild = sub.add_parser("rebuild", help="rebuild evaluation collections into staging and write the manifest")
    staging(p_rebuild)
    p_rebuild.add_argument("--tenant-id", default="kone")
    p_rebuild.add_argument("--jira-jql", default="", help="extra Jira slice (e.g. other customers, for filter checks)")
    p_rebuild.add_argument("--jira-limit", type=int, default=500)
    p_rebuild.add_argument("--pdf-dir", default="", help="PDFs to index (default: production pdf_uploads/<tenant>, read only)")
    p_rebuild.add_argument("--behavior-chunks", action="append", default=[], help="behavior chunk JSON to upsert into aem_guides")
    p_rebuild.add_argument(
        "--skip-source", action="append", default=[], choices=("experience_league", "github_dita", "pdf", "dita_spec", "jira_qa"),
        help="skip a source (recorded in the manifest; the check still requires jira_qa and aem_guides)",
    )

    p_check = sub.add_parser("check", help="exit 2 unless the manifest is fresh for the current code")
    p_check.add_argument("--staging-chroma-dir", default="")
    p_check.add_argument("--manifest", default="", help="manifest path (default: <staging>/rag-index-manifest.json)")
    p_check.add_argument("--no-embedding-check", action="store_true", help="skip loading backend embedding config")

    p_replay = sub.add_parser("replay", help="replay the five fixed cases twice against the staging index")
    staging(p_replay)
    p_replay.add_argument("--replays", type=int, default=2)
    p_replay.add_argument("--out", default="", help="report directory (default: <staging>/reports/<utc time>)")

    args = parser.parse_args(argv)
    try:
        if args.command == "rebuild":
            print("rebuilding staging RAG index (no production collections are touched)")
            return rebuild(args)
        if args.command == "check":
            if not args.manifest and not args.staging_chroma_dir:
                parser.error("check needs --manifest or --staging-chroma-dir")
            with_embedding = not args.no_embedding_check
            if with_embedding:
                if str(BACKEND) not in sys.path:
                    sys.path.insert(0, str(BACKEND))
            reasons = check(args, with_embedding=with_embedding)
            if reasons:
                print("REFUSED: " + ", ".join(reasons))
                return 2
            print("OK: index manifest is fresh for the current retrieval/chunking code")
            return 0
        if args.replays < 2:
            parser.error("--replays must be at least 2 (determinism is part of the pass criteria)")
        return replay(args)
    except GateRefused as refused:
        print(f"REFUSED: {refused}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
