"""Chat service - sessions, messages, RAG, streaming."""
import asyncio
import copy
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncGenerator, Optional
from uuid import uuid4

from app.db.session import SessionLocal
from app.db.chat_models import ChatSession, ChatMessage
from app.services.llm_service import (
    _coerce_llm_text_response,
    clear_llm_trace,
    format_llm_error_for_user,
    generate_chat_stream_with_tools,
    generate_text,
    is_llm_available,
    start_llm_trace,
    store_chat_llm_run,
    summarize_llm_trace,
)
from app.services.chat_tools import get_tool_catalog, get_tool_definitions, parse_tool_intent_from_content, run_tool
from app.core.schemas_chat_authoring import ChatAttachmentRef, ChatAuthoringRequestPayload, ChatDitaGenerationOptions
from app.core.schemas_grounded_answer import (
    ComparisonRow,
    GroundedAnswerKind,
    NormalizedGroundedFactSet,
    SourcePolicyDecision,
    VerifiedExampleSnippet,
)
from app.services.chat_authoring_governance import (
    AuthoringRunTimer,
    log_authoring_intent_rejected,
    log_authoring_trace_failed,
    log_authoring_trace_started,
    new_authoring_trace_id,
)
from app.services.chat_dita_authoring_service import get_chat_dita_authoring_service, merge_jira_into_authoring_prompt
from app.services.generate_dita_preview_service import (
    build_generate_dita_execution_contract,
    build_generate_dita_preview,
)
from app.services.prompt_router_service import route_prompt
from app.services.execution_policy_service import decide_execution_policy
from app.services.chat_agent_service import (
    AGENT_EXECUTION_KEY,
    AGENT_PLAN_KEY,
    APPROVAL_STATE_KEY,
    APPROVAL_REQUIRED_TOOLS,
    build_agent_plan,
    build_plan_preview_markdown,
    build_step_result_markdown,
    detect_agent_command,
    execution_from_plan,
    find_latest_agent_state,
    mark_step_status,
    reserved_agent_payload,
    resolve_followup_after_step,
    summarize_agent_results_locally,
)
from app.services.corrective_rag_service import run_chat_corrective_rag
from app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt
from app.services.dita_knowledge_retriever import retrieve_dita_knowledge
from app.services.claude_code_retriever import retrieve_claude_code_context
from app.services.jira_chat_search_service import extract_jira_search_query
from app.services.intent_analysis_service import analyze_intent_sync
from app.services.grounding_service import (
    build_evidence_pack,
    grounding_metadata_from_pack,
    grounding_to_notice,
    verify_grounded_answer,
)
from app.services.tenant_service import retrieve_tenant_context, retrieve_tenant_examples
from app.core.prompt_interface import PromptBuilder, load_prompt_spec
from app.core.structured_logging import get_structured_logger
from app.services.llm_service import _get_prompt_versions

logger = get_structured_logger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"

RAG_CONTEXT_MAX_CHARS = int(os.getenv("RAG_CONTEXT_MAX_CHARS", "6000"))
# Grounded chat: more DITA/spec chunks and evidence text help definitional questions (e.g. properties table).
CHAT_GROUNDED_DITA_K = int(os.getenv("CHAT_GROUNDED_DITA_K", "5"))
CHAT_GROUNDED_EVIDENCE_LIMIT = int(os.getenv("CHAT_GROUNDED_EVIDENCE_LIMIT", "5"))
CHAT_GROUNDED_EVIDENCE_MAX_CHARS = int(os.getenv("CHAT_GROUNDED_EVIDENCE_MAX_CHARS", "3000"))
RAG_AEM_K = int(os.getenv("RAG_AEM_K", "8"))
RAG_DITA_K = int(os.getenv("RAG_DITA_K", "8"))
RAG_SNIPPET_CHARS = int(os.getenv("RAG_SNIPPET_CHARS", "1000"))

# Chat limits (prevent unbounded growth)
CHAT_MAX_MESSAGES_PER_SESSION = int(os.getenv("CHAT_MAX_MESSAGES_PER_SESSION", "500"))
CHAT_CONTEXT_WINDOW_MESSAGES = int(os.getenv("CHAT_CONTEXT_WINDOW_MESSAGES", "20"))

# Session generation context for conversational refinement (in-memory, keyed by session_id)
_session_last_generation: dict[str, dict] = {}
_CHAT_CONTEXT_MAX_TOKENS_RAW = os.getenv("CHAT_CONTEXT_MAX_TOKENS", "120000").strip()
CHAT_CONTEXT_MAX_TOKENS = int(_CHAT_CONTEXT_MAX_TOKENS_RAW) if _CHAT_CONTEXT_MAX_TOKENS_RAW else None

