from __future__ import annotations

from app.core.schemas_prompt_router import ExecutionPolicyDecision, PromptRouteDecision


def decide_execution_policy(route: PromptRouteDecision) -> ExecutionPolicyDecision:
    if not route.supported and route.intent == "unsupported":
        return ExecutionPolicyDecision(
            action="reject_as_unsupported",
            reason="Prompt is outside the currently supported DITA-first workflow.",
            clarification_question=(
                "I can help with DITA questions, DITA generation, XML review, screenshots, and dataset jobs. "
                "What DITA-focused request would you like instead?"
            ),
            candidate_contract=dict(route.candidate_contract or {}),
        )

    if route.intent == "dita_generation":
        preview = dict((route.candidate_contract or {}).get("preview") or {})
        if str(preview.get("bundle_type") or "").strip().lower() == "unsupported":
            return ExecutionPolicyDecision(
                action="reject_as_unsupported",
                reason="The interpreted generate_dita request mixes in unsupported outputs.",
                clarification_question=str(preview.get("clarification_question") or "").strip() or None,
                candidate_contract=dict(route.candidate_contract or {}),
            )
        if route.needs_clarification:
            return ExecutionPolicyDecision(
                action="clarify_first",
                reason="The generation request is ambiguous or missing a material bundle decision.",
                clarification_question=str(preview.get("clarification_question") or "").strip() or None,
                candidate_contract=dict(route.candidate_contract or {}),
            )
        return ExecutionPolicyDecision(
            action="preview_first",
            reason="DITA generation should be reviewed before execution.",
            review_required=True,
            candidate_contract=dict(route.candidate_contract or {}),
        )

    if route.intent == "dita_answer_then_generation":
        preview = dict((route.candidate_contract or {}).get("preview") or {})
        if str(preview.get("bundle_type") or "").strip().lower() == "unsupported":
            return ExecutionPolicyDecision(
                action="reject_as_unsupported",
                reason="The generation portion of the mixed DITA request is unsupported.",
                clarification_question=str(preview.get("clarification_question") or "").strip() or None,
                candidate_contract=dict(route.candidate_contract or {}),
            )
        if route.needs_clarification:
            return ExecutionPolicyDecision(
                action="answer_then_preview",
                reason="Answer the DITA question, then ask for the missing generation detail.",
                clarification_question=str(preview.get("clarification_question") or "").strip() or None,
                candidate_contract=dict(route.candidate_contract or {}),
            )
        return ExecutionPolicyDecision(
            action="answer_then_preview",
            reason="Mixed DITA prompt should answer first and show a review-first generation preview.",
            review_required=True,
            candidate_contract=dict(route.candidate_contract or {}),
        )

    if route.intent in {"dita_question", "aem_guides_question", "native_pdf_guidance", "dita_ot_build"}:
        return ExecutionPolicyDecision(
            action="answer_directly",
            reason="Grounded question answer path is appropriate for this prompt.",
            candidate_contract=dict(route.candidate_contract or {}),
        )

    if route.intent in {"dita_review", "dataset_job", "artifact_request", "screenshot_authoring"}:
        return ExecutionPolicyDecision(
            action="run_directly",
            reason="This intent is handled by the specialized execution path.",
            candidate_contract=dict(route.candidate_contract or {}),
        )

    return ExecutionPolicyDecision(
        action="answer_directly",
        reason="Fallback to existing chat behavior.",
        candidate_contract=dict(route.candidate_contract or {}),
    )
