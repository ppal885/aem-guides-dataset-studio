"""Unit tests for screenshot-guided DITA authoring pipeline orchestration."""

import pytest

from app.core.schemas_chat_authoring import (
    ChatAttachmentRef,
    ChatDitaGenerationOptions,
    ChatDitaValidationResult,
    ChatImageContext,
    ChatReferenceDitaSummary,
    ChatSemanticPlan,
    ChatSemanticPlanSection,
    ScreenshotContentModel,
)
from app.services.dita_authoring_pipeline import (
    RepairStageResult,
    SerializationResult,
    ValidationStageResult,
    run_screenshot_guided_pipeline,
)


@pytest.mark.anyio
async def test_pipeline_runs_stages_in_order_and_records_trace(monkeypatch):
    async def fake_extract(*, image, image_bytes, user_prompt):
        return ChatImageContext(
            summary="s",
            structured=ScreenshotContentModel(confidence=0.91, numbered_steps=["a"]),
        )

    monkeypatch.setattr(
        "app.services.topic_generation.screenshot_understanding_service.extract_screenshot_context",
        fake_extract,
    )

    class _Exec:
        async def summarize_reference_dita(self, **kwargs):
            return ChatReferenceDitaSummary(structure_summary="none")

        async def build_semantic_plan(self, **kwargs):
            return ChatSemanticPlan(
                title="Topic",
                dita_type="task",
                shortdesc="sd",
                audience="authors",
                purpose="p",
                sections=[
                    ChatSemanticPlanSection(name="context", purpose="c", details=["d"]),
                ],
            )

        async def render_dita_xml(self, **kwargs):
            return SerializationResult(
                xml="<task id='t1'><title>Topic</title><taskbody><steps><step><cmd/></step></steps></taskbody></task>",
                mode="programmatic",
            )

        async def validate_candidate(self, **kwargs):
            return ValidationStageResult(
                normalized_xml=kwargs["xml"],
                validation_result=ChatDitaValidationResult(valid=True),
                review_snapshot={"quality_score": 90},
            )

        async def repair_once_if_needed(self, **kwargs):
            raise AssertionError("repair must not run when validation is valid")

    img = ChatAttachmentRef(
        asset_id="i1",
        kind="image",
        filename="x.png",
        mime_type="image/png",
        size_bytes=4,
        url="/a",
    )
    s1, s2, s3, s4, s5, s6, s7, val, s9, trace = await run_screenshot_guided_pipeline(
        executor=_Exec(),
        user_prompt="make a task",
        tenant_id="t1",
        image=img,
        image_bytes=b"\x89PNG\r\n",
        reference_attachment=None,
        reference_text="",
        base_options=ChatDitaGenerationOptions(strict_validation=True, style_strictness="high"),
        strictness="high",
        reference_guided_enabled=True,
    )

    assert s9 is None
    assert val.validation_result.valid is True
    assert s7.mode == "programmatic"
    names = [rec.stage for rec in trace.stages]
    assert names == [
        "analyze_screenshot",
        "analyze_reference_topic",
        "resolve_authoring_pattern",
        "infer_topic_type",
        "build_semantic_plan",
        "merge_screenshot_structured",
        "build_structured_draft",
        "serialize_xml",
        "validate",
    ]
    assert trace.stages[0].detail.get("screenshot_confidence") == pytest.approx(0.91)
    dumped = trace.to_debug_list()
    assert len(dumped) == 9
    assert all("stage" in row and "order" in row for row in dumped)


@pytest.mark.anyio
async def test_pipeline_optional_repair_stage(monkeypatch):
    async def fake_extract(**kwargs):
        return ChatImageContext(structured=ScreenshotContentModel())

    monkeypatch.setattr(
        "app.services.topic_generation.screenshot_understanding_service.extract_screenshot_context",
        fake_extract,
    )

    class _Exec:
        async def summarize_reference_dita(self, **kwargs):
            return ChatReferenceDitaSummary()

        async def build_semantic_plan(self, **kwargs):
            return ChatSemanticPlan(
                title="T",
                dita_type="concept",
                shortdesc="x",
                sections=[ChatSemanticPlanSection(name="body", purpose="p", details=[])],
            )

        async def render_dita_xml(self, **kwargs):
            return SerializationResult(xml="<concept id='c1'><title>T</title><conbody/></concept>", mode="llm")

        async def validate_candidate(self, **kwargs):
            return ValidationStageResult(
                normalized_xml=kwargs["xml"],
                validation_result=ChatDitaValidationResult(valid=False, validator_errors=["e1"]),
                review_snapshot={},
            )

        async def repair_once_if_needed(self, **kwargs):
            return RepairStageResult(
                xml=kwargs["xml"].replace("<conbody/>", "<conbody><p>fixed</p></conbody>"),
                validation_result=ChatDitaValidationResult(valid=True, repaired=True),
                review_snapshot={},
                repaired=True,
            )

    img = ChatAttachmentRef(
        asset_id="i1",
        kind="image",
        filename="x.png",
        mime_type="image/png",
        size_bytes=4,
        url="/a",
    )
    _s1, _s2, _s3, _s4, _s5, _s6, _s7, val, s9, trace = await run_screenshot_guided_pipeline(
        executor=_Exec(),
        user_prompt="x",
        tenant_id="t1",
        image=img,
        image_bytes=b"x",
        reference_attachment=None,
        reference_text="",
        base_options=ChatDitaGenerationOptions(strict_validation=True),
        strictness="low",
        reference_guided_enabled=True,
    )

    assert s9 is not None
    assert s9.validation_result.valid is True
    assert trace.stages[-1].stage == "repair_optional"