_CHAT_PROMPT_BUILDER: Optional[PromptBuilder] = None
_DATASET_REQUEST_PATTERN = re.compile(
    r"\b(generate|create|build|make|run|start)\b.*\b(dataset|recipe|sample|smoke test|test data)\b|"
    r"\b(generate|create|build|make|run)\b.*\b(task_topics|concept_topics|glossary_pack|reference_topics|"
    r"properties_table_reference|syntax_diagram_reference|bookmap|conref_pack|keyscope|bulk_dita|incremental_topicref|insurance_incremental|"
    r"map_parse|relationship_table|validation_duplicate|maps_topicref|maps_reltable|maps_mapref)\b",
    re.IGNORECASE,
)
_DITA_GENERATION_PATTERN = re.compile(
    r"\b(generate|create|write|draft|make|build|need|want|get|give|send|export|"
    r"produce|prepare|provide|fetch|grab|pull|output|deliver|share|save|show)\b"
    r".*\b(dita|tasks?|task topics?|concepts?|concept topics?|references?|reference topics?|"
    r"glossary|glossaries|glossentry|glossentries|topics?|"
    r"zip|bundle|xml|sample|example|template|scaffold|boilerplate|bookmap|reltable|ditamap|maps?)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Download / ZIP intent detection (keyword-set approach, not fragile regex)
# ---------------------------------------------------------------------------
_DOWNLOAD_NOUNS = frozenset({
    "zip", "bundle", "package", "download", "export", "file", "files",
    "archive", "output", "link", "url", "artifact", "artifacts",
    "result", "results", "content", "dataset", "deliverable",
    "attachment", "generated", "dita", "xml",
})

_DOWNLOAD_VERBS = frozenset({
    "download", "zip", "bundle", "package", "export", "save",
    "provide", "share", "prepare", "fetch", "grab", "pull", "produce",
    "output", "deliver", "send", "give", "get", "need", "want",
    "show", "hand", "extract", "retrieve", "obtain", "acquire",
    "transfer", "receive", "collect", "take", "access", "open",
    "load", "bring", "pass", "attach", "generate", "create",
    "make", "build", "pack", "wrap", "compress",
})

# Standalone phrases that are unambiguously download requests
_DOWNLOAD_STANDALONE = re.compile(
    r"(?i)^\s*("
    r"zip\s*(it|that|this|up|please|now|ok|okay|already|the\s+\w+)?\s*[.!?]*\s*$|"
    r"download\s*(it|that|this|link|please|now|ok|okay|already)?\s*[.!?]*\s*$|"
    r"bundle\s*(it|that|this|please|now|ok|okay|already)?\s*[.!?]*\s*$|"
    r"package\s*(it|that|this|up|please|now|ok|okay|already)?\s*[.!?]*\s*$|"
    r"export\s*(it|that|this|please|now|ok|okay|already)?\s*[.!?]*\s*$|"
    r"(gimme|give me|hand me|show me|can i have|where'?s|where is|i need|i want)\s+(the\s+)?(zip|download|bundle|package|link|file|output|result|artifact)|"
    r"(can i|may i|i want to|i need to|let me|how do i|how to)\s+(download|get|access|open|retrieve|obtain|export|save)|"
    r"link\s*\??\s*$|"
    r"download\s+link\s*\??\s*$|"
    r"save\s+as\s+zip|"
    r"pack\s+it\s+up|"
    r"zip\s+the\s+\w+|"
    r"export\s+(the\s+)?(dita|files?|content|output|generated|xml|result|results|dataset|bundle)|"
    r"get\s+(me\s+)?(the\s+)?(zip|download|bundle|package|file|output|result|artifact)|"
    r"(just|please|can you|could you|would you)\s+(zip|download|bundle|package|export|save)\b"
    r")"
)

# Negative filter: explanatory questions about zip/download concepts
_DOWNLOAD_EXPLANATION_PATTERN = re.compile(
    r"(?i)^\s*(what\s+(is|are|does)|explain|define|meaning\s+of|tell\s+me\s+about)\b.*(zip|download|bundle|package)",
)


def _has_download_intent(text: str, *, session_aware: bool = False) -> bool:
    """Detect download/zip intent in user message.

    When session_aware=True (a previous generation exists in the session),
    use a very loose check — any download-related noun is sufficient.
    When session_aware=False, require more explicit phrasing (verb + noun or standalone phrase).
    """
    t = (text or "").strip().lower()
    if not t:
        return False
    # Always exclude explanatory / definitional questions
    if _DOWNLOAD_EXPLANATION_PATTERN.match(text):
        return False
    # Standalone phrases always match (regardless of session)
    if _DOWNLOAD_STANDALONE.match(text):
        return True
    words = set(re.findall(r"\b\w+\b", t))
    if session_aware:
        # With session context, any download-related noun is enough
        if words & _DOWNLOAD_NOUNS:
            return True
        # Also match follow-up phrases like "for the same", "for this", "ready?"
        if re.search(r"\b(for the same|for this|for that|the same|the above|same thing|ready|done)\b", t):
            return True
        # Match any download verb alone (e.g., "save", "export", "download")
        if words & {"download", "zip", "export", "save", "bundle", "pack", "package", "compress"}:
            return True
        return False
    # Without session context, require verb + noun combination
    return bool(words & _DOWNLOAD_VERBS) and bool(words & _DOWNLOAD_NOUNS)

_JIRA_SEARCH_PATTERN = re.compile(
    r"\b(jira|jiras|issue|issues|ticket|tickets)\b.*\b(fetch|find|show|search|lookup|look up|get|list|related|similar|matching|relevant)\b|"
    r"\b(fetch|find|show|search|lookup|look up|get|list)\b.*\b(jira|jiras|issue|issues|ticket|tickets)\b",
    re.IGNORECASE,
)

# XML review/validation detection: user pastes XML + asks for review
_XML_REVIEW_PATTERN = re.compile(
    r"(?s)(<\?xml|<!DOCTYPE|<(?:task|concept|topic|reference|glossentry|bookmap|map)\b)"
    r".*\b(review|validate|check|improve|fix|quality|score|suggest|correct|analy[sz]e)\b|"
    r"\b(review|validate|check|improve|fix|quality|score|suggest|correct|analy[sz]e)\b"
    r".*(<\?xml|<!DOCTYPE|<(?:task|concept|topic|reference|glossentry|bookmap|map)\b)",
    re.IGNORECASE,
)

# Recipe discovery: user wants to explore available recipes
_RECIPE_SEARCH_PATTERN = re.compile(
    r"\b(recipe|recipes)\b.*\b(find|search|list|show|available|which|what|recommend|suggest)\b|"
    r"\b(find|search|list|show|available|which|what|recommend|suggest)\b.*\b(recipe|recipes)\b|"
    r"\bwhat\s+(dataset|recipe)s?\s+(are|can|do)\b",
    re.IGNORECASE,
)

# Job status check: user asks about job progress
_JOB_STATUS_PATTERN = re.compile(
    r"\b(job|dataset)\b.*\b(status|done|finished|complete|ready|progress|running)\b|"
    r"\b(status|done|finished|complete|ready|progress)\b.*\b(job|dataset)\b|"
    r"\bis\s+(my|the)\s+(job|dataset|generation)\s+(done|ready|finished|complete)\b",
    re.IGNORECASE,
)

# Broader tool-mode path: rich chat_system prompt + tools for AEM/DITA/map authoring (not short definitional Qs).
_DOMAIN_TOOL_PATTERN = re.compile(
    r"\b(aem guides|\baem\b|adobe experience manager|experience manager guides|xml documentation|"
    r"\bdita\b|ditamap|ditaval|topicref|topichead|topicgroup|topicset|mapref|navref|keydef|keyref|conref|conkeyref|reltable|"
    r"bookmap|glossentry|glossgroup|subject scheme|reference topic|concept topic|task topic|technical content|"
    r"web editor|oxygen|\boxygen\b|framemaker|structured authoring|profiling|properties table|"
    r"proptype|propvalue|propdesc|basemap|publication|choicetable|simpletable|"
    r"native pdf|output preset|baseline|condition preset|review task|translation workflow|"
    r"content fragment|version history|map dashboard|bulk activation|chunk attribute|"
    r"specialization|constraint|branch filter)\b",
    re.IGNORECASE,
)
_DOMAIN_TOOL_ACTION_PATTERN = re.compile(
    r"\b(search|look\s*up|lookup|find|gather|collect|pull|compare|summari[sz]e|analy[sz]e|list|show)\b",
    re.IGNORECASE,
)
_SHORT_DEFINITION_OR_EXPLAIN = re.compile(
    r"(?is)^\s*(what\s+is|what\s+are|define|explain|meaning\s+of)\b.{1,200}$",
)
_DITA_STRUCTURAL_QUERY_PATTERN = re.compile(
    r"</?[A-Za-z][A-Za-z0-9._:-]*>|"
    r"\b(dita|ditamap|xml|doctype|element|attribute|topicref|topichead|topicgroup|mapref|navref|"
    r"keydef|keyref|conref|conkeyref|href|reltable|bookmap|glossentry|subject scheme|"
    r"related-links|related links?|relatedl|linklist|link list|linkinfo|link info|link element|"
    r"foreign element|data-about|data about|boolean element|index-base|index base|itemgroup|item group|"
    r"no-topic-nesting|no topic nesting|state element|unknown element|required-cleanup|required cleanup|"
    r"ditaval elements?|ditaval val|ditaval prop|revprop|startflag|endflag|alt-text|style-conflict|"
    r"id attributes?|metadata attributes?|localization attributes?|debug attributes?|architectural attributes?|"
    r"common map attributes?|cals table attributes?|display attributes?|date attributes?|"
    r"link relationship attributes?|common attributes?|simpletable attributes?|"
    r"xml:lang|xtrf|xtrc|domains|class attribute|"
    r"translate attribute|dir attribute|colsep|rowsep|rowheader|valign|expanse|frame attribute|"
    r"scale attribute|expiry|golive|role attribute|otherrole|base attribute|status attribute|"
    r"keycol|relcolwidth|refcols|indexterm|"
    r"task topic|concept topic|reference topic|specialization|constraint|keyscope)\b",
    re.IGNORECASE,
)
_DITA_ANSWER_INTENT_PATTERN = re.compile(
    r"^\s*(what|how|where|when|why|which|should|must|will|would|do|does|can|could|explain|define)\b|"
    r"\b(?:and\s+then|then|and|also)\s+(?:explain|define)\b|"
    r"\b(compare|difference\s+between|versus|vs\.?)\b",
    re.IGNORECASE,
)
_ASSISTIVE_DITA_GENERATION_REQUEST_PATTERN = re.compile(
    r"^\s*(can|could|would)\s+you\s+"
    r"(generate|create|write|draft|make|build|produce|prepare)\b",
    re.IGNORECASE,
)
_AEM_UI_CONFIGURATION_QUERY_PATTERN = re.compile(
    r"\b(aem guides|web editor|editor|toolbar|toolbars|shortcut|shortcuts|folder profile|"
    r"user preferences|editor settings|ui config|ui configuration|editor config|editor configuration|"
    r"theme|base path|citations)\b",
    re.IGNORECASE,
)
_NATIVE_PDF_QUERY_PATTERN = re.compile(
    r"\b(native pdf|pdf template|pdf output|watermark|page layout|headers?|footers?|table of contents|toc|cover page)\b",
    re.IGNORECASE,
)
_OUTPUT_PRESET_QUERY_PATTERN = re.compile(
    r"\b(output preset|output presets|publishing|publish|html5|pdf preset|aem sites|site generation)\b",
    re.IGNORECASE,
)
_DITA_ATTRIBUTE_QUERY_PATTERN = re.compile(
    r"@([A-Za-z_:][A-Za-z0-9_.:-]*)|"
    r"\battribute\s+`?@?([A-Za-z_:][A-Za-z0-9_.:-]*)`?\b|"
    r"\b`?@?([A-Za-z_:][A-Za-z0-9_.:-]*)`?\s+attribute\b",
    re.IGNORECASE,
)
_QUESTION_LED_PRODUCT_PATTERN = re.compile(
    r"\b(how|why|when|where|which|compare|versus|vs|difference|required|require|resolve|works?|working)\b",
    re.IGNORECASE,
)
_DITA_RELATED_LINKS_TOC_QUERY_PATTERN = re.compile(
    r"(?=.*\b(?:toc|table\s+of\s+contents|pdf|pdf\s+output)\b)"
    r"(?=.*\b(?:linklist|link\s+list|related-links|related\s+links?)\b)"
    r"(?=.*\btitle\b)",
    re.IGNORECASE,
)
_DITA_OUTPUT_TARGET_PATTERN = re.compile(
    r"\b(pdf|native\s+pdf|web|html|html5|aem\s+sites?|browser|dita-ot|output|outputs|publish|publishing)\b",
    re.IGNORECASE,
)
_DITA_OUTPUT_CONSTRUCT_PATTERN = re.compile(
    r"</?[A-Za-z][A-Za-z0-9._:-]*>|"
    r"\b(taskbody|conref|conkeyref|keyref|topicref|xref|choicetable|reltable|glossentry|"
    r"ditamap|bookmap|related-links|related\s+links?|relatedl|linklist|link\s+list|linkinfo|"
    r"foreign|foreign\s+element|data-about|data\s+about|boolean\s+element|index-base|"
    r"itemgroup|item\s+group|no-topic-nesting|state\s+element|unknown\s+element|required-cleanup|"
    r"ditaval\s+elements?|ditaval\s+val|ditaval\s+prop|revprop|startflag|endflag|alt-text|style-conflict|"
    r"id\s+attributes?|metadata\s+attributes?|localization\s+attributes?|debug\s+attributes?|architectural\s+attributes?|"
    r"common\s+map\s+attributes?|cals\s+table\s+attributes?|display\s+attributes?|date\s+attributes?|"
    r"link\s+relationship\s+attributes?|common\s+attributes?|simpletable\s+attributes?|"
    r"xml:lang|xtrf|xtrc|domains|class\s+attribute|"
    r"translate\s+attribute|dir\s+attribute|colsep|rowsep|rowheader|valign|expanse|frame\s+attribute|"
    r"scale\s+attribute|expiry|golive|role\s+attribute|otherrole|base\s+attribute|status\s+attribute|"
    r"keycol|relcolwidth|refcols|"
    r"processing-role|collection-type|locktitle|keyscope|navtitle)\b",
    re.IGNORECASE,
)
_DITA_FOREIGN_ELEMENT_QUERY_PATTERN = re.compile(r"</?foreign\b|\bforeign\s+element\b|\bforeign\b", re.IGNORECASE)

_HUMAN_PRECISION_ADDON: Optional[str] = None


@dataclass
class _GroundingCandidate:
    source: str
    label: str
    text: str
    url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


def _domain_tool_mode_enabled() -> bool:
    return os.getenv("CHAT_DOMAIN_TOOL_MODE", "true").strip().lower() in ("1", "true", "yes", "on")


def _looks_like_short_definition_question(text: str) -> bool:
    """Keep short 'what is / explain …' flows on the grounded path (evidence + verify)."""
    t = (text or "").strip()
    if len(t) > 200:
        return False
    return bool(_SHORT_DEFINITION_OR_EXPLAIN.match(t))


def _should_include_structural_dita_rag(question: str) -> bool:
    text = (question or "").strip()
    if not text:
        return False
    if _is_dita_construct_output_query(text):
        return True
    if _DITA_RELATED_LINKS_TOC_QUERY_PATTERN.search(text):
        return True
    if _AEM_UI_CONFIGURATION_QUERY_PATTERN.search(text) and not _DITA_STRUCTURAL_QUERY_PATTERN.search(text):
        return False
    return bool(_DITA_STRUCTURAL_QUERY_PATTERN.search(text))


def _is_dita_answer_request(question: str) -> bool:
    text = (question or "").strip()
    if not text or _ASSISTIVE_DITA_GENERATION_REQUEST_PATTERN.search(text):
        return False
    if _is_dita_construct_output_query(text):
        return True
    if _DITA_RELATED_LINKS_TOC_QUERY_PATTERN.search(text):
        return True
    return bool(_DITA_STRUCTURAL_QUERY_PATTERN.search(text) and _DITA_ANSWER_INTENT_PATTERN.search(text))


def _is_dita_construct_output_query(text: str) -> bool:
    trimmed = (text or "").strip()
    if not trimmed or trimmed.startswith("/"):
        return False
    return bool(
        _DITA_OUTPUT_TARGET_PATTERN.search(trimmed)
        and _DITA_OUTPUT_CONSTRUCT_PATTERN.search(trimmed)
        and (_DITA_ANSWER_INTENT_PATTERN.search(trimmed) or trimmed.endswith("?"))
    )


def _get_human_precision_addon() -> str:
    global _HUMAN_PRECISION_ADDON
    if _HUMAN_PRECISION_ADDON is not None:
        return _HUMAN_PRECISION_ADDON
    path = PROMPTS_DIR / "chat_human_precision.txt"
    try:
        _HUMAN_PRECISION_ADDON = path.read_text(encoding="utf-8").strip()
    except OSError:
        _HUMAN_PRECISION_ADDON = ""
    return _HUMAN_PRECISION_ADDON


def _get_chat_prompt_builder() -> PromptBuilder:
    """Get or create chat PromptBuilder. Uses PromptSpec from JSON or .txt fallback."""
    global _CHAT_PROMPT_BUILDER
    if _CHAT_PROMPT_BUILDER is not None:
        return _CHAT_PROMPT_BUILDER
    version = os.getenv("CHAT_PROMPT_VERSION", "").strip() or _get_prompt_versions().get("chat_system", "v1")
    spec = load_prompt_spec(PROMPTS_DIR, "chat_system", version)
    if spec:
        _CHAT_PROMPT_BUILDER = PromptBuilder(spec)
        return _CHAT_PROMPT_BUILDER
    logger.warning_structured(
        "Chat prompt spec not found, using fallback",
        extra_fields={"prompt_id": "chat_system"},
    )
    from app.core.prompt_interface import PromptSpec
    fallback = PromptSpec(
        id="chat_system",
        version="fallback",
        sections={
            "base": (
                "You are a friendly AI assistant for AEM Guides Dataset Studio. "
                "Help with DITA, recipes, and dataset generation. Use generate_dita when user pastes Jira content or asks to create DITA. "
                "Never invent download URLs, external links, file sizes, or bundle contents. "
                "Only reference a download when a tool result provides a verified app URL."
            )
        },
        section_order=["base"],
    )
    _CHAT_PROMPT_BUILDER = PromptBuilder(fallback)
    return _CHAT_PROMPT_BUILDER


def _build_chat_system_prompt(user_context: str, rag_context: str) -> str:
    """Build full chat system prompt from spec + dynamic blocks."""
    prompt = _get_chat_prompt_builder().build(user_context=user_context, rag_context=rag_context)
    safety_rules = (
        "\n\nTOOL RESULT SAFETY RULES:\n"
        "- Never invent or rewrite download URLs.\n"
        "- Never use placeholder links like example.com.\n"
        "- If a generate_dita tool result exists, use only its returned download_url and prefer telling the user to use the in-app download action.\n"
        "- Do not claim a bundle was generated unless the tool result says it was.\n"
        "- Do not invent file size, ZIP contents, expiry windows, or availability disclaimers."
    )
    return prompt + safety_rules


_tiktoken_encoder = None


def _get_tiktoken_encoder():
    """Lazy-load tiktoken encoder (cl100k_base, used by Claude)."""
    global _tiktoken_encoder
    if _tiktoken_encoder is None:
        try:
            import tiktoken
            _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tiktoken_encoder = False
    return _tiktoken_encoder if _tiktoken_encoder else None


def _approx_tokens(text: str) -> int:
    """Token count. Uses tiktoken when CHAT_USE_TIKTOKEN=true, else ~4 chars/token approximation."""
    if os.getenv("CHAT_USE_TIKTOKEN", "").lower() in ("true", "1", "yes"):
        enc = _get_tiktoken_encoder()
        if enc:
            return len(enc.encode(text or ""))
    return len(text or "") // 4


def _truncate_messages_by_tokens(messages: list[dict], max_tokens: int) -> list[dict]:
    """Keep most recent messages until within token budget."""
    if max_tokens <= 0:
        return messages[-1:] if messages else []
    total = 0
    result = []
    for m in reversed(messages):
        content = m.get("content") or ""
        if isinstance(content, list):
            content = str(content)
        tok = _approx_tokens(str(content)) + 4  # overhead per message
        if total + tok > max_tokens and result:
            break
        result.insert(0, m)
        total += tok
    return result


# Jira-style headings that indicate pasted Jira content
JIRA_STYLE_PATTERNS = [
    r"h3\.\s*Issue\s+Summary",
    r"h3\.\s*Issue\s+Description",
    r"Issue\s+Summary\s*\n",
    r"Issue\s+Description\s*\n",
    r"Steps to Reproduce",
    r"Expected Result",
    r"Actual Result",
]


def _detect_jira_style_text(text: str) -> bool:
    """Return True if text appears to be Jira-style pasted content."""
    if not text or len(text) < 50:
        return False
    t = text.strip()
    return any(re.search(p, t, re.IGNORECASE) for p in JIRA_STYLE_PATTERNS)


def _build_context_block(
    context: Optional[dict],
    user_content: str,
    session_id: Optional[str] = None,
) -> str:
    """Build USER CONTEXT block for system prompt from context dict and/or detected Jira text."""
    parts = []
    if context and isinstance(context, dict):
        source = context.get("source_page") or context.get("source")
        issue_key = context.get("issue_key")
        issue_summary = context.get("issue_summary")
        if source:
            parts.append(f"The user is on: {source}.")
        if issue_key:
            parts.append(f"Current issue: {issue_key}.")
        if issue_summary:
            parts.append(f"Issue summary: {issue_summary[:300]}{'...' if len(issue_summary) > 300 else ''}")
    if _detect_jira_style_text(user_content):
        parts.append(
            "The user has pasted Jira-style content. Call generate_dita immediately with the pasted text. "
            "Do not just summarize. If generation succeeds, direct the user to the in-app download action from the tool result."
        )
    # Conversational refinement: last generation in this session
    if session_id:
        last_gen = get_session_last_generation(session_id)
        if last_gen:
            prev_text = (last_gen.get("text") or "")[:800]
            prev_download = last_gen.get("download_url") or ""
            parts.append(
                f"LAST GENERATION IN THIS SESSION (user can refine or download):\n"
                f"Previous text: {prev_text}{'...' if len(last_gen.get('text', '') or '') > 800 else ''}\n"
                f"Download URL: {prev_download}\n"
                "When user says 'add X', 'refine', 'make steps more detailed', etc., call generate_dita with "
                "text=<previous text> and instructions=<their refinement request>.\n"
                "When user asks for 'zip', 'download', 'bundle', 'package', or 'export', AND a previous generation "
                "exists with a download URL above, provide that download URL directly — do NOT re-generate or "
                "explain what a ZIP file is. If no previous generation exists, call generate_dita to create one."
            )
    if not parts:
        return ""
    return "\n\nUSER CONTEXT:\n" + "\n".join(parts) + "\n\n"


def _tool_result_download_url(result: dict | None) -> str:
    if not isinstance(result, dict):
        return ""
    download_url = str(result.get("download_url") or "").strip()
    if download_url.startswith("/api/v1/ai/bundle/") and download_url.endswith("/download"):
        return download_url
    return ""


def _tool_result_summary(result: dict[str, Any]) -> str:
    if result.get("attribute_name"):
        value = " ".join(str(result.get("text_content") or "").split()).strip()
        if value:
            return value
    if result.get("element_name"):
        for key in ("content_model_summary", "placement_summary", "text_content"):
            value = " ".join(str(result.get(key) or "").split()).strip()
            if value:
                return value
    for key in ("summary", "content_model_summary", "placement_summary", "short_answer", "message"):
        value = " ".join(str(result.get(key) or "").split()).strip()
        if value:
            return value
    return ""


def _tool_result_warnings(result: dict[str, Any]) -> list[str]:
    warnings = result.get("warnings") or []
    if isinstance(warnings, list):
        return [str(item).strip() for item in warnings if str(item).strip()]
    if isinstance(warnings, str) and warnings.strip():
        return [warnings.strip()]
    return []


def _extract_aem_retrieval_metadata(tool_results_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    aem = tool_results_by_name.get("lookup_aem_guides") or {}
    if not isinstance(aem, dict):
        return {}
    embedding = aem.get("embedding") or {}
    metadata: dict[str, Any] = {
        "mode": str(aem.get("retrieval_mode") or "").strip(),
        "semantic_required": bool(aem.get("semantic_required")),
    }
    live_search = aem.get("live_search") or {}
    if isinstance(live_search, dict):
        metadata["live_search"] = {
            "provider": str(live_search.get("provider") or "").strip(),
            "enabled": bool(live_search.get("enabled")),
            "strategy": str(live_search.get("strategy") or "").strip(),
            "result_count": int(live_search.get("result_count") or 0),
        }
    if isinstance(embedding, dict):
        metadata["embedding"] = {
            "available": bool(embedding.get("available")),
            "configured_model": str(embedding.get("configured_model") or "").strip(),
            "configured_model_path": str(embedding.get("configured_model_path") or "").strip(),
            "active_model_identifier": str(embedding.get("active_model_identifier") or "").strip(),
            "load_mode": str(embedding.get("load_mode") or "").strip(),
            "error": str(embedding.get("error") or "").strip(),
        }
    warning_values = _tool_result_warnings(aem)
    if warning_values:
        metadata["warnings"] = warning_values
    error_text = str(aem.get("error") or "").strip()
    if error_text:
        metadata["error"] = error_text
    return {key: value for key, value in metadata.items() if value not in ("", [], {}, None)}


def _first_summary_sentence(text: str, *, max_chars: int = 280) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    match = re.search(r"(.+?[.!?])(?:\s|$)", cleaned)
    sentence = (match.group(1) if match else cleaned).strip()
    if len(sentence) <= max_chars:
        return sentence
    return sentence[: max_chars - 3].rstrip() + "..."


def _extract_attribute_syntax_line(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    match = re.search(r"Syntax:\s*(.+)", cleaned, re.IGNORECASE)
    if not match:
        return ""
    syntax = str(match.group(1) or "").strip()
    if not syntax:
        return ""
    return syntax.splitlines()[0].strip().rstrip(".")


def _has_strong_direct_dita_tool_evidence(result: dict[str, Any]) -> bool:
    if not isinstance(result, dict) or result.get("error"):
        return False
    if result.get("text_content") and (
        result.get("supported_elements")
        or result.get("all_valid_values")
        or result.get("combination_attributes")
        or result.get("default_scenarios")
        or result.get("usage_contexts")
        or result.get("spec_chunks")
        or result.get("graph_knowledge")
    ):
        return True
    return False


def _build_post_tool_assistant_text(tool_results_by_name: dict[str, dict]) -> str:
    lines: list[str] = []

    dita_result = tool_results_by_name.get("generate_dita")
    if isinstance(dita_result, dict):
        if dita_result.get("error"):
            lines.append(f"DITA bundle generation failed: {dita_result.get('error')}")
        else:
            summary = _tool_result_summary(dita_result)
            jira_id = str(dita_result.get("jira_id") or "generated bundle").strip()
            run_id = str(dita_result.get("run_id") or "").strip()
            download_url = _tool_result_download_url(dita_result)
            if summary:
                lines.append(summary)
            else:
                lines.append(f"DITA bundle generated for `{jira_id}`.")
            if download_url:
                lines.append("Use the Download DITA Bundle action below to fetch the real ZIP from this app.")
            else:
                lines.append("The bundle was created, but no verified download URL is available yet.")
            if run_id:
                lines.append(f"Run ID: `{run_id}`")
            scenarios = dita_result.get("scenarios")
            if isinstance(scenarios, list) and scenarios:
                lines.append(f"Scenarios generated: {len(scenarios)}")

    job_result = tool_results_by_name.get("create_job")
    if isinstance(job_result, dict):
        if job_result.get("error"):
            lines.append(f"Dataset job creation failed: {job_result.get('error')}")
        else:
            summary = _tool_result_summary(job_result)
            job_id = str(job_result.get("job_id") or "").strip()
            recipe_type = str(job_result.get("recipe_type") or "").strip()
            if summary:
                lines.append(summary)
            else:
                lines.append(
                    f"Dataset generation started{f' for `{recipe_type}`' if recipe_type else ''}."
                    f"{f' Job ID: `{job_id}`.' if job_id else ''} Use the in-chat dataset card for progress and download."
                )
            lines.append("Use the in-chat dataset card for progress and download.")

    jira_result = tool_results_by_name.get("search_jira_issues")
    if isinstance(jira_result, dict):
        summary = _tool_result_summary(jira_result)
        issues = jira_result.get("issues")
        if summary:
            lines.append(summary)
        if isinstance(issues, list) and issues:
            first = issues[0] if isinstance(issues[0], dict) else {}
            issue_key = str(first.get("issue_key") or "").strip()
            issue_summary = str(first.get("summary") or "").strip()
            issue_line = (
                "I found a real Jira issue match from verified search results."
                f"{f' `{issue_key}`' if issue_key else ''}"
                f"{f': {issue_summary}' if issue_summary else ''}"
            )
            if issue_line not in lines:
                lines.append(issue_line)
        elif not summary:
            query = str(jira_result.get("query") or "your search").strip()
            lines.append(f"No verified Jira issues matched `{query}`.")

    for name, result in tool_results_by_name.items():
        if name in {"generate_dita", "create_job", "search_jira_issues"}:
            continue
        if not isinstance(result, dict):
            continue
        if result.get("error"):
            lines.append(f"{name.replace('_', ' ')} failed: {result.get('error')}")
            continue
        summary = _tool_result_summary(result)
        if summary:
            lines.append(summary)
        warnings = _tool_result_warnings(result)
        if warnings:
            lines.append(warnings[0])
        sources = result.get("sources") or []
        if isinstance(sources, list) and sources:
            first = sources[0] if isinstance(sources[0], dict) else {}
            if isinstance(first, dict):
                label = str(first.get("label") or first.get("title") or "").strip()
                url = str(first.get("url") or first.get("uri") or "").strip()
                if label and url:
                      lines.append(f"Sources: {label} — {url}")
                elif label:
                      lines.append(f"Sources: {label}")
                elif url:
                      lines.append(f"Sources: {url}")

    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        clean = line.strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(clean)

    return "\n\n".join(deduped).strip()


def _build_authoring_assistant_text(result: dict[str, Any]) -> str:
    status = str(result.get("status") or "error").strip() or "error"
    title = str(result.get("title") or "Generated topic").strip() or "Generated topic"
    dita_type = str(result.get("dita_type") or "topic").strip() or "topic"
    validation = result.get("validation_result") or {}
    valid = bool(validation.get("valid"))
    quality_score = validation.get("quality_score")
    saved_asset_path = str(result.get("saved_asset_path") or "").strip()
    debug = result.get("debug") or {}
    if isinstance(debug, dict) and debug.get("output_mode") == "xml_only":
        return (
            f"Generated **{dita_type}** topic: **{title}**. "
            f"Validation: {'passed' if valid else 'needs attention'}."
        )
    lines = [
        "## DITA topic generation",
        f"- Status: {status.replace('_', ' ')}",
        f"- Title: {title}",
        f"- DITA type: {dita_type}",
        f"- Validation: {'passed' if valid else 'needs attention'}",
    ]
    if quality_score is not None:
        lines.append(f"- Quality score: {quality_score}")
    if saved_asset_path:
        lines.append(f"- Saved asset path: {saved_asset_path}")
    artifact_url = str(result.get("artifact_url") or "").strip()
    if artifact_url:
        lines.append("- Use the Open XML action below to inspect the generated topic.")
    recs = result.get("link_recommendations")
    if isinstance(recs, list) and recs:
        lines.append("")
        lines.append("### Link & reuse guidance (safe — no invented paths)")
        for item in recs[:12]:
            if not isinstance(item, dict):
                continue
            summ = str(item.get("summary") or "").strip()
            act = str(item.get("action") or "").strip()
            sev = str(item.get("severity") or "info").strip()
            if not summ:
                continue
            bullet = f"- **{sev}**: {summ}"
            if act:
                bullet += f" — {act}"
            lines.append(bullet)
    return "\n".join(lines)


def _should_use_tool_mode(user_content: str, session_id: str | None = None) -> bool:
    return _determine_answer_mode(user_content, session_id=session_id) in {
        "generation_request",
        "xml_review_answer",
    }


def _is_plain_generate_dita_request(user_content: str) -> bool:
    text = (user_content or "").strip()
    if not text:
        return False
    if text.startswith("/"):
        return False
    if _looks_like_dita_xml(text):
        return False
    if _XML_REVIEW_PATTERN.search(text):
        return False
    if _JOB_STATUS_PATTERN.search(text):
        return False
    if _has_download_intent(text, session_aware=False):
        return False
    if _is_dita_answer_request(text):
        return False
    return bool(_detect_jira_style_text(text) or _DITA_GENERATION_PATTERN.search(text))


def _looks_like_generate_dita_clarification_response(
    user_content: str,
    *,
    preview: dict[str, Any] | None = None,
) -> bool:
    text = (user_content or "").strip()
    if not text or text.startswith("/"):
        return False
    if "?" in text or _looks_like_dita_xml(text):
        return False
    if _is_plain_generate_dita_request(text) or _is_direct_jira_search_request(text):
        return False

    preview = preview or {}
    question = str(preview.get("clarification_question") or "").strip().lower()
    topic_family = str(preview.get("topic_family") or "").strip().lower()
    lowered = text.lower()

    if "subject" in question or "domain" in question:
        return len(text.split()) <= 12 and len(text) <= 120

    if topic_family == "topic":
        return bool(
            re.fullmatch(
                r"\s*(?:\d+\s+)?(?:concept|task|reference|generic|topic)(?:\s+topics?)?(?:\s+with\s+a\s+map)?(?:\s+on\s+.+)?\s*",
                lowered,
            )
        )

    return len(text.split()) <= 10 and len(text) <= 100


_GENERATE_DITA_ACK_PATTERN = re.compile(
    r"^\s*(?:approve|approved|continue|run it|go ahead|proceed|yes(?:\s+please)?|do it|ok|okay|sure)\s*[.!?]*\s*$",
    re.IGNORECASE,
)


def _looks_like_generate_dita_acknowledgement(user_content: str) -> bool:
    return bool(_GENERATE_DITA_ACK_PATTERN.fullmatch((user_content or "").strip()))


def _determine_answer_mode(user_content: str, session_id: str | None = None) -> str:
    text = (user_content or "").strip()
    if not text:
        return "default"
    if _detect_jira_style_text(text):
        return "generation_request"
    if _DATASET_REQUEST_PATTERN.search(text):
        return "agent_research_plan"
    if _is_dita_answer_request(text):
        return "grounded_dita_answer"
    if _DITA_GENERATION_PATTERN.search(text):
        return "generation_request"
    if _XML_REVIEW_PATTERN.search(text):
        return "xml_review_answer"
    if _RECIPE_SEARCH_PATTERN.search(text):
        return "agent_research_plan"
    if _JOB_STATUS_PATTERN.search(text):
        return "generation_request"
    if session_id:
        last_gen = get_session_last_generation(session_id)
        if last_gen and last_gen.get("download_url"):
            if _has_download_intent(text, session_aware=True):
                return "generation_request"
    if _has_download_intent(text, session_aware=False):
        return "generation_request"
    if (
        _domain_tool_mode_enabled()
        and _DOMAIN_TOOL_PATTERN.search(text)
        and _DOMAIN_TOOL_ACTION_PATTERN.search(text)
        and not _looks_like_short_definition_question(text)
    ):
        return "agent_research_plan"
    if _AEM_UI_CONFIGURATION_QUERY_PATTERN.search(text) and not _DITA_STRUCTURAL_QUERY_PATTERN.search(text):
        return "grounded_aem_answer"
    if _AEM_UI_CONFIGURATION_QUERY_PATTERN.search(text) and _DITA_STRUCTURAL_QUERY_PATTERN.search(text):
        return "agent_research_plan"
    if _DITA_STRUCTURAL_QUERY_PATTERN.search(text):
        return "grounded_dita_answer"
    if _DOMAIN_TOOL_PATTERN.search(text):
        if _looks_like_short_definition_question(text) or _QUESTION_LED_PRODUCT_PATTERN.search(text):
            return "grounded_aem_answer"
        return "agent_research_plan"
    return "default"


def _extract_requested_dita_attribute(user_content: str) -> str:
    text = (user_content or "").strip()
    if not text:
        return ""
    if _DITA_RELATED_LINKS_TOC_QUERY_PATTERN.search(text):
        # In this question family, "TOC" means the generated table of contents,
        # not the map-scoped @toc attribute. Keep the lookup on element semantics.
        return ""
    try:
        from app.services.dita_query_interpreter import extract_attribute_names

        attribute_names = extract_attribute_names(text)
        if attribute_names:
            return str(attribute_names[0]).strip().lower()
    except Exception:
        pass
    match = _DITA_ATTRIBUTE_QUERY_PATTERN.search(text)
    if match:
        candidate = next((group for group in match.groups() if group), "")
        candidate = candidate.strip().lstrip("@").lower()
        if candidate not in {"attribute", "dita", "xml", "topic", "map"}:
            return candidate

    try:
        intent = analyze_intent_sync(text)
    except Exception:
        return ""

    detected = getattr(intent, "detected_dita_construct", None)
    attributes = list(getattr(detected, "attributes", []) or [])
    return str(attributes[0]).strip().lower() if attributes else ""


def _grounded_tool_requests(answer_mode: str, user_content: str) -> list[tuple[str, dict[str, Any]]]:
    requests: list[tuple[str, dict[str, Any]]] = []
    lowered = (user_content or "").strip().lower()

    if answer_mode == "grounded_dita_answer":
        attribute_name = _extract_requested_dita_attribute(user_content)
        if attribute_name:
            requests.append(("lookup_dita_attribute", {"attribute_name": attribute_name}))
        requests.append(("lookup_dita_spec", {"query": user_content}))
        return requests

    if answer_mode == "grounded_aem_answer":
        if _NATIVE_PDF_QUERY_PATTERN.search(lowered):
            requests.append(("generate_native_pdf_config", {"query": user_content}))
            requests.append(("lookup_output_preset", {"query": user_content, "output_type": "native_pdf"}))
        elif _OUTPUT_PRESET_QUERY_PATTERN.search(lowered):
            requests.append(("lookup_output_preset", {"query": user_content}))
        else:
            requests.append(("lookup_aem_guides", {"query": user_content}))
        if _should_include_tenant_knowledge_for_aem_query(user_content):
            requests.append(("search_tenant_knowledge", {"query": user_content}))
    return requests


def _append_grounding_candidate(
    candidates: list[_GroundingCandidate],
    *,
    source: str,
    label: str,
    text: str,
    url: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    clean_text = " ".join(str(text or "").split()).strip()
    clean_label = " ".join(str(label or "").split()).strip()
    clean_url = str(url or "").strip()
    if not clean_text:
        return
    candidates.append(
        _GroundingCandidate(
            source=source,
            label=clean_label or source.replace("_", " ").title(),
            text=clean_text,
            url=clean_url,
            metadata=dict(metadata or {}),
            score=0.0,
        )
    )


def _tool_result_to_grounding_candidates(
    tool_name: str,
    result: dict[str, Any],
) -> list[_GroundingCandidate]:
    if not isinstance(result, dict) or result.get("error"):
        return []

    source_kind = {
        "lookup_dita_spec": "dita_spec",
        "lookup_dita_attribute": "dita_spec",
        "lookup_aem_guides": "aem_guides",
        "lookup_output_preset": "aem_guides",
        "generate_native_pdf_config": "aem_guides" if result.get("evidence") else "unknown",
        "search_tenant_knowledge": "tenant_context",
    }.get(tool_name, "unknown")

    candidates: list[_GroundingCandidate] = []
    for source in (result.get("sources") or [])[:6]:
        if not isinstance(source, dict):
            continue
        _append_grounding_candidate(
            candidates,
            source=source_kind,
            label=str(source.get("label") or source.get("title") or "").strip(),
            text=str(source.get("snippet") or source.get("summary") or "").strip(),
            url=str(source.get("url") or source.get("uri") or "").strip(),
            metadata={"title": str(source.get("label") or source.get("title") or "").strip()},
        )

    has_positive_evidence = False
    if tool_name == "lookup_dita_attribute":
        has_positive_evidence = bool(
            result.get("text_content")
            or result.get("all_valid_values")
            or result.get("supported_elements")
            or result.get("combination_attributes")
            or result.get("default_scenarios")
        )
    elif tool_name == "lookup_dita_spec":
        has_positive_evidence = bool(
            result.get("spec_chunks")
            or result.get("graph_knowledge")
            or result.get("attribute_name")
            or result.get("text_content")
            or result.get("all_valid_values")
        )
    elif tool_name == "lookup_aem_guides":
        has_positive_evidence = bool(result.get("results"))
    elif tool_name == "lookup_output_preset":
        has_positive_evidence = bool(result.get("doc_results") or result.get("seed_results"))
    elif tool_name == "generate_native_pdf_config":
        has_positive_evidence = bool(result.get("short_answer") or result.get("recommended_actions"))
    elif tool_name == "search_tenant_knowledge":
        has_positive_evidence = bool(result.get("results"))

    summary = _tool_result_summary(result)
    if summary and has_positive_evidence:
        _append_grounding_candidate(
            candidates,
            source=source_kind,
            label=str(result.get("query") or tool_name.replace("_", " ").title()).strip(),
            text=summary,
            url=str(result.get("source_url") or "").strip(),
            metadata={"title": str(result.get("query") or tool_name).strip()},
        )

    if tool_name == "lookup_dita_attribute":
        attribute_name = str(result.get("attribute_name") or "").strip()
        text_content = str(result.get("text_content") or "").strip()
        if text_content:
            _append_grounding_candidate(
                candidates,
                source="dita_spec",
                label=f"@{attribute_name}" if attribute_name else "DITA attribute",
                text=text_content,
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"@{attribute_name}" if attribute_name else "DITA attribute"},
            )
        syntax_line = _extract_attribute_syntax_line(text_content)
        if syntax_line:
            _append_grounding_candidate(
                candidates,
                source="dita_spec",
                label=f"@{attribute_name} syntax" if attribute_name else "Attribute syntax",
                text=f"Syntax: {syntax_line}.",
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"@{attribute_name} syntax" if attribute_name else "Attribute syntax"},
            )
        valid_values = [str(item).strip() for item in (result.get("all_valid_values") or []) if str(item).strip()]
        if valid_values:
            _append_grounding_candidate(
                candidates,
                source="dita_spec",
                label=f"@{attribute_name} valid values" if attribute_name else "Valid values",
                text=f"Valid values: {', '.join(valid_values[:12])}.",
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"@{attribute_name} valid values" if attribute_name else "Valid values"},
            )
        supported_elements = [str(item).strip() for item in (result.get("supported_elements") or []) if str(item).strip()]
        if supported_elements:
            _append_grounding_candidate(
                candidates,
                source="dita_graph",
                label=f"@{attribute_name} supported elements" if attribute_name else "Supported elements",
                text=f"Supported elements: {', '.join(supported_elements[:12])}.",
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"@{attribute_name} supported elements" if attribute_name else "Supported elements"},
            )
        combinations = [str(item).strip() for item in (result.get("combination_attributes") or []) if str(item).strip()]
        if combinations:
            _append_grounding_candidate(
                candidates,
                source="dita_spec",
                label=f"@{attribute_name} companion attributes" if attribute_name else "Companion attributes",
                text=f"Common companion attributes: {', '.join(combinations[:10])}.",
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"@{attribute_name} companion attributes" if attribute_name else "Companion attributes"},
            )
        default_scenarios = [str(item).strip() for item in (result.get("default_scenarios") or []) if str(item).strip()]
        if default_scenarios:
            _append_grounding_candidate(
                candidates,
                source="dita_spec",
                label=f"@{attribute_name} defaults" if attribute_name else "Default behavior",
                text=f"Default behavior examples: {'; '.join(default_scenarios[:3])}.",
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"@{attribute_name} defaults" if attribute_name else "Default behavior"},
            )
    elif tool_name == "lookup_dita_spec":
        attribute_name = str(result.get("attribute_name") or "").strip()
        text_content = str(result.get("text_content") or "").strip()
        if attribute_name and text_content:
            _append_grounding_candidate(
                candidates,
                source="dita_spec",
                label=f"@{attribute_name}",
                text=text_content,
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"@{attribute_name}"},
            )
        syntax_line = _extract_attribute_syntax_line(text_content)
        if attribute_name and syntax_line:
            _append_grounding_candidate(
                candidates,
                source="dita_spec",
                label=f"@{attribute_name} syntax",
                text=f"Syntax: {syntax_line}.",
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"@{attribute_name} syntax"},
            )
        valid_values = [str(item).strip() for item in (result.get("all_valid_values") or []) if str(item).strip()]
        if attribute_name and valid_values:
            _append_grounding_candidate(
                candidates,
                source="dita_spec",
                label=f"@{attribute_name} valid values",
                text=f"Valid values: {', '.join(valid_values[:12])}.",
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"@{attribute_name} valid values"},
            )
        element_name = str(result.get("element_name") or "").strip()
        content_model_summary = str(result.get("content_model_summary") or "").strip()
        placement_summary = str(result.get("placement_summary") or "").strip()
        if element_name and (content_model_summary or placement_summary or text_content):
            _append_grounding_candidate(
                candidates,
                source="dita_spec",
                label=f"<{element_name}>",
                text=content_model_summary or placement_summary or text_content,
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"<{element_name}>"},
            )
        allowed_children = [str(item).strip() for item in (result.get("allowed_children") or []) if str(item).strip()]
        if element_name and allowed_children:
            _append_grounding_candidate(
                candidates,
                source="dita_graph",
                label=f"<{element_name}> children",
                text=f"Allowed children: {', '.join(allowed_children[:12])}.",
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"<{element_name}> children"},
            )
        parent_elements = [str(item).strip() for item in (result.get("parent_elements") or []) if str(item).strip()]
        if element_name and parent_elements:
            _append_grounding_candidate(
                candidates,
                source="dita_graph",
                label=f"<{element_name}> placement",
                text=f"Can appear inside: {', '.join(parent_elements[:12])}.",
                url=str(result.get("source_url") or "").strip(),
                metadata={"title": f"<{element_name}> placement"},
            )
        graph_knowledge = str(result.get("graph_knowledge") or "").strip()
        if graph_knowledge:
            _append_grounding_candidate(
                candidates,
                source="dita_graph",
                label="DITA graph knowledge",
                text=graph_knowledge,
                metadata={"title": "DITA graph knowledge"},
            )
    elif tool_name == "generate_native_pdf_config":
        short_answer = str(result.get("short_answer") or "").strip()
        actions = [str(item).strip() for item in (result.get("recommended_actions") or []) if str(item).strip()]
        if short_answer or actions:
            _append_grounding_candidate(
                candidates,
                source=source_kind,
                label=str(result.get("config_area") or "Native PDF guidance").strip(),
                text=" ".join([short_answer, *actions[:3]]).strip(),
                metadata={"title": str(result.get("config_area") or "Native PDF guidance").strip()},
            )
    elif tool_name == "lookup_output_preset":
        snippets = [str(item.get("text_content") or "").strip() for item in (result.get("seed_results") or []) if isinstance(item, dict)]
        if snippets:
            _append_grounding_candidate(
                candidates,
                source="aem_guides",
                label=str(result.get("output_type") or result.get("query") or "Output preset").strip(),
                text=" ".join(snippets[:3]).strip(),
                metadata={"title": str(result.get("output_type") or result.get("query") or "Output preset").strip()},
            )
    return candidates


