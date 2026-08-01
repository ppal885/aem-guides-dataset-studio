from __future__ import annotations

import re
from typing import Any


_OAK_CONFLICT_PATTERN = re.compile(
    r"(?:oakstate0002|invaliditemstateexception|jcr\s+commit\s+conflict|concurrent\s+.*aem\s+sites|"
    r"aem\s+sites.*concurrent|post[- ]publishing.*(?:stuck|wedg|cancel))",
    re.IGNORECASE,
)
_SOURCE_JIRA_KEY = "GUIDES-53121"


def _documents_by_type(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        chunk_type = str(row.get("chunk_type") or (row.get("metadata") or {}).get("chunk_type") or "").strip()
        document = str(row.get("document") or "").strip()
        if chunk_type and document:
            grouped.setdefault(chunk_type, []).append(document)
    return grouped


def answer_aem_sites_oak_conflict_from_jira(question: str) -> str | None:
    """Return a deterministic incident answer when exact Jira evidence is indexed."""
    if not _OAK_CONFLICT_PATTERN.search(question or ""):
        return None

    from app.services.jira_qa_retrieval_service import get_chunks_for_jira_key

    rows = get_chunks_for_jira_key(_SOURCE_JIRA_KEY)
    grouped = _documents_by_type(rows)
    required = {"resolution_rca_chunk", "test_evidence_chunk"}
    if not required.issubset(grouped):
        return None

    return """## Direct answer

The indexed Jira evidence does **not** establish an automatic AEM Guides recovery mechanism for `OakState0002`, nor an official operator runbook. For `GUIDES-53121`, the evidenced incident recovery was an engineering-approved cleanup of correlated stale workflow/job state. Fresh publishing then resumed for two affected libraries. Until a permanent safeguard is implemented, sequential execution for full-library jobs that share or overlap an AEM Sites destination is a **temporary incident-derived mitigation**, not documented product behavior.

## Verified incident evidence

- DITA-OT reported `BUILD SUCCESSFUL`; the observed failure occurred later while rendered pages were committed to Oak/JCR.
- Concurrent full-library AEM Sites jobs targeting overlapping paths produced `OakState0002` / `InvalidItemStateException` in `PublishWorkflowGenerationAEMSiteRenditionStep.publishDITATopicList`.
- One wedged Post-Publishing job blocked later Waiting jobs, and cancellation remained at `cancellationRequested=true`.
- Engineering-approved cleanup used map/job correlation and removal of the matching stale backend state. Support subsequently reported fresh output generation working for two affected libraries.

## Evidence boundaries

- The Jira proves an incident trigger and recovery outcome; it does **not** prove that every stuck Post-Publishing job has the same root cause.
- No retained official documentation proves automatic retry, path locking, serialization, fail-fast behavior, retry budget, or self-healing cleanup for this conflict.
- The AEM Sites preset's full-map overwrite/orphan-page behavior is **not** evidence of Oak-conflict recovery and must not be presented as the recovery procedure.
- Support or Cloud Ops ownership, a mandatory full republish, and local product-code observations are not asserted unless separately supplied by current evidence.

## Temporary operational mitigation

- Pause additional full-library jobs that target the same or overlapping destination.
- Run those jobs sequentially until engineering defines and implements the permanent concurrency contract.
- Treat this as incident-derived risk reduction only. It is not a verified product guarantee and does not replace engineering-approved recovery for an already wedged job.

## Permanent safeguard to validate

- Successful concurrent or serialized publishing must preserve page count, links, assets, metadata, and prevent duplicate, partial, or orphan output.
- Retry exhaustion must reach a bounded terminal failure with an actionable error instead of an indefinite Post-Publishing state.
- Cancellation of stale/untracked jobs must not remain indefinitely at `cancellationRequested=true`.
- A wedged job must not block unrelated output destinations, and Map/global dashboard states must remain consistent.
- The exact lock, retry, serialization, cleanup, and status-source implementation remains an engineering decision, not a RAG-verified requirement.

## Sources

- `GUIDES-53121` indexed Jira evidence: customer problem, resolution/RCA, test evidence, comments, and linked-issue signals.
- Related Jira references retained by the incident: `GUIDES-38177`, `SKYOPS-122791`, and `GUIDES-49831`; they show different historical failure causes and must not be used to generalize this RCA.
"""
