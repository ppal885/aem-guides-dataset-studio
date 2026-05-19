"""Executive summary and section text for enterprise response mode."""

from __future__ import annotations

import re
from typing import Any


def build_executive_summary(
    *,
    jira_key: str | None,
    intent: str,
    risk_level: str,
    confidence: float,
    reasoning_understanding: str,
    failure_count: int,
    coverage_score: int,
) -> str:
    jk = jira_key or "unscoped"
    return (
        f"**Executive summary** — Ticket **{jk}** | intent `{intent}` | assessed risk **{risk_level}** "
        f"| model confidence **{round(confidence * 100)}%**.\n\n"
        f"- **QA read**: {reasoning_understanding[:400].strip() or 'Review indexed Jira and CI attachments.'}\n"
        f"- **CI signal**: {failure_count} correlated failing tests in supplied payloads (0 if none provided).\n"
        f"- **Automation coverage heuristic**: **{coverage_score}/100** (raise with Behave excerpts or enterprise index).\n"
    )


def enterprise_answer_sections(
    *,
    executive_summary: str,
    qa_understanding: str,
    risk_analysis: str,
    regression_scope: str,
    automation_assessment: str,
    coverage: dict[str, Any],
    uac_points: str,
    api_flow: dict[str, Any],
    similar_note: str,
) -> str:
    cov_gaps = "\n".join(f"- {g}" for g in (coverage.get("gaps") or [])[:6]) or "- None flagged"
    api_pts = "\n".join(f"- {x}" for x in (api_flow.get("validation_points") or [])[:6])
    return (
        f"{executive_summary}\n\n"
        f"## QA understanding\n{qa_understanding}\n\n"
        f"## Risk analysis\n{risk_analysis}\n\n"
        f"## Regression scope\n{regression_scope}\n\n"
        f"## Automation assessment\n{automation_assessment}\n\n"
        f"## Existing coverage (heuristic)\n- Score: **{coverage.get('coverage_score', 0)}/100**\n"
        f"- Matching tags: {', '.join((coverage.get('matching_tags') or [])[:8]) or 'n/a'}\n"
        f"### Coverage gaps\n{cov_gaps}\n\n"
        f"## UAC discussion points\n{uac_points}\n\n"
        f"## API validation points\n{api_pts}\n\n"
        f"## Similar historical issues\n{similar_note}\n"
    )


def _dedupe_question_lines(lines: list[str], *, max_items: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines:
        key = re.sub(r"\s+", " ", ln.strip().lower())
        key = re.sub(r"^[#*`\s]+", "", key)
        key = key[:240]
        if len(key) < 2:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(ln.strip())
        if len(out) >= max_items:
            break
    return out


def _extract_question_bullets(markdown_blob: str) -> list[str]:
    out: list[str] = []
    for raw in (markdown_blob or "").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- ") or s.startswith("* "):
            out.append(s[2:].strip())
        elif re.match(r"^\d+\.\s+", s):
            out.append(re.sub(r"^\d+\.\s+", "", s).strip())
    return out


def enterprise_workshop_brief(
    *,
    executive_summary: str,
    qa_understanding: str,
    risk_analysis: str,
    automation_one_liner: str,
    uac_points: str,
    similar_note: str,
) -> str:
    """Shorter workshop view for PM/Dev/QA — avoids repeating the same questions in many sections."""
    risk_short = (risk_analysis or "").strip()
    if len(risk_short) > 1100:
        risk_short = risk_short[:1100].rstrip() + "…"
    qa = (qa_understanding or "").strip()
    bullets = _dedupe_question_lines(_extract_question_bullets(uac_points), max_items=14)
    checklist = "\n".join(f"- {b}" for b in bullets) if bullets else "- Agree repro steps, environments, and pass/fail criteria before UAC."
    return (
        f"{executive_summary}\n\n"
        f"## One-page workshop brief\n"
        f"**Understanding:** {qa}\n\n"
        f"**Risk (short):**\n{risk_short}\n\n"
        f"**Automation / coverage:** {automation_one_liner}\n\n"
        f"## Questions to align (single checklist)\n{checklist}\n\n"
        f"## Similar historical issues\n{similar_note}\n\n"
        "---\n\n"
        "*Longer analysis, Behave draft, and test-data ideas are under **Detailed narrative** below.*\n"
    )
