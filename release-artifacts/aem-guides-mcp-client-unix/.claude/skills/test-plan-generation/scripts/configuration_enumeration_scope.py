"""Validate configuration-driven enumeration coverage.

Configuration-backed lists are extensibility contracts, not snapshots of the
entries visible in one environment.  This module makes the recurring coverage
dimensions explicit and requires every one to be mapped to an acceptance
criterion, an open question, or a justified out-of-scope decision.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SCHEMA_VERSION = "aem-guides-configuration-enumeration-scope-v1"
DATA_SCHEMA_VERSION = "aem-guides-configuration-enumeration-anchors-v1"
DISPOSITIONS = ("COVERED_BY_AC", "OPEN_QUESTION", "OUT_OF_SCOPE")
REQUIRED_DIMENSIONS = (
    "authoritative_source",
    "overlay_precedence",
    "dynamic_entry",
    "mapped_label",
    "raw_or_default_fallback",
    "applicability",
    "activation_reload",
    "unrelated_entry_preservation",
    "invalid_entry",
    "duplicate_entry",
    "removal",
    "upgrade",
    "rollback",
)

def _load_dimension_anchors():
    path = Path(__file__).with_name("data") / "configuration_enumeration_scope.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != DATA_SCHEMA_VERSION:
        raise ValueError(
            f"configuration enumeration anchor schema must be {DATA_SCHEMA_VERSION}"
        )
    anchors = data.get("dimension_semantic_anchors")
    if not isinstance(anchors, dict) or set(anchors) != set(REQUIRED_DIMENSIONS):
        raise ValueError(
            "configuration enumeration anchors must match every required dimension"
        )
    if any(
        not isinstance(values, list)
        or not values
        or not all(isinstance(value, str) and value.strip() for value in values)
        for values in anchors.values()
    ):
        raise ValueError("every configuration enumeration dimension needs string anchors")
    return anchors


# Vocabulary is data, not gate logic. A future configured provider, format, action,
# field, or other enumerated choice extends the catalog without changing Python.
DIMENSION_SEMANTIC_ANCHORS = _load_dimension_anchors()

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_AC_LINE_RE = re.compile(r"^\s*-\s*(AC-\d{2})\b(?P<text>.*)$", re.MULTILINE)
_OQ_LINE_RE = re.compile(r"^\s*-\s*(OQ-\d{2})\b(?P<text>.*)$", re.MULTILINE)


def _present(entry, key):
    value = entry.get(key)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _normalise_text(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _contains_term(target, term):
    normalized_target = _normalise_text(target)
    normalized_term = _normalise_text(term)
    if not normalized_term:
        return False
    return f" {normalized_term} " in f" {normalized_target} "


def _index_semantic_targets(plan_text):
    ac_targets = {}
    for match in _AC_LINE_RE.finditer(str(plan_text or "")):
        text = re.split(
            r"\|\s*Evidence\s*:", match.group("text"), maxsplit=1, flags=re.I
        )[0]
        ac_targets.setdefault(match.group(1), text.strip())
    oq_targets = {
        match.group(1): match.group("text").strip()
        for match in _OQ_LINE_RE.finditer(str(plan_text or ""))
    }
    return ac_targets, oq_targets


def _trace_terms(value, field, tag):
    if not isinstance(value, list):
        return [], [f"{tag}.{field} must be a string list"]
    problems = []
    terms = []
    seen = set()
    for index, item in enumerate(value):
        term = str(item).strip() if isinstance(item, str) else ""
        if not term or "\n" in term or "\r" in term:
            problems.append(f"{tag}.{field}[{index}] must be a non-empty phrase")
            continue
        normalized = _normalise_text(term)
        if normalized in seen:
            problems.append(f"{tag}.{field}[{index}] duplicates phrase {term!r}")
            continue
        seen.add(normalized)
        terms.append(term)
    return terms, problems


def _dimension_bound(dimension, terms):
    anchors = DIMENSION_SEMANTIC_ANCHORS[dimension]
    return any(
        _contains_term(term, anchor)
        for term in terms
        for anchor in anchors
    )


def _semantic_target(entry, ac_targets, oq_targets):
    disposition = entry.get("disposition")
    if disposition == "COVERED_BY_AC":
        ref = str(entry.get("ac_ref", "")).strip()
        return ac_targets.get(ref), f"referenced AC {ref!r}"
    if disposition == "OPEN_QUESTION":
        ref = str(entry.get("open_question_ref", "")).strip()
        return oq_targets.get(ref), f"referenced Open Question {ref!r}"
    if disposition == "OUT_OF_SCOPE":
        return str(entry.get("reason", "")).strip(), "out-of-scope reason"
    return None, "invalid disposition"


def _validate_semantic_trace(entry, dimension, tag, *, ac_targets, oq_targets):
    trace = entry.get("semantic_trace")
    if not isinstance(trace, dict):
        return [f"{tag}.semantic_trace must be an object"]

    required_all, all_problems = _trace_terms(
        trace.get("required_terms_all"), "required_terms_all", f"{tag}.semantic_trace"
    )
    required_any, any_problems = _trace_terms(
        trace.get("required_terms_any"), "required_terms_any", f"{tag}.semantic_trace"
    )
    problems = all_problems + any_problems
    terms = required_all + required_any
    if not terms:
        problems.append(
            f"{tag}.semantic_trace must declare at least one required phrase"
        )
        return problems
    if not _dimension_bound(dimension, terms):
        problems.append(
            f"{tag}.semantic_trace is not bound to dimension {dimension!r}"
        )

    target, target_label = _semantic_target(entry, ac_targets, oq_targets)
    if not target:
        problems.append(f"{tag}.semantic_trace cannot find {target_label} in plan text")
        return problems

    for term in required_all:
        if not _contains_term(target, term):
            problems.append(
                f"{tag}.semantic_trace required_terms_all phrase {term!r} "
                f"is absent from {target_label}"
            )
    if required_any and not any(_contains_term(target, term) for term in required_any):
        problems.append(
            f"{tag}.semantic_trace requires at least one required_terms_any phrase "
            f"in {target_label}: {required_any!r}"
        )
    return problems


def _validate_disposition(entry, tag, *, ac_ids, open_question_ids):
    problems = []
    disposition = entry.get("disposition")
    if disposition not in DISPOSITIONS:
        return [f"{tag}.disposition must be one of {DISPOSITIONS}"]

    if disposition == "COVERED_BY_AC":
        ref = str(entry.get("ac_ref", "")).strip()
        if not ref or (ac_ids is not None and ref not in ac_ids):
            problems.append(f"{tag}: COVERED_BY_AC requires a valid ac_ref")
        if _present(entry, "open_question_ref") or _present(entry, "reason"):
            problems.append(
                f"{tag}: COVERED_BY_AC must not retain open_question_ref or reason"
            )
    elif disposition == "OPEN_QUESTION":
        ref = str(entry.get("open_question_ref", "")).strip()
        if not ref or (open_question_ids is not None and ref not in open_question_ids):
            problems.append(
                f"{tag}: OPEN_QUESTION requires a valid open_question_ref"
            )
        if _present(entry, "ac_ref") or _present(entry, "reason"):
            problems.append(
                f"{tag}: OPEN_QUESTION must not retain ac_ref or reason"
            )
    else:
        if not str(entry.get("reason", "")).strip():
            problems.append(f"{tag}: OUT_OF_SCOPE requires a non-empty reason")
        if _present(entry, "ac_ref") or _present(entry, "open_question_ref"):
            problems.append(
                f"{tag}: OUT_OF_SCOPE must not retain ac_ref or open_question_ref"
            )
    return problems


def validate_configuration_enumeration_scope(
    block, *, ac_ids=None, open_question_ids=None, plan_text=""
):
    """Return validation failures for a configuration enumeration block.

    Expected shape::

        {
          "schema_version": "aem-guides-configuration-enumeration-scope-v1",
          "construct_type": "conditional-attribute",
          "dimensions": [
            {
              "dimension": "dynamic_entry",
              "disposition": "COVERED_BY_AC",
              "ac_ref": "AC-04",
              "semantic_trace": {
                "required_terms_all": ["new configured entry"],
                "required_terms_any": ["without a product code change", "runtime"]
              }
            }
          ]
        }

    Identifier membership and semantic relevance are separate checks.  The
    caller supplies parsed identifier sets, while this validator indexes the
    canonical AC and Open Question lines in ``plan_text`` and verifies the
    entry's explicit semantic trace against the selected target.  For an
    out-of-scope disposition, the reason itself is the semantic target.
    """
    known_ac_ids = None if ac_ids is None else set(ac_ids)
    known_oq_ids = None if open_question_ids is None else set(open_question_ids)
    ac_targets, oq_targets = _index_semantic_targets(plan_text)
    if not isinstance(block, dict):
        return ["configuration_enumeration_scope must be an object"]

    problems = []
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(
            "configuration_enumeration_scope.schema_version must be "
            + SCHEMA_VERSION
        )

    construct_type = str(block.get("construct_type", "")).strip()
    if not _SLUG_RE.fullmatch(construct_type):
        problems.append(
            "configuration_enumeration_scope.construct_type must be a stable "
            "lowercase slug"
        )

    dimensions = block.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        return problems + [
            "configuration_enumeration_scope.dimensions must be a non-empty list"
        ]

    seen = set()
    for index, entry in enumerate(dimensions):
        tag = f"configuration_enumeration_scope.dimensions[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{tag} must be an object")
            continue
        dimension = str(entry.get("dimension", "")).strip()
        if dimension not in REQUIRED_DIMENSIONS:
            problems.append(f"{tag}.dimension is unknown: {dimension!r}")
            continue
        if dimension in seen:
            problems.append(f"{tag} duplicates dimension {dimension!r}")
        seen.add(dimension)
        problems.extend(
            _validate_disposition(
                entry,
                tag,
                ac_ids=known_ac_ids,
                open_question_ids=known_oq_ids,
            )
        )
        problems.extend(
            _validate_semantic_trace(
                entry,
                dimension,
                tag,
                ac_targets=ac_targets,
                oq_targets=oq_targets,
            )
        )

    missing = [dimension for dimension in REQUIRED_DIMENSIONS if dimension not in seen]
    if missing:
        problems.append(
            "missing configuration enumeration dimension disposition(s): "
            + repr(missing)
        )
    return problems


def _valid_fixture():
    dimensions = []
    plan_lines = []
    ac_ids = set()
    open_question_ids = set()
    for index, dimension in enumerate(REQUIRED_DIMENSIONS):
        phrase = DIMENSION_SEMANTIC_ANCHORS[dimension][0]
        semantic_trace = {
            "required_terms_all": [phrase] if index % 2 == 0 else [],
            "required_terms_any": [] if index % 2 == 0 else [phrase],
        }
        if index % 3 == 0:
            ref = f"AC-{index + 1:02d}"
            entry = {
                "dimension": dimension,
                "disposition": "COVERED_BY_AC",
                "ac_ref": ref,
                "semantic_trace": semantic_trace,
            }
            ac_ids.add(ref)
            plan_lines.append(
                f"- {ref} [Proposed]: (Basic) Given {phrase} is configured "
                f"| When a tester validates it | Then {phrase} is applied "
                "| Evidence: self-test."
            )
        elif index % 3 == 1:
            ref = f"OQ-{index + 1:02d}"
            entry = {
                "dimension": dimension,
                "disposition": "OPEN_QUESTION",
                "open_question_ref": ref,
                "semantic_trace": semantic_trace,
            }
            open_question_ids.add(ref)
            plan_lines.append(
                f"- {ref}: What is the contract for {phrase}? "
                "QA impact: The answer changes the expected result."
            )
        else:
            entry = {
                "dimension": dimension,
                "disposition": "OUT_OF_SCOPE",
                "reason": f"The {phrase} contract is outside this ticket.",
                "semantic_trace": semantic_trace,
            }
        dimensions.append(entry)
    block = {
        "schema_version": SCHEMA_VERSION,
        "construct_type": "conditional-attribute",
        "dimensions": dimensions,
    }
    arguments = {
        "ac_ids": ac_ids,
        "open_question_ids": open_question_ids,
        "plan_text": "\n".join(plan_lines),
    }
    return block, arguments


def _valid_block():
    return _valid_fixture()[0]


def run_self_tests():
    """Return a list of failed self-test descriptions."""
    failures = []

    valid, known = _valid_fixture()
    if validate_configuration_enumeration_scope(valid, **known):
        failures.append("valid mixed-disposition block was rejected")

    missing, known = _valid_fixture()
    missing["dimensions"] = missing["dimensions"][:-1]
    if not any(
        "missing configuration enumeration dimension" in problem
        for problem in validate_configuration_enumeration_scope(missing, **known)
    ):
        failures.append("missing required dimension was not rejected")

    bad_ac, known = _valid_fixture()
    covered = next(
        item
        for item in bad_ac["dimensions"]
        if item["disposition"] == "COVERED_BY_AC"
    )
    covered["ac_ref"] = "AC-99"
    if not any(
        "valid ac_ref" in problem
        for problem in validate_configuration_enumeration_scope(bad_ac, **known)
    ):
        failures.append("unknown AC reference was not rejected")

    bad_oq, known = _valid_fixture()
    question = next(
        item
        for item in bad_oq["dimensions"]
        if item["disposition"] == "OPEN_QUESTION"
    )
    question["open_question_ref"] = "OQ-99"
    if not any(
        "valid open_question_ref" in problem
        for problem in validate_configuration_enumeration_scope(bad_oq, **known)
    ):
        failures.append("unknown Open Question reference was not rejected")

    duplicate, known = _valid_fixture()
    duplicate["dimensions"].append(dict(duplicate["dimensions"][0]))
    if not any(
        "duplicates dimension" in problem
        for problem in validate_configuration_enumeration_scope(duplicate, **known)
    ):
        failures.append("duplicate dimension was not rejected")

    unknown, known = _valid_fixture()
    unknown["dimensions"][0]["dimension"] = "current-default-snapshot"
    if not any(
        ".dimension is unknown" in problem
        for problem in validate_configuration_enumeration_scope(unknown, **known)
    ):
        failures.append("unknown dimension was not rejected")

    unjustified, known = _valid_fixture()
    excluded = next(
        item
        for item in unjustified["dimensions"]
        if item["disposition"] == "OUT_OF_SCOPE"
    )
    excluded["reason"] = ""
    if not any(
        "OUT_OF_SCOPE requires a non-empty reason" in problem
        for problem in validate_configuration_enumeration_scope(unjustified, **known)
    ):
        failures.append("unjustified out-of-scope disposition was not rejected")

    stale, known = _valid_fixture()
    stale["dimensions"][0]["open_question_ref"] = next(
        iter(known["open_question_ids"])
    )
    if not any(
        "must not retain open_question_ref" in problem
        for problem in validate_configuration_enumeration_scope(stale, **known)
    ):
        failures.append("stale cross-disposition reference was not rejected")

    missing_trace, known = _valid_fixture()
    del missing_trace["dimensions"][0]["semantic_trace"]
    if not any(
        "semantic_trace must be an object" in problem
        for problem in validate_configuration_enumeration_scope(
            missing_trace, **known
        )
    ):
        failures.append("missing semantic trace was not rejected")

    unrelated_ac, known = _valid_fixture()
    covered = next(
        item
        for item in unrelated_ac["dimensions"]
        if item["disposition"] == "COVERED_BY_AC"
    )
    covered["ac_ref"] = "AC-99"
    known["ac_ids"].add("AC-99")
    known["plan_text"] += (
        "\n- AC-99 [Proposed]: (Basic) Given a friendly name is configured "
        "| When the label opens | Then the friendly name is displayed "
        "| Evidence: self-test."
    )
    if not any(
        "required_terms_all phrase" in problem and "AC-99" in problem
        for problem in validate_configuration_enumeration_scope(
            unrelated_ac, **known
        )
    ):
        failures.append("semantically unrelated AC mapping was not rejected")

    unrelated_oq, known = _valid_fixture()
    question = next(
        item
        for item in unrelated_oq["dimensions"]
        if item["disposition"] == "OPEN_QUESTION"
    )
    question["open_question_ref"] = "OQ-99"
    known["open_question_ids"].add("OQ-99")
    known["plan_text"] += (
        "\n- OQ-99: Which build upgrade is supported? "
        "QA impact: The answer changes the version matrix."
    )
    if not any(
        "required_terms_any phrase" in problem and "OQ-99" in problem
        for problem in validate_configuration_enumeration_scope(
            unrelated_oq, **known
        )
    ):
        failures.append("semantically unrelated Open Question mapping was not rejected")

    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate the configuration-enumeration scope module."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run deterministic built-in validator tests",
    )
    args = parser.parse_args(argv)
    if not args.self_test:
        parser.error("the standalone command currently requires --self-test")
    failures = run_self_tests()
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("configuration_enumeration_scope self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
