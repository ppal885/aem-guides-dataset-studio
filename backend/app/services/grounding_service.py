from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from app.core.structured_logging import get_structured_logger
from app.services.llm_service import _coerce_llm_text_response

logger = get_structured_logger(__name__)

_STOPWORDS = {
    "a", "an", "and", "or", "the", "to", "for", "from", "with", "without", "this", "that", "these", "those",
    "issue", "ticket", "topic", "task", "story", "feature", "bug", "page", "document", "article", "guide",
    "guides", "user", "users", "when", "where", "what", "how", "using", "used", "into", "onto",
    "you", "your", "mean", "means", "meant",
}

_NEGATION_TERMS = {"not", "never", "without", "unsupported", "disabled", "disable", "cannot", "can't"}
_AFFIRMATION_TERMS = {"supported", "enabled", "enable", "can", "works", "allowed"}

_SOURCE_AUTHORITY = {
    "tenant_context": ("tenant_approved", 1.0),
    "tenant_examples": ("approved_example", 0.95),
    "aem_guides": ("platform_doc", 0.78),
    "dita_spec": ("standards_doc", 0.72),
    "dita_graph": ("standards_doc", 0.7),
    "claude_setup": ("operational_note", 0.45),
    "tavily": ("web_result", 0.2),
    "unknown": ("unknown", 0.1),
}

_SOURCE_POLICY_BONUS = {
    "tenant_context": 0.12,
    "tenant_examples": 0.08,
    "aem_guides": 0.03,
    "dita_spec": 0.02,
    "dita_graph": 0.02,
    "claude_setup": -0.05,
    "tavily": -0.15,
    "unknown": -0.08,
}

_SOURCE_LABELS = {
    "tenant_context": "Tenant Knowledge",
    "tenant_examples": "Approved Example",
    "aem_guides": "Experience League",
    "dita_spec": "DITA Spec",
    "dita_graph": "DITA Structure",
    "claude_setup": "Claude / Adobe Setup",
    "tavily": "Web Result",
}

_DOC_TYPE_LABELS = {
    "approved_topic": "Approved Topic",
    "style_guide": "Style Guide",
    "terminology": "Terminology",
    "api_reference": "API Reference",
    "product_doc": "Product Doc",
    "user_manual": "User Manual",
    "release_notes": "Release Notes",
}

_DITA_EXAMPLE_REQUEST_PATTERN = re.compile(
    r"\b(example|sample|snippet|skeleton|template|boilerplate|minimal|show me|give me)\b",
    re.IGNORECASE,
)
_DITA_STRUCTURE_QUERY_PATTERN = re.compile(
    r"</?[A-Za-z][A-Za-z0-9._:-]*>|"
    r"\b(dita|ditamap|xml|doctype|element|attribute|content model|topicref|topichead|topicgroup|mapref|navref|"
    r"keydef|keyref|conref|conkeyref|href|reltable|bookmap|glossentry|subject scheme|"
    r"task topic|concept topic|reference topic|specialization|constraint|keyscope)\b",
    re.IGNORECASE,
)
_DITA_ROOT_HINTS = (
    ("reference", re.compile(r"\b(reference topic|reference|refbody)\b", re.IGNORECASE)),
    ("task", re.compile(r"\b(task topic|task|taskbody|steps?)\b", re.IGNORECASE)),
    ("concept", re.compile(r"\b(concept topic|concept|conbody)\b", re.IGNORECASE)),
    ("topic", re.compile(r"\b(topic|body)\b", re.IGNORECASE)),
)
_PLACEHOLDER_PHRASES = (
    "briefly introduce",
    "provide an overview",
    "present detailed information",
    "summarize the key points",
    "replace this",
    "placeholder",
)


