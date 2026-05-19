"""Generate measurable acceptance criteria grounded in enrichment + evidence ids."""

from __future__ import annotations

from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument

from services.uac.evidence_store import RequirementEvidenceStore


def generate_acceptance_criteria(
    en: JiraEnrichedDocument,
    store: RequirementEvidenceStore,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Returns criteria rows and collected missing_expectations."""

    eid = store.add(
        "current_jira",
        f"Acceptance criteria basis {en.jira_key}",
        str(en.jira_key or ""),
        {},
    )
    missing: list[str] = []
    rows: list[dict[str, Any]] = []

    outs = [str(o) for o in (en.affected_outputs or []) if str(o).strip()] or ["unspecified_output"]
    ents = [str(x) for x in (en.dita_entities or []) if str(x).strip()] or ["unspecified_entity"]

    primary_out = outs[0]
    primary_ent = ents[0]

    if primary_out == "unspecified_output":
        missing.append("Define which output(s) must pass (preview, Native PDF, AEM Sites, baseline).")

    exp = (en.expected_behavior or "").strip() or "behavior agreed in ticket after clarification"

    rows.append(
        {
            "criterion": f"Given {primary_ent} content in scope, when the fix is applied on {primary_out}, then {exp}.",
            "entity": primary_ent,
            "output": primary_out,
            "expected_behavior": exp[:800],
            "given": f"Authored content uses {primary_ent} as described in {en.jira_key}.",
            "when": f"User publishes or generates {primary_out} for the repro map/topics.",
            "then": exp[:800],
            "evidence": [eid],
        }
    )

    if len(outs) > 1:
        second = outs[1]
        rows.append(
            {
                "criterion": (
                    f"Parity: behavior on `{second}` must match agreed reference for {primary_ent} "
                    f"(no undocumented divergence vs `{primary_out}`)."
                ),
                "entity": primary_ent,
                "output": f"{primary_out}|{second}",
                "expected_behavior": "Documented parity: same logical content outcomes across outputs unless exempted in ticket.",
                "given": f"Same source map/topics as {en.jira_key}.",
                "when": f"Generate {primary_out} and {second}.",
                "then": "No regression versus stated baseline behavior in ticket/comments.",
                "evidence": [eid],
            }
        )

    if (en.actual_behavior or "").strip():
        rows.append(
            {
                "criterion": f"Regression guard: actual failure mode `{((en.actual_behavior or '')[:200])}` must not reproduce.",
                "entity": primary_ent,
                "output": primary_out,
                "expected_behavior": "Failure mode absent under defined repro.",
                "given": "Repro steps from ticket.",
                "when": "Execute repro post-fix.",
                "then": "Observed behavior matches expected behavior; no recurrence of reported failure.",
                "evidence": [eid],
            }
        )

    return rows[:12], missing


__all__ = ["generate_acceptance_criteria"]
