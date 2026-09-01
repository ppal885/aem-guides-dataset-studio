"""Print the content-minimal FJ-18 paired fixture qualification report."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
TEST_MODULE = BACKEND_ROOT / "tests" / "test_fluffyjaws_second_pass_fusion.py"
sys.path.insert(0, str(BACKEND_ROOT))

CASE_LABELS = (
    "Native PDF publishing/configuration",
    "DITA structural/output hierarchy",
    "XML Editor copy/paste",
    "Assets capability family",
    "Straightforward local-evidence case",
)


def _section_counts(result: Any) -> dict[str, int]:
    return {
        section.section_key: len(section.items)
        for section in result.structured_plan.sections
    }


def main() -> None:
    namespace = runpy.run_path(str(TEST_MODULE))
    canonical_runtime = namespace["CanonicalTestPlanRuntime"]
    shadow_service = namespace["ReasoningEvidenceShadowService"]
    shadow_config = namespace["FluffyJawsShadowConfig"]
    runtime_mode = namespace["FluffyJawsRuntimeMode"]
    entry_point = namespace["RuntimeEntryPoint"]
    generation_profile = namespace["GenerationProfile"]
    get_question_trace = namespace["get_last_question_retrieval_trace"]
    get_provider_trace = namespace["get_last_fluffyjaws_shadow_trace"]
    get_decision = namespace["get_last_second_pass_influence_decision"]
    baseline_fixture = namespace["_baseline_fixture"]
    provider_factory = namespace["_provider"]
    service_factory = namespace["_service"]
    authorization = namespace["_authorization"]

    rows: list[dict[str, Any]] = []
    for index, label in enumerate(CASE_LABELS):
        baseline, fixture = baseline_fixture(index)
        disabled_runtime = canonical_runtime(
            shadow_service=shadow_service(
                config=shadow_config(
                    mode=runtime_mode.FLUFFYJAWS_DISABLED
                )
            )
        )
        disabled_request = disabled_runtime.build_request(
            jira_key=fixture["jira_key"],
            tenant_id="fluffyjaws-fj18-report",
            entry_point=entry_point.PYTHON_API,
            generation_profile=generation_profile.BACKEND_COMPATIBILITY,
        )
        disabled = disabled_runtime.generate_backend_compatibility(
            request=disabled_request,
            packet=fixture,
        )
        disabled_trace = get_question_trace()

        second_pass_runtime = canonical_runtime(
            shadow_service=service_factory(
                provider=provider_factory(),
                attestation_check=authorization,
            )
        )
        second_pass_request = second_pass_runtime.build_request(
            jira_key=fixture["jira_key"],
            tenant_id="fluffyjaws-fj18-report",
            entry_point=entry_point.PYTHON_API,
            generation_profile=generation_profile.BACKEND_COMPATIBILITY,
        )
        second_pass = second_pass_runtime.generate_backend_compatibility(
            request=second_pass_request,
            packet=fixture,
        )
        second_pass_trace = get_question_trace()
        provider_trace = get_provider_trace()
        decision = get_decision()
        if (
            disabled_trace is None
            or second_pass_trace is None
            or provider_trace is None
            or decision is None
        ):
            raise RuntimeError("FJ-18 paired trace was not captured")

        disabled_questions = disabled.output_payload["missing_questions"]
        second_pass_questions = second_pass.output_payload["missing_questions"]
        rows.append(
            {
                "case_id": baseline["case_id"],
                "case_label": label,
                "fixture_sha256": baseline["fixture_sha256"],
                "request_id": decision.request_id,
                "questions": {
                    "disabled_count": len(disabled_questions),
                    "second_pass_count": len(second_pass_questions),
                    "unchanged": disabled_questions == second_pass_questions,
                },
                "evidence": {
                    "disabled_record_count": len(disabled.evidence_bundle.records),
                    "second_pass_record_count": len(
                        second_pass.evidence_bundle.records
                    ),
                    "provider_call_count": provider_trace.metrics.provider_call_count,
                    "provider_fused_count": len(
                        decision.provider_fused_evidence_ids
                    ),
                    "provider_consumed_count": len(
                        decision.provider_consumed_evidence_ids
                    ),
                },
                "hypotheses": {
                    "disabled_count": len(disabled.output_payload["hypotheses"]),
                    "second_pass_count": len(
                        second_pass.output_payload["hypotheses"]
                    ),
                    "changed_ids": list(decision.changed_hypothesis_ids),
                },
                "dispositions": {
                    "disabled_count": len(
                        disabled.output_payload["coverage_dispositions"]
                    ),
                    "second_pass_count": len(
                        second_pass.output_payload["coverage_dispositions"]
                    ),
                    "changed_ids": list(decision.changed_disposition_ids),
                },
                "full_qe_coverage": {
                    "disabled_section_item_counts": _section_counts(disabled),
                    "second_pass_section_item_counts": _section_counts(second_pass),
                    "section_deltas": [
                        delta.model_dump(mode="json")
                        for delta in decision.section_deltas
                    ],
                },
                "open_questions": {
                    "added_ids": list(decision.added_open_question_ids),
                    "removed_ids": list(decision.removed_open_question_ids),
                },
                "acceptance": {
                    "output_unchanged": decision.acceptance_output_unchanged,
                    "candidate_count_disabled": len(
                        disabled.output_payload["acceptance_candidates"]
                    ),
                    "candidate_count_second_pass": len(
                        second_pass.output_payload["acceptance_candidates"]
                    ),
                },
                "lineage": [
                    lineage.model_dump(mode="json")
                    for lineage in decision.influence_lineages
                ],
                "decision": decision.model_dump(mode="json"),
                "unsupported_expansion": bool(decision.blocking_reason_codes),
            }
        )

    report = {
        "schema_version": "aem-guides-fj18-fixture-comparison-v1",
        "provider_mode": "CONTROLLED_INJECTED_PROVIDER",
        "default_runtime_mode": "FLUFFYJAWS_DISABLED",
        "live_provider_status": "BLOCKED_BY_FJ_02",
        "case_count": len(rows),
        "all_cases_passed": all(
            row["decision"]["status"] == "PASSED" for row in rows
        ),
        "unexplained_output_growth_count": sum(
            1 for row in rows if row["unsupported_expansion"]
        ),
        "cases": rows,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