async def _build_grounded_tool_evidence_pack(
    *,
    answer_mode: str,
    user_content: str,
    tenant_id: str,
    user_id: str,
    session_id: str,
) -> tuple[object | None, dict[str, Any], dict[str, dict[str, Any]]]:
    requests = _grounded_tool_requests(answer_mode, user_content)
    if not requests:
        return None, {}, {}

    tool_results: dict[str, dict[str, Any]] = {}
    candidates: list[_GroundingCandidate] = []
    for tool_name, params in requests:
        result = await run_tool(
            tool_name,
            params,
            user_id=user_id,
            session_id=session_id,
            tenant_id=tenant_id,
        )
        tool_results[tool_name] = result
        candidates.extend(_tool_result_to_grounding_candidates(tool_name, result))

    if not candidates:
        return None, {"strategy": "tool_grounding", "tool_names": list(tool_results)}, tool_results

    evidence_pack = build_evidence_pack(
        query=user_content,
        tenant_id=tenant_id,
        candidates=candidates,
    )
    if answer_mode == "grounded_dita_answer":
        attr_result = tool_results.get("lookup_dita_attribute") or {}
        spec_result = tool_results.get("lookup_dita_spec") or {}
        if _has_strong_direct_dita_tool_evidence(attr_result) or _has_strong_direct_dita_tool_evidence(spec_result):
            evidence_pack.decision.status = "grounded"
            evidence_pack.decision.confidence = max(float(evidence_pack.decision.confidence or 0.0), 0.88)
            evidence_pack.decision.reason = "Structured DITA spec tools returned direct evidence for this question."
            evidence_pack.decision.thin_evidence = False
            if "dita_spec" not in evidence_pack.decision.source_kinds:
                evidence_pack.decision.source_kinds.append("dita_spec")
    retrieval_meta = {
        "strategy": "tool_grounding",
        "tool_names": list(tool_results),
        "strength": evidence_pack.decision.status,
        "reason": evidence_pack.decision.reason,
        "correction_applied": False,
        "corrected_query": "",
    }
    return evidence_pack, retrieval_meta, tool_results


_MAP_SCOPED_ATTR_NAMES = frozenset(
    {
        "keyscope",
        "processing-role",
        "chunk",
        "collection-type",
        "linking",
        "toc",
        "print",
        "keydef",
        "keyref",
        "mapref",
        "topicref",
        "ditavalref",
        "reltable",
    }
)

_MAP_CONSTRUCT_ELEMENT_NAMES = frozenset(
    {
        "map",
        "bookmap",
        "topicref",
        "topichead",
        "topicgroup",
        "mapref",
        "navref",
        "keydef",
        "reltable",
        "ditavalref",
        "topicsubject",
        "subjectref",
        "subjectscheme",
    }
)


def _clean_grounded_strings(items: Any, *, limit: int | None = None) -> list[str]:
    values: list[str] = []
    if not isinstance(items, list):
        return values
    for item in items:
        text = " ".join(str(item or "").split()).strip()
        if not text or text in values:
            continue
        values.append(text)
        if limit is not None and len(values) >= limit:
            break
    return values


def _summary_grounded_strings(items: Any, *, limit: int | None = None) -> list[str]:
    values: list[str] = []
    if not isinstance(items, list):
        return values
    for item in items:
        text = _first_summary_sentence(" ".join(str(item or "").split()).strip())
        if not text or text in values:
            continue
        values.append(text)
        if limit is not None and len(values) >= limit:
            break
    return values


def _clean_graph_knowledge_for_answer(text: str) -> str:
    compact = " ".join(str(text or "").split()).strip()
    if not compact:
        return ""
    # Skip machine-style graph dumps; renderer has better structured sections now.
    if compact.lower().startswith("element '") and "children=[" in compact and "attributes={" in compact:
        return ""
    return compact


def _extract_example_shape_request(question: str) -> bool:
    return bool(
        re.search(
            r"\b(examples?|samples?|snippets?|show me|xml examples?)\b",
            question or "",
            re.IGNORECASE,
        )
    )


def _fact_source_policy(
    *,
    answer_mode: str,
    tool_results_by_name: dict[str, dict[str, Any]],
) -> SourcePolicyDecision:
    if answer_mode == "grounded_dita_answer":
        return "dita_spec_first"
    if isinstance(tool_results_by_name.get("generate_native_pdf_config"), dict) and tool_results_by_name.get("generate_native_pdf_config"):
        return "native_pdf_first"
    tenant_result = tool_results_by_name.get("search_tenant_knowledge") or {}
    if isinstance(tenant_result, dict) and ((tenant_result.get("results") or []) or int(tenant_result.get("count") or 0) > 0):
        return "mixed_explicit"
    return "aem_guides_first"


_TENANT_AEM_QUERY_PATTERN = re.compile(
    r"\b(our|my|tenant|workspace|project|repository|repo|internal|client|customer|company|organization|"
    r"custom|customize|configured for us|in our setup|in our environment|in this environment|in this workspace|"
    r"connector|integration in our|how we use|how do we use)\b",
    re.IGNORECASE,
)
_GENERIC_RETRIEVAL_SUMMARY_PATTERN = re.compile(
    r"^\s*(found\s+\d+\s+(?:aem guides|documentation|docs?)\s+matches?|retrieved\s+\d+\s+matches?)\b",
    re.IGNORECASE,
)


def _should_include_tenant_knowledge_for_aem_query(question: str) -> bool:
    text = str(question or "").strip()
    if not text:
        return False
    return bool(_TENANT_AEM_QUERY_PATTERN.search(text))


def _filter_aem_guidance_results(question: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guidance_kind = _classify_aem_guidance_kind(question)
    lowered_question = str(question or "").lower()
    authoring_create = guidance_kind == "how_to" and "create" in lowered_question
    baseline_focus = bool(re.search(r"\bbaselines?\b", lowered_question))
    question_terms = {
        token
        for token in re.findall(r"[a-z0-9]{3,}", lowered_question)
        if token not in {"aem", "guides", "adobe", "experience", "manager"}
    }
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        combined = " ".join([title, url, snippet]).lower()
        score = 0.0
        score += sum(1 for token in question_terms if token in combined) / max(1, len(question_terms))

        if baseline_focus:
            if "baseline" in combined:
                score += 0.65
            if "/work-with-baseline/" in combined or "web-editor-baseline" in combined:
                score += 0.45
            if re.search(r"\b(manual update|automatic update|static baseline|dynamic baseline|date\s*:|label\s*:|labels\s*:)\b", combined):
                score += 0.45
            if re.search(r"\b(document states?|draft|approved|translated|published)\b", combined):
                score -= 1.25
            if re.search(r"\b(translation workflow|review task|workspace settings|component mapping|dita search|indexing)\b", combined):
                score -= 0.6
        elif authoring_create:
            if "/author-content/" in combined:
                score += 0.45
            if re.search(r"\b(create topics?|create (a )?map|map editor|work with the map editor|web editor)\b", combined):
                score += 0.35
            if re.search(r"\b(select create > dita map|create > dita topic|new file icon|repository panel|assets ui)\b", combined):
                score += 0.35
            if re.search(r"\b(repository panel|new file icon|new topic dialog box|create > dita topic)\b", combined):
                score += 0.45
            if re.search(r"\b(select create > dita map|new map dialog|blueprint page|map title)\b", combined):
                score += 0.45
            if re.search(r"\b(citations?|ditaval|reuse|content reuse|template|download files)\b", combined) and not re.search(r"\b(topic|map)\b", title.lower()):
                score -= 0.45
            if re.search(r"\b(know the editor features|download files|preview topics?|ditaval editor|citations?)\b", combined):
                score -= 0.75
            if re.search(r"\b(repository view:\s*new:|options menu)\b", combined):
                score -= 0.65
            if re.search(r"\b(allows you to create and edit map files|this topic walks you through)\b", combined):
                score -= 0.25
            if re.search(r"\b(properties page|context menu|metadata|schedule \(de\)activation|document state)\b", combined):
                score -= 0.75
            if "template" not in lowered_question and re.search(r"\b(custom(?:ized)? templates?|create dita template|topic template|map template)\b", combined):
                score -= 0.9
            if re.search(r"\b(output|publish|publishing|output preset|aem sites|incremental output)\b", combined):
                score -= 0.8
            if re.search(r"</?[a-z][a-z0-9:_-]*|<map\b|<topicref\b", snippet):
                score -= 0.8
        elif guidance_kind == "configuration":
            if "/install-conf-guide/" in combined:
                score += 0.4
            if re.search(r"\b(settings?|configure|configuration|profile|filter|workspace|indexing|mapping|search)\b", combined):
                score += 0.25
        elif guidance_kind == "troubleshooting":
            if re.search(r"\b(error|issue|problem|troubleshoot|not working|unable|cannot|can't|fails?)\b", combined):
                score += 0.3
        elif guidance_kind == "comparison":
            if re.search(r"\b(vs|versus|difference|different)\b", combined):
                score += 0.2

        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected: list[dict[str, Any]] = []
    seen_url_counts: dict[str, int] = {}
    seen_url_buckets: set[tuple[str, str]] = set()
    max_per_url = 2 if authoring_create else 1
    for _score, item in scored:
        url = str(item.get("url") or "").strip()
        bucket = _classify_aem_guidance_result_bucket(question, item)
        if bucket == "irrelevant":
            continue
        url_key = url or str(item.get("title") or "").strip()
        if not url_key:
            continue
        if (url_key, bucket) in seen_url_buckets:
            continue
        if seen_url_counts.get(url_key, 0) >= max_per_url:
            continue
        seen_url_counts[url_key] = seen_url_counts.get(url_key, 0) + 1
        seen_url_buckets.add((url_key, bucket))
        selected.append(item)
        if len(selected) >= 5:
            break
    return selected


def _classify_aem_guidance_result_bucket(question: str, item: dict[str, Any]) -> str:
    lowered_question = str(question or "").lower()
    combined = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("url") or ""),
            str(item.get("snippet") or ""),
        ]
    ).lower()
    if "baseline" in lowered_question:
        if "baseline" not in combined:
            return "irrelevant"
        if re.search(r"\b(document states?|draft|approved|translated|published|translation workflow)\b", combined):
            return "irrelevant"
        return "baseline"
    if _classify_aem_guidance_kind(question) == "how_to" and "create" in lowered_question:
        if re.search(r"\b(assets ui)\b", combined) and re.search(r"\b(create > dita topic|type of dita document|blueprint page)\b", combined):
            return "topic_assets_create"
        if re.search(r"\b(repository panel|new file icon|new topic dialog|new > topic|create > dita topic)\b", combined):
            return "topic_editor_create"
        if re.search(r"\b(create > dita map|new > dita map|new map dialog|map title|map template)\b", combined):
            return "map_create"
        if re.search(r"\b(map editor|create and edit map files|this topic walks you through)\b", combined):
            return "map_overview"
        if re.search(r"\b(ditaval|citation|download files|preview topics?|know the editor features|content reuse)\b", combined):
            return "irrelevant"
    return "general"


