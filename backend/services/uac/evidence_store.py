"""Evidence store for UAC Requirement Intelligence — every claim maps to typed evidence records."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Literal

EvidenceType = Literal["current_jira", "similar_jira", "experience_league_doc", "dita_ot_doc", "domain_knowledge"]


@dataclass
class EvidenceRecord:
    evidence_id: str
    evidence_type: EvidenceType
    summary: str
    source_ref: str
    metadata: dict[str, Any] = field(default_factory=dict)


class RequirementEvidenceStore:
    """Accumulates evidence with stable ids (E1, E2, …) for orchestrator outputs."""

    def __init__(self) -> None:
        self._counter = itertools.count(1)
        self.records: list[EvidenceRecord] = []

    def _next_id(self) -> str:
        return f"E{next(self._counter)}"

    def add(
        self,
        evidence_type: EvidenceType,
        summary: str,
        source_ref: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        eid = self._next_id()
        self.records.append(
            EvidenceRecord(
                evidence_id=eid,
                evidence_type=evidence_type,
                summary=(summary or "").strip()[:2000],
                source_ref=(source_ref or "").strip()[:500],
                metadata=dict(metadata or {}),
            )
        )
        return eid

    def manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "evidence_id": r.evidence_id,
                "evidence_type": r.evidence_type,
                "summary": r.summary,
                "source_ref": r.source_ref,
                "metadata": r.metadata,
            }
            for r in self.records
        ]

    def blob_for_validation(self) -> str:
        parts: list[str] = []
        for r in self.records:
            parts.append(f"{r.evidence_id} [{r.evidence_type}] {r.summary} :: {r.source_ref}")
        return "\n".join(parts).lower()


__all__ = ["EvidenceRecord", "EvidenceType", "RequirementEvidenceStore"]
