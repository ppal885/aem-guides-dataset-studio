from __future__ import annotations

import asyncio
import base64
import contextlib
from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock, patch

from app.benchmarks.authoring_eval.models import (
    BenchmarkCase,
    BenchmarkDefaults,
    BenchmarkManifest,
    CaseEvalReport,
    SuiteReport,
)
from app.benchmarks.authoring_eval.scoring import apply_case_assertions, build_dimension_scores
from app.core.schemas_chat_authoring import (
    ChatAttachmentRef,
    ChatAuthoringRequestPayload,
    ChatDitaGenerationOptions,
    ChatImageContext,
    ScreenshotContentModel,
)
from app.services.chat_dita_authoring_service import ChatDitaAuthoringService

# 1×1 transparent PNG (valid) for cases without a real screenshot asset.
_MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _vision_context_from_case(case: BenchmarkCase) -> ChatImageContext:
    vs = case.vision.structured
    return ChatImageContext(
        summary=case.vision.summary or "Benchmark screenshot stub.",
        visible_text=list(case.vision.visible_text),
        warnings=list(case.vision.warnings),
        vision_provider=case.vision.vision_provider,
        structured=ScreenshotContentModel(
            title=vs.title,
            numbered_steps=list(vs.numbered_steps),
            bullet_lists=[list(x) for x in vs.bullet_lists],
            ui_labels=list(vs.ui_labels),
            confidence=vs.confidence,
            uncertainty_warnings=list(vs.uncertainty_warnings),
        ),
    )


def _load_bytes(dataset_root: Path, rel: str | None, *, fallback: bytes) -> bytes:
    if not rel:
        return fallback
    p = dataset_root / rel
    if not p.is_file():
        return fallback
    return p.read_bytes()


def _aggregate(reports: list[CaseEvalReport]) -> dict[str, Any]:
    n = len(reports)
    if n == 0:
        return {"n_cases": 0}

    def _mean_bool(key: Callable[[CaseEvalReport], bool | None]) -> float | None:
        vals = [key(r) for r in reports]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        return sum(1 for v in vals if v) / len(vals)

    def _mean_float(getter: Callable[[CaseEvalReport], float | None]) -> float | None:
        vals = [getter(r) for r in reports]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        return sum(vals) / len(vals)

    topic_correct = [r.dimensions.topic_type_correct for r in reports]
    topic_defined = [t for t in topic_correct if t is not None]

    return {
        "n_cases": n,
        "xml_validity_rate": sum(1 for r in reports if r.dimensions.xml_valid) / n,
        "structural_correctness_rate": sum(1 for r in reports if r.dimensions.structural_ok) / n,
        "topic_type_correctness_rate": (sum(1 for t in topic_defined if t) / len(topic_defined))
        if topic_defined
        else None,
        "style_adherence_mean": _mean_float(lambda r: r.dimensions.style_adherence),
        "mean_over_copying_risk": sum(r.dimensions.over_copying_risk for r in reports) / n,
        "mean_unresolved_xref_conref_rate": sum(r.dimensions.unresolved_xref_conref_rate for r in reports) / n,
        "pipeline_repair_rate": sum(1 for r in reports if r.dimensions.pipeline_repair_used) / n,
        "insertion_success_rate": _mean_bool(lambda r: r.dimensions.insertion_success),
        "regeneration_rate": None,
        "edit_after_generation_rate": None,
        "all_assertions_passed": all(not r.assertion_failures for r in reports),
        "failed_case_ids": [r.case_id for r in reports if r.assertion_failures],
    }


