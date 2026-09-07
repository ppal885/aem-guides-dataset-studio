"""Miss-probe library (UACDISCOVER-02) - the compounding learning loop.

Every human-caught miss becomes a REUSABLE discovery probe, so the skill improves
per correction instead of needing a new bespoke gate each time. This module holds
the persistent, curated probe library (data/miss_probes.json) and exposes matching
probes to the dimension synthesizer (UACDISCOVER-01) as LEARNED_PROBE candidates.

Governance mirrors human_feedback_delta.py (the only supervisory learning truth):
  * A probe is ACTIVE only from source=HUMAN with promotion_state APPROVED
    (VALIDATING -> SHADOW). AI_REVIEW / FLUFFYJAWS / MODEL can never be ACTIVE.
  * Deterministically mined LEARNED precedents may emit only in SHADOW after
    source binding, independent-report and low-confidence checks. They never
    establish Human approval, a confirmed miss, or an acceptance contract.
  * signal_pattern.match and candidate_template must be GENERALIZED - a single
    concrete literal (Jira key, symbol, path, camelCase identifier) is rejected.
  * counterexamples_checked must be true before ACTIVE.
  * RENDERING_LANGUAGE_PATTERN / TESTABILITY_PATTERN deltas can never become a
    discovery probe.
  * A probe below the independent-case floor without a normative invariant stays
    SHADOW; RETIRED probes never emit.

Generic only.  Standard library only.  No product identifier is hardcoded here;
the shipped library lives in data/miss_probes.json.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "aem-guides-miss-probes-v1"
REQUIRED_INDEPENDENT_CASES = 2
HUMAN_SOURCE = "HUMAN"
LEARNED_SOURCE = "LEARNED"
LEARNED_CONFIDENCE_CEILING = 0.3
LANGUAGE_PATTERN_CLASSES = {"RENDERING_LANGUAGE_PATTERN", "TESTABILITY_PATTERN"}
VALID_AXES = {
    "VALUE_SET_CHANNEL", "CODE_PATH_CONSUMER", "OUTPUT_PRESET", "TOPIC_TYPE",
    "TERMINAL_STATE", "LIFECYCLE", "CONFIG_BRANCH", "PERMISSION_ROLE",
    "MIGRATION_PATH", "NEGATIVE_BOUNDARY", "ENTRY_POINT", "REPRO_DIMENSION",
    "DOWNSTREAM_REGRESSION", "LOCALIZATION", "STATE_PARTITION", "REFERENCE_ARTIFACT",
}

_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_SYMBOLISH_RE = re.compile(r"[A-Za-z]+::|[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*|[\\/][\w.\\/-]+|\.\w+\(")
_SOURCE_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _learned_shadow_status(probe: dict, provenance: dict) -> tuple[str, list[str]]:
    """CSV-mined precedents may advise, but cannot claim Human supervision.

    Case hashes are provenance identifiers only, never matching predicates. The
    external mining ledger retains their original source keys and row binding.
    Duplicate variants share an incident_id and therefore count only once. This
    checks the declared mining assessment, not Human confirmation of independence;
    the latter remains part of approval review and is never inferred from hashes.
    """
    if provenance.get("promotion_state") != "VALIDATING":
        return "RETIRED", ["LEARNED source requires VALIDATING; approval cannot be inferred"]
    confidence = probe.get("confidence")
    if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= LEARNED_CONFIDENCE_CEILING):
        return "RETIRED", ["LEARNED confidence must be finite and between 0 and 0.3"]
    source_hash = provenance.get("source_hash")
    if not isinstance(source_hash, str) or not _SOURCE_HASH_RE.fullmatch(source_hash):
        return "RETIRED", ["LEARNED provenance requires a SHA-256 source hash"]
    supports = provenance.get("supporting_cases")
    if not isinstance(supports, list) or len(supports) < REQUIRED_INDEPENDENT_CASES:
        return "RETIRED", ["LEARNED provenance needs at least two independently bound cases"]
    case_ids: set[str] = set()
    incident_ids: set[str] = set()
    source_refs: set[str] = set()
    for item in supports:
        if not isinstance(item, dict):
            return "RETIRED", ["LEARNED supporting case must be an object"]
        case_id, incident_id = item.get("case_id"), item.get("incident_id")
        if any(not isinstance(value, str) or not _SOURCE_HASH_RE.fullmatch(value)
               for value in (case_id, incident_id)):
            return "RETIRED", ["LEARNED case and incident IDs must be SHA-256 provenance references"]
        if case_id in case_ids:
            return "RETIRED", ["duplicate LEARNED supporting case"]
        if item.get("evidence_kind") not in {"VALIDATED_AC", "THEME_PRECEDENT"}:
            return "RETIRED", ["LEARNED case evidence kind is not an accepted corpus category"]
        source_ref = item.get("source_ref")
        if not isinstance(source_ref, str) or not source_ref.startswith(source_hash + "#row="):
            return "RETIRED", ["LEARNED case must bind to the mined CSV source and row"]
        row = source_ref[len(source_hash + "#row="):]
        if not row.isascii() or not row.isdigit() or len(row) > 9 or int(row) < 2:
            return "RETIRED", ["LEARNED case row must identify a data row"]
        if source_ref in source_refs:
            return "RETIRED", ["duplicate LEARNED supporting CSV row"]
        case_ids.add(case_id)
        incident_ids.add(incident_id)
        source_refs.add(source_ref)
    count = provenance.get("independent_case_count")
    if type(count) is not int or count != len(incident_ids) or count < REQUIRED_INDEPENDENT_CASES:
        return "RETIRED", ["LEARNED independent support count must match distinct incident references"]
    return "SHADOW", ["LEARNED precedent only; VALIDATING, not Human-approved acceptance truth"]


def _default_library_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "miss_probes.json"


def load_library(path: str | Path | None = None) -> list[dict]:
    p = Path(path) if path else _default_library_path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    probes = data.get("probes") if isinstance(data, dict) else data
    return [pr for pr in probes if isinstance(pr, dict)] if isinstance(probes, list) else []


def _is_literal(token: str) -> bool:
    """A token is too specific (not generalized) if it looks like an identifier."""
    if not isinstance(token, str) or not token.strip():
        return True
    if _JIRA_KEY_RE.search(token) or _SYMBOLISH_RE.search(token):
        return True
    return False


def _generalized(probe: dict) -> bool:
    sp = probe.get("signal_pattern") or {}
    match = sp.get("match") if isinstance(sp, dict) else None
    if not isinstance(match, list) or not match:
        return False
    concrete = [tok for tok in match if _is_literal(str(tok))]
    if concrete:
        return False
    template = str((probe.get("implied_dimension") or {}).get("candidate_template", ""))
    if not template.strip() or _JIRA_KEY_RE.search(template):
        return False
    return True


def effective_status(probe: dict) -> tuple[str, list[str]]:
    """Return (effective_status, reasons). Enforces governance defensively even if
    the stored status over-claims. effective_status is ACTIVE / SHADOW / RETIRED."""
    if not isinstance(probe, dict):
        return "RETIRED", ["probe must be an object"]
    reasons: list[str] = []
    declared = str(probe.get("status", "")).strip().upper()
    if declared == "RETIRED":
        return "RETIRED", ["declared RETIRED"]

    prov = probe.get("provenance") or {}
    if not isinstance(prov, dict) or not isinstance(probe.get("implied_dimension"), dict):
        return "RETIRED", ["probe provenance and implied_dimension must be objects"]
    source = str(prov.get("source", "")).strip().upper()
    promotion = str(prov.get("promotion_state", "")).strip().upper()
    axis = str((probe.get("implied_dimension") or {}).get("axis", "")).strip().upper()
    pattern_class = str(probe.get("pattern_class", "")).strip().upper()

    if source not in {HUMAN_SOURCE, LEARNED_SOURCE}:
        return "RETIRED", [f"non-human source {source or '<none>'} can never emit"]
    if pattern_class in LANGUAGE_PATTERN_CLASSES:
        return "RETIRED", ["language/testability pattern is not a discovery probe"]
    if axis not in VALID_AXES:
        return "RETIRED", [f"invalid implied dimension axis {axis or '<none>'}"]
    if not _generalized(probe):
        return "RETIRED", ["not generalized: signal_pattern/candidate_template names a concrete literal"]

    if source == LEARNED_SOURCE:
        return _learned_shadow_status(probe, prov)

    counterexamples = bool(probe.get("counterexamples_checked"))
    cases = prov.get("independent_case_count")
    cases = cases if isinstance(cases, int) else 0
    normative = bool(probe.get("normative_invariant"))

    # VALIDATING-derived or below-floor probes run in SHADOW.
    if promotion == "APPROVED" and counterexamples and (cases >= REQUIRED_INDEPENDENT_CASES or normative):
        return "ACTIVE", reasons
    if promotion in {"APPROVED", "VALIDATING"}:
        why = []
        if not counterexamples:
            why.append("counterexamples not checked")
        if not (cases >= REQUIRED_INDEPENDENT_CASES or normative):
            why.append(f"independent_case_count {cases} < {REQUIRED_INDEPENDENT_CASES} and no normative invariant")
        if promotion == "VALIDATING":
            why.append("promotion_state VALIDATING")
        return "SHADOW", why or ["shadow"]
    return "RETIRED", [f"promotion_state {promotion or '<none>'} is not promotable"]


def candidates_for(evidence_pairs: list[tuple[str, str]], library_path: str | Path | None = None) -> list[dict]:
    """Emit LEARNED_PROBE INVESTIGATION_CANDIDATEs for probes matching the evidence.

    evidence_pairs is a list of (evidence_label, text) as produced by the dimension
    synthesizer, so the library never has to re-derive evidence extraction.
    """
    candidates: list[dict] = []
    haystacks = [(label, str(text).lower()) for label, text in evidence_pairs]
    for probe in load_library(library_path):
        status, _ = effective_status(probe)
        if status not in {"ACTIVE", "SHADOW"}:
            continue
        sp = probe.get("signal_pattern") or {}
        match = [str(t).lower() for t in (sp.get("match") or []) if str(t).strip()]
        if not match:
            continue
        hits = [label for label, text in haystacks if any(tok in text for tok in match)]
        if not hits:
            continue
        axis = str((probe.get("implied_dimension") or {}).get("axis", "")).upper()
        template = str((probe.get("implied_dimension") or {}).get("candidate_template", ""))
        delta_ids = [d for d in ((probe.get("provenance") or {}).get("delta_ids") or []) if isinstance(d, str)]
        candidate = {
            "hypothesis_id": "",
            "dimension": axis,
            "candidate": template,
            "reason": f"LEARNED_PROBE {probe.get('probe_id', '')} matched the current evidence",
            "technical_basis": [
                f"LEARNED_PROBE:{probe.get('probe_id', '')}",
                *(f"delta:{d}" for d in delta_ids),
            ],
            "current_evidence": hits,
            "status": "INVESTIGATION_CANDIDATE",
            "requires_more_evidence": True,
            "confidence": 0.5 if status == "ACTIVE" else 0.3,
            "equivalence_key": f"LEARNED_PROBE:{axis}",
            "generator": "LEARNED_PROBE",
            "probe_id": probe.get("probe_id", ""),
            "non_authoritative": status == "SHADOW",
        }
        provenance = probe.get("provenance") or {}
        if provenance.get("source") == LEARNED_SOURCE:
            candidate.update({
                "confidence": probe["confidence"],
                "source": LEARNED_SOURCE,
                "authority": "SUPPORTING_DISCOVERY",
                "promotion_state": "VALIDATING",
                "effective_status": "SHADOW",
                "auto_author_ac": False,
                "auto_promote": False,
                "equivalence_key": "LEARNED_PROBE:" + str(probe.get("equivalence_key") or probe.get("probe_id")),
            })
            candidate["technical_basis"] += [
                "mined-source:" + provenance["source_hash"],
                *("case:" + case["case_id"] for case in provenance["supporting_cases"]),
            ]
        candidates.append(candidate)
    return candidates


def is_present(manifest: dict | None = None) -> bool:
    data = manifest if isinstance(manifest, dict) else {}
    return isinstance(data.get("miss_probe_activity"), dict)


def validate(manifest: dict | None = None) -> list[str]:
    """Consistency check for an optional manifest miss_probe_activity block.

    Absent block -> clean pass (backward-compatible). When declared, every referenced
    probe_id must exist in the library and each disposition must name a real axis.
    """
    data = manifest if isinstance(manifest, dict) else {}
    block = data.get("miss_probe_activity")
    if not isinstance(block, dict):
        return []
    problems: list[str] = []
    known = {str(p.get("probe_id")) for p in load_library() if p.get("probe_id")}
    for i, entry in enumerate(block.get("dispositions") or []):
        if not isinstance(entry, dict):
            problems.append(f"miss_probe_activity.dispositions[{i}] must be an object")
            continue
        pid = str(entry.get("probe_id", "")).strip()
        if pid and pid not in known:
            problems.append(f"miss_probe_activity references unknown probe_id {pid}")
        disp = str(entry.get("disposition", "")).strip().upper()
        if disp not in {"COVERED_BY_AC", "OPEN_QUESTION", "REJECTED", "INVESTIGATE"}:
            problems.append(f"miss_probe_activity {pid or i} has invalid disposition {disp or '<none>'}")
    return problems


def summarize(manifest: dict | None = None) -> str:
    library = load_library()
    active = sum(1 for p in library if effective_status(p)[0] == "ACTIVE")
    shadow = sum(1 for p in library if effective_status(p)[0] == "SHADOW")
    return f"miss-probe library: {len(library)} probe(s) ({active} active, {shadow} shadow)"


def run_self_tests() -> None:
    """Exercise advisory mining independently of any real customer or ticket."""
    import copy
    import tempfile

    source_hash = "sha256:" + "a" * 64
    probe = {
        "probe_id": "MP-TEST",
        "pattern_class": "DISCOVERY_PATTERN",
        "signal_pattern": {"match": ["table header"]},
        "implied_dimension": {
            "axis": "STATE_PARTITION",
            "candidate_template": "investigate header changes using current evidence",
        },
        "provenance": {
            "source": "LEARNED", "promotion_state": "VALIDATING",
            "independent_case_count": 2, "source_hash": source_hash,
            "supporting_cases": [
                {"case_id": "sha256:" + c * 64,
                 "incident_id": "sha256:" + c * 64,
                 "source_ref": source_hash + "#row=" + str(row),
                 "evidence_kind": kind}
                for c, row, kind in (("b", 2, "THEME_PRECEDENT"), ("c", 3, "VALIDATED_AC"))
            ],
        },
        "confidence": 0.2, "status": "SHADOW", "counterexamples_checked": False,
        "equivalence_key": "header-state-investigation",
    }
    assert effective_status(probe)[0] == "SHADOW"
    overclaim = copy.deepcopy(probe)
    overclaim.update(status="ACTIVE", normative_invariant=True, counterexamples_checked=True)
    assert effective_status(overclaim)[0] == "SHADOW", "stored ACTIVE cannot promote a mined precedent"
    for source in ("MODEL", "AI_REVIEW", "FLUFFYJAWS"):
        bad = copy.deepcopy(probe)
        bad["provenance"]["source"] = source
        assert effective_status(bad)[0] == "RETIRED"
    for promotion in ("APPROVED", "CANDIDATE", ""):
        bad = copy.deepcopy(probe)
        bad["provenance"]["promotion_state"] = promotion
        assert effective_status(bad)[0] == "RETIRED"
    for confidence in (-0.1, 0.31, True, float("nan"), float("inf"), "0.2", None):
        bad = copy.deepcopy(probe)
        bad["confidence"] = confidence
        assert effective_status(bad)[0] == "RETIRED"
    for mutate in (
        lambda p: p["provenance"].update(independent_case_count=99),
        lambda p: p["provenance"].update(independent_case_count=True),
        lambda p: p["provenance"].update(source_hash="unbound"),
        lambda p: p["provenance"].update(supporting_cases=[]),
        lambda p: p["provenance"]["supporting_cases"][1].update(incident_id="sha256:" + "b" * 64),
        lambda p: p["provenance"]["supporting_cases"][1].update(case_id="sha256:" + "b" * 64),
        lambda p: p["provenance"]["supporting_cases"][1].update(source_ref=source_hash + "#row=1"),
        lambda p: p["provenance"]["supporting_cases"][1].update(source_ref=source_hash + "#row=2"),
        lambda p: p["provenance"]["supporting_cases"][1].update(evidence_kind="AI_REVIEW"),
        lambda p: p["signal_pattern"].update(match=["specificCamelSymbol"]),
        lambda p: p["implied_dimension"].update(axis="UNDECLARED_AXIS"),
        lambda p: p.update(pattern_class="RENDERING_LANGUAGE_PATTERN"),
        lambda p: p.update(status="RETIRED"),
    ):
        bad = copy.deepcopy(probe)
        mutate(bad)
        assert effective_status(bad)[0] == "RETIRED"
    with tempfile.TemporaryDirectory(prefix="learned-probe-test-") as directory:
        library = Path(directory) / "probes.json"
        library.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "probes": [probe]}), encoding="utf-8")
        candidates = candidates_for([("source-summary", "Table header changes")], library)
        assert len(candidates) == 1
        item = candidates[0]
        assert item["generator"] == "LEARNED_PROBE"
        assert item["status"] == "INVESTIGATION_CANDIDATE"
        assert item["source"] == "LEARNED" and item["non_authoritative"] is True
        assert item["confidence"] == 0.2 and item["promotion_state"] == "VALIDATING"
        assert item["auto_author_ac"] is False and item["auto_promote"] is False
        assert item["current_evidence"] == ["source-summary"]
        assert len([basis for basis in item["technical_basis"] if basis.startswith("case:")]) == 2
        assert candidates_for([("source-summary", "An unrelated dialog closes")], library) == []
        assert candidates_for([("source-summary", source_hash)], library) == [], "provenance never matches"


def main() -> int:
    parser = argparse.ArgumentParser(description="Miss-probe library (UACDISCOVER-02)")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_tests()
        print("PASS: learned miss-probe advisory governance self-tests")
        return 0
    if args.list:
        for probe in load_library():
            status, reasons = effective_status(probe)
            print(f"{probe.get('probe_id')}: {status} ({'; '.join(reasons) or 'ok'})")
    manifest = (
        json.loads(args.manifest.read_text(encoding="utf-8"))
        if args.manifest and args.manifest.exists()
        else {}
    )
    problems = validate(manifest)
    for p in problems:
        print(f"REVIEW miss-probe: {p}")
    print(summarize(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