def _iter_aem_guidance_texts(aem: dict[str, Any], output_preset: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    question = str(aem.get("_question") or "").strip()
    filtered_aem_results = _filter_aem_guidance_results(question, list(aem.get("results") or [])) if question else list(aem.get("results") or [])[:5]
    filtered_output_results = _filter_aem_guidance_results(question, list(output_preset.get("doc_results") or [])) if question else list(output_preset.get("doc_results") or [])[:4]

    if not filtered_aem_results and not filtered_output_results:
        for candidate in (
            str(aem.get("summary") or "").strip(),
            str(output_preset.get("summary") or "").strip(),
        ):
            if candidate and not _GENERIC_RETRIEVAL_SUMMARY_PATTERN.match(candidate):
                texts.append(" ".join(candidate.split()))

    for item in filtered_aem_results[:6]:
        if not isinstance(item, dict):
            continue
        snippet = " ".join(str(item.get("snippet") or "").split()).strip()
        if snippet:
            texts.append(snippet)

    for item in filtered_output_results[:4]:
        if not isinstance(item, dict):
            continue
        snippet = " ".join(str(item.get("snippet") or "").split()).strip()
        if snippet:
            texts.append(snippet)

    for item in (output_preset.get("seed_results") or [])[:4]:
        if not isinstance(item, dict):
            continue
        snippet = " ".join(str(item.get("text_content") or "").split()).strip()
        if snippet:
            texts.append(snippet)
    return texts


def _is_aem_translation_workflow_question(question: str) -> bool:
    lowered = str(question or "").lower()
    return (
        "translation" in lowered
        and any(term in lowered for term in ("workflow", "how does", "how do", "steps", "process"))
    )


def _build_aem_translation_workflow_guidance(
    question: str,
    aem: dict[str, Any],
    output_preset: dict[str, Any],
) -> tuple[str, list[str]]:
    if not _is_aem_translation_workflow_question(question):
        return "", []

    texts = " \n ".join(_iter_aem_guidance_texts(aem, output_preset)).lower()
    if not texts:
        return "", []

    steps: list[str] = []
    if any(phrase in texts for phrase in ("configure translation service", "cloud services tab", "translation connector", "source language folder")):
        steps.append("Configure the translation service on the source language folder before starting localization.")
    if any(phrase in texts for phrase in ("translation project", "project folder you created for localization", "create project in adobe experience manager", "dita map console")):
        steps.append("Create or open the localization project from the DITA map-driven translation flow.")
    if any(phrase in texts for phrase in ("start the translation job", "translation job tile", "projects console", "start the translation workflow")):
        steps.append("Start the Translation Job from the localization project in the Projects console.")
    if any(phrase in texts for phrase in ("view the status of the translation job", "ellipsis at the bottom of the translation job tile", "translation job changes to ready to review", "ready to review")):
        steps.append("Monitor the Translation Job status and review the translated copy when the job reaches Ready to Review.")
    if any(phrase in texts for phrase in ("human translation service", "export the content for translation", "import it back into the translation project")):
        steps.append("For human translation, export the content for translation and import it back into the same translation project.")

    if len(steps) < 2:
        return "", []

    summary = (
        "In AEM Guides, the translation workflow is to "
        + "; then ".join(
            [
                steps[0].rstrip(".").lower(),
                *[step.rstrip(".").lower() for step in steps[1:]],
            ]
        )
        + "."
    )
    summary = summary[0].upper() + summary[1:]
    return summary, steps


def _is_aem_baseline_question(question: str) -> bool:
    return bool(re.search(r"\bbaselines?\b", str(question or "").lower()))


def _build_aem_baseline_type_guidance(
    question: str,
    aem: dict[str, Any],
    output_preset: dict[str, Any],
) -> tuple[str, list[str]]:
    if not _is_aem_baseline_question(question):
        return "", []

    texts = " \n ".join(_iter_aem_guidance_texts(aem, output_preset))
    lowered_text = texts.lower()
    if "baseline" not in lowered_text:
        return "", []

    actions: list[str] = []
    has_manual = bool(
        re.search(r"\bmanual update\b", lowered_text)
        or re.search(r"\b(static baseline|manually create a static baseline)\b", lowered_text)
    )
    has_auto = bool(
        re.search(r"\bautomatic update\b", lowered_text)
        or re.search(r"\b(dynamic baseline|updated dynamically)\b", lowered_text)
    )
    has_date = "date" in lowered_text and "baseline" in lowered_text
    has_label = "label" in lowered_text and "baseline" in lowered_text

    if has_manual:
        qualifier = " using a specific date/time or version label" if (has_date or has_label) else ""
        actions.append(f"Manual update baseline: creates a static baseline{qualifier}.")
    if has_auto:
        actions.append("Automatic update baseline: creates a dynamic baseline that picks topic versions from selected labels at use time.")
    if has_label and has_auto:
        actions.append("Label priority matters for automatic update: labels selected earlier take priority over later labels.")
    if has_label and has_manual:
        actions.append("For manual update, labels can be applied to direct and indirect references, with fallback handling for topics without the selected label.")

    if not actions:
        return "", []

    if has_manual and has_auto:
        summary = (
            "In AEM Guides, users can create two baseline configurations: "
            "Manual update static baselines and Automatic update dynamic baselines."
        )
    else:
        summary = "In AEM Guides, baseline configuration depends on the verified baseline options available in the Map console."
    return summary, actions[:4]


def _classify_aem_guidance_kind(question: str) -> str:
    lowered = str(question or "").lower()
    if re.search(r"\b(vs|versus|compare|difference|different)\b", lowered):
        return "comparison"
    if re.search(r"\b(error|issue|problem|problems|troubleshoot|troubleshooting|not working|fails?|failing|unable|cannot|can't|broken)\b", lowered):
        return "troubleshooting"
    if re.search(r"\b(configure|configuration|settings?|set up|setup|enable|disable|customi[sz]e|mapping|profile|filters?|workspace|preset|indexing|search)\b", lowered):
        return "configuration"
    if re.search(r"\b(how|steps?|workflow|create|open|start|publish|generate|review|use)\b", lowered):
        return "how_to"
    return "overview"


def _extract_aem_guidance_sentences(aem: dict[str, Any], output_preset: dict[str, Any]) -> list[str]:
    sentences: list[str] = []
    for text in _iter_aem_guidance_texts(aem, output_preset):
        cleaned_text = str(text or "")
        cleaned_text = re.sub(r"\{[^{}]*\}", " ", cleaned_text)
        cleaned_text = re.sub(r"[A-Za-z0-9 _-]+\|\s*Adobe Experience Manager", " ", cleaned_text)
        cleaned_text = re.sub(r"DocumentationAEM GuidesAEM Guides Documentation", " ", cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r"Last update:[^.]*", " ", cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r"CREATED FOR:\s*[A-Za-z ,/]+", " ", cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r"Topics:\s*[A-Za-z /&-]+", " ", cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r"\b(INFO|NOTE|TIP|IMPORTANT)\b", " ", cleaned_text)
        for raw in re.split(r"(?<=[.!?])\s+", cleaned_text):
            sentence = " ".join(str(raw or "").split()).strip()
            sentence = re.sub(
                r"^There are two ways to create topics in Experience Manager Guides:\s*",
                "",
                sentence,
                flags=re.IGNORECASE,
            )
            sentence = re.sub(
                r"^Create topics from the (Editor|Assets UI)\s+Perform the following steps to create a topic from the (Editor|Assets UI):\s*",
                "",
                sentence,
                flags=re.IGNORECASE,
            )
            sentence = re.sub(
                r"^Perform the following steps to create (a topic|a map|the topic|the map)( from the (Editor|Assets UI))?:\s*",
                "",
                sentence,
                flags=re.IGNORECASE,
            )
            action_match = re.search(
                r"\b(In the|From the|Open the|Open|Select|Choose|Navigate to|To create|You can create)\b",
                sentence,
                re.IGNORECASE,
            )
            if action_match and action_match.start() > 0:
                sentence = sentence[action_match.start():].strip()
            for anchor in (
                "In the Repository panel",
                "In the Assets UI",
                "To create a new topic, select Create > DITA Topic",
                "Select Create > DITA Map",
                "On the Blueprint page",
                "In the New topic dialog box",
                "In the New map dialog",
                "You can create these files using the Create > DITA Map workflow",
            ):
                anchor_index = sentence.lower().find(anchor.lower())
                if anchor_index > 0:
                    sentence = sentence[anchor_index:].strip()
                    break
            if not sentence:
                continue
            if len(sentence.split()) < 4 and ">" not in sentence:
                continue
            if _GENERIC_RETRIEVAL_SUMMARY_PATTERN.match(sentence):
                continue
            if re.match(r"^(note|tip|important)\b", sentence, re.IGNORECASE):
                continue
            if re.search(r"</?[A-Za-z][A-Za-z0-9:_-]*|<map\b|<topicref\b", sentence):
                continue
            if re.search(r"\b(last update:|created for:|documentationaem guides|topics:\s+[a-z])\b", sentence, re.IGNORECASE):
                continue
            if re.search(r"\brepository view:\s*new:\s*create a new dita topic, dita map, or a folder\b", sentence, re.IGNORECASE):
                continue
            if sentence not in sentences:
                sentences.append(sentence)
    return sentences


def _score_aem_guidance_sentence(question: str, sentence: str, guidance_kind: str) -> float:
    lowered_sentence = sentence.lower()
    lowered_question = str(question or "").lower()
    question_terms = [
        token
        for token in re.findall(r"[a-z0-9]{3,}", lowered_question)
        if token not in {"aem", "guides", "adobe", "experience", "manager"}
    ]
    overlap = sum(1 for token in question_terms if token in lowered_sentence) / max(1, len(question_terms))
    score = overlap

    if guidance_kind == "how_to":
        if re.search(r"\b(create|open|select|choose|configure|start|review|go to|navigate|use)\b", lowered_sentence):
            score += 0.35
        if re.search(r"\b(console|editor|map|topic|job|workflow|project|publish)\b", lowered_sentence):
            score += 0.15
        if re.search(r"\b(repository panel|explorer view|new file icon|create > dita topic|create > dita map|assets ui)\b", lowered_sentence):
            score += 0.22
        if re.search(r"\b(select new and choose topic|select create > dita map|new topic dialog|new map dialog|select topic from the dropdown)\b", lowered_sentence):
            score += 0.35
        if "create" in lowered_question and "create" in lowered_sentence:
            score += 0.32
        if "create" in lowered_question and lowered_sentence.startswith("open "):
            score -= 0.18
        if "map" in lowered_question and "map" in lowered_sentence:
            score += 0.12
        if "topic" in lowered_question and "topic" in lowered_sentence:
            score += 0.12
        if "create" in lowered_question and re.search(r"\b(output|publish|publishing|output preset|aem sites)\b", lowered_sentence):
            score -= 0.55
        if "template" not in lowered_question and "template" in lowered_sentence:
            score -= 0.28
        if re.search(
            r"\b(topic references?|topicref|chapter element|folder profile|organizational requirements|type column|global and folder profile)\b",
            lowered_sentence,
        ):
            score -= 0.45
        if re.search(r"\b(repository view:\s*new:|options menu|download as pdf|preview)\b", lowered_sentence):
            score -= 0.6
        if re.search(r"\b(you can create these files using|this topic walks you through|allows you to create and edit map files)\b", lowered_sentence):
            score -= 0.22
    elif guidance_kind == "configuration":
        if re.search(r"\b(configure|settings?|tab|panel|properties|profile|preset|mapping|filter|workspace|indexing|search)\b", lowered_sentence):
            score += 0.4
        if re.search(r"\b(open|select|go to|choose|set)\b", lowered_sentence):
            score += 0.12
        if "configure" in lowered_question and "configure" in lowered_sentence:
            score += 0.25
        if "settings" in lowered_question and "settings" in lowered_sentence:
            score += 0.18
    elif guidance_kind == "troubleshooting":
        if re.search(r"\b(ensure|must|must not|should not|permission|supported|not supported|cannot|can't|fails?|error)\b", lowered_sentence):
            score += 0.4
    elif guidance_kind == "comparison":
        if re.search(r"\b(vs|versus|compared|difference|different|instead of)\b", lowered_sentence):
            score += 0.35
    else:
        if re.search(r"\b(is|are|supports?|lets you|allows?|used for|enables?)\b", lowered_sentence):
            score += 0.18

    if re.search(r"\b(note|notes?)\b", lowered_sentence):
        score -= 0.08
    if _GENERIC_RETRIEVAL_SUMMARY_PATTERN.match(sentence):
        score -= 1.0
    return score


def _build_aem_guidance_settings(question: str, aem: dict[str, Any], output_preset: dict[str, Any]) -> list[str]:
    guidance_kind = _classify_aem_guidance_kind(question)
    if guidance_kind not in {"configuration", "how_to"}:
        return []

    text = " \n ".join(_iter_aem_guidance_texts(aem, output_preset)).lower()
    labels: list[str] = []
    known_locations = (
        ("cloud services tab", "Cloud Services tab"),
        ("folder properties", "Folder properties"),
        ("workspace settings", "Workspace settings"),
        ("projects console", "Projects console"),
        ("translation job tile", "Translation Job tile"),
        ("dita map console", "DITA map console"),
        ("output preset", "Output preset"),
        ("folder profile", "Folder profile"),
        ("document state", "Document states"),
        ("filter", "Filters"),
        ("component mapping", "Component mapping"),
        ("aem sites", "AEM Sites"),
        ("web editor", "Web Editor"),
        ("map console", "Map Console"),
        ("repository panel", "Repository panel"),
        ("assets ui", "Assets UI"),
        ("explorer view", "Explorer view"),
        ("baseline", "Baseline"),
        ("condition preset", "Condition preset"),
    )
    for needle, label in known_locations:
        if needle in text and label not in labels:
            labels.append(label)
    lowered_question = str(question or "").lower()
    if guidance_kind == "how_to" and "create" in lowered_question:
        labels = [label for label in labels if label in {"Repository panel", "Assets UI", "Web Editor", "Map Console", "Explorer view"}]
    return labels[:5]


def _build_aem_guidance_cautions(question: str, aem: dict[str, Any], output_preset: dict[str, Any]) -> list[str]:
    guidance_kind = _classify_aem_guidance_kind(question)
    if guidance_kind not in {"troubleshooting", "configuration", "how_to"}:
        return []

    cautions: list[tuple[float, str]] = []
    for sentence in _extract_aem_guidance_sentences(aem, output_preset):
        lowered = sentence.lower()
        if not re.search(r"\b(ensure|must|must not|should not|do not|permission|supported|not supported|cannot|can't)\b", lowered):
            continue
        if "create" in str(question or "").lower() and re.search(r"\b(template|folder profile|output preset|aem sites)\b", lowered):
            continue
        if "create" in str(question or "").lower() and re.search(
            r"\b(manually specify|ends with \.ditamap|ends with \.dita|uuid|file name is automatically suggested)\b",
            lowered,
        ):
            continue
        cautions.append((_score_aem_guidance_sentence(question, sentence, "troubleshooting"), sentence))
    cautions.sort(key=lambda item: item[0], reverse=True)

    deduped: list[str] = []
    for _score, sentence in cautions:
        if sentence not in deduped:
            deduped.append(sentence)
        if len(deduped) >= 3:
            break
    return deduped


def _compose_aem_guidance_summary(question: str, guidance_kind: str, actions: list[str]) -> str:
    if not actions:
        return ""
    cleaned_actions = [action.rstrip(".") for action in actions[:4]]
    if not cleaned_actions:
        return ""

    def _lowercase_initial(value: str) -> str:
        if not value:
            return value
        return value[:1].lower() + value[1:]

    lead_parts = [cleaned_actions[0]]
    lead_parts.extend(_lowercase_initial(action) for action in cleaned_actions[1:])
    lead = "; then ".join(lead_parts)
    if guidance_kind == "how_to":
        return f"In AEM Guides, the verified workflow is: {lead}."
    if guidance_kind == "configuration":
        return f"In AEM Guides, configure this with the following verified steps: {lead}."
    if guidance_kind == "troubleshooting":
        return f"In AEM Guides, the verified troubleshooting path is: {lead}."
    if guidance_kind == "comparison":
        return "; ".join(action.rstrip(".") for action in actions[:2])
    return actions[0]


def _select_best_aem_guidance_sentence(
    question: str,
    sentences: list[str],
    *,
    include_patterns: tuple[str, ...],
    exclude_patterns: tuple[str, ...] = (),
    used: set[str] | None = None,
) -> str:
    used = used or set()
    candidates: list[tuple[float, str]] = []
    for sentence in sentences:
        if sentence in used:
            continue
        lowered = sentence.lower()
        if include_patterns and not any(re.search(pattern, lowered) for pattern in include_patterns):
            continue
        if exclude_patterns and any(re.search(pattern, lowered) for pattern in exclude_patterns):
            continue
        score = _score_aem_guidance_sentence(question, sentence, "how_to")
        candidates.append((score, sentence))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _build_aem_create_authoring_actions(question: str, sentences: list[str]) -> list[str]:
    lowered_question = str(question or "").lower()
    if _classify_aem_guidance_kind(question) != "how_to" or "create" not in lowered_question:
        return []

    wants_topic = "topic" in lowered_question
    wants_map = "map" in lowered_question
    if not wants_topic and not wants_map:
        wants_topic = True
        wants_map = True

    actions: list[str] = []
    lowered_sentences = [sentence.lower() for sentence in sentences]

    has_map_create = any(re.search(r"\b(select create > dita map|new > dita map)\b", lowered) for lowered in lowered_sentences)
    if not has_map_create:
        has_map_create = any(re.search(r"\b(create map|select create map)\b", lowered) for lowered in lowered_sentences)
    has_map_setup = any(
        re.search(r"\b(blueprint page|new map dialog|map title|map template|file name|select next)\b", lowered)
        for lowered in lowered_sentences
    )
    has_topic_repo = any(
        re.search(r"\b(repository panel|new file icon|new > topic)\b", lowered)
        for lowered in lowered_sentences
    )
    has_topic_assets_nav = any(
        re.search(r"\bin the assets ui, navigate to the location where you want to create the topic\b", lowered)
        for lowered in lowered_sentences
    )
    has_topic_assets_create = any(
        re.search(r"\b(create > dita topic)\b", lowered)
        for lowered in lowered_sentences
    )
    has_topic_setup = any(
        re.search(r"\b(new topic dialog box|type of dita document|provide the following details|topic is created|opened in the editor|select next)\b", lowered)
        for lowered in lowered_sentences
    )

    if wants_map and has_map_create:
        actions.append("To create a map, select Create > DITA Map.")
    if wants_map and has_map_setup:
        actions.append("Choose the map template on the Blueprint page or in the New map dialog, then provide the map details and continue.")

    if wants_topic:
        if has_topic_repo and has_topic_assets_create and has_topic_assets_nav:
            actions.append(
                "To create a topic, either use the Repository panel New file icon and choose Topic, or in Assets UI navigate to the target folder and select Create > DITA Topic."
            )
        elif has_topic_repo:
            actions.append("To create a topic from the Editor, use the Repository panel New file icon and choose Topic.")
        elif has_topic_assets_create and has_topic_assets_nav:
            actions.append("To create a topic from Assets UI, navigate to the target folder and select Create > DITA Topic.")
        elif has_topic_assets_create:
            actions.append("To create a topic, select Create > DITA Topic.")

        if has_topic_setup:
            actions.append("Choose the DITA topic type, provide the topic details, and select Create to open it in the Editor.")

    return actions[:4]


def _build_aem_guidance_actions(
    question: str,
    aem: dict[str, Any],
    output_preset: dict[str, Any],
) -> list[str]:
    baseline_summary, baseline_actions = _build_aem_baseline_type_guidance(question, aem, output_preset)
    if baseline_summary and baseline_actions:
        return baseline_actions[:4]

    workflow_summary, workflow_steps = _build_aem_translation_workflow_guidance(question, aem, output_preset)
    if workflow_summary and workflow_steps:
        return workflow_steps[:5]

    guidance_kind = _classify_aem_guidance_kind(question)
    sentences = _extract_aem_guidance_sentences(aem, output_preset)
    authoring_create_actions = _build_aem_create_authoring_actions(question, sentences)
    if authoring_create_actions:
        return authoring_create_actions

    scored: list[tuple[float, str]] = []
    lowered_question = str(question or "").lower()
    for sentence in sentences:
        lowered_sentence = sentence.lower()
        if guidance_kind == "how_to" and "create" in lowered_question:
            if re.search(r"\b(output|publish|publishing|output preset|aem sites|generate article-based output)\b", lowered_sentence):
                continue
        score = _score_aem_guidance_sentence(question, sentence, guidance_kind)
        if score <= 0:
            continue
        scored.append((score, sentence))
    scored.sort(key=lambda item: item[0], reverse=True)

    deduped: list[str] = []
    if guidance_kind == "how_to":
        focus_terms = [
            term
            for term in ("topic", "map")
            if term in lowered_question
        ]
        for term in focus_terms:
            for _score, sentence in scored:
                lowered_sentence = sentence.lower()
                if term in lowered_sentence and sentence not in deduped:
                    deduped.append(sentence)
                    break

    for _score, sentence in scored:
        if sentence not in deduped:
            deduped.append(sentence)
        if len(deduped) >= 4:
            break

    if guidance_kind == "how_to" and "create" in lowered_question:
        def _create_priority(sentence: str) -> tuple[int, str]:
            lowered = sentence.lower()
            if "select create > dita map" in lowered or "create map" in lowered:
                return (0, lowered)
            if "create > dita topic" in lowered or "create a new topic" in lowered:
                return (1, lowered)
            if "select new" in lowered or "choose topic" in lowered:
                return (2, lowered)
            if lowered.startswith("open "):
                return (4, lowered)
            return (3, lowered)

        deduped = sorted(deduped, key=_create_priority)
    return deduped


def _select_aem_guidance_summary(
    question: str,
    aem: dict[str, Any],
    output_preset: dict[str, Any],
) -> str:
    baseline_summary, _baseline_actions = _build_aem_baseline_type_guidance(question, aem, output_preset)
    if baseline_summary:
        return baseline_summary

    workflow_summary, _workflow_steps = _build_aem_translation_workflow_guidance(question, aem, output_preset)
    if workflow_summary:
        return workflow_summary

    guidance_kind = _classify_aem_guidance_kind(question)
    composed_summary = _compose_aem_guidance_summary(
        question,
        guidance_kind,
        _build_aem_guidance_actions(question, aem, output_preset),
    )
    if composed_summary:
        return composed_summary

    def _score_candidate(text: str) -> float:
        lowered_text = text.lower()
        lowered_question = str(question or "").lower()
        question_terms = [token for token in re.findall(r"[a-z0-9]{3,}", lowered_question) if token not in {"guides", "adobe", "experience", "manager"}]
        matches = sum(1 for token in question_terms if token in lowered_text)
        score = matches / max(1, len(question_terms))
        workflow_question = any(term in lowered_question for term in ("workflow", "how does", "how do", "steps"))
        if "workflow" in lowered_question and "workflow" in lowered_text:
            score += 0.35
        if "translation" in lowered_question and "translation" in lowered_text:
            score += 0.2
        for phrase in (
            "translation job",
            "translation project",
            "ready to review",
            "start the translation job",
            "create a translation project",
            "review translated output",
            "review the translated output",
            "monitor the translation job",
        ):
            if phrase in lowered_text:
                score += 0.26 if workflow_question else 0.18
        if "permission" in lowered_text or "folder should not have more than" in lowered_text:
            score -= 0.25
        if workflow_question and any(phrase in lowered_text for phrase in ("must not be used", "should not be used", "ensure that the user")):
            score -= 0.28
        return score

    candidates: list[str] = []
    for text in _iter_aem_guidance_texts(aem, output_preset):
        snippet = _first_summary_sentence(text)
        if snippet:
            candidates.append(snippet)

    ranked = sorted(
        (candidate for candidate in candidates if candidate),
        key=_score_candidate,
        reverse=True,
    )
    return ranked[0] if ranked else ""


def _safe_verified_examples(
    *,
    question: str,
    answer_kind: GroundedAnswerKind,
    raw_examples: list[str],
    attr_name: str = "",
) -> tuple[list[VerifiedExampleSnippet], list[str]]:
    if not _extract_example_shape_request(question):
        return [], []
    warnings: list[str] = []
    examples: list[VerifiedExampleSnippet] = []
    attr_name = str(attr_name or "").strip().lower()
    for item in raw_examples[:4]:
        snippet = str(item or "").strip()
        lowered = snippet.lower()
        if not snippet:
            continue
        if answer_kind == "dita_map_construct":
            if not any(token in lowered for token in ("<map", "<topicref", "<keydef", "<mapref", "keyref=", "keyscope=", "processing-role=")):
                continue
        elif answer_kind.startswith("dita_"):
            if "<topic " in lowered and attr_name in _MAP_SCOPED_ATTR_NAMES:
                continue
            if "<" not in lowered and "@" not in lowered:
                continue
        examples.append(
            VerifiedExampleSnippet(
                label="Verified example",
                snippet=snippet,
                source="structured_tool",
                deterministic=False,
            )
        )
    if _extract_example_shape_request(question) and not examples:
        warnings.append("No verified snippet was available for this construct, so the answer omits example XML.")
    return examples, warnings


def _normalize_grounded_tool_facts(
    *,
    answer_mode: str,
    question: str,
    tool_results_by_name: dict[str, dict[str, Any]],
) -> NormalizedGroundedFactSet | None:
    source_policy = _fact_source_policy(answer_mode=answer_mode, tool_results_by_name=tool_results_by_name)
    common_warnings: list[str] = []
    for result in tool_results_by_name.values():
        if isinstance(result, dict):
            for warning in _tool_result_warnings(result):
                if warning not in common_warnings:
                    common_warnings.append(warning)

    if answer_mode == "grounded_dita_answer":
        attr = tool_results_by_name.get("lookup_dita_attribute") or {}
        spec = tool_results_by_name.get("lookup_dita_spec") or {}
        if (not isinstance(attr, dict) or attr.get("error")) and isinstance(spec, dict) and spec.get("attribute_name"):
            attr = spec

        if (
            _DITA_RELATED_LINKS_TOC_QUERY_PATTERN.search(question)
            and isinstance(spec, dict)
            and not spec.get("error")
        ):
            return NormalizedGroundedFactSet(
                answer_kind="dita_placement",
                source_policy=source_policy,
                canonical_definition=(
                    "No. By default, a <linklist>/<title> inside <related-links> is topic-local related-links "
                    "content, not a normal PDF TOC entry. The PDF TOC is driven by the map/topicref navigation "
                    "hierarchy; a rendered linklist title may appear as a heading in the topic's related-links "
                    "block, but that is not TOC generation."
                ),
                parent_elements=["related-links"],
                placement_notes=[
                    "Use map <topicref> titles or @navtitle for normal PDF TOC/navigation entries.",
                    "Use <related-links>/<linklist>/<title> to label a group of related links inside a topic.",
                    "A PDF transform may render that title in the related-links section, but it should not promote it into the TOC unless customized.",
                ],
                common_mistakes=[
                    "Treating topic-local related-link headings as map navigation entries.",
                    "Fixing Native PDF TOC styling when the underlying question is DITA structure and processor behavior.",
                ],
                semantic_warnings=common_warnings,
                thin_evidence=False,
                cross_source_mixed=False,
            )

        if (
            _is_dita_construct_output_query(question)
            and _DITA_FOREIGN_ELEMENT_QUERY_PATTERN.search(question)
            and isinstance(spec, dict)
            and not spec.get("error")
        ):
            return NormalizedGroundedFactSet(
                answer_kind="dita_output_behavior",
                source_policy=source_policy,
                canonical_definition=(
                    "The <foreign> element carries non-DITA vocabulary such as SVG, MathML, or custom XML. "
                    "In Web output it can be passed through when the transform and browser support that vocabulary; "
                    "in PDF output it is processor-dependent, so unsupported foreign content should have fallback or "
                    "be converted to a PDF-safe format."
                ),
                supported_elements=["foreign", "fallback"],
                usage_patterns=[
                    "Use <foreign> when you need to embed non-DITA XML inside topic content.",
                    "Use <fallback> inside <foreign> when portable output is required.",
                    "For stable PDF output, prefer a supported image/reference workflow when the PDF engine cannot render the embedded vocabulary.",
                ],
                default_behavior=[
                    "DITA defines <foreign> as a container for non-DITA content; it does not guarantee identical rendering across output formats.",
                    "Web/HTML output can preserve supported vocabularies such as inline SVG or MathML when the transform passes them through.",
                    "PDF output depends on the PDF transform and formatter; unsupported content can be ignored, rasterized externally, or replaced by fallback depending on the pipeline.",
                ],
                placement_notes=[
                    "Web output: verify that the HTML transform preserves the foreign namespace and that target browsers support it.",
                    "PDF output: verify the Native PDF or DITA-OT formatter behavior for the embedded vocabulary before relying on it.",
                    "Fallback: provide fallback content for readers/processors that cannot render the foreign vocabulary.",
                ],
                common_mistakes=[
                    "Assuming <foreign> itself forces SVG/MathML to render in every PDF processor.",
                    "Troubleshooting PDF styling before checking whether the DITA transform supports the embedded foreign vocabulary.",
                    "Omitting fallback content when the same topic must publish reliably to both Web and PDF.",
                ],
                semantic_warnings=common_warnings,
                thin_evidence=False,
                cross_source_mixed=False,
            )

        if isinstance(spec, dict) and not spec.get("error") and spec.get("query_type") == "element_comparison":
            rows: list[ComparisonRow] = []
            for item in (spec.get("comparisons") or [])[:4]:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("element_name") or item.get("label") or "").strip()
                if not label:
                    continue
                rows.append(
                    ComparisonRow(
                        label=label,
                        definition=_first_summary_sentence(
                            str(item.get("text_content") or item.get("summary") or "").strip()
                        ),
                        usage_patterns=_clean_grounded_strings(item.get("usage_contexts") or [], limit=2),
                        supported_elements=_clean_grounded_strings(item.get("parent_elements") or [], limit=8),
                        companion_attributes=_clean_grounded_strings(item.get("supported_attributes") or [], limit=8),
                        common_mistakes=_clean_grounded_strings(item.get("common_mistakes") or [], limit=2),
                    )
                )
            if rows:
                return NormalizedGroundedFactSet(
                    answer_kind="dita_element_comparison",
                    source_policy=source_policy,
                    canonical_definition=_first_summary_sentence(str(spec.get("summary") or "").strip())
                    or f"Compared DITA elements {', '.join(f'<{row.label}>' for row in rows[:4])}.",
                    comparison_rows=rows,
                    semantic_warnings=common_warnings,
                    thin_evidence=False,
                    cross_source_mixed=False,
                )

        if isinstance(spec, dict) and not spec.get("error") and spec.get("query_type") == "attribute_comparison":
            rows: list[ComparisonRow] = []
            raw_examples: list[str] = []
            for item in (spec.get("comparisons") or [])[:4]:
                if not isinstance(item, dict):
                    continue
                raw_examples.extend(_clean_grounded_strings(item.get("correct_examples") or [], limit=2))
                rows.append(
                    ComparisonRow(
                        label=str(item.get("attribute_name") or "").strip(),
                        definition=_first_summary_sentence(str(item.get("text_content") or "").strip()),
                        syntax=str(item.get("attribute_syntax") or _extract_attribute_syntax_line(str(item.get("text_content") or ""))).strip(),
                        usage_patterns=_clean_grounded_strings(item.get("usage_contexts") or [], limit=2),
                        supported_elements=_clean_grounded_strings(item.get("supported_elements") or [], limit=8),
                        companion_attributes=_clean_grounded_strings(item.get("combination_attributes") or [], limit=6),
                        common_mistakes=_clean_grounded_strings(item.get("common_mistakes") or [], limit=2),
                    )
                )
            if rows:
                examples, example_warnings = _safe_verified_examples(
                    question=question,
                    answer_kind="dita_attribute_comparison",
                    raw_examples=raw_examples,
                )
                return NormalizedGroundedFactSet(
                    answer_kind="dita_attribute_comparison",
                    source_policy=source_policy,
                    canonical_definition=_first_summary_sentence(str(spec.get("summary") or "").strip()),
                    comparison_rows=rows,
                    verified_examples=examples,
                    example_verified=bool(examples),
                    semantic_warnings=common_warnings + example_warnings,
                    thin_evidence=False,
                    cross_source_mixed=False,
                )

        if isinstance(attr, dict) and not attr.get("error") and attr.get("attribute_name"):
            attr_name = str(attr.get("attribute_name") or "").strip()
            semantic_class = str(attr.get("attribute_semantic_class") or "").strip().lower()
            answer_kind: GroundedAnswerKind = (
                "dita_map_construct"
                if semantic_class == "map_scoped" or attr_name.lower() in _MAP_SCOPED_ATTR_NAMES
                else "dita_attribute"
            )
            examples, example_warnings = _safe_verified_examples(
                question=question,
                answer_kind=answer_kind,
                raw_examples=_clean_grounded_strings(attr.get("correct_examples") or [], limit=3),
                attr_name=attr_name,
            )
            return NormalizedGroundedFactSet(
                answer_kind=answer_kind,
                source_policy=source_policy,
                canonical_definition=_first_summary_sentence(str(attr.get("text_content") or "").strip()),
                syntax=str(attr.get("attribute_syntax") or _extract_attribute_syntax_line(str(attr.get("text_content") or ""))).strip(),
                valid_values=_clean_grounded_strings(attr.get("all_valid_values") or [], limit=12),
                supported_elements=_clean_grounded_strings(attr.get("supported_elements") or [], limit=10),
                companion_attributes=_clean_grounded_strings(attr.get("combination_attributes") or [], limit=8),
                usage_patterns=_clean_grounded_strings(attr.get("usage_contexts") or [], limit=3),
                default_behavior=_clean_grounded_strings(attr.get("default_scenarios") or [], limit=3),
                common_mistakes=_clean_grounded_strings(attr.get("common_mistakes") or [], limit=3),
                verified_examples=examples,
                example_verified=bool(examples),
                semantic_warnings=common_warnings + example_warnings,
                thin_evidence=False,
                cross_source_mixed=False,
            )

        if isinstance(spec, dict) and not spec.get("error"):
            query_type = str(spec.get("query_type") or "").strip().lower()
            element_name = str(spec.get("element_name") or "").strip()
            element_name_lower = element_name.lower()
            allowed_children = _clean_grounded_strings(spec.get("allowed_children") or [], limit=12)
            parent_elements = _clean_grounded_strings(spec.get("parent_elements") or [], limit=12)
            supported_attributes = _clean_grounded_strings(spec.get("supported_attributes") or [], limit=12)
            usage_patterns = _clean_grounded_strings(spec.get("usage_contexts") or [], limit=3)
            common_mistakes = _clean_grounded_strings(spec.get("common_mistakes") or [], limit=3)
            notes: list[str] = []
            spec_chunk_texts = [
                " ".join(str(item.get("text_content") or "").split()).strip()
                for item in (spec.get("spec_chunks") or [])[:3]
                if isinstance(item, dict) and str(item.get("text_content") or "").strip()
            ]
            graph_knowledge = _clean_graph_knowledge_for_answer(str(spec.get("graph_knowledge") or ""))
            if graph_knowledge:
                notes.append(f"Resolution behavior: {graph_knowledge}")
            summary = _first_summary_sentence(
                str(
                    spec.get("content_model_summary")
                    or spec.get("placement_summary")
                    or spec.get("text_content")
                    or (spec_chunk_texts[0] if spec_chunk_texts else "")
                    or spec.get("summary")
                    or ""
                ).strip()
            )
            if query_type == "content_model" and (element_name or allowed_children):
                return NormalizedGroundedFactSet(
                    answer_kind="dita_content_model",
                    source_policy=source_policy,
                    canonical_definition=summary,
                    allowed_children=allowed_children,
                    parent_elements=parent_elements,
                    companion_attributes=supported_attributes,
                    usage_patterns=usage_patterns,
                    common_mistakes=common_mistakes,
                    placement_notes=notes,
                    semantic_warnings=common_warnings,
                )
            if query_type == "placement" and (element_name or parent_elements):
                return NormalizedGroundedFactSet(
                    answer_kind="dita_placement",
                    source_policy=source_policy,
                    canonical_definition=summary,
                    parent_elements=parent_elements,
                    companion_attributes=supported_attributes,
                    usage_patterns=usage_patterns,
                    common_mistakes=common_mistakes,
                    placement_notes=notes,
                    semantic_warnings=common_warnings,
                )
            if element_name_lower in _MAP_CONSTRUCT_ELEMENT_NAMES and (summary or element_name):
                return NormalizedGroundedFactSet(
                    answer_kind="dita_map_construct",
                    source_policy=source_policy,
                    canonical_definition=summary,
                    supported_elements=parent_elements,
                    allowed_children=allowed_children,
                    companion_attributes=supported_attributes,
                    usage_patterns=(usage_patterns or _summary_grounded_strings(spec_chunk_texts, limit=3)),
                    common_mistakes=common_mistakes,
                    placement_notes=notes,
                    semantic_warnings=common_warnings,
                )
            if summary or element_name:
                return NormalizedGroundedFactSet(
                    answer_kind="dita_element",
                    source_policy=source_policy,
                    canonical_definition=summary,
                    allowed_children=allowed_children,
                    parent_elements=parent_elements,
                    companion_attributes=supported_attributes,
                    usage_patterns=(_summary_grounded_strings(spec_chunk_texts, limit=3) or usage_patterns),
                    common_mistakes=common_mistakes,
                    placement_notes=notes,
                    semantic_warnings=common_warnings,
                )
        return None

    native_pdf = tool_results_by_name.get("generate_native_pdf_config") or {}
    output_preset = tool_results_by_name.get("lookup_output_preset") or {}
    aem = tool_results_by_name.get("lookup_aem_guides") or {}
    if isinstance(aem, dict) and question:
        aem = {**aem, "_question": question}
    tenant = tool_results_by_name.get("search_tenant_knowledge") or {}
    cross_source_mixed = bool(
        isinstance(tenant, dict)
        and (tenant.get("results") or tenant.get("count"))
        and ((isinstance(aem, dict) and (aem.get("results") or aem.get("count"))) or (isinstance(output_preset, dict) and (output_preset.get("doc_results") or output_preset.get("seed_results"))))
    )

    if isinstance(native_pdf, dict) and native_pdf and not native_pdf.get("error"):
        examples = [
            VerifiedExampleSnippet(label="Verified config snippet", snippet=str(item).strip(), source="native_pdf_tool")
            for item in _clean_grounded_strings(native_pdf.get("xml_or_css_snippets") or [], limit=2)
        ]
        warnings = list(common_warnings)
        if cross_source_mixed:
            warnings.append("Tenant knowledge was treated as secondary support after Native PDF guidance.")
        return NormalizedGroundedFactSet(
            answer_kind="native_pdf_guidance",
            source_policy=source_policy,
            canonical_definition=str(native_pdf.get("short_answer") or native_pdf.get("summary") or "").strip(),
            recommended_actions=_clean_grounded_strings(native_pdf.get("recommended_actions") or [], limit=4),
            relevant_settings=_clean_grounded_strings(native_pdf.get("relevant_settings") or [], limit=4),
            common_mistakes=_clean_grounded_strings(native_pdf.get("common_mistakes") or [], limit=3),
            verified_examples=examples,
            example_verified=bool(examples),
            semantic_warnings=warnings,
            cross_source_mixed=cross_source_mixed,
        )

    recommended_actions = _build_aem_guidance_actions(question, aem, output_preset)
    summary = _select_aem_guidance_summary(question, aem, output_preset)
    if recommended_actions or summary:
        warnings = list(common_warnings)
        if cross_source_mixed:
            warnings.append("Tenant knowledge was blended only as secondary context after product guidance.")
        return NormalizedGroundedFactSet(
            answer_kind="aem_guides_guidance",
            source_policy=source_policy,
            guidance_kind=_classify_aem_guidance_kind(question),
            canonical_definition=summary,
            recommended_actions=recommended_actions[:4],
            relevant_settings=_build_aem_guidance_settings(question, aem, output_preset),
            common_mistakes=_build_aem_guidance_cautions(question, aem, output_preset),
            semantic_warnings=warnings,
            cross_source_mixed=cross_source_mixed,
        )
    return None


