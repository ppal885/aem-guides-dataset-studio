"""Retrieve Claude Code setup documentation for RAG when user asks about Claude Code, Adobe AI, or Bedrock setup."""
import re
from pathlib import Path

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# Keywords that trigger inclusion of Claude Code docs
CLAUDE_CODE_TRIGGER_TERMS = frozenset({
    "claude", "claude code", "adobe", "bedrock", "aws bedrock",
    "setup", "install", "cursor", "migrate", "migration",
    "camp", "turnkey", "shared access", "onetrust",
    "grp-dl-aif", "secretshare", "environment variable",
    "vscode extension", "terminal cli", "jetbrains",
})

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "claude_code_setup"
MAX_CONTEXT_CHARS = 2500  # Leave room for other RAG sources


def _query_matches_claude_code(query: str) -> bool:
    """Return True if query is relevant to Claude Code / Adobe AI setup."""
    if not query or not isinstance(query, str):
        return False
    q = query.lower().strip()
    return any(term in q for term in CLAUDE_CODE_TRIGGER_TERMS)


def _load_markdown_chunks() -> list[tuple[str, str]]:
    """Load README and SKILL markdown, split by ## headers. Returns [(title, content), ...]."""
    chunks = []
    for name in ("README.md", "SKILL.md"):
        path = KNOWLEDGE_DIR / name
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.debug_structured("Failed to load Claude Code doc", extra_fields={"path": str(path), "error": str(e)})
            continue
        # Split by ## headers
        parts = re.split(r"\n##\s+", text, flags=re.IGNORECASE)
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            lines = part.split("\n")
            title = lines[0].strip("# ").strip() if lines else name
            content = "\n".join(lines[1:]).strip() if len(lines) > 1 else part
            if content:
                chunks.append((f"{name}: {title}", content[:1200]))  # Cap per chunk
    return chunks


def retrieve_claude_code_context(query: str) -> str:
    """
    If query is relevant to Claude Code/Adobe AI setup, return formatted context.
    Otherwise return empty string.
    """
    if not _query_matches_claude_code(query):
        return ""

    try:
        chunks = _load_markdown_chunks()
        if not chunks:
            return ""

        parts = []
        total = 0
        for title, content in chunks[:5]:  # Max 5 chunks
            block = f"### {title}\n{content}\n"
            if total + len(block) > MAX_CONTEXT_CHARS:
                block = block[: MAX_CONTEXT_CHARS - total - 20] + "\n[truncated]"
                parts.append(block)
                break
            parts.append(block)
            total += len(block)

        if not parts:
            return ""
        return "\n".join(parts)
    except Exception as e:
        logger.debug_structured("Claude Code retriever failed", extra_fields={"error": str(e)})
        return ""
