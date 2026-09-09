"""Fail-closed tests for the gate-receipt Jira AC posting boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

try:
    from backend.scripts import post_acs_to_jira as poster
except ModuleNotFoundError:  # backend pytest is commonly invoked with backend/ as cwd
    from scripts import post_acs_to_jira as poster


VALID_PLAN = """**Acceptance Criteria**
- AC-01 [Proposed]: (Basic) Given an author has an editable topic | When the author saves the topic | Then the saved value is visible after the topic is reopened | Evidence: Jira GUIDES-12345 description.
- AC-02 [Confirmed]: (Negative) Given an author lacks edit permission | When the author attempts to save the topic | Then the save is rejected and the stored topic remains unchanged | Evidence: accepted UAC clause UAC-02.

**Test Scenarios**
- P1 [Basic]: Action: Save and reopen an editable topic. Expected: The saved value remains visible.
- P1 [Negative]: Action: Attempt the save without edit permission. Expected: The save is rejected and stored content is unchanged.

**Regression Areas**
- Reopen a previously saved topic to confirm existing content remains readable.

**Automation Coverage & Gaps**
- Main feature coverage: Not covered - no exact existing automation symbol was found.
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_receipt(path: Path, receipt: dict) -> None:
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def _bundle(tmp_path: Path, *, plan_text: str = VALID_PLAN) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    plan = tmp_path / "plan.md"
    manifest = tmp_path / "manifest.json"
    combined = tmp_path / "combined.md"
    compact = tmp_path / "compact.md"
    extracted = tmp_path / "acs.json"
    receipt_path = tmp_path / "gate-receipt.json"

    plan.write_text(plan_text, encoding="utf-8")
    manifest.write_text(json.dumps({"issue": "GUIDES-12345"}) + "\n", encoding="utf-8")
    combined.write_text(plan_text + "\n**Appendix A - Evidence**\n- Evidence is hash-bound.\n", encoding="utf-8")
    compact.write_text(
        poster._run_canonical(poster._CANONICAL_RENDERER, plan, "compact renderer"),
        encoding="utf-8",
    )
    extracted.write_text(
        poster._run_canonical(poster._CANONICAL_EXTRACTOR, plan, "AC extractor"),
        encoding="utf-8",
    )
    artifacts = {
        name: {"path": path.name, "sha256": _sha(path)}
        for name, path in {
            "plan": plan,
            "manifest": manifest,
            "combined": combined,
            "compact": compact,
            "extracted_acs": extracted,
        }.items()
    }
    _write_receipt(
        receipt_path,
        {
            "schema_version": "aem-guides-gate-receipt-v1",
            "passed": True,
            "postable": True,
            "issue": "GUIDES-12345",
            "generated_at": "2026-08-24T12:00:00Z",
            "artifacts": artifacts,
        },
    )
    return {
        "plan": plan,
        "manifest": manifest,
        "combined": combined,
        "compact": compact,
        "extracted": extracted,
        "receipt": receipt_path,
    }


def _verify(paths: dict[str, Path], **kwargs) -> poster.VerifiedPostPayload:
    return poster.verify_gate_receipt(
        key=kwargs.pop("key", "GUIDES-12345"),
        plan_path=kwargs.pop("plan_path", paths["plan"]),
        manifest_path=kwargs.pop("manifest_path", paths["manifest"]),
        combined_path=kwargs.pop("combined_path", paths["combined"]),
        receipt_path=kwargs.pop("receipt_path", paths["receipt"]),
        **kwargs,
    )


def _mutate_receipt(paths: dict[str, Path], mutate) -> None:
    receipt = json.loads(paths["receipt"].read_text(encoding="utf-8"))
    mutate(receipt)
    _write_receipt(paths["receipt"], receipt)


