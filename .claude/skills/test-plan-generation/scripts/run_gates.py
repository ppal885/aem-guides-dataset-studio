"""Single mandatory gate for a test plan.

One command, one green/red result. It exists so a partial run cannot pass by
simply not invoking a check: the evidence manifest is REQUIRED, and the manifest
plus the combined plan+appendix are audited together.

It runs, in order:
  1. Manifest presence + completeness, including the five-source availability
     preflight and separate tool evidence for ask_dita_expert product-documentation
     probes and search_jira_history queries.
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
from datetime import datetime
from pathlib import Path


CANONICAL_JIRA_COMPONENTS = {
    "Editor",
    "Authoring",
    "Publishing",
    "Platform",
    "Schematron",
    "Integration",
}


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_mod = _load("validate_test_plan", "validate_test_plan.py")
verify_mod = _load("verify_evidence", "verify_evidence.py")

REQUIRED_MANIFEST_KEYS = (
    "issue",
    "attachments",
    "evidence_preflight",
    "rag_tool",
    "rag_probes",
    "jira_history_tool",
    "jira_history_queries",
    "indexed_history_run",
    "clones",
)

PREFLIGHT_SOURCE_KEYS = (
    "product_rag",
    "jira_history",
    "live_jira",
    "git",
    "figma",
)
PREFLIGHT_STATUSES = {"available", "unavailable", "not_applicable"}
PREFLIGHT_MODES = {"full", "degraded"}
PREFLIGHT_READINESS_IMPACTS = {"none", "draft_only", "blocked"}
PREFLIGHT_SOURCE_LABELS = {
    "product_rag": ("product rag", "ask_dita_expert"),
    "jira_history": ("jira history", "search_jira_history", "indexed jira"),
    "live_jira": ("live jira",),
    "git": ("git", "github", "diff"),
    "figma": ("figma", "design"),
}
PREFLIGHT_RESTRICTION_TERMS = {
    "product_rag": ("behaviour", "behavior", "product documentation", "documented product"),
    "jira_history": ("similar", "historical", "history", "regression learning"),
    "live_jira": ("status", "resolution", "fix version", "comment", "attachment", "mutable"),
    "git": ("implementation", "changed file", "changed line", "root cause", "fix impact", "diff"),
    "figma": ("layout", "interaction", "visual", "prototype", "design behaviour", "design behavior"),
}
PREFLIGHT_CHECK_ACTIONS = (
    "call",
    "fetch",
    "query",
    "search",
    "inspect",
    "read",
    "download",
    "probe",
    "sync",
    "diff",
    "ask_dita_expert",
    "search_jira_history",
    "check_rag_status",
)
PREFLIGHT_FAILURE_MARKERS = (
    "failed",
    "failure",
    "error",
    "exception",
    "unavailable",
    "denied",
    "timeout",
    "timed out",
    "connection refused",
    "http 401",
    "http 403",
    "returned 401",
    "returned 403",
)
PREFLIGHT_CONFIGURATION_SUCCESS_MARKERS = (
    "succeed",
    "returned",
    "response received",
    "completed",
    "verified",
    "inspected",
    "fetched",
    "queried",
    "searched",
    "downloaded",
    "probe result",
    " ran",
)


def _is_timezone_aware_iso8601(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _validate_evidence_preflight(data: dict) -> list[str]:
    failures: list[str] = []
    preflight = data.get("evidence_preflight")
    if not isinstance(preflight, dict):
        return ["evidence_preflight must be an object"]

    mode = str(preflight.get("mode", "")).strip()
    if mode not in PREFLIGHT_MODES:
        failures.append("evidence_preflight.mode must be 'full' or 'degraded'")

    if not _is_timezone_aware_iso8601(preflight.get("checked_at")):
        failures.append("evidence_preflight.checked_at must be a timezone-aware ISO-8601 timestamp")

    sources = preflight.get("sources")
    unavailable_sources: list[str] = []
    if not isinstance(sources, dict):
        failures.append("evidence_preflight.sources must be an object containing all five source checks")
        sources = {}
    source_keys = set(sources)
    missing_sources = set(PREFLIGHT_SOURCE_KEYS) - source_keys
    unexpected_sources = source_keys - set(PREFLIGHT_SOURCE_KEYS)
    if missing_sources:
        failures.append(
            "evidence_preflight.sources is missing: " + ", ".join(sorted(missing_sources))
        )
    if unexpected_sources:
        failures.append(
            "evidence_preflight.sources has unsupported keys: " + ", ".join(sorted(unexpected_sources))
        )

    for source_key in PREFLIGHT_SOURCE_KEYS:
        source = sources.get(source_key)
        if not isinstance(source, dict):
            if source_key not in missing_sources:
                failures.append(f"evidence_preflight.sources.{source_key} must be an object")
            continue
        status = str(source.get("status", "")).strip()
        checked_via = str(source.get("checked_via", "")).strip()
        reason = str(source.get("reason", "")).strip()
        if status not in PREFLIGHT_STATUSES:
            failures.append(
                f"evidence_preflight.sources.{source_key}.status must be available, unavailable, or not_applicable"
            )
        if not checked_via:
            failures.append(f"evidence_preflight.sources.{source_key}.checked_via is required")
        elif status == "available":
            checked_lower = checked_via.lower()
            if any(marker in checked_lower for marker in PREFLIGHT_FAILURE_MARKERS):
                failures.append(
                    f"evidence_preflight.sources.{source_key} cannot be available when checked_via records a failed check"
                )
            elif "configur" in checked_lower and not any(
                marker in checked_lower for marker in PREFLIGHT_CONFIGURATION_SUCCESS_MARKERS
            ):
                failures.append(
                    f"evidence_preflight.sources.{source_key}.checked_via must describe a successful call or inspection, not configuration alone"
                )
            elif not any(action in checked_lower for action in PREFLIGHT_CHECK_ACTIONS):
                failures.append(
                    f"evidence_preflight.sources.{source_key}.checked_via must describe a successful call or inspection, not configuration alone"
                )
        if status in {"unavailable", "not_applicable"} and not reason:
            failures.append(
                f"evidence_preflight.sources.{source_key}.reason is required when status is {status}"
            )
        if status == "unavailable":
            unavailable_sources.append(source_key)

    expected_mode = "degraded" if unavailable_sources else "full"
    if mode in PREFLIGHT_MODES and mode != expected_mode:
        failures.append(
            f"evidence_preflight.mode must be '{expected_mode}' for the recorded source statuses"
        )

    restrictions = preflight.get("claim_restrictions")
    if not isinstance(restrictions, list) or any(
        not isinstance(item, str) or not item.strip() for item in restrictions
    ):
        failures.append("evidence_preflight.claim_restrictions must be a list of non-empty strings")
        restrictions = []
    if mode == "degraded" and not restrictions:
        failures.append("degraded evidence_preflight requires at least one claim restriction")
    restriction_text = " ".join(restrictions).lower()
    for source_key in unavailable_sources:
        if not any(term in restriction_text for term in PREFLIGHT_RESTRICTION_TERMS[source_key]):
            failures.append(
                f"evidence_preflight.claim_restrictions must cover unavailable source '{source_key}'"
            )

    readiness_impact = str(preflight.get("readiness_impact", "")).strip()
    if readiness_impact not in PREFLIGHT_READINESS_IMPACTS:
        failures.append("evidence_preflight.readiness_impact must be none, draft_only, or blocked")
    readiness_reason = str(preflight.get("readiness_impact_reason", "")).strip()
    if readiness_impact in {"draft_only", "blocked"} and not readiness_reason:
        failures.append(
            "evidence_preflight.readiness_impact_reason is required when readiness impact is not none"
        )
    return failures


def _validate_preflight_plan_alignment(data: dict, plan_text: str) -> list[str]:
    preflight = data.get("evidence_preflight")
    if not isinstance(preflight, dict):
        return []
    mode = str(preflight.get("mode", "")).strip()
    sources = preflight.get("sources") if isinstance(preflight.get("sources"), dict) else {}
    readiness_impact = str(preflight.get("readiness_impact", "")).strip()
    boundary = next(
        (
            line.strip()
            for line in plan_text.splitlines()
            if line.strip().lower().startswith("- evidence boundary:")
        ),
        "",
    )
    if not boundary:
        return ["plan must contain an Evidence boundary bullet aligned with evidence_preflight"]
    boundary_lower = boundary.lower()
    if mode in PREFLIGHT_MODES and f"evidence mode: {mode}" not in boundary_lower:
        return [f"Evidence boundary must state 'Evidence mode: {mode}'"]

    failures: list[str] = []
    unavailable_sources = [
        key
        for key in PREFLIGHT_SOURCE_KEYS
        if isinstance(sources.get(key), dict) and sources[key].get("status") == "unavailable"
    ]
    if mode == "degraded":
        for source_key in unavailable_sources:
            if not any(label in boundary_lower for label in PREFLIGHT_SOURCE_LABELS[source_key]):
                failures.append(
                    f"degraded Evidence boundary must name unavailable source '{source_key}'"
                )
        if not any(
            marker in boundary_lower
            for marker in ("unavailable", "unverified", "not verified", "cannot", "restricted")
        ):
            failures.append(
                "degraded Evidence boundary must state what is unavailable or remains unverified"
            )

    plan_lower = plan_text.lower()
    git_unavailable = "git" in unavailable_sources
    if "lifecycle understood as: implementation review" in plan_lower and git_unavailable:
        if readiness_impact not in {"draft_only", "blocked"}:
            failures.append(
                "Implementation Review with unavailable Git evidence must have draft_only or blocked readiness impact"
            )
    if "lifecycle understood as: post-fix validation" in plan_lower and git_unavailable:
        if readiness_impact != "blocked":
            failures.append(
                "Post-Fix Validation with unavailable Git/fix evidence must have blocked readiness impact"
            )
    return failures


def _validate_dual_source_evidence(data: dict) -> list[str]:
    failures: list[str] = []
    if data.get("rag_tool") != "ask_dita_expert":
        failures.append("rag_tool must be 'ask_dita_expert'; product-documentation evidence cannot come from search_jira_history")
    if data.get("jira_history_tool") != "search_jira_history":
        failures.append("jira_history_tool must be 'search_jira_history'; Jira history cannot come from ask_dita_expert")

    probes = data.get("rag_probes")
    behaviour_matters = data.get("behaviour_matters", True)
    if not isinstance(probes, list):
        failures.append("rag_probes must be a list of ask_dita_expert questions")
    else:
        if any(not isinstance(probe, str) or not probe.strip() for probe in probes):
            failures.append("every rag_probes entry must be a non-empty ask_dita_expert question")
        if behaviour_matters and len(probes) < 3:
            failures.append("rag_probes must record at least three ask_dita_expert questions when behaviour matters")
        if not behaviour_matters and not str(data.get("behaviour_not_applicable_reason", "")).strip():
            failures.append("behaviour_matters=false requires behaviour_not_applicable_reason")

    queries = data.get("jira_history_queries")
    unavailable_reason = str(data.get("jira_history_unavailable_reason", "")).strip()
    if not isinstance(queries, list):
        failures.append("jira_history_queries must be a list of search_jira_history call records")
    elif not unavailable_reason:
        scopes: set[str] = set()
        for index, query in enumerate(queries):
            if not isinstance(query, dict):
                failures.append(f"jira_history_queries[{index}] must be an object")
                continue
            scope = str(query.get("scope", "")).strip()
            scopes.add(scope)
            if not str(query.get("query", "")).strip():
                failures.append(f"jira_history_queries[{index}] is missing query")
            component = str(query.get("component", "")).strip()
            if not component:
                failures.append(f"jira_history_queries[{index}] is missing component")
            elif component not in CANONICAL_JIRA_COMPONENTS:
                allowed = ", ".join(sorted(CANONICAL_JIRA_COMPONENTS))
                failures.append(
                    f"jira_history_queries[{index}] component must be one of: {allowed}"
                )
            if scope == "same_customer":
                if not str(query.get("customer", "")).strip() and not str(query.get("customer_unavailable_reason", "")).strip():
                    failures.append(
                        f"jira_history_queries[{index}] same_customer search requires customer or customer_unavailable_reason"
                    )
            elif scope == "cross_customer":
                if str(query.get("customer", "")).strip():
                    failures.append(f"jira_history_queries[{index}] cross_customer search must omit customer")
            else:
                failures.append(
                    f"jira_history_queries[{index}] scope must be 'same_customer' or 'cross_customer'"
                )
        missing_scopes = {"same_customer", "cross_customer"} - scopes
        if missing_scopes:
            failures.append(
                "jira_history_queries must record both same_customer and cross_customer search_jira_history calls"
            )
        if data.get("indexed_history_run") is not True:
            failures.append("indexed_history_run must be true after search_jira_history queries run")
    else:
        if queries:
            failures.append("jira_history_unavailable_reason cannot be combined with recorded Jira-history queries")
        if not isinstance(data.get("indexed_history_run"), str) or not str(data["indexed_history_run"]).strip():
            failures.append("indexed_history_run must record the fallback reason when search_jira_history is unavailable")
    return failures


def check_manifest_completeness(path: str | None) -> list[str]:
    if not path:
        return ["evidence manifest is required but was not supplied (--manifest)"]
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"evidence manifest missing or invalid JSON: {exc}"]
    if not isinstance(data, dict):
        return ["evidence manifest must be a JSON object"]
    failures: list[str] = []
    for key in REQUIRED_MANIFEST_KEYS:
        if key not in data:
            failures.append(
                f"manifest is missing required key '{key}' - every plan must declare "
                f"preflight status, both RAG tool paths, their queries, attachments, and clone state"
            )
    failures.extend(_validate_evidence_preflight(data))
    failures.extend(_validate_dual_source_evidence(data))
    clones = data.get("clones")
    if isinstance(clones, list):
        for index, entry in enumerate(clones):
            if not isinstance(entry, dict):
                failures.append(f"manifest clones[{index}] must be an object")
                continue
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
    if manifest_path and Path(manifest_path).is_file():
        try:
            manifest_data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest_data = {}
        if isinstance(manifest_data, dict):
            failures += [
                f"[manifest] {failure}"
                for failure in _validate_preflight_plan_alignment(manifest_data, body)
            ]

    combined = Path(combined_path).read_text(encoding="utf-8")
    jira_keys = verify_mod._load_manifest(jira_keys_path)
    # Pass the manifest's clone roots so git-ref citations (main:<path>, etc.) are
    # disk-checked against the actual repos instead of being trusted blindly.
    git_ref_roots: list[str] = []
    if manifest_path and Path(manifest_path).is_file():
        try:
            _mdata = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            git_ref_roots = [c.get("path") for c in (_mdata.get("clones") or []) if isinstance(c, dict) and c.get("path")]
        except (OSError, json.JSONDecodeError):
            git_ref_roots = []
    v_fail, v_notes = verify_mod.verify(combined, jira_keys, git_ref_roots=git_ref_roots)
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
