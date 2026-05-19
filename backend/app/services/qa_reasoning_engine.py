"""Structured QA reasoning layer (simulates senior QA thinking)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.jira_qa_domain_heuristics import domain_block_for_prompt
from app.services.llm_service import generate_text, is_llm_available


def _strip_llm_json_fence(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def parse_llm_json_dict(raw: str) -> dict[str, Any] | None:
    """Parse a JSON object from an LLM reply (pure JSON, fenced, or prose + JSON)."""
    text = _strip_llm_json_fence(raw)
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start < 0:
        return None
    decoder = json.JSONDecoder()
    try:
        data, _end = decoder.raw_decode(text, start)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


class QAReasoningEngine:
    async def reason(
        self,
        *,
        context_blob: str,
        enriched_doc: str,
        user_query: str,
        intent: str,
        label_context: str | None = None,
    ) -> dict[str, Any]:
        base: dict[str, Any] = {
            "understanding": "",
            "assumptions": [],
            "missing_information": [],
            "risk_hypothesis": [],
            "test_strategy": [],
            "automation_strategy": [],
            "confidence": 0.45,
        }
        ctx = (context_blob or "").strip()
        if len(ctx) < 80:
            base["understanding"] = "Very little indexed Jira context; answers will stay tentative."
            base["missing_information"].append("Ticket not indexed or minimal description in RAG.")
            base["confidence"] = 0.25
            if not is_llm_available():
                return base

        if not is_llm_available():
            base["understanding"] = "LLM offline — heuristic understanding only."
            base["test_strategy"].append("Smoke authoring + publish path once evidence is indexed.")
            return base

        domain = domain_block_for_prompt()
        system = (
            "You are a principal QA engineer for AEM Guides. Think step-by-step for triage. "
            "Return JSON ONLY with keys: understanding (string), assumptions (array of strings), "
            "missing_information (array), risk_hypothesis (array), test_strategy (array of short bullets), "
            "automation_strategy (array of short bullets), confidence (0-1 float). "
            "Ground claims in EVIDENCE; flag ambiguity. Tie risks to DITA/publish/editor when relevant."
        )
        lc = (label_context or "").strip()
        label_tail = f"\n\n### Label intelligence (Jira labels → domains/heuristics)\n{lc[:3500]}" if lc else ""
        user = (
            f"DOMAIN_HINTS:\n{domain[:4500]}\n\nINTENT: {intent}\nUSER_QUERY:\n{user_query[:2000]}\n\n"
            f"ENRICHED_DOC:\n{(enriched_doc or '')[:4000]}\n\nEVIDENCE:\n{ctx[:10000]}{label_tail}"
        )
        try:
            # 900 tokens often truncates mid-JSON → json.loads fails; allow a fuller object.
            raw = await generate_text(system, user, max_tokens=2200, step_name="jira_copilot_reasoning")
            data = parse_llm_json_dict(raw)
            if not isinstance(data, dict):
                raise ValueError("reasoning_json_not_object")
            base["understanding"] = str(data.get("understanding") or "")[:2000]
            for key in ("assumptions", "missing_information", "risk_hypothesis", "test_strategy", "automation_strategy"):
                val = data.get(key)
                if isinstance(val, list):
                    base[key] = [str(x)[:400] for x in val if str(x).strip()][:20]
            try:
                conf = float(data.get("confidence") if data.get("confidence") is not None else base["confidence"])
            except (TypeError, ValueError):
                conf = base["confidence"]
            base["confidence"] = round(max(0.0, min(1.0, conf)), 3)
        except Exception:
            base["understanding"] = "Reasoning engine could not parse model output; rely on gap/risk modules."
            base["confidence"] = min(base["confidence"], 0.4)
        return base
