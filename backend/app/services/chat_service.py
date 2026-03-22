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
    format_llm_error_for_user,
    generate_chat_stream,
    generate_chat_stream_with_tools,
    is_llm_available,
    store_chat_llm_run,
)
from app.services.chat_tools import get_tool_definitions, run_tool
from app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt
from app.services.dita_knowledge_retriever import retrieve_dita_knowledge
from app.services.claude_code_retriever import retrieve_claude_code_context
from app.services.tenant_service import retrieve_tenant_context, retrieve_tenant_examples
from app.core.prompt_interface import PromptBuilder, load_prompt_spec
from app.core.structured_logging import get_structured_logger
from app.services.llm_service import _get_prompt_versions

logger = get_structured_logger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"

RAG_CONTEXT_MAX_CHARS = int(os.getenv("RAG_CONTEXT_MAX_CHARS", "6000"))
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
                f"Dataset job created{f' for `{recipe_type}`' if recipe_type else ''}."
                f"{f' Job ID: `{job_id}`.' if job_id else ''} Check Job History for downloads."
            )

    return "\n\n".join(line for line in lines if line).strip()


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
        "- Suggest DITA improvements like conref, conkeyref, keyref, keywords, reuse, and stronger structure.\n"
        "- Help turn issue text into task, concept, or reference-topic direction.\n"
        "- Guide research using AEM Guides docs, DITA references, tenant knowledge, and imported examples.\n"
        "- Start DITA bundle generation when you paste Jira-style content.\n\n"
        f"Current workspace: `{tenant_id}`.\n\n"
        "Try one of these prompts:\n"
        "- Summarize the Jira comments into author-ready guidance.\n"
        "- Review this DITA topic for conref, keyref, and keyword improvements.\n"
        "- Convert this issue into a clean task topic outline.\n"
        "- Suggest how to make this topic more reusable across AEM Guides content."
    )


def _builtin_unavailable_response(user_content: str, tenant_id: str) -> str:
    trimmed = (user_content or "").strip()
    if _is_capability_prompt(trimmed):
        return _builtin_capability_response(tenant_id)
    return (
        "Live AI responses are temporarily unavailable right now, but the chat workspace is still ready for structured authoring tasks.\n\n"
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


def _build_fallback_notice(
    *,
    exc: Exception | None = None,
    provider_configured: bool = True,
) -> dict:
    if not provider_configured:
        return {
            "type": "notice",
            "code": "provider_unavailable",
            "level": "warning",
            "title": "Live AI provider is not configured",
            "message": "Showing a local fallback response from indexed knowledge because no live chat provider is currently available.",
        }

    friendly = format_llm_error_for_user(exc or RuntimeError("The assistant is temporarily unavailable."))
    lowered = friendly.lower()
    if "rate-limit" in lowered or "rate limit" in lowered:
        return {
            "type": "notice",
            "code": "provider_rate_limited",
            "level": "warning",
            "title": "Live AI providers are rate-limited",
            "message": "Showing a local fallback response from indexed knowledge while the configured providers recover.",
        }
    if "quota" in lowered:
        return {
            "type": "notice",
            "code": "provider_quota_exhausted",
            "level": "warning",
            "title": "Live AI provider quota is exhausted",
            "message": "Showing a local fallback response from indexed knowledge until provider quota is available again.",
        }
    return {
        "type": "notice",
        "code": "provider_unavailable",
        "level": "warning",
        "title": "Live AI response is unavailable",
        "message": "Showing a local fallback response from indexed knowledge for this reply.",
    }


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
                name = c.get("element_name", "")
                text = (c.get("text_content") or "")[:RAG_SNIPPET_CHARS]
                dita_parts.append(f"[{i}] {name}\n{text}")
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


async def chat_turn(
    session_id: str,
    user_content: str,
    user_id: str = "chat-user",
    context: Optional[dict] = None,
    tenant_id: str = "kone",
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

    assistant_msg_id = str(uuid4())

    if _is_capability_prompt(user_content):
        fallback_text = _builtin_capability_response(tenant_id)
        _persist_assistant_message(session_id, assistant_msg_id, fallback_text)
        yield {"type": "chunk", "content": fallback_text}
        yield {"type": "done"}
        return

    if not is_llm_available():
        yield _build_fallback_notice(provider_configured=False)
        fallback_text = await _build_local_fallback_response(user_content, tenant_id, context)
        _persist_assistant_message(session_id, assistant_msg_id, fallback_text)
        yield {"type": "chunk", "content": fallback_text}
        yield {"type": "done"}
        return

    # Load history
    history = get_messages(session_id)
    llm_messages = _messages_to_llm_format(history)

    # RAG context and user context
    rag_context = _build_rag_context(user_content, tenant_id=tenant_id)
    context_block = _build_context_block(context, user_content, session_id=session_id)
    system_prompt = _build_chat_system_prompt(user_context=context_block, rag_context=rag_context)

    # Truncate messages: token-based if CHAT_CONTEXT_MAX_TOKENS set, else message-count
    if CHAT_CONTEXT_MAX_TOKENS:
        reserved_tokens = _approx_tokens(system_prompt)
        msg_budget = max(0, CHAT_CONTEXT_MAX_TOKENS - reserved_tokens)
        llm_messages = _truncate_messages_by_tokens(llm_messages, msg_budget)
    else:
        llm_messages = _truncate_messages_for_context(llm_messages)

    tools = get_tool_definitions()
    full_content = []
    max_tool_rounds = 5
    total_input_tokens = 0
    total_output_tokens = 0

    try:
        for _ in range(max_tool_rounds):
            round_text = []
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

            tool_results_by_name: dict[str, dict] = {}

            if tool_use_blocks:
                assistant_blocks = [{"type": "text", "text": "".join(round_text)}] if round_text else []
                for b in tool_use_blocks:
                    assistant_blocks.append({
                        "type": "tool_use",
                        "id": b["id"],
                        "name": b["name"],
                        "input": b["input"],
                    })
                llm_messages.append({"role": "assistant", "content": assistant_blocks})

                tool_results = []
                for b in tool_use_blocks:
                    run_id = str(uuid4()) if b["name"] == "generate_dita" else None
                    if run_id:
                        from app.api.v1.routes.ai_dataset import _update_generate_progress
                        _update_generate_progress(run_id, status="running", stage="starting", jira_id=f"TEXT-{run_id[:8]}")
                        yield {"type": "tool_start", "name": "generate_dita", "run_id": run_id}
                    result = await run_tool(
                        b["name"],
                        b.get("input") or {},
                        user_id=user_id,
                        session_id=session_id,
                        run_id=run_id,
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

        # Persist assistant message
        _persist_assistant_message(
            session_id,
            assistant_msg_id,
            full_text,
            tool_calls=tool_use_blocks,
            tool_results=tool_results_by_name,
        )

        # Store token usage for observability (best-effort, non-blocking)
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
        yield _build_fallback_notice(exc=e, provider_configured=True)
        fallback_text = await _build_local_fallback_response(user_content, tenant_id, context, rag_context=rag_context)
        try:
            _persist_assistant_message(session_id, assistant_msg_id, fallback_text)
            yield {"type": "chunk", "content": fallback_text}
            yield {"type": "done"}
        except Exception:
            yield {"type": "error", "message": format_llm_error_for_user(e)}