@dataclass
class Citation:
    id: str
    label: str
    title: str
    uri: str = ""
    section: str = ""
    page: str = ""
    authority: str = ""
    source_kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceChunk:
    id: str
    source_kind: str
    tenant_id: str
    doc_type: str
    authority: str
    title: str
    uri: str
    section: str
    page: str
    content: str
    authority_score: float
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    rerank_score: float = 0.0
    coverage_score: float = 0.0
    duplicate_group: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def citation(self) -> Citation:
        label_parts = [self.title or _SOURCE_LABELS.get(self.source_kind, "Evidence")]
        if self.section:
            label_parts.append(self.section)
        if self.page:
            label_parts.append(f"p. {self.page}")
        return Citation(
            id=self.id,
            label=" | ".join(part for part in label_parts if part),
            title=self.title or _SOURCE_LABELS.get(self.source_kind, "Evidence"),
            uri=self.uri,
            section=self.section,
            page=self.page,
            authority=self.authority,
            source_kind=self.source_kind,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["citation"] = self.citation().to_dict()
        return payload


@dataclass
class GroundingDecision:
    status: str
    confidence: float
    reason: str
    evidence_count: int
    source_kinds: list[str] = field(default_factory=list)
    has_conflict: bool = False
    thin_evidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidencePack:
    query: str
    tenant_id: str
    chunks: list[EvidenceChunk]
    decision: GroundingDecision
    issue_key: str = ""

    def citations(self, limit: int = 4) -> list[Citation]:
        return [chunk.citation() for chunk in self.chunks[:limit]]

    def top_titles(self, limit: int = 4) -> list[str]:
        seen: set[str] = set()
        titles: list[str] = []
        for chunk in self.chunks:
            title = (chunk.title or _SOURCE_LABELS.get(chunk.source_kind, "Evidence")).strip()
            if not title or title in seen:
                continue
            seen.add(title)
            titles.append(title)
            if len(titles) >= limit:
                break
        return titles

    def build_prompt_context(self, max_chars: int = 5000, limit: int = 6) -> str:
        blocks: list[str] = []
        for chunk in self.chunks[:limit]:
            citation = chunk.citation()
            header = f"[{citation.id}] {citation.label}"
            if chunk.authority:
                header += f" ({chunk.authority})"
            blocks.append(f"{header}\n{chunk.content[:900]}")
        content = "\n\n".join(blocks)
        return content[:max_chars] + ("\n\n[truncated]" if len(content) > max_chars else "")

    def evidence_summary(self) -> dict[str, Any]:
        return {
            "evidence_count": len(self.chunks),
            "top_sources": [citation.label for citation in self.citations(limit=4)],
            "top_titles": self.top_titles(limit=4),
            "status": self.decision.status,
            "confidence": self.decision.confidence,
            "reason": self.decision.reason,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "tenant_id": self.tenant_id,
            "issue_key": self.issue_key,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "decision": self.decision.to_dict(),
            "citations": [citation.to_dict() for citation in self.citations(limit=8)],
            "evidence_summary": self.evidence_summary(),
        }


@dataclass
class GroundedAnswer:
    answer: str
    citation_ids: list[str]
    unsupported_points: list[str]
    grounding_status: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SectionEvidence:
    section: str
    citation_ids: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _tokenize(text: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9._/-]{2,}", text or ""):
        lowered = token.lower()
        if lowered in _STOPWORDS or lowered in seen:
            continue
        seen.add(lowered)
        tokens.append(token)
    return tokens[:16]


def _sentence_split(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", _normalize_space(text))
    return [part.strip() for part in parts if part.strip()]


def _first_sentence(text: str) -> str:
    sentences = _sentence_split(text)
    return sentences[0] if sentences else _normalize_space(text)


def _term_overlap_ratio(query: str, text: str) -> float:
    query_terms = _tokenize(query)
    if not query_terms:
        return 1.0
    lowered_text = (text or "").lower()
    matched = sum(1 for token in query_terms if token.lower() in lowered_text)
    return matched / max(1, len(query_terms))


def _phrase_bonus(query: str, text: str) -> float:
    text_lower = (text or "").lower()
    bonus = 0.0
    for token in _tokenize(query)[:6]:
        if token.lower() in text_lower:
            bonus += 0.05
    return min(0.2, bonus)


def _missing_query_terms(question: str, evidence_pack: "EvidencePack") -> list[str]:
    if not evidence_pack.chunks:
        return []
    all_text = " ".join(chunk.content.lower() for chunk in evidence_pack.chunks[:4])
    missing: list[str] = []
    for token in _tokenize(question):
        lowered = token.lower()
        if lowered in all_text:
            continue
        if lowered in missing:
            continue
        missing.append(lowered)
    return missing[:4]


def _top_evidence_points(evidence_pack: "EvidencePack", *, limit: int = 3) -> list[str]:
    points: list[str] = []
    for chunk in evidence_pack.chunks[:limit]:
        citation = chunk.citation()
        sentence = _first_sentence(chunk.content)
        if not sentence:
            continue
        points.append(f"[{citation.id}] {sentence}")
    return points


def _format_structured_answer(
    *,
    short_answer: str,
    how_it_works: Iterable[str] | None = None,
    verified_points: Iterable[str] | None = None,
    not_verified_points: Iterable[str] | None = None,
    citations: Iterable[Citation] | None = None,
) -> str:
    sections: list[str] = ["## Short answer", _normalize_space(short_answer) or "I don't have enough verified information to answer that confidently."]

    how_points = [_normalize_space(point) for point in (how_it_works or []) if _normalize_space(point)]
    if how_points:
        sections.extend(["", "## How it works", *[f"- {point}" for point in how_points]])

    verified = [_normalize_space(point) for point in (verified_points or []) if _normalize_space(point)]
    not_verified = [_normalize_space(point) for point in (not_verified_points or []) if _normalize_space(point)]
    if verified or not_verified:
        sections.extend(["", "## What is verified / not verified"])
        sections.extend([f"- Verified: {point}" for point in verified])
        sections.extend([f"- Not verified: {point}" for point in not_verified])

    selected_citations = list(citations or [])
    if selected_citations:
        sections.extend(["", "## Sources"])
        sections.extend(
            [
                f"- [{citation.id}] {citation.label}{f' - {citation.uri}' if citation.uri else ''}"
                for citation in selected_citations
            ]
        )

    return "\n".join(sections).strip()


def _doc_type_label(doc_type: str) -> str:
    return _DOC_TYPE_LABELS.get(doc_type or "", doc_type or "")


def _extract_page(metadata: dict[str, Any], uri: str) -> str:
    page = str(metadata.get("page") or "").strip()
    if page:
        return page
    match = re.search(r"[#?&]page=(\d+)", uri or "")
    return match.group(1) if match else ""


def _source_authority(source_kind: str, metadata: dict[str, Any]) -> tuple[str, float]:
    authority, base_score = _SOURCE_AUTHORITY.get(source_kind or "unknown", _SOURCE_AUTHORITY["unknown"])
    credibility = str(metadata.get("credibility") or "").strip()
    if credibility:
        try:
            base_score = max(base_score, min(1.0, float(credibility)))
        except ValueError:
            pass
    doc_type = str(metadata.get("doc_type") or "").strip()
    if doc_type == "approved_topic":
        base_score = max(base_score, 0.95)
    elif doc_type in {"style_guide", "terminology"}:
        base_score = max(base_score, 0.9)
    return authority, base_score


def _source_policy_bonus(source_kind: str, coverage_score: float, lexical_score: float) -> float:
    base_bonus = _SOURCE_POLICY_BONUS.get(source_kind or "unknown", _SOURCE_POLICY_BONUS["unknown"])
    if base_bonus == 0.0:
        return 0.0
    relevance_scale = max(0.25, min(1.0, (coverage_score * 0.75) + (lexical_score * 0.25)))
    return round(base_bonus * relevance_scale, 3)


def _candidate_metadata(candidate: Any) -> dict[str, Any]:
    metadata = getattr(candidate, "metadata", None) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    raw = metadata.get("raw")
    if isinstance(raw, dict):
        raw_metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else raw
        if isinstance(raw_metadata, dict):
            merged = dict(raw_metadata)
            merged.update(metadata)
            metadata = merged
    return metadata


def _candidate_doc_type(source_kind: str, metadata: dict[str, Any]) -> str:
    if metadata.get("doc_type"):
        return str(metadata.get("doc_type"))
    if source_kind == "tenant_examples":
        return "approved_topic"
    if source_kind == "aem_guides":
        return "product_doc"
    if source_kind in {"dita_spec", "dita_graph"}:
        return "spec"
    return "other"


def _candidate_title(candidate: Any, source_kind: str, metadata: dict[str, Any]) -> str:
    for key in ("title", "label", "filename", "element_name", "source"):
        value = _normalize_space(str(metadata.get(key) or ""))
        if value:
            return value
    label = _normalize_space(str(getattr(candidate, "label", "") or ""))
    if label:
        return label
    return _SOURCE_LABELS.get(source_kind, "Evidence")


def _candidate_uri(candidate: Any, metadata: dict[str, Any]) -> str:
    for key in ("url", "source_url", "download_url"):
        value = _normalize_space(str(metadata.get(key) or ""))
        if value:
            return value
    return _normalize_space(str(getattr(candidate, "url", "") or ""))


def _candidate_section(metadata: dict[str, Any]) -> str:
    for key in ("section", "heading", "element_name", "filename"):
        value = _normalize_space(str(metadata.get(key) or ""))
        if value:
            return value
    return ""


def _dedupe_chunks(chunks: Iterable[EvidenceChunk]) -> list[EvidenceChunk]:
    deduped: list[EvidenceChunk] = []
    seen: set[str] = set()
    for chunk in chunks:
        key = f"{chunk.source_kind}:{chunk.duplicate_group}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    return deduped


def _detect_conflicts(query: str, chunks: list[EvidenceChunk]) -> tuple[bool, str]:
    versions = {
        version
        for chunk in chunks[:4]
        for version in re.findall(r"\b\d+(?:\.\d+){1,2}\b", chunk.content)
    }
    if len(versions) > 2 and any(version in query for version in versions) is False:
        major_versions = {v.split(".")[0] for v in versions}
        if len(major_versions) > 1:
            return True, f"Top evidence mentions multiple versions: {', '.join(sorted(versions)[:3])}."

    neg_only_chunks: set[int] = set()
    aff_only_chunks: set[int] = set()
    for idx, chunk in enumerate(chunks[:3]):
        text = chunk.content.lower()
        has_neg = any(term in text for term in _NEGATION_TERMS)
        has_aff = any(term in text for term in _AFFIRMATION_TERMS)
        if has_neg and not has_aff:
            neg_only_chunks.add(idx)
        elif has_aff and not has_neg:
            aff_only_chunks.add(idx)
    if neg_only_chunks and aff_only_chunks:
        return True, "Top evidence contains both supported and unsupported signals."
    return False, ""


def build_evidence_pack(
    *,
    query: str,
    tenant_id: str,
    candidates: Iterable[Any],
    issue_key: str = "",
    max_chunks: int = 8,
) -> EvidencePack:
    query_text = _normalize_space(query)
    normalized: list[EvidenceChunk] = []
    for index, candidate in enumerate(candidates, start=1):
        source_kind = _normalize_space(str(getattr(candidate, "source", "") or "")) or "unknown"
        content = _normalize_space(str(getattr(candidate, "text", "") or ""))
        if not content:
            continue
        metadata = _candidate_metadata(candidate)
        authority, authority_score = _source_authority(source_kind, metadata)
        title = _candidate_title(candidate, source_kind, metadata)
        uri = _candidate_uri(candidate, metadata)
        section = _candidate_section(metadata)
        page = _extract_page(metadata, uri)
        lexical_score = _term_overlap_ratio(query_text, content)
        semantic_score = max(0.0, float(getattr(candidate, "score", 0.0) or 0.0))
        coverage_score = min(1.0, lexical_score + _phrase_bonus(query_text, content))
        policy_bonus = _source_policy_bonus(source_kind, coverage_score, lexical_score)
        rerank_score = min(
            1.0,
            (authority_score * 0.48)
            + (lexical_score * 0.24)
            + (coverage_score * 0.16)
            + (min(1.0, semantic_score) * 0.04)
            + policy_bonus,
        )
        duplicate_group = re.sub(r"\W+", " ", content.lower())[:180]
        normalized.append(
            EvidenceChunk(
                id=f"E{index}",
                source_kind=source_kind,
                tenant_id=tenant_id,
                doc_type=_candidate_doc_type(source_kind, metadata),
                authority=authority,
                title=title,
                uri=uri,
                section=section,
                page=page,
                content=content,
                authority_score=round(authority_score, 3),
                lexical_score=round(lexical_score, 3),
                semantic_score=round(semantic_score, 3),
                rerank_score=round(rerank_score, 3),
                coverage_score=round(coverage_score, 3),
                duplicate_group=duplicate_group,
                metadata=metadata,
            )
        )

    normalized.sort(
        key=lambda chunk: (
            -chunk.rerank_score,
            -chunk.authority_score,
            -chunk.coverage_score,
            -chunk.lexical_score,
            _SOURCE_AUTHORITY.get(chunk.source_kind, _SOURCE_AUTHORITY["unknown"])[1] * -1,
        )
    )
    deduped = _dedupe_chunks(normalized)[:max_chunks]
    has_conflict, conflict_reason = _detect_conflicts(query_text, deduped)
    avg_score = (
        sum(chunk.rerank_score for chunk in deduped[:3]) / max(1, min(3, len(deduped)))
        if deduped
        else 0.0
    )
    thin_evidence = len(deduped) < 2 or sum(1 for chunk in deduped[:3] if chunk.authority_score >= 0.75) == 0
    if not deduped:
        decision = GroundingDecision(
            status="abstain",
            confidence=0.0,
            reason="No indexed evidence matched this query strongly enough.",
            evidence_count=0,
            source_kinds=[],
            has_conflict=False,
            thin_evidence=True,
        )
    elif has_conflict:
        decision = GroundingDecision(
            status="conflict",
            confidence=round(min(0.55, avg_score), 2),
            reason=conflict_reason or "Top evidence is conflicting.",
            evidence_count=len(deduped),
            source_kinds=list(dict.fromkeys(chunk.source_kind for chunk in deduped[:4])),
            has_conflict=True,
            thin_evidence=thin_evidence,
        )
    elif thin_evidence or avg_score < 0.45:
        decision = GroundingDecision(
            status="abstain",
            confidence=round(avg_score, 2),
            reason="Evidence is too thin or weak to support a confident answer.",
            evidence_count=len(deduped),
            source_kinds=list(dict.fromkeys(chunk.source_kind for chunk in deduped[:4])),
            has_conflict=False,
            thin_evidence=True,
        )
    elif avg_score < 0.68:
        decision = GroundingDecision(
            status="partial",
            confidence=round(avg_score, 2),
            reason="Evidence is useful but incomplete, so the answer should stay narrow.",
            evidence_count=len(deduped),
            source_kinds=list(dict.fromkeys(chunk.source_kind for chunk in deduped[:4])),
            has_conflict=False,
            thin_evidence=False,
        )
    else:
        decision = GroundingDecision(
            status="grounded",
            confidence=round(min(0.98, avg_score), 2),
            reason="Evidence is strong enough to answer within the indexed documentation.",
            evidence_count=len(deduped),
            source_kinds=list(dict.fromkeys(chunk.source_kind for chunk in deduped[:4])),
            has_conflict=False,
            thin_evidence=False,
        )
    return EvidencePack(
        query=query_text,
        tenant_id=tenant_id,
        chunks=deduped,
        decision=decision,
        issue_key=issue_key,
    )


def build_abstention_answer(question: str, evidence_pack: EvidencePack, tenant_id: str) -> str:
    closest_sources = [citation.label for citation in evidence_pack.citations(limit=3)]
    verified_points = [evidence_pack.decision.reason]
    if closest_sources:
        verified_points.append(f"Closest verified sources: {', '.join(closest_sources)}.")
    not_verified_points = [
        "The indexed evidence is too thin or conflicting to support a confident answer.",
        f"Workspace: `{tenant_id}`.",
    ]
    return _format_structured_answer(
        short_answer="I don't have enough verified information in the indexed documentation to answer that confidently.",
        verified_points=verified_points,
        not_verified_points=not_verified_points,
        citations=evidence_pack.citations(limit=3),
    )


def build_grounding_metadata(
    evidence_pack: EvidencePack,
    *,
    corrected_query: str = "",
    correction_applied: bool = False,
    unsupported_points: list[str] | None = None,
    llm: dict[str, Any] | None = None,
    answer_kind: str = "",
    source_policy: str = "",
    example_verified: bool = False,
    semantic_warnings: list[str] | None = None,
    retrieval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    citations = [citation.to_dict() for citation in evidence_pack.citations(limit=6)]
    return {
        "query": evidence_pack.query,
        "status": evidence_pack.decision.status,
        "confidence": evidence_pack.decision.confidence,
        "reason": evidence_pack.decision.reason,
        "has_conflict": evidence_pack.decision.has_conflict,
        "thin_evidence": evidence_pack.decision.thin_evidence,
        "corrected_query": corrected_query,
        "correction_applied": correction_applied,
        "citations": citations,
        "evidence_summary": evidence_pack.evidence_summary(),
        "unsupported_points": unsupported_points or [],
        "llm": llm or {},
        "answer_kind": answer_kind,
        "source_policy": source_policy,
        "example_verified": example_verified,
        "semantic_warnings": semantic_warnings or [],
        "retrieval": retrieval or {},
    }


def build_section_evidence_map(
    evidence_pack: EvidencePack,
    *,
    sections: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    desired_sections = list(sections or ["title", "shortdesc", "context", "steps", "result", "version_note"])
    if not evidence_pack.chunks:
        return {section: SectionEvidence(section=section, note="No grounded evidence available.").to_dict() for section in desired_sections}

    citations = evidence_pack.citations(limit=6)
    example_ids = [citation.id for citation in citations if citation.source_kind == "tenant_examples"]
    tenant_ids = [citation.id for citation in citations if citation.source_kind == "tenant_context"]
    platform_ids = [citation.id for citation in citations if citation.source_kind == "aem_guides"]
    spec_ids = [citation.id for citation in citations if citation.source_kind in {"dita_spec", "dita_graph"}]
    version_ids = [
        chunk.citation().id
        for chunk in evidence_pack.chunks
        if re.search(r"\b\d+(?:\.\d+){1,2}\b", chunk.content)
    ]

    mapping = {
        "title": SectionEvidence("title", (tenant_ids or platform_ids or spec_ids)[:2], "Keep the title aligned to the highest-authority subject terms."),
        "shortdesc": SectionEvidence("shortdesc", (tenant_ids + platform_ids)[:2] or spec_ids[:1], "Use only outcome language that is supported by evidence."),
        "context": SectionEvidence("context", (tenant_ids + platform_ids + spec_ids)[:3], "Explain when the task applies using grounded problem context."),
        "steps": SectionEvidence("steps", (example_ids + tenant_ids + platform_ids + spec_ids)[:4], "Prefer approved examples and tenant docs for procedural detail."),
        "result": SectionEvidence("result", (tenant_ids + platform_ids)[:2] or spec_ids[:1], "State only the verified end state."),
        "version_note": SectionEvidence("version_note", version_ids[:2], "Only include a version note when the cited evidence explicitly mentions it."),
    }
    return {section: mapping.get(section, SectionEvidence(section=section, citation_ids=[])).to_dict() for section in desired_sections}


def _heuristic_supported_sentences(answer: str, evidence_pack: EvidencePack) -> tuple[list[str], list[str]]:
    supported: list[str] = []
    unsupported: list[str] = []
    for sentence in _sentence_split(answer):
        normalized_sentence = re.sub(r"^[#>\-\*\s`]+", "", sentence or "").replace("`", "").strip()
        if not normalized_sentence:
            continue
        if len(normalized_sentence) < 25:
            supported.append(normalized_sentence)
            continue
        if max((_term_overlap_ratio(normalized_sentence, chunk.content) for chunk in evidence_pack.chunks[:4]), default=0.0) >= 0.18:
            supported.append(normalized_sentence)
        else:
            unsupported.append(normalized_sentence)
    return supported, unsupported


def _looks_like_dita_structure_question(question: str) -> bool:
    return bool(_DITA_STRUCTURE_QUERY_PATTERN.search(question or ""))


def _looks_like_dita_example_request(question: str) -> bool:
    return bool(_looks_like_dita_structure_question(question) and _DITA_EXAMPLE_REQUEST_PATTERN.search(question or ""))


def _requested_dita_root(question: str) -> str | None:
    text = question or ""
    for root_name, pattern in _DITA_ROOT_HINTS:
        if pattern.search(text):
            return root_name
    return None


def _safe_example_for_root(root_name: str) -> str | None:
    root = (root_name or "").strip().lower()
    if root == "task":
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">\n'
            '<task id="sample-task">\n'
            '  <title>Sample task</title>\n'
            '  <shortdesc>Describe the task outcome.</shortdesc>\n'
            '  <taskbody>\n'
            '    <steps>\n'
            '      <step>\n'
            '        <cmd>Perform the action.</cmd>\n'
            '      </step>\n'
            '    </steps>\n'
            '  </taskbody>\n'
            '</task>'
        )
    if root == "concept":
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "technicalContent/dtd/concept.dtd">\n'
            '<concept id="sample-concept">\n'
            '  <title>Sample concept</title>\n'
            '  <shortdesc>Summarize the concept in one sentence.</shortdesc>\n'
            '  <conbody>\n'
            '    <p>Explain the concept here.</p>\n'
            '  </conbody>\n'
            '</concept>'
        )
    if root == "reference":
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "technicalContent/dtd/reference.dtd">\n'
            '<reference id="sample-reference">\n'
            '  <title>Sample reference</title>\n'
            '  <shortdesc>Summarize what this reference topic covers.</shortdesc>\n'
            '  <refbody>\n'
            '    <section>\n'
            '      <title>Details</title>\n'
            '      <p>Document the supported details here.</p>\n'
            '    </section>\n'
            '  </refbody>\n'
            '</reference>'
        )
    if root == "topic":
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">\n'
            '<topic id="sample-topic">\n'
            '  <title>Sample topic</title>\n'
            '  <shortdesc>Summarize the topic.</shortdesc>\n'
            '  <body>\n'
            '    <p>Write the topic content here.</p>\n'
            '  </body>\n'
            '</topic>'
        )
    return None


