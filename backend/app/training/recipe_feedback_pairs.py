"""
Build recipe feedback pairs from RunFeedback for contrastive training and retriever boost.

From RunFeedback:
- Positive: (evidence_text, recipe_id) for thumbs_up (recipes_used) or (evidence_text, expected_recipe_id) for corrections
- Negative: (evidence_text, recipe_used) when expected_recipe_id != recipe_used

Output: list of (evidence, recipe_id, label: 1|0) for contrastive training.

Future work (Phase 5.3): Full fine-tuning - use build_recipe_feedback_pairs() to generate training data,
extend finetune_dita_embeddings.py or add finetune_recipe_retriever.py to train on (evidence, recipe_id) pairs.
Requires training pipeline and model versioning.
"""
import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.run_feedback_models import RunFeedback
from app.db.jira_models import JiraIssue


def _get_evidence_for_jira(session: Session, jira_id: str | None) -> str:
    """Get evidence text from JiraIssue for jira_id."""
    if not jira_id:
        return ""
    row = session.query(JiraIssue).filter(JiraIssue.issue_key == jira_id).first()
    if not row:
        return ""
    parts = []
    if row.summary:
        parts.append(str(row.summary)[:2000])
    if row.description:
        parts.append(str(row.description)[:3000])
    if row.text_for_search:
        parts.append(str(row.text_for_search)[:1000])
    return " ".join(parts).strip() if parts else ""


def build_recipe_feedback_pairs(
    session: Session,
    limit: int = 200,
) -> list[tuple[str, str, int]]:
    """
    Build (evidence, recipe_id, label) pairs from RunFeedback.
    label: 1 = positive (should use this recipe), 0 = negative (should not use).
    """
    pairs: list[tuple[str, str, int]] = []
    rows = (
        session.query(RunFeedback)
        .filter(
            (RunFeedback.user_rating.in_(("thumbs_up", "thumbs_down", "wrong_recipe")))
            | (RunFeedback.expected_recipe_id.isnot(None))
        )
        .order_by(RunFeedback.created_at.desc())
        .limit(limit)
        .all()
    )

    for row in rows:
        evidence = _get_evidence_for_jira(session, row.jira_id)
        if not evidence:
            continue

        recipes_used = []
        if row.recipes_used:
            try:
                recipes_used = json.loads(row.recipes_used) if isinstance(row.recipes_used, str) else row.recipes_used
            except (json.JSONDecodeError, TypeError):
                pass
        elif row.eval_metrics:
            try:
                metrics = json.loads(row.eval_metrics or "{}")
                recipes_used = metrics.get("recipes_used", [])
            except (json.JSONDecodeError, TypeError):
                pass

        recipe_used = recipes_used[0] if recipes_used else None
        expected = row.expected_recipe_id

        if row.user_rating == "thumbs_up" and recipe_used:
            pairs.append((evidence, recipe_used, 1))
        elif expected:
            pairs.append((evidence, expected, 1))
            if recipe_used and recipe_used != expected:
                pairs.append((evidence, recipe_used, 0))

    return pairs


def get_feedback_boost_keywords() -> dict[str, str]:
    """
    Get keyword -> recipe_id mapping from routing overrides for retriever boost.
    Used when evidence contains these keywords to boost the corresponding recipe.
    """
    try:
        from app.services.feedback_aggregation_service import load_routing_overrides
        overrides = load_routing_overrides()
        return overrides.get("jira_evidence_keywords") or {}
    except Exception:
        return {}


def export_feedback_pairs_for_eval(session: Session, output_path: str, limit: int = 200) -> int:
    """
    Export (evidence, recipe_id, label) pairs to JSON for eval retrieval accuracy.
    Returns count of pairs written.
    """
    pairs = build_recipe_feedback_pairs(session, limit=limit)
    out = [{"evidence": e[:2000], "recipe_id": r, "label": l} for e, r, l in pairs]
    from pathlib import Path
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        import json
        json.dump(out, f, indent=2)
    return len(out)
