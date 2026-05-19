"""Reranking layer for QA copilot hybrid search results."""

from __future__ import annotations

from typing import Any

from app.rag.metadata_filtering import JiraMetadataCriteria, metadata_score


class EnterpriseQaReranker:
    """Boost exact customer, feature, environment, issue type, and semantic scores."""

    def rerank(self, hits: list[dict[str, Any]], criteria: JiraMetadataCriteria) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for hit in hits:
            meta = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
            doc = str(hit.get("document") or "")
            base = float(hit.get("score") or hit.get("final_score") or 0.0)
            md_score, reasons = metadata_score(criteria, meta, doc)
            final = max(0.0, min(1.0, base + (0.2 * md_score)))
            row = dict(hit)
            row["score"] = round(final, 4)
            row["rerank"] = {
                **(row.get("rerank") if isinstance(row.get("rerank"), dict) else {}),
                "qa_copilot_metadata_score": round(md_score, 4),
                "qa_copilot_boost_reasons": reasons,
                "qa_copilot_final_score": round(final, 4),
            }
            out.append(row)
        return sorted(out, key=lambda x: float(x.get("score") or 0.0), reverse=True)