async def evaluate_single_case(
    service: ChatDitaAuthoringService,
    case: BenchmarkCase,
    *,
    dataset_root: Path,
    defaults: BenchmarkDefaults,
    mock_aem_save: bool = False,
) -> CaseEvalReport:
    """Run one manifest case with a stubbed vision stage (deterministic offline eval)."""
    image_bytes = _load_bytes(dataset_root, case.screenshot_path, fallback=_MINIMAL_PNG)
    ref_raw = ""
    if case.reference_path:
        ref_path = dataset_root / case.reference_path
        if ref_path.is_file():
            ref_raw = ref_path.read_text(encoding="utf-8")

    img = ChatAttachmentRef(
        asset_id=f"bench-img-{case.id}",
        kind="image",
        filename="bench.png",
        mime_type="image/png",
        size_bytes=len(image_bytes),
        url=f"/bench/{case.id}.png",
    )
    attachments: list[ChatAttachmentRef] = [img]
    if case.reference_path and ref_raw:
        attachments.append(
            ChatAttachmentRef(
                asset_id=f"bench-ref-{case.id}",
                kind="reference_dita",
                filename=Path(case.reference_path).name,
                mime_type="application/xml",
                size_bytes=len(ref_raw.encode("utf-8")),
                url=f"/bench/{case.id}.dita",
            )
        )

    opts = ChatDitaGenerationOptions(
        dita_type=case.dita_type_override,
        style_strictness=case.style_strictness,
        strict_validation=case.strict_validation,
        output_mode=case.output_mode,
        save_path=case.save_path,
    )
    payload = ChatAuthoringRequestPayload(content=case.prompt, attachments=attachments, generation_options=opts)

    captured_xml: list[str] = []

    async def fake_vision(*, image, image_bytes, user_prompt):
        return _vision_context_from_case(case)

    def fake_read(aid: str):
        if aid == img.asset_id:
            return image_bytes, {}
        if ref_raw and aid.startswith("bench-ref-"):
            return ref_raw.encode("utf-8"), {}
        return b"", {}

    def fake_save(**kwargs):
        content = kwargs.get("content") or ""
        captured_xml.append(str(content))
        return ChatAttachmentRef(
            asset_id=f"bench-out-{case.id}",
            kind="generated_dita",
            filename=kwargs.get("filename") or "out.dita",
            mime_type="application/xml",
            size_bytes=len(str(content).encode("utf-8")),
            url=f"/bench/out-{case.id}",
        )

    review_payload = {"validation": [], "aem_guides_validation_errors": [], "quality_score": 88}

    patches: list[Any] = [
        patch(
            "app.services.topic_generation.screenshot_understanding_service.extract_screenshot_context",
            side_effect=fake_vision,
        ),
        patch("app.services.chat_dita_authoring_service.read_asset_bytes", side_effect=fake_read),
        patch("app.services.chat_dita_authoring_service.save_text_asset", side_effect=fake_save),
        patch(
            "app.services.topic_generation.dita_validation_service.build_review_snapshot",
            new=AsyncMock(return_value=review_payload),
        ),
        patch(
            "app.services.topic_generation.dita_validation_service.validate_dita_folder",
            lambda _p: {"errors": [], "warnings": []},
        ),
        patch("app.services.chat_dita_authoring_service.is_llm_available", return_value=False),
    ]
    if mock_aem_save and case.expect_saved_to_aem:
        patches.append(patch.object(service, "_save_to_aem", return_value="/mock/aem/path/topic.dita"))

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = await service.generate_topic_from_request(
            payload=payload,
            session_id=defaults.session_id,
            user_id=defaults.user_id,
            tenant_id=defaults.tenant_id,
        )

    generated = "\n".join(captured_xml) if captured_xml else (result.xml_preview or "")
    dims, extras = build_dimension_scores(
        case=case,
        generated_xml=generated,
        result_status=result.status,
        generated_dita_type=result.dita_type,
        reference_raw=ref_raw if ref_raw.strip() else None,
        debug=result.debug.model_dump(mode="json"),
    )
    failures = apply_case_assertions(case, dims)
    return CaseEvalReport(
        case_id=case.id,
        ok=len(failures) == 0,
        dimensions=dims,
        result_status=result.status,
        generated_dita_type=result.dita_type,
        assertion_failures=failures,
        extra={**extras, "xml_chars": len(generated)},
    )


async def evaluate_manifest(
    service: ChatDitaAuthoringService,
    manifest: BenchmarkManifest,
    *,
    dataset_root: Path,
    mock_aem_save: bool = True,
) -> SuiteReport:
    reports: list[CaseEvalReport] = []
    for case in manifest.cases:
        r = await evaluate_single_case(
            service,
            case,
            dataset_root=dataset_root,
            defaults=manifest.defaults,
            mock_aem_save=mock_aem_save,
        )
        reports.append(r)
    return SuiteReport(
        manifest_path=str(dataset_root / "manifest.yaml"),
        case_reports=reports,
        aggregates=_aggregate(reports),
    )


def run_manifest_sync(
    manifest_path: Path,
    *,
    dataset_root: Path | None = None,
    mock_aem_save: bool = True,
) -> SuiteReport:
    root = dataset_root or manifest_path.parent
    manifest = BenchmarkManifest.load_yaml(manifest_path)
    service = ChatDitaAuthoringService()
    return asyncio.run(
        evaluate_manifest(service, manifest, dataset_root=root, mock_aem_save=mock_aem_save)
    )
