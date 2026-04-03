from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core.structured_logging import get_structured_logger
from app.services.ai_flow_intelligence_service import record_query_result
from app.services.grounding_service import build_evidence_pack, build_section_evidence_map
from app.storage import get_storage

logger = get_structured_logger(__name__)

_STOPWORDS = {
    "a", "an", "and", "or", "the", "to", "for", "from", "with", "without", "this", "that", "these", "those",
    "issue", "ticket", "topic", "task", "story", "feature", "bug", "guides", "guide", "user", "users",
    "page", "document", "article", "into", "onto", "over", "under", "what", "when", "where", "how",
    "require", "required", "requires", "should", "could", "would", "need", "needed", "needs",
    "resolve", "resolved", "resolves", "resolution", "get", "gets", "got", "using", "used",
    "does", "do", "did", "we", "our", "their", "its", "is", "are", "be", "in", "of", "on",
}
_CORRECTIVE_TRACE_PATH = "corrective_rag_traces.jsonl"
_CLAUDE_HINT_PATTERN = re.compile(r"\b(claude|bedrock|aws|anthropic|adobe ai|mcp|codex|openai)\b", re.IGNORECASE)
_REFERENCE_QUERY_PATTERN = re.compile(r"\b(href|keyref|conkeyref|conref|topicref|cross[- ]reference)\b", re.IGNORECASE)
_AUTHOR_VIEW_PATTERN = re.compile(r"\b(author view|map editor|source view|layout view|preview)\b", re.IGNORECASE)
_ADOBE_PRODUCT_PATTERN = re.compile(
    r"\b(aem|adobe|experience manager|experience league|aem guides|map editor|author view|output preset|assets ui)\b",
    re.IGNORECASE,
)
# DITA markup, topic types, and common author questions — widens Experience League fallback + query variants for chat.
_DITA_OR_STRUCTURE_QUERY_PATTERN = re.compile(
    r"\b("
    r"dita|ditamap|topicref|bookmap|map editor|root map|"
    r"reference topic|task topic|concept topic|glossentry|glossdef|glossref|"
    r"refbody|shortdesc|prolog|metadata|navtitle|"
    r"properties\b|prophead|proptype|propvalue|propdesc|property\b|"
    r"conref|conkeyref|keyref|keydef|keyscope|subject scheme|"
    r"topichead|reltable|simpletable|table\b|fig\b|image\b|xref\b"
    r")\b",
    re.IGNORECASE,
)
_CLAUSE_SPLIT_PATTERN = re.compile(
    r"\s*(?:\?\s*|,\s*(?=how\b|what\b|when\b|where\b|why\b|whether\b|if\b)|\band\s+(?=how\b|what\b|when\b|where\b|why\b|whether\b|if\b))",
    re.IGNORECASE,
)
_QUERY_ALIAS_CONFIG = "chat_query_aliases.json"


@dataclass
class RetrievalCandidate:
    source: str
    label: str
    text: str
    score: float = 0.0
    url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalAssessment:
    score: float
    strength: str
    reason: str
    term_coverage: float
    issue_coverage: float
    source_diversity: int
    duplicate_ratio: float
    off_topic_ratio: float
    evidence_count: int


@dataclass
class CorrectionPlan:
    corrected_query: str
    query_variants: list[str] = field(default_factory=list)
    reason: str = ""
    correction_applied: bool = False


@dataclass
class CorrectiveRagResult:
    query: str
    corrected_query: str
    correction_applied: bool
    assessment: RetrievalAssessment
    candidates: list[RetrievalCandidate] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    retrieval_summary: dict[str, Any] = field(default_factory=dict)

    def context_text(self, max_chars: int = 6000) -> str:
        if not self.candidates:
            return ""
        grouped: dict[str, list[str]] = {}
        for candidate in self.candidates:
            grouped.setdefault(candidate.label, []).append(candidate.text[:1000])
        blocks: list[str] = []
        for label, snippets in grouped.items():
            numbered = [f"[{index}] {snippet}" for index, snippet in enumerate(snippets, 1) if snippet]
            if numbered:
                blocks.append(f"{label}:\n" + "\n\n".join(numbered))
        content = "\n\n".join(blocks)
        return content[:max_chars] + ("\n\n[truncated]" if len(content) > max_chars else "")


