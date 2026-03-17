"""Chat service - sessions, messages, RAG, streaming."""
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional
from uuid import uuid4

from app.db.session import SessionLocal
from app.db.chat_models import ChatSession, ChatMessage
from app.services.llm_service import generate_chat_stream, generate_chat_stream_with_tools, is_llm_available, store_chat_llm_run
from app.services.chat_tools import get_tool_definitions, run_tool
from app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt
from app.services.dita_knowledge_retriever import retrieve_dita_knowledge
from app.services.claude_code_retriever import retrieve_claude_code_context
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
        sections={"base": "You are a friendly AI assistant for AEM Guides Dataset Studio. Help with DITA, recipes, and dataset generation. Use generate_dita when user pastes Jira content or asks to create DITA."},
        section_order=["base"],
    )
    _CHAT_PROMPT_BUILDER = PromptBuilder(fallback)
    return _CHAT_PROMPT_BUILDER


def _build_chat_system_prompt(user_context: str, rag_context: str) -> str:
    """Build full chat system prompt from spec + dynamic blocks."""
    return _get_chat_prompt_builder().build(user_context=user_context, rag_context=rag_context)


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
            "Do not just summarize—generate DITA and provide the download link."
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


def _build_rag_context(query: str) -> str:
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
        return [
            {
                "id": r.id,
                "title": r.title or "New Chat",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


def get_session(session_id: str) -> dict | None:
    """Get session by id. Returns None if not found."""
    db = SessionLocal()
    try:
        s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not s:
            return None
        return {
            "id": s.id,
            "title": s.title or "New Chat",
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
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
        return [
            {
                "id": r.id,
                "role": r.role,
                "content": r.content,
                "tool_calls": json.loads(r.tool_calls) if r.tool_calls else None,
                "tool_results": json.loads(r.tool_results) if r.tool_results else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
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
) -> AsyncGenerator[dict, None]:
    """
    Process a chat turn: persist user message, call LLM with RAG, stream response, persist assistant message.
    Yields dicts: {"type": "chunk", "content": "..."} | {"type": "done"} | {"type": "tool", "name": "...", "result": {...}} | {"type": "error", "message": "..."}
    """
    if not is_llm_available():
        yield {"type": "error", "message": "LLM unavailable. Set ANTHROPIC_API_KEY, GROQ_API_KEY, or LLM_PROVIDER=bedrock with AWS credentials in backend/.env"}
        return

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

    # Load history
    history = get_messages(session_id)
    llm_messages = _messages_to_llm_format(history)

    # RAG context and user context
    rag_context = _build_rag_context(user_content)
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
    assistant_msg_id = str(uuid4())
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
                    yield {"type": "tool", "name": b["name"], "result": result}

                result_blocks = [
                    {"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(r)}
                    for b, r in zip(tool_use_blocks, tool_results)
                ]
                llm_messages.append({"role": "user", "content": result_blocks})
            else:
                break

        full_text = "".join(full_content)

        # Persist assistant message
        db = SessionLocal()
        try:
            db.add(
                ChatMessage(
                    id=assistant_msg_id,
                    session_id=session_id,
                    role="assistant",
                    content=full_text,
                    created_at=datetime.utcnow(),
                )
            )
            s = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if s:
                s.updated_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

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
        yield {"type": "error", "message": str(e)}
