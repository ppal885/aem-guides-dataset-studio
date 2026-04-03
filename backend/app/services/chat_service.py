"""Chat service - sessions, messages, RAG, streaming."""
import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator, Optional
from uuid import uuid4

from app.db.session import SessionLocal
from app.db.chat_models import ChatSession, ChatMessage
from app.services.llm_service import (
    _coerce_llm_text_response,
    format_llm_error_for_user,
    generate_chat_stream_with_tools,
    generate_text,
    is_llm_available,
    store_chat_llm_run,
)
from app.services.chat_tools import get_tool_definitions, run_tool
from app.services.corrective_rag_service import run_chat_corrective_rag
from app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt
from app.services.dita_knowledge_retriever import retrieve_dita_knowledge
from app.services.claude_code_retriever import retrieve_claude_code_context
from app.services.jira_chat_search_service import extract_jira_search_query
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
    r"properties_table_reference|bookmap|conref_pack|keyscope|bulk_dita|incremental_topicref|insurance_incremental|"
    r"map_parse|relationship_table|validation_duplicate|maps_topicref|maps_reltable|maps_mapref)\b",
    re.IGNORECASE,
)
_DITA_GENERATION_PATTERN = re.compile(
    r"\b(generate|create|write|draft|make|build)\b.*\b(dita|task topic|concept topic|reference topic|glossentry|topic|zip|bundle|xml|sample|example|template|scaffold|boilerplate|bookmap|reltable|ditamap)\b",
    re.IGNORECASE,
)
_JIRA_SEARCH_PATTERN = re.compile(
    r"\b(jira|jiras|issue|issues|ticket|tickets)\b.*\b(fetch|find|show|search|lookup|look up|get|list|related|similar|matching|relevant)\b|"
    r"\b(fetch|find|show|search|lookup|look up|get|list)\b.*\b(jira|jiras|issue|issues|ticket|tickets)\b",
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
_SHORT_DEFINITION_OR_EXPLAIN = re.compile(
    r"(?is)^\s*(what\s+is|what\s+are|define|explain|meaning\s+of)\b.{1,200}$",
)

_HUMAN_PRECISION_ADDON: Optional[str] = None


def _domain_tool_mode_enabled() -> bool:
    return os.getenv("CHAT_DOMAIN_TOOL_MODE", "true").strip().lower() in ("1", "true", "yes", "on")


def _looks_like_short_definition_question(text: str) -> bool:
    """Keep short 'what is / explain …' flows on the grounded path (evidence + verify)."""
    t = (text or "").strip()
    if len(t) > 200:
        return False
    return bool(_SHORT_DEFINITION_OR_EXPLAIN.match(t))


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
            parts.append(
                f"LAST GENERATION IN THIS SESSION (user can refine):\n"
                f"Previous text: {prev_text}{'...' if len(last_gen.get('text', '') or '') > 800 else ''}\n"
                "When user says 'add X', 'refine', 'make steps more detailed', etc., call generate_dita with "
                "text=<previous text> and instructions=<their refinement request>."
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


def _build_post_tool_assistant_text(tool_results_by_name: dict[str, dict]) -> str:
    lines: list[str] = []

    dita_result = tool_results_by_name.get("generate_dita")
    if isinstance(dita_result, dict):
        if dita_result.get("error"):
            lines.append(f"DITA bundle generation failed: {dita_result.get('error')}")
        else:
            jira_id = str(dita_result.get("jira_id") or "generated bundle").strip()
            run_id = str(dita_result.get("run_id") or "").strip()
            download_url = _tool_result_download_url(dita_result)
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
            job_id = str(job_result.get("job_id") or "").strip()
            recipe_type = str(job_result.get("recipe_type") or "").strip()
            lines.append(
                f"Dataset generation started{f' for `{recipe_type}`' if recipe_type else ''}."
                f"{f' Job ID: `{job_id}`.' if job_id else ''} Use the in-chat dataset card for progress and download."
            )

    jira_result = tool_results_by_name.get("search_jira_issues")
    if isinstance(jira_result, dict):
        issues = jira_result.get("issues")
        if isinstance(issues, list) and issues:
            first = issues[0] if isinstance(issues[0], dict) else {}
            issue_key = str(first.get("issue_key") or "").strip()
            summary = str(first.get("summary") or "").strip()
            lines.append(
                "I found a real Jira issue match from verified search results."
                f"{f' `{issue_key}`' if issue_key else ''}"
                f"{f': {summary}' if summary else ''}"
            )
        else:
            query = str(jira_result.get("query") or "your search").strip()
            lines.append(f"No verified Jira issues matched `{query}`.")

    return "\n\n".join(line for line in lines if line).strip()


def _should_use_tool_mode(user_content: str) -> bool:
    text = (user_content or "").strip()
    if not text:
        return False
    if _detect_jira_style_text(text):
        return True
    if _DATASET_REQUEST_PATTERN.search(text):
        return True
    if _DITA_GENERATION_PATTERN.search(text):
        return True
    if (
        _domain_tool_mode_enabled()
        and _DOMAIN_TOOL_PATTERN.search(text)
        and not _looks_like_short_definition_question(text)
    ):
        return True
    return False


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
        "I can help in a few practical ways even without a live model reply:\n\n"
        "- Summarize Jira issues and comments into author-ready guidance.\n"
        "- Search or compare Jira issues when you ask to find tickets.\n"
        "- Suggest DITA improvements: conref, conkeyref, keyref, keys, profiling, maps, reltables, reuse.\n"
        "- Explain map structures (topicref, mapref, navref, keydef) and reference topics when you paste XML.\n"
        "- Turn issue text into task, concept, or reference-topic outlines.\n"
        "- Ground answers in AEM Guides docs, DITA spec chunks, tenant knowledge, and imported examples.\n"
        "- Generate DITA bundles from pasted Jira-style content, or start dataset jobs (recipes like "
        "task_topics, maps_reltable_basic, bulk_dita_map_topics) from chat when tools are available.\n\n"
        f"Current workspace: `{tenant_id}`.\n\n"
        "Try one of these prompts:\n"
        "- Summarize the Jira comments into author-ready guidance.\n"
        "- Search Jira for issues about map validation.\n"
        "- Review this DITA topic for conref, keyref, and keyword improvements.\n"
        "- How do I fix broken keyrefs in a root map with multiple submaps?\n"
        "- Create a dataset with the properties_table_reference recipe for QA.\n"
        "- Convert this issue into a clean task topic outline."
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
        "1. **Always include XML examples** when the question involves DITA elements, "
        "attributes, or structure. Wrap in ```xml fenced blocks.\n"
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
        "use your knowledge of DITA 1.3 / AEM Guides and note what comes from general "
        "DITA knowledge.\n"
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
        s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if s:
            s.updated_at = datetime.utcnow()
        db.commit()
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


def create_session() -> str:
    """Create a new chat session. Returns session_id."""
    session_id = str(uuid4())
    db = SessionLocal()
    try:
        s = ChatSession(
            id=session_id,
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


def list_sessions(limit: int = 50, offset: int = 0) -> list[dict]:
    """List chat sessions, newest first."""
    db = SessionLocal()
    try:
        rows = (
            db.query(ChatSession)
            .order_by(ChatSession.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_serialize_session_row(r) for r in rows]
    finally:
        db.close()


def get_session(session_id: str) -> dict | None:
    """Get session by id. Returns None if not found."""
    db = SessionLocal()
    try:
        s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not s:
            return None
        return _serialize_session_row(s)
    finally:
        db.close()


def get_messages(session_id: str, limit: int = 100) -> list[dict]:
    """Get messages for a session."""
    db = SessionLocal()
    try:
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


def branch_session_from_message(session_id: str, message_id: str) -> tuple[dict, list[dict]]:
    """Create a new session by copying messages before a user message being edited."""
    db = SessionLocal()
    try:
        source_session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
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


def delete_session(session_id: str) -> bool:
    """Delete a session and its messages. Returns True if deleted."""
    db = SessionLocal()
    try:
        s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
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


def update_session_title(session_id: str, title: str) -> dict | None:
    """Update session title and return the serialized session."""
    _update_session_title(session_id, title)
    return get_session(session_id)


def delete_all_chat_sessions() -> int:
    """Delete every chat session and message. Returns number of deleted sessions."""
    db = SessionLocal()
    try:
        deleted = db.query(ChatSession).count()
        db.query(ChatMessage).delete(synchronize_session=False)
        db.query(ChatSession).delete(synchronize_session=False)
        db.commit()
        return deleted
    finally:
        db.close()


def update_user_message_truncate_after(session_id: str, message_id: str, content: str) -> list[dict]:
    """Edit a user message in place and remove all following messages."""
    trimmed = (content or "").strip()
    if not trimmed:
        raise ValueError("Message content cannot be empty")

    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
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


def pop_last_assistant_if_any(session_id: str) -> bool:
    """Remove the last assistant message when present."""
    db = SessionLocal()
    try:
        last = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if not last or last.role != "assistant":
            return False
        db.delete(last)
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session:
            session.updated_at = datetime.utcnow()
        db.commit()
        return True
    finally:
        db.close()


def get_last_user_message_content(session_id: str) -> str | None:
    """Return the most recent user message content for a session."""
    db = SessionLocal()
    try:
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


async def _stream_assistant_reply(
    session_id: str,
    *,
    user_content: str,
    assistant_msg_id: str,
    user_id: str = "chat-user",
    context: Optional[dict] = None,
    tenant_id: str = "kone",
    human_prompts: bool = False,
) -> AsyncGenerator[dict, None]:
    """Generate and persist an assistant reply for an existing last user message."""
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

    if _should_use_tool_mode(user_content):
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
    try:
        evidence_pack, retrieval_meta = await _build_chat_evidence_pack(user_content, tenant_id)
        if evidence_pack is None:
            raise ValueError("No evidence pack could be built for the chat question")

        # Always try to generate a draft answer via the LLM, even when
        # grounding evidence is weak/absent — the DITA seed + RAG context
        # and the LLM's own knowledge can still produce a useful response.
        transcript = _recent_chat_transcript(session_id)
        draft_answer = ""
        if is_llm_available():
            # Build enriched DITA RAG context (with common_mistakes, examples, attributes)
            dita_rag = ""
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
            )

        grounded_answer = await verify_grounded_answer(
            question=user_content,
            draft_answer=draft_answer,
                evidence_pack=evidence_pack,
            )

        grounding = grounding_metadata_from_pack(
            evidence_pack,
            grounded_answer,
            corrected_query=str(retrieval_meta.get("corrected_query") or ""),
            correction_applied=bool(retrieval_meta.get("correction_applied")),
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
            return
        except Exception as fallback_exc:
            logger.error_structured(
                "Chat fallback response failed",
                extra_fields={"session_id": session_id, "error": str(fallback_exc)},
                exc_info=True,
            )
        try:
            if evidence_pack is not None:
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
                return
        except Exception:
            logger.debug_structured("Grounded fallback failed", extra_fields={"session_id": session_id})
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
    db = SessionLocal()
    try:
        db.add(
            ChatMessage(
                id=user_msg_id,
                session_id=session_id,
                role="user",
                content=user_content,
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
    ):
        yield event


async def regenerate_last_assistant(
    session_id: str,
    user_id: str = "chat-user",
    context: Optional[dict] = None,
    tenant_id: str = "kone",
    human_prompts: bool | None = None,
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
    user_content = get_last_user_message_content(session_id)
    if not user_content:
        yield {"type": "error", "message": "No user message found to regenerate from"}
        return

    hp = bool(human_prompts) if human_prompts is not None else False
    async for event in _stream_assistant_reply(
        session_id,
        user_content=user_content,
        assistant_msg_id=str(uuid4()),
        user_id=user_id,
        context=context,
        tenant_id=tenant_id,
        human_prompts=hp,
    ):
        yield event