class FakeJira:
    def __init__(
        self,
        *,
        current: str = "",
        current_reads: list[str] | None = None,
        read_error: Exception | None = None,
        omit_ac_field: bool = False,
    ) -> None:
        self.current = current
        self.current_reads = list(current_reads or [])
        self.read_error = read_error
        self.omit_ac_field = omit_ac_field
        self.writes: list[tuple] = []
        self.reads: list[str] = []

    def get_issue(self, key: str, fields: str) -> dict:
        self.reads.append(fields)
        if fields == poster.AC_FIELD:
            if self.read_error:
                raise self.read_error
            if self.omit_ac_field:
                return {"key": key, "fields": {}}
            value = self.current_reads.pop(0) if self.current_reads else self.current
            return {"key": key, "fields": {poster.AC_FIELD: value}}
        return {"key": key, "fields": {poster.QE_ASSIGNEE_FIELD: {"name": "qe-user"}}}

    def set_acceptance_criteria(
        self, key: str, text: str, *, review_label: str, review_comment: str | None
    ) -> None:
        self.writes.append((key, text, review_label, review_comment))
        self.current = text

    def update_issue(self, key: str, *, fields: dict) -> None:
        assert set(fields) == {poster.AC_FIELD}
        self.writes.append((key, fields[poster.AC_FIELD], None, None))
        self.current = fields[poster.AC_FIELD]


@pytest.fixture
def transport_only(monkeypatch):
    """Legacy transport unit tests; canonical binding is tested separately below."""
    monkeypatch.setattr(poster, "_reverify_for_apply", lambda payload: None)


