"""Principal performance-QA assessment and plan-alignment contract.

The full assessment is internal evidence-manifest data. The test plan gains no
new section: when performance is required, only canonical Performance ACs and
their mapped scenarios become reader-visible.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ac_contract import acceptance_lines, parse_ac_line


PERFORMANCE_SCHEMA_VERSION = "aem-guides-performance-assessment-v1"
PERFORMANCE_DECISIONS = ("required", "conditional", "not_required")
PERFORMANCE_RISKS = ("high", "medium", "low")
SIGNAL_CATEGORIES = (
    "data_volume_or_cardinality_growth",
    "concurrency_or_contention",
    "repetition_or_long_duration",
    "latency_timeout_or_throughput",
    "cpu_memory_gc_or_storage",
    "queue_backlog_or_external_dependency",
    "persistence_cleanup_or_stale_state",
)
SIGNAL_STATUSES = ("present", "absent", "unknown")
WORKLOAD_FIELDS = ("operation", "cardinality", "concurrency", "repetition", "duration")
METRICS = (
    "latency_p50",
    "latency_p90",
    "latency_p95",
    "latency_p99",
    "throughput",
    "error_rate",
    "timeout_rate",
    "cpu_utilization",
    "memory_usage",
    "heap_usage",
    "gc_pause",
    "queue_depth",
    "backlog_age",
    "storage_growth",
    "reference_cardinality",
)
TEST_TYPES = ("load", "stress", "soak", "scalability", "concurrency", "benchmark")
ORACLE_STATUSES = ("quantified", "unresolved", "not_applicable")
AC_ID_RE = re.compile(r"^AC-\d{2}$")
HEADING_RE = re.compile(r"^\*\*(.+?)\*\*$")
QUANTIFIED_VALUE_RE = re.compile(
    r"(?i)\b\d[\d,]*(?:\.\d+)?\s*(?:%|ms|milliseconds?|s|sec(?:onds?)?|"
    r"min(?:utes?)?|hours?|req(?:uests?)?/(?:s|sec(?:ond)?s?)|ops?/(?:s|sec(?:ond)?s?)|"
    r"items?/(?:s|sec(?:ond)?s?)|topics?/(?:s|sec(?:ond)?s?)|maps?/(?:s|sec(?:ond)?s?)|"
    r"jobs?/(?:s|sec(?:ond)?s?)|pages?/(?:s|sec(?:ond)?s?)|kb|mb|gb|kib|mib|gib|"
    r"errors?|timeouts?)(?=\s|$|[.,;])"
)
QUANTIFIED_WORKLOAD_RE = re.compile(
    r"(?i)\b\d[\d,]*(?:\.\d+)?\s*(?:(?:concurrent|simultaneous|parallel|"
    r"virtual|active)\s+)?(?:users?|threads?|jobs?|requests?|operations?|"
    r"topics?|maps?|assets?|files?|pages?|languages?|outputs?|iterations?|records?|references?)\b"
)
PERFORMANCE_SCENARIO_RE = re.compile(
    r"(?i)\b(?:performance|load|stress|soak|benchmark|scalability|concurren(?:cy|t)|"
    r"latency|throughput|resource|heap|queue|backlog)\b"
)
PERFORMANCE_QUESTION_RE = re.compile(
    r"(?i)\b(?:performance|latency|throughput|scale|volume|concurren(?:cy|t)|"
    r"memory|heap|cpu|queue|backlog|sla|baseline)\b"
)
JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
PLAN_JIRA_KEY_RE = re.compile(r"\b(?!AC-)[A-Z][A-Z0-9_]{2,}-\d+\b")
HISTORICAL_RELATIONSHIPS = ("same_mechanism", "shared_execution_path", "area_only")
COMPARATIVE_ORACLE_RE = re.compile(
    r"(?i)(?:\b\d+(?:\.\d+)?\s*x\b|\b\d+(?:\.\d+)?\s*%\b|"
    r"(?:at\s+least|at\s+most|no\s+more\s+than|no\s+less\s+than|"
    r"<=|>=|less\s+than\s+or\s+equal|greater\s+than\s+or\s+equal).{0,40}"
    r"\d+(?:\.\d+)?\s*(?:x|%))"
)
HISTORICAL_PERFORMANCE_MENTION_RE = re.compile(
    r"(?i)\b(?:performance|latency|throughput|load|stress|soak|benchmark|"
    r"scalability|concurren(?:cy|t)|timeout|response[ -]?time|cpu|memory|gc)\b"
)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _jira_keys_in_value(value: Any) -> set[str]:
    """Extract Jira keys from the manifest's current-issue identifier."""
    if isinstance(value, str):
        return set(PLAN_JIRA_KEY_RE.findall(value))
    if isinstance(value, dict):
        return {
            key
            for nested in value.values()
            for key in _jira_keys_in_value(nested)
        }
    if isinstance(value, list):
        return {
            key
            for nested in value
            for key in _jira_keys_in_value(nested)
        }
    return set()


