"""Cross-role discussion prompts for UAC alignment (PM / Dev / QA)."""

from __future__ import annotations

from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument

from services.uac.evidence_store import RequirementEvidenceStore


def build_discussion_questions(
    en: JiraEnrichedDocument,
    ambiguities: list[dict[str, Any]],
    store: RequirementEvidenceStore,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    eid = store.add(
        "current_jira",
        f"Discussion seed for {en.jira_key}",
        str(en.jira_key or ""),
        {},
    )
    ev = [eid]
    pm: list[dict[str, Any]] = []
    dev: list[dict[str, Any]] = []
    qa_l: list[dict[str, Any]] = []
    decisions: list[str] = []

    outs = ", ".join(en.affected_outputs or []) or "TBD outputs"
    ents = ", ".join(en.dita_entities or []) or "TBD entities"

    pm.append(
        {
            "question": f"What is the minimum shippable behavior for {outs} given {ents}, and what is explicitly out of scope?",
            "audience": "pm",
            "rationale": "Prevents scope drift between authoring, publishing, and customer commitments.",
            "evidence": ev,
        }
    )
    dev.append(
        {
            "question": "Are we changing parser/DITA-OT hooks, UI model state, or server publishing services — and which layer owns the fix?",
            "audience": "dev",
            "rationale": "Aligns code ownership and regression ownership.",
            "evidence": ev,
        }
    )
    qa_l.append(
        {
            "question": f"Which output pairs require parity evidence (preview vs publish) for {en.jira_key}, and what artifact proves it?",
            "audience": "qa",
            "rationale": "Makes acceptance evidence concrete per output channel.",
            "evidence": ev,
        }
    )

    for amb in ambiguities[:5]:
        who = str(amb.get("who_should_clarify") or "cross_team")
        q = {
            "question": f"Resolve: {amb.get('ambiguity')} — {amb.get('why_it_matters')}",
            "audience": "cross_team" if who == "cross_team" else who,
            "rationale": f"Severity {amb.get('severity')} on area `{amb.get('affected_area')}`.",
            "evidence": list(amb.get("evidence") or []),
        }
        if who == "pm":
            pm.append(q)
        elif who == "dev":
            dev.append(q)
        elif who == "qa":
            qa_l.append(q)
        else:
            pm.append({**q, "audience": "pm", "rationale": f"{q['rationale']} (cross-team alignment owner: PM)."})

    if any(str(a.get("severity")) == "high" for a in ambiguities):
        decisions.append("Document a single agreed expected result per affected output before QA execution.")

    return pm[:12], dev[:12], qa_l[:12], decisions[:8]


__all__ = ["build_discussion_questions"]
