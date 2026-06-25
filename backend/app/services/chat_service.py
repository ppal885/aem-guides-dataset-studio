"""Chat service - sessions, messages, RAG, streaming."""
import asyncio
import copy
import json
import os
import re
from dataclasses import dataclass, field, replace
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
    get_active_llm_provider,
    generate_chat_stream_with_tools,
    generate_text,
    is_llm_available,
    start_llm_trace,
    store_chat_llm_run,
    summarize_llm_trace,
)
from app.services.chat_tools import (
    CHAT_GUIDANCE_ONLY_DISABLED_TOOLS,
    get_tool_catalog,
    get_tool_definitions,
    is_chat_guidance_only_mode,
    parse_tool_intent_from_content,
    run_tool,
)
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
from app.services.hierarchical_retriever import hierarchical_retrieve, format_bundle_for_prompt
from app.models.chunk_metadata import ChunkMetadata, ScoredChunk, RetrievalBundle
from app.services.dita_knowledge_retriever import retrieve_dita_knowledge
from app.services.learned_qa_service import format_learned_qa_for_prompt
from app.services.claude_code_retriever import retrieve_claude_code_context
from app.services.jira_chat_search_service import extract_jira_search_query
from app.services.jira_generate_resolve import extract_issue_key_from_generation_request
from app.services.intent_analysis_service import analyze_intent_sync
from app.services.grounding_service import (
    build_evidence_pack,
    grounding_metadata_from_pack,
    grounding_to_notice,
    _build_thin_evidence_answer,
    _looks_like_publish_filtering_question,
    _looks_like_retrieval_summary,
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
RAG_QUERY_MAX_CHARS = int(os.getenv("RAG_QUERY_MAX_CHARS", "500"))

# Chat limits (prevent unbounded growth)
CHAT_MAX_MESSAGES_PER_SESSION = int(os.getenv("CHAT_MAX_MESSAGES_PER_SESSION", "500"))
CHAT_CONTEXT_WINDOW_MESSAGES = int(os.getenv("CHAT_CONTEXT_WINDOW_MESSAGES", "20"))

# Session generation context for conversational refinement (in-memory, keyed by session_id)
_session_last_generation: dict[str, dict] = {}
# Hierarchical retrieval feature flag (Phase C3) — uses richer formatting from
# hierarchical_retriever but does NOT yet do async structural expansion (parent/child/conref).
# Full expansion requires CHUNK_METADATA_ENABLED + async retrieval path (future enhancement).
HIERARCHICAL_RETRIEVAL_ENABLED = os.getenv("HIERARCHICAL_RETRIEVAL_ENABLED", "false").lower() == "true"

# D7: Tool result caching — avoids re-executing identical read-only tool calls
CHAT_TOOL_CACHE_ENABLED = os.getenv("CHAT_TOOL_CACHE_ENABLED", "false").lower() == "true"
CHAT_LLM_ILLUSTRATIVE_DITA_EXAMPLES = os.getenv("CHAT_LLM_ILLUSTRATIVE_DITA_EXAMPLES", "false").lower() in ("1", "true", "yes", "on")
_STALE_NO_VERIFIED_SNIPPET_WARNING = "No verified snippet was available for this construct, so the answer omits example XML."
_EXAMPLE_INTENT_RE = re.compile(
    r"\b(example|snippet|show|sample|illustrat|demonstrate|give.*xml|xml.*example|code.*example)\b",
    re.IGNORECASE,
)
_tool_cache = None
def _get_tool_cache():
    global _tool_cache
    if _tool_cache is None:
        from app.services.tool_result_cache import ToolResultCache
        _tool_cache = ToolResultCache()
    return _tool_cache

_CHAT_CONTEXT_MAX_TOKENS_RAW = os.getenv("CHAT_CONTEXT_MAX_TOKENS", "120000").strip()
CHAT_CONTEXT_MAX_TOKENS = int(_CHAT_CONTEXT_MAX_TOKENS_RAW) if _CHAT_CONTEXT_MAX_TOKENS_RAW else None

_CHAT_PROMPT_BUILDER: Optional[PromptBuilder] = None
_DATASET_REQUEST_PATTERN = re.compile(
    r"\b(generate|create|build|make|run|start)\b.*\b(dataset|recipe|sample|smoke test|test data)\b",
    re.IGNORECASE,
)
# Explicit recipe type names always mean "generate this" — route directly to generation_request
_RECIPE_TYPE_GENERATION_PATTERN = re.compile(
    r"\b(generate|create|build|make|run)\b.*\b(task_topics|concept_topics|glossary_pack|reference_topics|"
    r"properties_table_reference|syntax_diagram_reference|bookmap|conref_pack|keyscope|bulk_dita|incremental_topicref|insurance_incremental|"
    r"map_parse|relationship_table|validation_duplicate|maps_topicref|maps_reltable|maps_mapref|"
    r"deep_hierarchy|wide_branching|flat_hierarchical_dita|large_scale|freeform)\b",
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
    # topic structure
    r"shortdesc|abstract|prolog|taskbody|conbody|refbody|troublebody|"
    r"prereq|context|steps|step|cmd|info|substeps|substep|choices?|choicetables?|"
    r"choiceoption|choicedesc|stepresult|tutorialinfo|stepxmp|result|postreq|"
    r"condition|cause|remedy|responsibleparty|"
    # block elements
    r"section|example|note|warning|hazardstatement|caution|danger|attention|"
    r"typeofhazard|consequence|howtoavoid|messagepanel|"
    r"p\b|ul|ol|li|sl|sli|dl|dlentry|dlhead|dthd|ddhd|dt\b|dd\b|"
    r"table|tgroup|thead|tbody|tfoot|colspec|row|entry|"
    r"simpletable|sthead|strow|stentry|properties|prophead|proprow|proptype|propvalue|propdesc|"
    r"fig|desc|image|alt|object|param|"
    r"lines|pre|codeblock|codeph|lq|q|cite|"
    r"draft-comment|required-cleanup|"
    # inline elements
    r"ph\b|keyword|term|b\b|i\b|u\b|sub\b|sup\b|tt\b|"
    r"uicontrol|wintitle|menucascade|shortcut|screen|"
    r"cmdname|filepath|varname|apiname|parmname|msgph|msgblock|"
    r"synph|syntaxdiagram|groupseq|groupchoice|groupcomp|fragref|fragment|synnote|"
    r"userinput|systemoutput|codeph|"
    r"xref|link|linktext|linktitle|linkpool|related-links|related links?|relatedl|"
    r"linklist|link list|linkinfo|link info|link element|"
    # map / reuse
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
    r"task topic|concept topic|reference topic|specialization|constraint|keyscope|"
    # Conditional profiling attributes (audience, platform, product for DITAVAL)
    r"@audience|@platform|@product|@props|audience\s+attribute|platform.specific|audience.specific|"
    # Code elements context
    r"shell\s+command|code\s+block|command\s+line|wrap.*command|element.*command)\b",
    re.IGNORECASE,
)
_DITA_ANSWER_INTENT_PATTERN = re.compile(
    r"^\s*(what|how|where|when|why|which|should|must|will|would|do|does|can|could|explain|define|tell\s+me\s+about|help\s+me\s+understand)\b|"
    r"\b(?:and\s+then|then|and|also)\s+(?:explain|define)\b|"
    r"\b(compare|difference\s+between|versus|vs\.?)\b",
    re.IGNORECASE,
)
_LEARNED_QA_DOMAIN_PATTERN = re.compile(
    r"\b(dita|aem guides|morerows|simpletable|cals|keyscope|keyref|conref|mapref|processing-role|resource-only|draft-comment|required-cleanup|ditaval|native pdf|dita-ot|chunk|subject scheme|subjectscheme|topicref|table)\b",
    re.IGNORECASE,
)
_ASSISTIVE_DITA_GENERATION_REQUEST_PATTERN = re.compile(
    r"^\s*(can|could|would)\s+you\s+"
    r"(generate|create|write|draft|make|build|produce|prepare)\b",
    re.IGNORECASE,
)
_EXPLICIT_COMPARISON_REQUEST_PATTERN = re.compile(
    r"\b(vs\.?|versus|compare|comparison|difference\s+between|instead\s+of)\b",
    re.IGNORECASE,
)
_AEM_UI_CONFIGURATION_QUERY_PATTERN = re.compile(
    r"\b(aem guides|web editor|editor|toolbar|toolbars|shortcut|shortcuts|folder profile|"
    r"user preferences|editor settings|ui config|ui configuration|editor config|editor configuration|"
    r"theme|base path|citations)\b",
    re.IGNORECASE,
)
_NATIVE_PDF_QUERY_PATTERN = re.compile(
    r"\b(native pdf|pdf template|watermark|page layout|headers?|footers?|table of contents|toc|cover page)\b",
    re.IGNORECASE,
)
_OUTPUT_PRESET_QUERY_PATTERN = re.compile(
    r"\b(output preset|output presets|publishing|publish|html5|pdf preset|aem sites|site generation)\b",
    re.IGNORECASE,
)
_DITA_OT_BUILD_PARAMS_RE = re.compile(
    r"\bdita.?ot\b.{0,50}\barg(?:s|ument)?s?\b|"
    r"\barg(?:s|ument)?s?\b.{0,50}\bdita.?ot\b|"
    r"\bargs\.\w+\b|"
    r"what\s+arg\w*\s+(?:should|to)\s+pass.{0,30}\bdita\b",
    re.IGNORECASE,
)
_NATIVE_PDF_OT_ARGS_RE = re.compile(
    r"(?:native\s+pdf|native-pdf).{0,80}(?:dita.?ot|ot\s+arg|args?\.\w+|argument)|"
    r"(?:dita.?ot|ot\s+arg|args?\.\w+|argument).{0,80}(?:native\s+pdf|native-pdf)",
    re.IGNORECASE,
)
_OUTPUT_PRESET_TAXONOMY_RE = re.compile(
    r"output\s+preset\s+types?|"  # "output preset types/type"
    r"types?\s+of\s+output\s+preset|"  # "types of output preset"
    r"\b\d+\b\s+output\s+preset|"  # "7 output presets" (whole-number only, not "HTML5")
    r"output\s+preset.*when\s+to\s+use",  # "output preset … when to use"
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
    # DITA-OT error codes / build failures: spec RAG is noise, not signal
    if _DITA_OT_ERROR_PATTERN.search(text):
        return False
    # AEM-product publishing questions (Native PDF, output preset, AEM Guides UI):
    # the structural DITA spec is not the relevant evidence source here
    _aem_product_ctx = re.search(
        r"\b(native\s+pdf|output\s+preset|folder\s+profile|aem\s+guides|web\s+editor)\b",
        text, re.IGNORECASE,
    )
    if _aem_product_ctx:
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


_DITA_ELEMENT_TAG_PATTERN = re.compile(r"</?[a-z][a-z0-9\-]*>", re.IGNORECASE)
_DITA_ELEMENT_DEFINITION_INTENT = re.compile(
    r"^(what\s+is|what('s| is)\s+the\s+(use|purpose|role|function)|explain|how\s+(do\s+I\s+)?use|when\s+(do\s+I\s+)?use|tell\s+me\s+about)\b",
    re.IGNORECASE,
)
_DITA_STRUCTURE_FEEDBACK_CONSTRUCTS = re.compile(
    r"\b(choicetables?|simpletable|properties\s*table|reltable|relationship\s*table|topicref|conref|keyref|"
    r"bookmap|ditamap|xref|shortdesc|taskbody|prereq|postreq|substeps?|choices?|result|"
    r"codeblock|note|warning|hazardstatement|uicontrol|cmdname|varname|filepath|apiname)\b",
    re.IGNORECASE,
)
_DITA_STRUCTURE_FEEDBACK_KEYWORDS = re.compile(
    r"\b(incorrect|wrong|broken|bad|off|invalid|error|not\s+right|doesn't?\s+look|isn't?\s+right|"
    r"markup\s+is|example\s+is|structure\s+is|syntax\s+is)\b",
    re.IGNORECASE,
)


def _is_dita_element_definition_query(text: str) -> bool:
    """Return True for short 'what is <elem>?' style questions about a specific DITA element."""
    t = (text or "").strip()
    if not t or len(t) > 200:
        return False
    if _ASSISTIVE_DITA_GENERATION_REQUEST_PATTERN.search(t):
        return False
    return bool(_DITA_ELEMENT_TAG_PATTERN.search(t) and _DITA_ELEMENT_DEFINITION_INTENT.search(t))


def _is_dita_structure_feedback_query(text: str) -> bool:
    """Return True when the user is flagging a DITA construct example/markup as incorrect."""
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        _DITA_STRUCTURE_FEEDBACK_CONSTRUCTS.search(t)
        and _DITA_STRUCTURE_FEEDBACK_KEYWORDS.search(t)
    )


def _should_skip_aem_rag_for_dita_query(text: str) -> bool:
    """Return True when AEM Experience League RAG adds noise rather than signal."""
    return _is_dita_structure_feedback_query(text) or _is_dita_element_definition_query(text)


_DITA_ELEMENT_GUIDANCE: Optional[str] = None
_DITA_OT_GUIDANCE: Optional[str] = None
_DITA_AUTHORING_GUIDANCE: Optional[str] = None

_DITA_OT_PATTERN = re.compile(
    r"\b(dita.?ot|dita open toolkit|transtype|transform|pdf2|html5\s+output|publish|publishing|"
    r"output preset|native pdf|ant\s+propert|plugin|ditaval filter|xsl.fo|fop|xslt|"
    r"dita command|dita --input|dita --format|dita --output|"
    # DITA-OT error/warning codes (DOTX, DOTJ, DOTA, DOTF prefixes)
    r"DOT[XJAF]\d+|DITA.OT\s+error|build\s+fail|transform\s+fail|"
    # Common OT symptoms
    r"NullPointerException|OutOfMemoryError|xsl.*error|fo.*error|fop.*error|"
    r"missing.*(image|topic|map)|broken.*link|unresolved.*(key|conref|xref)|"
    r"dita.ot\s+\d+\.\d+|upgrade.*dita.ot|dita.ot.*version|"
    # AEM Guides publishing
    r"native\s+pdf|aem.*publish|publish.*aem|output.*preset|preset.*output|"
    # Output quality symptoms (not errors but publishing problems)
    r"missing.*toc|toc.*missing|table.*of.*contents.*missing|missing.*table.*of.*contents|"
    r"output.*wrong|wrong.*output|output.*missing|broken.*output|"
    r"html5.*slow|slow.*html5|large.*map.*slow|performance.*output|"
    r"toc.*not.*appear|toc.*empty|headings.*missing.*output)\b",
    re.IGNORECASE,
)
_DITA_OT_ERROR_PATTERN = re.compile(
    r"\b(DOT[XJAF]\w+|"                               # error codes: DOTX020, DOTJ013F, DOTA045W, etc.
    r"NullPointerException|OutOfMemoryError|"
    r"stack\s*trace|exception\s+in\s+thread|"
    r"build\s+fail(ed|ure)|transform\s+fail(ed|ure)|"
    r"fop.*error|xsl.*error|fo.*error|"
    r"unresolved\s+(key\w*|conref\w*|xref\w*)|"
    r"missing\s+(image|topic|file|map)|broken\s+link|"
    r"dita.ot.*bug|dita.ot.*issue|known\s+issue)\b",
    re.IGNORECASE,
)

_DITA_AUTHORING_PATTERN = re.compile(
    r"\b(best practice|when (should|to) use|concept (vs?|versus) task|content reuse|"
    r"how (do I|to) (reuse|structure|organise|organize|write|author)|shortdesc rule|"
    r"map structure|keydef|keyscope|conref (library|map|pattern)|ditaval|condition|"
    r"topic type|file (naming|organisation|organization)|"
    r"keyref.*(product|variable|name|text)|product.*(name|variable).*keyref|"
    r"how.*(use|set.?up|create).*(keyref|key\s+definition|keydef)|"
    r"keyscopes?|"
    # Multi-product / content sharing architecture questions
    r"products?\s+shar|shar.*\s+content|reuse\s+strat|avoid\s+duplic|"
    r"architecture.*dita|dita.*architecture)\b",
    re.IGNORECASE,
)

_DITA_OT_COMPARISON_PATTERN = re.compile(
    r"\b(native\s+pdf\s+(vs?|versus|compared?|difference)|"
    r"pdf2\s+(vs?|versus|compared?|difference)|"
    r"difference.*native\s+pdf|difference.*pdf2|"
    r"compare.*(native\s+pdf|pdf2)|"
    r"native\s+pdf.*vs.*pdf2|pdf2.*vs.*native)\b",
    re.IGNORECASE,
)


def _load_skill_guidance(filename: str) -> str:
    path = PROMPTS_DIR / filename
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _get_dita_element_guidance() -> str:
    global _DITA_ELEMENT_GUIDANCE
    if _DITA_ELEMENT_GUIDANCE is None:
        _DITA_ELEMENT_GUIDANCE = _load_skill_guidance("chat_dita_element_guidance.txt")
    return _DITA_ELEMENT_GUIDANCE


def _get_dita_ot_guidance() -> str:
    global _DITA_OT_GUIDANCE
    if _DITA_OT_GUIDANCE is None:
        _DITA_OT_GUIDANCE = _load_skill_guidance("chat_dita_ot_guidance.txt")
    return _DITA_OT_GUIDANCE


def _get_dita_authoring_guidance() -> str:
    global _DITA_AUTHORING_GUIDANCE
    if _DITA_AUTHORING_GUIDANCE is None:
        _DITA_AUTHORING_GUIDANCE = _load_skill_guidance("chat_dita_authoring_guidance.txt")
    return _DITA_AUTHORING_GUIDANCE


def _select_skill_guidance(user_content: str) -> str:
    """Return the appropriate skill guidance block for the user's question."""
    text = (user_content or "").strip()
    if not text:
        return ""
    if _DITA_OT_PATTERN.search(text):
        return _get_dita_ot_guidance()
    if _DITA_AUTHORING_PATTERN.search(text):
        return _get_dita_authoring_guidance()
    if _DITA_ELEMENT_TAG_PATTERN.search(text) or _DITA_STRUCTURAL_QUERY_PATTERN.search(text):
        return _get_dita_element_guidance()
    return ""


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
                "Help with DITA, AEM Guides, DITA-OT, troubleshooting, and Jira issue understanding. "
                "Keep answers grounded, senior-level, and practical. Builder handles dataset generation workflows. "
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


def _is_chat_generation_redirect_tool(tool_name: str) -> bool:
    normalized = str(tool_name or "").strip()
    return normalized in CHAT_GUIDANCE_ONLY_DISABLED_TOOLS or normalized == "generate_dita"


def _plan_contains_chat_generation_redirect(plan: dict[str, Any] | None) -> bool:
    if not isinstance(plan, dict):
        return False
    for step in plan.get("steps") or []:
        if _is_chat_generation_redirect_tool(str(step.get("tool_name") or "").strip()):
            return True
    return False


def _build_builder_handoff_message(
    user_content: str,
    *,
    blocked_tool: str = "",
    legacy_plan: bool = False,
    mixed_intent: bool = False,
) -> str:
    lines = [
        "Chat now focuses on DITA, AEM Guides, DITA-OT, troubleshooting, and Jira issue understanding.",
        "",
    ]
    if legacy_plan:
        lines.append("That saved dataset workflow can no longer run from chat.")
    elif blocked_tool:
        lines.append(f"`{blocked_tool}` is no longer available from chat.")
    else:
        lines.append("Dataset generation has moved out of chat.")
    lines.extend(
        [
            "",
            "Use Builder for dataset and artifact generation instead.",
            "- Open Builder: `/builder`",
            "- Use chat here for grounded explanations, troubleshooting, Jira issue understanding, and senior-quality XML examples.",
        ]
    )
    if mixed_intent:
        lines.extend(
            [
                "",
                "I answered the guidance part here and left generation to Builder.",
            ]
        )
    elif extract_issue_key_from_generation_request(user_content) or _JIRA_SEARCH_PATTERN.search(user_content):
        lines.extend(
            [
                "",
                "If you want, I can still summarize the Jira issue, explain the repro, or help troubleshoot the DITA/AEM impact here.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "If you want, I can still explain the DITA pattern or help refine the question before you generate anything in Builder.",
            ]
        )
    return "\n".join(lines).strip()


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
            "The user has pasted Jira-style content. Focus on issue understanding, repro analysis, DITA/AEM impact, "
            "and troubleshooting unless they explicitly need Builder-based generation."
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


_TEXT_ENCODING_REPAIRS: tuple[tuple[str, str], ...] = (
    ("âš ï¸", "⚠️"),
    ("âœ…", "✅"),
    ("â€¦", "…"),
    ("â€”", "—"),
    ("â€“", "–"),
    ("â€™", "’"),
    ("â€œ", "“"),
    ("â€\x9d", "”"),
    ("â†’", "→"),
    ("â–²", "▲"),
    ("â–¼", "▼"),
    ("Â·", "·"),
)


def _repair_text_encoding_artifacts(text: str) -> str:
    cleaned = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    for broken, fixed in _TEXT_ENCODING_REPAIRS:
        cleaned = cleaned.replace(broken, fixed)
    return cleaned


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
    # Element lookups: success + element_name + non-empty sources qualifies
    if (
        result.get("status") == "success"
        and result.get("element_name")
        and result.get("query_type") == "element"
        and result.get("sources")
    ):
        return True
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
            lines.append("## Top Jira matches")
            for item in issues[:3]:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("issue_key") or "").strip()
                summary_text = str(item.get("summary") or "").strip()
                status = str(item.get("status") or "").strip()
                issue_type = str(item.get("issue_type") or "").strip()
                source = str(item.get("source") or "").strip()
                detail_parts = [part for part in [status, issue_type, source] if part]
                detail = f" ({', '.join(detail_parts)})" if detail_parts else ""
                bullet = f"- `{key}` — {summary_text}{detail}" if key else f"- {summary_text}{detail}"
                if bullet not in lines:
                    lines.append(bullet)
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

    return _repair_text_encoding_artifacts("\n\n".join(deduped).strip())


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
        return _repair_text_encoding_artifacts(
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
    return _repair_text_encoding_artifacts("\n".join(lines))


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
    return bool(
        _detect_jira_style_text(text)
        or _DITA_GENERATION_PATTERN.search(text)
        or extract_issue_key_from_generation_request(text)
    )


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
    requested_attribute = _extract_requested_dita_attribute(text)
    if _detect_jira_style_text(text):
        return "generation_request"
    if extract_issue_key_from_generation_request(text):
        return "generation_request"
    if _DATASET_REQUEST_PATTERN.search(text):
        return "agent_research_plan"
    if _RECIPE_TYPE_GENERATION_PATTERN.search(text):
        return "generation_request"
    if _DITA_OT_PATTERN.search(text):
        # Error codes / build failures → default mode so GitHub RAG is primary evidence
        if _DITA_OT_ERROR_PATTERN.search(text):
            return "default"
        # Comparison questions (native PDF vs pdf2, etc.) → default so OT guidance table is used
        if _DITA_OT_COMPARISON_PATTERN.search(text):
            return "default"
        # Pure DITA-OT parameter/argument questions without AEM-specific product context
        # (e.g. "What arguments should be given in dita ot?") → spec RAG is primary evidence
        # Broad pattern tolerates typos like "argumernts" (real test prompt)
        _is_pure_ot_param = re.search(
            r"\b(arg[a-z]*|param(?:eter)?s?|flag[s]?|option[s]?|switch(?:es)?|command.?line)\b",
            text, re.IGNORECASE,
        )
        _has_aem_product_context = re.search(
            r"\b(native\s+pdf|aem\s+guides|folder\s+profile|web\s+editor|output\s+preset)\b",
            text, re.IGNORECASE,
        )
        if _is_pure_ot_param and not _has_aem_product_context:
            return "grounded_dita_answer"
        # Short follow-up statement in a session where prior messages are about DITA spec/args
        # (e.g. "I am using DITA-OT PDF" after "What argument enables draft-comment?")
        if session_id and len(text.split()) <= 8:
            prior = _fetch_last_user_messages_for_session(session_id, limit=4)
            if any(re.search(r"\barg(?:ument)?s?\b|\bparam(?:eter)?s?\b|\battribute\b", m, re.IGNORECASE)
                   for m in prior if m.strip() != text.strip()):
                return "grounded_dita_answer"
        # General OT/publishing questions → AEM Guides grounding
        return "grounded_aem_answer"
    if _DITA_AUTHORING_PATTERN.search(text) and not _is_dita_answer_request(text):
        # Authoring strategy / keyscope / reuse questions — skill guidance covers this.
        # Skip override when the query is specifically asking about a DITA element/attribute
        # (structural + intent) — the spec lookup answers those better.
        return "default"
    # Multi-context questions spanning DITA spec + AEM Guides product → need multi-source research,
    # UNLESS the question is specifically asking about a DITA element/attribute (grounded spec answer)
    if _AEM_UI_CONFIGURATION_QUERY_PATTERN.search(text) and _DITA_STRUCTURAL_QUERY_PATTERN.search(text):
        if _is_dita_answer_request(text):
            return "grounded_dita_answer"
        return "agent_research_plan"
    if requested_attribute and (_is_definition_style_question(text) or _DITA_ANSWER_INTENT_PATTERN.search(text)):
        return "grounded_dita_answer"
    if _DITA_STRUCTURAL_QUERY_PATTERN.search(text) and (_extract_example_shape_request(text) or _wants_full_example(text)):
        return "grounded_dita_answer"
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

    # DITA-OT error codes / build failures: spec lookup returns wrong element docs.
    # Return empty tool requests — the LLM will answer from GitHub RAG + skill guidance.
    if _DITA_OT_ERROR_PATTERN.search(user_content) and answer_mode == "grounded_dita_answer":
        return requests

    if answer_mode == "grounded_dita_answer":
        # Broad map-construct questions span multiple elements — skip single-attribute lookup
        is_broad_map = _needs_broad_map_construct_answer(user_content)
        if not is_broad_map:
            attribute_name = _extract_requested_dita_attribute(user_content)
            if attribute_name:
                requests.append(("lookup_dita_attribute", {"attribute_name": attribute_name}))

        # DITA-OT build params: boost the query with known arg names, add AEM + tenant search
        if _DITA_OT_BUILD_PARAMS_RE.search(user_content):
            boosted_q = f"{user_content} args.draft required-cleanup"
            requests.append(("lookup_dita_spec", {"query": boosted_q}))
            requests.append(("lookup_aem_guides", {"query": boosted_q}))
            requests.append(("search_tenant_knowledge", {"query": boosted_q}))
        elif (
            _is_dita_construct_output_query(user_content)
            and not _DITA_FOREIGN_ELEMENT_QUERY_PATTERN.search(user_content)
            and not _DITA_RELATED_LINKS_TOC_QUERY_PATTERN.search(user_content)
        ):
            requests.append(("lookup_dita_spec", {"query": user_content}))
            if _NATIVE_PDF_QUERY_PATTERN.search(lowered):
                requests.append(("generate_native_pdf_config", {"query": user_content}))
                requests.append(("lookup_output_preset", {"query": user_content, "output_type": "native_pdf"}))
            requests.append(("lookup_aem_guides", {"query": user_content}))
            requests.append(("search_tenant_knowledge", {"query": user_content}))
        elif _looks_like_publish_filtering_question(user_content):
            boosted_q = (
                f"{user_content} ditaval conditional processing audience props otherprops "
                "draft-comment required-cleanup output preset"
            )
            requests.append(("lookup_dita_spec", {"query": boosted_q}))
        else:
            requests.append(("lookup_dita_spec", {"query": user_content}))
        return requests

    if answer_mode == "grounded_aem_answer":
        if _NATIVE_PDF_QUERY_PATTERN.search(lowered):
            # When OT arguments are also mentioned, set config_type accordingly
            _ot_args = bool(_NATIVE_PDF_OT_ARGS_RE.search(user_content) or _DITA_OT_BUILD_PARAMS_RE.search(user_content))
            _native_pdf_params: dict[str, Any] = {"query": user_content}
            if _ot_args:
                _native_pdf_params["config_type"] = "dita_ot_arguments"
            requests.append(("generate_native_pdf_config", _native_pdf_params))
            requests.append(("lookup_output_preset", {"query": user_content, "output_type": "native_pdf"}))
            requests.append(("lookup_aem_guides", {"query": user_content}))
            if _ot_args:
                requests.append(("lookup_dita_spec", {"query": user_content}))
        elif _OUTPUT_PRESET_QUERY_PATTERN.search(lowered):
            requests.append(("lookup_output_preset", {"query": user_content}))
            # Boost AEM lookup for taxonomy/comparison questions
            if _OUTPUT_PRESET_TAXONOMY_RE.search(user_content):
                aem_q = f"understand output presets types in AEM Guides: {user_content}"
            else:
                aem_q = user_content
            requests.append(("lookup_aem_guides", {"query": aem_q}))
        else:
            requests.append(("lookup_aem_guides", {"query": user_content}))
        if _should_include_tenant_knowledge_for_aem_query(user_content):
            requests.append(("search_tenant_knowledge", {"query": user_content}))
    return requests


_BROAD_MAP_TERMS = ["topichead", "navtitle", "locktitle", "topicref", "mapref", "topicgroup", "keyref"]
_OT_SOURCE_DOMAIN_RE = re.compile(
    r"\bdita.?ot\b|\bpdf2\b|\btranstype\b|\bbuild\s+param|\bplugin\b|\bargs\.\w+\b|\barg(?:s|ument)?s?\b.{0,30}\bpublish\b",
    re.IGNORECASE,
)
_OT_OFFICIAL_LABEL_RE = re.compile(
    r"args\.\w+|"  # "args.draft", "args.input"
    r"(?:dita.?ot|dita-ot)\s+(?:base|dev|build|ref|param|version)|"  # "DITA-OT base parameters"
    r"dita.?ot\s+\d+\.|"  # "DITA-OT 3.7"
    r"dita-ot\.org",  # literal URL domain in label
    re.IGNORECASE,
)
_OT_OFFICIAL_URL_RE = re.compile(r"dita-ot\.org", re.IGNORECASE)


def _needs_broad_map_construct_answer(query: str) -> bool:
    """Return True if the question spans 3+ DITA map elements/attributes together.

    Such questions are too broad for a single attribute lookup — use spec search instead.
    """
    count = sum(
        1 for term in _BROAD_MAP_TERMS
        if re.search(rf"\b{re.escape(term)}\b|<{re.escape(term)}>", query, re.IGNORECASE)
    )
    return count >= 3


def _apply_docs_source_domain_gate(
    query: str,
    candidates: "list[_GroundingCandidate]",
) -> "tuple[list[_GroundingCandidate], dict]":
    """Filter grounding candidates by source domain relevance.

    For OT queries, dita_spec element-only evidence is insufficient — OT docs are required.
    """
    debug: dict = {}
    source_domain = "dita_ot" if _OT_SOURCE_DOMAIN_RE.search(query) or re.search(r"\bargs\.\w+\b", query, re.IGNORECASE) else "general"
    debug["source_domain"] = source_domain

    if source_domain != "dita_ot":
        debug["source_domain_mismatch"] = False
        debug["official_evidence_found"] = False
        debug["rejected_candidates"] = []
        return list(candidates), debug

    selected: list[_GroundingCandidate] = []
    rejected: list[dict] = []
    official_found = False

    _NON_OT_SOURCES = {"dita_spec", "dita_graph"}
    for c in candidates:
        is_element_only = c.source in _NON_OT_SOURCES and not _OT_OFFICIAL_LABEL_RE.search(c.label or "")
        if is_element_only:
            rejected.append({
                "label": c.label,
                "source": c.source,
                "reason": "DITA spec element evidence is not enough for a DITA-OT build/configuration question",
            })
            continue
        if _OT_OFFICIAL_URL_RE.search(c.url or "") or _OT_OFFICIAL_LABEL_RE.search(c.label or ""):
            official_found = True
        selected.append(c)

    debug["source_domain_mismatch"] = len(rejected) > 0  # True when any candidates were filtered out
    debug["official_evidence_found"] = official_found
    debug["rejected_candidates"] = rejected
    return selected, debug


@dataclass
class _ContextualDocsQuery:
    source_domain: str
    answer_question: str
    raw_query: str


def _build_contextual_docs_query(session_id: str, query: str) -> _ContextualDocsQuery:
    """Build a contextual docs query enriched with session history."""
    prior = _recent_user_messages_before_latest(session_id, query, limit=5)
    source_domain = "dita_ot" if _OT_SOURCE_DOMAIN_RE.search(query) or _DITA_OT_PATTERN.search(query) else "general"

    # When prior messages mention draft-comment and we're in OT context, reformulate question
    if source_domain == "dita_ot" and any(_DRAFT_COMMENT_RE.search(m) for m in prior):
        answer_question = "What command-line argument enables draft-comment content in DITA-OT PDF output?"
    else:
        answer_question = query

    return _ContextualDocsQuery(
        source_domain=source_domain,
        answer_question=answer_question,
        raw_query=query,
    )


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
    # Process both "sources" (structured) and "results" (raw tool response) fields
    _raw_sources = (result.get("sources") or result.get("results") or [])[:6]
    for source in _raw_sources:
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
        has_positive_evidence = bool(result.get("evidence"))
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
        if result.get("evidence"):
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
    # Expand follow-up queries using session context (e.g. "I am using DITA-OT PDF" +
    # prior "What is the argument for draft-comment?" → adds "args.draft" to the query)
    effective_content = _expand_follow_up_retrieval_query(session_id, user_content) if session_id else user_content
    requests = _grounded_tool_requests(answer_mode, effective_content)
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

    # Apply source domain gate — filter out wrong-domain candidates for OT queries
    gated_candidates, gate_debug = _apply_docs_source_domain_gate(user_content, candidates)
    source_domain = gate_debug.get("source_domain", "general")
    source_domain_mismatch = gate_debug.get("source_domain_mismatch", False)
    rejected_candidates = gate_debug.get("rejected_candidates", [])
    official_docs_retry = False

    # For OT queries: retry lookup_aem_guides when no official OT docs (dita-ot.org) were found yet
    _has_official_ot_evidence = gate_debug.get("official_evidence_found", False)
    if source_domain == "dita_ot" and not _has_official_ot_evidence and "lookup_aem_guides" in tool_results:
        ot_retry_query = f"DITA-OT command-line parameter: {user_content}"
        retry_result = await run_tool(
            "lookup_aem_guides",
            {"query": ot_retry_query},
            user_id=user_id,
            session_id=session_id,
            tenant_id=tenant_id,
        )
        tool_results["lookup_aem_guides"] = retry_result
        retry_candidates = _tool_result_to_grounding_candidates("lookup_aem_guides", retry_result)
        if retry_candidates:
            gated_candidates.extend(retry_candidates)
            source_domain_mismatch = False
            official_docs_retry = True

    if not gated_candidates:
        gated_candidates = candidates  # fallback: use all candidates if gate removed everything

    evidence_pack = build_evidence_pack(
        query=user_content,
        tenant_id=tenant_id,
        candidates=gated_candidates,
    )
    if official_docs_retry:
        # Official OT docs found after retry — treat as grounded
        evidence_pack.decision.status = "grounded"
        evidence_pack.decision.confidence = max(float(evidence_pack.decision.confidence or 0.0), 0.88)
        evidence_pack.decision.reason = "Official DITA-OT documentation found after targeted retry."
        evidence_pack.decision.thin_evidence = False
    elif answer_mode == "grounded_dita_answer":
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
        "source_domain": source_domain,
        "source_domain_mismatch": source_domain_mismatch,
        "official_docs_retry": official_docs_retry,
        "retrieval_debug": {"rejected_candidates": rejected_candidates},
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


_CLOSED_VALUE_ATTR_NAMES = frozenset(
    {
        "chunk",
        "collection-type",
        "expanse",
        "frame",
        "importance",
        "linking",
        "locktitle",
        "print",
        "processing-role",
        "scale",
        "scalefit",
        "search",
        "toc",
    }
)


def _should_render_attribute_valid_values(
    attr_name: str,
    semantic_class: str,
    values: list[str],
) -> bool:
    if not values:
        return False
    normalized_name = str(attr_name or "").strip().lower()
    normalized_class = str(semantic_class or "").strip().lower()
    if normalized_class in {"enum", "boolean_like"}:
        return True
    return normalized_name in _CLOSED_VALUE_ATTR_NAMES


def _attribute_valid_value_warning(attr_name: str, semantic_class: str, values: list[str]) -> str | None:
    if _should_render_attribute_valid_values(attr_name, semantic_class, values):
        return None
    if not values:
        return None
    normalized = str(attr_name or "").strip()
    return (
        f"`@{normalized}` is not treated as a closed enum here, so unverified value labels were omitted. "
        "Use the syntax/usage sections for the value shape instead."
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


_XML_PRETTY_ROOT_TAGS = {
    "map",
    "bookmap",
    "topic",
    "concept",
    "task",
    "reference",
    "body",
    "conbody",
    "taskbody",
    "refbody",
    "section",
    "table",
    "tgroup",
    "thead",
    "tbody",
    "row",
    "entry",
    "simpletable",
    "sthead",
    "strow",
    "choicetable",
    "chhead",
    "chrow",
    "properties",
    "property",
    "topicref",
    "topichead",
    "topicgroup",
    "reltable",
    "relrow",
    "relcell",
    "steps",
    "step",
    "ul",
    "ol",
    "li",
    "note",
}
_FULL_EXAMPLE_REQUEST_RE = re.compile(
    r"\b(full|complete|end-to-end|whole)\s+(xml\s+)?(example|snippet)\b|"
    r"\bshow\s+me\s+(?:a\s+)?(?:full|complete)\s+(?:xml\s+)?(?:example|snippet)\b",
    re.IGNORECASE,
)
_XML_ALREADY_FULL_ROOT_TAGS = {
    "map",
    "bookmap",
    "topic",
    "concept",
    "task",
    "reference",
    "glossentry",
    "table",
    "simpletable",
    "choicetable",
    "val",
    "ditaval",
}
_MAP_FRAGMENT_ROOT_TAGS = {
    "topicref",
    "topichead",
    "topicgroup",
    "mapref",
    "keydef",
    "topicmeta",
    "reltable",
    "relrow",
    "relcell",
    "ditavalref",
}
_TABLE_FRAGMENT_ROOT_TAGS = {"row", "entry", "thead", "tbody", "tfoot", "tgroup", "colspec"}
_SIMPLETABLE_FRAGMENT_ROOT_TAGS = {"sthead", "strow", "stentry"}
_TASK_FRAGMENT_ROOT_TAGS = {"taskbody", "steps", "step", "cmd", "info", "stepresult", "prereq", "context", "result", "postreq"}
_BODY_BLOCK_FRAGMENT_ROOT_TAGS = {
    "body",
    "conbody",
    "refbody",
    "section",
    "example",
    "p",
    "note",
    "fig",
    "ul",
    "ol",
    "dl",
    "pre",
    "codeblock",
    "lines",
}
_INLINE_FRAGMENT_ROOT_TAGS = {
    "keyword",
    "term",
    "ph",
    "xref",
    "codeph",
    "filepath",
    "uicontrol",
    "wintitle",
    "menucascade",
    "image",
    "draft-comment",
    "required-cleanup",
}


def _pretty_print_xml_fragment(fragment: str) -> str:
    text = str(fragment or "").strip()
    if not text.startswith("<") or ">" not in text:
        return ""
    try:
        from xml.dom import minidom

        doc = minidom.parseString(f"<_chat_root_>{text}</_chat_root_>")
        nodes = [
            node
            for node in doc.documentElement.childNodes
            if node.nodeType != node.TEXT_NODE or str(node.data or "").strip()
        ]
        if not nodes:
            return ""

        element_nodes = [node for node in nodes if node.nodeType == node.ELEMENT_NODE]
        root_tags = [str(getattr(node, "tagName", "") or "").lower() for node in element_nodes]
        should_pretty = len(element_nodes) > 1 or any(tag in _XML_PRETTY_ROOT_TAGS for tag in root_tags)
        if not should_pretty:
            return ""

        rendered: list[str] = []
        for node in nodes:
            if node.nodeType == node.TEXT_NODE:
                stripped = str(node.data or "").strip()
                if stripped:
                    rendered.append(stripped)
                continue
            pretty = str(node.toprettyxml(indent="  ") or "").strip()
            if pretty:
                rendered.append(pretty)
        return "\n".join(rendered).strip()
    except Exception:
        return ""


def _normalize_verified_xml_snippet(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    if "\n" in text:
        lines = [line.rstrip() for line in text.splitlines()]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines).strip()

    compact = " ".join(text.split()).strip()
    pretty = _pretty_print_xml_fragment(compact)
    return pretty or compact


def _wants_full_example(question: str) -> bool:
    return bool(_FULL_EXAMPLE_REQUEST_RE.search(question or ""))


def _leading_xml_tag_name(snippet: str) -> str:
    match = re.match(r"\s*<\s*/?\s*([A-Za-z_:][A-Za-z0-9_.:-]*)", snippet or "")
    return str(match.group(1) if match else "").strip().lower()


def _indent_xml_block(snippet: str, spaces: int) -> str:
    prefix = " " * max(0, int(spaces))
    return "\n".join(f"{prefix}{line}" if line.strip() else line for line in str(snippet or "").splitlines())


def _wrap_xml_fragment(
    snippet: str,
    *,
    opening_lines: list[str],
    closing_lines: list[str],
    indent_spaces: int,
) -> str:
    inner = _indent_xml_block(snippet, indent_spaces)
    return "\n".join([*opening_lines, inner, *closing_lines]).strip()


def _expand_verified_xml_example(
    snippet: str,
    *,
    answer_kind: GroundedAnswerKind,
    attr_name: str = "",
) -> str:
    text = _normalize_verified_xml_snippet(snippet)
    if not text:
        return ""

    root = _leading_xml_tag_name(text)
    lowered = text.lower()
    normalized_attr = str(attr_name or "").strip().lower()

    if root in _XML_ALREADY_FULL_ROOT_TAGS:
        return text

    if (
        normalized_attr == "morerows"
        or root in _TABLE_FRAGMENT_ROOT_TAGS
        or any(token in lowered for token in ('morerows=', 'namest=', 'nameend='))
    ):
        return _wrap_xml_fragment(
            text,
            opening_lines=["<table>", "  <title>Example table</title>", "  <tgroup cols=\"2\">", "    <tbody>"],
            closing_lines=["    </tbody>", "  </tgroup>", "</table>"],
            indent_spaces=6,
        )

    if root in _SIMPLETABLE_FRAGMENT_ROOT_TAGS:
        return _wrap_xml_fragment(
            text,
            opening_lines=["<simpletable>"],
            closing_lines=["</simpletable>"],
            indent_spaces=2,
        )

    if root in _MAP_FRAGMENT_ROOT_TAGS or (
        answer_kind in {"dita_attribute", "dita_map_construct"} and normalized_attr in _MAP_SCOPED_ATTR_NAMES
    ):
        return _wrap_xml_fragment(
            text,
            opening_lines=["<map>", "  <title>Example map</title>"],
            closing_lines=["</map>"],
            indent_spaces=2,
        )

    if root in {"steps", "step"}:
        return _wrap_xml_fragment(
            text,
            opening_lines=["<task id=\"example-task\">", "  <title>Example task</title>", "  <taskbody>"],
            closing_lines=["  </taskbody>", "</task>"],
            indent_spaces=4,
        )

    if root == "cmd":
        return "\n".join(
            [
                "<task id=\"example-task\">",
                "  <title>Example task</title>",
                "  <taskbody>",
                "    <steps>",
                "      <step>",
                _indent_xml_block(text, 8),
                "      </step>",
                "    </steps>",
                "  </taskbody>",
                "</task>",
            ]
        ).strip()

    if root in _TASK_FRAGMENT_ROOT_TAGS:
        return _wrap_xml_fragment(
            text,
            opening_lines=["<task id=\"example-task\">", "  <title>Example task</title>", "  <taskbody>"],
            closing_lines=["  </taskbody>", "</task>"],
            indent_spaces=4,
        )

    if root in _BODY_BLOCK_FRAGMENT_ROOT_TAGS:
        return _wrap_xml_fragment(
            text,
            opening_lines=["<topic id=\"example-topic\">", "  <title>Example topic</title>", "  <body>"],
            closing_lines=["  </body>", "</topic>"],
            indent_spaces=4,
        )

    if root in _INLINE_FRAGMENT_ROOT_TAGS:
        return "\n".join(
            [
                "<topic id=\"example-topic\">",
                "  <title>Example topic</title>",
                "  <body>",
                "    <p>",
                _indent_xml_block(text, 6),
                "    </p>",
                "  </body>",
                "</topic>",
            ]
        ).strip()

    return text


def _clean_grounded_xml_examples(items: Any, *, limit: int | None = None) -> list[str]:
    values: list[str] = []
    if not isinstance(items, list):
        return values
    for item in items:
        text = _normalize_verified_xml_snippet(item)
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


_DEFINITION_STYLE_QUESTION_RE = re.compile(
    r"^\s*(?:"
    r"what\s+(?:is|are|does|did)\b|"
    r"explain\b|"
    r"tell\s+me\s+about\b|"
    r"help\s+me\s+understand\b|"
    r"how\s+does\b|"
    r"meaning\s+of\b"
    r")",
    re.IGNORECASE,
)


def _is_definition_style_question(question: str) -> bool:
    return bool(_DEFINITION_STYLE_QUESTION_RE.search(question or ""))


def _should_auto_include_verified_example(question: str, answer_kind: GroundedAnswerKind) -> bool:
    if answer_kind not in {"dita_attribute", "dita_map_construct"}:
        return False
    return _is_definition_style_question(question)


def _fact_source_policy(
    *,
    answer_mode: str,
    tool_results_by_name: dict[str, dict[str, Any]],
) -> SourcePolicyDecision:
    if answer_mode == "grounded_dita_answer":
        if isinstance(tool_results_by_name.get("generate_native_pdf_config"), dict) and tool_results_by_name.get("generate_native_pdf_config"):
            return "dita_spec_first_then_processor_docs"
        if isinstance(tool_results_by_name.get("lookup_aem_guides"), dict) and tool_results_by_name.get("lookup_aem_guides"):
            return "dita_spec_first_then_aem_guides"
        tenant_result = tool_results_by_name.get("search_tenant_knowledge") or {}
        if isinstance(tenant_result, dict) and ((tenant_result.get("results") or []) or int(tenant_result.get("count") or 0) > 0):
            return "mixed_explicit"
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

    if (
        _DITA_OT_PATTERN.search(question or "")
        and re.search(r"\bdraft.?comment|required.?cleanup\b", lowered_question)
        and re.search(r"\bpdf|pdf2\b", lowered_question)
    ):
        explicit = "Use `--args.draft=yes` to include `<draft-comment>` and `<required-cleanup>` content in DITA-OT PDF/PDF2 output."
        if not any("--args.draft=yes" in item.lower() for item in deduped):
            deduped.insert(0, explicit)
        elif not any("<draft-comment>" in item.lower() or "<required-cleanup>" in item.lower() for item in deduped):
            deduped.insert(0, explicit)

    return deduped


def _tenant_output_guidance_points(tenant: dict[str, Any], *, limit: int = 2) -> list[str]:
    results = tenant.get("results") or []
    points: list[str] = []
    for item in results[:limit]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("title") or item.get("doc_type") or "").strip()
        content = _first_summary_sentence(
            str(item.get("content") or item.get("summary") or item.get("snippet") or "").strip()
        )
        if label and content:
            point = f"Indexed workspace/Jira evidence: {label} — {content}"
        else:
            point = content or label
        if point and point not in points:
            points.append(point)
    return points[:limit]


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
    wants_examples = _extract_example_shape_request(question) or _should_auto_include_verified_example(question, answer_kind)
    if not wants_examples:
        return [], []
    warnings: list[str] = []
    examples: list[VerifiedExampleSnippet] = []
    attr_name = str(attr_name or "").strip().lower()
    for item in raw_examples[:4]:
        snippet = _expand_verified_xml_example(
            item,
            answer_kind=answer_kind,
            attr_name=attr_name,
        )
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
    if wants_examples and not examples:
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

        if _is_dita_construct_output_query(question):
            native_pdf = tool_results_by_name.get("generate_native_pdf_config") or {}
            output_preset = tool_results_by_name.get("lookup_output_preset") or {}
            aem = tool_results_by_name.get("lookup_aem_guides") or {}
            tenant = tool_results_by_name.get("search_tenant_knowledge") or {}
            aem_payload = {**aem, "_question": question} if isinstance(aem, dict) and question else {}

            attr_name = str(attr.get("attribute_name") or "").strip()
            semantic_class = str(attr.get("attribute_semantic_class") or "").strip().lower()
            raw_valid_values = _clean_grounded_strings(attr.get("all_valid_values") or [], limit=12)
            valid_values = (
                raw_valid_values
                if _should_render_attribute_valid_values(attr_name, semantic_class, raw_valid_values)
                else []
            )
            element_name = str(spec.get("element_name") or "").strip()
            element_name_lower = element_name.lower()
            construct_label = (
                f"`@{attr_name}`"
                if attr_name
                else (f"`<{element_name}>`" if element_name else "this DITA construct")
            )
            construct_definition = _first_summary_sentence(
                str(attr.get("text_content") or spec.get("text_content") or spec.get("summary") or "").strip()
            )
            raw_examples = _clean_grounded_xml_examples(
                (attr.get("correct_examples") or spec.get("correct_examples") or []),
                limit=3,
            )
            native_pdf_has_doc_evidence = bool(
                isinstance(native_pdf, dict) and native_pdf.get("evidence") and not native_pdf.get("error")
            )
            aem_summary = _select_aem_guidance_summary(question, aem_payload, output_preset) if aem_payload else ""
            aem_actions = _build_aem_guidance_actions(question, aem_payload, output_preset) if aem_payload else []
            aem_settings = _build_aem_guidance_settings(question, aem_payload, output_preset) if aem_payload else []
            aem_cautions = _build_aem_guidance_cautions(question, aem_payload, output_preset) if aem_payload else []
            tenant_points = _tenant_output_guidance_points(tenant)
            native_pdf_summary = str(native_pdf.get("short_answer") or native_pdf.get("summary") or "").strip()

            if attr_name or element_name or native_pdf_has_doc_evidence or aem_summary or tenant_points:
                if element_name_lower == "glossentry" and _NATIVE_PDF_QUERY_PATTERN.search(question or ""):
                    short_answer = (
                        "`<glossentry>` defines glossary topic structure, but its Native PDF behavior depends on "
                        "how the glossary topic is included in the map and how the PDF pipeline renders it, not "
                        "on the element name alone."
                    )
                elif attr_name or element_name:
                    short_answer = (
                        f"{construct_label} defines the DITA structure, but its exact published-output behavior "
                        "is processor-specific, so verify the output pipeline instead of relying on the DITA "
                        "name alone."
                    )
                else:
                    short_answer = (
                        "This is an output-behavior question, so the DITA construct alone is not enough — "
                        "you need product or pipeline evidence to verify the actual publish result."
                    )

                default_behavior: list[str] = []
                if construct_definition:
                    default_behavior.append(f"DITA role: {construct_definition}")
                if element_name_lower == "glossentry":
                    default_behavior.append(
                        "Glossary hover, tooltip, or editor-preview behavior is typically a web/editor feature; "
                        "Native PDF normally renders the glossary topic content itself, not those interactive behaviors."
                    )
                if native_pdf_summary and native_pdf_summary not in default_behavior:
                    default_behavior.append(native_pdf_summary)
                if aem_summary and aem_summary not in default_behavior:
                    default_behavior.append(aem_summary)

                placement_notes: list[str] = []
                for value in _clean_grounded_strings(native_pdf.get("relevant_settings") or [], limit=4):
                    if value not in placement_notes:
                        placement_notes.append(value)
                for value in aem_settings[:4]:
                    if value not in placement_notes:
                        placement_notes.append(value)
                for value in tenant_points:
                    if value not in placement_notes:
                        placement_notes.append(value)

                usage_patterns: list[str] = []
                for value in _clean_grounded_strings(native_pdf.get("recommended_actions") or [], limit=4):
                    if value not in usage_patterns:
                        usage_patterns.append(value)
                for value in aem_actions[:4]:
                    if value not in usage_patterns:
                        usage_patterns.append(value)
                if element_name_lower == "glossentry":
                    for value in [
                        "Keep the glossary entry structurally valid and referenced from the root map, then verify the Native PDF output from the intended preset/template.",
                        "If you expect glossary navigation or bookmark behavior, validate the map hierarchy and PDF preset rather than the glossentry markup alone.",
                    ]:
                        if value not in usage_patterns:
                            usage_patterns.append(value)

                common_mistakes: list[str] = []
                for value in _clean_grounded_strings(native_pdf.get("common_mistakes") or [], limit=3):
                    if value not in common_mistakes:
                        common_mistakes.append(value)
                for value in aem_cautions[:3]:
                    if value not in common_mistakes:
                        common_mistakes.append(value)
                if element_name_lower == "glossentry":
                    for value in [
                        "Assuming Web Editor glossary hover or popup behavior will automatically appear in Native PDF output.",
                        "Troubleshooting template styling before confirming that the glossary topic is actually included in the map and output flow.",
                    ]:
                        if value not in common_mistakes:
                            common_mistakes.append(value)

                examples, example_warnings = _safe_verified_examples(
                    question=question,
                    answer_kind="dita_output_behavior",
                    raw_examples=raw_examples,
                    attr_name=attr_name,
                )
                thin_evidence = not (native_pdf_has_doc_evidence or aem_summary or tenant_points)
                semantic_warnings = list(common_warnings)
                semantic_warnings.extend(example_warnings)
                if thin_evidence:
                    semantic_warnings.append(
                        "The current evidence verifies the DITA construct, but product-specific output behavior was not directly retrieved."
                    )
                return NormalizedGroundedFactSet(
                    answer_kind="dita_output_behavior",
                    source_policy=source_policy,
                    canonical_definition=short_answer,
                    syntax=str(attr.get("attribute_syntax") or "").strip(),
                    valid_values=valid_values,
                    default_behavior=default_behavior[:5],
                    placement_notes=placement_notes[:5],
                    usage_patterns=usage_patterns[:5],
                    common_mistakes=common_mistakes[:4],
                    verified_examples=examples,
                    example_verified=bool(examples),
                    semantic_warnings=semantic_warnings,
                    thin_evidence=thin_evidence,
                    cross_source_mixed=bool(tenant_points and (native_pdf_has_doc_evidence or aem_summary)),
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

        if isinstance(spec, dict) and not spec.get("error") and spec.get("query_type") == "element_family_overview":
            rows: list[ComparisonRow] = []
            common_mistakes: list[str] = []
            for item in (spec.get("comparisons") or [])[:4]:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("element_name") or item.get("label") or "").strip()
                if not label:
                    continue
                row_mistakes = _clean_grounded_strings(item.get("common_mistakes") or [], limit=2)
                for mistake in row_mistakes:
                    bullet = f"`<{label}>`: {mistake}"
                    if bullet not in common_mistakes:
                        common_mistakes.append(bullet)
                rows.append(
                    ComparisonRow(
                        label=label,
                        definition=_first_summary_sentence(
                            str(item.get("text_content") or item.get("summary") or "").strip()
                        ),
                        usage_patterns=_clean_grounded_strings(item.get("usage_contexts") or [], limit=2),
                        supported_elements=_clean_grounded_strings(item.get("parent_elements") or [], limit=8),
                        companion_attributes=_clean_grounded_strings(item.get("supported_attributes") or [], limit=8),
                        common_mistakes=row_mistakes,
                    )
                )
            if rows:
                return NormalizedGroundedFactSet(
                    answer_kind="dita_element_family_overview",
                    source_policy=source_policy,
                    canonical_definition=_first_summary_sentence(str(spec.get("summary") or "").strip())
                    or f"The main DITA elements in this family are {', '.join(f'<{row.label}>' for row in rows[:4])}.",
                    comparison_rows=rows,
                    common_mistakes=common_mistakes,
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
                raw_examples.extend(_clean_grounded_xml_examples(item.get("correct_examples") or [], limit=2))
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
            raw_valid_values = _clean_grounded_strings(attr.get("all_valid_values") or [], limit=12)
            valid_values = (
                raw_valid_values
                if _should_render_attribute_valid_values(attr_name, semantic_class, raw_valid_values)
                else []
            )
            answer_kind: GroundedAnswerKind = (
                "dita_map_construct"
                if semantic_class == "map_scoped" or attr_name.lower() in _MAP_SCOPED_ATTR_NAMES
                else "dita_attribute"
            )
            examples, example_warnings = _safe_verified_examples(
                question=question,
                answer_kind=answer_kind,
                raw_examples=_clean_grounded_xml_examples(attr.get("correct_examples") or [], limit=3),
                attr_name=attr_name,
            )
            semantic_warnings = common_warnings + example_warnings
            value_warning = _attribute_valid_value_warning(attr_name, semantic_class, raw_valid_values)
            if value_warning:
                semantic_warnings.append(value_warning)
            return NormalizedGroundedFactSet(
                answer_kind=answer_kind,
                source_policy=source_policy,
                canonical_definition=_first_summary_sentence(str(attr.get("text_content") or "").strip()),
                syntax=str(attr.get("attribute_syntax") or _extract_attribute_syntax_line(str(attr.get("text_content") or ""))).strip(),
                valid_values=valid_values,
                supported_elements=_clean_grounded_strings(attr.get("supported_elements") or [], limit=10),
                companion_attributes=_clean_grounded_strings(attr.get("combination_attributes") or [], limit=8),
                usage_patterns=_clean_grounded_strings(attr.get("usage_contexts") or [], limit=3),
                default_behavior=_clean_grounded_strings(attr.get("default_scenarios") or [], limit=3),
                common_mistakes=_clean_grounded_strings(attr.get("common_mistakes") or [], limit=3),
                verified_examples=examples,
                example_verified=bool(examples),
                semantic_warnings=semantic_warnings,
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
            raw_examples = _clean_grounded_xml_examples(spec.get("correct_examples") or [], limit=3)
            notes: list[str] = []
            spec_chunk_texts = [
                " ".join(str(item.get("text_content") or "").split()).strip()
                for item in (spec.get("spec_chunks") or [])[:3]
                if isinstance(item, dict) and str(item.get("text_content") or "").strip()
            ]
            # If top-level element_name is missing, try a single-chunk spec result (unambiguous element query)
            if not element_name and len(spec.get("spec_chunks") or []) == 1:
                first_chunk = spec["spec_chunks"][0]
                if isinstance(first_chunk, dict):
                    element_name = str(first_chunk.get("element_name") or "").strip()
                    element_name_lower = element_name.lower()
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
                examples, example_warnings = _safe_verified_examples(
                    question=question,
                    answer_kind="dita_content_model",
                    raw_examples=raw_examples,
                )
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
                    verified_examples=examples,
                    example_verified=bool(examples),
                    semantic_warnings=common_warnings + example_warnings,
                )
            if query_type == "placement" and (element_name or parent_elements):
                examples, example_warnings = _safe_verified_examples(
                    question=question,
                    answer_kind="dita_placement",
                    raw_examples=raw_examples,
                )
                return NormalizedGroundedFactSet(
                    answer_kind="dita_placement",
                    source_policy=source_policy,
                    canonical_definition=summary,
                    parent_elements=parent_elements,
                    companion_attributes=supported_attributes,
                    usage_patterns=usage_patterns,
                    common_mistakes=common_mistakes,
                    placement_notes=notes,
                    verified_examples=examples,
                    example_verified=bool(examples),
                    semantic_warnings=common_warnings + example_warnings,
                )
            if element_name_lower in _MAP_CONSTRUCT_ELEMENT_NAMES and (summary or element_name):
                examples, example_warnings = _safe_verified_examples(
                    question=question,
                    answer_kind="dita_map_construct",
                    raw_examples=raw_examples,
                )
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
                    verified_examples=examples,
                    example_verified=bool(examples),
                    semantic_warnings=common_warnings + example_warnings,
                )
            # Only render a structured direct answer when the tool identified a specific DITA element
            # (element_name, query_type, or child/parent lists). For general spec queries returning raw
            # ChromaDB chunks, return None so the LLM synthesises a proper answer.
            has_structural_metadata = bool(element_name or query_type or allowed_children or parent_elements)
            if has_structural_metadata and (summary or element_name):
                examples, example_warnings = _safe_verified_examples(
                    question=question,
                    answer_kind="dita_element",
                    raw_examples=raw_examples,
                )
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
                    verified_examples=examples,
                    example_verified=bool(examples),
                    semantic_warnings=common_warnings + example_warnings,
                )
            aem = tool_results_by_name.get("lookup_aem_guides") or {}
            if (
                isinstance(aem, dict)
                and not aem.get("error")
                and (aem.get("results") or aem.get("count"))
                and (
                    str(aem.get("source_domain") or "").strip().lower() == "dita_ot"
                    or bool(_DITA_OT_PATTERN.search(question or ""))
                )
            ):
                aem_payload = {**aem, "_question": question}
                summary = _select_aem_guidance_summary(question, aem_payload, {})
                recommended_actions = _build_aem_guidance_actions(question, aem_payload, {})
                if recommended_actions or summary:
                    return NormalizedGroundedFactSet(
                        answer_kind="aem_guides_guidance",
                        source_policy=source_policy,
                        guidance_kind=_classify_aem_guidance_kind(question),
                        canonical_definition=summary,
                        recommended_actions=recommended_actions[:4],
                        relevant_settings=_build_aem_guidance_settings(question, aem_payload, {}),
                        common_mistakes=_build_aem_guidance_cautions(question, aem_payload, {}),
                        semantic_warnings=common_warnings,
                        cross_source_mixed=False,
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

    native_pdf_has_doc_evidence = bool(
        isinstance(native_pdf, dict) and native_pdf.get("evidence") and not native_pdf.get("error")
    )
    if isinstance(native_pdf, dict) and native_pdf and not native_pdf.get("error") and native_pdf_has_doc_evidence:
        examples = [
            VerifiedExampleSnippet(label="Verified config snippet", snippet=str(item).strip(), source="native_pdf_tool")
            for item in _clean_grounded_xml_examples(native_pdf.get("xml_or_css_snippets") or [], limit=2)
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


def _select_tools_for_query(all_tools: list[dict], query: str, max_tools: int = 8, max_extra: int = 4) -> list[dict]:
    """Select most relevant tools for a query (used when provider has limited context like Groq).

    Always includes core tools, then adds query-relevant ones up to max_tools.
    max_extra: maximum number of non-core tools to add (default 4).
    """
    q = query.lower()
    available_names = {str(tool.get("name") or "").strip() for tool in all_tools}
    # Core tools always included
    core_tools = {
        name
        for name in {"generate_dita", "lookup_aem_guides", "lookup_dita_spec", "search_tenant_knowledge"}
        if name in available_names
    }
    # Relevance keywords for optional tools
    tool_keywords: dict[str, list[str]] = {
        "create_job": ["dataset", "recipe", "generate", "create", "bulk", "sample", "smoke"],
        "search_jira_issues": ["jira", "issue", "ticket", "bug", "story"],
        "review_dita_xml": ["review", "validate", "check", "xml", "error"],
        "find_recipes": ["recipe", "template", "pattern", "dataset"],
        "get_job_status": ["job", "status", "progress", "running"],
        "lookup_output_preset": ["output", "preset", "pdf", "publish", "site"],
        "list_jobs": ["job", "history", "recent", "list"],
        "fix_dita_xml": ["fix", "repair", "correct", "error", "invalid"],
        "lookup_dita_attribute": ["attribute", "property", "element"],
        "list_indexed_pdfs": ["pdf", "indexed", "document", "upload"],
        "generate_native_pdf_config": ["pdf", "native", "config", "template", "stylesheet"],
        "browse_dataset": ["browse", "dataset", "explore", "view"],
        # Phase F: Content Intelligence Tools
        "generate_shortdesc": ["shortdesc", "short description", "summary", "abstract", "missing"],
        "advise_topic_type": ["topic type", "misclassified", "wrong type", "concept", "task", "reference", "classify"],
        "check_style_guide": ["style", "style guide", "passive voice", "terminology", "writing", "quality", "grammar", "tone"],
        # Phase I: Visual & Interactive Tools
        "generate_diagram": ["diagram", "flowchart", "mindmap", "mind map", "visualize", "mermaid", "chart", "flow", "graph"],
        "migrate_content": ["migrate", "convert", "word", "markdown", "html", "import", "migration", "docx", "transform"],
        "visualize_map": ["visualize", "map structure", "topic map", "graph", "tree", "hierarchy", "ditamap"],
    }
    # Score each optional tool by keyword matches
    selected_names = set(core_tools)
    scored: list[tuple[str, int]] = []
    for name, keywords in tool_keywords.items():
        if name not in available_names:
            continue
        if name in selected_names:
            continue
        score = sum(1 for kw in keywords if kw in q)
        scored.append((name, score))
    # Sort by relevance, add top tools up to budget
    scored.sort(key=lambda x: x[1], reverse=True)
    extras_added = 0
    for name, score in scored:
        if len(selected_names) >= max_tools or extras_added >= max_extra:
            break
        if score > 0 or len(selected_names) < max_tools:
            selected_names.add(name)
            extras_added += 1
    return [t for t in all_tools if t.get("name") in selected_names]


def _markdown_table_cell(value: Any) -> str:
    if isinstance(value, list):
        text = "<br>".join(str(item).strip() for item in value if str(item or "").strip())
    else:
        text = str(value or "").strip()
    text = " ".join(text.split()).replace("|", "\\|")
    return text or "-"


def _normalized_fact_text(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip().lower()
    return text.rstrip(".")


def _unique_fact_points(values: list[str], *, exclude: set[str] | None = None) -> list[str]:
    excluded = set(exclude or set())
    results: list[str] = []
    seen: set[str] = set()
    for value in values:
        rendered = " ".join(str(value or "").split()).strip()
        if not rendered:
            continue
        normalized = _normalized_fact_text(rendered)
        if not normalized or normalized in seen or normalized in excluded:
            continue
        seen.add(normalized)
        results.append(rendered)
    return results


def _preferred_grounded_short_answer(facts: NormalizedGroundedFactSet) -> str:
    short_answer = " ".join(str(facts.canonical_definition or "").split()).strip()
    generic_fallback = "dita attribute used in construct-specific contexts"
    lowered = short_answer.lower()
    if "@keyscope attribute creates a named scope for key definitions" in lowered:
        return (
            "The @keyscope attribute creates a named scope for key definitions in a DITA map, "
            "so the same key names can exist in different branches and be addressed as "
            "`scope-name.key-name`."
        )
    if short_answer and generic_fallback not in short_answer.lower():
        return short_answer
    for candidate in [*facts.usage_patterns, *facts.default_behavior, *facts.placement_notes]:
        rendered = " ".join(str(candidate or "").split()).strip()
        if rendered:
            return rendered
    return short_answer


def _render_grounded_quick_reference_table(facts: NormalizedGroundedFactSet) -> list[str]:
    rows: list[tuple[str, str]] = []
    if facts.syntax:
        rows.append(("Syntax", f"`{facts.syntax}`"))
    if facts.valid_values:
        rows.append(("Valid values", ", ".join(f"`{value}`" for value in facts.valid_values[:8])))
    if facts.supported_elements:
        label = "Where it applies" if facts.answer_kind == "dita_map_construct" else "Supported elements"
        rows.append((label, ", ".join(f"`<{value}>`" for value in facts.supported_elements[:8])))
    if facts.parent_elements and facts.answer_kind in {"dita_element", "dita_content_model", "dita_placement"}:
        rows.append(("Valid parents", ", ".join(f"`<{value}>`" for value in facts.parent_elements[:8])))
    if facts.allowed_children and facts.answer_kind in {"dita_element", "dita_content_model"}:
        rows.append(("Common children", ", ".join(f"`<{value}>`" for value in facts.allowed_children[:8])))
    if facts.default_behavior:
        rows.append(("Key behavior", _markdown_table_cell(facts.default_behavior[:2])))
    if facts.companion_attributes:
        companion_values = [
            f"`@{value.lstrip('@')}`" if not str(value).startswith("<") else f"`{value}`"
            for value in facts.companion_attributes[:6]
        ]
        rows.append(("Companion attributes", ", ".join(companion_values)))
    if not rows:
        return []
    lines = ["", "## Quick reference", "| Field | Details |", "|---|---|"]
    for label, detail in rows:
        lines.append(f"| {label} | {_markdown_table_cell(detail)} |")
    return lines


def _grounded_example_explanation_points(
    facts: NormalizedGroundedFactSet,
    *,
    snippet: str,
    limit: int = 3,
) -> list[str]:
    candidates: list[str] = []
    snippet_lower = str(snippet or "").lower()
    if facts.default_behavior:
        candidates.extend(facts.default_behavior[:2])
    if "morerows=" in snippet_lower and snippet_lower.count("<row") >= 2:
        candidates.append(
            "Rows below a `@morerows` entry do not repeat that occupied cell position; the spanning cell above already covers it."
        )
        candidates.append(
            "For `morerows=\"1\"`, the cell starts in the current row and spans one additional row, so it covers two rows total."
        )
    if "namest=" in snippet_lower and "nameend=" in snippet_lower:
        candidates.append(
            "`@namest` and `@nameend` mark the start and end columns for a horizontal cell span."
        )
    if "keyscope=" in snippet_lower and "keyref=" in snippet_lower:
        candidates.append(
            "`@keyscope` creates the scope name for the keys defined in that map branch or referenced submap."
        )
        candidates.append(
            "A qualified reference such as `keyref=\"book-b.install\"` means “resolve the key `install` inside the `book-b` scope.”"
        )
        candidates.append(
            "This lets different branches reuse the same key names without collisions because each branch can own its own scope."
        )
    if "scope=\"peer\"" in snippet_lower and "format=\"ditamap\"" in snippet_lower:
        candidates.append(
            "`scope=\"peer\"` with `format=\"ditamap\"` commonly marks another deliverable or submap whose keys you want to namespace."
        )
    if facts.usage_patterns:
        candidates.extend(facts.usage_patterns[:2])
    if facts.answer_kind == "dita_attribute" and facts.supported_elements:
        supported = ", ".join(f"`<{value}>`" for value in facts.supported_elements[:4])
        candidates.append(f"This attribute is supported on {supported}.")
    elif facts.placement_notes:
        candidates.extend(facts.placement_notes[:2])
    return _unique_fact_points(candidates)[:limit]


def _render_normalized_grounded_fact_set(facts: NormalizedGroundedFactSet) -> str:
    short_answer = _preferred_grounded_short_answer(facts)
    if not short_answer:
        return ""
    normalized_short_answer = _normalized_fact_text(short_answer)
    usage_patterns = _unique_fact_points(facts.usage_patterns, exclude={normalized_short_answer})
    default_behavior = _unique_fact_points(
        facts.default_behavior,
        exclude={normalized_short_answer, *[_normalized_fact_text(value) for value in usage_patterns]},
    )

    # AEM product guidance answers use "## At a glance"; DITA spec answers use "## Short answer"
    _first_heading = "## At a glance" if facts.answer_kind == "aem_guides_guidance" else "## Short answer"
    sections: list[str] = [_first_heading, short_answer]
    quick_reference = _render_grounded_quick_reference_table(facts)
    if quick_reference:
        sections.extend(quick_reference)

    practical_points = []
    for value in [*usage_patterns[:3], *default_behavior[:2], *facts.placement_notes[:2]]:
        if value and value not in practical_points:
            practical_points.append(value)

    if facts.answer_kind in {"dita_attribute", "dita_map_construct"}:
        if practical_points:
            sections.extend(["", "## In practice", *[f"- {value}" for value in practical_points[:4]]])
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
            related = [
                f"`@{value.lstrip('@')}`" if not str(value).startswith("<") else f"`{value}`"
                for value in facts.companion_attributes[:6]
                if str(value).strip()
            ]
            if related:
                sections.extend(["", "## Related concepts", f"- See also: {', '.join(related)}"])
        if default_behavior:
            sections.extend(["", "## Default behavior", *[f"- {value}" for value in default_behavior[:4]]])
        if facts.answer_kind == "dita_map_construct":
            resolution_points = []
            for value in [*facts.placement_notes[:4], *usage_patterns[:4]]:
                if value and value not in resolution_points:
                    resolution_points.append(value)
            if resolution_points:
                sections.extend(["", "## Resolution behavior", *[f"- {value}" for value in resolution_points[:5]]])
        elif usage_patterns:
            sections.extend(["", "## Typical usage", *[f"- {value}" for value in usage_patterns[:4]]])
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
        if not facts.comparison_rows:
            return ""
        sections.extend(
            [
                "",
                "## Comparison",
                "| Attribute | What it does | Syntax | Typical use | Supported elements |",
                "|---|---|---|---|---|",
            ]
        )
        for row in facts.comparison_rows[:4]:
            sections.append(
                "| "
                + " | ".join(
                    [
                        f"`@{_markdown_table_cell(row.label.lstrip('@'))}`",
                        _markdown_table_cell(row.definition),
                        _markdown_table_cell(row.syntax),
                        _markdown_table_cell(row.usage_patterns[:2]),
                        _markdown_table_cell([f"`{value}`" for value in row.supported_elements[:8]]),
                    ]
                )
                + " |"
            )
        usage_rows = [
            f"- `@{row.label.lstrip('@')}`: {row.usage_patterns[0]}"
            for row in facts.comparison_rows[:4]
            if row.usage_patterns
        ]
        if usage_rows:
            sections.extend(["", "## When to use each", *usage_rows[:4]])
    elif facts.answer_kind == "dita_element_comparison":
        if not facts.comparison_rows:
            return ""
        sections.extend(
            [
                "",
                "## Comparison",
                "| Element | What it does | Valid parents | Common attributes | Typical use |",
                "|---|---|---|---|---|",
            ]
        )
        for row in facts.comparison_rows[:4]:
            sections.append(
                "| "
                + " | ".join(
                    [
                        f"`<{_markdown_table_cell(row.label.strip('<>'))}>`",
                        _markdown_table_cell(row.definition),
                        _markdown_table_cell([f"`{value}`" for value in row.supported_elements[:8]]),
                        _markdown_table_cell([f"`{value}`" for value in row.companion_attributes[:8]]),
                        _markdown_table_cell(row.usage_patterns[:2]),
                    ]
                )
                + " |"
            )
        usage_rows = [
            f"- `<{row.label.strip('<>')}>`: {row.usage_patterns[0]}"
            for row in facts.comparison_rows[:4]
            if row.usage_patterns
        ]
        if usage_rows:
            sections.extend(["", "## When to use each", *usage_rows[:4]])
        mistakes = []
        for row in facts.comparison_rows[:4]:
            for mistake in row.common_mistakes[:2]:
                item = f"`<{row.label}>`: {mistake}"
                if mistake and item not in mistakes:
                    mistakes.append(item)
        if mistakes:
            sections.extend(["", "## Common mistakes", *[f"- {value}" for value in mistakes[:4]]])
    elif facts.answer_kind == "dita_element_family_overview":
        if not facts.comparison_rows:
            return ""
        sections.extend(["", "## Types"])
        for row in facts.comparison_rows[:4]:
            detail_parts = [item for item in [row.definition] if item]
            if row.usage_patterns:
                detail_parts.append(f"Typical use: {'; '.join(row.usage_patterns[:2])}")
            if row.supported_elements:
                detail_parts.append(
                    "Valid parents: " + ", ".join(f"`{value}`" for value in row.supported_elements[:5] if str(value).strip())
                )
            sections.append(f"- `<{row.label.strip('<>')}>`: {' '.join(detail_parts).strip()}")
        mistakes = []
        for row in facts.comparison_rows[:4]:
            for mistake in row.common_mistakes[:2]:
                item = f"`<{row.label}>`: {mistake}"
                if mistake and item not in mistakes:
                    mistakes.append(item)
        if facts.common_mistakes:
            for mistake in facts.common_mistakes[:4]:
                if mistake and mistake not in mistakes:
                    mistakes.append(mistake)
        usage_rows = [
            f"- `<{row.label.strip('<>')}>`: {row.usage_patterns[0]}"
            for row in facts.comparison_rows[:4]
            if row.usage_patterns
        ]
        if usage_rows:
            sections.extend(["", "## When to use each", *usage_rows[:4]])
        if mistakes:
            sections.extend(["", "## Common mistakes", *[f"- {value}" for value in mistakes[:4]]])
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
        if example_limit == 1:
            example_notes = _grounded_example_explanation_points(
                facts,
                snippet=facts.verified_examples[0].snippet,
            )
            if example_notes:
                sections.extend(["", "## Example explained", *[f"- {value}" for value in example_notes]])

    notes = []
    for item in facts.unsupported_points[:3]:
        if item not in notes:
            notes.append(item)
    for item in facts.semantic_warnings[:3]:
        if item not in notes:
            notes.append(item)
    if notes:
        sections.extend(["", "## Verification notes", *[f"- {value}" for value in notes]])

    # Strengthen hint when evidence is thin or retrieval confidence is low
    if facts.thin_evidence or facts.semantic_warnings:
        sections.extend([
            "",
            "## What would strengthen this answer",
            "- Share the XML snippet, element name, or attribute you're working with",
            "- Mention the DITA version or AEM Guides release if version-specific",
        ])

    return _repair_text_encoding_artifacts("\n".join(sections).strip())


async def _maybe_enrich_illustrative_dita_examples(
    *,
    question: str,
    facts: "NormalizedGroundedFactSet",
    tool_results_by_name: dict[str, Any],
    trace_id: str = "",
) -> "NormalizedGroundedFactSet":
    """Optionally call the LLM to generate illustrative DITA XML snippets when no verified examples exist.

    Only runs when:
    - CHAT_LLM_ILLUSTRATIVE_DITA_EXAMPLES feature flag is on
    - LLM is available
    - The question has clear example intent ("show me an example", "give a snippet", etc.)
    - facts.verified_examples is empty (no verified example already present)
    """
    import xml.etree.ElementTree as _ET
    from dataclasses import replace as _replace

    if not CHAT_LLM_ILLUSTRATIVE_DITA_EXAMPLES:
        return facts
    if not is_llm_available():
        return facts
    if not _EXAMPLE_INTENT_RE.search(question or ""):
        return facts
    if facts.verified_examples:
        return facts

    # Build context for snippet generation
    attr_name = ""
    attr_result = tool_results_by_name.get("lookup_dita_attribute") or {}
    if isinstance(attr_result, dict):
        attr_name = str(attr_result.get("attribute_name") or "").strip()

    element_hint = str(facts.canonical_definition or "").strip()[:200]
    element_names = ", ".join(f"`<{e}>`" for e in (facts.supported_elements or [])[:3])
    prompt = (
        f"Generate 1-2 short, well-formed DITA 1.3 XML snippets illustrating "
        f"{'`@' + attr_name + '`' if attr_name else 'this DITA construct'}.\n"
        f"Context: {element_hint}\n"
        f"{'Relevant elements: ' + element_names if element_names else ''}\n"
        "Return JSON: {\"snippets\": [\"<snippet1/>\", \"<snippet2/>\"]}. "
        "Snippets must be valid XML. Keep them minimal (3-5 lines max)."
    )

    try:
        raw = await generate_text(
            system_prompt="You generate minimal, correct DITA XML examples. Return only the JSON object.",
            user_prompt=prompt,
            max_tokens=400,
            step_name="chat_illustrative_dita_examples",
            trace_id=trace_id,
        )
        import json as _json
        raw_clean = str(raw or "").strip()
        # Find JSON object in the response
        _start = raw_clean.find("{")
        _end = raw_clean.rfind("}") + 1
        if _start < 0 or _end <= _start:
            return facts
        parsed = _json.loads(raw_clean[_start:_end])
        snippets = [str(s).strip() for s in (parsed.get("snippets") or []) if str(s).strip()]
    except Exception:
        return facts

    # Validate each snippet is well-formed XML
    valid_examples = []
    for snip in snippets[:2]:
        try:
            _ET.fromstring(snip)
            valid_examples.append(
                VerifiedExampleSnippet(
                    label="Illustrative example",
                    snippet=_normalize_verified_xml_snippet(snip),
                    source="llm_suggested",
                )
            )
        except Exception:
            pass

    if not valid_examples:
        return facts

    # Remove the stale "no snippet" warning since we now have one
    updated_warnings = [w for w in (facts.semantic_warnings or []) if w != _STALE_NO_VERIFIED_SNIPPET_WARNING]
    return _replace(
        facts,
        verified_examples=valid_examples,
        example_verified=False,
        example_source="illustrative_llm",
        generation_strategy="llm_illustrative_gap_fill",
        semantic_warnings=updated_warnings,
    )


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


def _should_enrich_grounded_answer_with_llm(
    question: str,
    facts: NormalizedGroundedFactSet | None,
) -> bool:
    if facts is None:
        return False
    if facts.answer_kind == "dita_element_family_overview":
        return True
    if facts.answer_kind in {"dita_element_comparison", "dita_attribute_comparison"}:
        return not bool(_EXPLICIT_COMPARISON_REQUEST_PATTERN.search(question or ""))
    return False


def _grounded_answer_shape_hint(
    question: str,
    facts: NormalizedGroundedFactSet | None,
) -> str:
    q = (question or "").strip()
    if facts is None:
        # Even without tool facts, inject shape guidance based on question form
        return _question_shape_hint(q)

    if facts.answer_kind == "dita_element_family_overview":
        return (
            "Answer as an overview of the main DITA table types and when to use each one. "
            "Do not force a comparison table unless the user explicitly asked to compare."
        )
    if facts.answer_kind in {"dita_element_comparison", "dita_attribute_comparison"} and not _EXPLICIT_COMPARISON_REQUEST_PATTERN.search(q):
        return (
            "The user did not explicitly ask for a comparison table. Prefer a natural overview that explains each item "
            "and when to use it, using a comparison table only if it genuinely improves clarity."
        )
    return _question_shape_hint(q)


def _question_shape_hint(question: str) -> str:
    """Return a shape/format hint for the LLM based on question type."""
    q = (question or "").strip()
    if not q:
        return ""
    hints: list[str] = []
    q_lower = q.lower()
    if _EXPLICIT_COMPARISON_REQUEST_PATTERN.search(q):
        hints.append(
            "Use a markdown comparison table (columns: feature/dimension; rows: each option). "
            "After the table, add a 1-paragraph 'When to choose X over Y' recommendation."
        )
    if _wants_full_example(q):
        hints.append(
            "If you include XML, prefer one full, self-contained example with the enclosing topic, map, or table structure instead of only a fragment. "
            "After the XML, briefly explain the expected result or why the example works."
        )
    elif _extract_example_shape_request(q):
        hints.append(
            "Include a verified XML example. Prefer a complete enclosing structure when the construct normally sits inside a map, topic, or table. "
            "After the XML, briefly explain what the processor or reader would see."
        )
    if _is_definition_style_question(q):
        hints.append(
            "Open with a direct one-sentence definition. "
            "Then cover: scope note, how it works in practice, key attributes or related concepts, an example, and common mistakes."
        )
    elif re.search(r"\bhow\s+do\s+I\b|\bhow\s+to\b|\bhow\s+can\s+I\b", q, re.IGNORECASE):
        hints.append(
            "Use numbered steps. Include a code block (XML or command) if the answer involves markup or CLI. "
            "End with a 'Common mistakes' note if applicable."
        )
    elif re.search(r"\bwhy\b|\bwhat.*wrong\b|\bproblem\b|\bfail(ed|ing)?\b|\berror\b", q, re.IGNORECASE):
        hints.append(
            "Lead with the most likely cause (1-2 sentences). "
            "Then: how to diagnose, the fix, and how to prevent it next time."
        )
    elif re.search(r"\blist\b|\ball\s+(the\s+)?(type|value|option|attr|element)\b", q, re.IGNORECASE):
        hints.append(
            "Use a markdown table or bullet list. Be exhaustive — list ALL values/options, not just common ones. "
            "Add a brief description for each."
        )
    return "\n\n".join(hints)


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
        "- Answer DITA, AEM Guides, DITA-OT, publishing, reuse, maps, and troubleshooting questions with grounded evidence.\n"
        "- Give senior-style XML examples, including full map or table context when the question needs it.\n"
        "- Run read-only research plans that look up DITA spec details, AEM Guides docs, tenant knowledge, and Jira matches before answering.\n"
        "- Review pasted DITA XML, explain what is wrong, and suggest safer fixes.\n"
        "- Search Jira and compare similar issues using verified search output.\n\n"
        f"Current workspace: `{tenant_id}`.\n\n"
        "Try one of these prompts:\n"
        "- What is keyscope in DITA? Show a full example.\n"
        "- How do I exclude draft-only content at publish time?\n"
        "- Review this DITA topic for conref, keyref, and keyword improvements.\n"
        "- Search Jira for issues about map validation and summarize the findings.\n"
        "- Why is my keyref not resolving in a root map with multiple submaps?\n"
        "- What does `processing-role=\"resource-only\"` do in a map?"
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
        "- Explain the difference between `<topicgroup>` and `<topichead>` with an example.\n"
        "- Review this draft for reuse, publishing, and AEM Guides readiness.\n\n"
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
    answer_mode: str | None = None,
    session_id: str = "",
    user_id: str = "chat-user",
) -> str:
    def _finalize(text: str) -> str:
        return _repair_text_encoding_artifacts(text).strip()

    trimmed = (user_content or "").strip()
    if _is_capability_prompt(trimmed):
        return _finalize(_builtin_capability_response(tenant_id))

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
        return _finalize(await _build_xml_review_fallback_response(trimmed, issue, tenant_id, rag_context=rag_context or ""))

    lowered = trimmed.lower()
    if issue_key and any(token in lowered for token in ("jira", "comment", "discussion", "outline", "task topic", "author guidance")):
        return _finalize(_build_issue_guidance_fallback(trimmed, issue, rag_context or "", tenant_id))

    resolved_answer_mode = str(answer_mode or _determine_answer_mode(trimmed, session_id=session_id)).strip().lower()
    if resolved_answer_mode in {"grounded_dita_answer", "grounded_aem_answer"}:
        try:
            evidence_pack, _retrieval_meta, grounded_tool_results = await _build_grounded_tool_evidence_pack(
                answer_mode=resolved_answer_mode,
                user_content=trimmed,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
            )
            if evidence_pack is not None:
                draft_answer, normalized_grounded_facts = _build_grounded_tool_draft_answer(
                    answer_mode=resolved_answer_mode,
                    question=trimmed,
                    tool_results_by_name=grounded_tool_results,
                )
                if not draft_answer.strip() and resolved_answer_mode == "grounded_dita_answer":
                    thin_answer = _build_thin_evidence_answer(
                        question=trimmed,
                        evidence_pack=evidence_pack,
                        unsupported=[],
                    ).strip()
                    if thin_answer:
                        return _finalize(thin_answer)
                if draft_answer.strip():
                    grounded_answer = await verify_grounded_answer(
                        question=trimmed,
                        draft_answer=draft_answer,
                        evidence_pack=evidence_pack,
                        verified_examples=(
                            [item.to_dict() for item in (normalized_grounded_facts.verified_examples if normalized_grounded_facts else [])]
                        ),
                        structured_tool_answer=normalized_grounded_facts is not None,
                    )
                    if _looks_like_retrieval_summary(grounded_answer.answer) and grounded_answer.grounding_status in {"partial", "abstain", "conflict"}:
                        grounded_answer = replace(
                            grounded_answer,
                            answer=_build_thin_evidence_answer(
                                question=trimmed,
                                evidence_pack=evidence_pack,
                                unsupported=grounded_answer.unsupported_points,
                            ),
                            unsupported_points=grounded_answer.unsupported_points[:4],
                            grounding_status="partial",
                            reason="The offline fallback rewrote a retrieval-style answer into plain guidance.",
                        )
                    if grounded_answer.answer.strip():
                        return _finalize(grounded_answer.answer)
        except Exception as exc:
            logger.warning_structured(
                "Local grounded fallback skipped",
                extra_fields={"tenant_id": tenant_id, "answer_mode": resolved_answer_mode, "error": str(exc)},
                exc_info=True,
            )

    if rag_context:
        return _finalize(_build_rag_grounded_fallback_response(trimmed, rag_context, tenant_id, issue_key=issue_key))

    return _finalize(_builtin_unavailable_response(trimmed, tenant_id))


def _build_compact_chat_system_prompt(
    rag_context: str = "",
    *,
    human_prompts: bool = False,
    skill_guidance: str = "",
) -> str:
    """Compact system prompt for grounded chat — fits within Groq 12K TPM limit.

    Retains the key answer-quality rules from chat_system.json without the
    full 37K prompt.  Total size ~3-4K chars (~800-1000 tokens).
    """
    base = (
        "You are **DITA Dataset Studio Chat** — a senior assistant for DITA XML, "
        "AEM Guides, and technical documentation. Use a clear, professional tone "
        "appropriate for enterprise technical communication.\n\n"
        "# VOICE AND STRUCTURE\n"
        "- Open with a direct answer; follow with `##` sections only as needed.\n"
        "- Never open with retrieval-language like 'Retrieved DITA specification guidance' unless the user explicitly asks for sources.\n"
        "- Make each reply self-contained: the reader should understand without guessing from prior turns.\n"
        "- Prefer precise terminology; avoid marketing tone and filler.\n"
        "- Use emoji or decorative callouts sparingly; only when they aid scanning.\n\n"
        "# ANSWER RULES\n"
        "1. **XML examples**: Include when the user asks for examples or when a short, spec-aligned snippet "
        "is essential. Never invent element nesting or attributes. Do not force XML into purely UI or "
        "product-navigation questions.\n"
        "2. **Common mistakes**: If evidence lists common mistakes, add a concise **Common mistakes** subsection "
        "with incorrect vs correct patterns (prose or XML as fits).\n"
        "3. **Be specific**: Name parents, children, and attributes that matter. Do not say "
        "'various attributes' — enumerate them.\n"
        "4. **Comparisons** (vs / compare / difference between): Use a **markdown table** with columns for each "
        "item compared (e.g. purpose, content model, typical parents, when to use). Bullet-only side-by-side "
        "comparisons are insufficient for element or attribute comparisons.\n"
        "5. **Depth**: Structural DITA topics need enough depth (multiple sections). Narrow factual questions "
        "may be shorter while remaining complete.\n"
        "6. **Markdown**: Use `##`, bullets, fenced code blocks; **bold** or `backticks` for element and attribute names.\n"
        "7. **Evidence**: Ground claims in context supplied below. If evidence is thin or conflicting, keep the answer useful "
        "and direct, then add a brief caveat; do not replace the answer with a source-by-source recap or a retrieval summary.\n"
        "8. **Tool results**: When the UI already shows a structured tool card (e.g. DITA element tables), do not "
        "repeat the entire table in prose. Add interpretation, tradeoffs, and practical guidance.\n"
        "9. Do not invent download URLs, undocumented product behavior, or citations not present in context.\n\n"
        "# ANSWER PATTERNS (choose what fits)\n"
        "- **Definitional**: Overview, content model, attributes, optional example, common mistakes.\n"
        "- **Comparison**: Short lead-in, **comparison table**, when to use each, optional examples.\n"
        "- **How-to**: Prerequisites, numbered steps, optional snippet, caveats.\n"
        "- **Troubleshooting**: Likely cause, checks, fix.\n\n"
        "Do **not** use a rigid global template of '## Short answer / ## How it works / ## What is verified' for "
        "normal chat replies. (Long-form **agent research** answers use a separate prescribed outline from the "
        "synthesis step.)\n"
    )
    # Evidence discipline: always remind the LLM not to echo evidence ID labels in replies
    base += (
        "\n\n# EVIDENCE HANDLING\n"
        "No evidence line tags ([E1], [E2], etc.) should appear in your reply unless the user prompt explicitly asks you to cite them. "
        "If the evidence block contains such labels, use them only when the user prompt says to; otherwise, ignore those labels in your output."
    )

    if skill_guidance:
        base += f"\n\n# ANSWERING GUIDANCE\n{skill_guidance}"
    if rag_context:
        base += f"\n\n# REFERENCE KNOWLEDGE\n{rag_context}"
        if "DITA OPEN TOOLKIT GITHUB ISSUES" in rag_context:
            base += (
                "\n\n# DITA-OT GITHUB CONTEXT\n"
                "When DITA Open Toolkit GitHub issues appear above, the reader may be new to hierarchical "
                "conditional processing or subject schemes. Explain expected vs reported toolkit behavior plainly; "
                "cite issue URLs from context; treat open issues as community reports — verify on the user's OT version."
            )
    if human_prompts:
        addon = _get_human_precision_addon().strip()
        if addon:
            base += f"\n\n# PRECISION MODE\n{addon}"

    # Optional follow-up suggestions block (env-gated)
    _suggest_followups_env = os.environ.get("CHAT_SUGGEST_FOLLOWUPS", "").strip().lower()
    if _suggest_followups_env in ("1", "true", "yes", "on"):
        base += (
            "\n\n# FOLLOW-UP SUGGESTIONS\n"
            "After your answer, optionally add a `## Next questions` section with 2-3 short follow-up questions "
            "the user might want to ask next. Keep each one to one line."
        )

    return base


def _build_grounded_answer_system_prompt(*, human_prompts: bool = False) -> str:
    """Legacy structured prompt — kept for heuristic fallback paths only."""
    return _build_compact_chat_system_prompt(human_prompts=human_prompts)


def _recent_chat_transcript(session_id: str, *, limit: int = 15) -> str:
    # Fetch more than needed so we can slice the LATEST `limit` messages
    rows = get_messages(session_id, limit=limit * 4)
    rows = rows[-limit:]
    if not rows:
        return ""
    lines: list[str] = []
    for row in rows:
        role = str(row.get("role") or "").strip().lower()
        content = str(row.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        # Increased from 500 → 1500 chars so multi-turn context is preserved
        lines.append(f"{role.title()}: {content[:1500]}")
    return "\n".join(lines[-limit:])


_FOLLOW_UP_ANAPHORA = re.compile(
    r"\b(this|that|it|those|these|the same|also|as well|too|instead|above|previous)\b",
    re.IGNORECASE,
)


def _is_follow_up_question(text: str) -> bool:
    """Return True if the question is likely a follow-up referencing prior context."""
    t = (text or "").strip()
    if not t:
        return False
    word_count = len(t.split())
    if word_count <= 5:
        return True   # "what about conref?" "give me an example"
    return bool(_FOLLOW_UP_ANAPHORA.search(t))


def _expand_query_with_context(query: str, transcript: str) -> str:
    """Prepend the prior assistant topic to follow-up queries for better RAG retrieval."""
    if not transcript or not _is_follow_up_question(query):
        return query
    for line in reversed(transcript.splitlines()):
        if line.startswith("Assistant:"):
            topic = line[10:].strip()[:80].split(".")[0].strip()
            if topic and len(topic) > 10:
                return f"{topic} — {query}"
    return query


def _fetch_last_messages_for_session(session_id: str, limit: int = 10) -> list[dict]:
    """Return the last `limit` messages of any role (oldest first, newest last)."""
    rows = get_messages(session_id, limit=limit * 2)
    return rows[-limit:]


def _fetch_last_user_messages_for_session(session_id: str, *, limit: int = 10) -> list[str]:
    """Return the last `limit` user message content strings (oldest first, newest last)."""
    rows = get_messages(session_id, limit=limit * 2)
    user_msgs = [
        str(r.get("content") or "").strip()
        for r in rows
        if r.get("role") == "user" and r.get("content")
    ]
    return user_msgs[-limit:]


def _recent_user_messages_before_latest(session_id: str, latest: str, *, limit: int = 3) -> list[str]:
    """Return up to `limit` user messages immediately before `latest` in the session."""
    all_msgs = _fetch_last_user_messages_for_session(session_id, limit=limit + 5)
    if all_msgs and all_msgs[-1].strip() == latest.strip():
        all_msgs = all_msgs[:-1]
    return all_msgs[-limit:]


_DRAFT_COMMENT_RE = re.compile(r"\bdraft.?comment", re.IGNORECASE)  # no trailing \b — matches "draft-comments" too
_OT_ARGS_CONTEXT_RE = re.compile(r"\barg(?:s|ument)?s?\b|\bdita.?ot\b|\bpdf\b|\bpublish\b", re.IGNORECASE)


def _expand_follow_up_retrieval_query(session_id: str, query: str) -> str:
    """Expand a follow-up query with context from prior user messages in the session."""
    prior = _recent_user_messages_before_latest(session_id, query, limit=5)
    if not prior:
        return query

    parts: list[str] = [query]

    # If prior messages mention draft-comment and current is about DITA-OT args → expand
    draft_prior = [m for m in prior if _DRAFT_COMMENT_RE.search(m)]
    if draft_prior and _OT_ARGS_CONTEXT_RE.search(query):
        if "args.draft" not in query:
            parts.append("args.draft --args.draft=yes")
        # Include the prior message so "draft-comments" appears in merged string
        parts.insert(0, draft_prior[0].strip()[:120])
    elif _is_follow_up_question(query) and prior:
        topic_hint = prior[-1][:100].strip()
        if topic_hint:
            parts.insert(0, f"Follow-up: {topic_hint}")

    return " — ".join(parts) if len(parts) > 1 else parts[0]


_TUTORIAL_DEPTH_TRIGGERS = re.compile(
    r"\bprocessing.role\b|\bresource.only\b|\btoc\b|\bnavigation\b|\bmap\s+hierarchy\b|\bcondition.*filter\b",
    re.IGNORECASE,
)


def _grounded_dita_tutorial_depth_addon(question: str) -> str:
    """Return a TUTORIAL DEPTH instruction block for complex DITA structural questions.

    Returns empty string for simple/unrelated questions.
    """
    if not _TUTORIAL_DEPTH_TRIGGERS.search(question or ""):
        return ""
    return (
        "## TUTORIAL DEPTH GUIDANCE\n"
        "This question involves a structural DITA concept that benefits from a deeper tutorial-style answer:\n"
        "- Explain the concept with a concrete example (a real toc/map scenario)\n"
        "- Show how it affects the output (toc, navigation, conditional filtering)\n"
        "- Mention the common misunderstanding or mistake\n"
        "- Keep it tutorial-style, not just a definition"
    )


_EVIDENCE_ID_RE = re.compile(r"\[E\d+\]")


def _build_grounded_answer_user_prompt(
    *,
    question: str,
    evidence_context: str,
    transcript: str,
    corrected_query: str = "",
    correction_applied: bool = False,
    structured_answer_hint: str = "",
    answer_shape_hint: str = "",
    tutorial_depth_addon: str = "",
) -> str:
    parts = [f"Question:\n{question}"]
    if transcript:
        parts.append(f"Recent conversation:\n{transcript}")
    if correction_applied and corrected_query:
        parts.append(f"Retrieval query used:\n{corrected_query}")
    if structured_answer_hint.strip():
        parts.append(f"Grounded structured facts:\n{structured_answer_hint.strip()[:2000]}")

    has_evidence_ids = bool(_EVIDENCE_ID_RE.search(evidence_context or ""))
    evidence_instruction = (
        "Write in a natural assistant voice. Base the answer on the evidence above, but do not narrate the retrieval process. "
        "If evidence is thin or conflicting, answer directly with the best supported explanation, then add a short caution in a `## Verification notes` section."
    )
    if has_evidence_ids:
        evidence_instruction += (
            " The evidence paragraphs above are labeled [E1], [E2], etc. "
            "You may cite them inline as [E1] where relevant, but ignore those labels if the answer flows better without them."
        )
    parts.append(f"Evidence:\n{evidence_context}\n\n{evidence_instruction}")

    if answer_shape_hint.strip():
        parts.append(f"Answer shape guidance:\n{answer_shape_hint.strip()}")
    if tutorial_depth_addon.strip():
        parts.append(tutorial_depth_addon.strip())
    return "\n\n".join(parts)


def _stream_text_chunks(text: str) -> list[str]:
    cleaned = _repair_text_encoding_artifacts(_coerce_llm_text_response(text)).strip()
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


async def _build_chat_evidence_pack(
    user_content: str,
    tenant_id: str,
    *,
    transcript: str = "",
) -> tuple[object, dict]:
    # Expand follow-up queries with prior conversation context for better retrieval
    retrieval_query = _expand_query_with_context(user_content, transcript)
    rag_result = await run_chat_corrective_rag(retrieval_query, tenant_id=tenant_id)
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
                content=_repair_text_encoding_artifacts(content),
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

    capped_query = query[:RAG_QUERY_MAX_CHARS]
    parts = []

    try:
        if _LEARNED_QA_DOMAIN_PATTERN.search(query):
            learned_context = format_learned_qa_for_prompt(capped_query, k=3)
            if learned_context:
                parts.append(learned_context[:RAG_CONTEXT_MAX_CHARS])
    except Exception as e:
        logger.debug_structured("RAG learned QA failed", extra_fields={"error": str(e)})

    # AEM Guides docs (increased k and snippet size for better retrieval)
    try:
        docs = retrieve_relevant_docs(
            capped_query,
            k=RAG_AEM_K,
            max_snippet_chars=RAG_SNIPPET_CHARS,
        )
        if docs:
            if HIERARCHICAL_RETRIEVAL_ENABLED:
                # Phase C3: Use hierarchical retriever formatting for richer context.
                # This builds a RetrievalBundle from flat retrieval results and formats
                # with structured headers (doc_type/element_name). No async expansion
                # yet — full parent/child/conref expansion requires CHUNK_METADATA_ENABLED
                # and an async retrieval path (future enhancement).
                try:
                    primary_chunks = [
                        ScoredChunk(
                            chunk_id=f"aem_{i}",
                            content=d.get("snippet", ""),
                            metadata=ChunkMetadata(
                                chunk_id=f"aem_{i}",
                                source_type="crawl",
                                source_url=d.get("url", ""),
                                doc_type="aem_doc",
                                element_name=d.get("title", "doc"),
                                section_title=d.get("title", ""),
                            ),
                            semantic_similarity=max(0.0, 1.0 - i * 0.05),
                            authority_score=0.78,
                            structural_relevance=0.0,
                            final_score=max(0.0, 1.0 - i * 0.05) * 0.40 + 0.78 * 0.25,
                            relationship_type=None,
                        )
                        for i, d in enumerate(docs)
                    ]
                    bundle = RetrievalBundle(
                        primary_chunks=primary_chunks,
                        context_chunks=[],
                        total_tokens=sum(max(1, len(c.content) // 3) for c in primary_chunks),
                        root_docs=[],
                        relationships_used=[],
                        query=capped_query,
                    )
                    formatted = format_bundle_for_prompt(bundle, max_chars=RAG_CONTEXT_MAX_CHARS)
                    if formatted:
                        parts.append("AEM GUIDES DOCUMENTATION:\n" + formatted)
                    logger.debug_structured(
                        "Hierarchical retrieval formatting used",
                        extra_fields={"num_chunks": len(primary_chunks)},
                    )
                except Exception as he:
                    # Fallback to flat formatting if hierarchical formatting fails
                    logger.warning(
                        f"Hierarchical formatting failed, falling back to flat: {he}"
                    )
                    formatted = format_docs_for_prompt(docs)
                    if formatted:
                        parts.append("AEM GUIDES DOCUMENTATION:\n" + formatted)
            else:
                formatted = format_docs_for_prompt(docs)
                if formatted:
                    parts.append("AEM GUIDES DOCUMENTATION:\n" + formatted)
    except Exception as e:
        logger.debug_structured("RAG AEM docs failed", extra_fields={"error": str(e)})

    # DITA spec — skip for DITA-OT error/build-failure queries (spec is noise there)
    if not _DITA_OT_ERROR_PATTERN.search(query):
        try:
            dita_chunks = retrieve_dita_knowledge(capped_query, k=RAG_DITA_K)
            if dita_chunks:
                dita_parts = []
                for i, c in enumerate(dita_chunks[:RAG_DITA_K], 1):
                    dita_parts.append(_format_dita_chunk(c, i, max_text_chars=RAG_SNIPPET_CHARS))
                if dita_parts:
                    parts.append("DITA SPEC REFERENCE:\n" + "\n\n".join(dita_parts))
        except Exception as e:
            logger.debug_structured("RAG DITA failed", extra_fields={"error": str(e)})

    try:
        tenant_chunks = retrieve_tenant_context(capped_query, tenant_id=tenant_id, k=4)
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
        example_chunks = retrieve_tenant_examples(capped_query, tenant_id=tenant_id, k=2)
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
        claude_ctx = retrieve_claude_code_context(capped_query)
        if claude_ctx:
            parts.append("CLAUDE CODE / ADOBE AI SETUP:\n" + claude_ctx)
    except Exception as e:
        logger.debug_structured("RAG Claude Code failed", extra_fields={"error": str(e)})

    # DITA OT GitHub issues (publishing, transtype, plugin, XSLT queries)
    try:
        from app.services.dita_ot_github_rag_service import retrieve_dita_ot_github_for_query
        ot_issues = retrieve_dita_ot_github_for_query(capped_query, k=3)
        if ot_issues:
            ot_parts = []
            for issue in ot_issues:
                title = issue.get("title", "")
                url = issue.get("url", "")
                is_ref = issue.get("source") == "dita_ot_github_reference"
                cap = 3500 if is_ref else 600
                snippet = (issue.get("snippet") or "")[:cap]
                ot_parts.append(f"Issue: {title}\nURL: {url}\n{snippet}")
            parts.append("DITA OPEN TOOLKIT GITHUB ISSUES:\n" + "\n\n".join(ot_parts))
    except Exception as e:
        logger.debug_structured("RAG DITA OT GitHub failed", extra_fields={"error": str(e)})

    # Jira QA knowledge base (bug reports, QA patterns, past resolutions)
    try:
        from app.services.embedding_service import embed_query as _embed_query, is_embedding_available
        from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, query_collection as _qc
        if is_embedding_available():
            _jira_emb = _embed_query(capped_query)
            if _jira_emb:
                _jira_rows = _qc(CHROMA_COLLECTION_JIRA_QA, _jira_emb, k=3)
                if _jira_rows:
                    jira_rag_parts = []
                    for row in _jira_rows:
                        meta = row.get("metadata") or {}
                        jira_key = meta.get("jira_key", "")
                        title = meta.get("title", "") or meta.get("summary", "")
                        chunk_type = meta.get("chunk_type", "")
                        doc = (row.get("document") or "")[:500]
                        if doc:
                            header = jira_key or "Issue"
                            if title:
                                header += f": {title}"
                            if chunk_type:
                                header += f" [{chunk_type}]"
                            jira_rag_parts.append(f"{header}\n{doc}")
                    if jira_rag_parts:
                        parts.append("JIRA QA KNOWLEDGE BASE:\n" + "\n\n".join(jira_rag_parts))
    except Exception as e:
        logger.debug_structured("RAG Jira QA failed", extra_fields={"error": str(e)})

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
            if recipe_type == "freeform":
                affected_artifacts.append("Freeform dataset job based on your chat prompt")
            else:
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
    from app.services.chat_tools import _FREEFORM_REDIRECT_PATTERN
    from app.services.jira_generate_resolve import (
        extract_issue_key_from_generation_request,
        fetch_issue_text_for_generate,
    )

    # Enrich the preview text with full Jira issue content + LLM deep analysis
    # so the contract builder sees description, steps, subject, recommended topics.
    from app.services.jira_generate_resolve import (
        enrich_jira_text_with_analysis,
    )
    import re as _re_kd2
    _JIRA_KEYREF_DIRECT_RE = _re_kd2.compile(
        r"\b(keydef|keyref|keyscope|keys?\s+map|keymap|insert.*keyword|keyword.*insert"
        r"|key\s+def|key\s+reference|keys\s+def)\b",
        _re_kd2.IGNORECASE,
    )
    _jira_key = extract_issue_key_from_generation_request(text or "")
    _jira_is_keyref = False
    if _jira_key:
        _issue_text, _jira_err = fetch_issue_text_for_generate(_jira_key)
        if _issue_text:
            # Check DIRECTLY if the Jira issue is about keyref/keymap — no LLM needed
            _jira_is_keyref = bool(_JIRA_KEYREF_DIRECT_RE.search(_issue_text[:2000]))
            # Run LLM analysis to extract DITA concepts & topic recommendations
            _enriched = enrich_jira_text_with_analysis(_issue_text, issue_key=_jira_key)
            text = f"{_enriched}\n\n## Generation Request\n{text}"

    # Freeform check: use original request, "DITA keyref scenario" marker, OR direct Jira text match
    _original_request = text or ""
    _gen_req_idx = _original_request.rfind("\n## Generation Request\n")
    _gen_req_section = _original_request
    if _gen_req_idx >= 0:
        _gen_req_section = _original_request[_gen_req_idx + len("\n## Generation Request\n"):]
    _is_freeform = bool(_FREEFORM_REDIRECT_PATTERN.search(_gen_req_section))
    # Primary: direct Jira text match (most reliable — no LLM needed)
    if not _is_freeform and _jira_is_keyref:
        _is_freeform = True
    # Fallback: LLM analysis marker
    if not _is_freeform and "DITA keyref scenario" in (_original_request or ""):
        _is_freeform = True
    if _is_freeform:
        # Freeform advanced-construct request: skip the contract service entirely.
        # execute_generate_dita will detect the same keywords and redirect to
        # execute_create_job(freeform), so we just need plan_status="proposed".
        preview = {"status": "preview_ready", "summary": "Freeform DITA bundle generation"}
        bundle_contract = None
        preview_ready = True
        clarification_required = False
    else:
        preview = build_generate_dita_preview(text=text, instructions=instructions)
        bundle_contract = build_generate_dita_execution_contract(preview=preview)
        preview_status = str(preview.get("status") or "").strip().lower()
        preview_ready = preview_status == "preview_ready"
        clarification_required = preview_status == "clarification_required" or bool(preview.get("clarification_needed"))
    title = "Generate DITA bundle"
    step_status = "pending" if preview_ready else "blocked"
    summary = str(preview.get("summary") or "Preview the DITA bundle before generation.").strip()
    plan_status = "proposed" if preview_ready else ("unsupported" if str(preview.get("status") or "").strip().lower() == "unsupported" else "clarification_required")
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

    return "\n\n".join(sections)


def _messages_to_llm_format(messages: list[dict]) -> list[dict]:
    """Convert DB messages to LLM format (role + content).

    When an assistant message has tool_results, append a compact summary so the LLM
    can reason about previous tool invocations on subsequent turns.
    """
    out = []
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role in ("user", "assistant") and content:
            enriched = content
            if role == "assistant":
                tool_results = m.get("tool_results")
                if isinstance(tool_results, dict) and tool_results:
                    summary = _summarize_tool_results_for_context(tool_results)
                    if summary:
                        enriched = f"{content}\n\n[Previous tool results: {summary}]"
            out.append({"role": role, "content": enriched})
    return out


def _summarize_tool_results_for_context(tool_results: dict) -> str:
    """Build a compact summary of tool results for LLM context (< 300 chars per tool)."""
    parts: list[str] = []
    for name, result in tool_results.items():
        if name == "_grounding":
            continue  # Skip grounding metadata
        if not isinstance(result, dict):
            continue
        if result.get("error"):
            parts.append(f"{name}: error - {str(result['error'])[:100]}")
        elif name == "generate_dita":
            jira_id = result.get("jira_id", "")
            dl = result.get("download_url", "")
            parts.append(f"{name}: jira_id={jira_id}, download_url={dl}")
        elif name == "create_job":
            parts.append(f"{name}: job_id={result.get('job_id', '')}, status={result.get('status', '')}")
        elif name == "search_jira_issues":
            issues = result.get("issues", [])
            parts.append(f"{name}: {len(issues)} issues found")
        elif name == "review_dita_xml":
            parts.append(f"{name}: score={result.get('quality_score', '?')}")
        elif name == "lookup_dita_spec":
            chunks = result.get("spec_chunks", [])
            parts.append(f"{name}: {len(chunks)} spec results")
        elif name == "list_jobs":
            jobs = result.get("jobs", [])
            parts.append(f"{name}: {len(jobs)} jobs listed")
        else:
            parts.append(f"{name}: completed")
    return "; ".join(parts)


def _truncate_messages_for_context(messages: list[dict], max_messages: int = CHAT_CONTEXT_WINDOW_MESSAGES) -> list[dict]:
    """Sliding window: keep only the most recent messages to fit LLM context."""
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]


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
            "If evidence is incomplete, state exactly what could not be verified.\n"
            "Use a professional tone. Avoid emoji unless the evidence uses them.\n"
            "Return markdown with exactly these sections in order:\n"
            "## Summary\n"
            "## Details\n"
            "## Limits of evidence\n"
            "## Recommended next step\n"
            "## Sources\n"
            "In **Summary**, give 2–4 sentences with the direct answer.\n"
            "In **Details**, use concrete bullets derived only from the evidence.\n"
            "In **Limits of evidence**, list gaps, uncertainty, or topics not covered by the evidence.\n"
            "In **Recommended next step**, suggest one actionable follow-up the user should take. Omit if not applicable.\n"
            "In **Sources**, list only sources that appear in the evidence block.\n"
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
                max_tokens=1600,
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

    if is_chat_guidance_only_mode() and _plan_contains_chat_generation_redirect(plan):
        redirect_text = _build_builder_handoff_message(
            plan.get("user_request") or state.get("message", {}).get("content") or user_content,
            legacy_plan=True,
        )
        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            redirect_text,
            tool_results={
                "_builder_handoff": {
                    "builder_path": "/builder",
                    "reason": "chat_guidance_only",
                    "legacy_plan_blocked": True,
                }
            },
        )
        async for event in _emit_streamed_text(redirect_text):
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
        structured_fallback_answer = draft_answer
        grounding_path = "tool_only"
        llm_enriched = False
        _has_spec_tool_evidence = bool(
            grounded_tool_results.get("lookup_dita_spec") or grounded_tool_results.get("lookup_dita_attribute")
        )
        should_enrich_with_llm = _should_enrich_grounded_answer_with_llm(question, normalized_grounded_facts)
        if (not draft_answer or should_enrich_with_llm) and is_llm_available():
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
            evidence_ctx_for_prompt = evidence_ctx[:3000]
            if evidence_pack.decision.status in {"abstain", "conflict"}:
                evidence_ctx_for_prompt = (
                    "The indexed evidence is thin or conflicting. Answer directly from your general DITA knowledge in a "
                    "helpful, natural voice, then add a short `## Verification notes` section.\n\n"
                    "Do not echo the evidence snippets or write a retrieval recap."
                )
            answer_shape_hint = _grounded_answer_shape_hint(question, normalized_grounded_facts)
            if evidence_pack.decision.status in {"abstain", "conflict"}:
                thin_evidence_hint = (
                    "The retrieved evidence is thin or conflicting. Answer directly in natural prose with the best supported "
                    "interpretation, then add a brief `## Verification notes` section. Do not start with 'Retrieved ...' "
                    "or turn the answer into a source-by-source recap."
                )
                answer_shape_hint = "\n\n".join(part for part in [answer_shape_hint, thin_evidence_hint] if part)
            structured_answer_hint = (
                draft_answer
                if should_enrich_with_llm and evidence_pack.decision.status not in {"abstain", "conflict"}
                else ""
            )
            try:
                llm_draft = await generate_text(
                    system_prompt=_build_compact_chat_system_prompt(rag_context=_build_rag_context(question, tenant_id=tenant_id), skill_guidance=_select_skill_guidance(question)),
                    user_prompt=_build_grounded_answer_user_prompt(
                        question=question,
                        evidence_context=evidence_ctx_for_prompt,
                        transcript=transcript,
                        corrected_query=str(retrieval_meta.get("corrected_query") or ""),
                        correction_applied=bool(retrieval_meta.get("correction_applied")),
                        structured_answer_hint=structured_answer_hint,
                        answer_shape_hint=answer_shape_hint,
                    ),
                    max_tokens=1600,
                    step_name="chat_mixed_grounded_dita_answer",
                    trace_id=trace_id,
                )
                if str(llm_draft or "").strip():
                    draft_answer = llm_draft
                    grounding_path = "tool_plus_llm"
                    llm_enriched = True
            except Exception as exc:
                logger.warning_structured(
                    "Grounded DITA LLM enrichment skipped",
                    extra_fields={"trace_id": trace_id, "error": str(exc)},
                )

        grounded_answer = await verify_grounded_answer(
            question=question,
            draft_answer=draft_answer,
            evidence_pack=evidence_pack,
            verified_examples=(
                [item.to_dict() for item in (normalized_grounded_facts.verified_examples if normalized_grounded_facts else [])]
            ),
            structured_tool_answer=normalized_grounded_facts is not None and not llm_enriched,
            structured_fallback_answer=structured_fallback_answer if llm_enriched else "",
        )
        if _looks_like_retrieval_summary(grounded_answer.answer) and grounded_answer.grounding_status in {"partial", "abstain", "conflict"}:
            grounded_answer = replace(
                grounded_answer,
                answer=_build_thin_evidence_answer(
                    question=question,
                    evidence_pack=evidence_pack,
                    unsupported=grounded_answer.unsupported_points,
                ),
                unsupported_points=grounded_answer.unsupported_points[:4],
                grounding_status="partial",
                reason="The answer was rewritten into a clearer plain-language summary because the draft still read like a retrieval recap.",
            )
        if evidence_pack.decision.status in {"abstain", "conflict"}:
            grounded_answer = replace(
                grounded_answer,
                answer=_build_thin_evidence_answer(
                    question=question,
                    evidence_pack=evidence_pack,
                    unsupported=grounded_answer.unsupported_points,
                ),
                unsupported_points=grounded_answer.unsupported_points[:4],
                grounding_status="partial",
                reason="The draft answer was rewritten into a clearer plain-language summary because the evidence was too thin.",
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

    if is_chat_guidance_only_mode():
        handoff_text = _build_builder_handoff_message(
            user_content,
            blocked_tool="generate_dita",
            mixed_intent=True,
        )
        final_text = "\n\n---\n\n".join(
            part for part in [answer_text.strip() if answer_text else "", handoff_text] if part
        ).strip()
        tool_results: dict[str, Any] = {
            "_builder_handoff": {
                "builder_path": "/builder",
                "reason": "chat_guidance_only",
                "blocked_tool": "generate_dita",
                "mixed_intent": True,
            }
        }
        if grounding:
            tool_results["_grounding"] = grounding
        _persist_assistant_message(session_id, assistant_msg_id, final_text, tool_results=tool_results)
        async for event in _emit_streamed_text(final_text):
            yield event
        yield {"type": "done"}
        return

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

    if is_chat_guidance_only_mode() and _is_chat_generation_redirect_tool(tool_name):
        redirect_text = _build_builder_handoff_message(
            user_content,
            blocked_tool=tool_name,
        )
        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            redirect_text,
            tool_results={
                "_builder_handoff": {
                    "builder_path": "/builder",
                    "reason": "chat_guidance_only",
                    "blocked_tool": tool_name,
                }
            },
        )
        async for event in _emit_streamed_text(redirect_text):
            yield event
        yield {"type": "done"}
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
                "Ask something like `generate a DITA task topic from this screenshot` or "
                "`create a dataset from this attached image` (with screenshot authoring options enabled) "
                "and I’ll run the staged authoring pipeline."
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
    # DITA-OT error codes / build failures must use default mode — the DITA spec
    # lookup (grounded_dita_answer) returns element docs, not error resolutions.
    if _DITA_OT_ERROR_PATTERN.search(user_content):
        answer_mode = "default"
    # Comparison questions need the OT guidance table, not the native PDF config tool
    elif _DITA_OT_COMPARISON_PATTERN.search(user_content):
        answer_mode = "default"
    # Authoring strategy questions need authoring guidance (default mode).
    # BUT if the query is specifically a DITA element/attribute lookup (structural+intent),
    # keep grounded_dita_answer so the spec lookup returns the right info.
    elif _DITA_AUTHORING_PATTERN.search(user_content) and not _is_dita_answer_request(user_content):
        answer_mode = "default"

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

    if is_chat_guidance_only_mode() and route_decision.intent in {"dataset_job", "dita_generation"}:
        redirect_text = _build_builder_handoff_message(
            user_content,
            blocked_tool="generate_dita" if route_decision.intent == "dita_generation" else "",
        )
        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            redirect_text,
            tool_results={
                "_builder_handoff": {
                    "builder_path": "/builder",
                    "reason": "chat_guidance_only",
                    "route_intent": route_decision.intent,
                }
            },
        )
        async for event in _emit_streamed_text(redirect_text):
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

    if route_decision.intent == "dita_generation" and policy_decision.action in {"preview_first", "clarify_first"} and not _DITA_AUTHORING_PATTERN.search(user_content):
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

    if _should_use_tool_mode(user_content, session_id=session_id):
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
            answer_mode=answer_mode,
            session_id=session_id,
            user_id=user_id,
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
            # Pass transcript so follow-up queries get expanded with prior context
            _pre_transcript = _recent_chat_transcript(session_id)
            evidence_pack, retrieval_meta = await _build_chat_evidence_pack(
                user_content, tenant_id, transcript=_pre_transcript
            )
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
        structured_fallback_answer = draft_answer
        grounding_path = "tool_only"
        llm_enriched = False
        _has_spec_tool_evidence_gen = bool(
            grounded_tool_results.get("lookup_dita_spec") or grounded_tool_results.get("lookup_dita_attribute")
        )
        should_enrich_with_llm = _should_enrich_grounded_answer_with_llm(user_content, normalized_grounded_facts)
        # For OT-domain queries, the spec tool returns element docs (not OT param docs).
        # Force LLM synthesis so it uses the AEM/OT evidence from the lookup_aem_guides tool.
        if retrieval_meta.get("source_domain") == "dita_ot" and grounded_tool_results.get("lookup_aem_guides"):
            should_enrich_with_llm = True
        if (not draft_answer or should_enrich_with_llm) and is_llm_available():
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
            evidence_ctx_for_prompt = evidence_ctx[:3000]
            if evidence_pack.decision.status in {"abstain", "conflict"}:
                evidence_ctx_for_prompt = (
                    "The indexed evidence is thin or conflicting. Answer directly from your general DITA knowledge in a "
                    "helpful, natural voice, then add a short `## Verification notes` section.\n\n"
                    "Do not echo the evidence snippets or write a retrieval recap."
                )
            # DITA-OT error codes / build failures: spec evidence is irrelevant —
            # the DITA-OT GitHub issues in rag_context are the authoritative source.
            elif _DITA_OT_ERROR_PATTERN.search(user_content):
                evidence_ctx_for_prompt = (
                    "The spec evidence above is NOT relevant to this build error or publishing issue. "
                    "Answer from the DITA-OT GitHub issues in the context below and your own knowledge. "
                    "Be direct and empathetic — give the fix or cause first. "
                    "If you see a relevant GitHub issue, cite it with the URL."
                )
            # Authoring strategy / keyscopes / content reuse: the indexed spec evidence may not
            # cover the question. Answer fully from the DITA AUTHORING GUIDANCE in the system prompt.
            elif _DITA_AUTHORING_PATTERN.search(user_content):
                evidence_ctx_for_prompt = (
                    "The indexed spec evidence may not directly cover this authoring question. "
                    "Answer fully and helpfully from the DITA AUTHORING GUIDANCE and ANSWERING GUIDANCE "
                    "sections in the system prompt above. Give a complete answer with examples — "
                    "do not say you lack evidence; use your knowledge."
                )
            # Use compact prompt to stay within Groq 12K TPM limit.
            # The full chat_system.json (~10K tokens) exceeds the limit when
            # combined with evidence + DITA RAG + user message.
            system_prompt = _build_compact_chat_system_prompt(
                rag_context=rag_context,
                human_prompts=human_prompts,
                skill_guidance=_select_skill_guidance(user_content),
            )
            answer_shape_hint = _grounded_answer_shape_hint(user_content, normalized_grounded_facts)
            if evidence_pack.decision.status in {"abstain", "conflict"}:
                thin_evidence_hint = (
                    "The retrieved evidence is thin or conflicting. Answer directly in natural prose with the best supported "
                    "interpretation, then add a brief `## Verification notes` section. Do not start with 'Retrieved ...' "
                    "or turn the answer into a source-by-source recap."
                )
                answer_shape_hint = "\n\n".join(part for part in [answer_shape_hint, thin_evidence_hint] if part)
            structured_answer_hint = (
                draft_answer
                if should_enrich_with_llm and evidence_pack.decision.status not in {"abstain", "conflict"}
                else ""
            )
            try:
                llm_draft = await generate_text(
                    system_prompt=system_prompt,
                    user_prompt=_build_grounded_answer_user_prompt(
                        question=user_content,
                        evidence_context=evidence_ctx_for_prompt,
                        transcript=transcript,
                        corrected_query=str(retrieval_meta.get("corrected_query") or ""),
                        correction_applied=bool(retrieval_meta.get("correction_applied")),
                        structured_answer_hint=structured_answer_hint,
                        answer_shape_hint=answer_shape_hint,
                    ),
                    max_tokens=2400,
                    step_name="chat_grounded_answer",
                    trace_id=assistant_msg_id,
                )
                if str(llm_draft or "").strip():
                    draft_answer = llm_draft
                    grounding_path = "tool_plus_llm"
                    llm_enriched = True
            except Exception as exc:
                logger.warning_structured(
                    "Grounded chat LLM enrichment skipped",
                    extra_fields={"trace_id": assistant_msg_id, "error": str(exc)},
                )

        grounded_answer = await verify_grounded_answer(
            question=user_content,
            draft_answer=draft_answer,
            evidence_pack=evidence_pack,
            verified_examples=(
                [item.to_dict() for item in (normalized_grounded_facts.verified_examples if normalized_grounded_facts else [])]
            ),
            # For DITA-OT error queries the spec evidence is misleading — force pass-through
            structured_tool_answer=(
                False if _DITA_OT_ERROR_PATTERN.search(user_content)
                else normalized_grounded_facts is not None and not llm_enriched
            ),
            structured_fallback_answer=structured_fallback_answer if llm_enriched else "",
        )
        if _looks_like_retrieval_summary(grounded_answer.answer) and grounded_answer.grounding_status in {"partial", "abstain", "conflict"}:
            grounded_answer = replace(
                grounded_answer,
                answer=_build_thin_evidence_answer(
                    question=user_content,
                    evidence_pack=evidence_pack,
                    unsupported=grounded_answer.unsupported_points,
                ),
                unsupported_points=grounded_answer.unsupported_points[:4],
                grounding_status="partial",
                reason="The answer was rewritten into a clearer plain-language summary because the draft still read like a retrieval recap.",
            )
        if evidence_pack.decision.status in {"abstain", "conflict"}:
            # Skip replacement if verify_grounded_answer already returned a good LLM
            # answer (thin_evidence_override=False signals it passed through the draft).
            if grounded_answer.thin_evidence_override is not False:
                grounded_answer = replace(
                    grounded_answer,
                    answer=_build_thin_evidence_answer(
                        question=user_content,
                        evidence_pack=evidence_pack,
                        unsupported=grounded_answer.unsupported_points,
                    ),
                    unsupported_points=grounded_answer.unsupported_points[:4],
                    grounding_status="partial",
                    reason="The draft answer was rewritten into a clearer plain-language summary because the evidence was too thin.",
                )

        # For DITA-OT error/build-failure queries, any DITA spec element answer
        # (## at a glance / ## where it applies format) is wrong — replace it with
        # a proper OT-guidance response using the skill guidance in the system prompt.
        _ot_element_spec_answer = (
            _DITA_OT_ERROR_PATTERN.search(user_content)
            and grounded_answer.answer.strip().lower().startswith("## at a glance")
        )
        if _ot_element_spec_answer:
            grounded_answer = replace(
                grounded_answer,
                answer=_build_thin_evidence_answer(
                    question=user_content,
                    evidence_pack=evidence_pack,
                    unsupported=[],
                ),
                grounding_status="partial",
                reason="Spec element answer replaced for DITA-OT error query — using OT guidance instead.",
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
        # Merge source domain / OT gate diagnostics from tool retrieval meta
        grounding["source_domain"] = str(retrieval_meta.get("source_domain") or "general")
        grounding["source_domain_mismatch"] = bool(retrieval_meta.get("source_domain_mismatch"))
        grounding["official_docs_retry"] = bool(retrieval_meta.get("official_docs_retry"))
        grounding["retrieval_debug"] = dict(retrieval_meta.get("retrieval_debug") or {})
        if llm_enriched:
            grounding["llm_gate_reason"] = "llm_synthesis_attempted_with_grounded_evidence"
        yield {"type": "grounding", "grounding": grounding, "notice": grounding_to_notice(grounding)}

        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            grounded_answer.answer,
            tool_results={"_grounding": grounding},
        )

        for chunk in _stream_text_chunks(grounded_answer.answer):
            yield {"type": "chunk", "content": chunk}

        followups = _build_suggested_followups(user_content, {}, grounded_answer.answer)
        if followups:
            yield {"type": "suggested_followups", "followups": followups}

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


def _is_transient_error(error_msg: str) -> bool:
    """Classify whether a tool error is transient (worth retrying) vs permanent.

    When CHAT_ERROR_TAXONOMY is enabled, delegates to the structured error taxonomy.
    Otherwise falls back to the original keyword-based matching.
    """
    from app.core.agentic_config import agentic_config
    if getattr(agentic_config, "chat_error_taxonomy_enabled", True):
        from app.services.tool_error_taxonomy import is_retryable
        return is_retryable(error_msg)
    # Legacy fallback
    transient_keywords = [
        "timeout", "timed out", "connection", "unavailable", "rate limit",
        "429", "503", "502", "504", "temporary", "retry", "ECONNRESET",
        "network", "socket",
    ]
    lower = (error_msg or "").lower()
    return any(kw in lower for kw in transient_keywords)


async def _execute_tool_with_retry(
    *,
    tool_name: str,
    tool_input: dict,
    user_id: str,
    session_id: str | None,
    run_id: str | None,
    tenant_id: str,
    max_retries: int = 1,
) -> dict:
    """Execute a tool with optional retry on transient errors."""
    from app.services.chat_tools import run_tool

    result = await run_tool(
        tool_name,
        tool_input,
        user_id=user_id,
        session_id=session_id,
        run_id=run_id,
        tenant_id=tenant_id,
    )

    if max_retries > 0 and result.get("error") and _is_transient_error(str(result["error"])):
        # Use structured error taxonomy for backoff when available
        _use_taxonomy = getattr(agentic_config, "chat_error_taxonomy_enabled", True)
        for retry_num in range(1, max_retries + 1):
            err_str = str(result.get("error", ""))
            delay = 0.5 * retry_num  # Legacy default
            error_cat = ""
            if _use_taxonomy:
                from app.services.tool_error_taxonomy import classify_error, get_retry_delay, get_retry_strategy
                category = classify_error(err_str)
                error_cat = category.value
                strategy = get_retry_strategy(category)
                if not strategy.should_retry:
                    result["_error_category"] = error_cat
                    break  # Don't retry auth/validation errors
                delay = get_retry_delay(category, retry_num)

            logger.info_structured(
                "Retrying tool error",
                extra_fields={
                    "tool": tool_name,
                    "retry": retry_num,
                    "delay_sec": round(delay, 2),
                    "error_category": error_cat,
                    "error": err_str[:200],
                },
            )
            await asyncio.sleep(delay)
            result = await run_tool(
                tool_name,
                tool_input,
                user_id=user_id,
                session_id=session_id,
                run_id=run_id,
                tenant_id=tenant_id,
            )
            if not result.get("error") or not _is_transient_error(str(result["error"])):
                result["_retried"] = True
                result["_retry_count"] = retry_num
                if error_cat:
                    result["_error_category"] = error_cat
                break
        else:
            result["_retried"] = True
            result["_retry_count"] = max_retries

    return result


def _check_approval_gate(tool_name: str, tool_input: dict, topic_threshold: int = 1000) -> str:
    """Return an approval reason string if the action requires user confirmation, else empty string."""
    if tool_name == "create_job":
        config = tool_input.get("config") or {}
        recipes = config.get("recipes") or [{}]
        for recipe in recipes:
            topic_count = recipe.get("topic_count", 0)
            if isinstance(topic_count, int) and topic_count >= topic_threshold:
                return f"This will generate a large dataset with {topic_count} topics. Please confirm."
        recipe_type = tool_input.get("recipe_type", "")
        if recipe_type in ("flat_hierarchical_dita", "bulk_dita_map_topics", "large_scale"):
            # Check if default counts are large
            default_large = {
                "flat_hierarchical_dita": 5000,
                "bulk_dita_map_topics": 100,
                "large_scale": 500,
            }
            default_count = default_large.get(recipe_type, 0)
            if default_count >= topic_threshold:
                return f"Recipe '{recipe_type}' defaults to {default_count} topics. Please confirm."
    return ""


def _build_thinking_summary(user_content: str, context: Optional[dict] = None) -> str:
    """Build a short thinking/planning summary shown to the user before tool calls."""
    text = (user_content or "").lower()
    parts: list[str] = []

    # Detect intent categories
    if any(k in text for k in ("generate", "create dita", "jira", "convert", "bundle", "zip")):
        parts.append("Preparing to generate DITA content")
    if any(k in text for k in ("recipe", "dataset", "job", "bulk")):
        parts.append("Setting up dataset generation")
    if any(k in text for k in ("review", "validate", "check", "fix", "correct")):
        parts.append("Reviewing content for quality")
    if any(k in text for k in ("what is", "how do", "explain", "tell me about", "what are", "lookup", "look up")):
        parts.append("Looking up reference information")
    if any(k in text for k in ("pdf", "native pdf", "template", "output preset", "publish")):
        parts.append("Checking PDF/publishing configuration")
    if any(k in text for k in ("aem", "experience league", "guides")):
        parts.append("Searching AEM Guides documentation")

    if not parts:
        parts.append("Determining the best approach")

    # Add context awareness
    if context:
        if context.get("last_download_url"):
            parts.append("Previous generation available for refinement")
        if context.get("issue_key"):
            parts.append(f"Context: Jira {context['issue_key']}")

    return " → ".join(parts)


def _build_suggested_followups(
    user_content: str,
    tool_results: dict[str, dict],
    assistant_text: str,
) -> list[dict[str, str]]:
    """Generate 2-3 contextual follow-up suggestions based on what just happened."""
    suggestions: list[dict[str, str]] = []
    text = (user_content or "").lower()

    # After DITA generation → suggest review, refine, download
    if "generate_dita" in tool_results:
        result = tool_results["generate_dita"]
        if not result.get("error"):
            suggestions.append({"label": "Review XML quality", "text": "Review the generated DITA XML for quality issues"})
            suggestions.append({"label": "Refine output", "text": "Make the steps more detailed and add prerequisites"})
            if result.get("download_url"):
                suggestions.append({"label": "Browse files", "text": f"Show me the files in this generated bundle"})

    # After job creation → suggest check status, browse
    elif "create_job" in tool_results:
        result = tool_results["create_job"]
        if not result.get("error"):
            job_id = result.get("job_id", "")
            suggestions.append({"label": "Check job status", "text": f"What's the status of job {job_id}?"})
            suggestions.append({"label": "List all jobs", "text": "Show me all my recent dataset jobs"})

    # After DITA spec lookup → suggest related lookups
    elif "lookup_dita_spec" in tool_results or "lookup_dita_attribute" in tool_results:
        suggestions.append({"label": "Show XML example", "text": "Show me a complete XML example using this element"})
        suggestions.append({"label": "Compare elements", "text": "What are the differences between similar elements?"})

    # After review → suggest fix
    elif "review_dita_xml" in tool_results:
        result = tool_results["review_dita_xml"]
        if not result.get("error"):
            score = result.get("quality_score")
            if isinstance(score, (int, float)) and score < 90:
                suggestions.append({"label": "Auto-fix issues", "text": "Fix the issues found in my XML"})
            suggestions.append({"label": "Explain issues", "text": "Explain the validation issues in detail"})

    # After fix → suggest re-review
    elif "fix_dita_xml" in tool_results:
        suggestions.append({"label": "Re-review", "text": "Review the fixed XML again to verify quality"})

    # After Jira search → suggest generate from result
    elif "search_jira_issues" in tool_results:
        result = tool_results["search_jira_issues"]
        issues = result.get("issues", [])
        if issues and isinstance(issues[0], dict):
            key = issues[0].get("issue_key", "")
            if key:
                suggestions.append({"label": f"Generate from {key}", "text": f"Generate DITA from Jira issue {key}"})

    # After AEM Guides lookup → suggest deeper dives
    elif "lookup_aem_guides" in tool_results:
        suggestions.append({"label": "Show output presets", "text": "What output preset types are available in AEM Guides?"})

    # Generic: if no tools were used, suggest based on content
    if not suggestions:
        if any(k in text for k in ("dita", "xml", "element", "attribute")):
            suggestions.append({"label": "Look up DITA spec", "text": "Look up the DITA spec for this element"})
        if any(k in text for k in ("aem", "guides", "publish", "output")):
            suggestions.append({"label": "Search AEM docs", "text": "Search AEM Guides documentation for this topic"})
        if not suggestions:
            suggestions.append({"label": "Generate DITA", "text": "Generate a DITA topic from this description"})
            suggestions.append({"label": "Find recipes", "text": "What dataset recipes are available?"})

    return suggestions[:3]


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
    from app.core.agentic_config import agentic_config

    rag_context = _build_rag_context(user_content, tenant_id=tenant_id)

    # Groq free tier: 12K TPM — aggressively trim RAG context to leave room for tools + history
    _active_provider = get_active_llm_provider()
    if _active_provider == "groq" and len(rag_context) > 2000:
        rag_context = rag_context[:2000] + "\n[truncated for model limit]"

    # Use compact prompt to stay within Groq 12K TPM limit
    system_prompt = _build_compact_chat_system_prompt(rag_context=rag_context, human_prompts=human_prompts, skill_guidance=_select_skill_guidance(user_content))
    # Inject session context (previous generation download URL, refinement hints)
    context_block = _build_context_block(context, user_content, session_id=session_id)
    if context_block:
        system_prompt += context_block

    emit_thinking = bool(getattr(agentic_config, "chat_thinking_enabled", True))
    emit_state = bool(getattr(agentic_config, "chat_state_events_enabled", True))

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

    # --- Thinking phase: emit plan before first LLM call ---
    if emit_thinking:
        yield {
            "type": "thinking",
            "content": _build_thinking_summary(user_content, context),
        }

    if emit_state:
        yield {"type": "state", "state": "analyzing", "message": "Analyzing your request..."}

    history = get_messages(session_id)
    llm_messages = _messages_to_llm_format(history)

    if CHAT_CONTEXT_MAX_TOKENS:
        reserved_tokens = _approx_tokens(system_prompt)
        msg_budget = max(0, CHAT_CONTEXT_MAX_TOKENS - reserved_tokens)
        llm_messages = _truncate_messages_by_tokens(llm_messages, msg_budget)
    else:
        llm_messages = _truncate_messages_for_context(llm_messages)

    tools = get_tool_definitions()

    # Smart tool selection for Groq: reduce tool count to stay under 12K TPM.
    # Groq free tier has very tight limits; 19 tools + system prompt + RAG + history overwhelms it.
    if _active_provider == "groq":
        if len(tools) > 5:
            tools = _select_tools_for_query(tools, user_content, max_tools=5, max_extra=1)
        # Also limit conversation history to 4 messages for Groq
        if len(llm_messages) > 4:
            llm_messages = llm_messages[-4:]

    full_content: list[str] = []
    max_tool_rounds = int(getattr(agentic_config, "max_chat_tool_rounds", 8))
    tool_retry_enabled = bool(getattr(agentic_config, "chat_tool_retry_enabled", True))
    tool_max_retries = int(getattr(agentic_config, "chat_tool_max_retries", 1))
    approval_gates = bool(getattr(agentic_config, "chat_approval_gates_enabled", True))
    approval_threshold = int(getattr(agentic_config, "chat_approval_topic_threshold", 1000))
    job_progress_streaming = bool(getattr(agentic_config, "chat_job_progress_streaming", True))
    # Phase A feature flags
    _obs_enabled = bool(getattr(agentic_config, "chat_tool_observability_enabled", True))
    _obs_sse = bool(getattr(agentic_config, "chat_tool_metrics_sse_enabled", False))
    _parse_validation = bool(getattr(agentic_config, "chat_tool_parse_validation_enabled", True))
    _extended_gates = bool(getattr(agentic_config, "chat_extended_approval_gates_enabled", False))
    total_input_tokens = 0
    total_output_tokens = 0
    tool_results_by_name: dict[str, dict] = {}
    tool_use_blocks = None

    # A3: Observability collector
    obs_collector = None
    if _obs_enabled:
        from app.services.tool_observability import ToolObservabilityCollector
        _trace_id = assistant_msg_id or session_id or ""
        obs_collector = ToolObservabilityCollector(session_id=session_id or "", trace_id=_trace_id)

    try:
        for round_idx in range(max_tool_rounds):
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

                # --- A1: Check for parse errors on tool arguments ---
                if _parse_validation:
                    parse_error_blocks = [b for b in tool_use_blocks if b.get("_parse_error")]
                    if parse_error_blocks:
                        # Return error to LLM so it can retry with valid JSON
                        err_results = []
                        for b in parse_error_blocks:
                            err_results.append({
                                "type": "tool_result",
                                "tool_use_id": b["id"],
                                "content": json.dumps({
                                    "error": f"Malformed tool arguments: {b['_parse_error']}. Please retry with valid JSON.",
                                }),
                                "is_error": True,
                            })
                            if obs_collector:
                                obs_collector.record_execution(
                                    tool_name=b["name"], round_idx=round_idx,
                                    latency_ms=0, success=False,
                                    error_category="parse_error", was_parse_error=True,
                                    error_message=b["_parse_error"][:200],
                                )
                        llm_messages.append({"role": "user", "content": err_results})
                        continue  # Let LLM retry in the next round

                # --- Phase 3: Approval gates for destructive/costly actions ---
                needs_approval = False
                approval_reason = ""
                if approval_gates:
                    for b in tool_use_blocks:
                        reason = _check_approval_gate(b["name"], b.get("input") or {}, approval_threshold)
                        if reason:
                            needs_approval = True
                            approval_reason = reason
                            break

                # --- A5: Extended approval gates ---
                if not needs_approval and _extended_gates:
                    from app.services.approval_gates import get_default_registry
                    gate_config = {
                        "topic_threshold": approval_threshold,
                        "generate_char_threshold": int(getattr(agentic_config, "chat_approval_generate_char_threshold", 50000)),
                        "max_parallel_tools": int(getattr(agentic_config, "chat_approval_max_parallel_tools", 3)),
                        "tool_count_in_round": len(tool_use_blocks),
                    }
                    for b in tool_use_blocks:
                        reason = get_default_registry().check_gates(b["name"], b.get("input") or {}, gate_config)
                        if reason:
                            needs_approval = True
                            approval_reason = reason
                            break

                if needs_approval:
                    yield {
                        "type": "approval_required",
                        "message": approval_reason,
                        "tools": [b["name"] for b in tool_use_blocks],
                        "round": round_idx + 1,
                    }
                    # Don't execute — let LLM know approval is needed
                    approval_result = {
                        "type": "tool_result",
                        "tool_use_id": tool_use_blocks[0]["id"],
                        "content": json.dumps({
                            "status": "approval_required",
                            "message": f"Action requires user approval: {approval_reason}. Ask the user to confirm before proceeding.",
                        }),
                    }
                    llm_messages.append({"role": "user", "content": [approval_result]})
                    continue

                if emit_state:
                    tool_names = [b["name"] for b in tool_use_blocks]
                    yield {
                        "type": "state",
                        "state": "tool_calling",
                        "message": f"Using {', '.join(tool_names)}...",
                        "tools": tool_names,
                        "round": round_idx + 1,
                        "max_rounds": max_tool_rounds,
                    }

                tool_results = []
                for b in tool_use_blocks:
                    tool_name = b["name"]
                    tool_input = b.get("input") or {}
                    run_id = str(uuid4()) if tool_name == "generate_dita" else None
                    if run_id:
                        from app.api.v1.routes.ai_dataset import _update_generate_progress

                        _update_generate_progress(
                            run_id,
                            status="running",
                            stage="starting",
                            jira_id=f"TEXT-{run_id[:8]}",
                        )
                        yield {"type": "tool_start", "name": "generate_dita", "run_id": run_id}

                    # --- D7: Check tool result cache before execution ---
                    _cached_result = None
                    if CHAT_TOOL_CACHE_ENABLED:
                        _cached_result = _get_tool_cache().get(tool_name, tool_input)

                    # --- Phase 2: Auto-retry with error classification ---
                    # A3: Time tool execution
                    _tool_start_ts = __import__("time").monotonic()

                    if _cached_result is not None:
                        result = _cached_result
                        result["_cached"] = True
                    else:
                        result = await _execute_tool_with_retry(
                            tool_name=tool_name,
                            tool_input=tool_input,
                            user_id=user_id,
                            session_id=session_id,
                            run_id=run_id,
                            tenant_id=tenant_id,
                            max_retries=tool_max_retries if tool_retry_enabled else 0,
                        )
                        # Store in cache on success
                        if CHAT_TOOL_CACHE_ENABLED and not result.get("error"):
                            _get_tool_cache().put(tool_name, tool_input, result)

                    _tool_elapsed_ms = (__import__("time").monotonic() - _tool_start_ts) * 1000

                    was_retried = result.pop("_retried", False)
                    retry_count = result.pop("_retry_count", 0)
                    error_cat = result.pop("_error_category", "")

                    logger.info_structured(
                        "Chat tool invoked",
                        extra_fields={
                            "session_id": session_id,
                            "tool": tool_name,
                            "trace_id": assistant_msg_id,
                            "had_error": bool(result.get("error")),
                            "retried": was_retried,
                            "retry_count": retry_count,
                            "latency_ms": round(_tool_elapsed_ms, 1),
                        },
                    )

                    # A3: Record to observability collector
                    if obs_collector:
                        from app.services.tool_observability import _truncate_for_summary
                        obs_collector.record_execution(
                            tool_name=tool_name,
                            round_idx=round_idx,
                            latency_ms=_tool_elapsed_ms,
                            success=not bool(result.get("error")),
                            error_category=error_cat,
                            error_message=str(result.get("error", ""))[:200] if result.get("error") else "",
                            retry_count=retry_count,
                            input_summary=_truncate_for_summary(tool_input),
                            output_summary=_truncate_for_summary(result),
                        )

                    # Emit retry state so frontend shows recovery indicator
                    if was_retried and emit_state:
                        yield {
                            "type": "state",
                            "state": "retrying",
                            "message": f"Retried {tool_name} ({retry_count}x) — {'recovered' if not result.get('error') else 'still failing'}",
                        }
                    tool_results.append(result)
                    tool_results_by_name[tool_name] = result
                    yield {"type": "tool", "name": tool_name, "result": result}

                    # --- Phase 3: Live job progress for create_job ---
                    if tool_name == "create_job" and job_progress_streaming and not result.get("error"):
                        job_id = result.get("job_id")
                        if job_id:
                            yield {
                                "type": "job_progress",
                                "job_id": job_id,
                                "name": result.get("name", ""),
                                "recipe_type": result.get("recipe_type", ""),
                                "status": result.get("status", "pending"),
                                "download_url": result.get("download_url", ""),
                            }

                # Groq free tier: truncate tool results to fit within 12K TPM
                def _truncate_result_for_llm(r: dict, max_chars: int = 6000) -> str:
                    full = json.dumps(r)
                    if _active_provider == "groq" and len(full) > max_chars:
                        return full[:max_chars] + '..."truncated for model limit"}'
                    return full

                result_blocks = [
                    {"type": "tool_result", "tool_use_id": b["id"], "content": _truncate_result_for_llm(r)}
                    for b, r in zip(tool_use_blocks, tool_results)
                ]
                llm_messages.append({"role": "user", "content": result_blocks})

                if emit_state and round_idx < max_tool_rounds - 1:
                    yield {"type": "state", "state": "synthesizing", "message": "Processing tool results..."}

                # Let the LLM synthesize a response from tool results instead of
                # using canned text. The loop continues to the next round where the
                # LLM will see the tool results and produce a natural response.
                # Only fall back to canned text if we've exhausted all rounds.
                if round_idx >= max_tool_rounds - 1:
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

        # A3: Emit observability summary
        if obs_collector:
            obs_collector.emit_summary()
            if _obs_sse:
                yield {"type": "tool_metrics", "data": obs_collector.to_summary_dict()}

        # Emit suggested follow-ups based on tool usage and content
        followups = _build_suggested_followups(user_content, tool_results_by_name, full_text)
        if followups:
            yield {"type": "suggested_followups", "followups": followups}

        yield {"type": "done"}
    except Exception as e:
        err_str = str(e)
        logger.error_structured(
            "Chat turn failed",
            extra_fields={"session_id": session_id, "error": err_str},
            exc_info=True,
        )
        # If Groq failed on tool calling or request too large, retry the LLM call without tools
        _err_lower = err_str.lower()
        is_tool_call_failure = (
            "failed to call a function" in _err_lower
            or "failed_generation" in _err_lower
            or "413" in _err_lower
            or "request too large" in _err_lower
            or ("rate_limit" in _err_lower and "tokens" in _err_lower)
        )
        if is_tool_call_failure:
            logger.warning("Tool-call failure detected — retrying without tools")
            try:
                retry_content: list[str] = []
                async for evt_type, data in generate_chat_stream_with_tools(
                    system_prompt=system_prompt,
                    messages=llm_messages,
                    tools=None,
                    max_tokens=4096,
                ):
                    if evt_type == "chunk":
                        retry_content.append(data)
                        yield {"type": "chunk", "content": data}
                    elif evt_type in ("done",):
                        break
                retry_text = "".join(retry_content)
                if retry_text.strip():
                    _persist_assistant_message(session_id, assistant_msg_id, retry_text)
                    yield {"type": "done"}
                    return
            except Exception as retry_exc:
                logger.error_structured(
                    "No-tool retry also failed",
                    extra_fields={"session_id": session_id, "error": str(retry_exc)},
                    exc_info=True,
                )
        try:
            fallback_text = await _build_local_fallback_response(
                user_content,
                tenant_id,
                context,
                rag_context=rag_context,
            )
            # For tool-call failures, don't append the scary provider error — the local
            # fallback is sufficient and the error note confuses users.
            if not is_tool_call_failure:
                fallback_text = _append_provider_note(fallback_text, _format_exposed_chat_error(e))
            else:
                fallback_text = _append_provider_note(
                    fallback_text,
                    "Note: The assistant is temporarily unavailable. Please try again in a moment.",
                )
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