def _controlled_list(value: Any, allowed: tuple[str, ...], label: str) -> list[str]:
    failures: list[str] = []
    if not isinstance(value, list):
        return [f"{label} must be a list"]
    if any(not isinstance(item, str) or item not in allowed for item in value):
        failures.append(f"{label} contains an unsupported value")
    if all(isinstance(item, str) for item in value) and len(value) != len(set(value)):
        failures.append(f"{label} must not contain duplicates")
    return failures


def _validate_historical_contracts(value: Any) -> tuple[list[str], int]:
    """Validate retained same-mechanism performance contracts from Jira history."""
    if value is None:
        return [], 0
    if not isinstance(value, list):
        return ["performance_assessment.historical_contracts must be a list"], 0

    failures: list[str] = []
    retained_count = 0
    seen_keys: set[str] = set()
    for index, contract in enumerate(value):
        prefix = f"performance_assessment.historical_contracts[{index}]"
        if not isinstance(contract, dict):
            failures.append(f"{prefix} must be an object")
            continue

        jira_key = contract.get("jira_key")
        if not isinstance(jira_key, str) or not JIRA_KEY_RE.fullmatch(jira_key):
            failures.append(f"{prefix}.jira_key must be a valid Jira key")
        elif jira_key in seen_keys:
            failures.append(f"{prefix}.jira_key duplicates another historical contract")
        else:
            seen_keys.add(jira_key)

        relationship = contract.get("relationship")
        if relationship not in HISTORICAL_RELATIONSHIPS:
            failures.append(f"{prefix}.relationship is invalid")

        retained = contract.get("retained")
        if not isinstance(retained, bool):
            failures.append(f"{prefix}.retained must be true or false")
            retained = False

        for field in ("mechanism", "workload", "oracle"):
            if not _nonempty_string(contract.get(field)):
                failures.append(f"{prefix}.{field} is required")

        evidence_refs = contract.get("evidence_refs")
        if (
            not isinstance(evidence_refs, list)
            or not evidence_refs
            or any(not _nonempty_string(item) for item in evidence_refs)
        ):
            failures.append(f"{prefix}.evidence_refs must cite at least one underlying source")

        if retained:
            retained_count += 1
            if relationship == "area_only":
                failures.append(f"{prefix} cannot retain area-only performance history")
            workload = str(contract.get("workload", ""))
            oracle = str(contract.get("oracle", ""))
            if not (QUANTIFIED_WORKLOAD_RE.search(workload) or QUANTIFIED_VALUE_RE.search(workload)):
                failures.append(f"{prefix}.workload must be quantified before retention")
            if not (QUANTIFIED_VALUE_RE.search(oracle) or COMPARATIVE_ORACLE_RE.search(oracle)):
                failures.append(f"{prefix}.oracle must contain a measurable numeric or comparative target")

    return failures, retained_count