def _extract_xml_code_blocks(answer: str) -> list[str]:
    if not answer:
        return []
    blocks = re.findall(r"```(?:xml)?\s*([\s\S]*?)```", answer, flags=re.IGNORECASE)
    extracted = [block.strip() for block in blocks if block and block.strip()]
    if extracted:
        return extracted
    stripped = answer.strip()
    if stripped.startswith("<?xml") or stripped.startswith("<!DOCTYPE") or stripped.startswith("<topic") or stripped.startswith("<task") or stripped.startswith("<concept") or stripped.startswith("<reference"):
        return [stripped]
    return []


def _xml_block_has_placeholder_content(xml_text: str) -> bool:
    lowered = (xml_text or "").lower()
    if any(phrase in lowered for phrase in _PLACEHOLDER_PHRASES):
        return True
    return (
        lowered.count("<title>introduction</title>") >= 1
        and lowered.count("<title>body</title>") >= 1
        and lowered.count("<title>conclusion</title>") >= 1
    )


def _looks_like_overconfident_draft(
    *,
    question: str,
    draft_answer: str,
    evidence_pack: EvidencePack,
    supported: list[str],
    unsupported: list[str],
) -> bool:
    if evidence_pack.decision.status in {"abstain", "conflict"}:
        return True
    xml_blocks = _extract_xml_code_blocks(draft_answer)
    if xml_blocks and _looks_like_dita_structure_question(question):
        return True
    if any(_xml_block_has_placeholder_content(block) for block in xml_blocks):
        return True
    if (
        "## Short answer" in draft_answer
        and ("## Verified details" in draft_answer or "## Sources" in draft_answer)
        and not unsupported
    ):
        return False
    if unsupported and (not supported or len(unsupported) >= len(supported)):
        return True
    return False


