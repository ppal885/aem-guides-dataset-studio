"""Intent extraction from Jira evidence pack."""
import json
from pathlib import Path
from typing import Optional

from app.services.llm_service import generate_json, is_llm_available
from app.services.dita_knowledge_retriever import retrieve_dita_knowledge, retrieve_dita_graph_knowledge
from app.utils.evidence_extractor import extract_evidence_context
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"


async def extract_intent(
    evidence_pack: dict,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
) -> dict:
    """
    Extract structured intent from evidence pack via LLM.
    Returns {intent_summary, constructs, scenario_hint, evidence_sources}.
    Falls back to defaults when LLM unavailable or fails.
    """
    default = {
        "intent_summary": "",
        "constructs": [],
        "scenario_hint": "MIN_REPRO",
        "evidence_sources": [],
    }

    if not is_llm_available():
        primary = evidence_pack.get("primary") or {}
        summary = (primary.get("summary") or "Issue")[:100]
        default["intent_summary"] = f"Reproduce: {summary}"
        return default

    prompt_path = PROMPTS_DIR / "intent_extractor.txt"
    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    if not prompt:
        return default

    primary = evidence_pack.get("primary") or {}
    evidence_text = extract_evidence_context(primary, max_chars=6000)
    attachments_summary = []
    for att in primary.get("attachments") or []:
        fn = att.get("filename", "")
        excerpt_len = len(att.get("excerpt") or "") + len(att.get("full_content") or "")
        if excerpt_len:
            attachments_summary.append(f"{fn} ({excerpt_len} chars)")
    comments_summary = []
    for i, c in enumerate(primary.get("comments") or []):
        body = (c.get("body_text", "") if isinstance(c, dict) else "")[:500]
        if body:
            comments_summary.append(f"comment_{i + 1}: {body[:200]}...")

    # RAG: DITA spec to constrain constructs (keydef, keyref, conref, etc.)
    query_text = f"{primary.get('summary', '')} {primary.get('description', '')}"[:500]
    dita_block = ""
    try:
        dita_chunks = retrieve_dita_knowledge(query_text, k=3)
        if dita_chunks:
            _tc = lambda c: (c.get("text_content") or "")
            texts = [" ".join(t) if isinstance(t, list) else str(t)[:400] for t in (_tc(c) for c in dita_chunks)]
            dita_block = "DITA KNOWLEDGE (constructs must be valid DITA elements):\n" + "\n---\n".join(texts) + "\n\n"
        graph_block = retrieve_dita_graph_knowledge(element_hint=query_text)
        if graph_block:
            dita_block += "DITA STRUCTURE:\n" + graph_block[:1500] + "\n\n"
    except Exception:
        pass

    user_parts = [f"{dita_block}Evidence:\n{evidence_text}"]
    if attachments_summary:
        user_parts.append(f"\nAttachments: {', '.join(attachments_summary)}")
    if comments_summary:
        user_parts.append(f"\nComments:\n" + "\n".join(comments_summary[:5]))
    user_parts.append("\n\nOutput JSON only:")

    try:
        result = await generate_json(
            prompt,
            "\n".join(user_parts),
            max_tokens=500,
            step_name="intent_extractor",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as e:
        logger.warning_structured(
            "Intent extraction failed",
            extra_fields={"jira_id": jira_id, "error": str(e)},
        )
        return default

    if not result:
        return default

    intent_summary = result.get("intent_summary") or default["intent_summary"]
    constructs = result.get("constructs")
    if not isinstance(constructs, list):
        constructs = default["constructs"]
    scenario_hint = result.get("scenario_hint") or default["scenario_hint"]
    if scenario_hint not in ("MIN_REPRO", "BOUNDARY", "STRESS", "EDGE", "SCALE"):
        scenario_hint = default["scenario_hint"]
    evidence_sources = result.get("evidence_sources")
    if not isinstance(evidence_sources, list):
        evidence_sources = default["evidence_sources"]

    return {
        "intent_summary": intent_summary,
        "constructs": constructs,
        "scenario_hint": scenario_hint,
        "evidence_sources": evidence_sources,
    }