def validate_performance_assessment(manifest: dict[str, Any]) -> list[str]:
    """Validate the internal principal-QA performance risk decision."""
    assessment = manifest.get("performance_assessment")
    if not isinstance(assessment, dict):
        return ["performance_assessment must be an object"]

    failures: list[str] = []
    if assessment.get("schema_version") != PERFORMANCE_SCHEMA_VERSION:
        failures.append(
            f"performance_assessment.schema_version must be '{PERFORMANCE_SCHEMA_VERSION}'"
        )

    decision = assessment.get("decision")
    if decision not in PERFORMANCE_DECISIONS:
        failures.append("performance_assessment.decision must be required, conditional, or not_required")

    risk_rating = assessment.get("risk_rating")
    if risk_rating not in PERFORMANCE_RISKS:
        failures.append("performance_assessment.risk_rating must be high, medium, or low")

    signal_review = assessment.get("signal_review")
    statuses: list[str] = []
    if not isinstance(signal_review, dict):
        failures.append("performance_assessment.signal_review must be an object")
    else:
        missing = [category for category in SIGNAL_CATEGORIES if category not in signal_review]
        extras = [category for category in signal_review if category not in SIGNAL_CATEGORIES]
        if missing or extras:
            failures.append(
                "performance_assessment.signal_review must contain exactly the seven canonical "
                f"risk categories; missing={missing}, extra={extras}"
            )
        for category in SIGNAL_CATEGORIES:
            review = signal_review.get(category)
            if not isinstance(review, dict):
                continue
            status = review.get("status")
            statuses.append(status)
            if status not in SIGNAL_STATUSES:
                failures.append(f"performance_assessment.signal_review.{category}.status is invalid")
            if not _nonempty_string(review.get("finding")):
                failures.append(f"performance_assessment.signal_review.{category}.finding is required")
            evidence_refs = review.get("evidence_refs")
            if (
                not isinstance(evidence_refs, list)
                or not evidence_refs
                or any(not _nonempty_string(item) for item in evidence_refs)
            ):
                failures.append(
                    f"performance_assessment.signal_review.{category}.evidence_refs "
                    "must cite at least one underlying source"
                )

    workload = assessment.get("workload_model")
    if not isinstance(workload, dict):
        failures.append("performance_assessment.workload_model must be an object")
        workload_text = ""
    else:
        missing = [field for field in WORKLOAD_FIELDS if not _nonempty_string(workload.get(field))]
        if missing:
            failures.append(
                f"performance_assessment.workload_model is missing concrete fields: {', '.join(missing)}"
            )
        workload_text = " ".join(str(workload.get(field, "")) for field in WORKLOAD_FIELDS)

    failures.extend(_controlled_list(assessment.get("metrics"), METRICS, "performance_assessment.metrics"))
    failures.extend(
        _controlled_list(assessment.get("test_types"), TEST_TYPES, "performance_assessment.test_types")
    )
    historical_failures, retained_historical_count = _validate_historical_contracts(
        assessment.get("historical_contracts")
    )
    failures.extend(historical_failures)

    oracle = assessment.get("oracle")
    oracle_status = None
    thresholds: list[str] = []
    if not isinstance(oracle, dict):
        failures.append("performance_assessment.oracle must be an object")
    else:
        oracle_status = oracle.get("status")
        if oracle_status not in ORACLE_STATUSES:
            failures.append("performance_assessment.oracle.status is invalid")
        if not _nonempty_string(oracle.get("source_ref")):
            failures.append("performance_assessment.oracle.source_ref must cite the decision source")
        raw_thresholds = oracle.get("thresholds")
        if not isinstance(raw_thresholds, list):
            failures.append("performance_assessment.oracle.thresholds must be a list")
        else:
            thresholds = raw_thresholds
            if any(not _nonempty_string(item) for item in thresholds):
                failures.append("performance_assessment.oracle.thresholds contains an empty threshold")

    performance_ac_ids = assessment.get("performance_ac_ids")
    if not isinstance(performance_ac_ids, list):
        failures.append("performance_assessment.performance_ac_ids must be a list")
        performance_ac_ids = []
    else:
        if any(not isinstance(item, str) or not AC_ID_RE.fullmatch(item) for item in performance_ac_ids):
            failures.append("performance_assessment.performance_ac_ids contains an invalid AC ID")
        if all(isinstance(item, str) for item in performance_ac_ids) and len(
            performance_ac_ids
        ) != len(set(performance_ac_ids)):
            failures.append("performance_assessment.performance_ac_ids must not contain duplicates")

    if not _nonempty_string(assessment.get("rationale")) or len(
        str(assessment.get("rationale", "")).strip()
    ) < 40:
        failures.append("performance_assessment.rationale must explain the evidence-based decision")

    metrics = assessment.get("metrics") if isinstance(assessment.get("metrics"), list) else []
    test_types = assessment.get("test_types") if isinstance(assessment.get("test_types"), list) else []
    present_count = statuses.count("present")
    unknown_count = statuses.count("unknown")

    if decision == "required":
        if risk_rating not in ("high", "medium"):
            failures.append("required performance testing must have high or medium risk")
        if present_count == 0:
            failures.append("required performance testing needs at least one present risk signal")
        if not metrics:
            failures.append("required performance testing needs explicit metrics")
        if not test_types:
            failures.append("required performance testing needs at least one test type")
        if oracle_status != "quantified":
            failures.append("required performance testing needs a quantified oracle")
        if (
            not thresholds
            or any(not isinstance(item, str) for item in thresholds)
            or any(
                not (
                    QUANTIFIED_VALUE_RE.search(item)
                    or COMPARATIVE_ORACLE_RE.search(item)
                )
                for item in thresholds
                if isinstance(item, str)
            )
        ):
            failures.append(
                "required performance thresholds must contain measurable numeric units or a "
                "source-backed comparative target"
            )
        if not performance_ac_ids:
            failures.append("required performance testing must declare Performance AC IDs")
        if not (QUANTIFIED_WORKLOAD_RE.search(workload_text) or QUANTIFIED_VALUE_RE.search(workload_text)):
            failures.append("required performance testing needs a quantified workload model")
    elif decision == "conditional":
        if risk_rating not in ("high", "medium"):
            failures.append("conditional performance testing must have high or medium risk")
        if present_count + unknown_count == 0:
            failures.append("conditional performance testing needs a present or unknown material signal")
        if oracle_status != "unresolved":
            failures.append("conditional performance testing must keep the oracle unresolved")
        if thresholds:
            failures.append("conditional performance testing cannot declare thresholds before resolution")
        if performance_ac_ids:
            failures.append(
                "conditional performance testing cannot declare Performance AC IDs until its oracle is resolved"
            )
    elif decision == "not_required":
        if risk_rating != "low":
            failures.append("not_required performance testing must have low risk")
        if any(status != "absent" for status in statuses):
            failures.append("not_required performance testing requires every reviewed signal to be absent")
        if metrics:
            failures.append("not_required performance testing must not declare performance metrics")
        if test_types:
            failures.append("not_required performance testing must not declare test types")
        if oracle_status != "not_applicable":
            failures.append("not_required performance testing must use a not_applicable oracle")
        if thresholds:
            failures.append("not_required performance testing must not declare thresholds")
        if performance_ac_ids:
            failures.append("not_required performance testing must not declare Performance AC IDs")

    if retained_historical_count and decision != "required":
        failures.append(
            "a retained same-mechanism or shared-execution-path historical performance contract "
            "requires decision=required and a visible Performance AC"
        )

    return failures


