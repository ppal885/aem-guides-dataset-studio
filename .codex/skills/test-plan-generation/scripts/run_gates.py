"""Single mandatory gate for a test plan.

One command, one green/red result. It exists so a partial run cannot pass by
simply not invoking a check: the evidence manifest is REQUIRED, and the manifest
plus the combined plan+appendix are audited together.

It runs, in order:
  1. Manifest presence + completeness (issue, attachments, rag_probes,
     indexed_history_run must all be declared).
  2. Structural validation of the eleven-section bullet-only body
     (validate_test_plan.py).
  3. Evidence audit of the combined plan+appendix deliverable and the manifest
     (verify_evidence.py): source paths on disk, cited line numbers in range,
     attachments downloaded + attested, >=3 RAG probes when behaviour matters,
     and fenced code evidence present when anything is Covered / Partially covered.
  4. The script self-tests (protect the gates from silent regression).

Usage:
  python scripts/run_gates.py --plan <body.md> --combined <plan+appendix.md> --manifest <manifest.json>

Exit 0 only when everything passes; any failure prints FAIL lines and exits 1.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_mod = _load("validate_test_plan", "validate_test_plan.py")
verify_mod = _load("verify_evidence", "verify_evidence.py")

REQUIRED_MANIFEST_KEYS = ("issue", "attachments", "rag_probes", "indexed_history_run", "clones")


def check_manifest_completeness(path: str | None) -> list[str]:
    if not path:
        return ["evidence manifest is required but was not supplied (--manifest)"]
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"evidence manifest missing or invalid JSON: {exc}"]
    failures: list[str] = []
    for key in REQUIRED_MANIFEST_KEYS:
        if key not in data:
            failures.append(
                f"manifest is missing required key '{key}' - every plan must declare "
                f"attachments, rag_probes, and indexed_history_run even if empty/false with a reason"
            )
    if "indexed_history_run" in data and not data["indexed_history_run"]:
        failures.append(
            "indexed_history_run must be truthy (record that the jira_qa history was queried) or a reason string"
        )
    clones = data.get("clones")
    if isinstance(clones, list):
        for entry in clones:
            ident = entry.get("path", "?")
            synced_with_sha = bool(entry.get("synced")) and bool(entry.get("sha"))
            provisional = bool(entry.get("provisional")) and bool(entry.get("note"))
            if not (synced_with_sha or provisional):
                failures.append(
                    f"clone {ident}: must be either synced with a captured sha, or provisional:true with a note "
                    f"explaining the SHA was not captured - a clone cannot be cited as current evidence unproven"
                )
    elif clones is not None:
        failures.append("manifest 'clones' must be a list")
    return failures


def run(plan_path: str, combined_path: str, manifest_path: str | None, jira_keys_path: str | None,
        skip_self_tests: bool) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []

    failures += [f"[manifest] {f}" for f in check_manifest_completeness(manifest_path)]

    body = Path(plan_path).read_text(encoding="utf-8")
    failures += [f"[validate] {e}" for e in validate_mod.validate(body)]

    combined = Path(combined_path).read_text(encoding="utf-8")
    jira_keys = verify_mod._load_manifest(jira_keys_path)
    v_fail, v_notes = verify_mod.verify(combined, jira_keys)
    failures += [f"[verify] {f}" for f in v_fail]
    notes += v_notes
    if manifest_path and Path(manifest_path).is_file():
        a_fail, a_notes = verify_mod.verify_attachments(manifest_path)
        failures += [f"[verify] {f}" for f in a_fail]
        notes += a_notes

    if not skip_self_tests:
        try:
            self_tests = _load("test_skill_scripts", "test_skill_scripts.py")
            self_tests.test_validator()
            self_tests.test_verifier()
            self_tests.test_attachment_manifest()
            notes.append("self-tests green")
        except AssertionError as exc:
            failures.append(f"[self-tests] {exc}")
        except Exception as exc:  # noqa: BLE001 - surface any self-test breakage as a gate failure
            failures.append(f"[self-tests] error: {exc}")

    return failures, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Single mandatory gate for an AEM Guides test plan.")
    parser.add_argument("--plan", required=True, help="the eleven-section bullet-only plan body")
    parser.add_argument("--combined", required=True, help="plan body + Appendix A (the delivered file)")
    parser.add_argument("--manifest", required=True, help="evidence manifest JSON")
    parser.add_argument("--jira-keys", dest="jira_keys", default=None)
    parser.add_argument("--skip-self-tests", action="store_true")
    args = parser.parse_args()

    failures, notes = run(args.plan, args.combined, args.manifest, args.jira_keys, args.skip_self_tests)

    for note in notes:
        print(f"NOTE: {note}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        print(f"\nGATE FAILED ({len(failures)} issue(s)) - do not deliver this plan as validated.")
        return 1
    print("\nGATE PASSED - manifest complete, structure valid, evidence verified"
          + ("." if args.skip_self_tests else ", self-tests green."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
