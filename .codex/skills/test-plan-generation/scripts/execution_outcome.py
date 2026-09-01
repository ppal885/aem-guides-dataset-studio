"""Validate and normalize real QE execution outcomes (UACLOOP-01).

The outcome block is optional.  When present, it records which acceptance
criteria found defects and which shipped defects escaped the plan.  Outcomes
can advise governed learning, but this module never authors acceptance
criteria and never promotes a discovery probe.

Generic and stdlib-only.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path


BLOCK_NAME = "execution_outcome"
TRUSTED_SOURCES = frozenset({"HUMAN", "CI"})
EXECUTION_STATES = frozenset({"PASS", "FAIL", "NOT_RUN"})
CANDIDATE_STATE = "CANDIDATE"
AC_ID_RE = re.compile(r"^AC-[0-9]{2,}$")


def _pipeline_stages() -> frozenset[str]:
    """Load the canonical stage vocabulary instead of maintaining a copy."""
    module_path = Path(__file__).with_name("human_feedback_delta.py")
    spec = importlib.util.spec_from_file_location(
        "execution_outcome_human_feedback_delta", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load pipeline-stage vocabulary from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return frozenset(module.PIPELINE_STAGES)


PIPELINE_STAGES = _pipeline_stages()


def _record(payload):
    if not isinstance(payload, dict):
        return None
    if BLOCK_NAME in payload:
        return payload.get(BLOCK_NAME)
    if any(
        key in payload
        for key in ("plan_key", "acs", "escapes", "source", "recorded_at")
    ):
        return payload
    return None


def is_present(payload) -> bool:
    """Return true for a direct record or an explicitly supplied manifest block."""
    return isinstance(payload, dict) and (
        BLOCK_NAME in payload
        or any(
            key in payload
            for key in ("plan_key", "acs", "escapes", "source", "recorded_at")
        )
    )


def _nonempty_string(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_recorded_at(value) -> bool:
    if not _nonempty_string(value):
        return False
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate(payload) -> list[str]:
    """Validate a direct execution-outcome record or a containing manifest."""
    if not is_present(payload):
        return []

    record = _record(payload)
    if not isinstance(record, dict):
        return ["execution_outcome must be an object"]

    problems: list[str] = []
    if not _nonempty_string(record.get("plan_key")):
        problems.append("execution_outcome.plan_key must be a non-empty string")

    source = record.get("source")
    if source not in TRUSTED_SOURCES:
        problems.append(
            "execution_outcome.source must be HUMAN or trusted CI; MODEL/AI "
            "cannot create execution outcomes or escapes"
        )

    if not _valid_recorded_at(record.get("recorded_at")):
        problems.append(
            "execution_outcome.recorded_at must be a timezone-aware ISO-8601 timestamp"
        )

    acs = record.get("acs", [])
    if not isinstance(acs, list):
        problems.append("execution_outcome.acs must be a list")
    else:
        seen_ac_ids: set[str] = set()
        for index, ac in enumerate(acs):
            tag = f"execution_outcome.acs[{index}]"
            if not isinstance(ac, dict):
                problems.append(f"{tag} must be an object")
                continue
            ac_id = ac.get("ac_id")
            if not _nonempty_string(ac_id) or not AC_ID_RE.fullmatch(ac_id.strip()):
                problems.append(f"{tag}.ac_id must use the canonical AC-NN form")
            elif ac_id.strip() in seen_ac_ids:
                problems.append(f"{tag}.ac_id '{ac_id.strip()}' is duplicated")
            else:
                seen_ac_ids.add(ac_id.strip())

            execution = ac.get("execution")
            if execution not in EXECUTION_STATES:
                problems.append(
                    f"{tag}.execution must be one of {', '.join(sorted(EXECUTION_STATES))}"
                )

            found_defect = ac.get("found_defect")
            if not isinstance(found_defect, bool):
                problems.append(f"{tag}.found_defect must be a boolean")

            defect_ref = ac.get("defect_ref", "")
            if not isinstance(defect_ref, str):
                problems.append(f"{tag}.defect_ref must be a string")
            elif found_defect is True and not defect_ref.strip():
                problems.append(
                    f"{tag}.defect_ref is required when found_defect=true"
                )

            if "coverage_dimension" in ac and not _nonempty_string(
                ac.get("coverage_dimension")
            ):
                problems.append(
                    f"{tag}.coverage_dimension must be a non-empty string when supplied"
                )

    escapes = record.get("escapes", [])
    if not isinstance(escapes, list):
        problems.append("execution_outcome.escapes must be a list")
    else:
        seen_defect_refs: set[str] = set()
        for index, escape in enumerate(escapes):
            tag = f"execution_outcome.escapes[{index}]"
            if not isinstance(escape, dict):
                problems.append(f"{tag} must be an object")
                continue

            defect_ref = escape.get("defect_ref")
            if not _nonempty_string(defect_ref):
                problems.append(f"{tag}.defect_ref must be a non-empty string")
            elif defect_ref.strip() in seen_defect_refs:
                problems.append(
                    f"{tag}.defect_ref '{defect_ref.strip()}' is duplicated"
                )
            else:
                seen_defect_refs.add(defect_ref.strip())

            if not _nonempty_string(escape.get("summary")):
                problems.append(f"{tag}.summary must be a non-empty string")

            if not _nonempty_string(escape.get("should_have_been_covered_by")):
                problems.append(
                    f"{tag}.should_have_been_covered_by must name a coverage axis/dimension"
                )

            stage = escape.get("first_missed_stage")
            if not _nonempty_string(stage):
                problems.append(
                    f"{tag}.first_missed_stage is required so the lesson targets "
                    "the first failed pipeline stage"
                )
            elif stage.strip() not in PIPELINE_STAGES:
                problems.append(
                    f"{tag}.first_missed_stage '{stage.strip()}' must be one of "
                    f"{', '.join(sorted(PIPELINE_STAGES))}"
                )

    return problems


def _stable_probe_id(plan_key: str, defect_ref: str) -> str:
    digest = hashlib.sha256(
        f"{plan_key}\x1f{defect_ref}".encode("utf-8")
    ).hexdigest()[:16]
    return f"execution-escape-{digest}"


def to_candidate_miss_probes(payload) -> list[dict]:
    """Convert Human-confirmed escapes into governed CANDIDATE probe inputs."""
    problems = validate(payload)
    if problems:
        raise ValueError("; ".join(problems))
    if not is_present(payload):
        return []

    record = _record(payload)
    if record.get("source") != "HUMAN":
        return []

    plan_key = record["plan_key"].strip()
    probes = []
    for escape in record.get("escapes", []):
        defect_ref = escape["defect_ref"].strip()
        dimension = escape["should_have_been_covered_by"].strip()
        stage = escape["first_missed_stage"].strip()
        probes.append(
            {
                "schema_version": "aem-guides-uacdiscover-miss-probe-input-v1",
                "probe_id": _stable_probe_id(plan_key, defect_ref),
                "probe_type": "EXECUTION_ESCAPE",
                "plan_key": plan_key,
                "defect_ref": defect_ref,
                "summary": escape["summary"].strip(),
                "coverage_dimension": dimension,
                "should_have_been_covered_by": dimension,
                "first_failed_stage": stage,
                "source": "HUMAN",
                "promotion_state": CANDIDATE_STATE,
                "auto_promote": False,
                "auto_author_ac": False,
            }
        )
    return probes


def _resolve_ac_dimension(record: dict, ac: dict, ac_dimension_map: dict) -> str:
    inline = ac.get("coverage_dimension")
    if _nonempty_string(inline):
        return inline.strip()
    plan_key = str(record.get("plan_key", "")).strip()
    ac_id = str(ac.get("ac_id", "")).strip()
    for lookup_key in ((plan_key, ac_id), f"{plan_key}:{ac_id}", ac_id):
        value = ac_dimension_map.get(lookup_key)
        if _nonempty_string(value):
            return value.strip()
    return ""


def dimension_priority_signals(
    payloads,
    ac_dimension_map: dict | None = None,
    minimum_distinct_defects: int = 2,
) -> list[dict]:
    """Return deterministic priority signals; never create or change an AC."""
    if not isinstance(minimum_distinct_defects, int) or minimum_distinct_defects < 2:
        raise ValueError("minimum_distinct_defects must be an integer >= 2")
    mapping = ac_dimension_map or {}
    if not isinstance(mapping, dict):
        raise ValueError("ac_dimension_map must be a dictionary")

    grouped: dict[str, dict[str, set[str]]] = {}
    for payload in payloads:
        problems = validate(payload)
        if problems:
            raise ValueError("; ".join(problems))
        if not is_present(payload):
            continue
        record = _record(payload)
        for ac in record.get("acs", []):
            if ac.get("found_defect") is not True:
                continue
            dimension = _resolve_ac_dimension(record, ac, mapping)
            if not dimension:
                continue
            bucket = grouped.setdefault(
                dimension, {"defect_refs": set(), "ac_ids": set()}
            )
            bucket["defect_refs"].add(ac["defect_ref"].strip())
            bucket["ac_ids"].add(ac["ac_id"].strip())

    signals = []
    for dimension in sorted(grouped):
        defect_refs = sorted(grouped[dimension]["defect_refs"])
        if len(defect_refs) < minimum_distinct_defects:
            continue
        signals.append(
            {
                "coverage_dimension": dimension,
                "distinct_defect_count": len(defect_refs),
                "defect_refs": defect_refs,
                "ac_ids": sorted(grouped[dimension]["ac_ids"]),
                "priority_action": "RAISE",
                "source": "EXECUTION_OUTCOME",
                "auto_author_ac": False,
            }
        )
    return signals


def summarize(payload) -> str:
    if not is_present(payload):
        return "ExecutionOutcome: NOT_PRESENT (backward-compatible)"
    problems = validate(payload)
    record = _record(payload)
    ac_count = len(record.get("acs", [])) if isinstance(record, dict) and isinstance(record.get("acs", []), list) else 0
    escape_count = len(record.get("escapes", [])) if isinstance(record, dict) and isinstance(record.get("escapes", []), list) else 0
    status = "CLEAN" if not problems else "ISSUES"
    lines = [
        f"ExecutionOutcome: {status} ({ac_count} AC outcome(s), {escape_count} escape(s))"
    ]
    lines.extend(f"  {problem}" for problem in problems)
    return "\n".join(lines)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate optional QE execution outcomes (UACLOOP-01)"
    )
    parser.add_argument("--manifest")
    parser.add_argument(
        "--emit-candidate-probes",
        action="store_true",
        help="Emit governed Human CANDIDATE miss-probe inputs as JSON",
    )
    args = parser.parse_args()

    payload = {}
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    problems = validate(payload)
    if args.emit_candidate_probes and not problems:
        print(json.dumps(to_candidate_miss_probes(payload), indent=2, sort_keys=True))
    else:
        print(summarize(payload))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