def _section_lines(text: str, target: str) -> list[str]:
    lines: list[str] = []
    current = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = HEADING_RE.fullmatch(line.strip())
        if heading:
            current = heading.group(1) == target
            continue
        if current and line.strip():
            lines.append(line)
    return lines


def validate_plan_alignment(manifest: dict[str, Any], text: str) -> list[str]:
    """Keep the internal decision aligned with visible ACs and scenarios."""
    assessment = manifest.get("performance_assessment")
    if not isinstance(assessment, dict):
        return ["performance assessment cannot be aligned because it is missing"]

    criteria = []
    for line in acceptance_lines(text):
        criterion = parse_ac_line(line)
        if criterion is not None:
            criteria.append(criterion)
    performance_criteria = [criterion for criterion in criteria if criterion["sphere"] == "Performance"]
    actual_ids = [criterion["id"] for criterion in performance_criteria]
    declared_ids = assessment.get("performance_ac_ids")
    declared_ids = declared_ids if isinstance(declared_ids, list) else []
    decision = assessment.get("decision")
    failures: list[str] = []

    if actual_ids != declared_ids:
        failures.append(
            "performance_assessment.performance_ac_ids must exactly match visible Performance ACs; "
            f"declared={declared_ids}, visible={actual_ids}"
        )

    if decision == "required" and not performance_criteria:
        failures.append(
            "performance assessment is required, so Acceptance Criteria must include a Performance AC"
        )
    if decision in ("conditional", "not_required") and performance_criteria:
        failures.append(
            f"performance assessment is {decision}, so no Performance AC may be emitted"
        )

    historical_contracts = assessment.get("historical_contracts")
    retained_contracts = [
        contract
        for contract in historical_contracts
        if isinstance(contract, dict)
        and contract.get("retained") is True
        and contract.get("relationship") in ("same_mechanism", "shared_execution_path")
    ] if isinstance(historical_contracts, list) else []
    reviewed_contract_keys = {
        str(contract.get("jira_key", "")).strip()
        for contract in historical_contracts
        if isinstance(contract, dict)
        and str(contract.get("jira_key", "")).strip()
    } if isinstance(historical_contracts, list) else set()
    historical_plan_lines = [
        *_section_lines(text, "Known Jira Bugs / Past Similar Tickets"),
        *_section_lines(text, "Regression Areas"),
    ]
    mentioned_performance_keys = {
        key
        for line in historical_plan_lines
        if HISTORICAL_PERFORMANCE_MENTION_RE.search(line)
        for key in PLAN_JIRA_KEY_RE.findall(line)
    }
    current_issue_keys = _jira_keys_in_value(manifest.get("issue"))
    unclassified_history = (
        mentioned_performance_keys - reviewed_contract_keys - current_issue_keys
    )
    for jira_key in sorted(unclassified_history):
        failures.append(
            f"historical performance Jira {jira_key} is mentioned in the plan but is missing "
            "from performance_assessment.historical_contracts; classify it as same_mechanism, "
            "shared_execution_path, or area_only before release"
        )
    for contract in retained_contracts:
        jira_key = str(contract.get("jira_key", "")).strip()
        if jira_key and not any(jira_key in criterion["evidence"] for criterion in performance_criteria):
            failures.append(
                f"retained historical performance contract {jira_key} must be cited in a visible "
                "Performance AC Evidence field"
            )

    scenario_lines = _section_lines(text, "Test Scenarios")
    for criterion in performance_criteria:
        if not QUANTIFIED_WORKLOAD_RE.search(criterion["given"]):
            failures.append(
                f"{criterion['id']} Performance Given must contain a quantified workload "
                "(for example topic count, user count, job count, or iterations)"
            )
        if not (
            QUANTIFIED_VALUE_RE.search(criterion["then"])
            or COMPARATIVE_ORACLE_RE.search(criterion["then"])
        ):
            failures.append(
                f"{criterion['id']} Performance Then must contain a measurable numeric or comparative oracle"
            )
        mapped = [
            line
            for line in scenario_lines
            if f"[{criterion['id']}]" in line or re.search(
                rf"\[(?:AC-\d{{2}},\s*)*{re.escape(criterion['id'])}(?:,\s*AC-\d{{2}})*\]",
                line,
            )
        ]
        if not mapped:
            failures.append(f"{criterion['id']} must map to a Test Scenarios bullet")
        elif not any(PERFORMANCE_SCENARIO_RE.search(line) for line in mapped):
            failures.append(
                f"{criterion['id']} must map to a performance/load/soak/concurrency/benchmark scenario"
            )

    if decision == "conditional":
        open_questions = _section_lines(text, "Open Questions")
        if not any(
            PERFORMANCE_QUESTION_RE.search(line) and "qa impact" in line.lower()
            for line in open_questions
        ):
            failures.append(
                "conditional performance assessment requires an Open Questions bullet that resolves "
                "the workload/SLA/baseline decision and states QA impact"
            )

    return failures
