"""LLM critique and repair instruction formatting for regeneration loops."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.core.schemas_dita_pipeline import (
    CritiqueReport,
    GenerationPlan,
    IntentRecord,
    SemanticValidationReport,
)
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"


def _load_critique_prompt() -> str:
    p = PROMPTS_DIR / "dita_critique_engine.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _truncate_xml_for_critique(combined_xml: str, max_chars: int = 12000) -> str:
    s = (combined_xml or "").strip()
    return s[:max_chars] + ("\n...[truncated]" if len(s) > max_chars else "")


async def critique_generation_async(
    intent: IntentRecord,
    plan: GenerationPlan,
    combined_xml: str,
    validation: SemanticValidationReport,
    *,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
) -> CritiqueReport:
    from app.services.llm_service import generate_json, is_llm_available

    prompt = _load_critique_prompt()
    if not prompt or not is_llm_available():
        return CritiqueReport(
            aligned_with_intent=False,
            shallow_wrap=validation.shallow_output,
            missing_required_constructs=[],
            repair_instructions=[v.repair_hint for v in validation.violations if v.repair_hint],
        )

    user_payload = {
        "INTENT": intent.model_dump(),
        "GENERATION_PLAN": plan.model_dump(),
        "SEMANTIC_VALIDATION": {
            "ok": validation.ok,
            "shallow_output": validation.shallow_output,
            "violations": [v.model_dump() for v in validation.violations],
        },
        "GENERATED_XML_EXCERPT": _truncate_xml_for_critique(combined_xml),
    }
    try:
        raw = await generate_json(
            prompt,
            json.dumps(user_payload, indent=2)[:14000],
            max_tokens=1500,
            step_name="dita_critique",
            trace_id=trace_id,
            jira_id=jira_id,
        )
        if not isinstance(raw, dict):
            raw = {}
        return CritiqueReport(
            aligned_with_intent=bool(raw.get("aligned_with_intent", True)),
            shallow_wrap=bool(raw.get("shallow_wrap", validation.shallow_output)),
            missing_required_constructs=list(raw.get("missing_required_constructs") or []),
            violations=list(raw.get("violations") or []),
            repair_instructions=list(raw.get("repair_instructions") or []),
        )
    except Exception as e:
        logger.warning_structured("Critique LLM failed", extra_fields={"error": str(e), "jira_id": jira_id})
        return CritiqueReport(
            aligned_with_intent=False,
            shallow_wrap=validation.shallow_output,
            repair_instructions=[v.repair_hint for v in validation.violations if v.repair_hint],
        )


def format_regeneration_addon(
    validation: SemanticValidationReport,
    critique: CritiqueReport,
    plan: Optional[GenerationPlan] = None,
) -> str:
    """Append to additional_instructions / user prompt for LLM regeneration."""
    parts = [
        "REGENERATION REQUIRED — previous output failed semantic checks.",
        "Fix ALL of the following (do not repeat the same mistake):",
    ]
    if plan and plan.repair_hints:
        parts.append("Recipe repair hints (mandatory guidance from selection contract):")
        for h in plan.repair_hints[:10]:
            parts.append(f"- {h}")
    for v in validation.violations:
        parts.append(f"- [{v.rule_id}] {v.message}. {v.repair_hint}")
    if critique.repair_instructions:
        parts.append("Critique instructions:")
        for r in critique.repair_instructions[:12]:
            parts.append(f"- {r}")
    if critique.missing_required_constructs:
        parts.append(
            "Missing constructs: " + ", ".join(critique.missing_required_constructs)
        )
    return "\n".join(parts)
