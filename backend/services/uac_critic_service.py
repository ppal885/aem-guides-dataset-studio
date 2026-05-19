"""Public UAC critic facade for evidence-gated QA/UAC answers."""

from __future__ import annotations

from typing import Any, Sequence

from app.services.uac_critic_service import critic_refine_uac_answer  # noqa: F401
from services.uac_generation_service import generate_uac_recommendations


def critique_structured_uac(
    enriched_jira: Any,
    similar_jiras: Sequence[Any] | None,
    retrieval_debug: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the deterministic structured critic/generator path.

    TODO: allow alternate LLM critic providers once provider contracts are
    standardized across Studio deployments.
    """

    return generate_uac_recommendations(enriched_jira, similar_jiras or [], retrieval_debug or {})


__all__ = ["critic_refine_uac_answer", "critique_structured_uac"]
