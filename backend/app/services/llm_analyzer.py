"""LLM analyzer for JIRA DITA issue analysis."""
from pathlib import Path
from typing import Optional

from app.services.llm_service import generate_json, is_llm_available
from app.services.dita_knowledge_retriever import retrieve_dita_knowledge, retrieve_dita_graph_knowledge
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "templates" / "prompts" / "jira_dita_analysis.txt"


def normalize_issue_text(issue: dict) -> str:
    """Concatenate summary, description, labels, comments into single text for LLM."""
    parts = []
    summary = (issue.get("summary") or "").strip()
    if summary:
        parts.append(f"Summary: {summary}")
    description = (issue.get("description") or "").strip()
    if description:
        parts.append(f"Description: {description}")
    labels = issue.get("labels") or []
    if labels:
        parts.append(f"Labels: {', '.join(str(l) for l in labels)}")
    comments = issue.get("comments") or []
    if comments:
        comment_texts = []
        for c in comments:
            bt = (c.get("body_text") or "").strip()
            if bt:
                comment_texts.append(bt)
        if comment_texts:
            parts.append("Comments: " + "\n---\n".join(comment_texts))
    return "\n\n".join(parts).strip() or "No content"


async def analyze_issue(issue_text: str, issue_key: Optional[str] = None) -> Optional[dict]:
    """
    Run LLM analysis on issue text. Returns {category, dita_features, root_cause, fix, dataset_example}.
    """
    if not is_llm_available():
        logger.warning_structured("LLM not available for DITA analysis", extra_fields={"issue_key": issue_key})
        return None

    try:
        prompt_template = PROMPT_PATH.read_text(encoding="utf-8") if PROMPT_PATH.exists() else ""
        if not prompt_template:
            prompt_template = (
                "You are a DITA architecture expert. Analyze the JIRA issue and output JSON with "
                "category, dita_features, root_cause, fix, dataset_example."
            )
        # RAG: DITA spec for accurate dita_features and dataset_example
        dita_block = ""
        try:
            dita_chunks = retrieve_dita_knowledge(issue_text[:500], k=4)
            if dita_chunks:
                _tc = lambda c: (c.get("text_content") or "")
                texts = [" ".join(t) if isinstance(t, list) else str(t)[:600] for t in (_tc(c) for c in dita_chunks)]
                dita_block = "DITA KNOWLEDGE (use for valid dita_features and dataset_example):\n" + "\n---\n".join(texts) + "\n\n"
            graph_block = retrieve_dita_graph_knowledge(element_hint=issue_text[:500])
            if graph_block:
                dita_block += "DITA STRUCTURE:\n" + graph_block[:2000] + "\n\n"
        except Exception:
            pass

        user_prompt = (dita_block + prompt_template).replace("{jira_text}", issue_text[:12000])
        system_prompt = "Output STRICT JSON only. No markdown, no explanation, no code blocks."

        result = await generate_json(
            system_prompt,
            user_prompt,
            max_tokens=2000,
            step_name="jira_dita_analysis",
            jira_id=issue_key,
        )
        if not result or not isinstance(result, dict):
            return None
        return result
    except Exception as e:
        logger.warning_structured(
            "LLM analysis failed for issue",
            extra_fields={"issue_key": issue_key, "error": str(e)},
        )
        return None
