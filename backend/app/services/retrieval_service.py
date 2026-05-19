"""Customer-aware Jira retrieval service for the enterprise QA copilot."""

from __future__ import annotations

import re
from typing import Any

from app.models.jira_models import CommonPattern, JiraIssueDetails, JiraIssueSearchResult
from app.rag.hybrid_search import HybridJiraSearch, HybridSearchOutput
from app.rag.metadata_filtering import JiraMetadataCriteria, metadata_contains, parse_json_list
from app.services.jira_qa_retrieval_service import get_chunks_for_jira_key, live_jira_snapshot_chunk


_PATTERN_LEXICON: dict[str, tuple[str, ...]] = {
    "conref resolution failures": ("conref", "content reference", "broken reference"),
    "UUID mismatch": ("uuid", "guid", "identifier mismatch"),
    "publishing regression": ("publish", "publishing", "pdf", "native pdf", "output"),
    "keyref/conkeyref failures": ("keyref", "conkeyref", "keydef"),
    "preview vs output mismatch": ("preview", "output mismatch", "rendered output"),
    "stale references after rename or move": ("stale", "rename", "move", "moved topic"),
    "editor synchronization issues": ("web editor", "sync", "synchronization", "save reopen"),
    "DITAVAL filtering issues": ("ditaval", "conditional processing", "condition"),
}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _shorten(text: str, limit: int = 420) -> str:
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."


def _line_after(label: str, text: str) -> str | None:
    pat = re.compile(rf"{re.escape(label)}\s*[:\-]\s*(?P<value>.+)", flags=re.IGNORECASE)
    for line in (text or "").splitlines():
        match = pat.search(line.strip())
        if match:
            return _shorten(match.group("value"), 300)
    return None


def _metadata_list(meta: dict[str, Any], *keys: str) -> list[str]:
    out: list[str] = []
    for key in keys:
        for item in parse_json_list(meta.get(key)):
            if item not in out:
                out.append(item)
    return out


