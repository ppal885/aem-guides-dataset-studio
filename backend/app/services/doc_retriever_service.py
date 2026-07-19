"""Retrieve relevant documentation chunks for RAG augmentation.

This module is used most often for AEM Guides product guidance. The bundled
corpus can also contain non-Experience League content, so callers can
optionally constrain retrieval by host and benefit from a product-doc-aware
reranker instead of relying on raw snippet similarity alone.
"""
import json
import os
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from app.storage import get_storage
from app.services.embedding_service import embed_query, get_embedding_diagnostics, is_embedding_available
from app.services.vector_store_service import (
    is_chroma_available,
    query_collection,
    get_collection_count,
    CHROMA_COLLECTION_AEM_GUIDES,
    CHROMA_COLLECTION_DITA_SPEC,
    CHROMA_COLLECTION_JIRA_QA,
)
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

DOC_CHUNKS_FILENAME = "aem_guides_doc_chunks.json"
BEHAVIOR_DOC_CHUNKS_FILENAME = "aem_guides_behavior_chunks.json"
ENRICHED_BEHAVIOR_DOC_CHUNKS_FILENAME = "aem_guides_enriched_behavior_chunks.json"
DITA_OT_ISSUE_DOC_CHUNKS_FILENAME = "dita_ot_issue_behavior_chunks.json"
MANUAL_DOC_CHUNKS_FILENAME = "manual_aem_guides_doc_chunks.json"
MAX_SNIPPET_CHARS = 1500


def _get_doc_chunks_path() -> Path:
    storage = get_storage()
    return storage.base_path / DOC_CHUNKS_FILENAME


def _get_manual_doc_chunks_path() -> Path:
    storage = get_storage()
    return storage.base_path / MANUAL_DOC_CHUNKS_FILENAME


def _get_behavior_doc_chunks_path() -> Path:
    storage = get_storage()
    return storage.base_path / BEHAVIOR_DOC_CHUNKS_FILENAME


def _get_enriched_behavior_doc_chunks_path() -> Path:
    storage = get_storage()
    return storage.base_path / ENRICHED_BEHAVIOR_DOC_CHUNKS_FILENAME


def _get_dita_ot_issue_doc_chunks_path() -> Path:
    storage = get_storage()
    return storage.base_path / DITA_OT_ISSUE_DOC_CHUNKS_FILENAME


