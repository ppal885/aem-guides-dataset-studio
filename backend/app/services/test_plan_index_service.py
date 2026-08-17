"""Index a validated skill-generated test plan markdown into the jira_qa ChromaDB collection."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

from app.services.test_plan_artifact_service import TEST_PLANS_DIR, _normalize_jira_key

# Section title -> chunk_type; None = skip (code-path / file-ref sections, not useful for retrieval)
_SECTION_MAP: dict[str, str | None] = {
    "Understanding From Jira": "understanding_chunk",
    "Acceptance Criteria": "acceptance_criteria_chunk",
    "Expected Behaviour": "learning_behavior_chunk",
    "Test Scenarios": "test_evidence_chunk",
    "Known Jira Bugs / Past Similar Tickets": "learning_behavior_chunk",
    "Regression Areas": "resolution_rca_chunk",
    "Open Questions": "resolution_rca_chunk",
    "Scope From Git": None,
    "Code Touched": None,
    "Lines Changed": None,
    "Automation Coverage & Gaps": None,
}

_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*\s*$", re.MULTILINE)


def _parse_sections(text: str) -> list[tuple[str, str, str]]:
    """Return [(title, body, chunk_type)] for indexable sections only."""
    matches = list(_HEADING_RE.finditer(text))
    out: list[tuple[str, str, str]] = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        ctype = _SECTION_MAP.get(title)
        if ctype is None:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            out.append((title, body, ctype))
    return out


def _build_rows(jira_key: str, sections: list[tuple[str, str, str]], plan_hash: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for title, body, ctype in sections:
        idx = counts.get(ctype, 0)
        counts[ctype] = idx + 1
        doc = f"[{jira_key} | {ctype}]\nSource: skill-generated test plan\n\n{body[:10000]}"
        rows.append({
            "chunk_id": f"{jira_key}::testplan::{ctype}::{idx}",
            "document": doc,
            "metadata": {
                "jira_key": jira_key,
                "chunk_type": ctype,
                "section_title": title[:120],
                "source": "skill_test_plan",
                "plan_hash": plan_hash[:64],
                "customer": "",
                "domain": "baseline",
                "enrich_domain": "baseline",
                "resolution": "",
                "import_source_type": "skill_test_plan",
            },
        })
    return rows


def _upsert_rows(rows: list[dict[str, Any]]) -> bool:
    from app.services.embedding_service import embed_texts_batched
    from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, add_documents

    documents = [r["document"] for r in rows]
    embeddings = embed_texts_batched(documents, batch_size=32)
    if embeddings is None:
        return False
    ids = [r["chunk_id"] for r in rows]
    metadatas = [
        {k: v for k, v in r["metadata"].items() if isinstance(v, (str, int, float, bool))}
        for r in rows
    ]
    vectors = [embeddings[i].tolist() for i in range(len(rows))]
    for attempt in range(1, 4):
        if add_documents(CHROMA_COLLECTION_JIRA_QA, ids, documents, metadatas, vectors):
            return True
        if attempt < 3:
            time.sleep(0.5 * attempt)
    return False


def index_test_plan(jira_key: str, markdown: str | None = None) -> dict[str, Any]:
    """
    Index a validated plan into jira_qa ChromaDB.

    If `markdown` is supplied, index it directly (used during save).
    Otherwise read the saved plan file from TEST_PLANS_DIR (used for re-indexing).
    """
    from app.services.vector_store_service import is_chroma_available
    from app.services.embedding_service import is_embedding_available

    key = _normalize_jira_key(jira_key)

    if markdown is None:
        plan_file = TEST_PLANS_DIR / f"{key}-test-plan.md"
        if not plan_file.exists():
            raise FileNotFoundError(f"No saved plan for {key} at {plan_file}")
        markdown = plan_file.read_text(encoding="utf-8")

    plan_hash = hashlib.sha256(markdown.encode()).hexdigest()
    sections = _parse_sections(markdown)
    if not sections:
        return {
            "jira_key": key,
            "indexed": False,
            "reason": "No recognised sections found — plan may not be in 11-section format.",
            "chunks_indexed": 0,
        }

    if not is_chroma_available():
        return {
            "jira_key": key,
            "indexed": False,
            "reason": "ChromaDB unavailable",
            "chunks_indexed": 0,
        }
    if not is_embedding_available():
        return {
            "jira_key": key,
            "indexed": False,
            "reason": "Embedding model unavailable",
            "chunks_indexed": 0,
        }

    rows = _build_rows(key, sections, plan_hash)
    ok = _upsert_rows(rows)
    chunk_ids = [r["chunk_id"] for r in rows]
    return {
        "jira_key": key,
        "indexed": ok,
        "chunks_indexed": len(rows) if ok else 0,
        "plan_hash": plan_hash[:16] + "...",
        "chunk_ids": chunk_ids if ok else [],
        "reason": None if ok else "Upsert failed — check ChromaDB and embedding service logs.",
    }
