from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

from app.benchmarks.test_plan_quality.models import (
    BenchmarkArtifactFingerprints,
    CaseMetrics,
    CaseReport,
    EvidenceCatalog,
    GoldenCase,
    RetrievalArtifact,
)


JIRA_KEY_RE = re.compile(r"\b(?!AC-\d+\b)[A-Z][A-Z0-9]+-\d+\b")
HEADING_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")
PAST_JIRA_ENTRY_RE = re.compile(
    r"^-\s+(?:\*\*)?(?P<key>(?!AC-\d+\b)[A-Z][A-Z0-9]+-\d+)\b"
)
ABSOLUTE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s`,;)]+")
BACKTICK_ABSOLUTE_PATH_RE = re.compile(r"`((?:[A-Za-z]:[\\/]|/)[^`]+)`")
GRAPH_PATH_ONLY_RE = re.compile(r"^(?:graph-)?path:[^\s]+$", re.I)
TRUSTED_WEB_HOSTS = {
    "experienceleague.adobe.com",
    "docs.oasis-open.org",
    "dita-lang.org",
    "www.dita-lang.org",
    "github.com",
    "www.figma.com",
    "figma.com",
}
LOCAL_SOURCE_TYPES = {"code", "attachment", "log"}
EVIDENCE_FINGERPRINT_FILES = ("retrieval.json", "evidence-catalog.json")
PLAN_FINGERPRINT_FILES = ("full-plan.md", "combined-plan.md")


def _framed_sha256(parts: list[tuple[str, bytes]]) -> str:
    """Hash named byte sequences without ambiguous concatenation boundaries."""
    digest = hashlib.sha256()
    for name, payload in parts:
        encoded_name = name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(8, "big"))
        digest.update(encoded_name)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return f"sha256:{digest.hexdigest()}"


def compute_benchmark_fingerprints(
    case_dir: Path,
    case_id: str,
) -> BenchmarkArtifactFingerprints:
    evidence_parts = [
        (filename, (case_dir / filename).read_bytes())
        for filename in EVIDENCE_FINGERPRINT_FILES
    ]
    evidence_snapshot_id = _framed_sha256(evidence_parts)
    plan_parts = [("evidence_snapshot_id", evidence_snapshot_id.encode("utf-8"))]
    plan_parts.extend(
        (filename, (case_dir / filename).read_bytes())
        for filename in PLAN_FINGERPRINT_FILES
    )
    return BenchmarkArtifactFingerprints(
        case_id=case_id,
        evidence_snapshot_id=evidence_snapshot_id,
        plan_fingerprint=_framed_sha256(plan_parts),
    )


def write_benchmark_fingerprints(
    case_dir: Path,
    case_id: str,
) -> BenchmarkArtifactFingerprints:
    fingerprints = compute_benchmark_fingerprints(case_dir, case_id)
    (case_dir / "fingerprints.json").write_text(
        fingerprints.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return fingerprints


def fingerprint_helper_script() -> str:
    """Return the immutable, dependency-free helper copied into candidate runs."""
    return '''from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def framed_sha256(parts):
    digest = hashlib.sha256()
    for name, payload in parts:
        encoded_name = name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(8, "big"))
        digest.update(encoded_name)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return f"sha256:{digest.hexdigest()}"


def main():
    case_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    evidence_snapshot_id = framed_sha256([
        (name, (case_dir / name).read_bytes())
        for name in ("retrieval.json", "evidence-catalog.json")
    ])
    plan_fingerprint = framed_sha256([
        ("evidence_snapshot_id", evidence_snapshot_id.encode("utf-8")),
        *[
            (name, (case_dir / name).read_bytes())
            for name in ("full-plan.md", "combined-plan.md")
        ],
    ])
    payload = {
        "schema_version": "aem-guides-test-plan-artifact-fingerprints-v1",
        "case_id": case_dir.name,
        "evidence_snapshot_id": evidence_snapshot_id,
        "plan_fingerprint": plan_fingerprint,
    }
    (case_dir / "fingerprints.json").write_text(
        json.dumps(payload, indent=2) + "\\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
'''


def load_skill_module(skill_root: Path, filename: str, module_name: str) -> ModuleType:
    path = skill_root / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load skill module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def section_lines(text: str, heading: str) -> list[str]:
    lines: list[str] = []
    active = False
    for raw_line in text.splitlines():
        match = HEADING_RE.fullmatch(raw_line.strip())
        if match:
            active = match.group(1) == heading
            continue
        if active:
            lines.append(raw_line.rstrip())
    return lines


def selected_history_keys(plan: str, issue_key: str) -> list[str]:
    selected: list[str] = []
    for line in section_lines(plan, "Known Jira Bugs / Past Similar Tickets"):
        match = PAST_JIRA_ENTRY_RE.match(line.strip())
        if not match:
            continue
        key = match.group("key")
        if key != issue_key and key not in selected:
            selected.append(key)
    return selected[:5]


def retrieved_history_keys(retrieval: RetrievalArtifact) -> list[str]:
    ranked: dict[str, int] = {}
    for query in retrieval.queries:
        for result in query.results:
            ranked[result.jira_key] = min(result.rank, ranked.get(result.jira_key, result.rank))
    return [key for key, _rank in sorted(ranked.items(), key=lambda item: (item[1], item[0]))]


def retrieved_history_keys_at(retrieval: RetrievalArtifact, cutoff: int) -> list[str]:
    keys: list[str] = []
    for query in retrieval.queries:
        for result in sorted(query.results, key=lambda item: item.rank):
            if result.rank <= cutoff and result.jira_key not in keys:
                keys.append(result.jira_key)
    return keys


def retrieved_history_versions(
    retrieval: RetrievalArtifact,
) -> tuple[dict[str, str], list[str]]:
    versions: dict[str, str] = {}
    conflicts: list[str] = []
    for query in retrieval.queries:
        for result in query.results:
            prior = versions.get(result.jira_key)
            if prior is not None and prior != result.version_applicability:
                conflicts.append(result.jira_key)
                continue
            versions[result.jira_key] = result.version_applicability
    return versions, list(dict.fromkeys(conflicts))


def _precision_recall(
    selected: list[str],
    expected: set[str],
    *,
    expect_no_match: bool,
) -> tuple[float, float]:
    if expect_no_match:
        score = 1.0 if not selected else 0.0
        return score, score
    if not selected:
        return 0.0, 0.0
    hits = expected.intersection(selected)
    return len(hits) / len(selected), len(hits) / len(expected)


def _retrieval_recall(retrieved: list[str], expected: set[str], *, expect_no_match: bool) -> float:
    if expect_no_match:
        return 1.0
    return len(expected.intersection(retrieved)) / len(expected)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _existing_source_path(source_ref: str) -> Path | None:
    candidates = [source_ref.strip().strip("`"), *BACKTICK_ABSOLUTE_PATH_RE.findall(source_ref)]
    candidates.extend(ABSOLUTE_PATH_RE.findall(source_ref))
    for value in candidates:
        cleaned = re.sub(r":\d+(?::\d+)?$", "", value.rstrip(".,;:)]}"))
        path = Path(cleaned)
        if path.is_file():
            return path
    return None


def _trusted_https_url(source_ref: str) -> bool:
    parsed = urlparse(source_ref)
    return parsed.scheme == "https" and parsed.hostname in TRUSTED_WEB_HOSTS


def _verified_catalog_tokens(
    catalog: EvidenceCatalog,
    allowed_jiras: set[str],
) -> tuple[list[str], list[str]]:
    tokens: list[str] = []
    invalid: list[str] = []
    for source in catalog.sources:
        valid = source.trust_tier != "candidate"
        if source.source_type == "jira":
            keys = set(JIRA_KEY_RE.findall(f"{source.source_id} {source.source_ref}"))
            valid = (
                valid
                and bool(keys.intersection(allowed_jiras))
                and source.verification_method in {"jira_mcp", "rag_retrieval", "pasted_input"}
            )
        elif source.source_type in {"url", "dita"}:
            stable_rag_ref = source.source_ref.startswith(("aem_guides:", "dita_spec:"))
            valid = (
                valid
                and source.verification_method in {"direct_url", "rag_retrieval"}
                and (_trusted_https_url(source.source_ref) or stable_rag_ref)
            )
        elif source.source_type in LOCAL_SOURCE_TYPES:
            expected_method = {
                "code": "repo_read",
                "attachment": "attachment_read",
                "log": "log_read",
            }[source.source_type]
            path = _existing_source_path(source.source_ref)
            valid = (
                valid
                and source.verification_method == expected_method
                and path is not None
                and bool(source.source_hash)
                and source.source_hash == _sha256(path)
            )
        elif source.source_type == "figma":
            valid = (
                valid
                and source.verification_method == "figma_mcp"
                and _trusted_https_url(source.source_ref)
                and urlparse(source.source_ref).hostname in {"figma.com", "www.figma.com"}
            )
        if not valid:
            invalid.append(source.source_id)
            continue
        for value in (source.source_id, source.source_ref):
            token = value.strip()
            if token and token not in tokens:
                tokens.append(token)
    return tokens, invalid


def _citation_accuracy(
    criteria: list[dict[str, Any]],
    catalog: EvidenceCatalog,
    allowed_jiras: set[str],
) -> tuple[float, list[str], list[str]]:
    if not criteria:
        return 0.0, ["Acceptance Criteria contains no canonical criteria"], []
    tokens, invalid_sources = _verified_catalog_tokens(catalog, allowed_jiras)
    unknown: list[str] = []
    valid = 0
    for criterion in criteria:
        evidence = str(criterion.get("evidence") or "").strip()
        evidence_lower = evidence.casefold()
        catalog_match = any(token.casefold() in evidence_lower for token in tokens)
        if GRAPH_PATH_ONLY_RE.fullmatch(evidence):
            catalog_match = False
        if catalog_match:
            valid += 1
        else:
            unknown.append(str(criterion.get("id") or "unknown"))
    return valid / len(criteria), unknown, invalid_sources


def _allowed_jira_keys(
    case: GoldenCase,
    retrieval: RetrievalArtifact,
    catalog: EvidenceCatalog,
) -> set[str]:
    allowed = {case.jira_key}
    allowed.update(retrieved_history_keys(retrieval))
    for source in catalog.sources:
        if source.source_type == "jira":
            allowed.update(JIRA_KEY_RE.findall(f"{source.source_id} {source.source_ref}"))
    return allowed


def score_case(
    case: GoldenCase,
    *,
    case_dir: Path,
    skill_root: Path,
) -> CaseReport:
    required = {
        "full-plan.md": case_dir / "full-plan.md",
        "combined-plan.md": case_dir / "combined-plan.md",
        "evidence-manifest.json": case_dir / "evidence-manifest.json",
        "retrieval.json": case_dir / "retrieval.json",
        "evidence-catalog.json": case_dir / "evidence-catalog.json",
        "fingerprints.json": case_dir / "fingerprints.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        return CaseReport(
            case_id=case.id,
            jira_key=case.jira_key,
            component=case.component,
            passed=False,
            metrics=CaseMetrics(),
            failures=["missing benchmark artifact: " + name for name in missing],
        )

    failures: list[str] = []
    notes: list[str] = []
    try:
        plan = required["full-plan.md"].read_text(encoding="utf-8")
        combined = required["combined-plan.md"].read_text(encoding="utf-8")
        evidence_manifest = json.loads(required["evidence-manifest.json"].read_text(encoding="utf-8"))
        retrieval = RetrievalArtifact.model_validate_json(required["retrieval.json"].read_text(encoding="utf-8"))
        catalog = EvidenceCatalog.model_validate_json(required["evidence-catalog.json"].read_text(encoding="utf-8"))
        fingerprints = BenchmarkArtifactFingerprints.model_validate_json(
            required["fingerprints.json"].read_text(encoding="utf-8")
        )
    except Exception as exc:
        return CaseReport(
            case_id=case.id,
            jira_key=case.jira_key,
            component=case.component,
            passed=False,
            metrics=CaseMetrics(),
            failures=[f"benchmark artifact could not be parsed: {type(exc).__name__}: {exc}"],
        )

    if retrieval.issue.strip().upper() != case.jira_key:
        failures.append("retrieval.json issue does not match the benchmark case")
    if catalog.issue.strip().upper() != case.jira_key:
        failures.append("evidence-catalog.json issue does not match the benchmark case")
    computed_fingerprints = compute_benchmark_fingerprints(case_dir, case.id)
    fingerprint_integrity = (
        fingerprints.model_dump(mode="json")
        == computed_fingerprints.model_dump(mode="json")
    )
    if not fingerprint_integrity:
        failures.append(
            "fingerprints.json does not match the exact submitted evidence and plan artifacts"
        )
    for query in retrieval.queries:
        blob = query.query.casefold()
        missing_terms = [term for term in case.required_query_terms if term.casefold() not in blob]
        if missing_terms:
            failures.append(
                f"{query.scope} retrieval query omitted required mechanism term(s): {', '.join(missing_terms)}"
            )
        if query.component != case.component:
            failures.append(
                f"{query.scope} retrieval query component is {query.component!r}; expected {case.component!r}"
            )
        if query.scope == "same_customer" and case.customer and query.customer != case.customer:
            failures.append("same_customer retrieval query used the wrong customer")
        if query.scope == "cross_customer" and query.customer:
            failures.append("cross_customer retrieval query must not set customer")

    ac_failures: list[str] = []
    parsed_criteria: list[dict[str, Any]] = []
    try:
        ac_module = load_skill_module(skill_root, "ac_contract.py", f"benchmark_ac_{case.id}")
        ac_lines = ac_module.acceptance_lines(plan)
        criteria = [ac_module.parse_ac_line(line) for line in ac_lines]
        if not criteria:
            ac_failures.append("Acceptance Criteria contains no canonical criteria")
        if any(criterion is None for criterion in criteria):
            ac_failures.append("one or more Acceptance Criteria lines violate the immutable AC grammar")
        parsed_criteria = [criterion for criterion in criteria if criterion is not None]
        ac_failures.extend(ac_module.validate_ac_sequence(parsed_criteria))
    except Exception as exc:
        ac_failures.append(
            f"benchmark could not execute the AC contract: {type(exc).__name__}: {exc}"
        )
    failures.extend(ac_failures)

    selected = selected_history_keys(plan, case.jira_key)
    retrieved = retrieved_history_keys(retrieval)
    retrieved_at_10 = retrieved_history_keys_at(retrieval, 10)
    actual_history_versions, version_conflicts = retrieved_history_versions(retrieval)
    expected = set(case.expected_history_keys)
    history_precision, history_recall = _precision_recall(
        selected,
        expected,
        expect_no_match=case.expect_no_strong_history,
    )
    retrieval_recall = _retrieval_recall(
        retrieved_at_10,
        expected,
        expect_no_match=case.expect_no_strong_history,
    )
    if any(key not in retrieved for key in selected):
        failures.append("Past Jiras contains a key that was not present in recorded retrieval results")
    if version_conflicts:
        failures.append(
            "retrieval queries disagree on release/version applicability for: "
            + ", ".join(version_conflicts)
        )
    version_mismatches = [
        key
        for key, expected_version in case.expected_history_versions.items()
        if actual_history_versions.get(key) != expected_version
    ]
    history_version_accuracy = not version_conflicts and not version_mismatches
    if version_mismatches:
        failures.append(
            "historical release/version applicability mismatch for: "
            + ", ".join(
                f"{key} (expected {case.expected_history_versions[key]}, "
                f"found {actual_history_versions.get(key, 'missing')})"
                for key in version_mismatches
            )
        )

    allowed_jiras = _allowed_jira_keys(case, retrieval, catalog)
    citation_accuracy, unknown_citations, invalid_sources = _citation_accuracy(
        parsed_criteria,
        catalog,
        allowed_jiras,
    )
    if unknown_citations:
        failures.append(
            "Acceptance Criteria cite evidence absent from evidence-catalog.json: "
            + ", ".join(unknown_citations)
        )
    if invalid_sources:
        failures.append(
            "evidence catalog contains unverified or ineligible source(s): "
            + ", ".join(invalid_sources)
        )

    performance = evidence_manifest.get("performance_assessment")
    actual_performance = str(performance.get("decision") or "") if isinstance(performance, dict) else ""
    performance_ok = actual_performance == case.expected_performance_decision
    if not performance_ok:
        failures.append(
            "performance decision mismatch: "
            f"expected {case.expected_performance_decision}, found {actual_performance or 'missing'}"
        )

    cited_jiras = set(JIRA_KEY_RE.findall(plan + "\n" + combined))
    unverified_jiras = sorted(cited_jiras - allowed_jiras)
    if unverified_jiras:
        failures.append("unverified Jira citation(s): " + ", ".join(unverified_jiras))

    gate_failures: list[str] = []
    gate_notes: list[str] = []
    fetched_keys_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f"benchmark-{case.id}-",
            suffix="-jira-keys.txt",
            delete=False,
        ) as handle:
            handle.write("\n".join(sorted(allowed_jiras)) + "\n")
            fetched_keys_path = Path(handle.name)
        gates = load_skill_module(skill_root, "run_gates.py", f"benchmark_gates_{case.id}")
        gate_failures, gate_notes = gates.run(
            str(required["full-plan.md"]),
            str(required["combined-plan.md"]),
            str(required["evidence-manifest.json"]),
            str(fetched_keys_path),
            True,
        )
        notes.extend(gate_notes)
    except Exception as exc:
        gate_failures = [
            f"benchmark could not execute skill gates: {type(exc).__name__}: {exc}"
        ]
    finally:
        if fetched_keys_path is not None:
            fetched_keys_path.unlink(missing_ok=True)
    failures.extend("skill gate: " + failure for failure in gate_failures)

    hallucination_free = not (
        unverified_jiras
        or unknown_citations
        or invalid_sources
        or any("[verify]" in failure for failure in gate_failures)
        or any(key not in retrieved for key in selected)
    )
    metrics = CaseMetrics(
        artifact_complete=True,
        gate_pass=not gate_failures,
        ac_contract=not ac_failures,
        history_precision_at_5=history_precision,
        history_recall_at_5=history_recall,
        retrieval_recall_at_10=retrieval_recall,
        citation_accuracy=citation_accuracy,
        performance_decision_accuracy=performance_ok,
        history_version_accuracy=history_version_accuracy,
        fingerprint_integrity=fingerprint_integrity,
        hallucination_free=hallucination_free,
    )
    return CaseReport(
        case_id=case.id,
        jira_key=case.jira_key,
        component=case.component,
        passed=not failures,
        metrics=metrics,
        selected_history_keys=selected,
        retrieved_history_keys=retrieved[:10],
        actual_performance_decision=actual_performance,
        actual_history_versions=dict(sorted(actual_history_versions.items())),
        evidence_snapshot_id=fingerprints.evidence_snapshot_id,
        plan_fingerprint=fingerprints.plan_fingerprint,
        ac_count=len(parsed_criteria),
        unknown_ac_citations=unknown_citations,
        unverified_evidence_sources=invalid_sources,
        unverified_jira_keys=unverified_jiras,
        failures=list(dict.fromkeys(failures)),
        notes=notes,
    )
