"""LLM synthesis + dynamic follow-up questions for Jira QA RAG."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.jira_qa_intent_service import INTENTS
from app.services.jira_qa_related_intelligence import classify_related_match
from app.services.llm_service import generate_text, is_llm_available


def pack_chunk_context(chunks: list[dict[str, Any]], *, max_chars: int = 14000) -> str:
    """Turn retrieved chunk dicts into a single evidence string."""
    parts: list[str] = []
    for c in chunks:
        ct = str(c.get("chunk_type") or "")
        jk = str(c.get("jira_key") or "")
        doc = str(c.get("document") or "").strip()
        if doc:
            parts.append(f"### Chunk: {jk} [{ct}]\n{doc}")
    blob = "\n\n".join(parts)
    return blob[:max_chars]


def hits_to_sources(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for h in hits:
        item: dict[str, Any] = {
            "jira_key": h.get("jira_key"),
            "title": h.get("title"),
            "chunk_type": h.get("chunk_type"),
            "score": float(h.get("score") or 0.0),
        }
        if isinstance(h.get("rerank"), dict):
            item["rerank"] = h["rerank"]
        out.append(item)
    return out


async def generate_suggested_questions(
    *,
    jira_key: str | None,
    user_message: str,
    answer_preview: str,
    intent: str,
) -> list[str]:
    """LLM-generated follow-ups; grounded in ticket and answer."""
    if not is_llm_available():
        q: list[str] = []
        if jira_key:
            q.append(f"What should PM, Dev, and QA clarify next for {jira_key}?")
            q.append(f"What scope or dependencies are still unclear on {jira_key}?")
        q.append("What acceptance criteria or oracles are still ambiguous?")
        q.append("What risks or regressions deserve a deeper look given the ticket text?")
        return [x for x in q if x][:6]

    system = (
        "You suggest concise follow-up prompts for QA working with PM and engineering on the same Jira ticket—"
        "alignment and open questions, not post-delivery wrap-up. "
        'Output JSON only: {"questions":["..."]} with 3 to 6 questions. '
        "Each item must be specific to the Jira/issue context and the prior answer, not generic. "
        "No duplicates."
    )
    user = (
        f"jira_key: {jira_key or 'unknown'}\n"
        f"intent: {intent}\n"
        f"user_message: {user_message[:1200]}\n"
        f"answer_excerpt: {answer_preview[:2500]}\n"
    )
    try:
        raw = await generate_text(system, user, max_tokens=400, step_name="jira_qa_followups")
        raw = raw.strip()
        if "```" in raw:
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        qs = data.get("questions") if isinstance(data, dict) else None
        if isinstance(qs, list):
            out = [str(q).strip() for q in qs if str(q).strip()]
            return out[:8]
    except Exception:
        pass
    return []


async def related_ticket_reason(
    base_key: str,
    related_key: str,
    related_title: str,
    base_excerpt: str,
    related_excerpt: str,
) -> str:
    if not is_llm_available():
        overlap = []
        for tok in set(related_title.lower().split()) & set(base_excerpt.lower().split()):
            if len(tok) > 3:
                overlap.append(tok)
        if overlap:
            return f"Overlaps in theme/title tokens: {', '.join(overlap[:6])} (vs {base_key})."
        return f"Vector similarity in QA index suggests related work area to {base_key}."

    system = (
        "In one or two sentences, explain why the related ticket may matter for QA. "
        "Be specific. Do not invent facts absent from excerpts."
    )
    user = (
        f"base: {base_key}\nrelated: {related_key} — {related_title}\n"
        f"base_excerpt:\n{base_excerpt[:1500]}\n\nrelated_excerpt:\n{related_excerpt[:1500]}"
    )
    try:
        text = await generate_text(system, user, max_tokens=180, step_name="jira_qa_related_reason")
        return text.strip()
    except Exception:
        return (
            f"Related ticket {related_key} aligns with embedding/search signals vs {base_key} "
            f"(verify in Jira before relying on similarity)."
        )


async def synthesize_answer_for_intent(
    *,
    intent: str,
    jira_key: str | None,
    user_message: str,
    context_blob: str,
    extra_instructions: str = "",
) -> str:
    if intent not in INTENTS:
        intent = "general_qa_question"

    templates = {
        "ticket_summary": (
            "Summarize for QA/UAC preparation using ONLY the evidence. Sections:\n"
            "## Customer problem\n## Affected feature / area\n## Current behavior\n## Expected behavior\n"
            "## Impact\n## Missing information\n## Important comments\n## Attachment / log signals\n"
            "If a section is unknown from evidence, say *Not stated in indexed ticket data.*"
        ),
        "related_tickets": (
            "The user asked about related issues. Evidence may include candidate tickets; "
            "explain how they might relate for QA (do not claim they are duplicates unless obvious)."
        ),
        "testing_scope": (
            "Provide structured QA testing scope:\n"
            "## Positive scenarios\n## Negative scenarios\n## Edge cases\n## Regression areas\n## Data setup\n"
            "## Environment / version coverage\n## Old vs new behavior checks\n"
            "## Publishing / save / reopen / API / metadata / references checks (AEM Guides)\n"
        ),
        "uac_discussion": (
            "Produce UAC discussion points grouped under:\n"
            "### Product Manager\n### Developer\n### QA\n### Customer/Support (if relevant)\n"
            "Cover scope, expected behavior, unsupported cases, backward compatibility, regression risk, "
            "automation feasibility, test data, acceptance criteria gaps."
        ),
        "uac_preparation": (
            "Same as UAC discussion: structured bullets for PM/Dev/QA/Support. "
            "Highlight acceptance gaps, risks, and what must be demoed or signed off."
        ),
        "edge_cases": (
            "Enumerate edge and boundary scenarios for AEM Guides / DITA (refs, DITAVAL, publish, editors, assets, API). "
            "Mark which are evidenced vs hypothesized."
        ),
        "regression_analysis": (
            "Regression-oriented analysis: blast radius, impacted modules, old vs new editor, publishing paths, "
            "customer-specific data risks. Separate proven vs inferred."
        ),
        "gap_analysis": (
            "Explicit gap analysis: missing AC, unclear oracle, environment unknowns, negative paths, data setup. "
            "Tie each gap to a clarifying question."
        ),
        "risk_prediction": (
            "Risk forecast for QA: production likelihood, regression hotspots, data/content hazards, flakiness. "
            "Stay grounded in ticket evidence; label assumptions."
        ),
        "api_validation": (
            "API-focused validation plan: endpoints, payloads, error contracts, idempotency, auth; "
            "map to AEM Guides services mentioned in evidence."
        ),
        "data_setup": (
            "Test data blueprint: minimal maps/topics, baselines, customer corpus rules, anonymization, "
            "negative fixtures, MIME/BSON stress if relevant."
        ),
        "debugging_assistance": (
            "Debugging aide for QA: hypothesis list, what to capture (HAR, logs, GUIDES traces), "
            "isolation steps, bisect authoring vs publishing failures."
        ),
        "automation_fit": (
            "Integrate the provided automation rubric JSON and narrative:\n"
            "Summarize Automation Fit (Yes/No/Partial), score 0-10, recommended layer (UI/API/Hybrid/Manual only), "
            "reason, risks (flaky UI, clipboard, environment, test data instability, output validation). "
            "List suggested automated vs manual-only scenarios."
        ),
        "test_case_generation": (
            "Generate manual and automation-leaning test cases as markdown tables with columns: "
            "ID, Priority, Preconditions, Test data, Steps, Expected, Automation feasibility (per row)."
        ),
        "test_ticket_creation": (
            "Draft a complete internal QA test ticket with fields: Title, Linked Customer Jira, Objective, "
            "Scope, Out of scope, Test data, Manual testing, Automation testing, Regression areas, Risks, DoD."
        ),
        "gherkin_generation": (
            "Write valid Gherkin/Behave-style scenarios for AEM Guides: Feature, Background (if needed), "
            "Scenarios with Given/When/Then. Use realistic DITA map/topic, Web Editor, save/reopen, preview, "
            "publish, baseline, DITAVAL/conditions, conrefs/keys, metadata, API checks where useful. "
            "No generic placeholders."
        ),
        "general_qa_question": "Answer the QA question using the evidence. Be practical and precise.",
    }
    guide = templates.get(intent, templates["general_qa_question"])

    system = (
        "You are a senior QA engineer for Adobe Experience Manager Guides. "
        "Use only the evidence block for factual claims about the ticket; you may use general AEM Guides "
        "testing knowledge for method/approach when evidence is thin (mark assumptions clearly).\n"
        f"{guide}\n{extra_instructions}"
    )
    user = (
        f"jira_key: {jira_key or 'not fixed'}\nuser_request:\n{user_message[:4000]}\n\n"
        f"### Evidence\n{context_blob[:30000]}"
    )
    if not is_llm_available():
        return (
            f"## Answer\nLLM is not configured. Evidence excerpt follows.\n\n```\n{context_blob[:3500]}\n```"
        )
    return await generate_text(system, user, max_tokens=3500, step_name=f"jira_qa_{intent}")


async def build_related_tickets_payload(
    base_jira_key: str,
    *,
    top_k: int,
    customer: str | None,
    hits: list[dict[str, Any]],
    base_context: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in hits[:top_k]:
        rk = str(h.get("jira_key") or "")
        reason = await related_ticket_reason(
            base_jira_key,
            rk,
            str(h.get("title") or ""),
            base_context,
            str(h.get("document") or ""),
        )
        meta = h.get("metadata") or {}
        match_type, match_reason = classify_related_match(
            base_blob=base_context,
            related_doc=str(h.get("document") or ""),
            related_title=str(h.get("title") or ""),
            related_meta=meta,
        )
        item: dict[str, Any] = {
            "jira_key": rk,
            "title": h.get("title"),
            "status": meta.get("status"),
            "customer": meta.get("customer"),
            "similarity_score": float(h.get("score") or 0.0),
            "match_type": match_type,
            "reason": f"{reason} [{match_type}: {match_reason}]",
        }
        if isinstance(h.get("rerank"), dict):
            item["rerank"] = h["rerank"]
        out.append(item)
    return out