def _build_evidence_only_answer(
    *,
    question: str,
    evidence_pack: EvidencePack,
    verified_examples: list[dict[str, Any]] | None = None,
) -> str:
    citations = evidence_pack.citations(limit=4)
    short_answer = _first_sentence(evidence_pack.chunks[0].content) if evidence_pack.chunks else ""
    if not short_answer:
        short_answer = "I don't have enough verified information in the indexed evidence to answer that confidently."
    how_it_works = []
    for chunk in evidence_pack.chunks[:3]:
        sentence = _first_sentence(chunk.content)
        if sentence and sentence not in how_it_works:
            how_it_works.append(sentence)
    verified_points = [evidence_pack.decision.reason]
    not_verified_points: list[str] = []
    missing_terms = _missing_query_terms(question, evidence_pack)
    for term in missing_terms[:3]:
        not_verified_points.append(f"The term `{term}` was not directly verified in the retrieved evidence.")
    answer = _format_structured_answer(
        short_answer=short_answer,
        how_it_works=how_it_works[:3],
        verified_points=verified_points,
        not_verified_points=not_verified_points,
        citations=citations,
    )
    examples = [item for item in (verified_examples or []) if isinstance(item, dict) and str(item.get("snippet") or "").strip()]
    if examples:
        first = examples[0]
        label = str(first.get("label") or "Verified example").strip()
        snippet = str(first.get("snippet") or "").strip()
        answer = answer + f"\n\n## {label}\n```xml\n{snippet}\n```"
    return answer


