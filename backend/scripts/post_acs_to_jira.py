"""Safely publish gate-approved Acceptance Criteria to Jira.

This is deliberately a two-key operation:

1. ``run_gates.py`` must have emitted a successful, hash-bound receipt for the
   exact plan, combined deliverable, evidence manifest, compact rendering, and
   strict AC extraction artifacts.
2. A human must pass ``--apply``. Without it this command is a read-only dry
   run, including a fail-closed read of Jira's current AC field.

The compact rendering is never used as the posting source. Jira text is
projected from canonical ``aem-guides-ac-v1`` records as simple Starting point,
Action, and Expected result lines. ID and review status remain visible. Sphere,
the canonical Given/When/Then labels, and the local Evidence locator remain in
the hash-bound artifacts and are deliberately omitted from Jira.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv


_BACKEND = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND.parent
_CANONICAL_SKILL_SCRIPTS = _REPO_ROOT / "skills" / "test-plan-generation" / "scripts"
_CANONICAL_EXTRACTOR = _CANONICAL_SKILL_SCRIPTS / "extract_acs.py"
_CANONICAL_RENDERER = _CANONICAL_SKILL_SCRIPTS / "render_compact_view.py"

sys.path.insert(0, str(_BACKEND))
load_dotenv(_BACKEND / ".env")

GATE_RECEIPT_SCHEMA = "aem-guides-gate-receipt-v1"
AC_SCHEMA = "aem-guides-ac-v1"
AC_FIELD = "customfield_13400"
QE_ASSIGNEE_FIELD = "customfield_18512"
REQUIRED_ARTIFACTS = ("plan", "manifest", "combined", "compact", "extracted_acs")
JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")


class PostingSafetyError(RuntimeError):
    """Raised when the posting safety contract cannot be proven."""


def _load_ac_projector() -> Callable[..., str]:
    """Load the projector from the exact canonical skill path, without import drift."""

    path = _CANONICAL_SKILL_SCRIPTS / "ac_presentation.py"
    spec = importlib.util.spec_from_file_location("canonical_ac_presentation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"canonical AC presentation module is unavailable: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    projector = getattr(module, "project_ac_for_people", None)
    if not callable(projector):
        raise RuntimeError("canonical AC presentation projector is missing")
    return projector


_PROJECT_AC_FOR_PEOPLE = _load_ac_projector()


@dataclass(frozen=True)
class VerifiedPostPayload:
    """Immutable local payload produced before any Jira client is constructed."""

    issue: str
    receipt_path: Path
    plan_path: Path
    manifest_path: Path
    combined_path: Path
    compact_path: Path
    extracted_acs_path: Path
    criteria: tuple[dict[str, str], ...]
    acceptance_criteria_text: str
    expected_current_ac_sha256: str | None


@dataclass(frozen=True)
class PostResult:
    issue: str
    mode: str
    applied: bool
    criteria_count: int
    current_ac_sha256: str


def _normalize_jira_key(value: str) -> str:
    key = (value or "").strip().upper()
    if not JIRA_KEY_RE.fullmatch(key):
        raise PostingSafetyError("expected an exact Jira key such as GUIDES-36430")
    return key


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def jira_acceptance_criteria_sha256(value: str) -> str:
    """Hash the exact Jira field value, without whitespace normalization."""

    return _sha256_bytes(value.encode("utf-8"))


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PostingSafetyError(f"{label} is not readable UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PostingSafetyError(f"{label} must contain one JSON object: {path}")
    return value


def _resolve_file(value: Any, *, base_dir: Path, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PostingSafetyError(f"{label}.path must be a non-empty string")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise PostingSafetyError(f"{label} file is missing or unreadable: {candidate}") from exc
    if not resolved.is_file():
        raise PostingSafetyError(f"{label} path is not a file: {resolved}")
    return resolved


def _resolve_cli_file(value: str | Path, *, label: str) -> Path:
    try:
        resolved = Path(value).resolve(strict=True)
    except OSError as exc:
        raise PostingSafetyError(f"{label} file is missing or unreadable: {value}") from exc
    if not resolved.is_file():
        raise PostingSafetyError(f"{label} path is not a file: {resolved}")
    return resolved


def _receipt_timestamp_is_valid(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _manifest_issue(data: dict[str, Any]) -> str:
    value = data.get("issue")
    if isinstance(value, dict):
        value = value.get("key") or value.get("issue_key") or value.get("id")
    if not isinstance(value, str):
        raise PostingSafetyError("manifest issue must be a Jira key string or an object with key")
    return _normalize_jira_key(value)


def _run_canonical(script: Path, plan_path: Path, label: str) -> str:
    if not script.is_file():
        raise PostingSafetyError(f"canonical {label} script is missing: {script}")
    completed = subprocess.run(
        [sys.executable, str(script), str(plan_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout or "no diagnostic").strip()
        raise PostingSafetyError(f"canonical {label} rejected the plan: {diagnostic}")
    return completed.stdout


def _fresh_strict_criteria(plan_path: Path) -> list[dict[str, str]]:
    stdout = _run_canonical(_CANONICAL_EXTRACTOR, plan_path, "AC extractor")
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise PostingSafetyError("canonical AC extractor returned invalid JSON") from exc
    if not isinstance(value, list) or not value:
        raise PostingSafetyError("canonical AC extractor returned no AC records")
    required = {
        "id",
        "status",
        "sphere",
        "given",
        "when",
        "then",
        "evidence",
        "raw",
        "schema_version",
    }
    for index, row in enumerate(value, start=1):
        if not isinstance(row, dict) or set(row) != required:
            raise PostingSafetyError(
                f"canonical AC record {index} does not have the exact structured field set"
            )
        if row.get("schema_version") != AC_SCHEMA:
            raise PostingSafetyError(
                f"canonical AC record {index} schema_version must be {AC_SCHEMA}"
            )
        if row.get("status") not in {"Proposed", "Confirmed"}:
            raise PostingSafetyError(f"canonical AC record {index} has an invalid status")
        raw = row.get("raw")
        if not isinstance(raw, str) or not raw.startswith(f"{row['id']} [{row['status']}]:"):
            raise PostingSafetyError(f"canonical AC record {index} raw projection is inconsistent")
    return value


def _read_extracted_artifact(path: Path) -> list[dict[str, str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PostingSafetyError(f"extracted_acs artifact is invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, list):
        raise PostingSafetyError("extracted_acs artifact must contain a JSON list")
    return value


def _jira_ac_projection(row: dict[str, str]) -> str:
    """Project the behavioral contract without leaking local evidence paths to Jira.

    Non-negotiable: the [Proposed]/[Confirmed] status tag is NEVER written to the Jira
    Acceptance Criteria field (it is internal-record only). The Needs_Human_Review label
    conveys the not-yet-accepted status instead, so the AC text the human reads stays
    clean. include_status must remain False.
    """
    return _PROJECT_AC_FOR_PEOPLE(
        row,
        include_status=False,
        header_bullet=False,
    )


def _receipt_expected_current_hash(
    receipt: dict[str, Any], cli_value: str | None
) -> str | None:
    receipt_has_value = "jira_acceptance_criteria_sha256" in receipt
    receipt_value = receipt.get("jira_acceptance_criteria_sha256")
    if receipt_has_value and (
        not isinstance(receipt_value, str) or not SHA256_RE.fullmatch(receipt_value)
    ):
        raise PostingSafetyError(
            "receipt jira_acceptance_criteria_sha256 must be a lowercase SHA-256 hex string"
        )
    if cli_value is not None and not SHA256_RE.fullmatch(cli_value):
        raise PostingSafetyError(
            "--expected-current-ac-sha256 must be a lowercase SHA-256 hex string"
        )
    if cli_value is not None and receipt_has_value and cli_value != receipt_value:
        raise PostingSafetyError(
            "CLI expected-current AC hash does not match the hash bound into the gate receipt"
        )
    return cli_value if cli_value is not None else receipt_value


def verify_gate_receipt(
    *,
    key: str,
    plan_path: str | Path,
    manifest_path: str | Path,
    combined_path: str | Path,
    receipt_path: str | Path,
    expected_current_ac_sha256: str | None = None,
) -> VerifiedPostPayload:
    """Verify all local posting evidence before any Jira client can exist.

    Required ``aem-guides-gate-receipt-v1`` shape::

        {
          "schema_version": "aem-guides-gate-receipt-v1",
          "passed": true,
          "postable": true,
          "issue": "GUIDES-12345",
          "generated_at": "2026-08-24T12:00:00Z",
          "artifacts": {
            "plan": {"path": "plan.md", "sha256": "<64 lowercase hex>"},
            "manifest": {"path": "manifest.json", "sha256": "..."},
            "combined": {"path": "combined.md", "sha256": "..."},
            "compact": {"path": "compact.md", "sha256": "..."},
            "extracted_acs": {"path": "acs.json", "sha256": "..."}
          }
        }

    Paths may be absolute or relative to the receipt. The optional top-level
    ``jira_acceptance_criteria_sha256`` is an optimistic concurrency guard for
    the exact Jira field value observed before the gate run.
    """

    issue = _normalize_jira_key(key)
    receipt_file = _resolve_cli_file(receipt_path, label="gate receipt")
    receipt = _read_json_object(receipt_file, "gate receipt")

    if receipt.get("schema_version") != GATE_RECEIPT_SCHEMA:
        raise PostingSafetyError(f"gate receipt schema_version must be {GATE_RECEIPT_SCHEMA}")
    if receipt.get("passed") is not True:
        raise PostingSafetyError("gate receipt is not passed=true")
    if receipt.get("postable") is not True:
        raise PostingSafetyError("gate receipt is not postable=true")
    if _normalize_jira_key(str(receipt.get("issue") or "")) != issue:
        raise PostingSafetyError("gate receipt issue does not match --key")
    if not _receipt_timestamp_is_valid(receipt.get("generated_at")):
        raise PostingSafetyError(
            "gate receipt generated_at must be a timezone-aware ISO-8601 timestamp"
        )

    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict):
        raise PostingSafetyError("gate receipt artifacts must be an object")
    missing = [name for name in REQUIRED_ARTIFACTS if name not in artifacts]
    if missing:
        raise PostingSafetyError("gate receipt is missing artifacts: " + ", ".join(missing))

    verified_paths: dict[str, Path] = {}
    for name in REQUIRED_ARTIFACTS:
        entry = artifacts.get(name)
        if not isinstance(entry, dict):
            raise PostingSafetyError(f"gate receipt artifact {name} must be an object")
        expected_hash = entry.get("sha256")
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            raise PostingSafetyError(
                f"gate receipt artifact {name}.sha256 must be 64 lowercase hex characters"
            )
        path = _resolve_file(entry.get("path"), base_dir=receipt_file.parent, label=name)
        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
            raise PostingSafetyError(
                f"stale gate receipt: {name} hash mismatch "
                f"(expected {expected_hash}, got {actual_hash})"
            )
        verified_paths[name] = path

    explicit_paths = {
        "plan": _resolve_cli_file(plan_path, label="plan"),
        "manifest": _resolve_cli_file(manifest_path, label="manifest"),
        "combined": _resolve_cli_file(combined_path, label="combined"),
    }
    for name, explicit_path in explicit_paths.items():
        if explicit_path != verified_paths[name]:
            raise PostingSafetyError(
                f"--{name} path is not the exact artifact bound into the gate receipt"
            )

    manifest = _read_json_object(verified_paths["manifest"], "manifest")
    if _manifest_issue(manifest) != issue:
        raise PostingSafetyError("manifest issue does not match --key")

    fresh_criteria = _fresh_strict_criteria(verified_paths["plan"])
    extracted_criteria = _read_extracted_artifact(verified_paths["extracted_acs"])
    if extracted_criteria != fresh_criteria:
        raise PostingSafetyError(
            "extracted_acs artifact does not equal a fresh canonical strict extraction"
        )

    fresh_compact = _run_canonical(
        _CANONICAL_RENDERER, verified_paths["plan"], "compact renderer"
    )
    try:
        saved_compact = verified_paths["compact"].read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PostingSafetyError(f"compact artifact is not readable UTF-8: {exc}") from exc
    if saved_compact != fresh_compact:
        raise PostingSafetyError(
            "compact artifact does not equal a fresh canonical rendering of the plan"
        )

    acceptance_text = "\n\n".join(_jira_ac_projection(row) for row in fresh_criteria)
    guard = _receipt_expected_current_hash(receipt, expected_current_ac_sha256)
    return VerifiedPostPayload(
        issue=issue,
        receipt_path=receipt_file,
        plan_path=verified_paths["plan"],
        manifest_path=verified_paths["manifest"],
        combined_path=verified_paths["combined"],
        compact_path=verified_paths["compact"],
        extracted_acs_path=verified_paths["extracted_acs"],
        criteria=tuple(fresh_criteria),
        acceptance_criteria_text=acceptance_text,
        expected_current_ac_sha256=guard,
    )


def _read_current_acceptance_criteria(client: Any, key: str) -> str:
    try:
        issue = client.get_issue(key, fields=AC_FIELD)
    except Exception as exc:  # noqa: BLE001 - every read failure is a hard stop
        raise PostingSafetyError(
            f"could not read Jira's current Acceptance Criteria field; nothing was written: {exc}"
        ) from exc
    if not isinstance(issue, dict):
        raise PostingSafetyError(
            "Jira current-field read returned a non-object response; nothing was written"
        )
    returned_key = issue.get("key")
    if returned_key is not None and _normalize_jira_key(str(returned_key)) != key:
        raise PostingSafetyError(
            "Jira current-field read returned a different issue; nothing was written"
        )
    fields = issue.get("fields")
    if not isinstance(fields, dict) or AC_FIELD not in fields:
        raise PostingSafetyError(
            "Jira current-field read omitted the Acceptance Criteria field; nothing was written"
        )
    value = fields.get(AC_FIELD)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise PostingSafetyError(
            "Jira Acceptance Criteria field is not plain text; nothing was written"
        )
    return value


def _qe_assignee_username(client: Any, key: str) -> str | None:
    """Return the QE Assignee username; tagging remains best-effort metadata."""

    try:
        issue = client.get_issue(key, fields=QE_ASSIGNEE_FIELD)
        qe = (issue.get("fields") or {}).get(QE_ASSIGNEE_FIELD)
        if isinstance(qe, dict):
            value = qe.get("name")
            return value if isinstance(value, str) and value.strip() else None
    except Exception:  # noqa: BLE001 - optional tagging must not weaken AC safety
        return None
    return None


def execute_verified_post(
    payload: VerifiedPostPayload,
    *,
    apply: bool = False,
    label: str = "Needs_Human_Review",
    no_qe_tag: bool = False,
    client_factory: Callable[[], Any] | None = None,
) -> PostResult:
    """Read Jira state and optionally apply an already locally verified payload."""

    if not LABEL_RE.fullmatch(label or ""):
        raise PostingSafetyError("review label contains unsupported characters")
    if client_factory is None:
        # Imported only after verify_gate_receipt has returned to the caller.
        from app.services.jira_client import JiraClient

        client_factory = JiraClient

    client = client_factory()
    current = _read_current_acceptance_criteria(client, payload.issue)
    current_hash = jira_acceptance_criteria_sha256(current)
    if (
        payload.expected_current_ac_sha256 is not None
        and current_hash != payload.expected_current_ac_sha256
    ):
        raise PostingSafetyError(
            "Jira Acceptance Criteria changed since the expected-current hash was recorded; "
            "nothing was written"
        )

    current_normalized = current.strip()
    intended = payload.acceptance_criteria_text
    unchanged = current_normalized == intended
    mode = "unchanged" if unchanged else ("update" if current_normalized else "first post")

    print(
        f"Issue: {payload.issue} ({mode})\n"
        f"AC field content ({len(payload.criteria)} criteria, receipt verified):\n"
        + "-" * 60
    )
    print(intended)
    print("-" * 60 + f"\nLabel: {label}")

    if not apply:
        print("\nDry-run (default): Jira was read, but nothing was written. Pass --apply to write.")
        return PostResult(
            issue=payload.issue,
            mode=mode,
            applied=False,
            criteria_count=len(payload.criteria),
            current_ac_sha256=current_hash,
        )
    if unchanged:
        print("\nNo write: Jira already contains the exact acceptance criteria.")
        return PostResult(
            issue=payload.issue,
            mode=mode,
            applied=False,
            criteria_count=len(payload.criteria),
            current_ac_sha256=current_hash,
        )

    qe = None
    if not no_qe_tag and mode == "first post":
        qe = _qe_assignee_username(client, payload.issue)
    if mode == "update":
        comment = (
            "Acceptance Criteria field updated from a passed AEM Guides test-plan gate receipt "
            f"(now {len(payload.criteria)} criteria, AI-generated). Flagged {label} - please "
            "re-review the updated Proposed/Confirmed criteria."
        )
    else:
        mention = f"[~{qe}] " if qe else ""
        reviewer_note = "please review (QE Assignee)" if qe else "a human must review"
        comment = (
            f"{mention}Acceptance Criteria posted from a passed AEM Guides test-plan gate receipt "
            f"(AI-generated). Flagged {label} - {reviewer_note} and confirm before sign-off."
        )

    # Jira has no conditional-update primitive here. Re-read immediately before
    # mutation and reject any state change since the first read.
    immediately_before_write = _read_current_acceptance_criteria(client, payload.issue)
    if jira_acceptance_criteria_sha256(immediately_before_write) != current_hash:
        raise PostingSafetyError(
            "Jira Acceptance Criteria changed during this command; nothing was written"
        )

    client.set_acceptance_criteria(
        payload.issue,
        intended,
        review_label=label,
        review_comment=comment,
    )
    print(
        f"\nOK: {mode} applied to {payload.issue} Acceptance Criteria field "
        f"({len(payload.criteria)} criteria); label {label}; comment added."
    )
    return PostResult(
        issue=payload.issue,
        mode=mode,
        applied=True,
        criteria_count=len(payload.criteria),
        current_ac_sha256=current_hash,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Post receipt-verified structured ACs to Jira (dry-run unless --apply)."
    )
    parser.add_argument("--key", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--combined", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--gate-receipt", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="explicitly authorize the Jira write")
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="explicit form of the default read-only behavior",
    )
    parser.add_argument("--label", default="Needs_Human_Review")
    parser.add_argument("--no-qe-tag", action="store_true")
    parser.add_argument(
        "--expected-current-ac-sha256",
        default=None,
        help="optional lowercase SHA-256 of the exact current Jira AC field",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        # Pure-local verification intentionally precedes JiraClient import or
        # construction. A failed/stale/mismatched receipt cannot initiate a read.
        payload = verify_gate_receipt(
            key=args.key,
            plan_path=args.plan,
            manifest_path=args.manifest,
            combined_path=args.combined,
            receipt_path=args.gate_receipt,
            expected_current_ac_sha256=args.expected_current_ac_sha256,
        )
        execute_verified_post(
            payload,
            apply=args.apply,
            label=args.label,
            no_qe_tag=args.no_qe_tag,
        )
    except Exception as exc:  # noqa: BLE001 - every uncertainty must stop the write
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