def _trace_path() -> Path:
    path = get_storage().base_path / _CORRECTIVE_TRACE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config" / _QUERY_ALIAS_CONFIG


@lru_cache(maxsize=1)
def _load_query_alias_rules() -> list[dict[str, list[str]]]:
    path = _config_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    aliases = payload.get("aliases") if isinstance(payload, dict) else None
    if not isinstance(aliases, list):
        return []
    rules: list[dict[str, list[str]]] = []
    for item in aliases:
        if not isinstance(item, dict):
            continue
        match = [str(v).strip() for v in item.get("match", []) if str(v).strip()]
        variants = [str(v).strip() for v in item.get("variants", []) if str(v).strip()]
        if match and variants:
            rules.append({"match": match, "variants": variants})
    return rules


def _tokenize(text: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9._/-]{2,}", text or ""):
        lowered = token.lower()
        if lowered in _STOPWORDS or lowered in seen:
            continue
        seen.add(lowered)
        tokens.append(token)
    return tokens[:12]


def _expand_alias_variants(query: str) -> list[str]:
    base = (query or "").strip()
    if not base:
        return []
    variants: list[str] = []
    lowered = base.lower()
    for rule in _load_query_alias_rules():
        matches = rule.get("match") or []
        if not any(term.lower() in lowered for term in matches):
            continue
        for variant in rule.get("variants") or []:
            if variant.lower() in lowered:
                continue
            variants.append(f"{base} {variant}".strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        cleaned = re.sub(r"\s+", " ", variant).strip()
        if not cleaned:
            continue
        lowered_clean = cleaned.lower()
        if lowered_clean in seen:
            continue
        seen.add(lowered_clean)
        deduped.append(cleaned)
    return deduped[:6]


def _decompose_query_clauses(query: str) -> list[str]:
    text = re.sub(r"\s+", " ", (query or "").strip())
    if not text:
        return []
    parts = [segment.strip(" ,") for segment in _CLAUSE_SPLIT_PATTERN.split(text) if segment.strip(" ,")]
    if len(parts) <= 1:
        return [text]
    clauses: list[str] = []
    seen: set[str] = set()
    for part in parts:
        lowered = part.lower()
        if lowered in seen or len(part) < 8:
            continue
        seen.add(lowered)
        clauses.append(part)
    return clauses or [text]


def _version_tokens(text: str) -> list[str]:
    return re.findall(r"\b\d+(?:\.\d+){1,2}\b", text or "")[:5]


def _text_overlap_ratio(query: str, text: str) -> float:
    query_terms = _tokenize(query)
    if not query_terms:
        return 1.0
    lowered_text = (text or "").lower()
    covered = sum(1 for token in query_terms if token.lower() in lowered_text)
    return covered / max(1, len(query_terms))


def _dedupe_candidates(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    unique: list[RetrievalCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = re.sub(r"\s+", " ", (candidate.text or "").strip().lower())
        if not text:
            continue
        key = f"{candidate.label}:{text[:220]}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _grade_candidates(query: str, candidates: list[RetrievalCandidate], *, issue: dict | None = None) -> RetrievalAssessment:
    query_terms = _tokenize(query)
    issue_terms = _tokenize(" ".join(str(part) for part in [
        (issue or {}).get("summary", ""),
        (issue or {}).get("description", ""),
        " ".join((issue or {}).get("components") or []),
        " ".join((issue or {}).get("labels") or []),
    ]))
    versions = _version_tokens(query)

    if not candidates:
        return RetrievalAssessment(
            score=0.0,
            strength="weak",
            reason="No local evidence was retrieved for this query.",
            term_coverage=0.0,
            issue_coverage=0.0,
            source_diversity=0,
            duplicate_ratio=0.0,
            off_topic_ratio=1.0,
            evidence_count=0,
        )

    all_text = " \n ".join(candidate.text for candidate in candidates).lower()
    term_coverage = (
        sum(1 for token in query_terms if token.lower() in all_text) / max(1, len(query_terms))
        if query_terms else 1.0
    )
    issue_coverage = (
        sum(1 for token in issue_terms[:8] if token.lower() in all_text) / max(1, min(8, len(issue_terms)))
        if issue_terms else 1.0
    )
    version_coverage = (
        sum(1 for version in versions if version in all_text) / max(1, len(versions))
        if versions else 1.0
    )
    source_diversity = len({candidate.source for candidate in candidates})
    duplicate_ratio = max(0.0, 1 - (len(_dedupe_candidates(candidates)) / max(1, len(candidates))))
    off_topic_ratio = (
        sum(1 for candidate in candidates if _text_overlap_ratio(query, candidate.text) < 0.18) / max(1, len(candidates))
    )
    evidence_count = len(candidates)
    score = (
        (term_coverage * 0.34)
        + (issue_coverage * 0.16)
        + (version_coverage * 0.12)
        + (min(1.0, evidence_count / 4) * 0.16)
        + (min(1.0, source_diversity / 3) * 0.12)
        + ((1 - duplicate_ratio) * 0.05)
        + ((1 - off_topic_ratio) * 0.05)
    )
    if score >= 0.7:
        strength = "strong"
    elif score >= 0.45:
        strength = "medium"
    else:
        strength = "weak"

    reason_parts: list[str] = []
    if term_coverage < 0.45:
        reason_parts.append("low term coverage")
    if issue_coverage < 0.4:
        reason_parts.append("issue context is underrepresented")
    if source_diversity < 2 and evidence_count < 4:
        reason_parts.append("evidence is narrow")
    if duplicate_ratio > 0.35:
        reason_parts.append("results are repetitive")
    if off_topic_ratio > 0.45:
        reason_parts.append("too many off-topic snippets")
    reason = ", ".join(reason_parts) if reason_parts else "local retrieval looks strong"

    return RetrievalAssessment(
        score=round(score, 3),
        strength=strength,
        reason=reason,
        term_coverage=round(term_coverage, 3),
        issue_coverage=round(issue_coverage, 3),
        source_diversity=source_diversity,
        duplicate_ratio=round(duplicate_ratio, 3),
        off_topic_ratio=round(off_topic_ratio, 3),
        evidence_count=evidence_count,
    )


def _deterministic_query_variants(query: str, *, issue: dict | None = None, category: str = "", mode: str = "") -> list[str]:
    base = (query or "").strip()
    variants: list[str] = [base]
    issue = issue or {}

    lowered_base = base.lower()
    collapsed = re.sub(r"([a-z])([A-Z])", r"\1 \2", base)
    collapsed = re.sub(r"([A-Za-z]+)(instance)\b", r"\1 \2", collapsed, flags=re.IGNORECASE)
    collapsed = re.sub(r"\s+", " ", collapsed).strip()
    if collapsed and collapsed.lower() != lowered_base:
        variants.append(collapsed)

    stripped_terms = [token for token in _tokenize(base) if token.lower() not in {"aem", "dita"}]
    if stripped_terms:
        variants.append(" ".join(stripped_terms[:8]))

    issue_bits = [
        issue.get("summary", ""),
        " ".join(issue.get("components") or []),
        " ".join(issue.get("fix_versions") or []),
    ]
    issue_extension = " ".join(str(bit).strip() for bit in issue_bits if str(bit).strip())
    if issue_extension and issue_extension.lower() not in base.lower():
        variants.append(f"{base} {issue_extension}".strip())
    variants.extend(_expand_alias_variants(base))

    if _AUTHOR_VIEW_PATTERN.search(base):
        variants.append(f"{base} Map Editor Author view AEM Guides".strip())
        variants.append(f"{base} Source view Layout view Preview AEM Guides".strip())

    if _REFERENCE_QUERY_PATTERN.search(base):
        variants.append(f"{base} topicref href conref conkeyref keyref".strip())
        variants.append(f"{base} content reuse references root map resolution".strip())

    if _REFERENCE_QUERY_PATTERN.search(base) and _AUTHOR_VIEW_PATTERN.search(base):
        variants.append(
            "AEM Guides Map Editor Author view topicref href conref conkeyref keyref resolution"
        )
        variants.append(
            "AEM Guides content reusability topicref href conref conkeyref keyref Author view"
        )

    if mode in {"authoring", "chat"} and _DITA_OR_STRUCTURE_QUERY_PATTERN.search(base):
        variants.append(
            f"{base} DITA reference topic refbody properties prophead proptype propvalue propdesc".strip()
        )
        variants.append("DITA 1.3 reference properties table prophead property row columns")
        variants.append(f"{base} Adobe Experience Manager Guides documentation".strip())

    if "aem guides" not in base.lower() and category in {"aem_guides", "bugs_fixes"}:
        variants.append(f"{base} AEM Guides".strip())
    if "dita" not in base.lower() and (mode in {"authoring", "chat"} or category in {"dita_elements", "dita_spec"}):
        variants.append(f"{base} DITA".strip())
    if category == "expert_examples":
        variants.append(f"{base} example topic".strip())
    if category == "bugs_fixes":
        variants.append(f"{base} workaround fix".strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        cleaned = re.sub(r"\s+", " ", variant).strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(cleaned)
    return deduped[:12]


def _is_adobe_product_query(query: str, *, category: str = "", mode: str = "") -> bool:
    if category in {"aem_guides", "bugs_fixes"}:
        return True
    q = query or ""
    if mode == "chat" and _ADOBE_PRODUCT_PATTERN.search(q):
        return True
    if mode == "chat" and _DITA_OR_STRUCTURE_QUERY_PATTERN.search(q):
        return True
    return False


async def _llm_refined_query(
    query: str,
    *,
    reason: str,
    issue: dict | None = None,
    mode: str = "",
    category: str = "",
) -> str:
    try:
        from app.services.llm_service import generate_text, is_llm_available

        if not is_llm_available():
            return ""
        prompt = (
            "Rewrite this retrieval query to improve grounding without changing intent.\n"
            f"Mode: {mode or 'general'}\n"
            f"Category: {category or 'general'}\n"
            f"Weakness: {reason}\n"
            f"Issue summary: {(issue or {}).get('summary', '')}\n"
            f"Original query: {query}\n\n"
            "Return only the rewritten query."
        )
        rewritten = await generate_text(
            system_prompt="You improve search queries for technical RAG. Return plain text only.",
            user_prompt=prompt,
            max_tokens=120,
            step_name="corrective_rag_query_rewrite",
            jira_id=(issue or {}).get("issue_key"),
        )
        cleaned = re.sub(r"\s+", " ", (rewritten or "").strip())
        return cleaned if cleaned and len(cleaned) >= 6 else ""
    except Exception:
        return ""


def _persist_trace(payload: dict[str, Any]) -> None:
    try:
        with _trace_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception as exc:
        logger.debug_structured("Failed to persist corrective RAG trace", extra_fields={"error": str(exc)})


def _candidate_from_doc(doc: dict[str, Any]) -> RetrievalCandidate | None:
    snippet = str(doc.get("snippet") or doc.get("content") or "").strip()
    if not snippet:
        return None
    return RetrievalCandidate(
        source="aem_guides",
        label="Experience League",
        text=snippet,
        url=str(doc.get("url") or ""),
        metadata={
            "title": doc.get("title") or "",
            "url": doc.get("url") or "",
            "doc_type": "product_doc",
            "section": doc.get("title") or "",
        },
    )


def _candidate_from_dita(chunk: dict[str, Any]) -> RetrievalCandidate | None:
    text = str(chunk.get("text_content") or "").strip()
    if not text:
        return None
    source_url = str(chunk.get("source_url") or "")
    page = ""
    page_match = re.search(r"[#?&]page=(\d+)", source_url)
    if page_match:
        page = page_match.group(1)
    return RetrievalCandidate(
        source="dita_spec",
        label="DITA Spec",
        text=text,
        url=source_url,
        metadata={
            "element_name": chunk.get("element_name") or "",
            "source_url": source_url,
            "page": page,
            "doc_type": chunk.get("content_type") or "spec",
            "section": chunk.get("element_name") or "",
            "title": chunk.get("element_name") or "DITA Spec",
        },
    )


def _candidate_from_tenant(chunk: dict[str, Any]) -> RetrievalCandidate | None:
    text = str(chunk.get("content") or "").strip()
    if not text:
        return None
    metadata = chunk.get("metadata") or {}
    return RetrievalCandidate(
        source="tenant_context",
        label="Tenant Knowledge",
        text=text,
        metadata={
            "label": metadata.get("label") or metadata.get("filename") or "Tenant knowledge",
            "title": metadata.get("label") or metadata.get("filename") or "Tenant knowledge",
            "filename": metadata.get("filename") or "",
            "doc_type": metadata.get("doc_type") or "product_doc",
            "section": metadata.get("section") or metadata.get("label") or "",
            "page": metadata.get("page") or "",
            "credibility": metadata.get("credibility") or "",
            "raw": chunk,
        },
    )


def _candidate_from_example(example: dict[str, Any]) -> RetrievalCandidate | None:
    text = str(example.get("content") or "").strip()
    if not text:
        return None
    return RetrievalCandidate(
        source="tenant_examples",
        label="Approved Examples",
        text=text,
        metadata={
            "filename": example.get("filename") or "example.dita",
            "title": example.get("filename") or "example.dita",
            "doc_type": "approved_topic",
            "section": example.get("filename") or "",
            "credibility": example.get("quality_score") or "",
            "raw": example,
        },
    )


def _candidate_from_claude(text: str) -> RetrievalCandidate | None:
    cleaned = str(text or "").strip()
    if not cleaned:
        return None
    return RetrievalCandidate(
        source="claude_setup",
        label="Claude / Adobe Setup",
        text=cleaned,
        metadata={"title": "Claude / Adobe Setup", "doc_type": "other"},
    )


def _retrieve_mode_candidates(query: str, *, tenant_id: str, mode: str, category: str = "") -> list[RetrievalCandidate]:
    from app.services.claude_code_retriever import retrieve_claude_code_context
    from app.services.dita_knowledge_retriever import retrieve_dita_graph_knowledge, retrieve_dita_knowledge
    from app.services.doc_retriever_service import retrieve_relevant_docs
    from app.services.tenant_service import retrieve_tenant_context, retrieve_tenant_examples

    candidates: list[RetrievalCandidate] = []

    include_docs = mode in {"authoring", "chat"} or category in {"aem_guides", "bugs_fixes", "dita_elements"}
    include_dita = mode in {"authoring", "chat"} or category in {"dita_elements", "dita_spec", "expert_examples"}
    include_tenant = mode in {"authoring", "chat"} or category == "client_docs"
    include_examples = mode in {"authoring", "chat"} or category == "expert_examples"

    if include_docs:
        for doc in retrieve_relevant_docs(query=query, k=6) or []:
            candidate = _candidate_from_doc(doc)
            if candidate:
                candidates.append(candidate)

    if include_dita:
        for chunk in retrieve_dita_knowledge(query_text=query, k=6) or []:
            candidate = _candidate_from_dita(chunk)
            if candidate:
                candidates.append(candidate)
        graph_summary = retrieve_dita_graph_knowledge(element_hint=query)
        if graph_summary:
            candidates.append(
                RetrievalCandidate(
                    source="dita_graph",
                    label="DITA Structure",
                    text=graph_summary,
                    metadata={"title": "DITA Structure", "doc_type": "spec", "section": "Structure rules"},
                )
            )

    if include_tenant:
        for chunk in retrieve_tenant_context(query=query, tenant_id=tenant_id, k=4) or []:
            candidate = _candidate_from_tenant(chunk)
            if candidate:
                candidates.append(candidate)

    if include_examples:
        for example in retrieve_tenant_examples(query=query, tenant_id=tenant_id, k=3) or []:
            candidate = _candidate_from_example(example)
            if candidate:
                candidates.append(candidate)

    if mode == "chat" and _CLAUDE_HINT_PATTERN.search(query or ""):
        candidate = _candidate_from_claude(retrieve_claude_code_context(query[:500]))
        if candidate:
            candidates.append(candidate)

    return _dedupe_candidates(candidates)


async def _retrieve_tavily_candidates(query: str, category: str) -> list[RetrievalCandidate]:
    from app.services.tavily_search_service import tavily_search_sync

    try:
        payload = await asyncio.to_thread(
            lambda: tavily_search_sync(query, category=category, max_results=4),
        )
        if not payload:
            return []

        candidates: list[RetrievalCandidate] = []
        answer = str(payload.get("answer") or "").strip()
        if answer:
            candidates.append(
                RetrievalCandidate(
                    source="tavily",
                    label="Web Answer",
                    text=answer,
                    metadata={"title": "Web Answer", "doc_type": "web_result"},
                )
            )
        for item in payload.get("results", []) or []:
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            candidates.append(
                RetrievalCandidate(
                    source="tavily",
                    label="Web Result",
                    text=content,
                    url=str(item.get("url") or ""),
                    metadata={
                        "title": item.get("title") or item.get("url") or "Web Result",
                        "url": item.get("url") or "",
                        "doc_type": "web_result",
                    },
                )
            )
        return _dedupe_candidates(candidates)
    except Exception as exc:
        logger.debug_structured(
            "Corrective Tavily retrieval failed",
            extra_fields={"error": str(exc), "category": category},
        )
        return []


async def _retrieve_experience_league_candidates(query: str) -> list[RetrievalCandidate]:
    from app.services.tavily_search_service import tavily_search_sync

    payload = await asyncio.to_thread(
        lambda: tavily_search_sync(query, category="aem_guides", max_results=4),
    )
    if not payload:
        return []

    candidates: list[RetrievalCandidate] = []
    for item in payload.get("results", []) or []:
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or "").strip()
        if not url or not content:
            continue
        hostname = (urlparse(url).hostname or "").lower()
        if hostname != "experienceleague.adobe.com":
            continue
        candidates.append(
            RetrievalCandidate(
                source="aem_guides",
                label="Experience League",
                text=content,
                url=url,
                metadata={
                    "title": item.get("title") or "Experience League",
                    "url": url,
                    "doc_type": "product_doc",
                    "live_source": True,
                },
            )
        )
    return _dedupe_candidates(candidates)


def _build_summary(
    *,
    original_query: str,
    result_query: str,
    correction_applied: bool,
    assessment: RetrievalAssessment,
    candidates: list[RetrievalCandidate],
    mode: str,
    category: str,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "category": category,
        "query": original_query,
        "corrected_query": result_query if correction_applied else "",
        "correction_applied": correction_applied,
        "strength": assessment.strength,
        "reason": assessment.reason,
        "sources_used": list(dict.fromkeys(candidate.label for candidate in candidates)),
        "evidence_count": len(candidates),
    }


def _is_better_assessment(
    candidate_assessment: RetrievalAssessment,
    current_assessment: RetrievalAssessment,
    *,
    candidate_count: int,
    current_count: int,
) -> bool:
    if candidate_assessment.score > current_assessment.score:
        return True
    strength_rank = {"weak": 0, "medium": 1, "strong": 2}
    candidate_strength = strength_rank.get(candidate_assessment.strength, 0)
    current_strength = strength_rank.get(current_assessment.strength, 0)
    if candidate_strength > current_strength:
        return True
    if candidate_assessment.score == current_assessment.score and candidate_count > current_count:
        return True
    return False


async def _run_corrective_rag(
    query: str,
    *,
    tenant_id: str,
    mode: str,
    issue: dict | None = None,
    category: str = "",
    allow_web_fallback: bool = False,
) -> CorrectiveRagResult:
    original_query = (query or "").strip()

    async def _best_for_seed(seed_query: str) -> tuple[str, list[RetrievalCandidate], RetrievalAssessment]:
        best_seed_query = seed_query
        best_seed_candidates = _retrieve_mode_candidates(seed_query, tenant_id=tenant_id, mode=mode, category=category)
        best_seed_assessment = _grade_candidates(seed_query, best_seed_candidates, issue=issue)
        seed_variants = _deterministic_query_variants(seed_query, issue=issue, category=category, mode=mode)
        if best_seed_assessment.strength == "weak":
            llm_variant = await _llm_refined_query(
                seed_query,
                reason=best_seed_assessment.reason,
                issue=issue,
                mode=mode,
                category=category,
            )
            if llm_variant and llm_variant.lower() not in {variant.lower() for variant in seed_variants}:
                seed_variants.append(llm_variant)
        for variant in seed_variants[1:]:
            candidate_set = _retrieve_mode_candidates(variant, tenant_id=tenant_id, mode=mode, category=category)
            assessment = _grade_candidates(variant, candidate_set, issue=issue)
            if _is_better_assessment(
                assessment,
                best_seed_assessment,
                candidate_count=len(candidate_set),
                current_count=len(best_seed_candidates),
            ):
                best_seed_query = variant
                best_seed_candidates = candidate_set
                best_seed_assessment = assessment
        return best_seed_query, best_seed_candidates, best_seed_assessment

    clauses = _decompose_query_clauses(original_query)
    clause_results: list[tuple[str, list[RetrievalCandidate], RetrievalAssessment]] = []
    for clause in clauses:
        clause_results.append(await _best_for_seed(clause))

    # Always try the full original query so multi-clause questions don't lose terms
    if len(clauses) > 1:
        clause_results.append(await _best_for_seed(original_query))

    best_query, best_candidates, best_assessment = clause_results[0] if clause_results else (original_query, [], _grade_candidates(original_query, []))
    for clause_query, clause_candidates, clause_assessment in clause_results[1:]:
        if _is_better_assessment(
            clause_assessment,
            best_assessment,
            candidate_count=len(clause_candidates),
            current_count=len(best_candidates),
        ):
            best_query = clause_query
            best_candidates = clause_candidates
            best_assessment = clause_assessment

    if len(clause_results) > 1:
        merged_candidates = _dedupe_candidates(
            [candidate for _, clause_candidates, _ in clause_results for candidate in clause_candidates]
        )
        merged_assessment = _grade_candidates(original_query, merged_candidates, issue=issue)
        if _is_better_assessment(
            merged_assessment,
            best_assessment,
            candidate_count=len(merged_candidates),
            current_count=len(best_candidates),
        ):
            best_query = "; ".join(query_text for query_text, _, _ in clause_results if query_text)
            best_candidates = merged_candidates
            best_assessment = merged_assessment

    from app.services.tavily_search_service import is_chat_tavily_enabled
    use_web_fallback = (mode == "research" and allow_web_fallback) or (mode == "chat" and is_chat_tavily_enabled())
    # Same kill-switch as general web Tavily: CHAT_TAVILY_ENABLED=false disables all chat Tavily (including EL-only search).
    use_adobe_live_fallback = (
        mode == "chat"
        and is_chat_tavily_enabled()
        and _is_adobe_product_query(original_query, category=category, mode=mode)
    )
    if use_web_fallback and best_assessment.strength == "weak":
        web_candidates = await _retrieve_tavily_candidates(best_query, category or "general")
        combined = _dedupe_candidates(best_candidates + web_candidates)
        assessment = _grade_candidates(original_query, combined, issue=issue)
        if assessment.score >= best_assessment.score or web_candidates:
            best_candidates = combined
            best_assessment = assessment
    if use_adobe_live_fallback and best_assessment.strength == "weak":
        live_candidates = await _retrieve_experience_league_candidates(best_query)
        combined = _dedupe_candidates(best_candidates + live_candidates)
        assessment = _grade_candidates(original_query, combined, issue=issue)
        if assessment.score >= best_assessment.score or live_candidates:
            best_candidates = combined
            best_assessment = assessment

    correction_applied = best_query.strip().lower() != original_query.strip().lower()
    summary = _build_summary(
        original_query=original_query,
        result_query=best_query,
        correction_applied=correction_applied,
        assessment=best_assessment,
        candidates=best_candidates,
        mode=mode,
        category=category,
    )
    _persist_trace(summary)
    record_query_result(
        tenant_id,
        category or mode,
        "rag",
        success=best_assessment.strength != "weak" and bool(best_candidates),
        error="" if best_assessment.strength != "weak" else best_assessment.reason,
        result_count=len(best_candidates),
    )
    return CorrectiveRagResult(
        query=original_query,
        corrected_query=best_query if correction_applied else "",
        correction_applied=correction_applied,
        assessment=best_assessment,
        candidates=best_candidates[:8],
        sources_used=summary["sources_used"],
        retrieval_summary=summary,
    )


async def run_authoring_corrective_rag(query: str, *, tenant_id: str, issue: dict | None = None) -> dict[str, Any]:
    result = await _run_corrective_rag(query, tenant_id=tenant_id, mode="authoring", issue=issue)
    evidence_pack = build_evidence_pack(
        query=query,
        tenant_id=tenant_id,
        candidates=result.candidates,
        issue_key=str((issue or {}).get("issue_key") or ""),
    )
    docs = [candidate for candidate in result.candidates if candidate.source == "aem_guides"]
    dita_chunks = [candidate for candidate in result.candidates if candidate.source in {"dita_spec", "dita_graph"}]
    tenant_chunks = [candidate for candidate in result.candidates if candidate.source == "tenant_context"]
    examples = [candidate for candidate in result.candidates if candidate.source == "tenant_examples"]
    retrieval_summary = dict(result.retrieval_summary or {})
    retrieval_summary.update(
        {
            "grounding_status": evidence_pack.decision.status,
            "grounding_confidence": evidence_pack.decision.confidence,
            "grounding_reason": evidence_pack.decision.reason,
        }
    )
    return {
        "query": result.query,
        "corrected_query": result.corrected_query,
        "correction_applied": result.correction_applied,
        "retrieval_summary": retrieval_summary,
        "sources_used": result.sources_used,
        "aem_context": "\n\n".join(candidate.text[:800] for candidate in docs[:5]),
        "dita_context": "\n---\n".join(candidate.text[:650] for candidate in dita_chunks[:5]),
        "tenant_context_text": "\n---\n".join(
            f"[{candidate.metadata.get('label') or 'Tenant knowledge'}] {candidate.text[:500]}"
            for candidate in tenant_chunks[:4]
        ),
        "similar_topics": [candidate.metadata.get("raw") or {} for candidate in examples[:3] if candidate.metadata.get("raw")],
        "evidence_pack": evidence_pack.to_dict(),
        "evidence_prompt_context": evidence_pack.build_prompt_context(max_chars=4200, limit=6),
        "section_evidence_map": build_section_evidence_map(evidence_pack),
    }


async def run_chat_corrective_rag(query: str, *, tenant_id: str) -> CorrectiveRagResult:
    return await _run_corrective_rag(query, tenant_id=tenant_id, mode="chat")


async def run_research_corrective_rag(
    query: str,
    *,
    tenant_id: str,
    category: str,
    requested_source: str,
    issue: dict | None = None,
) -> CorrectiveRagResult:
    allow_web_fallback = requested_source == "tavily"
    return await _run_corrective_rag(
        query,
        tenant_id=tenant_id,
        mode="research",
        issue=issue,
        category=category,
        allow_web_fallback=allow_web_fallback,
    )