async def verify_grounded_answer(
    *,
    question: str,
    draft_answer: str,
    evidence_pack: EvidencePack,
    jira_id: str | None = None,
    verified_examples: list[dict[str, Any]] | None = None,
    structured_tool_answer: bool = False,
) -> GroundedAnswer:
    draft_answer = _coerce_llm_text_response(draft_answer)
    verified_examples = [item for item in (verified_examples or []) if isinstance(item, dict)]

    # When we have a good draft answer (generated with full RAG context and
    # the rich chat_system prompt), pass it through directly — the draft is
    # already grounded via the RAG context it was built with.  Appending a
    # sources section gives the user provenance without a second LLM call
    # that was reformatting / destroying the answer.
    if draft_answer.strip():
        supported, unsupported = _heuristic_supported_sentences(draft_answer, evidence_pack)
        citation_objects = evidence_pack.citations(limit=5)
        citation_ids = [c.id for c in citation_objects]
        if not structured_tool_answer and (verified_examples or _looks_like_overconfident_draft(
            question=question,
            draft_answer=draft_answer,
            evidence_pack=evidence_pack,
            supported=supported,
            unsupported=unsupported,
        )):
            answer_text = _build_evidence_only_answer(
                question=question,
                evidence_pack=evidence_pack,
                verified_examples=verified_examples,
            )
            return GroundedAnswer(
                answer=answer_text,
                citation_ids=citation_ids,
                unsupported_points=list(unsupported[:4]),
                grounding_status="partial",
                reason="The draft answer was narrowed to verified evidence before being returned.",
            )
        answer_text = draft_answer.strip()
        if "## Short answer" not in answer_text:
            draft_points = [
                sentence
                for sentence in (_first_sentence(part.strip()) for part in draft_answer.splitlines() if part.strip())
                if sentence
            ]
            short_answer = draft_points[0] if draft_points else supported[0] if supported else ""
            how_it_works = draft_points[1:3] if len(draft_points) > 1 else supported[1:3]
            if not how_it_works:
                how_it_works = _top_evidence_points(evidence_pack, limit=2)
            verified_points = _top_evidence_points(evidence_pack, limit=3)
            not_verified = list(unsupported[:3])
            for term in _missing_query_terms(question, evidence_pack)[:3]:
                note = f"The term `{term}` was not directly verified in the retrieved evidence."
                if note not in not_verified:
                    not_verified.append(note)
            if not short_answer:
                short_answer = _first_sentence(evidence_pack.chunks[0].content) if evidence_pack.chunks else ""
            if not short_answer:
                short_answer = "I don't have enough verified information to answer that confidently."
            answer_text = _format_structured_answer(
                short_answer=short_answer,
                how_it_works=how_it_works[:3],
                verified_points=verified_points,
                not_verified_points=not_verified,
                citations=citation_objects,
            )
        elif citation_objects and "## Sources" not in answer_text:
            sources_lines = ["\n\n## Sources"]
            for c in citation_objects:
                label = c.label or c.id
                uri_part = f" - {c.uri}" if c.uri else ""
                sources_lines.append(f"- [{c.id}] {label}{uri_part}")
            answer_text += "\n".join(sources_lines)
        status = evidence_pack.decision.status
        if status in {"abstain", "conflict"}:
            status = "partial"
        return GroundedAnswer(
            answer=answer_text,
            citation_ids=citation_ids,
            unsupported_points=[],
            grounding_status=status,
            reason=evidence_pack.decision.reason,
        )

    # No draft answer — evidence only (abstention path)
    if evidence_pack.decision.status in {"abstain", "conflict"}:
        answer = build_abstention_answer(question, evidence_pack, evidence_pack.tenant_id)
        return GroundedAnswer(
            answer=answer,
            citation_ids=[citation.id for citation in evidence_pack.citations(limit=3)],
            unsupported_points=[],
            grounding_status=evidence_pack.decision.status,
            reason=evidence_pack.decision.reason,
        )

    # Fallback: heuristic answer from evidence chunks
    supported, unsupported = _heuristic_supported_sentences(draft_answer, evidence_pack)
    short_answer = supported[0] if supported else _first_sentence(evidence_pack.chunks[0].content) if evidence_pack.chunks else ""
    how_it_works = supported[1:3] if len(supported) > 1 else _top_evidence_points(evidence_pack, limit=2)
    verified_points = _top_evidence_points(evidence_pack, limit=3)
    not_verified = list(unsupported[:3])
    missing_terms = _missing_query_terms(question, evidence_pack)
    for term in missing_terms:
        not_verified.append(f"The term `{term}` itself was not directly verified in the retrieved evidence.")
    if not short_answer:
        short_answer = "I don't have enough verified information to answer that confidently."
    return GroundedAnswer(
        answer=_format_structured_answer(
            short_answer=short_answer,
            how_it_works=how_it_works,
            verified_points=verified_points,
            not_verified_points=not_verified,
            citations=evidence_pack.citations(limit=3),
        ),
        citation_ids=[citation.id for citation in evidence_pack.citations(limit=3)],
        unsupported_points=not_verified[:4],
        grounding_status="partial" if not_verified else evidence_pack.decision.status,
        reason=evidence_pack.decision.reason if not not_verified else "The final answer was narrowed to supported statements only.",
    )


