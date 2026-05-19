"""Multi-source retrieval for UAC intelligence: Jira QA RAG, Experience League, DITA-OT specs."""

from __future__ import annotations

from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.core.structured_logging import get_structured_logger
from app.services.doc_retriever_service import retrieve_relevant_docs_with_diagnostics
from app.services.dita_knowledge_retriever import retrieve_dita_knowledge
from app.services.jira_retrieval_service import MIN_FINAL_SCORE, RetrievedJira, explain_similarity, retrieve_similar_jiras

logger = get_structured_logger(__name__)


def _retrieval_query_text(en: JiraEnrichedDocument) -> str:
    parts = [
        en.summary or "",
        (en.description or "")[:12000],
        (en.raw_text or "")[:6000],
        " ".join(en.dita_entities or []),
        " ".join(en.affected_outputs or []),
        " ".join(en.components or []),
    ]
    return "\n\n".join(p for p in parts if p.strip())


def _has_anchors(en: JiraEnrichedDocument) -> bool:
    return bool(
        (en.domain or "").strip().lower() not in {"", "unknown"}
        or (en.dita_entities or [])
        or (en.affected_outputs or [])
    )


def retrieve_for_intelligence(
    en: JiraEnrichedDocument,
    *,
    max_similar_jiras: int,
    include_docs: bool,
    top_k_experience_league: int = 4,
    top_k_dita_spec: int = 3,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Retrieve similar Jiras plus optional doc corpora.

    Weak Jira matches (below ``MIN_FINAL_SCORE``) are listed only in ``debug.weak_similar`` when ``debug`` is true.
    """
    jk = str(en.jira_key or "").strip()
    qtext = _retrieval_query_text(en)
    eff_domain = en.domain if en.domain != "unknown" else None

    similar: list[RetrievedJira] = []
    weak_similar: list[dict[str, Any]] = []
    if max_similar_jiras > 0 and _has_anchors(en):
        sink: dict[str, Any] | None = {} if debug else None
        rows = retrieve_similar_jiras(
            qtext,
            domain=eff_domain,
            dita_entities=list(en.dita_entities or []),
            affected_outputs=list(en.affected_outputs or []),
            customer_names=list(en.customer_names or []),
            limit=max(1, min(max_similar_jiras, 24)),
            exclude_jira_key=jk or None,
            base_labels=list(en.labels or []),
            base_components=list(en.components or []),
            retrieval_debug_sink=sink,
            sub_domain=en.sub_domain,
            issue_type=en.issue_type,
            require_non_vector_evidence=False,
        )
        for r in rows:
            if r.final_score >= MIN_FINAL_SCORE:
                similar.append(r)
            elif debug:
                weak_similar.append(
                    {
                        "jira_key": r.jira_key,
                        "final_score": r.final_score,
                        "why_similar": r.why_similar,
                    }
                )
        if debug and sink is not None:
            sink["strong_similar_count"] = len(similar)
            sink["total_candidates"] = len(rows)
    elif debug:
        logger.info_structured(
            "uac_intelligence_retrieval_skip_similar",
            extra_fields={"jira_key": jk, "reason": "no_anchors_or_limit_zero"},
        )

    cur = en.model_dump()
    similar_payload: list[dict[str, Any]] = []
    for r in similar:
        expl = explain_similarity(cur, r)
        similar_payload.append(
            {
                "jira_key": r.jira_key,
                "title": r.title,
                "chunk_type": r.chunk_type,
                "why_similar": r.why_similar or expl.get("why_similar", ""),
                "explanation": expl,
                "scores": {
                    "final": r.final_score,
                    "vector": r.vector_score,
                    "keyword": r.keyword_score,
                    "metadata": r.metadata_score,
                },
                "document_excerpt": (r.document or "")[:900],
            }
        )

    el_rows: list[dict[str, Any]] = []
    dita_rows: list[dict[str, Any]] = []
    el_diagnostics: dict[str, Any] = {}
    if include_docs and qtext.strip():
        el = retrieve_relevant_docs_with_diagnostics(qtext.strip(), k=top_k_experience_league)
        el_diagnostics = {k: el.get(k) for k in ("retrieval_mode", "warnings", "count") if k in el}
        for item in el.get("results") or []:
            el_rows.append(
                {
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("url") or ""),
                    "snippet": str(item.get("snippet") or "")[:1500],
                }
            )

        for chunk in retrieve_dita_knowledge(qtext.strip(), k=top_k_dita_spec):
            dita_rows.append(
                {
                    "element_name": str(chunk.get("element_name") or ""),
                    "text_content": str(chunk.get("text_content") or "")[:1500],
                    "source_url": str(chunk.get("source_url") or ""),
                }
            )

    out: dict[str, Any] = {
        "query_preview": qtext[:500],
        "similar_jiras": similar_payload,
        "experience_league": el_rows,
        "dita_spec": dita_rows,
        "retrieval_notes": [],
    }
    if include_docs:
        out["retrieval_notes"].append(f"experience_league_mode={el_diagnostics.get('retrieval_mode', 'n/a')}")
    if debug:
        out["debug"] = {
            "weak_similar": weak_similar,
            "experience_league_diagnostics": el_diagnostics,
            "MIN_FINAL_SCORE": MIN_FINAL_SCORE,
        }
    return out


__all__ = ["retrieve_for_intelligence"]