def _render_normalized_grounded_fact_set(facts: NormalizedGroundedFactSet) -> str:
    short_answer = " ".join(str(facts.canonical_definition or "").split()).strip()
    if not short_answer:
        return ""

    sections: list[str] = ["## Short answer", short_answer]

    if facts.answer_kind in {"dita_attribute", "dita_map_construct"}:
        if facts.syntax:
            sections.extend(["", "## Syntax", f"- {facts.syntax}"])
        if facts.valid_values:
            sections.extend(["", "## Valid values", *[f"- `{value}`" for value in facts.valid_values[:12]]])
        if facts.supported_elements:
            title = "## Supported elements" if facts.answer_kind == "dita_attribute" else "## Where it applies"
            sections.extend(["", title, *[f"- `{element}`" for element in facts.supported_elements[:10]]])
        if facts.answer_kind == "dita_map_construct" and facts.allowed_children:
            sections.extend(["", "## What it can contain", *[f"- `{value}`" for value in facts.allowed_children[:12]]])
        if facts.companion_attributes:
            title = "## Common attributes" if facts.answer_kind == "dita_map_construct" else "## Companion attributes"
            sections.extend(["", title, *[f"- `{value}`" for value in facts.companion_attributes[:8]]])
        if facts.default_behavior:
            sections.extend(["", "## Default behavior", *[f"- {value}" for value in facts.default_behavior[:4]]])
        if facts.answer_kind == "dita_map_construct":
            resolution_points = []
            for value in [*facts.placement_notes[:4], *facts.usage_patterns[:4]]:
                if value and value not in resolution_points:
                    resolution_points.append(value)
            if resolution_points:
                sections.extend(["", "## Resolution behavior", *[f"- {value}" for value in resolution_points[:5]]])
        elif facts.usage_patterns:
            sections.extend(["", "## Typical usage", *[f"- {value}" for value in facts.usage_patterns[:4]]])
        if facts.common_mistakes:
            sections.extend(["", "## Common mistakes", *[f"- {value}" for value in facts.common_mistakes[:3]]])
    elif facts.answer_kind == "dita_content_model":
        if facts.allowed_children:
            sections.extend(["", "## Allowed children", *[f"- `{value}`" for value in facts.allowed_children[:12]]])
        if facts.parent_elements:
            sections.extend(["", "## Placement notes", *[f"- Can appear inside `{value}`" for value in facts.parent_elements[:10]]])
        if facts.companion_attributes:
            sections.extend(["", "## Common attributes", *[f"- `{value}`" for value in facts.companion_attributes[:10]]])
        if facts.common_mistakes:
            sections.extend(["", "## Common mistakes", *[f"- {value}" for value in facts.common_mistakes[:3]]])
    elif facts.answer_kind == "dita_placement":
        if facts.parent_elements:
            sections.extend(["", "## Valid parents", *[f"- `{value}`" for value in facts.parent_elements[:12]]])
        if facts.placement_notes:
            sections.extend(["", "## Placement notes", *[f"- {value}" for value in facts.placement_notes[:4]]])
        if facts.common_mistakes:
            sections.extend(["", "## Common mistakes", *[f"- {value}" for value in facts.common_mistakes[:3]]])
    elif facts.answer_kind == "dita_output_behavior":
        if facts.default_behavior:
            sections.extend(["", "## Output behavior", *[f"- {value}" for value in facts.default_behavior[:5]]])
        if facts.placement_notes:
            sections.extend(["", "## PDF vs Web guidance", *[f"- {value}" for value in facts.placement_notes[:5]]])
        if facts.usage_patterns:
            sections.extend(["", "## Recommended authoring pattern", *[f"- {value}" for value in facts.usage_patterns[:4]]])
        if facts.common_mistakes:
            sections.extend(["", "## Common mistakes", *[f"- {value}" for value in facts.common_mistakes[:3]]])
    elif facts.answer_kind == "dita_element":
        if facts.parent_elements:
            sections.extend(["", "## Where it appears", *[f"- Inside `{value}`" for value in facts.parent_elements[:10]]])
        if facts.allowed_children:
            sections.extend(["", "## What it can contain", *[f"- `{value}`" for value in facts.allowed_children[:12]]])
        if facts.companion_attributes:
            sections.extend(["", "## Common attributes", *[f"- `{value}`" for value in facts.companion_attributes[:10]]])
        resolution_points = []
        for value in [*facts.placement_notes[:3], *facts.usage_patterns[:4]]:
            if value and value not in resolution_points:
                resolution_points.append(value)
        if resolution_points:
            sections.extend(["", "## Typical usage", *[f"- {value}" for value in resolution_points[:5]]])
        if facts.common_mistakes:
            sections.extend(["", "## Common mistakes", *[f"- {value}" for value in facts.common_mistakes[:3]]])
    elif facts.answer_kind == "dita_attribute_comparison":
        sections.extend(["", "## Comparison"])
        for row in facts.comparison_rows[:4]:
            label = f"`{row.label}`"
            if row.definition:
                sections.append(f"- {label}: {row.definition}")
            else:
                sections.append(f"- {label}")
            if row.syntax:
                sections.append(f"- {label} syntax: {row.syntax}")
            if row.usage_patterns:
                sections.append(f"- {label} typical usage: {'; '.join(row.usage_patterns[:2])}")
            if row.supported_elements:
                sections.append(f"- {label} supported elements: {', '.join(row.supported_elements[:8])}")
        if not facts.comparison_rows:
            return ""
    elif facts.answer_kind == "dita_element_comparison":
        sections.extend(["", "## Comparison"])
        for row in facts.comparison_rows[:4]:
            label = f"`<{row.label}>`"
            if row.definition:
                sections.append(f"- {label}: {row.definition}")
            else:
                sections.append(f"- {label}")
            if row.supported_elements:
                sections.append(f"- {label} valid parents: {', '.join(f'`{value}`' for value in row.supported_elements[:8])}")
            if row.companion_attributes:
                sections.append(f"- {label} common attributes: {', '.join(f'`{value}`' for value in row.companion_attributes[:8])}")
            if row.usage_patterns:
                sections.append(f"- {label} typical usage: {'; '.join(row.usage_patterns[:2])}")
            if row.common_mistakes:
                sections.append(f"- {label} common mistake: {'; '.join(row.common_mistakes[:2])}")
        if not facts.comparison_rows:
            return ""
    elif facts.answer_kind == "native_pdf_guidance":
        if facts.recommended_actions:
            sections.extend(["", "## Recommended actions", *[f"- {value}" for value in facts.recommended_actions[:4]]])
        if facts.relevant_settings:
            sections.extend(["", "## Relevant settings", *[f"- {value}" for value in facts.relevant_settings[:4]]])
        if facts.common_mistakes:
            sections.extend(["", "## Common mistakes", *[f"- {value}" for value in facts.common_mistakes[:3]]])
    elif facts.answer_kind == "aem_guides_guidance":
        guidance_kind = str(facts.guidance_kind or "").strip().lower()
        if facts.recommended_actions:
            heading = "## Verified product guidance"
            if guidance_kind == "how_to":
                heading = "## Verified workflow"
            elif guidance_kind == "configuration":
                heading = "## Verified configuration steps"
            elif guidance_kind == "troubleshooting":
                heading = "## Verified fixes"
            elif guidance_kind == "comparison":
                heading = "## Verified differences"
            sections.extend(["", heading, *[f"- {value}" for value in facts.recommended_actions[:4]]])
        if facts.relevant_settings:
            settings_heading = "## Relevant settings" if guidance_kind == "configuration" else "## Relevant places in the UI"
            sections.extend(["", settings_heading, *[f"- {value}" for value in facts.relevant_settings[:5]]])
        if facts.common_mistakes:
            caution_heading = "## Likely causes" if guidance_kind == "troubleshooting" else "## Important notes"
            sections.extend(["", caution_heading, *[f"- {value}" for value in facts.common_mistakes[:3]]])
    else:
        if facts.usage_patterns:
            sections.extend(["", "## Verified details", *[f"- {value}" for value in facts.usage_patterns[:4]]])

    if facts.example_verified and facts.verified_examples:
        example_limit = 3 if facts.answer_kind in {"dita_attribute_comparison", "dita_element_comparison"} else 1
        heading = "## Verified XML examples" if example_limit > 1 else "## Verified example"
        sections.extend(["", heading])
        for item in facts.verified_examples[:example_limit]:
            sections.append(f"```xml\n{item.snippet}\n```")

    notes = []
    for item in facts.unsupported_points[:3]:
        if item not in notes:
            notes.append(item)
    for item in facts.semantic_warnings[:3]:
        if item not in notes:
            notes.append(item)
    if notes:
        sections.extend(["", "## Notes", *[f"- {value}" for value in notes]])

    return "\n".join(sections).strip()


def _build_grounded_tool_draft_answer(
    *,
    answer_mode: str,
    question: str,
    tool_results_by_name: dict[str, dict[str, Any]],
) -> tuple[str, NormalizedGroundedFactSet | None]:
    facts = _normalize_grounded_tool_facts(
        answer_mode=answer_mode,
        question=question,
        tool_results_by_name=tool_results_by_name,
    )
    if facts is None:
        return "", None
    return _render_normalized_grounded_fact_set(facts), facts


def _is_direct_jira_search_request(user_content: str) -> bool:
    text = (user_content or "").strip()
    if not text:
        return False
    if not _JIRA_SEARCH_PATTERN.search(text):
        return False
    return bool(extract_jira_search_query(text))


def _is_capability_prompt(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    patterns = [
        r"\bwhat can you do\b",
        r"\bhow can you help\b",
        r"\bwhat is your use\b",
        r"\bwhat are you for\b",
        r"\bhelp me use\b",
        r"\bhow do i use (this|you|ai chat)\b",
        r"\bwhat do you do\b",
        r"\bwho are you\b",
        r"^\s*help\s*$",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def _builtin_capability_response(tenant_id: str) -> str:
    return (
        "I can work in a few chat-first modes even without a live model reply:\n\n"
        "- Summarize Jira issues and comments into author-ready guidance.\n"
        "- Grounded answers for DITA, AEM Guides, keys, conref/conkeyref, maps, reltables, and reuse questions.\n"
        "- Multi-step research plans that look up AEM Guides docs, DITA spec details, tenant knowledge, and Jira matches before answering.\n"
        "- Approval-gated generation flows for DITA bundles, dataset jobs, and XML auto-fixes.\n"
        "- XML review flows that score pasted DITA, explain the issues, and pause before any fix is applied.\n"
        "- Jira search and comparison workflows that keep issue keys and results grounded in verified search output.\n"
        "- Dataset generation from chat with an in-thread progress card and ZIP download when the job completes.\n\n"
        f"Current workspace: `{tenant_id}`.\n\n"
        "Try one of these prompts:\n"
        "- Search Jira for issues about map validation and summarize the findings.\n"
        "- Review this DITA topic for conref, keyref, and keyword improvements, then pause before fixing it.\n"
        "- How do I fix broken keyrefs in a root map with multiple submaps?\n"
        "- Create a dataset with the parent_child_maps_keys_conref_conkeyref_selfrefs recipe.\n"
        "- Generate a DITA bundle from this Jira text, but show me the plan first.\n"
        "- Continue the last approved plan."
    )


def _builtin_unavailable_response(user_content: str, tenant_id: str) -> str:
    trimmed = (user_content or "").strip()
    if _is_capability_prompt(trimmed):
        return _builtin_capability_response(tenant_id)
    return (
        "Live AI responses are temporarily unavailable right now, but chat can still fall back to local indexed guidance.\n\n"
        "You can retry in a few minutes, or ask in a more directed way such as:\n"
        "- Summarize these Jira comments into author guidance.\n"
        "- Suggest conref, conkeyref, keyref, and keyword improvements for this XML.\n"
        "- Convert this issue into a task topic outline.\n"
        "- Review this draft for reuse and AEM Guides readiness.\n\n"
        f"Workspace: `{tenant_id}`"
    )


def _extract_issue_key(user_content: str, context: Optional[dict] = None) -> str:
    if isinstance(context, dict):
        candidate = str(context.get("issue_key") or "").strip()
        if candidate:
            return candidate
    match = re.search(r"\b[A-Z][A-Z0-9]+-\d+\b", user_content or "")
    return match.group(0) if match else ""


def _looks_like_dita_xml(text: str) -> bool:
    return bool(re.search(r"<(task|concept|reference|topic|glossentry)\b", text or "", re.IGNORECASE))


def _fallback_issue_stub(issue_key: str, context: Optional[dict] = None) -> dict:
    summary = ""
    if isinstance(context, dict):
        summary = str(context.get("issue_summary") or "").strip()
    return {
        "issue_key": issue_key,
        "summary": summary or issue_key or "Documentation issue",
        "description": "",
        "components": [],
        "labels": [],
        "comments": [],
        "attachments": [],
    }


def _extract_rag_highlights(rag_context: str, limit: int = 4) -> list[str]:
    if not rag_context:
        return []
    blocks = [block.strip() for block in rag_context.split("\n\n") if block.strip()]
    highlights: list[str] = []
    for block in blocks:
        if block.startswith("RELEVANT CONTEXT"):
            continue
        if block.startswith("Base your answer on this context"):
            continue
        if block.endswith(":") and "\n" not in block:
            continue
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].startswith("["):
            label = lines[0]
            detail = " ".join(lines[1:])
            if detail:
                highlights.append(f"{label}: {detail[:220]}")
            else:
                highlights.append(label[:220])
        else:
            highlights.append(" ".join(lines)[:220])
        if len(highlights) >= limit:
            break
    return highlights[:limit]


def _build_rag_grounded_fallback_response(
    user_content: str,
    rag_context: str,
    tenant_id: str,
    issue_key: str = "",
) -> str:
    highlights = _extract_rag_highlights(rag_context, limit=4)
    if not highlights:
        return _builtin_unavailable_response(user_content, tenant_id)

    lines = [
        "Using local indexed knowledge while live providers recover.",
        "",
    ]
    if issue_key:
        lines.append(f"Issue reference: `{issue_key}`")
        lines.append("")
    lines.append("Best available guidance:")
    for item in highlights:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "Good next prompts:",
            "- Review this XML for conref, conkeyref, keyref, and keyword improvements.",
            "- Turn this issue into a task topic outline with context, steps, and result.",
            "- Summarize the Jira discussion into user-facing author guidance.",
            f"",
            f"Workspace: `{tenant_id}`",
        ]
    )
    return "\n".join(lines).strip()


def _format_exposed_chat_error(exc: Exception) -> str:
    """User-visible error for chat: safe summary plus underlying provider message when present (no stack traces)."""
    base = format_llm_error_for_user(exc)
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        detail = str(cause).strip()
        if detail and detail.lower() not in base.lower():
            return f"{base}\n\nProvider error: {detail}"
    extra = str(exc).strip()
    if extra and extra != base and extra.lower() not in base.lower():
        return f"{base}\n\nDetail: {extra}"
    return base


def _llm_unavailable_configuration_message() -> str:
    if os.getenv("AI_USE_MOCK_LLM", "").lower() in ("true", "1", "yes"):
        return (
            "Live AI is disabled: AI_USE_MOCK_LLM is enabled. "
            "Set it to false or remove it, then restart the backend."
        )
    return (
        "Live AI is not configured or credentials are missing. "
        "In backend/.env set LLM_PROVIDER to anthropic, openai, groq, or bedrock and provide the matching "
        "credentials (ANTHROPIC_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, or AWS for Bedrock). "
        "Restart the backend after changes."
    )


def _append_provider_note(text: str, note: str) -> str:
    base = _coerce_llm_text_response(text).strip()
    extra = _coerce_llm_text_response(note).strip()
    if not extra:
        return base
    if not base:
        return extra
    if extra.lower() in base.lower():
        return base
    return f"{base}\n\nNote: {extra}"


def _build_issue_guidance_fallback(
    user_content: str,
    issue: dict,
    rag_context: str,
    tenant_id: str,
) -> str:
    lowered = (user_content or "").lower()
    issue_key = str(issue.get("issue_key") or "").strip()
    summary = str(issue.get("summary") or issue_key or "the issue").strip()
    highlights = _extract_rag_highlights(rag_context, limit=3)

    lines = ["Using local issue guidance while live providers recover.", ""]
    if issue_key:
        lines.append(f"Issue reference: `{issue_key}`")
    if summary and summary != issue_key:
        lines.append(f"Working summary: {summary}")
    lines.append("")

    if "outline" in lowered or "task topic" in lowered or "convert" in lowered:
        lines.extend(
            [
                "Task topic outline:",
                f"- Title: resolve the user-facing problem behind {summary}.",
                "- Shortdesc: describe the successful outcome for the author or reader.",
                "- Context: explain when the issue appears and why the task is needed.",
                "- Steps: verify the environment, apply the change, and confirm the expected behavior.",
                "- Result: describe the corrected behavior after the fix.",
            ]
        )
    else:
        lines.extend(
            [
                "Author guidance:",
                f"- Treat `{issue_key or summary}` as a user-facing documentation update, not a Jira bug report.",
                "- Pull the problem statement into context, then rewrite the resolution as clear procedural steps.",
                "- Keep the result focused on the corrected behavior rather than the ticket itself.",
            ]
        )

    if highlights:
        lines.append("")
        lines.append("Relevant indexed context:")
        for item in highlights:
            lines.append(f"- {item}")

    if "comment" in lowered or "discussion" in lowered:
        lines.append("")
        lines.append("If you paste the Jira comments or the draft XML next, I can give a more exact local review even while providers are busy.")

    lines.extend(["", f"Workspace: `{tenant_id}`"])
    return "\n".join(lines).strip()


async def _build_xml_review_fallback_response(
    xml: str,
    issue: dict,
    tenant_id: str,
    rag_context: str = "",
) -> str:
    from app.services.smart_suggestions_service import analyse_content

    report = await analyse_content(xml, issue, tenant_id=tenant_id)
    suggestions = report.suggestions[:4]
    lines = [
        "Using local XML analysis while live providers recover.",
        "",
        f"Detected topic type: `{issue.get('dita_type') or ('task' if '<task' in xml.lower() else 'topic')}`",
        f"Suggestions found: {report.total}",
    ]
    if suggestions:
        lines.append("")
        lines.append("Best next fixes:")
        for suggestion in suggestions:
            after = suggestion.after.strip()
            detail = f" {after}" if after else ""
            lines.append(f"- {suggestion.title}.{detail}")
    else:
        lines.append("")
        lines.append("This topic already looks structurally clean against the current local rule set.")

    if report.refine_completions:
        lines.append("")
        lines.append("Good follow-up asks:")
        for completion in report.refine_completions[:3]:
            lines.append(f"- {completion}")

    highlights = _extract_rag_highlights(rag_context, limit=2)
    if highlights:
        lines.append("")
        lines.append("Relevant indexed context:")
        for item in highlights:
            lines.append(f"- {item}")

    lines.extend(["", f"Workspace: `{tenant_id}`"])
    return "\n".join(lines).strip()


async def _build_local_fallback_response(
    user_content: str,
    tenant_id: str,
    context: Optional[dict] = None,
    *,
    rag_context: str | None = None,
) -> str:
    trimmed = (user_content or "").strip()
    if _is_capability_prompt(trimmed):
        return _builtin_capability_response(tenant_id)

    issue_key = _extract_issue_key(trimmed, context)
    issue = _fallback_issue_stub(issue_key, context)

    if rag_context is None:
        rag_context = _build_rag_context(trimmed[:500], tenant_id=tenant_id)

    if _looks_like_dita_xml(trimmed):
        if "<task" in trimmed.lower():
            issue["dita_type"] = "task"
        elif "<concept" in trimmed.lower():
            issue["dita_type"] = "concept"
        elif "<reference" in trimmed.lower():
            issue["dita_type"] = "reference"
        elif "<glossentry" in trimmed.lower():
            issue["dita_type"] = "glossentry"
        else:
            issue["dita_type"] = "topic"
        return await _build_xml_review_fallback_response(trimmed, issue, tenant_id, rag_context=rag_context or "")

    lowered = trimmed.lower()
    if issue_key and any(token in lowered for token in ("jira", "comment", "discussion", "outline", "task topic", "author guidance")):
        return _build_issue_guidance_fallback(trimmed, issue, rag_context or "", tenant_id)

    if rag_context:
        return _build_rag_grounded_fallback_response(trimmed, rag_context, tenant_id, issue_key=issue_key)

    return _builtin_unavailable_response(trimmed, tenant_id)


def _build_compact_chat_system_prompt(rag_context: str = "") -> str:
    """Compact system prompt for grounded chat — fits within Groq 12K TPM limit.

    Retains the key answer-quality rules from chat_system.json without the
    full 37K prompt.  Total size ~3-4K chars (~800-1000 tokens).
    """
    base = (
        "You are **DITA Dataset Studio Chat** — an expert assistant for DITA XML, "
        "AEM Guides, and technical documentation.\n\n"
        "# ANSWER RULES\n"
        "1. **Only include XML examples when the user asks for them or when a short verified snippet clearly helps.** "
        "Never guess XML structure.\n"
        "2. **Common mistakes**: If the evidence lists common mistakes for an element, "
        "include a ⚠️ Common Mistakes section.\n"
        "3. **Be specific**: Name parent/child elements, required attributes, content "
        "models. Never say 'various attributes' — list them.\n"
        "4. **Comparisons**: When comparing elements (e.g., choicetable vs simpletable "
        "vs table), use a markdown table with columns for each element.\n"
        "5. **Depth**: Give thorough, expert-level answers. A single paragraph is never "
        "enough for a structural DITA question.\n"
        "6. Use markdown formatting: headers (##), bullets, code blocks, bold for "
        "element names.\n"
        "7. When evidence is provided, ground your answer in it. When evidence is thin, "
        "stay narrow, say what is not verified, and do not fill gaps with confident guesses.\n"
        "8. Do not invent download URLs, product links, or claim features exist without "
        "evidence.\n\n"
        "# ANSWER STRUCTURE\n"
        "Use clear markdown sections. Choose the structure that fits the question:\n"
        "- **Definitional** (What is X?): Overview → Content model → Attributes → "
        "Example XML → Common mistakes\n"
        "- **Comparison** (X vs Y): Summary table → Detailed breakdown → When to use "
        "each → Example XML for each\n"
        "- **How-to** (How do I...?): Steps → Example XML → Tips / gotchas\n"
        "- **Troubleshooting**: Problem → Root cause → Fix → Corrected XML\n\n"
        "Do NOT use the rigid '## Short answer / ## How it works / ## What is verified' "
        "format. Use natural, helpful markdown sections instead."
    )
    if rag_context:
        base += f"\n\n# REFERENCE KNOWLEDGE\n{rag_context}"
    return base


def _build_grounded_answer_system_prompt(*, human_prompts: bool = False) -> str:
    """Legacy structured prompt — kept for heuristic fallback paths only."""
    return _build_compact_chat_system_prompt()


