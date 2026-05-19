"""Convert parsed :class:`TopicDraft` / :class:`ChatSemanticPlan` to another DITA root type (content-preserving)."""

from __future__ import annotations

from dataclasses import replace

from app.core.schemas_chat_authoring import ChatDitaType, ChatSemanticPlan, ChatSemanticPlanSection
from app.services.dita_topic_draft import TopicDraft


def _flatten_section_text(draft: TopicDraft) -> list[str]:
    out: list[str] = []
    for s in draft.sections:
        if (s.purpose or "").strip():
            out.append(s.purpose.strip())
        for d in s.details:
            if d.strip():
                out.append(d.strip())
    for n in draft.notes:
        if n.text.strip():
            out.append(n.text.strip())
    return out


def convert_plan_and_draft_to_type(
    plan: ChatSemanticPlan,
    draft: TopicDraft,
    new_type: ChatDitaType,
) -> tuple[ChatSemanticPlan, TopicDraft]:
    if plan.dita_type == new_type:
        return plan, draft

    flat = _flatten_section_text(draft)
    if not flat:
        flat = [plan.shortdesc.strip() or plan.title or "Content."]

    new_sections: list[ChatSemanticPlanSection]

    if new_type == "task":
        head, *rest = flat[0], flat[1:]
        ctx = [head] if head else ["See the user interface."]
        step_items = rest if rest else [head]
        new_sections = [
            ChatSemanticPlanSection(name="context", purpose="", details=ctx),
            ChatSemanticPlanSection(
                name="steps",
                purpose="",
                details=step_items or ["Follow the on-screen instructions."],
            ),
            ChatSemanticPlanSection(
                name="result",
                purpose="",
                details=["Confirm the outcome in the product."],
            ),
        ]
    elif new_type == "concept":
        new_sections = [ChatSemanticPlanSection(name="overview", purpose="", details=flat[:40])]
    elif new_type == "reference":
        new_sections = [ChatSemanticPlanSection(name="reference content", purpose="", details=flat[:40])]
    else:
        new_sections = [ChatSemanticPlanSection(name="body", purpose="", details=flat[:40])]

    new_plan = plan.model_copy(update={"dita_type": new_type, "sections": new_sections})
    new_draft = replace(
        draft,
        dita_type=new_type,
        title=plan.title,
        shortdesc=plan.shortdesc,
        sections=new_sections,
    )
    return new_plan, new_draft