def grounding_metadata_from_pack(
    evidence_pack: EvidencePack,
    grounded_answer: GroundedAnswer,
    *,
    corrected_query: str = "",
    correction_applied: bool = False,
    llm: dict[str, Any] | None = None,
    answer_kind: str = "",
    source_policy: str = "",
    example_verified: bool = False,
    semantic_warnings: list[str] | None = None,
    retrieval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    citation_lookup = {citation.id: citation.to_dict() for citation in evidence_pack.citations(limit=8)}
    selected = [citation_lookup[citation_id] for citation_id in grounded_answer.citation_ids if citation_id in citation_lookup]
    payload = build_grounding_metadata(
        evidence_pack,
        corrected_query=corrected_query,
        correction_applied=correction_applied,
        unsupported_points=grounded_answer.unsupported_points,
        llm=llm,
        answer_kind=answer_kind,
        source_policy=source_policy,
        example_verified=example_verified,
        semantic_warnings=semantic_warnings,
        retrieval=retrieval,
    )
    payload["status"] = grounded_answer.grounding_status
    payload["reason"] = grounded_answer.reason or payload["reason"]
    payload["citations"] = selected or payload["citations"]
    return payload


def grounding_to_notice(metadata: dict[str, Any]) -> dict[str, Any]:
    status = str(metadata.get("status") or "partial").strip().lower()
    title_map = {
        "grounded": "Grounded answer",
        "partial": "Partially grounded answer",
        "abstain": "Grounding limit reached",
        "conflict": "Conflicting evidence",
    }
    level_map = {
        "grounded": "info",
        "partial": "warning",
        "abstain": "warning",
        "conflict": "warning",
    }
    code_map = {
        "grounded": "grounding_grounded",
        "partial": "grounding_partial",
        "abstain": "grounding_abstain",
        "conflict": "grounding_conflict",
    }
    citations = metadata.get("citations") or []
    suffix = ""
    if citations:
        labels = [str(item.get("label") or item.get("title") or "").strip() for item in citations[:2] if isinstance(item, dict)]
        if labels:
            suffix = f" Sources: {', '.join(labels)}."
    return {
        "type": "notice",
        "code": code_map.get(status, "grounding_partial"),
        "level": level_map.get(status, "warning"),
        "title": title_map.get(status, "Grounding update"),
        "message": f"{metadata.get('reason') or 'Grounding metadata available.'}{suffix}".strip(),
    }


def dump_grounding_json(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, ensure_ascii=True)
