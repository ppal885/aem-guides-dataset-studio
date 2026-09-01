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
        self, key: str, text: str, *, review_label: str, review_comment: str
    ) -> None:
        self.writes.append((key, text, review_label, review_comment))


def test_valid_receipt_uses_strict_records_and_preserves_status(tmp_path: Path) -> None:
    payload = _verify(_bundle(tmp_path))

    assert [row["schema_version"] for row in payload.criteria] == [
        "aem-guides-ac-v1",
        "aem-guides-ac-v1",
    ]
    assert [row["status"] for row in payload.criteria] == ["Proposed", "Confirmed"]
    # Non-negotiable: the [Proposed]/[Confirmed] status tag is NEVER written to Jira.
    assert payload.acceptance_criteria_text == (
        "AC-01\n"
        "- Starting point: an author has an editable topic.\n"
        "- Action: the author saves the topic.\n"
        "- Expected result: the saved value is visible after the topic is reopened.\n\n"
        "AC-02\n"
        "- Starting point: an author lacks edit permission.\n"
        "- Action: the author attempts to save the topic.\n"
        "- Expected result: the save is rejected and the stored topic remains unchanged."
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


def test_default_is_read_only_and_apply_preserves_statuses(tmp_path: Path) -> None:
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
    tmp_path: Path, client: FakeJira
) -> None:
    payload = _verify(_bundle(tmp_path))
    with pytest.raises(poster.PostingSafetyError, match="nothing was written"):
        poster.execute_verified_post(payload, apply=True, client_factory=lambda: client)
    assert client.writes == []


def test_expected_current_and_race_guards_prevent_mutation(tmp_path: Path) -> None:
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


def test_unchanged_content_never_writes_even_with_apply(tmp_path: Path) -> None:
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