def test_valid_receipt_uses_strict_records_and_preserves_status(tmp_path: Path) -> None:
    payload = _verify(_bundle(tmp_path))

    assert [row["schema_version"] for row in payload.criteria] == [
        "aem-guides-ac-v1",
        "aem-guides-ac-v1",
    ]
    assert [row["status"] for row in payload.criteria] == ["Proposed", "Confirmed"]
    # Non-negotiable: the [Proposed]/[Confirmed] status tag is NEVER written to Jira.
    assert payload.acceptance_criteria_text == (
        "AC-01: an author has an editable topic; when the author saves the topic, "
        "the saved value is visible after the topic is reopened.\n\n"
        "AC-02: an author lacks edit permission; when the author attempts to save the topic, "
        "the save is rejected and the stored topic remains unchanged."
    )
    assert "[Proposed]" not in payload.acceptance_criteria_text
    assert "[Confirmed]" not in payload.acceptance_criteria_text
    assert "| Evidence:" not in payload.acceptance_criteria_text
    assert "Given " not in payload.acceptance_criteria_text
    assert "When " not in payload.acceptance_criteria_text
    assert "Then " not in payload.acceptance_criteria_text
    assert "(Basic)" not in payload.acceptance_criteria_text
    assert "(Negative)" not in payload.acceptance_criteria_text
    assert "Jira GUIDES-12345 description" not in payload.acceptance_criteria_text
    assert "accepted UAC clause UAC-02" not in payload.acceptance_criteria_text


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "aem-guides-gate-receipt-v0", "schema_version"),
        ("passed", False, "passed=true"),
        ("postable", False, "postable=true"),
        ("issue", "GUIDES-99999", "does not match"),
        ("generated_at", "2026-08-24", "timezone-aware"),
    ],
)
def test_receipt_schema_flags_key_and_timestamp_fail_closed(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    paths = _bundle(tmp_path)
    _mutate_receipt(paths, lambda receipt: receipt.__setitem__(field, value))

    with pytest.raises(poster.PostingSafetyError, match=message):
        _verify(paths)


def test_missing_receipt_and_missing_artifact_are_rejected(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    with pytest.raises(poster.PostingSafetyError, match="gate receipt file"):
        _verify(paths, receipt_path=tmp_path / "missing.json")

    _mutate_receipt(paths, lambda receipt: receipt["artifacts"].pop("compact"))
    with pytest.raises(poster.PostingSafetyError, match="missing artifacts: compact"):
        _verify(paths)


def test_stale_hash_and_explicit_path_mismatch_are_rejected(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    paths["plan"].write_text(VALID_PLAN + "\n", encoding="utf-8")
    with pytest.raises(poster.PostingSafetyError, match="stale gate receipt: plan hash mismatch"):
        _verify(paths)

    paths = _bundle(tmp_path / "second")
    other = tmp_path / "other-plan.md"
    other.write_text(VALID_PLAN, encoding="utf-8")
    with pytest.raises(poster.PostingSafetyError, match="not the exact artifact"):
        _verify(paths, plan_path=other)


def test_manifest_key_mismatch_is_rejected_even_when_rehashed(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    paths["manifest"].write_text(json.dumps({"issue": "GUIDES-99999"}), encoding="utf-8")
    _mutate_receipt(
        paths,
        lambda receipt: receipt["artifacts"]["manifest"].__setitem__(
            "sha256", _sha(paths["manifest"])
        ),
    )
    with pytest.raises(poster.PostingSafetyError, match="manifest issue does not match"):
        _verify(paths)


def test_malformed_compact_style_ac_is_rejected_by_fresh_strict_extractor(
    tmp_path: Path,
) -> None:
    paths = _bundle(tmp_path)
    malformed = VALID_PLAN.replace(
        "- AC-01 [Proposed]: (Basic) Given an author has an editable topic | "
        "When the author saves the topic | Then the saved value is visible after the topic "
        "is reopened | Evidence: Jira GUIDES-12345 description.",
        "- AC-01: The saved value is visible after reopen.",
    )
    paths["plan"].write_text(malformed, encoding="utf-8")
    _mutate_receipt(
        paths,
        lambda receipt: receipt["artifacts"]["plan"].__setitem__(
            "sha256", _sha(paths["plan"])
        ),
    )
    with pytest.raises(poster.PostingSafetyError, match="canonical AC extractor rejected"):
        _verify(paths)


def test_forged_extraction_and_compact_projection_are_rejected(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    paths["extracted"].write_text("[]\n", encoding="utf-8")
    _mutate_receipt(
        paths,
        lambda receipt: receipt["artifacts"]["extracted_acs"].__setitem__(
            "sha256", _sha(paths["extracted"])
        ),
    )
    with pytest.raises(poster.PostingSafetyError, match="fresh canonical strict extraction"):
        _verify(paths)

    paths = _bundle(tmp_path / "compact-forgery")
    paths["compact"].write_text("forged but rehashed\n", encoding="utf-8")
    _mutate_receipt(
        paths,
        lambda receipt: receipt["artifacts"]["compact"].__setitem__(
            "sha256", _sha(paths["compact"])
        ),
    )
    with pytest.raises(poster.PostingSafetyError, match="fresh canonical rendering"):
        _verify(paths)


def test_expected_current_hash_contract_is_validated_locally(tmp_path: Path) -> None:
    paths = _bundle(tmp_path)
    _mutate_receipt(
        paths,
        lambda receipt: receipt.__setitem__(
            "jira_acceptance_criteria_sha256",
            poster.jira_acceptance_criteria_sha256("old value"),
        ),
    )
    with pytest.raises(poster.PostingSafetyError, match="does not match the hash bound"):
        _verify(
            paths,
            expected_current_ac_sha256=poster.jira_acceptance_criteria_sha256("different"),
        )
    with pytest.raises(poster.PostingSafetyError, match="lowercase SHA-256"):
        _verify(paths, expected_current_ac_sha256="NOT-A-HASH")


def test_default_is_read_only_and_apply_preserves_statuses(tmp_path: Path, transport_only) -> None:
    payload = _verify(_bundle(tmp_path))
    dry_client = FakeJira()
    dry_result = poster.execute_verified_post(payload, client_factory=lambda: dry_client)
    assert dry_result.applied is False
    assert dry_client.writes == []

    apply_client = FakeJira()
    result = poster.execute_verified_post(
        payload,
        apply=True,
        client_factory=lambda: apply_client,
    )
    assert result.applied is True
    assert len(apply_client.writes) == 1
    _, posted, label, comment = apply_client.writes[0]
    assert "[Proposed]" not in posted and "[Confirmed]" not in posted
    assert label == "Needs_Human_Review"
    assert "passed AEM Guides test-plan gate receipt" in comment


@pytest.mark.parametrize(
    "client",
    [
        FakeJira(read_error=RuntimeError("network denied")),
        FakeJira(omit_ac_field=True),
    ],
)
def test_unreadable_current_jira_field_fails_without_mutation(
    tmp_path: Path, client: FakeJira, transport_only
) -> None:
    payload = _verify(_bundle(tmp_path))
    with pytest.raises(poster.PostingSafetyError, match="nothing was written"):
        poster.execute_verified_post(payload, apply=True, client_factory=lambda: client)
    assert client.writes == []


def test_expected_current_and_race_guards_prevent_mutation(tmp_path: Path, transport_only) -> None:
    paths = _bundle(tmp_path)
    payload = _verify(
        paths,
        expected_current_ac_sha256=poster.jira_acceptance_criteria_sha256("expected"),
    )
    changed_client = FakeJira(current="changed")
    with pytest.raises(poster.PostingSafetyError, match="expected-current hash"):
        poster.execute_verified_post(payload, apply=True, client_factory=lambda: changed_client)
    assert changed_client.writes == []

    payload = _verify(paths)
    racing_client = FakeJira(current_reads=["", "changed during command"])
    with pytest.raises(poster.PostingSafetyError, match="changed during this command"):
        poster.execute_verified_post(
            payload,
            apply=True,
            no_qe_tag=True,
            client_factory=lambda: racing_client,
        )
    assert racing_client.writes == []


def test_unchanged_content_never_writes_even_with_apply(tmp_path: Path, transport_only) -> None:
    payload = _verify(_bundle(tmp_path))
    client = FakeJira(current=payload.acceptance_criteria_text + "\n")
    result = poster.execute_verified_post(
        payload,
        apply=True,
        client_factory=lambda: client,
    )
    assert result.mode == "unchanged"
    assert result.applied is False
    assert client.writes == []


def test_invalid_receipt_stops_before_post_executor(tmp_path: Path, monkeypatch) -> None:
    paths = _bundle(tmp_path)
    _mutate_receipt(paths, lambda receipt: receipt.__setitem__("passed", False))
    called = False

    def forbidden_executor(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("post executor must not be called")

    monkeypatch.setattr(poster, "execute_verified_post", forbidden_executor)
    result = poster.main(
        [
            "--key",
            "GUIDES-12345",
            "--plan",
            str(paths["plan"]),
            "--combined",
            str(paths["combined"]),
            "--manifest",
            str(paths["manifest"]),
            "--gate-receipt",
            str(paths["receipt"]),
            "--apply",
        ]
    )
    assert result == 1
    assert called is False


V2_STATEMENT = "After saving a topic, reopening it shows the saved text."
V2_PLAN = VALID_PLAN[:VALID_PLAN.index("- AC-01")] + (
    f"- AC-01 [Confirmed]: (Basic) {V2_STATEMENT} Evidence: accepted UAC.\n"
) + VALID_PLAN[VALID_PLAN.index("\n**Test Scenarios**"):]


def test_v2_format_and_subpoints_are_preserved(tmp_path):
    plan = V2_PLAN.replace("Evidence: accepted UAC.\n", "Evidence: accepted UAC.\n  - Check a topic with inline text.\n")
    payload = _verify(_bundle(tmp_path, plan_text=plan))
    assert payload.criteria[0]["schema_version"] == "aem-guides-ac-v2"
    assert payload.acceptance_criteria_text == (
        f"AC-01: {V2_STATEMENT}\n  - Check a topic with inline text."
    )


def test_apply_without_canonical_result_stops_before_client(tmp_path):
    payload = _verify(_bundle(tmp_path))
    def forbidden():
        pytest.fail("no Jira read is allowed without canonical verification")
    with pytest.raises(poster.PostingSafetyError, match="requires --canonical-result"):
        poster.execute_verified_post(payload, apply=True, client_factory=forbidden)


@pytest.mark.parametrize("field_only", [False, True])
def test_no_comment_modes_skip_qe_lookup_and_verify_readback(tmp_path, transport_only, field_only):
    payload = _verify(_bundle(tmp_path, plan_text=V2_PLAN))
    client = FakeJira()
    result = poster.execute_verified_post(
        payload, apply=True, no_comment=True, field_only=field_only,
        client_factory=lambda: client,
    )
    assert result.applied
    assert client.writes == [(payload.issue, payload.acceptance_criteria_text,
                              None if field_only else "Needs_Human_Review", None)]
    assert client.reads == [poster.AC_FIELD] * 3


@pytest.mark.parametrize("readback", ["server stored a different value", RuntimeError("read-back unavailable")])
def test_failed_readback_never_reports_success(tmp_path, transport_only, readback):
    payload = _verify(_bundle(tmp_path, plan_text=V2_PLAN))
    class FailedReadback(FakeJira):
        def get_issue(self, key, fields):
            if self.writes:
                if isinstance(readback, Exception):
                    raise readback
                return {"key": key, "fields": {poster.AC_FIELD: readback}}
            return super().get_issue(key, fields)
    client = FailedReadback()
    with pytest.raises(poster.PostingSafetyError, match="write requested but read-back"):
        poster.execute_verified_post(payload, apply=True, field_only=True, client_factory=lambda: client)
    assert len(client.writes) == 1


def _canonical_fixture(paths):
    """Synthetic unit fixture, NOT a real-ticket runtime or gate-pass claim."""
    from app.core.schemas_canonical_test_plan_runtime import (
        AcceptanceCandidate, AcceptancePromotionDecision, CANONICAL_STAGE_ORDER,
        CandidateLifecycleRecord, RendererProjectionDecision, ContractMode,
        GenerationResult, GateDecision, RuntimeTrace, RuntimeStageTrace,
        StructuredQEPlan, PlanSection,
    )
    from app.services.canonical_evidence_service import normalize_codex_manifest
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    bundle = normalize_codex_manifest(manifest, tenant_id="fixture-tenant", jira_key="GUIDES-12345")
    candidate = AcceptanceCandidate(
        statement=V2_STATEMENT, contract_mode=ContractMode.HUMAN_ACCEPTED_CONTRACT,
        accepted_human_contract=True, in_scope=True, observable=True,
    )
    promotion = AcceptancePromotionDecision(
        candidate_id=candidate.candidate_id, status="PROMOTED",
        resulting_disposition="ACCEPTANCE_CONTRACT", authority_supported=True,
        scope_established=True, observable=True, exact_values_supported=True,
    )
    gates = [GateDecision(gate=s, status="PASSED") for s in CANONICAL_STAGE_ORDER if s.value.endswith("Gate")]
    lifecycle = CandidateLifecycleRecord(
        discovered_candidate_id=candidate.candidate_id, canonical_candidate_id=candidate.candidate_id,
        stages=["CANDIDATE_DISCOVERED", "APPLICABILITY_EVALUATED", "FINAL_DISPOSITION"],
        evidence_required=False, evidence_collected=False, final_disposition="AC", promotion_status="PROMOTED",
    )
    renderer = RendererProjectionDecision(
        discovered_candidate_id=candidate.candidate_id, canonical_candidate_id=candidate.candidate_id,
        final_disposition="AC", section_key="acceptance_contract", source_record_ids=[candidate.candidate_id],
    )
    plan = StructuredQEPlan(
        jira_key="GUIDES-12345", contract_mode=ContractMode.HUMAN_ACCEPTED_CONTRACT,
        sections=[PlanSection(section_key="acceptance_contract", title="Acceptance contract", items=[V2_STATEMENT])],
        promoted_candidate_ids=[candidate.candidate_id], gate_decisions=gates,
        candidate_lifecycle=[lifecycle], renderer_decisions=[renderer],
    )
    output = {
        "jira_key": plan.jira_key, "plan_markdown": f"# Acceptance contract\n- {V2_STATEMENT}\n",
        "structured_plan": plan.model_dump(mode="json"), "gate_decisions": [g.model_dump(mode="json") for g in gates],
        "acceptance_candidates": [candidate.model_dump(mode="json")], "promotion_decisions": [promotion.model_dump(mode="json")],
    }
    timestamp = "2026-09-09T00:00:00Z"
    trace = RuntimeTrace(
        run_id="fixture-run", request_id="fixture-request", entry_point="codex_skill",
        generation_profile="codex_canonical_v1", evidence_bundle_id=bundle.bundle_id,
        started_at=timestamp, completed_at=timestamp,
        stage_trace=[RuntimeStageTrace(
            stage=s, sequence=i, started_at=timestamp, completed_at=timestamp,
            duration_ms=0, input_sha256="a" * 64, output_sha256="b" * 64, status="completed",
        ) for i, s in enumerate(CANONICAL_STAGE_ORDER, 1)],
    )
    result = GenerationResult(
        run_id=trace.run_id, request_id=trace.request_id, evidence_bundle_id=bundle.bundle_id,
        evidence_bundle=bundle, status="completed", output_contract="strict-qe", output_kind="test_plan",
        output_payload=output, structured_output=output, rendered_output=output["plan_markdown"],
        structured_plan=plan, gate_decisions=gates, validation_status="passed", trace=trace,
    )
    path = paths["receipt"].parent / "canonical-result.json"
    path.write_text(result.model_dump_json(), encoding="utf-8")
    _mutate_receipt(paths, lambda receipt: receipt.__setitem__(
        "validator", poster._skill_module("skill_bundle_fingerprint.py").fingerprint(poster._CANONICAL_SKILL_SCRIPTS.parent)
    ))
    return path


def test_bound_canonical_result_can_post_field_only(tmp_path):
    paths = _bundle(tmp_path, plan_text=V2_PLAN)
    result_path = _canonical_fixture(paths)
    payload = _verify(paths, canonical_result_path=result_path)
    client = FakeJira(current="previous criteria")
    result = poster.execute_verified_post(payload, apply=True, field_only=True, client_factory=lambda: client)
    assert result.applied
    assert client.writes == [(payload.issue, f"AC-01: {V2_STATEMENT}", None, None)]


@pytest.mark.parametrize("field,value", [
    ("status", "needs_human_review"), ("status", "blocked"), ("status", "failed"),
    ("validation_status", "failed"), ("output_sha256", "f" * 64),
    ("schema_version", "made-up"), ("runtime_version", "1.0.0"),
])
def test_invalid_canonical_envelope_blocks(tmp_path, field, value):
    paths = _bundle(tmp_path, plan_text=V2_PLAN)
    path = _canonical_fixture(paths)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw[field] = value
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(poster.PostingSafetyError):
        _verify(paths, canonical_result_path=path)


def test_wrong_manifest_and_missing_stage_are_rejected(tmp_path):
    paths = _bundle(tmp_path, plan_text=V2_PLAN)
    path = _canonical_fixture(paths)
    manifest = {"issue": "GUIDES-12345", "description": "changed after generation"}
    paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    _mutate_receipt(paths, lambda r: r["artifacts"]["manifest"].__setitem__("sha256", _sha(paths["manifest"])))
    with pytest.raises(poster.PostingSafetyError, match="exact manifest"):
        _verify(paths, canonical_result_path=path)
    path = _canonical_fixture(paths)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["trace"]["stage_trace"].pop()
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(poster.PostingSafetyError, match="trace is incomplete"):
        _verify(paths, canonical_result_path=path)


def test_unpromoted_subpoint_is_not_silently_posted(tmp_path):
    paths = _bundle(tmp_path, plan_text=V2_PLAN.replace("Evidence: accepted UAC.\n", "Evidence: accepted UAC.\n  - An extra check.\n"))
    path = _canonical_fixture(paths)
    with pytest.raises(poster.PostingSafetyError, match="wording/sub-points differ"):
        _verify(paths, canonical_result_path=path)


def test_apply_rechecks_artifacts_before_constructing_client(tmp_path):
    paths = _bundle(tmp_path, plan_text=V2_PLAN)
    path = _canonical_fixture(paths)
    payload = _verify(paths, canonical_result_path=path)
    paths["plan"].write_text(V2_PLAN + "\nchanged", encoding="utf-8")
    def forbidden():
        pytest.fail("Jira client must not be constructed")
    with pytest.raises(poster.PostingSafetyError, match="stale gate receipt"):
        poster.execute_verified_post(payload, apply=True, client_factory=forbidden)


@pytest.mark.parametrize("change", [
    "wrong_issue", "rejected_promotion", "missing_renderer", "missing_gate",
    "wrong_section", "unsupported_authority",
])
def test_rehashed_inner_runtime_changes_do_not_bypass_binding(tmp_path, change):
    from app.core.schemas_canonical_test_plan_runtime import stable_sha256
    paths = _bundle(tmp_path, plan_text=V2_PLAN)
    path = _canonical_fixture(paths)
    raw = json.loads(path.read_text(encoding="utf-8"))
    output = raw["output_payload"]
    if change == "wrong_issue":
        output["jira_key"] = "GUIDES-99999"
    elif change == "rejected_promotion":
        output["promotion_decisions"][0]["status"] = "REJECTED"
    elif change == "missing_renderer":
        output["structured_plan"]["renderer_decisions"] = []
    elif change == "missing_gate":
        raw["gate_decisions"].pop()
        output["gate_decisions"] = raw["gate_decisions"]
        output["structured_plan"]["gate_decisions"] = raw["gate_decisions"]
    elif change == "wrong_section":
        output["structured_plan"]["sections"][0]["items"] = ["Unrelated text."]
    elif change == "unsupported_authority":
        output["promotion_decisions"][0]["authority_supported"] = False
    raw["structured_plan"] = output["structured_plan"]
    raw["structured_output"] = output
    raw["output_sha256"] = stable_sha256(output)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(poster.PostingSafetyError):
        _verify(paths, canonical_result_path=path)


def test_changed_skill_fingerprint_stops_posting(tmp_path):
    paths = _bundle(tmp_path, plan_text=V2_PLAN)
    path = _canonical_fixture(paths)
    _mutate_receipt(paths, lambda r: r["validator"].__setitem__("sha256", "0" * 64))
    with pytest.raises(ValueError, match="validator fingerprint hash mismatch"):
        _verify(paths, canonical_result_path=path)