def _recent_chat_transcript(session_id: str, *, limit: int = 6) -> str:
    rows = get_messages(session_id, limit=limit)
    if not rows:
        return ""
    lines: list[str] = []
    for row in rows[-limit:]:
        role = str(row.get("role") or "").strip().lower()
        content = str(row.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        lines.append(f"{role.title()}: {content[:500]}")
    return "\n".join(lines[-limit:])


def _build_grounded_answer_user_prompt(
    *,
    question: str,
    evidence_context: str,
    transcript: str,
    corrected_query: str = "",
    correction_applied: bool = False,
) -> str:
    parts = [f"Question:\n{question}"]
    if transcript:
        parts.append(f"Recent conversation:\n{transcript}")
    if correction_applied and corrected_query:
        parts.append(f"Retrieval query used:\n{corrected_query}")
    parts.append(
        "Evidence:\n"
        f"{evidence_context}\n\n"
        "If the question asks what something is, base the definition and structure on the evidence above; "
        "quote or paraphrase only what is supported."
    )
    return "\n\n".join(parts)


def _stream_text_chunks(text: str) -> list[str]:
    cleaned = _coerce_llm_text_response(text).strip()
    if not cleaned:
        return []
    paragraphs = [part.strip() for part in cleaned.split("\n\n") if part.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= 500:
            chunks.append(paragraph + "\n\n")
            continue
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        current = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) > 500 and current:
                chunks.append(current + "\n\n")
                current = sentence
            else:
                current = candidate
        if current:
            chunks.append(current + "\n\n")
    return chunks or [cleaned]


async def _build_chat_evidence_pack(user_content: str, tenant_id: str) -> tuple[object, dict]:
    rag_result = await run_chat_corrective_rag(user_content, tenant_id=tenant_id)
    pack = build_evidence_pack(
        query=rag_result.corrected_query or user_content,
        tenant_id=tenant_id,
        candidates=rag_result.candidates,
    )
    retrieval = dict(rag_result.retrieval_summary or {})
    retrieval.update(
        {
            "corrected_query": rag_result.corrected_query,
            "correction_applied": rag_result.correction_applied,
            "strength": rag_result.assessment.strength,
            "reason": rag_result.assessment.reason,
        }
    )
    return pack, retrieval


def _persist_assistant_message(
    session_id: str,
    assistant_msg_id: str,
    content: str,
    *,
    tool_calls: object | None = None,
    tool_results: object | None = None,
) -> None:
    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            logger.warning_structured(
                "Skipping assistant message persistence because session was not found",
                extra_fields={"session_id": session_id, "assistant_msg_id": assistant_msg_id},
            )
            return
        db.add(
            ChatMessage(
                id=assistant_msg_id,
                session_id=session_id,
                role="assistant",
                content=content,
                tool_calls=json.dumps(tool_calls) if tool_calls else None,
                tool_results=json.dumps(tool_results) if tool_results else None,
                created_at=datetime.utcnow(),
            )
        )
        session.updated_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error_structured(
            "Failed to persist assistant message",
            extra_fields={"session_id": session_id, "assistant_msg_id": assistant_msg_id, "error": str(exc)},
            exc_info=True,
        )
    finally:
        db.close()


def _format_dita_chunk(chunk: dict, index: int, max_text_chars: int = 1000) -> str:
    """Format a DITA seed/spec chunk with all structured fields for the LLM."""
    name = chunk.get("element_name", "")
    text = (chunk.get("text_content") or "")[:max_text_chars]
    lines = [f"[{index}] {name}", text]

    attrs = chunk.get("attributes")
    if attrs and isinstance(attrs, (dict, str)):
        if isinstance(attrs, str):
            try:
                import json as _json
                attrs = _json.loads(attrs)
            except Exception:
                attrs = None
        if isinstance(attrs, dict) and attrs:
            attr_str = ", ".join(f"{k} ({v})" for k, v in attrs.items())
            lines.append(f"ATTRIBUTES: {attr_str}")

    mistakes = chunk.get("common_mistakes")
    if mistakes and isinstance(mistakes, list):
        lines.append("⚠️ COMMON MISTAKES:")
        for m in mistakes[:5]:
            lines.append(f"- {m}")

    examples = chunk.get("correct_examples")
    if examples and isinstance(examples, list):
        lines.append("✅ CORRECT EXAMPLES:")
        for ex in examples[:2]:
            lines.append(str(ex)[:400])

    contexts = chunk.get("usage_contexts")
    if contexts and isinstance(contexts, list):
        lines.append("USAGE CONTEXTS: " + "; ".join(str(c) for c in contexts[:4]))

    source_url = chunk.get("source_url")
    if source_url:
        lines.append(f"SOURCE: {source_url}")

    return "\n".join(lines)


def _build_rag_context(query: str, tenant_id: str = "kone") -> str:
    """Retrieve RAG chunks and format for system prompt. Uses more chunks for better retrieval."""
    if not query or not str(query).strip():
        return ""

    parts = []

    # AEM Guides docs (increased k and snippet size for better retrieval)
    try:
        docs = retrieve_relevant_docs(
            query[:500],
            k=RAG_AEM_K,
            max_snippet_chars=RAG_SNIPPET_CHARS,
        )
        if docs:
            formatted = format_docs_for_prompt(docs)
            if formatted:
                parts.append("AEM GUIDES DOCUMENTATION:\n" + formatted)
    except Exception as e:
        logger.debug_structured("RAG AEM docs failed", extra_fields={"error": str(e)})

    # DITA spec
    try:
        dita_chunks = retrieve_dita_knowledge(query[:500], k=RAG_DITA_K)
        if dita_chunks:
            dita_parts = []
            for i, c in enumerate(dita_chunks[:RAG_DITA_K], 1):
                dita_parts.append(_format_dita_chunk(c, i, max_text_chars=RAG_SNIPPET_CHARS))
            if dita_parts:
                parts.append("DITA SPEC REFERENCE:\n" + "\n\n".join(dita_parts))
    except Exception as e:
        logger.debug_structured("RAG DITA failed", extra_fields={"error": str(e)})

    try:
        tenant_chunks = retrieve_tenant_context(query[:500], tenant_id=tenant_id, k=4)
        if tenant_chunks:
            tenant_parts = []
            for i, chunk in enumerate(tenant_chunks[:4], 1):
                metadata = chunk.get("metadata") or {}
                label = metadata.get("label") or metadata.get("filename") or "Tenant knowledge"
                content = (chunk.get("content") or "")[:RAG_SNIPPET_CHARS]
                if content:
                    tenant_parts.append(f"[{i}] {label}\n{content}")
            if tenant_parts:
                parts.append("TENANT KNOWLEDGE BASE:\n" + "\n\n".join(tenant_parts))
    except Exception as e:
        logger.debug_structured("RAG tenant context failed", extra_fields={"error": str(e), "tenant_id": tenant_id})

    try:
        example_chunks = retrieve_tenant_examples(query[:500], tenant_id=tenant_id, k=2)
        if example_chunks:
            example_parts = []
            for i, example in enumerate(example_chunks[:2], 1):
                label = example.get("filename") or f"Example {i}"
                content = (example.get("content") or "")[:RAG_SNIPPET_CHARS]
                if content:
                    example_parts.append(f"[{i}] {label}\n{content}")
            if example_parts:
                parts.append("APPROVED DITA EXAMPLES:\n" + "\n\n".join(example_parts))
    except Exception as e:
        logger.debug_structured("RAG tenant examples failed", extra_fields={"error": str(e), "tenant_id": tenant_id})

    # Claude Code / Adobe AI setup (when user asks about Claude, Bedrock, Adobe setup, etc.)
    try:
        claude_ctx = retrieve_claude_code_context(query[:500])
        if claude_ctx:
            parts.append("CLAUDE CODE / ADOBE AI SETUP:\n" + claude_ctx)
    except Exception as e:
        logger.debug_structured("RAG Claude Code failed", extra_fields={"error": str(e)})

    if not parts:
        return ""
    combined = "\n\n".join(parts)
    if len(combined) > RAG_CONTEXT_MAX_CHARS:
        combined = combined[:RAG_CONTEXT_MAX_CHARS] + "\n\n[truncated]"
    return (
        "\n\nRELEVANT CONTEXT (use when answering):\n"
        "Base your answer on this context. Do not invent information not present here. "
        "If the question is not covered, say so.\n\n"
        f"{combined}\n\n"
    )


def _filter_chat_sessions_query(query, *, user_id: str | None, tenant_id: str | None, is_admin: bool):
    if is_admin:
        if tenant_id:
            query = query.filter((ChatSession.tenant_id == tenant_id) | (ChatSession.tenant_id.is_(None)))
        return query
    if user_id:
        query = query.filter((ChatSession.user_id == user_id) | (ChatSession.user_id.is_(None)))
    if tenant_id:
        query = query.filter((ChatSession.tenant_id == tenant_id) | (ChatSession.tenant_id.is_(None)))
    return query


def _get_session_row(
    db,
    session_id: str,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
) -> ChatSession | None:
    query = db.query(ChatSession).filter(ChatSession.id == session_id)
    query = _filter_chat_sessions_query(query, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
    return query.first()


def create_session(*, user_id: str | None = None, tenant_id: str | None = None) -> str:
    """Create a new chat session. Returns session_id."""
    session_id = str(uuid4())
    db = SessionLocal()
    try:
        s = ChatSession(
            id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            title="New Chat",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(s)
        db.commit()
        return session_id
    finally:
        db.close()


def _serialize_session_row(session: ChatSession) -> dict:
    return {
        "id": session.id,
        "user_id": getattr(session, "user_id", None),
        "tenant_id": getattr(session, "tenant_id", None),
        "title": session.title or "New Chat",
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


def _serialize_message_row(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "tool_calls": json.loads(message.tool_calls) if message.tool_calls else None,
        "tool_results": json.loads(message.tool_results) if message.tool_results else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def list_sessions(
    limit: int = 50,
    offset: int = 0,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
) -> list[dict]:
    """List chat sessions, newest first."""
    db = SessionLocal()
    try:
        query = db.query(ChatSession)
        query = _filter_chat_sessions_query(query, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
        rows = (
            query
            .order_by(ChatSession.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_serialize_session_row(r) for r in rows]
    finally:
        db.close()


def get_session(
    session_id: str,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
) -> dict | None:
    """Get session by id. Returns None if not found."""
    db = SessionLocal()
    try:
        s = _get_session_row(db, session_id, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
        if not s:
            return None
        return _serialize_session_row(s)
    finally:
        db.close()


def get_messages(
    session_id: str,
    limit: int = 100,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
) -> list[dict]:
    """Get messages for a session."""
    db = SessionLocal()
    try:
        session_row = _get_session_row(db, session_id, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
        if not session_row:
            return []
        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
            .all()
        )
        return [_serialize_message_row(r) for r in rows]
    finally:
        db.close()


def branch_session_from_message(
    session_id: str,
    message_id: str,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
) -> tuple[dict, list[dict]]:
    """Create a new session by copying messages before a user message being edited."""
    db = SessionLocal()
    try:
        source_session = _get_session_row(db, session_id, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
        if not source_session:
            raise LookupError("Session not found")

        source_messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        target_index = next((index for index, row in enumerate(source_messages) if row.id == message_id), None)
        if target_index is None:
            raise LookupError("Message not found")

        target_message = source_messages[target_index]
        if target_message.role != "user":
            raise ValueError("Only user messages can be edited and resent")

        prefix_messages = source_messages[:target_index]
        now = datetime.utcnow()
        branched_session = ChatSession(
            id=str(uuid4()),
            user_id=getattr(source_session, "user_id", None),
            tenant_id=getattr(source_session, "tenant_id", None),
            # Always start edited branches as a fresh chat so the resent prompt can
            # become the visible title on the first new user message.
            title="New Chat",
            created_at=now,
            updated_at=now,
        )
        db.add(branched_session)
        db.flush()

        for index, row in enumerate(prefix_messages, start=1):
            db.add(
                ChatMessage(
                    id=str(uuid4()),
                    session_id=branched_session.id,
                    role=row.role,
                    content=row.content,
                    tool_calls=row.tool_calls,
                    tool_results=row.tool_results,
                    created_at=now + timedelta(microseconds=index),
                )
            )

        db.commit()
        db.refresh(branched_session)

        branched_messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == branched_session.id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        return _serialize_session_row(branched_session), [_serialize_message_row(row) for row in branched_messages]
    finally:
        db.close()


def delete_session(
    session_id: str,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
) -> bool:
    """Delete a session and its messages. Returns True if deleted."""
    db = SessionLocal()
    try:
        s = _get_session_row(db, session_id, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
        if not s:
            return False
        db.delete(s)
        db.commit()
        return True
    finally:
        db.close()


def get_old_chat_sessions(cutoff: datetime) -> list:
    """Return chat sessions not updated since cutoff (for retention cleanup)."""
    db = SessionLocal()
    try:
        return (
            db.query(ChatSession)
            .filter(ChatSession.updated_at < cutoff)
            .all()
        )
    finally:
        db.close()


def delete_old_chat_sessions(cutoff: datetime) -> int:
    """Delete chat sessions (and their messages via CASCADE) older than cutoff. Returns count deleted."""
    db = SessionLocal()
    try:
        deleted = db.query(ChatSession).filter(ChatSession.updated_at < cutoff).delete(synchronize_session=False)
        db.commit()
        return deleted
    finally:
        db.close()


def _messages_to_llm_format(messages: list[dict]) -> list[dict]:
    """Convert DB messages to LLM format (role + content)."""
    out = []
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


def _truncate_messages_for_context(messages: list[dict], max_messages: int = CHAT_CONTEXT_WINDOW_MESSAGES) -> list[dict]:
    """Sliding window: keep only the most recent messages to fit LLM context."""
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]


def _trim_session_if_over_limit(session_id: str) -> None:
    """If session has too many messages, delete oldest to stay under limit."""
    db = SessionLocal()
    try:
        count = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()
        if count < CHAT_MAX_MESSAGES_PER_SESSION:
            return
        to_remove = count - CHAT_MAX_MESSAGES_PER_SESSION + 1  # +1 for the message we're about to add
        if to_remove <= 0:
            return
        # Get oldest message IDs to delete
        oldest = (
            db.query(ChatMessage.id)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(to_remove)
            .all()
        )
        for (msg_id,) in oldest:
            db.query(ChatMessage).filter(ChatMessage.id == msg_id).delete(synchronize_session=False)
        db.commit()
        logger.debug_structured(
            "Trimmed chat session",
            extra_fields={"session_id": session_id, "removed": to_remove},
        )
    finally:
        db.close()


def get_session_last_generation(session_id: str) -> dict | None:
    """Return last DITA generation context for this session (for refinement)."""
    return _session_last_generation.get(session_id)


def set_session_last_generation(
    session_id: str,
    *,
    text: str,
    instructions: str | None,
    jira_id: str,
    run_id: str,
    download_url: str,
) -> None:
    """Store last generation so user can refine (e.g. 'add a concept topic')."""
    _session_last_generation[session_id] = {
        "text": text[:5000],
        "instructions": instructions,
        "jira_id": jira_id,
        "run_id": run_id,
        "download_url": download_url,
    }


def _update_session_title(session_id: str, title: str) -> None:
    """Update session title."""
    db = SessionLocal()
    try:
        s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if s:
            s.title = (title or "New Chat")[:500]
            s.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def update_session_title(
    session_id: str,
    title: str,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
) -> dict | None:
    """Update session title and return the serialized session."""
    db = SessionLocal()
    try:
        s = _get_session_row(db, session_id, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
        if not s:
            return None
        s.title = (title or "New Chat")[:500]
        s.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()
    return get_session(session_id, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)


def delete_all_chat_sessions(*, user_id: str | None = None, tenant_id: str | None = None, is_admin: bool = False) -> int:
    """Delete every chat session and message. Returns number of deleted sessions."""
    db = SessionLocal()
    try:
        query = db.query(ChatSession)
        query = _filter_chat_sessions_query(query, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
        rows = query.all()
        deleted = len(rows)
        if rows:
            ids = [row.id for row in rows]
            db.query(ChatMessage).filter(ChatMessage.session_id.in_(ids)).delete(synchronize_session=False)
            db.query(ChatSession).filter(ChatSession.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        return deleted
    finally:
        db.close()


def update_user_message_truncate_after(
    session_id: str,
    message_id: str,
    content: str,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
) -> list[dict]:
    """Edit a user message in place and remove all following messages."""
    trimmed = (content or "").strip()
    if not trimmed:
        raise ValueError("Message content cannot be empty")

    db = SessionLocal()
    try:
        session = _get_session_row(db, session_id, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
        if not session:
            raise LookupError("Session not found")

        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        target_index = next((index for index, row in enumerate(rows) if row.id == message_id), None)
        if target_index is None:
            raise LookupError("Message not found")

        target = rows[target_index]
        if target.role != "user":
            raise ValueError("Only user messages can be edited and resent")

        target.content = trimmed

        trailing_ids = [row.id for row in rows[target_index + 1 :]]
        if trailing_ids:
            (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id, ChatMessage.id.in_(trailing_ids))
                .delete(synchronize_session=False)
            )

        if target_index == 0:
            session.title = (trimmed[:80] + ("..." if len(trimmed) > 80 else "")) or "New Chat"
        session.updated_at = datetime.utcnow()
        db.commit()

        fresh = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        return [_serialize_message_row(row) for row in fresh]
    finally:
        db.close()


def pop_last_assistant_if_any(
    session_id: str,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
) -> bool:
    """Remove the last assistant message when present."""
    db = SessionLocal()
    try:
        session_row = _get_session_row(db, session_id, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
        if not session_row:
            return False
        last = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if not last or last.role != "assistant":
            return False
        db.delete(last)
        session = _get_session_row(db, session_id, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
        if session:
            session.updated_at = datetime.utcnow()
        db.commit()
        return True
    finally:
        db.close()


def get_last_user_message_content(
    session_id: str,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    is_admin: bool = False,
) -> str | None:
    """Return the most recent user message content for a session."""
    db = SessionLocal()
    try:
        session_row = _get_session_row(db, session_id, user_id=user_id, tenant_id=tenant_id, is_admin=is_admin)
        if not session_row:
            return None
        last = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role == "user")
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        text = (last.content or "").strip() if last else ""
        return text or None
    finally:
        db.close()


def get_last_user_message(session_id: str) -> dict | None:
    """Return the most recent user message as a serialized row."""
    db = SessionLocal()
    try:
        last = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role == "user")
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if not last:
            return None
        return _serialize_message_row(last)
    finally:
        db.close()


def _agent_non_reserved_tool_results(tool_results: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for key, value in (tool_results or {}).items():
        if key in {AGENT_PLAN_KEY, AGENT_EXECUTION_KEY, APPROVAL_STATE_KEY, "_grounding"}:
            continue
        if isinstance(value, dict):
            results[key] = copy.deepcopy(value)
    return results


def _agent_payload(
    *,
    plan: dict[str, Any],
    execution: dict[str, Any],
    approval_state: dict[str, Any] | None,
    tool_results_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return reserved_agent_payload(
        plan=plan,
        execution=execution,
        approval_state=approval_state,
        tool_results=tool_results_by_name,
    )


def _build_approval_state(plan: dict[str, Any], next_step: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(next_step.get("tool_name") or "tool")
    summary = str(next_step.get("summary") or next_step.get("title") or "").strip()
    gate_kind = str(next_step.get("gate_type") or "approval").strip().lower() or "approval"
    if gate_kind == "review":
        prompt = (
            f"Review the proposed `{tool_name}` bundle before generation."
            f"{f' {summary}' if summary else ''} Reply `approve` or `continue` when you want me to generate it."
        )
    else:
        prompt = (
            f"The next step will run `{tool_name}`."
            f"{f' {summary}' if summary else ''} Reply `approve` or `continue` to run it."
        )
    affected_artifacts: list[str] = []
    if tool_name == "create_job":
        recipe_type = str(((next_step.get("tool_input") or {}).get("recipe_type") or "")).strip()
        if recipe_type:
            affected_artifacts.append(f"Dataset job using recipe `{recipe_type}`")
        affected_artifacts.append("Dataset ZIP and job status card")
    elif tool_name == "generate_dita":
        preview = plan.get("preview") if isinstance(plan.get("preview"), dict) else {}
        expected_outputs = preview.get("expected_outputs") if isinstance(preview, dict) else None
        if isinstance(expected_outputs, list):
            affected_artifacts.extend(str(item).strip() for item in expected_outputs if str(item).strip())
        if not affected_artifacts:
            affected_artifacts.append("Generated DITA bundle and download action")
    elif tool_name == "fix_dita_xml":
        affected_artifacts.append("Fixed DITA XML output for the pasted content")
    return {
        "state": "required",
        "kind": gate_kind,
        "pending_step_id": next_step.get("id"),
        "pending_tool_name": tool_name,
        "prompt": prompt,
        "affected_artifacts": affected_artifacts,
        "allowed_responses": plan.get("resume_tokens") or ["approve", "continue"],
    }


def _tool_catalog_by_name() -> dict[str, dict[str, Any]]:
    return {str(tool["name"]): tool for tool in get_tool_catalog()}


def _tool_requires_review_first(tool_name: str) -> bool:
    tool = _tool_catalog_by_name().get(tool_name) or {}
    return bool(tool.get("review_first"))


def _build_generate_dita_preview_plan(
    *,
    user_request: str,
    text: str,
    instructions: str | None = None,
) -> dict[str, Any]:
    preview = build_generate_dita_preview(text=text, instructions=instructions)
    bundle_contract = build_generate_dita_execution_contract(preview=preview)
    preview_status = str(preview.get("status") or "").strip().lower()
    preview_ready = preview_status == "preview_ready"
    clarification_required = preview_status == "clarification_required" or bool(preview.get("clarification_needed"))
    title = "Generate DITA bundle"
    step_status = "pending" if preview_ready else "blocked"
    summary = str(preview.get("summary") or "Preview the DITA bundle before generation.").strip()
    plan_status = "unsupported" if preview_status == "unsupported" else ("proposed" if preview_ready else "clarification_required")
    resume_tokens = ["approve", "continue"] if preview_ready else []
    return {
        "goal": "Review the interpreted DITA bundle before generation",
        "mode": "generate_dita_preview",
        "user_request": user_request,
        "requires_approval": preview_ready,
        "expected_outputs": list(preview.get("expected_outputs") or []),
        "resume_tokens": resume_tokens,
        "status": plan_status,
        "preview": copy.deepcopy(preview),
        "generate_dita_request": {
            "text": text,
            "instructions": instructions,
            "bundle_contract": copy.deepcopy(bundle_contract),
        },
        "steps": [
            {
                "id": "generate_dita-step-1",
                "title": title,
                "tool_name": "generate_dita",
                "tool_input": {
                    "text": str(preview.get("execution_text") or text).strip(),
                    "instructions": preview.get("execution_instructions") or instructions,
                    "bundle_contract": copy.deepcopy(bundle_contract),
                },
                "approval_required": preview_ready,
                "gate_type": "review",
                "summary": summary,
                "note": str(preview.get("clarification_question") or "").strip() if clarification_required else "",
                "status": step_status,
            }
        ],
    }


def _refresh_generate_dita_plan_for_execution(plan: dict[str, Any]) -> dict[str, Any]:
    refreshed_plan = copy.deepcopy(plan)
    if str(refreshed_plan.get("mode") or "").strip() != "generate_dita_preview":
        return refreshed_plan

    preview = refreshed_plan.get("preview") if isinstance(refreshed_plan.get("preview"), dict) else {}
    request = (
        refreshed_plan.get("generate_dita_request")
        if isinstance(refreshed_plan.get("generate_dita_request"), dict)
        else {}
    )
    text = str(
        request.get("text")
        or preview.get("execution_text")
        or refreshed_plan.get("user_request")
        or ""
    ).strip()
    instructions = str(
        preview.get("execution_instructions")
        or request.get("instructions")
        or ""
    ).strip() or None
    bundle_contract = build_generate_dita_execution_contract(preview=preview)
    if bundle_contract is None:
        bundle_contract = copy.deepcopy(request.get("bundle_contract"))

    refreshed_plan["generate_dita_request"] = {
        "text": text,
        "instructions": instructions,
        "bundle_contract": copy.deepcopy(bundle_contract),
    }
    for step in refreshed_plan.get("steps") or []:
        if str(step.get("tool_name") or "").strip() != "generate_dita":
            continue
        step["tool_input"] = {
            "text": text,
            "instructions": instructions,
            "bundle_contract": copy.deepcopy(bundle_contract),
        }
    return refreshed_plan


def _merge_generate_dita_clarification_text(
    base_text: str,
    clarification: str,
    *,
    preview: dict[str, Any] | None = None,
) -> str:
    base = (base_text or "").strip()
    extra = (clarification or "").strip()
    if not extra:
        return base
    preview = preview or {}
    clarification_request = (
        preview.get("clarification_request")
        if isinstance(preview.get("clarification_request"), dict)
        else {}
    )
    missing_field = str(clarification_request.get("missing_field") or "").strip().lower()
    extra_lower = extra.lower()
    if missing_field == "constraint_conflict":
        conflict_items = preview.get("conflicts") if isinstance(preview.get("conflicts"), list) else []
        has_map_attribute_conflict = any(
            isinstance(item, dict)
            and str(item.get("kind") or "").strip().lower() == "attribute_family_conflict"
            and "@processing-role" in str(item.get("message") or "").lower()
            for item in conflict_items
        )
        if extra_lower == "map" and has_map_attribute_conflict:
            if re.search(r"\b(bookmap|ditamap|map)\b", base, re.IGNORECASE):
                return base
            return f"{base} with a DITA map".strip()
    if (
        str(preview.get("topic_family") or "").strip().lower() == "glossentry"
        and "about " not in base.lower()
        and " for " not in base.lower()
        and " on " not in base.lower()
    ):
        return f"{base} about {extra}".strip()
    return f"{base}\n{extra}".strip()


def _build_generate_dita_plan_from_clarification(
    clarification: str,
    state: dict[str, Any],
) -> dict[str, Any] | None:
    plan = copy.deepcopy(state.get("plan") or {})
    if str(plan.get("mode") or "").strip() != "generate_dita_preview":
        return None
    if str(plan.get("status") or "").strip() != "clarification_required":
        return None

    request = plan.get("generate_dita_request") if isinstance(plan.get("generate_dita_request"), dict) else {}
    base_text = str(request.get("text") or "").strip()
    base_instructions = request.get("instructions")
    preview = plan.get("preview") if isinstance(plan.get("preview"), dict) else {}
    merged_text = _merge_generate_dita_clarification_text(base_text, clarification, preview=preview)
    if not merged_text:
        return None
    return _build_generate_dita_preview_plan(
        user_request=(plan.get("user_request") or base_text or clarification),
        text=merged_text,
        instructions=base_instructions if isinstance(base_instructions, str) else None,
    )


def _find_pending_generate_dita_clarification_state(
    messages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    state = find_latest_agent_state(messages, pending_only=False)
    if not state:
        return None
    plan = state.get("plan") or {}
    if str(plan.get("mode") or "").strip() != "generate_dita_preview":
        return None
    if str(plan.get("status") or "").strip() != "clarification_required":
        return None
    return state


def _build_tool_intent_plan(user_content: str, tool_intent: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(tool_intent.get("name") or "").strip()
    tool_args = copy.deepcopy(tool_intent.get("args") or {})
    if tool_name == "generate_dita":
        return _build_generate_dita_preview_plan(
            user_request=user_content,
            text=str(tool_args.get("text") or "").strip(),
            instructions=str(tool_args.get("instructions") or "").strip() or None,
        )
    catalog_tool = _tool_catalog_by_name().get(tool_name) or {}
    title = str(catalog_tool.get("title") or tool_name.replace("_", " ").title())
    description = str(catalog_tool.get("description") or "").strip()
    return {
        "goal": f"Run {title}",
        "mode": "slash_tool",
        "user_request": user_content,
        "requires_approval": tool_name in APPROVAL_REQUIRED_TOOLS,
        "expected_outputs": [title],
        "resume_tokens": ["approve", "continue", "skip fix"],
        "status": "pending",
        "steps": [
            {
                "id": f"{tool_name}-step-1",
                "title": title,
                "tool_name": tool_name,
                "tool_input": tool_args,
                "approval_required": tool_name in APPROVAL_REQUIRED_TOOLS,
                "summary": description or f"Run `{tool_name}` with the provided slash-command arguments.",
                "status": "pending",
            }
        ],
    }


def _build_direct_tool_response(name: str, result: dict[str, Any]) -> str:
    if result.get("error"):
        return f"I ran `/{name}`, but it failed: {result.get('error')}"
    if name == "generate_xml_flowchart":
        title = str(result.get("title") or "the XML")
        visible_nodes = int(result.get("visible_node_count") or result.get("node_count") or 0)
        total_nodes = int(result.get("total_node_count") or visible_nodes)
        omitted_nodes = int(result.get("omitted_node_count") or 0)
        has_svg_preview = bool(
            str(result.get("preview_svg_data_url") or "").strip()
            or str(result.get("preview_svg") or "").strip()
        )
        scope = (
            f"a scoped structure overview for {title} showing {visible_nodes} of {total_nodes} nodes"
            if omitted_nodes
            else f"a Mermaid flowchart for {title}"
        )
        if has_svg_preview:
            return f"I generated {scope} with an SVG preview. Use the result card below to preview, copy, or download it."
        return (
            f"I generated {scope}. This run did not include an SVG preview, "
            "so use the Mermaid source or rerun the tool to generate the rendered SVG."
        )
    if name == "generate_image":
        artifacts = result.get("artifacts") or []
        warning = str(result.get("warning") or "").strip()
        base = f"I generated {len(artifacts)} image artifact{'s' if len(artifacts) != 1 else ''} from your prompt."
        if warning:
            base += f" {warning}"
        return base
    if name == "list_indexed_pdfs":
        return str(result.get("message") or "I listed the indexed PDFs in your knowledge base.")
    if name == "list_jobs":
        total = result.get("total_count")
        return f"I listed your recent dataset jobs{f' ({total} found)' if total is not None else ''}."
    if name == "search_jira_issues":
        count = len(result.get("issues") or [])
        return f"I found {count} related Jira issue{'s' if count != 1 else ''} for that query."
    if name == "review_dita_xml":
        score = result.get("quality_score")
        dita_type = str(result.get("dita_type") or "DITA").strip()
        summary = str(result.get("review_summary") or result.get("summary") or "").strip()
        if not summary:
            summary = f"I reviewed the DITA XML{f' and scored it {score}' if score is not None else ''}."
        lines = ["## Review summary", summary]
        priority_fixes = [item for item in (result.get("priority_fixes") or []) if isinstance(item, dict)]
        if priority_fixes:
            lines.extend(["", "## What to improve first"])
            for item in priority_fixes[:5]:
                title = str(item.get("title") or item.get("recommendation") or "Improve DITA quality").strip()
                recommendation = str(item.get("recommendation") or "").strip()
                impact = str(item.get("impact") or item.get("reason") or "").strip()
                detail_parts = [part for part in (recommendation, impact) if part]
                lines.append(f"- **{title}**: {' '.join(detail_parts) if detail_parts else 'Review this finding in the card below.'}")
        guidance = str(result.get("score_improvement_guidance") or "").strip()
        if guidance:
            lines.extend(["", "## Score lift", guidance])
        lines.append("")
        lines.append(f"The review card below shows the {dita_type} checks, suggestions, and fix details.")
        return "\n".join(lines)
    if name == "browse_dataset":
        if result.get("file_path"):
            return f"I opened `{result.get('file_path')}` from the generated dataset."
        return "I loaded the dataset structure so you can inspect the generated files."
    title = str((_tool_catalog_by_name().get(name) or {}).get("title") or name.replace("_", " ").title())
    return f"I ran `/{name}` and included the result below."


def _condense_for_agent_prompt(value: Any, *, max_chars: int = 900) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value[:max_chars]
    if isinstance(value, list):
        return [_condense_for_agent_prompt(item, max_chars=max_chars) for item in value[:5]]
    if isinstance(value, dict):
        condensed: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 18:
                break
            condensed[key] = _condense_for_agent_prompt(item, max_chars=max_chars)
        return condensed
    return value


def _build_agent_evidence_prompt(tool_results_by_name: dict[str, dict[str, Any]]) -> str:
    sections: list[str] = []

    aem = tool_results_by_name.get("lookup_aem_guides") or {}
    aem_results = aem.get("results") or []
    if aem_results:
        lines = ["AEM GUIDES DOCUMENTATION:"]
        for index, item in enumerate(aem_results[:5], start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("url") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            lines.append(f"{index}. Title: {title}")
            if url:
                lines.append(f"   URL: {url}")
            if snippet:
                lines.append(f"   Snippet: {snippet[:900]}")
        sections.append("\n".join(lines))

    dita = tool_results_by_name.get("lookup_dita_spec") or {}
    dita_chunks = dita.get("spec_chunks") or []
    if dita_chunks or dita.get("graph_knowledge"):
        lines = ["DITA SPECIFICATION:"]
        for index, item in enumerate(dita_chunks[:5], start=1):
            if not isinstance(item, dict):
                continue
            element_name = str(item.get("element_name") or "").strip()
            text_content = str(item.get("text_content") or "").strip()
            lines.append(f"{index}. Element: {element_name or 'unknown'}")
            if text_content:
                lines.append(f"   Excerpt: {text_content[:900]}")
        graph_knowledge = str(dita.get("graph_knowledge") or "").strip()
        if graph_knowledge:
            lines.append(f"Graph knowledge: {graph_knowledge[:1200]}")
        sections.append("\n".join(lines))

    tenant = tool_results_by_name.get("search_tenant_knowledge") or {}
    tenant_results = tenant.get("results") or []
    if tenant_results:
        lines = ["TENANT KNOWLEDGE:"]
        for index, item in enumerate(tenant_results[:5], start=1):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("doc_type") or f"item-{index}").strip()
            doc_type = str(item.get("doc_type") or "").strip()
            content = str(item.get("content") or "").strip()
            lines.append(f"{index}. Label: {label}")
            if doc_type:
                lines.append(f"   Type: {doc_type}")
            if content:
                lines.append(f"   Content: {content[:900]}")
        sections.append("\n".join(lines))

    pdf = tool_results_by_name.get("generate_native_pdf_config") or {}
    doc_results = pdf.get("doc_results") or []
    if doc_results:
        lines = ["NATIVE PDF GUIDANCE:"]
        for index, item in enumerate(doc_results[:5], start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("url") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            lines.append(f"{index}. Title: {title}")
            if url:
                lines.append(f"   URL: {url}")
            if snippet:
                lines.append(f"   Snippet: {snippet[:900]}")
        sections.append("\n".join(lines))

    jira = tool_results_by_name.get("search_jira_issues") or {}
    jira_issues = jira.get("issues") or []
    if jira_issues:
        lines = ["JIRA MATCHES:"]
        for index, item in enumerate(jira_issues[:5], start=1):
            if not isinstance(item, dict):
                continue
            issue_key = str(item.get("issue_key") or "").strip()
            summary = str(item.get("summary") or "").strip()
            status = str(item.get("status") or "").strip()
            url = str(item.get("url") or "").strip()
            lines.append(f"{index}. {issue_key}: {summary}")
            if status:
                lines.append(f"   Status: {status}")
            if url:
                lines.append(f"   URL: {url}")
        sections.append("\n".join(lines))

    return "\n\n".join(section for section in sections if section).strip()


async def _synthesize_agent_answer(
    *,
    user_content: str,
    plan: dict[str, Any],
    tool_results_by_name: dict[str, dict[str, Any]],
) -> str:
    evidence_prompt = _build_agent_evidence_prompt(tool_results_by_name)
    if evidence_prompt and is_llm_available():
        system_prompt = (
            "You are an enterprise technical documentation assistant for AEM Guides and DITA.\n"
            "Answer using ONLY the evidence provided.\n"
            "Do not narrate the research plan or step completion status.\n"
            "If evidence is incomplete, say exactly what is not verified.\n"
            "Return markdown with exactly these sections in order:\n"
            "## Short answer\n"
            "## How it works\n"
            "## What is verified / what is not verified\n"
            "## Sources\n"
            "In 'How it works', give concrete bullets derived from the evidence.\n"
            "In 'Sources', list only the provided sources.\n"
            "Do not invent facts, URLs, product behavior, or citations."
        )
        user_prompt = (
            f"Question:\n{user_content}\n\n"
            f"Plan goal:\n{str(plan.get('goal') or '').strip()}\n\n"
            f"Evidence:\n{evidence_prompt}"
        )
        try:
            text = await generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1400,
                step_name="chat_agent_research_answer",
            )
            text = _coerce_llm_text_response(text).strip()
            if text:
                return text
        except Exception as exc:
            logger.warning_structured(
                "Agent answer synthesis fell back to local summary",
                extra_fields={"error": str(exc)},
            )
    return summarize_agent_results_locally(user_content, plan, tool_results_by_name)


async def _emit_streamed_text(text: str) -> AsyncGenerator[dict, None]:
    for chunk in _stream_text_chunks(text):
        yield {"type": "chunk", "content": chunk}


async def _stream_agent_command_reply(
    session_id: str,
    *,
    user_content: str,
    assistant_msg_id: str,
    command: dict[str, Any],
    user_id: str,
    tenant_id: str,
) -> AsyncGenerator[dict, None]:
    state = command.get("state") or {}
    plan = copy.deepcopy(state.get("plan") or {})
    execution = copy.deepcopy(state.get("execution") or execution_from_plan(plan))
    prior_tool_results = _agent_non_reserved_tool_results(state.get("tool_results") or {})

    if command.get("type") == "show_step":
        step_text = build_step_result_markdown(plan, prior_tool_results, int(command.get("step_number") or 1))
        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            step_text,
            tool_results=_agent_payload(
                plan=plan,
                execution=execution,
                approval_state=state.get("approval_state"),
                tool_results_by_name=prior_tool_results,
            ),
        )
        async for event in _emit_streamed_text(step_text):
            yield event
        yield {"type": "done"}
        return

    if command.get("type") == "skip_fix":
        next_step = next(
            (
                step
                for step in plan.get("steps") or []
                if step.get("status") == "pending" and step.get("tool_name") == "fix_dita_xml"
            ),
            None,
        )
        if next_step:
            mark_step_status(plan, str(next_step.get("id")), "skipped", note="User skipped the auto-fix.")
        plan["status"] = "completed"
        execution = execution_from_plan(plan, current_step_id=None)
        text = summarize_agent_results_locally(plan.get("user_request") or user_content, plan, prior_tool_results)
        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            text,
            tool_results=_agent_payload(
                plan=plan,
                execution=execution,
                approval_state={"state": "skipped", "pending_step_id": next_step.get("id") if next_step else ""},
                tool_results_by_name=prior_tool_results,
            ),
        )
        async for event in _emit_streamed_text(text):
            yield event
        yield {"type": "done"}
        return

    async for event in _stream_agent_plan_reply(
        session_id,
        user_content=plan.get("user_request") or state.get("message", {}).get("content") or user_content,
        assistant_msg_id=assistant_msg_id,
        user_id=user_id,
        tenant_id=tenant_id,
        plan=plan,
        existing_tool_results=prior_tool_results,
        approval_granted=True,
    ):
        yield event


async def _stream_agent_plan_reply(
    session_id: str,
    *,
    user_content: str,
    assistant_msg_id: str,
    user_id: str,
    tenant_id: str,
    plan: dict[str, Any],
    existing_tool_results: dict[str, dict[str, Any]] | None = None,
    approval_granted: bool = False,
) -> AsyncGenerator[dict, None]:
    working_plan = _refresh_generate_dita_plan_for_execution(plan)
    tool_results_by_name = copy.deepcopy(existing_tool_results or {})
    if not working_plan.get("steps"):
        fallback_text = await _build_local_fallback_response(user_content, tenant_id)
        _persist_assistant_message(session_id, assistant_msg_id, fallback_text)
        async for event in _emit_streamed_text(fallback_text):
            yield event
        yield {"type": "done"}
        return

    yield {"type": "plan", "plan": copy.deepcopy(working_plan)}
    if str(working_plan.get("status") or "").strip() == "clarification_required":
        execution = execution_from_plan(working_plan, current_step_id=None)
        text = build_plan_preview_markdown(working_plan)
        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            text,
            tool_results=_agent_payload(
                plan=working_plan,
                execution=execution,
                approval_state={"state": "clarification_required", "kind": "review"},
                tool_results_by_name=tool_results_by_name,
            ),
        )
        async for event in _emit_streamed_text(text):
            yield event
        yield {"type": "done"}
        return
    working_plan["status"] = "running"
    current_step_id: str | None = None

    for step in working_plan.get("steps") or []:
        status = str(step.get("status") or "pending")
        if status in {"completed", "skipped"}:
            continue
        if step.get("approval_required") and not approval_granted:
            working_plan["status"] = "awaiting_approval"
            approval_state = _build_approval_state(working_plan, step)
            execution = execution_from_plan(working_plan, current_step_id=current_step_id)
            yield {"type": "approval_required", "plan": copy.deepcopy(working_plan), "approval": copy.deepcopy(approval_state)}
            text = build_plan_preview_markdown(working_plan, approval_state=approval_state)
            _persist_assistant_message(
                session_id,
                assistant_msg_id,
                text,
                tool_results=_agent_payload(
                    plan=working_plan,
                    execution=execution,
                    approval_state=approval_state,
                    tool_results_by_name=tool_results_by_name,
                ),
            )
            async for event in _emit_streamed_text(text):
                yield event
            yield {"type": "done"}
            return

        step_id = str(step.get("id") or "")
        current_step_id = step_id or current_step_id
        mark_step_status(working_plan, step_id, "running")
        execution = execution_from_plan(working_plan, current_step_id=current_step_id)
        yield {"type": "step_status", "execution": copy.deepcopy(execution), "step": copy.deepcopy(step)}

        tool_name = str(step.get("tool_name") or "")
        run_id = str(uuid4()) if tool_name == "generate_dita" else None
        if run_id:
            yield {"type": "tool_start", "name": tool_name, "run_id": run_id}
        result = await run_tool(
            tool_name,
            step.get("tool_input") or {},
            user_id=user_id or "chat-user",
            session_id=session_id,
            run_id=run_id,
            tenant_id=tenant_id or "kone",
        )
        tool_results_by_name[tool_name] = result
        yield {"type": "tool", "name": tool_name, "result": result}

        error = str(result.get("error") or "").strip() if isinstance(result, dict) else ""
        if error:
            mark_step_status(working_plan, step_id, "failed", error=error)
            execution = execution_from_plan(working_plan, current_step_id=current_step_id)
            yield {"type": "step_status", "execution": copy.deepcopy(execution), "step": copy.deepcopy(step)}
            if tool_name in APPROVAL_REQUIRED_TOOLS or step.get("approval_required"):
                working_plan["status"] = "failed"
                failure_text = summarize_agent_results_locally(user_content, working_plan, tool_results_by_name)
                _persist_assistant_message(
                    session_id,
                    assistant_msg_id,
                    failure_text,
                    tool_results=_agent_payload(
                        plan=working_plan,
                        execution=execution,
                        approval_state={"state": "failed", "pending_step_id": step_id, "pending_tool_name": tool_name},
                        tool_results_by_name=tool_results_by_name,
                    ),
                )
                async for event in _emit_streamed_text(failure_text):
                    yield event
                yield {"type": "done"}
                return
            continue

        mark_step_status(working_plan, step_id, "completed")
        working_plan, followup_note = resolve_followup_after_step(working_plan, step_id, result)
        if followup_note:
            step["note"] = followup_note
        execution = execution_from_plan(working_plan, current_step_id=current_step_id)
        yield {"type": "step_status", "execution": copy.deepcopy(execution), "step": copy.deepcopy(step)}

        if working_plan.get("status") == "completed":
            break

    working_plan["status"] = working_plan.get("status") or "completed"
    if working_plan["status"] == "running":
        working_plan["status"] = "completed"
    execution = execution_from_plan(working_plan, current_step_id=None)
    final_text = await _synthesize_agent_answer(
        user_content=user_content,
        plan=working_plan,
        tool_results_by_name=tool_results_by_name,
    )
    _persist_assistant_message(
        session_id,
        assistant_msg_id,
        final_text,
        tool_results=_agent_payload(
            plan=working_plan,
            execution=execution,
            approval_state={"state": "completed"},
            tool_results_by_name=tool_results_by_name,
        ),
    )
    async for event in _emit_streamed_text(final_text):
        yield event
    yield {"type": "done"}


async def _build_grounded_dita_answer_payload(
    *,
    question: str,
    session_id: str,
    user_id: str,
    tenant_id: str,
    trace_id: str,
    context: Optional[dict] = None,
) -> tuple[str, dict[str, Any]]:
    evidence_pack = None
    retrieval_meta: dict[str, object] = {}
    grounded_tool_results: dict[str, dict[str, Any]] = {}
    start_llm_trace(trace_id)
    try:
        evidence_pack, retrieval_meta, grounded_tool_results = await _build_grounded_tool_evidence_pack(
            answer_mode="grounded_dita_answer",
            user_content=question,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        if evidence_pack is None:
            evidence_pack, retrieval_meta = await _build_chat_evidence_pack(question, tenant_id)
        if evidence_pack is None:
            raise ValueError("No evidence pack could be built for the DITA answer segment")

        transcript = _recent_chat_transcript(session_id)
        draft_answer, normalized_grounded_facts = _build_grounded_tool_draft_answer(
            answer_mode="grounded_dita_answer",
            question=question,
            tool_results_by_name=grounded_tool_results,
        )
        grounding_path = "tool_only"
        if not draft_answer and evidence_pack.decision.status not in {"abstain", "conflict"} and is_llm_available():
            dita_rag = ""
            if _should_include_structural_dita_rag(question):
                try:
                    dita_chunks = retrieve_dita_knowledge(question[:800], k=CHAT_GROUNDED_DITA_K)
                    if dita_chunks:
                        dita_parts = [
                            _format_dita_chunk(c, i, max_text_chars=400)
                            for i, c in enumerate(dita_chunks[:CHAT_GROUNDED_DITA_K], 1)
                        ]
                        dita_rag = "DITA SPEC REFERENCE:\n" + "\n\n".join(dita_parts)
                except Exception:
                    pass
            evidence_ctx = evidence_pack.build_prompt_context(
                max_chars=CHAT_GROUNDED_EVIDENCE_MAX_CHARS,
                limit=CHAT_GROUNDED_EVIDENCE_LIMIT,
            )
            if dita_rag:
                evidence_ctx = dita_rag + "\n\n" + evidence_ctx
            draft_answer = await generate_text(
                system_prompt=_build_compact_chat_system_prompt(rag_context=_build_rag_context(question, tenant_id=tenant_id)),
                user_prompt=_build_grounded_answer_user_prompt(
                    question=question,
                    evidence_context=evidence_ctx[:3000],
                    transcript=transcript,
                    corrected_query=str(retrieval_meta.get("corrected_query") or ""),
                    correction_applied=bool(retrieval_meta.get("correction_applied")),
                ),
                max_tokens=1600,
                step_name="chat_mixed_grounded_dita_answer",
                trace_id=trace_id,
            )
            grounding_path = "tool_plus_llm"

        grounded_answer = await verify_grounded_answer(
            question=question,
            draft_answer=draft_answer,
            evidence_pack=evidence_pack,
            verified_examples=(
                [item.to_dict() for item in (normalized_grounded_facts.verified_examples if normalized_grounded_facts else [])]
            ),
            structured_tool_answer=normalized_grounded_facts is not None,
        )
        llm_summary = summarize_llm_trace(
            trace_id,
            default_path=grounding_path,
            llm_used_path="tool_plus_llm",
        )
        grounding = grounding_metadata_from_pack(
            evidence_pack,
            grounded_answer,
            corrected_query=str(retrieval_meta.get("corrected_query") or ""),
            correction_applied=bool(retrieval_meta.get("correction_applied")),
            llm=llm_summary,
            answer_kind=normalized_grounded_facts.answer_kind if normalized_grounded_facts else "",
            source_policy=normalized_grounded_facts.source_policy if normalized_grounded_facts else "",
            example_verified=bool(normalized_grounded_facts.example_verified) if normalized_grounded_facts else False,
            semantic_warnings=list(normalized_grounded_facts.semantic_warnings) if normalized_grounded_facts else [],
            retrieval=_extract_aem_retrieval_metadata(grounded_tool_results),
        )
        clear_llm_trace(trace_id)
        return grounded_answer.answer, grounding
    except Exception as exc:
        logger.error_structured(
            "Mixed-intent grounded DITA answer failed",
            extra_fields={"session_id": session_id, "error": str(exc)},
            exc_info=True,
        )
        clear_llm_trace(trace_id)
        fallback_text = await _build_local_fallback_response(question, tenant_id, context)
        return _append_provider_note(fallback_text, _format_exposed_chat_error(exc)), {}


async def _stream_mixed_dita_answer_then_preview_reply(
    session_id: str,
    *,
    user_content: str,
    assistant_msg_id: str,
    user_id: str,
    tenant_id: str,
    route_contract: dict[str, Any],
    context: Optional[dict] = None,
) -> AsyncGenerator[dict, None]:
    answer_segment = str(route_contract.get("answer_segment") or route_contract.get("answer_intent") or user_content).strip()
    generation_segment = str(route_contract.get("generation_segment") or route_contract.get("generation_intent") or user_content).strip()
    intent_order = [str(item).strip().lower() for item in (route_contract.get("intent_order") or []) if str(item).strip()]

    plan = _build_generate_dita_preview_plan(
        user_request=user_content,
        text=generation_segment or user_content,
        instructions=None,
    )
    plan.setdefault("metadata", {})
    if isinstance(plan.get("metadata"), dict):
        plan["metadata"].update(
            {
                "mixed_intent": True,
                "answer_intent": answer_segment,
                "generation_intent": generation_segment,
                "intent_order": intent_order,
            }
        )

    answer_text = ""
    grounding: dict[str, Any] = {}
    answer_first = not intent_order or intent_order[0] == "answer"
    if answer_first:
        answer_text, grounding = await _build_grounded_dita_answer_payload(
            question=answer_segment or user_content,
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            trace_id=f"{assistant_msg_id}:mixed_answer",
            context=context,
        )
        if grounding:
            grounding["mixed_intent"] = True
            grounding["answer_intent"] = answer_segment
            yield {"type": "grounding", "grounding": grounding, "notice": grounding_to_notice(grounding)}

    yield {"type": "plan", "plan": copy.deepcopy(plan)}
    tool_results_by_name: dict[str, dict[str, Any]] = {}
    preview_status = str(plan.get("status") or "").strip().lower()
    approval_state: dict[str, Any] | None
    if preview_status == "clarification_required":
        approval_state = {"state": "clarification_required", "kind": "review"}
        execution = execution_from_plan(plan, current_step_id=None)
        plan_text = build_plan_preview_markdown(plan)
    else:
        pending_step = next((step for step in plan.get("steps") or [] if str(step.get("status") or "pending") == "pending"), None)
        if pending_step and pending_step.get("approval_required"):
            plan["status"] = "awaiting_approval"
            approval_state = _build_approval_state(plan, pending_step)
            execution = execution_from_plan(plan, current_step_id=None)
            yield {"type": "approval_required", "plan": copy.deepcopy(plan), "approval": copy.deepcopy(approval_state)}
            plan_text = build_plan_preview_markdown(plan, approval_state=approval_state)
        else:
            approval_state = None
            execution = execution_from_plan(plan, current_step_id=None)
            plan_text = build_plan_preview_markdown(plan)

    sections = []
    if answer_text:
        sections.append(answer_text.strip())
        sections.append("---")
        sections.append("## Generation preview")
    sections.append(plan_text.strip())
    final_text = "\n\n".join(section for section in sections if section)

    tool_results = _agent_payload(
        plan=plan,
        execution=execution,
        approval_state=approval_state,
        tool_results_by_name=tool_results_by_name,
    )
    if grounding:
        tool_results["_grounding"] = grounding
    tool_results["_mixed_intent"] = {
        "mixed_intent": True,
        "answer_intent": answer_segment,
        "generation_intent": generation_segment,
        "intent_order": intent_order,
        "generation_preview": copy.deepcopy(plan.get("preview") or {}),
    }
    _persist_assistant_message(session_id, assistant_msg_id, final_text, tool_results=tool_results)
    async for event in _emit_streamed_text(final_text):
        yield event
    yield {"type": "done"}


async def _stream_tool_intent_reply(
    session_id: str,
    *,
    user_content: str,
    assistant_msg_id: str,
    tool_intent: dict[str, Any],
    user_id: str,
    tenant_id: str,
) -> AsyncGenerator[dict, None]:
    tool_name = str(tool_intent.get("name") or "").strip()
    if not tool_name:
        yield {"type": "error", "message": "Tool intent is missing a tool name."}
        return

    if tool_name == "generate_dita":
        tool_args = copy.deepcopy(tool_intent.get("args") or {})
        preview = build_generate_dita_preview(
            text=str(tool_args.get("text") or "").strip(),
            instructions=str(tool_args.get("instructions") or "").strip() or None,
        )
        if str(preview.get("status") or "").strip().lower() == "unsupported":
            rejection_text = (
                str(preview.get("clarification_question") or "").strip()
                or str(preview.get("summary") or "").strip()
                or "I can generate DITA only in this flow."
            )
            _persist_assistant_message(session_id, assistant_msg_id, rejection_text)
            async for event in _emit_streamed_text(rejection_text):
                yield event
            yield {"type": "done"}
            return

    if tool_name in APPROVAL_REQUIRED_TOOLS or _tool_requires_review_first(tool_name):
        plan = _build_tool_intent_plan(user_content, tool_intent)
        async for event in _stream_agent_plan_reply(
            session_id,
            user_content=user_content,
            assistant_msg_id=assistant_msg_id,
            user_id=user_id,
            tenant_id=tenant_id,
            plan=plan,
        ):
            yield event
        return

    run_id = str(uuid4()) if tool_name == "generate_dita" else None
    if run_id:
        yield {"type": "tool_start", "name": tool_name, "run_id": run_id}

    result = await run_tool(
        tool_name,
        tool_intent.get("args") or {},
        user_id=user_id,
        session_id=session_id,
        run_id=run_id,
        tenant_id=tenant_id,
    )
    yield {"type": "tool", "name": tool_name, "result": result}
    text = _build_direct_tool_response(tool_name, result)
    _persist_assistant_message(
        session_id,
        assistant_msg_id,
        text,
        tool_results={tool_name: result},
    )
    async for event in _emit_streamed_text(text):
        yield event
    yield {"type": "done"}


async def _stream_attachment_authoring_reply(
    session_id: str,
    *,
    user_content: str,
    assistant_msg_id: str,
    user_id: str,
    tenant_id: str,
    attachments: list[ChatAttachmentRef],
    generation_options: ChatDitaGenerationOptions,
    context: Optional[dict] = None,
    human_prompts: bool = False,
    jira_context: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    del context, human_prompts
    service = get_chat_dita_authoring_service()
    authoring_trace_id = new_authoring_trace_id()
    stream_timer = AuthoringRunTimer()
    jira_clean = (jira_context or "").strip() or None
    effective_prompt = merge_jira_into_authoring_prompt(user_content, jira_clean)
    payload = ChatAuthoringRequestPayload(
        content=user_content,
        attachments=attachments,
        generation_options=generation_options,
        authoring_trace_id=authoring_trace_id,
        jira_context=jira_clean,
    )
    log_authoring_trace_started(
        authoring_trace_id=authoring_trace_id,
        session_id=session_id,
        user_id=user_id,
        tenant_id=tenant_id,
        attachments=attachments,
        generation_options=generation_options,
        user_prompt=user_content,
    )
    try:
        decision = await service.should_handle_request(
            user_prompt=effective_prompt,
            attachments=attachments,
            generation_options=generation_options,
        )
        if not decision.is_authoring_request:
            fallback = (
                "I received the attachment(s), but the request does not clearly ask me to generate a new DITA topic from them.\n\n"
                f"Reason: {decision.reason or 'The authoring intent was too ambiguous.'}\n\n"
                "Ask something like `generate a DITA task topic from this screenshot` and I’ll run the staged authoring pipeline."
            )
            _persist_assistant_message(
                session_id,
                assistant_msg_id,
                fallback,
                tool_results={
                    "generate_dita_from_attachments": {
                        "status": "error",
                        "title": "",
                        "dita_type": generation_options.dita_type or "topic",
                        "xml_preview": "",
                        "validation_result": {"valid": False, "structural_issues": []},
                        "saved_asset_path": None,
                        "artifact_url": None,
                        "actions": [],
                        "message": fallback,
                        "debug": {
                            "authoring_trace_id": authoring_trace_id,
                            "classification_reason": decision.reason,
                            "classification_confidence": decision.confidence,
                        },
                    }
                },
            )
            log_authoring_intent_rejected(
                authoring_trace_id=authoring_trace_id,
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                reason=decision.reason or "",
                confidence=float(decision.confidence),
            )
            async for event in _emit_streamed_text(fallback):
                yield event
            yield {"type": "done"}
            return

        result_model = await service.generate_topic_from_request(
            payload=payload,
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        result = result_model.model_dump(mode="json")
        text = _build_authoring_assistant_text(result)
        yield {"type": "tool", "name": "generate_dita_from_attachments", "result": result}
        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            text,
            tool_results={"generate_dita_from_attachments": result},
        )
        async for event in _emit_streamed_text(text):
            yield event
        yield {"type": "done"}
    except Exception as exc:
        logger.error_structured(
            "Attachment authoring flow failed",
            extra_fields={
                "session_id": session_id,
                "authoring_trace_id": authoring_trace_id,
                "error": str(exc),
            },
            exc_info=True,
        )
        log_authoring_trace_failed(
            authoring_trace_id=authoring_trace_id,
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            error_stage="attachment_authoring_stream",
            error_message_redacted=str(exc),
            duration_ms=stream_timer.elapsed_ms(),
        )
        fallback = f"DITA generation from the attachment failed: {format_llm_error_for_user(exc)}"
        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            fallback,
            tool_results={
                "generate_dita_from_attachments": {
                    "status": "error",
                    "title": "",
                    "dita_type": generation_options.dita_type or "topic",
                    "xml_preview": "",
                    "validation_result": {"valid": False, "structural_issues": []},
                    "saved_asset_path": None,
                    "artifact_url": None,
                    "actions": [],
                    "message": fallback,
                    "debug": {"authoring_trace_id": authoring_trace_id},
                }
            },
        )
        async for event in _emit_streamed_text(fallback):
            yield event
        yield {"type": "done"}


async def _stream_assistant_reply(
    session_id: str,
    *,
    user_content: str,
    assistant_msg_id: str,
    user_id: str = "chat-user",
    context: Optional[dict] = None,
    tenant_id: str = "kone",
    human_prompts: bool = False,
    tool_intent: Optional[dict[str, Any]] = None,
    attachments: Optional[list[ChatAttachmentRef]] = None,
    generation_options: Optional[ChatDitaGenerationOptions] = None,
    jira_context: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """Generate and persist an assistant reply for an existing last user message."""
    if attachments:
        async for event in _stream_attachment_authoring_reply(
            session_id,
            user_content=user_content,
            assistant_msg_id=assistant_msg_id,
            user_id=user_id,
            tenant_id=tenant_id,
            attachments=attachments,
            generation_options=generation_options or ChatDitaGenerationOptions(),
            context=context,
            human_prompts=human_prompts,
            jira_context=jira_context,
        ):
            yield event
        return

    route_decision = route_prompt(user_content, attachments_present=bool(attachments))
    policy_decision = decide_execution_policy(route_decision)
    answer_mode = (
        route_decision.legacy_answer_mode
        if str(route_decision.legacy_answer_mode or "").strip() not in {"", "default"}
        else _determine_answer_mode(user_content, session_id=session_id)
    )

    parsed_tool_intent = tool_intent or parse_tool_intent_from_content(user_content)
    if parsed_tool_intent:
        async for event in _stream_tool_intent_reply(
            session_id,
            user_content=user_content,
            assistant_msg_id=assistant_msg_id,
            tool_intent=parsed_tool_intent,
            user_id=user_id,
            tenant_id=tenant_id,
        ):
            yield event
        return

    history = get_messages(session_id, limit=200)
    clarification_state = _find_pending_generate_dita_clarification_state(history)
    if clarification_state:
        preview = (
            clarification_state.get("plan", {}).get("preview")
            if isinstance(clarification_state.get("plan"), dict)
            else {}
        )
        if _looks_like_generate_dita_acknowledgement(user_content):
            clarification_text = (
                str(preview.get("clarification_question") or "").strip()
                or "I still need one missing DITA generation detail before I can continue."
            )
            _persist_assistant_message(
                session_id,
                assistant_msg_id,
                clarification_text,
                tool_results=copy.deepcopy((clarification_state.get("message") or {}).get("tool_results") or {}),
            )
            async for event in _emit_streamed_text(clarification_text):
                yield event
            yield {"type": "done"}
            return
        if _looks_like_generate_dita_clarification_response(user_content, preview=preview):
            resumed_plan = _build_generate_dita_plan_from_clarification(user_content, clarification_state)
            if resumed_plan:
                async for event in _stream_agent_plan_reply(
                    session_id,
                    user_content=str((resumed_plan.get("user_request") or user_content)),
                    assistant_msg_id=assistant_msg_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    plan=resumed_plan,
                ):
                    yield event
                return

    agent_command = detect_agent_command(user_content, history)
    if agent_command:
        async for event in _stream_agent_command_reply(
            session_id,
            user_content=user_content,
            assistant_msg_id=assistant_msg_id,
            command=agent_command,
            user_id=user_id,
            tenant_id=tenant_id,
        ):
            yield event
        return

    if policy_decision.action == "reject_as_unsupported":
        rejection_text = (
            policy_decision.clarification_question
            or "I can help with DITA questions, DITA generation, XML review, screenshots, and dataset jobs."
        )
        _persist_assistant_message(session_id, assistant_msg_id, rejection_text)
        async for event in _emit_streamed_text(rejection_text):
            yield event
        yield {"type": "done"}
        return

    if route_decision.intent == "dita_answer_then_generation" and policy_decision.action == "answer_then_preview":
        async for event in _stream_mixed_dita_answer_then_preview_reply(
            session_id,
            user_content=user_content,
            assistant_msg_id=assistant_msg_id,
            user_id=user_id,
            tenant_id=tenant_id,
            route_contract=route_decision.candidate_contract or {},
            context=context,
        ):
            yield event
        return

    if route_decision.intent == "dita_generation" and policy_decision.action in {"preview_first", "clarify_first"}:
        contract = route_decision.candidate_contract or {}
        fresh_generate_dita_plan = _build_generate_dita_preview_plan(
            user_request=user_content,
            text=str(contract.get("text") or user_content).strip(),
            instructions=(str(contract.get("instructions") or "").strip() or None),
        )
        async for event in _stream_agent_plan_reply(
            session_id,
            user_content=user_content,
            assistant_msg_id=assistant_msg_id,
            user_id=user_id,
            tenant_id=tenant_id,
            plan=fresh_generate_dita_plan,
        ):
            yield event
        return

    agent_plan = build_agent_plan(user_content, tenant_id=tenant_id) if answer_mode == "agent_research_plan" else None
    if agent_plan:
        async for event in _stream_agent_plan_reply(
            session_id,
            user_content=user_content,
            assistant_msg_id=assistant_msg_id,
            user_id=user_id,
            tenant_id=tenant_id,
            plan=agent_plan,
        ):
            yield event
        return

    if _is_capability_prompt(user_content):
        fallback_text = _builtin_capability_response(tenant_id)
        _persist_assistant_message(session_id, assistant_msg_id, fallback_text)
        yield {"type": "chunk", "content": fallback_text}
        yield {"type": "done"}
        return

    if _is_direct_jira_search_request(user_content):
        async for event in _stream_direct_jira_search_reply(
            session_id,
            user_content=user_content,
            assistant_msg_id=assistant_msg_id,
            user_id=user_id,
            tenant_id=tenant_id,
        ):
            yield event
        return

    if answer_mode in {"generation_request", "xml_review_answer"}:
        async for event in _stream_tool_mode_reply(
            session_id,
            user_content=user_content,
            assistant_msg_id=assistant_msg_id,
            user_id=user_id,
            context=context,
            tenant_id=tenant_id,
            human_prompts=human_prompts,
        ):
            yield event
        return

    if not is_llm_available():
        fallback_text = await _build_local_fallback_response(
            user_content,
            tenant_id,
            context,
        )
        fallback_text = _append_provider_note(fallback_text, _llm_unavailable_configuration_message())
        _persist_assistant_message(session_id, assistant_msg_id, fallback_text)
        yield {"type": "chunk", "content": fallback_text}
        yield {"type": "done"}
        return

    evidence_pack = None
    retrieval_meta: dict[str, object] = {}
    grounded_tool_results: dict[str, dict[str, Any]] = {}
    start_llm_trace(assistant_msg_id)
    try:
        if answer_mode in {"grounded_dita_answer", "grounded_aem_answer"}:
            evidence_pack, retrieval_meta, grounded_tool_results = await _build_grounded_tool_evidence_pack(
                answer_mode=answer_mode,
                user_content=user_content,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
            )
        if evidence_pack is None:
            evidence_pack, retrieval_meta = await _build_chat_evidence_pack(user_content, tenant_id)
        if evidence_pack is None:
            raise ValueError("No evidence pack could be built for the chat question")

        # Always try to generate a draft answer via the LLM, even when
        # grounding evidence is weak/absent — the DITA seed + RAG context
        # and the LLM's own knowledge can still produce a useful response.
        transcript = _recent_chat_transcript(session_id)
        draft_answer, normalized_grounded_facts = _build_grounded_tool_draft_answer(
            answer_mode=answer_mode,
            question=user_content,
            tool_results_by_name=grounded_tool_results,
        )
        grounding_path = "tool_only"
        if not draft_answer and evidence_pack.decision.status not in {"abstain", "conflict"} and is_llm_available():
            # Only inject structural DITA chunks when the question is actually about DITA/XML structure.
            dita_rag = ""
            if _should_include_structural_dita_rag(user_content):
                try:
                    dita_chunks = retrieve_dita_knowledge(
                        user_content[:800],
                        k=CHAT_GROUNDED_DITA_K,
                    )
                    if dita_chunks:
                        dita_parts = [
                            _format_dita_chunk(c, i, max_text_chars=400)
                            for i, c in enumerate(dita_chunks[:CHAT_GROUNDED_DITA_K], 1)
                        ]
                        dita_rag = "DITA SPEC REFERENCE:\n" + "\n\n".join(dita_parts)
                except Exception:
                    pass
            evidence_ctx = evidence_pack.build_prompt_context(
                max_chars=CHAT_GROUNDED_EVIDENCE_MAX_CHARS,
                limit=CHAT_GROUNDED_EVIDENCE_LIMIT,
            )
            if dita_rag:
                evidence_ctx = dita_rag + "\n\n" + evidence_ctx
            rag_context = _build_rag_context(user_content, tenant_id=tenant_id)
            # Use compact prompt to stay within Groq 12K TPM limit.
            # The full chat_system.json (~10K tokens) exceeds the limit when
            # combined with evidence + DITA RAG + user message.
            system_prompt = _build_compact_chat_system_prompt(
                rag_context=rag_context,
            )
            draft_answer = await generate_text(
                system_prompt=system_prompt,
                user_prompt=_build_grounded_answer_user_prompt(
                    question=user_content,
                    evidence_context=evidence_ctx[:3000],
                    transcript=transcript,
                    corrected_query=str(retrieval_meta.get("corrected_query") or ""),
                    correction_applied=bool(retrieval_meta.get("correction_applied")),
                ),
                max_tokens=2400,
                step_name="chat_grounded_answer",
                trace_id=assistant_msg_id,
            )
            grounding_path = "tool_plus_llm"

        grounded_answer = await verify_grounded_answer(
            question=user_content,
            draft_answer=draft_answer,
            evidence_pack=evidence_pack,
            verified_examples=(
                [item.to_dict() for item in (normalized_grounded_facts.verified_examples if normalized_grounded_facts else [])]
            ),
            structured_tool_answer=normalized_grounded_facts is not None,
            )

        llm_summary = summarize_llm_trace(
            assistant_msg_id,
            default_path=grounding_path,
            llm_used_path="tool_plus_llm",
        )
        grounding = grounding_metadata_from_pack(
            evidence_pack,
            grounded_answer,
            corrected_query=str(retrieval_meta.get("corrected_query") or ""),
            correction_applied=bool(retrieval_meta.get("correction_applied")),
            llm=llm_summary,
            answer_kind=normalized_grounded_facts.answer_kind if normalized_grounded_facts else "",
            source_policy=normalized_grounded_facts.source_policy if normalized_grounded_facts else "",
            example_verified=bool(normalized_grounded_facts.example_verified) if normalized_grounded_facts else False,
            semantic_warnings=list(normalized_grounded_facts.semantic_warnings) if normalized_grounded_facts else [],
            retrieval=_extract_aem_retrieval_metadata(grounded_tool_results),
        )
        yield {"type": "grounding", "grounding": grounding, "notice": grounding_to_notice(grounding)}

        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            grounded_answer.answer,
            tool_results={"_grounding": grounding},
        )

        for chunk in _stream_text_chunks(grounded_answer.answer):
            yield {"type": "chunk", "content": chunk}
        yield {"type": "done"}
        clear_llm_trace(assistant_msg_id)
        return
    except Exception as e:
        logger.error_structured(
            "Grounded chat reply failed",
            extra_fields={"session_id": session_id, "error": str(e)},
            exc_info=True,
        )
        try:
            fallback_text = await _build_local_fallback_response(
                user_content,
                tenant_id,
                context,
            )
            fallback_text = _append_provider_note(fallback_text, _format_exposed_chat_error(e))
            _persist_assistant_message(session_id, assistant_msg_id, fallback_text)
            yield {"type": "chunk", "content": fallback_text}
            yield {"type": "done"}
            clear_llm_trace(assistant_msg_id)
            return
        except Exception as fallback_exc:
            logger.error_structured(
                "Chat fallback response failed",
                extra_fields={"session_id": session_id, "error": str(fallback_exc)},
                exc_info=True,
            )
        try:
            if evidence_pack is not None:
                llm_summary = summarize_llm_trace(
                    assistant_msg_id,
                    default_path="tool_only",
                    llm_used_path="tool_plus_llm",
                )
                grounded_answer = await verify_grounded_answer(
                    question=user_content,
                    draft_answer="",
                    evidence_pack=evidence_pack,
                )
                grounding = grounding_metadata_from_pack(
                    evidence_pack,
                    grounded_answer,
                    corrected_query=str(retrieval_meta.get("corrected_query") or ""),
                    correction_applied=bool(retrieval_meta.get("correction_applied")),
                    llm=llm_summary,
                    retrieval=_extract_aem_retrieval_metadata(grounded_tool_results),
                )
                fallback_text = grounded_answer.answer + "\n\n> Live provider response was unavailable, so this answer was narrowed to local verified evidence."
                yield {"type": "grounding", "grounding": grounding, "notice": grounding_to_notice(grounding)}
                _persist_assistant_message(
                    session_id,
                    assistant_msg_id,
                    fallback_text,
                    tool_results={"_grounding": grounding},
                )
                for chunk in _stream_text_chunks(fallback_text):
                    yield {"type": "chunk", "content": chunk}
                yield {"type": "done"}
                clear_llm_trace(assistant_msg_id)
                return
        except Exception:
            logger.debug_structured("Grounded fallback failed", extra_fields={"session_id": session_id})
        clear_llm_trace(assistant_msg_id)
        yield {"type": "error", "message": _format_exposed_chat_error(e)}


async def _stream_direct_jira_search_reply(
    session_id: str,
    *,
    user_content: str,
    assistant_msg_id: str,
    user_id: str = "chat-user",
    tenant_id: str = "kone",
) -> AsyncGenerator[dict, None]:
    result = await run_tool(
        "search_jira_issues",
        {"query": user_content},
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
    )
    yield {"type": "tool", "name": "search_jira_issues", "result": result}
    response_text = _build_post_tool_assistant_text({"search_jira_issues": result}) or str(result.get("message") or "").strip()
    if not response_text:
        response_text = "No verified Jira matches were found."
    _persist_assistant_message(
        session_id,
        assistant_msg_id,
        response_text,
        tool_results={"search_jira_issues": result},
    )
    yield {"type": "chunk", "content": response_text}
    yield {"type": "done"}


async def _stream_tool_mode_reply(
    session_id: str,
    *,
    user_content: str,
    assistant_msg_id: str,
    user_id: str = "chat-user",
    context: Optional[dict] = None,
    tenant_id: str = "kone",
    human_prompts: bool = False,
) -> AsyncGenerator[dict, None]:
    """Original tool-capable chat loop for generation and job actions."""
    rag_context = _build_rag_context(user_content, tenant_id=tenant_id)
    # Use compact prompt to stay within Groq 12K TPM limit
    system_prompt = _build_compact_chat_system_prompt(rag_context=rag_context)
    # Inject session context (previous generation download URL, refinement hints)
    context_block = _build_context_block(context, user_content, session_id=session_id)
    if context_block:
        system_prompt += context_block

    if not is_llm_available():
        fallback_text = await _build_local_fallback_response(
            user_content,
            tenant_id,
            context,
            rag_context=rag_context,
        )
        fallback_text = _append_provider_note(fallback_text, _llm_unavailable_configuration_message())
        _persist_assistant_message(session_id, assistant_msg_id, fallback_text)
        yield {"type": "chunk", "content": fallback_text}
        yield {"type": "done"}
        return

    history = get_messages(session_id)
    llm_messages = _messages_to_llm_format(history)

    if CHAT_CONTEXT_MAX_TOKENS:
        reserved_tokens = _approx_tokens(system_prompt)
        msg_budget = max(0, CHAT_CONTEXT_MAX_TOKENS - reserved_tokens)
        llm_messages = _truncate_messages_by_tokens(llm_messages, msg_budget)
    else:
        llm_messages = _truncate_messages_for_context(llm_messages)

    tools = get_tool_definitions()
    full_content: list[str] = []
    max_tool_rounds = 5
    total_input_tokens = 0
    total_output_tokens = 0
    tool_results_by_name: dict[str, dict] = {}
    tool_use_blocks = None

    try:
        for _ in range(max_tool_rounds):
            round_text: list[str] = []
            tool_use_blocks = None
            async for evt_type, data in generate_chat_stream_with_tools(
                system_prompt=system_prompt,
                messages=llm_messages,
                tools=tools,
                max_tokens=4096,
            ):
                if evt_type == "chunk":
                    round_text.append(data)
                    full_content.append(data)
                    yield {"type": "chunk", "content": data}
                elif evt_type == "usage":
                    total_input_tokens += (data.get("input_tokens") or 0)
                    total_output_tokens += (data.get("output_tokens") or 0)
                elif evt_type == "tool_use_blocks":
                    tool_use_blocks = data
                    break
                elif evt_type == "done":
                    break

            if tool_use_blocks:
                assistant_blocks = [{"type": "text", "text": "".join(round_text)}] if round_text else []
                for b in tool_use_blocks:
                    assistant_blocks.append(
                        {
                            "type": "tool_use",
                            "id": b["id"],
                            "name": b["name"],
                            "input": b["input"],
                        }
                    )
                llm_messages.append({"role": "assistant", "content": assistant_blocks})

                tool_results = []
                for b in tool_use_blocks:
                    run_id = str(uuid4()) if b["name"] == "generate_dita" else None
                    if run_id:
                        from app.api.v1.routes.ai_dataset import _update_generate_progress

                        _update_generate_progress(
                            run_id,
                            status="running",
                            stage="starting",
                            jira_id=f"TEXT-{run_id[:8]}",
                        )
                        yield {"type": "tool_start", "name": "generate_dita", "run_id": run_id}
                    result = await run_tool(
                        b["name"],
                        b.get("input") or {},
                        user_id=user_id,
                        session_id=session_id,
                        run_id=run_id,
                        tenant_id=tenant_id,
                    )
                    logger.info_structured(
                        "Chat tool invoked",
                        extra_fields={
                            "session_id": session_id,
                            "tool": b["name"],
                            "trace_id": assistant_msg_id,
                        },
                    )
                    tool_results.append(result)
                    tool_results_by_name[b["name"]] = result
                    yield {"type": "tool", "name": b["name"], "result": result}

                result_blocks = [
                    {"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(r)}
                    for b, r in zip(tool_use_blocks, tool_results)
                ]
                llm_messages.append({"role": "user", "content": result_blocks})
                direct_tool_response = _build_post_tool_assistant_text(tool_results_by_name)
                if direct_tool_response:
                    separator = "\n\n" if full_content else ""
                    full_content.append(separator + direct_tool_response)
                    yield {"type": "chunk", "content": separator + direct_tool_response}
                    break
            else:
                break

        full_text = "".join(full_content)
        if not full_text.strip():
            full_text = await _build_local_fallback_response(
                user_content,
                tenant_id,
                context,
                rag_context=rag_context,
            )

        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            full_text,
            tool_calls=tool_use_blocks,
            tool_results=tool_results_by_name,
        )

        if total_input_tokens > 0 or total_output_tokens > 0:
            try:
                await asyncio.to_thread(
                    store_chat_llm_run,
                    session_id,
                    total_input_tokens,
                    total_output_tokens,
                )
            except Exception as store_err:
                logger.warning_structured(
                    "Failed to store chat LLM usage",
                    extra_fields={"session_id": session_id, "error": str(store_err)},
                )

        yield {"type": "done"}
    except Exception as e:
        logger.error_structured(
            "Chat turn failed",
            extra_fields={"session_id": session_id, "error": str(e)},
            exc_info=True,
        )
        try:
            fallback_text = await _build_local_fallback_response(
                user_content,
                tenant_id,
                context,
                rag_context=rag_context,
            )
            fallback_text = _append_provider_note(fallback_text, _format_exposed_chat_error(e))
            _persist_assistant_message(session_id, assistant_msg_id, fallback_text)
            yield {"type": "chunk", "content": fallback_text}
            yield {"type": "done"}
            return
        except Exception as fallback_exc:
            logger.error_structured(
                "Chat fallback response failed",
                extra_fields={"session_id": session_id, "error": str(fallback_exc)},
                exc_info=True,
            )
        yield {"type": "error", "message": _format_exposed_chat_error(e)}


async def chat_turn(
    session_id: str,
    user_content: str,
    user_id: str = "chat-user",
    context: Optional[dict] = None,
    tenant_id: str = "kone",
    human_prompts: bool | None = None,
    tool_intent: Optional[dict[str, Any]] = None,
    attachments: Optional[list[ChatAttachmentRef]] = None,
    generation_options: Optional[ChatDitaGenerationOptions] = None,
    jira_context: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """
    Process a chat turn: persist user message, call LLM with RAG, stream response, persist assistant message.
    Yields dicts: {"type": "chunk", "content": "..."} | {"type": "done"} | {"type": "tool", "name": "...", "result": {...}} | {"type": "error", "message": "..."}
    """
    user_content = (user_content or "").strip()
    if not user_content:
        yield {"type": "error", "message": "Message cannot be empty"}
        return

    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            yield {"type": "error", "message": "Session not found"}
            return
    finally:
        db.close()

    # Trim session if over message limit (before adding new message)
    _trim_session_if_over_limit(session_id)

    # Persist user message
    user_msg_id = str(uuid4())
    user_tool_results: dict[str, Any] | None = None
    if attachments:
        resolved_generation_options = generation_options or ChatDitaGenerationOptions()
        user_tool_results = {
            "_attachments": [item.model_dump(mode="json") for item in attachments],
            "_generation_options": resolved_generation_options.model_dump(mode="json"),
        }
        jc = (jira_context or "").strip()
        if jc:
            user_tool_results["_jira_context"] = jc[: min(len(jc), 50000)]
    db = SessionLocal()
    try:
        db.add(
            ChatMessage(
                id=user_msg_id,
                session_id=session_id,
                role="user",
                content=user_content,
                tool_results=json.dumps(user_tool_results) if user_tool_results else None,
                created_at=datetime.utcnow(),
            )
        )
        # Update session updated_at
        s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if s:
            s.updated_at = datetime.utcnow()
            # Set title from first user message if still "New Chat"
            if (s.title or "") == "New Chat":
                s.title = (user_content[:80] + ("..." if len(user_content) > 80 else "")) or "New Chat"
        db.commit()
    finally:
        db.close()

    hp = bool(human_prompts) if human_prompts is not None else False
    async for event in _stream_assistant_reply(
        session_id,
        user_content=user_content,
        assistant_msg_id=str(uuid4()),
        user_id=user_id,
        context=context,
        tenant_id=tenant_id,
        human_prompts=hp,
        tool_intent=tool_intent,
        attachments=attachments,
        generation_options=generation_options,
        jira_context=jira_context,
    ):
        yield event


async def regenerate_last_assistant(
    session_id: str,
    user_id: str = "chat-user",
    context: Optional[dict] = None,
    tenant_id: str = "kone",
    human_prompts: bool | None = None,
    generation_options: Optional[ChatDitaGenerationOptions] = None,
) -> AsyncGenerator[dict, None]:
    """Remove the latest assistant reply and generate a fresh one for the last user message."""
    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            yield {"type": "error", "message": "Session not found"}
            return
    finally:
        db.close()

    pop_last_assistant_if_any(session_id)
    last_user_message = get_last_user_message(session_id)
    user_content = str((last_user_message or {}).get("content") or "").strip()
    if not user_content:
        yield {"type": "error", "message": "No user message found to regenerate from"}
        return

    tool_results = (last_user_message or {}).get("tool_results") or {}
    attachments_payload = tool_results.get("_attachments") if isinstance(tool_results, dict) else None
    generation_payload = tool_results.get("_generation_options") if isinstance(tool_results, dict) else None
    attachments = []
    for item in attachments_payload or []:
        if not isinstance(item, dict):
            continue
        try:
            attachments.append(ChatAttachmentRef.model_validate(item))
        except Exception:
            logger.warning_structured(
                "Skipping invalid persisted chat attachment metadata during regenerate",
                extra_fields={"session_id": session_id, "attachment": item},
            )
    persisted_generation_options: Optional[ChatDitaGenerationOptions] = None
    if isinstance(generation_payload, dict):
        try:
            persisted_generation_options = ChatDitaGenerationOptions.model_validate(generation_payload)
        except Exception:
            logger.warning_structured(
                "Skipping invalid persisted generation options during regenerate",
                extra_fields={"session_id": session_id, "generation_options": generation_payload},
            )

    effective_generation_options = (
        generation_options if generation_options is not None else persisted_generation_options
    )

    jira_ctx = None
    if isinstance(tool_results, dict):
        raw_jc = tool_results.get("_jira_context")
        if isinstance(raw_jc, str) and raw_jc.strip():
            jira_ctx = raw_jc.strip()

    hp = bool(human_prompts) if human_prompts is not None else False
    async for event in _stream_assistant_reply(
        session_id,
        user_content=user_content,
        assistant_msg_id=str(uuid4()),
        user_id=user_id,
        context=context,
        tenant_id=tenant_id,
        human_prompts=hp,
        attachments=attachments or None,
        generation_options=effective_generation_options,
        jira_context=jira_ctx,
    ):
        yield event