def _load_chunk_file(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning_structured("Failed to load doc chunks", extra_fields={"path": str(path), "error": str(e)})
        return []


def _load_chunks() -> list[dict]:
    """Load doc chunks from JSON, including manual fallback chunks."""
    primary = _load_chunk_file(_get_doc_chunks_path())
    enriched_behavior = _load_chunk_file(_get_enriched_behavior_doc_chunks_path())
    behavior = _load_chunk_file(_get_behavior_doc_chunks_path())
    dita_ot_issues = _load_chunk_file(_get_dita_ot_issue_doc_chunks_path())
    manual = _load_chunk_file(_get_manual_doc_chunks_path())
    return [*manual, *dita_ot_issues, *enriched_behavior, *behavior, *primary]


def check_rag_readiness() -> dict:
    """
    Verify at least one RAG source (AEM Guides or DITA spec) has content.
    Returns dict with aem_guides_ready, enterprise_qa_ready, dita_spec_ready,
    jira_qa_ready, any_ready, message.
    """
    aem_guides_ready = False
    dita_spec_ready = False
    jira_qa_ready = False

    if is_chroma_available():
        aem_count = get_collection_count(CHROMA_COLLECTION_AEM_GUIDES)
        dita_count = get_collection_count(CHROMA_COLLECTION_DITA_SPEC)
        jira_count = get_collection_count(CHROMA_COLLECTION_JIRA_QA)
        aem_guides_ready = aem_count > 0
        dita_spec_ready = dita_count > 0
        jira_qa_ready = jira_count > 0

    if not aem_guides_ready:
        chunks = _load_chunks()
        aem_guides_ready = len(chunks) > 0

    enterprise_qa_ready = aem_guides_ready
    any_ready = enterprise_qa_ready or dita_spec_ready

    if any_ready and not jira_qa_ready:
        message = (
            "RAG sources ready. Run POST /api/v1/ai/index-jira-rag to enable jira-rag augmentation."
        )
    elif any_ready:
        message = "RAG sources ready"
    else:
        message = (
            "No RAG sources populated. Run POST /api/v1/ai/crawl-aem-guides to index Experience League docs, "
            "and POST /api/v1/ai/index-dita-pdf to index DITA spec. Then retry plan or generate."
        )
    return {
        "aem_guides_ready": aem_guides_ready,
        "enterprise_qa_ready": enterprise_qa_ready,
        "dita_spec_ready": dita_spec_ready,
        "jira_qa_ready": jira_qa_ready,
        "any_ready": any_ready,
        "message": message,
    }


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    text = re.sub(r"[^\w\s-]", " ", str(text).lower())
    return {t for t in text.split() if len(t) >= 2}


def _lexical_score(query_tokens: set[str], content: str) -> float:
    content_tokens = _tokenize(content)
    if not query_tokens:
        return 0.0
    matches = sum(1 for t in query_tokens if t in content_tokens)
    return matches / len(query_tokens) if query_tokens else 0.0


def _infer_evidence_type(value: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    text = str(value or "").lstrip().lower()
    if text.startswith("qa oracle for"):
        return "generation_oracle"
    if text.startswith("feature area:") and "use this as grounded behavior context" in text:
        return "learned_behavior_profile"
    return ""


def _matches_allowed_hosts(url: str, allowed_host_suffixes: tuple[str, ...] | None) -> bool:
    if not allowed_host_suffixes:
        return True
    hostname = (urlparse(str(url or "")).hostname or "").lower()
    if not hostname:
        return False
    return any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in allowed_host_suffixes)


def _phrase_candidates(query: str) -> list[str]:
    compact = re.sub(r"\s+", " ", str(query or "").strip().lower())
    if not compact:
        return []
    phrases: list[str] = []
    for phrase in re.split(r"[?.,;:()]+", compact):
        cleaned = " ".join(token for token in phrase.split() if len(token) >= 3)
        if len(cleaned.split()) >= 2 and cleaned not in phrases:
            phrases.append(cleaned)
    if "translation workflow" in compact and "translation workflow" not in phrases:
        phrases.insert(0, "translation workflow")
    if "baseline" in compact and "baseline" not in phrases:
        phrases.insert(0, "baseline")
    if "baseline" in compact and re.search(r"\b(type|types|kind|kinds|configuration|configurations)\b", compact):
        phrases.insert(0, "baseline types")
    if "create" in compact and "topic" in compact and "create topic" not in phrases:
        phrases.insert(0, "create topic")
    if "create" in compact and "map" in compact and "create map" not in phrases:
        phrases.insert(0, "create map")
    return phrases[:4]


def _classify_aem_query_intent(query: str) -> str:
    lowered = str(query or "").lower()
    if re.search(
        r"\b(configmgr|osgi|web console|configmanager|enable\.baseline\.v2)\b",
        lowered,
    ):
        return "configuration"
    if re.search(r"\bbaselines?\b", lowered):
        return "baseline"
    if re.search(r"\bmap collections?\b", lowered):
        return "publishing"
    # DITA-OT parameter/argument questions — prioritise dita-ot.org docs
    if re.search(r"\b(dita.?ot|dita open toolkit)\b", lowered) and re.search(
        r"\b(arg[a-z]*|param(?:eter)?s?|flag[s]?|option[s]?|command.?line|draft.comment|args?\.\w+|"
        r"transtype|input|format|output|filter|propertyfile|resource|subcommand)\b"
        r"|--\w+",  # CLI flags like --input, --format, --output
        lowered,
    ):
        return "dita_ot_params"
    if re.search(r"\b(create|new|author|edit|open|work with)\b", lowered) and re.search(
        r"\b(topic|map|editor|repository|explorer)\b",
        lowered,
    ):
        return "authoring_create"
    if re.search(r"\b(configure|configuration|settings?|profile|filter|indexing|search|workspace|mapping)\b", lowered):
        return "configuration"
    if re.search(r"\b(publish|publishing|output|preset|aem sites|pdf|replication|generate output)\b", lowered):
        return "publishing"
    if re.search(r"\b(translation|review|workflow|project|job)\b", lowered):
        return "workflow"
    return "general"


def _aem_intent_bonus(query: str, *, title: str, url: str, content: str) -> float:
    lowered_title = str(title or "").lower()
    lowered_url = str(url or "").lower()
    lowered_content = str(content or "").lower()
    intent = _classify_aem_query_intent(query)
    bonus = 0.0
    lowered_query = str(query or "").lower()

    if "dita-ot.org" in lowered_url:
        preprocess_targets = [
            (
                "/reference/preprocess-copy-to",
                r"\b(copy-to|copy to|copy-to processing|duplicate output|alternate output filename|copy-to target)\b",
            ),
            (
                "/reference/preprocess-conrefpush",
                r"\b(conrefpush|conref push|push content|pushed content|pushreplace|pushbefore|pushafter)\b",
            ),
            (
                "/reference/preprocess-conref",
                r"\b(conref\b|normal conrefs?|content reference|content references|resolve conrefs?|conref resolution)\b",
            ),
            (
                "/reference/preprocess-profile",
                r"\b(profile|profiling|ditaval|conditional processing|filter content|filters content|print rules?|exclude content)\b",
            ),
        ]
        suppress_dita_ot_profile_boost = bool(
            re.search(r"\b(aem guides|folder profile|conditional attribute|condition presets?)\b", lowered_query)
        )
        for url_fragment, pattern in preprocess_targets:
            if suppress_dita_ot_profile_boost and url_fragment == "/reference/preprocess-profile":
                continue
            if url_fragment in lowered_url and re.search(pattern, lowered_query):
                bonus += 4.40
                break
        if "/parameters/" in lowered_url and re.search(r"\b(parameters?|command arguments?|dita command|--input|--format|--output|--filter|--args)\b", lowered_query):
            bonus += 1.60

    if "generate-output-conditional-attribute-profiling" in lowered_url and re.search(
        r"\b(condition(?:al)?\s+attributes?|conditional\s+attribute\s+profiling|folder\s+profile|name\s+value\s+label)\b",
        lowered_query,
    ):
        bonus += 2.40
    if "generate-output-conditional-attribute-profiling" in lowered_url and re.search(
        r"\b(output\s+presets?|global|add to folder profile|default pdf|view log|related maps)\b",
        lowered_query,
    ):
        bonus -= 2.10
    if "web-editor-manage-output-presets" in lowered_url and re.search(
        r"\b(global|folder profile|add to folder profile|default pdf|view log|related maps|folder-level administrative)\b",
        lowered_query,
    ):
        bonus += 3.0
    if "generate-output-use-map-collection-output-generation" in lowered_url and re.search(
        r"\b(map collections?|generate selected|generate all|modified|remove from collection|configure metadata|asset metadata|enable all|enable folder profile presets)\b",
        lowered_query,
    ):
        bonus += 3.2
    if "generate-output-use-new-map-collection-output-generation" in lowered_url and re.search(
        r"\b(new map collections?|beta|generated history|published history|fetch presets|select available translations|publish to|preview|publish instance|modified since generation|modified since published)\b",
        lowered_query,
    ):
        bonus += 3.4
    if "generate-output-use-map-collection-output-generation" in lowered_url and re.search(
        r"\b(new map collections?|beta|generated history|published history|fetch presets|select available translations|publish to|preview|publish instance)\b",
        lowered_query,
    ):
        bonus -= 1.2
    if "/install-conf-guide/output-gen-config/" in lowered_url and re.search(
        r"\b(map collections?|generate selected|generate all|remove from collection|configure metadata)\b",
        lowered_query,
    ):
        bonus -= 1.6
    if "generate-output-use-condition-presets" in lowered_url and re.search(
        r"\b(condition(?:al)?\s+presets?|include|exclude|passthrough|flag)\b",
        lowered_query,
    ):
        bonus += 1.20

    if intent == "dita_ot_params":
        # Boost dita-ot.org parameter/argument documentation pages
        if "dita-ot.org" in lowered_url:
            bonus += 0.60
        if re.search(r"/parameters/parameters-base|/parameters/dita-command", lowered_url):
            bonus += 0.45
        if re.search(r"\bargs?\.\w+|--args\.|draft.comment\b", lowered_content):
            bonus += 0.35
        if "experienceleague.adobe.com" in lowered_url and "dita-ot" not in lowered_url:
            bonus -= 0.50  # de-prioritise AEM docs for pure DITA-OT param questions
        return bonus

    if intent == "authoring_create":
        if "/author-content/" in lowered_url:
            bonus += 0.45
        if "/work-with-editor/" in lowered_url or "/map-editor/" in lowered_url:
            bonus += 0.25
        if re.search(r"\bcreate topics?\b", lowered_title) or "web-editor-create-topics" in lowered_url:
            bonus += 0.48
        if re.search(r"\bcreate (a )?map\b", lowered_title) or "map-editor-create-map" in lowered_url:
            bonus += 0.48
        if "repository panel" in lowered_content or "explorer view" in lowered_content:
            bonus += 0.18
        if "web editor" in lowered_content or "map console" in lowered_content:
            bonus += 0.15
        if re.search(r"\b(perform the following steps|new topic dialog|new map dialog|create > dita topic|create > dita map|new file icon)\b", lowered_content):
            bonus += 0.32
        if re.search(r"\b(select create > dita map|select create > dita topic|select new and choose topic)\b", lowered_content):
            bonus += 0.45
        if "select create > dita map" in lowered_content:
            bonus += 0.85
        if re.search(r"\brepository panel\b", lowered_content) and re.search(r"\bnew file icon\b", lowered_content) and "topic" in lowered_content:
            bonus += 0.85
        if re.search(r"\bassets ui\b", lowered_content) and "create > dita topic" in lowered_content:
            bonus += 0.78
        if re.search(
            r"\b(repository panel.*new file icon.*topic|assets ui.*create > dita topic|blueprint page.*map templates?|new map dialog.*map template)\b",
            lowered_content,
        ):
            bonus += 0.38
        if "/map-management-publishing/" in lowered_url or "/output-gen/" in lowered_url:
            bonus -= 0.65
        if "/knowledge-base/" in lowered_url:
            bonus -= 0.18
        if re.search(r"\b(know the editor features|download files|preview topics?|ditaval editor|citations?)\b", lowered_title):
            bonus -= 0.7
        if "template" in lowered_title and "template" not in str(query or "").lower():
            bonus -= 0.55
        if re.search(r"\b(last update:|created for:|documentationaem guides|topics:\s+[a-z])\b", lowered_content):
            bonus -= 0.55
        if re.search(r"</?[a-z][a-z0-9:_-]*|<map\b|<topicref\b", content, re.IGNORECASE):
            bonus -= 0.85
        if re.search(r"\b(generate article-based output|publish|output preset|incremental output)\b", lowered_content):
            bonus -= 0.45
        if re.search(r"\b(options menu|download as pdf|view in assets ui|preview)\b", lowered_content) and not re.search(
            r"\b(create > dita topic|create > dita map|new > dita map|new > topic|new topic dialog|new map dialog|repository panel)\b",
            lowered_content,
        ):
            bonus -= 0.35
        if re.search(r"\b(properties page|schedule \(de\)activation|document state|metadata|context menu)\b", lowered_content):
            bonus -= 0.65
        if re.search(r"\b(create dita template|topic template|map template)\b", lowered_content) and "template" not in str(query or "").lower():
            bonus -= 0.7
        if re.search(r"\b(topic|map) is created at the specified path\b", lowered_content) and not re.search(
            r"\b(create > dita topic|create > dita map|new file icon|repository panel|assets ui|new topic dialog|new map dialog)\b",
            lowered_content,
        ):
            bonus -= 0.35
        if re.search(r"\bopened in the (editor|map editor)\b", lowered_content) and not re.search(
            r"\b(create > dita topic|create > dita map|new file icon|repository panel|assets ui)\b",
            lowered_content,
        ):
            bonus -= 0.22
        if re.search(r"\bselect create\.\b", lowered_content) and "dita" not in lowered_content:
            bonus -= 0.22

    elif intent == "configuration":
        if "/install-conf-guide/" in lowered_url:
            bonus += 0.45
        if "conf-new-baseline-on-prem" in lowered_url and re.search(
            r"\b(new baseline|on-premise|on-prem|enable faster baseline|baseline v2|configmanager|configmgr|web console|enable\.baseline\.v2|osgi)\b",
            lowered_query,
        ):
            bonus += 2.2
        if re.search(r"\b(configure|settings?|profile|filter|mapping|indexing|search|workspace)\b", lowered_title):
            bonus += 0.28
        if "/output-gen/" in lowered_url and "output" not in str(query or "").lower():
            bonus -= 0.22

    elif intent == "publishing":
        if "generate-output-create-edit-preset" in lowered_url and re.search(
            r"\b(output\s+)?presets?\b", lowered_query
        ) and re.search(r"\b(edit|duplicate|delete|remove|manage|options?|dropdown|top\s+bar|settings?)\b", lowered_query):
            bonus += 1.25
        if "/map-management-publishing/" in lowered_url or "/output-gen/" in lowered_url:
            bonus += 0.45
        if re.search(r"\b(output|publish|preset|aem sites|pdf)\b", lowered_title):
            bonus += 0.25

    elif intent == "workflow":
        if re.search(r"\b(workflow|job|project|review|translation)\b", lowered_title + " " + lowered_content):
            bonus += 0.28

    elif intent == "baseline":
        if "/work-with-baseline/" in lowered_url or "baseline" in lowered_title:
            bonus += 0.75
        if "web-editor-baseline" in lowered_url or "generate-output-use-baseline-for-publishing" in lowered_url:
            bonus += 0.35
        if "generate-output-use-baseline-for-publishing" in lowered_url and re.search(
            r"\b(map dashboard|assets ui|baselines page|browse topic|browse all topics|add labels|translated baseline|overwrite existing baseline)\b",
            lowered_query + " " + lowered_title + " " + lowered_content,
        ):
            bonus += 0.75
        if "#create-a-baseline" in lowered_url and re.search(
            r"\b(create a baseline|baseline name|set the version based on|version on|assets ui|save)\b",
            lowered_query,
        ):
            bonus += 0.85
        if (
            lowered_url.endswith("generate-output-use-baseline-for-publishing")
            and re.search(r"\b(create a baseline|baseline name|set the version based on)\b", lowered_query)
        ):
            bonus -= 0.35
        if lowered_url.endswith("generate-output-use-baseline-for-publishing") and re.search(
            r"\b(browse all topics|add labels|translated baseline|overwrite existing baseline|export translated baseline)\b",
            lowered_query,
        ):
            bonus += 0.75
        if "#create-a-baseline" in lowered_url and re.search(
            r"\b(browse all topics|add labels|translated baseline|overwrite existing baseline|export translated baseline)\b",
            lowered_query,
        ):
            bonus -= 0.55
        if lowered_url.endswith("web-editor-baseline") and re.search(
            r"\b(map dashboard|assets ui|baselines page|browse topic|browse all topics|add labels|translated baseline|overwrite existing baseline)\b",
            lowered_query,
        ):
            bonus -= 0.45
        if "web-editor-baseline-v2" in lowered_url and re.search(
            r"\b(new baseline|beta|2026\.04\.0|bulk processor|migration|migrate|rebuild|download|guid|dependency preview|graph-based|rest api|java sdk)\b",
            lowered_query,
        ):
            bonus += 1.1
        if "#key-enhancements-introduced-in-the-new-baseline" in lowered_url and re.search(
            r"\b(key enhancements?|incremental loading|streamlined data|guid search|dependency impact|row-level|deterministic|rest api|java sdk|pagination|backend validation)\b",
            lowered_query,
        ):
            bonus += 1.25
        if lowered_url.endswith("web-editor-baseline-v2") and re.search(
            r"\b(key enhancements?|incremental loading|streamlined data|guid search|dependency impact|row-level|deterministic)\b",
            lowered_query,
        ):
            bonus -= 0.35
        if "new-baseline-migration-faq" in lowered_url and re.search(
            r"\b(faq|invalid references?|reltable|direct references?|scope\s*=?\"?peer|rollback|old baselines?|working copy|prerequisites?|on-premise 5\.2|cloud service 2026\.05\.0|migration time|backup)\b",
            lowered_query,
        ):
            bonus += 1.45
        if lowered_url.endswith("web-editor-baseline-v2") and re.search(
            r"\b(faq|invalid references?|reltable|direct references?|scope\s*=?\"?peer|rollback|old baselines?|working copy|prerequisites?|migration time|backup)\b",
            lowered_query,
        ):
            bonus -= 0.45
        if "generate-output-use-baseline-for-publishing" in lowered_url and re.search(
            r"\b(new baseline|beta|2026\.04\.0|bulk processor|migration|migrate|rebuild|download|guid|dependency preview|graph-based|rest api|java sdk)\b",
            lowered_query,
        ):
            bonus -= 0.65
        if lowered_url.endswith("web-editor-baseline") and re.search(
            r"\b(map console|manual update|automatic update|static baseline|dynamic baseline|baseline filters|export baseline exact copy)\b",
            lowered_query,
        ):
            bonus += 0.45
        if re.search(r"\b(manual update|automatic update|static baseline|dynamic baseline|date\s*:|label\s*:|labels\s*:)\b", lowered_content):
            bonus += 0.55
        if re.search(r"\b(create and manage baselines?|new baseline|baseline tab|baseline panel|new baseline dialog)\b", lowered_content):
            bonus += 0.35
        if re.search(r"\b(document states?|draft|approved|translated|published)\b", lowered_title + " " + lowered_content):
            bonus -= 0.9
        if re.search(r"\b(translation workflow|review task|workspace settings|component mapping|dita search|indexing)\b", lowered_title + " " + lowered_content):
            bonus -= 0.45

    return bonus


def _document_relevance_score(
    query: str,
    *,
    title: str,
    url: str,
    content: str,
    evidence_type: str = "",
    allowed_host_suffixes: tuple[str, ...] | None,
) -> float:
    query_tokens = _tokenize(query)
    title_score = _lexical_score(query_tokens, title)
    url_score = _lexical_score(query_tokens, url)
    content_score = _lexical_score(query_tokens, content)
    lowered_title = str(title or "").lower()
    lowered_url = str(url or "").lower()
    lowered_content = str(content or "").lower()

    phrase_bonus = 0.0
    for phrase in _phrase_candidates(query):
        if phrase in lowered_title:
            phrase_bonus += 0.3
        elif phrase in lowered_url:
            phrase_bonus += 0.22
        elif phrase in lowered_content:
            phrase_bonus += 0.14

    host_bonus = 0.12 if _matches_allowed_hosts(url, allowed_host_suffixes) else 0.0
    evidence_bonus = 0.0
    lowered_evidence_type = str(evidence_type or "").lower()
    is_enriched_behavior = lowered_evidence_type.startswith("enriched_")
    asks_dita_publishing_behavior = bool(
        re.search(
            r"\b(xml:lang|chunk|copy-to|conref|conkeyref|keyref|keys?|xref|ditaval|conditional|profile|"
            r"pdf2?|html5?|dita-ot|publishing|output|generated?\s+data)\b",
            str(query or "").lower(),
        )
    )
    if is_enriched_behavior:
        evidence_bonus += 0.28
        if asks_dita_publishing_behavior:
            evidence_bonus += 0.42
    if asks_dita_publishing_behavior and "experience-manager-guides" in lowered_url:
        evidence_bonus += 0.25
    if asks_dita_publishing_behavior and "experienceleague.adobe.com/en/docs/workfront/" in lowered_url:
        evidence_bonus -= 0.35
    if re.search(r"\b(generate|generation|dataset|test data|qa|oracle|evidence|expected|review|mcp)\b", str(query or "").lower()):
        if lowered_evidence_type == "learned_behavior_profile":
            evidence_bonus += 0.45
        elif lowered_evidence_type == "generation_oracle":
            evidence_bonus += 0.35
        elif lowered_evidence_type == "enriched_learned_behavior":
            evidence_bonus += 0.55
        elif lowered_evidence_type == "enriched_generation_oracle":
            evidence_bonus += 0.50
    return (
        (content_score * 0.45)
        + (title_score * 0.35)
        + (url_score * 0.18)
        + min(0.4, phrase_bonus)
        + _aem_intent_bonus(query, title=title, url=url, content=content)
        + host_bonus
        + evidence_bonus
    )


def _filter_and_rank_docs(
    query: str,
    docs: list[dict],
    *,
    k: int,
    allowed_host_suffixes: tuple[str, ...] | None,
) -> list[dict]:
    filtered = [
        doc for doc in (docs or [])
        if _matches_allowed_hosts(str(doc.get("url") or ""), allowed_host_suffixes)
    ]
    intent = _classify_aem_query_intent(query)
    limit_per_doc = 2 if intent in {"authoring_create", "baseline"} else (1 if intent in {"configuration", "publishing", "workflow"} else 2)
    ranked = sorted(
        (
            (
                _document_relevance_score(
                    query,
                    title=str(doc.get("title") or ""),
                    url=str(doc.get("url") or ""),
                    content=str(doc.get("snippet") or doc.get("content") or ""),
                    evidence_type=str(doc.get("evidence_type") or ""),
                    allowed_host_suffixes=allowed_host_suffixes,
                ),
                doc,
            )
            for doc in filtered
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    deduped: list[dict] = []
    seen_counts: dict[str, int] = {}
    for _score, doc in ranked:
        url = str(doc.get("url") or "").strip()
        title = str(doc.get("title") or "").strip()
        dedupe_key = url or title
        if not dedupe_key:
            continue
        count = seen_counts.get(dedupe_key, 0)
        if count >= limit_per_doc:
            continue
        seen_counts[dedupe_key] = count + 1
        deduped.append(doc)
        if len(deduped) >= k:
            break
    return deduped


def _require_semantic_retrieval_for_aem_guides(
    allowed_host_suffixes: tuple[str, ...] | None,
) -> bool:
    raw = (os.getenv("AEM_GUIDES_REQUIRE_SEMANTIC_RETRIEVAL") or "").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return False
    if not allowed_host_suffixes:
        return True
    return any(
        suffix == "experienceleague.adobe.com" or suffix.endswith(".experienceleague.adobe.com")
        for suffix in allowed_host_suffixes
    )


def _embedding_requirement_message(
    embedding: dict[str, Any],
    *,
    chunks_loaded: bool,
    chunks_with_embeddings: int = 0,
    semantic_required: bool,
) -> str:
    if not semantic_required:
        return ""
    if not bool(embedding.get("available")):
        base = (
            "Semantic retrieval is required for AEM Guides product lookup, but the local embedding model is unavailable. "
            "Set DITA_EMBEDDING_MODEL_PATH to a local SentenceTransformer model directory and restart the backend."
        )
        error = str(embedding.get("error") or "").strip()
        return f"{base} Last embedding error: {error}" if error else base
    if chunks_loaded and chunks_with_embeddings <= 0:
        return (
            "Semantic retrieval is required for AEM Guides product lookup, but the indexed AEM Guides chunks do not contain embeddings yet. "
            "Reindex the corpus after configuring the local embedding model."
        )
    return (
        "Semantic retrieval is required for AEM Guides product lookup, but no semantic results were available for this request. "
        "Review the query wording or reindex the corpus before relying on lexical fallback."
    )


def _lexical_fallback_warning(embedding: dict[str, Any]) -> str:
    if bool(embedding.get("available")):
        return (
            "Semantic retrieval did not return a usable result, so retrieval fell back to lexical ranking only."
        )
    error = str(embedding.get("error") or "").strip()
    base = (
        "Semantic retrieval was unavailable, so retrieval used lexical ranking only. "
        "Set DITA_EMBEDDING_MODEL_PATH to a local SentenceTransformer model path to restore semantic search."
    )
    return f"{base} Last embedding error: {error}" if error else base


def retrieve_relevant_docs_with_diagnostics(
    query: str,
    k: int = 5,
    max_snippet_chars: int = MAX_SNIPPET_CHARS,
    allowed_host_suffixes: Optional[list[str] | tuple[str, ...]] = None,
) -> dict[str, Any]:
    """Retrieve AEM Guides chunks plus retrieval diagnostics."""
    query = (query or "").strip()
    allowed_hosts = tuple(str(item).strip().lower() for item in (allowed_host_suffixes or []) if str(item).strip())
    semantic_required = _require_semantic_retrieval_for_aem_guides(allowed_hosts)
    embedding = get_embedding_diagnostics()
    payload: dict[str, Any] = {
        "query": query,
        "results": [],
        "count": 0,
        "retrieval_mode": "none",
        "semantic_required": semantic_required,
        "embedding": embedding,
        "warnings": [],
    }

    if not query:
        return payload

    embedding_available = bool(embedding.get("available")) and bool(is_embedding_available())
    semantic_issue = ""

    if is_chroma_available() and embedding_available:
        query_emb = embed_query(query)
        if query_emb is None:
            semantic_issue = "Embedding query generation returned no vector."
        else:
            rows = query_collection(
                CHROMA_COLLECTION_AEM_GUIDES,
                query_embedding=query_emb.tolist() if hasattr(query_emb, "tolist") else list(query_emb),
                k=max(k * 12, 50),
            )
            if rows:
                result = []
                for row in rows:
                    meta = row.get("metadata") or {}
                    doc = row.get("document") or ""
                    snippet = doc[:max_snippet_chars]
                    result.append({
                        "chunk_id": row.get("id", ""),
                        "url": meta.get("source_url") or meta.get("canonical_url") or meta.get("url", ""),
                        "source_url": meta.get("source_url") or meta.get("url", ""),
                        "canonical_url": meta.get("canonical_url") or meta.get("url", ""),
                        "corpus": meta.get("corpus", "aem_guides"),
                        "evidence_type": _infer_evidence_type(snippet, str(meta.get("evidence_type") or "")),
                        "title": meta.get("title", ""),
                        "snippet": snippet,
                    })
                ranked = _filter_and_rank_docs(query, result, k=k, allowed_host_suffixes=allowed_hosts)
                logger.info_structured(
                    "AEM Guides docs from ChromaDB (Experience League)",
                    extra_fields={
                        "source": "chromadb",
                        "count": len(ranked),
                        "allowed_hosts": list(allowed_hosts),
                    },
                )
                payload["results"] = ranked
                payload["count"] = len(ranked)
                payload["retrieval_mode"] = "chromadb_semantic"
                return payload

    chunks = _load_chunks()
    indexed_chunk_count = 0
    if chunks and embedding_available:
        query_emb = embed_query(query)
        if query_emb is None:
            semantic_issue = semantic_issue or "Embedding query generation returned no vector."
        else:
            indexed = [(i, c, c.get("embedding")) for i, c in enumerate(chunks) if c.get("embedding")]
            indexed_chunk_count = len(indexed)
            if indexed:
                try:
                    import numpy as np
                    query_arr = np.array(query_emb)
                    emb_list = [x[2] for x in indexed]
                    chunk_arr = np.array(emb_list)
                    scores = np.dot(chunk_arr, query_arr)
                    order = np.argsort(scores)[::-1][: max(k * 12, 50)]
                    result = []
                    for idx in order:
                        c = indexed[idx][1]
                        snippet = (c.get("content") or "")[:max_snippet_chars]
                        result.append({
                            "chunk_id": c.get("id", ""),
                            "url": c.get("source_url") or c.get("canonical_url") or c.get("url", ""),
                            "source_url": c.get("source_url") or c.get("url", ""),
                            "canonical_url": c.get("canonical_url") or c.get("url", ""),
                            "corpus": c.get("corpus", "aem_guides"),
                            "evidence_type": _infer_evidence_type(snippet, str(c.get("evidence_type") or "")),
                            "title": c.get("title", ""),
                            "snippet": snippet,
                        })
                    ranked = _filter_and_rank_docs(query, result, k=k, allowed_host_suffixes=allowed_hosts)
                    if ranked:
                        logger.info_structured(
                            "AEM Guides docs from JSON fallback (ChromaDB empty or unavailable)",
                            extra_fields={
                                "source": "json_fallback",
                                "count": len(ranked),
                                "chunks_with_embeddings": len(indexed),
                                "total_chunks": len(chunks),
                                "allowed_hosts": list(allowed_hosts),
                            },
                        )
                        payload["results"] = ranked
                        payload["count"] = len(ranked)
                        payload["retrieval_mode"] = "json_semantic"
                        return payload
                except Exception as e:
                    semantic_issue = f"Embedding retrieval failed: {e}"
                    logger.warning_structured(
                        "Embedding retrieval failed, using lexical",
                        extra_fields={"error": str(e)},
                    )

    if semantic_required:
        message = _embedding_requirement_message(
            embedding,
            chunks_loaded=bool(chunks),
            chunks_with_embeddings=indexed_chunk_count,
            semantic_required=semantic_required,
        )
        if message:
            payload["warnings"].append(message)
            payload["error"] = message
            payload["retrieval_mode"] = "semantic_unavailable"
            return payload

    if semantic_issue:
        payload["warnings"].append(semantic_issue)

    if not chunks:
        logger.info_structured(
            "AEM Guides: no docs available (run POST /api/v1/ai/crawl-aem-guides to populate)",
            extra_fields={"source": "none"},
        )
        return payload

    scored = []
    for c in chunks:
        snippet = (c.get("content") or "")[:max_snippet_chars]
        score = _document_relevance_score(
            query,
            title=str(c.get("title") or ""),
            url=str(c.get("url") or ""),
            content=snippet,
            evidence_type=str(c.get("evidence_type") or ""),
            allowed_host_suffixes=allowed_hosts,
        )
        if score <= 0:
            continue
        scored.append(
            (
                score,
                {
                    "chunk_id": c.get("id", ""),
                    "url": c.get("source_url") or c.get("canonical_url") or c.get("url", ""),
                    "source_url": c.get("source_url") or c.get("url", ""),
                    "canonical_url": c.get("canonical_url") or c.get("url", ""),
                    "corpus": c.get("corpus", "aem_guides"),
                    "evidence_type": c.get("evidence_type", ""),
                    "title": c.get("title", ""),
                    "snippet": snippet,
                },
            )
        )
    scored.sort(key=lambda x: x[0], reverse=True)
    ranked_docs = [doc for _score, doc in scored]
    ranked = _filter_and_rank_docs(query, ranked_docs, k=k, allowed_host_suffixes=allowed_hosts)
    payload["results"] = ranked
    payload["count"] = len(ranked)
    payload["retrieval_mode"] = "lexical"
    payload["warnings"].append(_lexical_fallback_warning(embedding))
    return payload


def retrieve_relevant_docs(
    query: str,
    k: int = 5,
    max_snippet_chars: int = MAX_SNIPPET_CHARS,
    allowed_host_suffixes: Optional[list[str] | tuple[str, ...]] = None,
) -> list[dict]:
    """
    Retrieve top-k relevant AEM Guides doc chunks for the query.
    Returns list of dicts: url, title, snippet.
    Tries ChromaDB first, then JSON+embedding, then lexical.
    """
    payload = retrieve_relevant_docs_with_diagnostics(
        query,
        k=k,
        max_snippet_chars=max_snippet_chars,
        allowed_host_suffixes=allowed_host_suffixes,
    )
    return list(payload.get("results") or [])


def format_docs_for_prompt(docs: list[dict]) -> str:
    """Format retrieved docs for inclusion in LLM prompt."""
    if not docs:
        return ""
    parts = []
    for i, d in enumerate(docs, 1):
        url = d.get("url", "")
        title = d.get("title", "")
        snippet = d.get("snippet", "")
        parts.append(f"[{i}] {title or url}\n{snippet}")
    return "\n\n".join(parts)
