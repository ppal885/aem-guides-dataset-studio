"""Offline history retrieval for the golden benchmark (UACFIX-13).

When the live ``search_jira_history`` MCP is not available, the benchmark cannot
validate its history-dependent cases and retrieval-quality regressions go
unmonitored. This module provides an OFFLINE substitute: it retrieves candidate
historical Jira keys from the local ``jira_qa`` ChromaDB corpus and scores each
case's history recall against a documented per-case floor.

Honesty contract:
  * The result is ALWAYS labelled ``source="offline_chroma"`` and
    ``indexed_history_run=False``. It is a regression monitor, NEVER a live
    ``indexed_history_run=True`` claim and must not be presented as one.
  * If the local corpus is unavailable, we record that plainly and fail closed
    (exit non-zero) rather than fabricate a passing run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from app.benchmarks.test_plan_quality.models import BenchmarkManifest

OFFLINE_SOURCE = "offline_chroma"
DEFAULT_TOP_K = 10
# Conservative default floor: offline dense retrieval over the local jira_qa
# corpus recalls less than a live, filtered search_jira_history run, so the floor
# is a REGRESSION floor (catch drops from today's measured recall), not a target.
DEFAULT_RECALL_FLOOR = 0.0


@dataclass
class OfflineCaseResult:
    case_id: str
    jira_key: str
    expected_history_keys: list[str]
    expect_no_strong_history: bool
    retrieved_top_k: list[str] = field(default_factory=list)
    recall: Optional[float] = None
    floor: float = 0.0
    status: str = "scored"  # scored | no_expected_history | corpus_unavailable
    passed: bool = True

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "jira_key": self.jira_key,
            "expected_history_keys": self.expected_history_keys,
            "expect_no_strong_history": self.expect_no_strong_history,
            "retrieved_top_k": self.retrieved_top_k,
            "recall": self.recall,
            "floor": self.floor,
            "status": self.status,
            "passed": self.passed,
        }


def load_floors(path: Optional[Path]) -> tuple[float, dict[str, float]]:
    """Return (default_floor, per_case_floors) from an optional YAML config."""
    if path is None or not path.exists():
        return DEFAULT_RECALL_FLOOR, {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    default = float(data.get("default_recall_floor", DEFAULT_RECALL_FLOOR))
    cases = {
        str(cid): float(val)
        for cid, val in (data.get("cases") or {}).items()
    }
    return default, cases


def _retrieve_history_keys(query_text: str, k: int) -> Optional[list[str]]:
    """Return distinct Jira keys from jira_qa for the query, best-rank first.

    Returns None when the local corpus / embeddings are unavailable (so the
    caller can fail closed instead of scoring 0 as if the corpus were empty).
    """
    try:
        from app.services.embedding_service import embed_query
        from app.services.vector_store_service import (
            CHROMA_COLLECTION_JIRA_QA,
            _collection_exists,
            _get_client,
            query_collection,
        )
    except Exception:
        return None

    client = _get_client()
    if not client or not _collection_exists(client, CHROMA_COLLECTION_JIRA_QA):
        return None

    embedding = embed_query(query_text)
    if embedding is None:
        return None
    embedding = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    if not embedding:
        return None

    # Fetch extra rows because a ticket contributes several chunks; we dedupe to
    # distinct jira keys and keep only the first k distinct keys by rank.
    rows = query_collection(CHROMA_COLLECTION_JIRA_QA, embedding, k=max(k * 6, 24)) or []
    ordered: list[str] = []
    for row in rows:
        key = str((row.get("metadata") or {}).get("jira_key", "")).strip().upper()
        if key and key not in ordered:
            ordered.append(key)
        if len(ordered) >= k:
            break
    return ordered


def run_offline_history(
    manifest: BenchmarkManifest,
    *,
    top_k: int = DEFAULT_TOP_K,
    floors_path: Optional[Path] = None,
) -> dict:
    """Score every case's offline history recall. Returns a report dict."""
    default_floor, per_case = load_floors(floors_path)
    results: list[OfflineCaseResult] = []

    for case in manifest.cases:
        floor = per_case.get(case.id, default_floor)
        query_text = case.query
        terms = getattr(case, "required_query_terms", None) or []
        if terms:
            query_text = f"{query_text} " + " ".join(terms)

        res = OfflineCaseResult(
            case_id=case.id,
            jira_key=case.jira_key,
            expected_history_keys=list(case.expected_history_keys),
            expect_no_strong_history=bool(case.expect_no_strong_history),
            floor=floor,
        )

        retrieved = _retrieve_history_keys(query_text, top_k)
        if retrieved is None:
            res.status = "corpus_unavailable"
            res.passed = False
            results.append(res)
            continue

        res.retrieved_top_k = retrieved
        if res.expect_no_strong_history or not res.expected_history_keys:
            # No positive history target for this case; not scored against a
            # recall floor (a "no strong history" golden cannot regress on recall).
            res.status = "no_expected_history"
            res.recall = None
            res.passed = True
        else:
            expected = set(res.expected_history_keys)
            hit = expected & set(retrieved)
            res.recall = round(len(hit) / len(expected), 4)
            res.passed = res.recall >= floor
        results.append(res)

    scored = [r for r in results if r.status == "scored"]
    unavailable = [r for r in results if r.status == "corpus_unavailable"]
    all_pass = bool(results) and all(r.passed for r in results)

    return {
        "schema_version": "aem-guides-offline-history-v1",
        "source": OFFLINE_SOURCE,
        "indexed_history_run": False,
        "note": (
            "Offline jira_qa Chroma retrieval. This is a retrieval-regression "
            "monitor, not a live search_jira_history run; never cite it as "
            "indexed_history_run=True."
        ),
        "top_k": top_k,
        "default_recall_floor": default_floor,
        "benchmark_id": manifest.benchmark_id,
        "case_count": len(results),
        "scored_count": len(scored),
        "corpus_unavailable_count": len(unavailable),
        "passed": all_pass,
        "cases": [r.to_dict() for r in results],
    }


def render_offline_report(report: dict) -> str:
    lines = [
        f"# Offline history benchmark (source={report['source']})",
        "",
        f"indexed_history_run: {report['indexed_history_run']} (offline monitor, not a live claim)",
        f"cases: {report['case_count']}  scored: {report['scored_count']}  "
        f"corpus_unavailable: {report['corpus_unavailable_count']}",
        "",
    ]
    for c in report["cases"]:
        if c["status"] == "corpus_unavailable":
            lines.append(f"- {c['case_id']} ({c['jira_key']}): CORPUS UNAVAILABLE -> FAIL")
        elif c["status"] == "no_expected_history":
            lines.append(
                f"- {c['case_id']} ({c['jira_key']}): no expected history (not scored) -> PASS"
            )
        else:
            verdict = "PASS" if c["passed"] else "FAIL"
            lines.append(
                f"- {c['case_id']} ({c['jira_key']}): recall={c['recall']} "
                f"floor={c['floor']} expected={c['expected_history_keys']} -> {verdict}"
            )
    lines.append("")
    lines.append(f"RESULT: {'PASS' if report['passed'] else 'FAIL'}")
    lines.append("")
    return "\n".join(lines)
