"""Feedback loop: consume RunFeedback.suggested_updates into prompts.

Aggregates past validation failures for the same Jira issue and injects
suggested_fixes and recipe_hints into planner prompts.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_aggregated_feedback_for_prompt(
    session: "Session", jira_id: str | None = None, limit: int = 10
) -> str:
    """
    Aggregate RunFeedback.suggested_updates for prompt injection.
    Returns formatted text block for HISTORICAL FEEDBACK, or empty string if none.
    """
    if not jira_id:
        return ""
    try:
        from app.db.run_feedback_models import RunFeedback
        from sqlalchemy import desc

        rows = (
            session.query(RunFeedback)
            .filter(RunFeedback.jira_id == jira_id, RunFeedback.suggested_updates.isnot(None))
            .order_by(desc(RunFeedback.created_at))
            .limit(limit)
            .all()
        )
        if not rows:
            return ""

        all_fixes = []
        all_hints = []
        seen_fixes = set()
        seen_hints = set()

        for row in rows:
            try:
                data = json.loads(row.suggested_updates or "{}")
                for f in data.get("suggested_fixes", []):
                    if f and f not in seen_fixes:
                        seen_fixes.add(f)
                        all_fixes.append(f)
                for h in data.get("recipe_hints", []):
                    if h and h not in seen_hints:
                        seen_hints.add(h)
                        all_hints.append(h)
            except (json.JSONDecodeError, TypeError):
                continue

        if not all_fixes and not all_hints:
            return ""

        lines = ["HISTORICAL FEEDBACK (from past runs for this Jira issue - avoid these issues):"]
        if all_fixes:
            lines.append("Suggested fixes:")
            for f in all_fixes[:5]:
                lines.append(f"  - {f}")
        if all_hints:
            lines.append("Recipe hints:")
            for h in all_hints[:5]:
                lines.append(f"  - {h}")
        return "\n".join(lines) + "\n\n"
    except Exception:
        return ""