class QaCopilotRetrievalService:
    """Retrieval and historical pattern analysis backed by the Jira QA index."""

    def __init__(self, search_engine: HybridJiraSearch | None = None) -> None:
        self.search_engine = search_engine or HybridJiraSearch()
        self.last_search_debug: dict[str, Any] = {}

    def search_jira_issues(
        self,
        *,
        customer: str | None,
        feature: str | None,
        issue_type: str | None,
        environment: str | None,
        editor_type: str | None = None,
        output_type: str | None = None,
        time_window_days: int | None = None,
        source_jira_key: str | None = None,
        escalation_only: bool = False,
        limit: int = 10,
    ) -> tuple[list[JiraIssueSearchResult], HybridSearchOutput]:
        criteria = JiraMetadataCriteria(
            customer=customer,
            feature=feature,
            issue_type=issue_type,
            environment=environment,
            editor_type=editor_type,
            output_type=output_type,
            time_window_days=time_window_days,
            source_jira_key=source_jira_key,
            escalation_only=escalation_only,
        )
        output = self.search_engine.search(criteria, limit=limit)
        rows = [self._hit_to_issue(hit, criteria) for hit in output.hits]
        self.last_search_debug = output.debug
        return rows, output

    def _hit_to_issue(self, hit: dict[str, Any], criteria: JiraMetadataCriteria) -> JiraIssueSearchResult:
        meta = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        doc = str(hit.get("document") or "")
        labels = _metadata_list(meta, "labels", "customer_labels")
        components = _metadata_list(meta, "components")
        customer = str(meta.get("customer") or "").strip() or None
        if not customer and criteria.customer and metadata_contains(
            criteria.customer,
            meta,
            doc,
            fields=("customer_labels", "labels", "enrich_customers"),
        ):
            customer = criteria.customer
        root_cause = _first_text(
            str(meta.get("root_cause_summary") or ""),
            _line_after("Root cause", doc) or "",
            _line_after("Cause", doc) or "",
        ) or None
        resolution = _first_text(str(meta.get("resolution") or ""), _line_after("Resolution", doc) or "") or None
        return JiraIssueSearchResult(
            issue_key=str(hit.get("jira_key") or meta.get("jira_key") or "").strip(),
            summary=_first_text(str(hit.get("title") or ""), str(meta.get("title") or ""), str(meta.get("summary") or "")),
            customer=customer,
            feature=criteria.feature,
            labels=labels,
            issue_type=str(meta.get("issue_type") or criteria.issue_type or "").strip() or None,
            component=", ".join(components[:4]) or str(meta.get("component") or "").strip() or None,
            environment=str(meta.get("environment") or criteria.environment or "").strip() or None,
            similarity_score=float(hit.get("score") or 0.0),
            matched_snippet=_shorten(doc),
            resolution=resolution,
            root_cause_summary=root_cause,
            why_relevant=_first_text(
                str(hit.get("why_similar") or ""),
                str((hit.get("retrieval") or {}).get("why_similar") if isinstance(hit.get("retrieval"), dict) else ""),
                "Retrieved by hybrid Jira QA search with metadata and semantic relevance signals.",
            ),
            metadata=meta,
        )

    def get_related_issue_details(self, issues: list[JiraIssueSearchResult]) -> list[JiraIssueDetails]:
        details: list[JiraIssueDetails] = []
        for issue in issues:
            chunks = get_chunks_for_jira_key(issue.issue_key)
            live = live_jira_snapshot_chunk(issue.issue_key)
            if live:
                chunks.insert(0, live)
            if not chunks:
                chunks = [
                    {
                        "jira_key": issue.issue_key,
                        "chunk_type": "search_result_snippet",
                        "document": issue.matched_snippet,
                        "metadata": issue.metadata,
                    }
                ]
            details.append(self._chunks_to_details(issue, chunks))
        return details

    def _chunks_to_details(self, issue: JiraIssueSearchResult, chunks: list[dict[str, Any]]) -> JiraIssueDetails:
        docs_by_type: dict[str, list[str]] = {}
        all_meta: dict[str, Any] = dict(issue.metadata)
        for chunk in chunks:
            meta = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            all_meta.update({k: v for k, v in meta.items() if v not in (None, "", [], {})})
            ctype = str(chunk.get("chunk_type") or meta.get("chunk_type") or "unknown")
            doc = str(chunk.get("document") or "").strip()
            if doc:
                docs_by_type.setdefault(ctype, []).append(doc)
        blob = "\n\n".join(doc for docs in docs_by_type.values() for doc in docs)
        description = "\n\n".join(
            docs_by_type.get("description", [])
            + docs_by_type.get("description_long_part", [])
            + docs_by_type.get("full_ticket_summary", [])
            + docs_by_type.get("live_jira_snapshot", [])
        )
        comments = "\n\n".join(docs_by_type.get("comments_discussion", []) + docs_by_type.get("comments_summary", []))
        affected = _metadata_list(all_meta, "enrich_entities", "enrich_outputs", "components")
        customers = _metadata_list(all_meta, "enrich_customers", "customer_labels")
        if issue.customer and issue.customer not in customers:
            customers.insert(0, issue.customer)
        root_cause = issue.root_cause_summary or _line_after("Root cause", blob) or _line_after("Cause", blob)
        patterns = self._detect_patterns_in_text(blob)
        return JiraIssueDetails(
            issue_key=issue.issue_key,
            summary=issue.summary,
            description=_shorten(description, 2400),
            comments_summary=_shorten(comments, 1600),
            linked_issues=_metadata_list(all_meta, "linked_issues")[:20],
            regression_patterns=patterns,
            root_cause=root_cause,
            affected_areas=affected[:20],
            impacted_customers=customers[:20],
            qa_notes=_shorten("\n\n".join(docs_by_type.get("qa_notes", []) + docs_by_type.get("regression_risks", [])), 1400),
            automation_notes=_shorten("\n\n".join(docs_by_type.get("automation_notes", [])), 1400),
            evidence_chunks=[
                {
                    "chunk_type": str(c.get("chunk_type") or (c.get("metadata") or {}).get("chunk_type") or "unknown"),
                    "snippet": _shorten(str(c.get("document") or ""), 360),
                    "metadata": c.get("metadata") or {},
                }
                for c in chunks[:24]
            ],
            metadata=all_meta,
        )

    def detect_common_patterns(self, details: list[JiraIssueDetails]) -> list[CommonPattern]:
        buckets: dict[str, set[str]] = {}
        root_causes: dict[str, set[str]] = {}
        modules: dict[str, set[str]] = {}
        for detail in details:
            blob = "\n".join(
                [
                    detail.summary,
                    detail.description,
                    detail.comments_summary,
                    detail.qa_notes,
                    detail.automation_notes,
                    " ".join(detail.regression_patterns),
                ]
            )
            for pattern in self._detect_patterns_in_text(blob):
                buckets.setdefault(pattern, set()).add(detail.issue_key)
                if detail.root_cause:
                    root_causes.setdefault(pattern, set()).add(detail.root_cause)
                if detail.affected_areas:
                    modules.setdefault(pattern, set()).update(detail.affected_areas)
        out: list[CommonPattern] = []
        for pattern, keys in sorted(buckets.items(), key=lambda item: (-len(item[1]), item[0])):
            frequency = len(keys)
            out.append(
                CommonPattern(
                    pattern=pattern,
                    frequency=frequency,
                    probable_root_causes=sorted(root_causes.get(pattern) or {"Not stated in retrieved evidence."})[:5],
                    regression_risk="High" if frequency >= 3 else ("Medium" if frequency >= 2 else "Low"),
                    impacted_modules=sorted(modules.get(pattern) or set())[:8],
                    supporting_issues=sorted(keys),
                )
            )
        return out[:10]

    def _detect_patterns_in_text(self, text: str) -> list[str]:
        blob = (text or "").lower()
        patterns: list[str] = []
        for pattern, needles in _PATTERN_LEXICON.items():
            if any(needle in blob for needle in needles):
                patterns.append(pattern)
        return patterns
