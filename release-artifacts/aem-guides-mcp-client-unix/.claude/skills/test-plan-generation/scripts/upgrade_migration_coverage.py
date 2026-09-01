"""Signal-activated upgrade and migration test-coverage gate.

``temporal_evidence.py`` decides whether evidence applies to a product version.
This gate has a different responsibility: when the current ticket or evidence
describes an upgrade or migration operation, require an explicit test-coverage
ledger for its starting state, execution, resulting state, and rollback policy.

Plans without an upgrade or migration signal remain backward-compatible.  The
gate validates dimension coverage and traceability only; existing AC and Open
Question validators continue to own wording and presentation rules.

Generic only.  Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


PREFIX = "MIGRATION GATE:"
SCHEMA_VERSION = "aem-guides-upgrade-migration-coverage-v1"
BLOCK_NAME = "upgrade_migration_coverage"
DIMENSIONS = (
    "PRE_STATE",
    "MIGRATION_EXECUTION",
    "POST_STATE_AND_MIXED",
    "ROLLBACK_OR_IRREVERSIBILITY",
)
DISPOSITIONS = {"COVERED_BY_AC", "OPEN_QUESTION", "NOT_APPLICABLE"}
OPEN_QUESTION_DIMENSIONS = {"PRE_STATE", "ROLLBACK_OR_IRREVERSIBILITY"}

ACTIVATION_PATTERNS = (
    (
        "VERSION_UPGRADE",
        re.compile(
            r"\b(?:version|release|service\s*pack|build|installation|instance)\b"
            r".{0,45}\bupgrad(?:e|ed|es|ing)\b|"
            r"\bupgrad(?:e|ed|es|ing)\b.{0,70}"
            r"\b(?:version|release|service\s*pack|build|installation|instance|aem\s+guides)\b|"
            r"\b(?:before|after|during|through|following)\s+(?:an?\s+)?upgrad(?:e|ing)\b|"
            r"\bupgrade\s+(?:path|operation|process|workflow)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "DATA_OR_SCHEMA_MIGRATION",
        re.compile(
            r"\b(?:data|schema|repository|stored\s+(?:content|data)|"
            r"configuration|config(?:uration)?\s+format)\s+migrat(?:e|ed|es|ing|ion)\b|"
            r"\bmigrat(?:e|ed|es|ing|ion)\b.{0,65}"
            r"\b(?:data|schema|repository|stored\s+(?:content|data)|"
            r"configuration|config(?:uration)?\s+format)\b|"
            r"\bmigration\s+(?:job|task|script|utility|service|operation|workflow)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "NON_UUID_TO_UUID",
        re.compile(
            r"\bnon[-_\s]?uuid\b.{0,45}(?:->|=>|\bto\b|\binto\b)"
            r".{0,30}\buuid\b|"
            r"\b(?:legacy|non[-_\s]?uuid)\s+(?:id|identifier)s?\b.{0,45}"
            r"\buuid\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "ON_PREM_TO_CLOUD",
        re.compile(
            r"\bon[-_\s]?prem(?:ise)?\b.{0,55}(?:->|=>|\bto\b|\binto\b)"
            r".{0,35}\bcloud\b|"
            r"\bmigrat(?:e|ed|es|ing|ion)\b.{0,45}\bfrom\s+on[-_\s]?prem(?:ise)?\b"
            r".{0,45}\bto\s+(?:the\s+)?cloud\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "COMPATIBILITY_BOUNDARY",
        re.compile(
            r"\b(?:backward|backwards|forward|forwards)[-_\s]+compatib(?:ility|le)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "FIX_VERSION_FORMAT_BOUNDARY",
        re.compile(
            r"\bfix[-_\s]?version\b.{0,120}"
            r"\b(?:stored|persisted)\s+(?:data|content|configuration|config)\b"
            r".{0,75}\b(?:format|schema|representation)\b|"
            r"\bfix[-_\s]?version\b.{0,120}"
            r"\b(?:data|configuration|config|schema)\s+format\b.{0,55}"
            r"\b(?:change|changes|changed|convert|migration)\b|"
            r"\b(?:stored|persisted)\s+(?:data|content|configuration|config)\b"
            r".{0,75}\b(?:format|schema|representation)\b.{0,120}"
            r"\bfix[-_\s]?version\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)

MIXED_STATE_PATTERNS = (
    (
        "NON_UUID_TO_UUID",
        ACTIVATION_PATTERNS[2][1],
    ),
    (
        "PARTIAL_OR_MIXED_STATE",
        re.compile(
            r"\bpartial(?:ly)?\s+(?:migrat(?:ed|ion)|upgrad(?:ed|e))\b|"
            r"\bmixed[-_\s]+(?:state|format|version|identifier)s?\b|"
            r"\b(?:old|legacy|source)\b.{0,65}\b(?:new|migrated|target)\b"
            r".{0,65}\b(?:coexist|co-exist|alongside|same\s+(?:repository|system|deployment))\b|"
            r"\b(?:old|legacy|source)\s+and\s+(?:new|migrated|target)\b"
            r".{0,65}\b(?:coexist|co-exist|alongside|together)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "STAGED_OR_INTERRUPTIBLE_MIGRATION",
        re.compile(
            r"\b(?:rolling|staged|incremental|batch|online)\s+"
            r"(?:upgrade|migration)\b|"
            r"\b(?:upgrade|migration)\b.{0,65}"
            r"\b(?:interrupt(?:ed|ion)?|resume|resumable|checkpoint)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)

ATOMIC_MIGRATION_RE = re.compile(
    r"\b(?:atomic|all[-_\s]?or[-_\s]?nothing|single\s+transaction)\b"
    r".{0,80}\b(?:upgrade|migration|conversion)\b|"
    r"\b(?:upgrade|migration|conversion)\b.{0,80}"
    r"\b(?:atomic|all[-_\s]?or[-_\s]?nothing|no\s+(?:partial|mixed)\s+state)\b",
    re.IGNORECASE | re.DOTALL,
)

_IGNORED_MANIFEST_KEYS = {
    BLOCK_NAME,
    "security_coverage",
    "localization_coverage",
    "block_waivers",
}
_MIXED_STATE_FLAG_KEYS = {
    "mixed_state_possible",
    "partial_migration_possible",
    "old_and_new_can_coexist",
    "rolling_upgrade",
}
_FIX_VERSION_KEYS = {"fix_version", "fix_versions"}

OLD_STATE_RE = re.compile(
    r"\b(?:old|legacy|source\s+(?:format|version|release)|"
    r"pre[-_\s]?(?:upgrade|migration)|before\s+(?:the\s+)?(?:upgrade|migration)|"
    r"non[-_\s]?uuid|on[-_\s]?prem(?:ise)?)\b",
    re.IGNORECASE,
)
AUTHORED_OR_STORED_RE = re.compile(
    r"\b(?:author(?:ed|ing)?|stor(?:e|ed|ing)|persist(?:ed|ing)?|"
    r"sav(?:e|ed|ing)|creat(?:e|ed|ing)|existing|repository)\b",
    re.IGNORECASE,
)
MIGRATABLE_INPUT_RE = re.compile(
    r"\b(?:content|data|records?|assets?|topics?|maps?|identifiers?|ids?|"
    r"configuration|config|schema|properties|metadata)\b",
    re.IGNORECASE,
)

OPERATION_RE = re.compile(
    r"\b(?:upgrad(?:e|ed|es|ing)|migrat(?:e|ed|es|ing|ion)|"
    r"convert(?:ed|s|ing)?|conversion)\b",
    re.IGNORECASE,
)
OPERATION_RUN_RE = re.compile(
    r"\b(?:run|runs|running|execute|executes|executed|start|starts|started|"
    r"trigger|triggers|triggered|invoke|invokes|invoked|perform|performs|performed)\b",
    re.IGNORECASE,
)
OPERATION_COMPLETE_RE = re.compile(
    r"\b(?:complete|completes|completed|finish|finishes|finished|"
    r"succeed|succeeds|succeeded|successful|terminal\s+success)\b",
    re.IGNORECASE,
)
REPEAT_POLICY_RE = re.compile(
    r"\b(?:idempotent|rerun|reruns|rerunnable|re-run|re-runs|re-runnable|"
    r"retry|retries|resume|resumes|resumable|repeat|repeated|repeatable|"
    r"one[-_\s]?shot|one[-_\s]?time|exactly[-_\s]?once|runs?\s+once|"
    r"cannot\s+be\s+(?:rerun|re-run|repeated)|not\s+(?:rerunnable|repeatable))\b",
    re.IGNORECASE,
)
FAILURE_RE = re.compile(
    r"\b(?:fail|fails|failed|failure|error|exception|abort|aborted)\b",
    re.IGNORECASE,
)
FAILURE_REPORT_RE = re.compile(
    r"\b(?:report|reports|reported|log|logs|logged|message|status|"
    r"diagnostic|notification|result|reason)\b",
    re.IGNORECASE,
)

POST_STATE_RE = re.compile(
    r"\b(?:migrated|converted|post[-_\s]?(?:upgrade|migration)|"
    r"after\s+(?:the\s+)?(?:upgrade|migration)|target\s+(?:format|version|release)|"
    r"new\s+(?:format|version|schema|identifier)|uuid)\b",
    re.IGNORECASE,
)
POST_RESULT_RE = re.compile(
    r"\b(?:content|data|records?|assets?|topics?|maps?|identifiers?|ids?|"
    r"configuration|config|schema|properties|metadata|result|state)\b",
    re.IGNORECASE,
)
MIXED_COVERAGE_RE = re.compile(
    r"\b(?:partial(?:ly)?\s+migrated|partially\s+upgraded|"
    r"mixed[-_\s]+(?:state|format|version|identifier)s?|"
    r"old\s+and\s+new|legacy\s+and\s+migrated|non[-_\s]?uuid\s+and\s+uuid)\b"
    r".{0,100}\b(?:coexist|co-exist|alongside|together|remain|supported|handled|processed)\b|"
    r"\b(?:coexist|co-exist|alongside)\b.{0,100}"
    r"\b(?:old|legacy|new|migrated|non[-_\s]?uuid|uuid)\b|"
    r"\b(?:interrupted|resumed|incomplete)\s+(?:upgrade|migration)\b"
    r".{0,100}\b(?:old|new|mixed|partial|state|content|data)\b",
    re.IGNORECASE | re.DOTALL,
)

ROLLBACK_SUPPORTED_RE = re.compile(
    r"\b(?:rollback|roll\s+back|revert|restore)\b.{0,80}"
    r"\b(?:support|supported|can|success|successful|return|restore|restored|original|old|previous)\b|"
    r"\b(?:support|supported|can)\b.{0,50}\b(?:rollback|roll\s+back|revert|restore)\b",
    re.IGNORECASE | re.DOTALL,
)
IRREVERSIBLE_RE = re.compile(
    r"\b(?:irreversible|non[-_\s]?reversible|one[-_\s]?way)\b|"
    r"\b(?:cannot|can't|must\s+not|not\s+supported|unsupported|no)\b"
    r".{0,45}\b(?:rollback|roll\s+back|revert)\b|"
    r"\b(?:rollback|roll\s+back|revert)\b.{0,45}"
    r"\b(?:cannot|not\s+supported|unsupported|unavailable|impossible)\b",
    re.IGNORECASE | re.DOTALL,
)


def _problem(message: str) -> str:
    return f"{PREFIX} {message}"


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().casefold()).strip("_")


def _manifest_values(
    value: Any, path: tuple[str, ...] = ()
) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if normalized in _IGNORED_MANIFEST_KEYS:
                continue
            yield from _manifest_values(child, (*path, normalized))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _manifest_values(child, (*path, str(index)))
    else:
        yield path, value


def _manifest_text(manifest: dict[str, Any]) -> list[str]:
    return [value for _path, value in _manifest_values(manifest) if isinstance(value, str)]


def _has_fix_version_value(manifest: dict[str, Any]) -> bool:
    for path, value in _manifest_values(manifest):
        if any(part in _FIX_VERSION_KEYS for part in path):
            if isinstance(value, str) and value.strip():
                return True
    return False


def _mixed_state_flag_labels(manifest: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for path, value in _manifest_values(manifest):
        if path and path[-1] in _MIXED_STATE_FLAG_KEYS and value is True:
            labels.append(path[-1].upper())
    return labels


def _matched_labels(
    text: str, patterns: tuple[tuple[str, re.Pattern[str]], ...]
) -> list[str]:
    return [label for label, pattern in patterns if pattern.search(text)]


def detect_signals(
    plan_body: str = "", manifest: dict[str, Any] | None = None
) -> dict[str, list[str]]:
    """Return migration dimensions activated by current ticket/evidence text."""
    manifest_data = manifest if isinstance(manifest, dict) else {}
    haystack = "\n".join([plan_body or "", *_manifest_text(manifest_data)])
    activation = _matched_labels(haystack, ACTIVATION_PATTERNS)

    format_change = bool(
        re.search(
            r"\b(?:stored|persisted)\s+(?:data|content|configuration|config)\b"
            r".{0,80}\b(?:format|schema|representation)\b|"
            r"\b(?:data|configuration|config|schema)\s+format\b.{0,55}"
            r"\b(?:change|changes|changed|convert|migration)\b",
            haystack,
            re.IGNORECASE | re.DOTALL,
        )
    )
    if _has_fix_version_value(manifest_data) and format_change:
        activation.append("FIX_VERSION_FORMAT_BOUNDARY")

    activation = list(dict.fromkeys(activation))
    if not activation:
        return {}

    mixed = _matched_labels(haystack, MIXED_STATE_PATTERNS)
    mixed.extend(_mixed_state_flag_labels(manifest_data))
    mixed = list(dict.fromkeys(mixed))
    if ATOMIC_MIGRATION_RE.search(haystack):
        mixed = []

    detected = {dimension: list(activation) for dimension in DIMENSIONS}
    if mixed:
        detected["POST_STATE_AND_MIXED"].extend(
            f"MIXED_STATE_REQUIRED:{label}" for label in mixed
        )
    return detected


def _block(manifest: dict[str, Any] | None) -> Any:
    return manifest.get(BLOCK_NAME) if isinstance(manifest, dict) else None


def _records(block: Any) -> list[Any] | None:
    if isinstance(block, list):
        return block
    if isinstance(block, dict):
        if isinstance(block.get("dimensions"), list):
            return block["dimensions"]
        if "dimension" in block:
            return [block]
    return None


def _plan_records(plan_body: str, prefix: str) -> dict[str, str]:
    records: dict[str, str] = {}
    for line in (plan_body or "").splitlines():
        match = re.search(rf"\b({re.escape(prefix)}-\d{{2,}})\b", line, re.IGNORECASE)
        if match:
            records[match.group(1).upper()] = line.strip()
    return records


def _as_string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    return [item.strip().upper() for item in value if item.strip()]


def _reason_is_concrete(reason: str) -> bool:
    normalized = re.sub(r"\s+", " ", reason.strip()).casefold().rstrip(".")
    return len(normalized) >= 12 and normalized not in {
        "n/a",
        "na",
        "none",
        "not applicable",
        "not required",
        "unknown",
        "tbd",
        "to be decided",
    }


def _mixed_state_required(signals: dict[str, list[str]]) -> bool:
    return any(
        label.startswith("MIXED_STATE_REQUIRED:")
        for label in signals.get("POST_STATE_AND_MIXED", [])
    )


def _validate_dimension_text(
    dimension: str, text: str, *, mixed_state_required: bool
) -> list[str]:
    if dimension == "PRE_STATE":
        missing: list[str] = []
        if not OLD_STATE_RE.search(text):
            missing.append("the old format or source version")
        if not AUTHORED_OR_STORED_RE.search(text):
            missing.append("content authored or stored before migration")
        if not MIGRATABLE_INPUT_RE.search(text):
            missing.append("the content, data, or configuration being migrated")
        return missing

    if dimension == "MIGRATION_EXECUTION":
        missing = []
        if not OPERATION_RE.search(text) or not OPERATION_RUN_RE.search(text):
            missing.append("the migration or upgrade operation running")
        if not OPERATION_COMPLETE_RE.search(text):
            missing.append("successful operation completion")
        if not REPEAT_POLICY_RE.search(text):
            missing.append("idempotent/rerunnable behavior or an explicit one-shot policy")
        if not (FAILURE_RE.search(text) and FAILURE_REPORT_RE.search(text)):
            missing.append("observable failure reporting")
        return missing

    if dimension == "POST_STATE_AND_MIXED":
        missing = []
        if not POST_STATE_RE.search(text) or not POST_RESULT_RE.search(text):
            missing.append("the migrated result in the target state")
        if mixed_state_required and not MIXED_COVERAGE_RE.search(text):
            missing.append("the partial or old-and-new mixed state")
        return missing

    if dimension == "ROLLBACK_OR_IRREVERSIBILITY":
        if not (ROLLBACK_SUPPORTED_RE.search(text) or IRREVERSIBLE_RE.search(text)):
            return ["whether rollback is supported or the migration is irreversible"]
        return []

    return ["an unknown migration dimension was supplied"]


def is_present(plan_body: str = "", manifest: dict[str, Any] | None = None) -> bool:
    return _block(manifest) is not None or bool(detect_signals(plan_body, manifest))


def validate(
    plan_body: str = "", manifest: dict[str, Any] | None = None
) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    signals = detect_signals(plan_body, manifest_data)
    block = _block(manifest_data)

    if not signals and block is None:
        return []
    if block is None:
        active = ", ".join(dict.fromkeys(
            label for labels in signals.values() for label in labels
            if not label.startswith("MIXED_STATE_REQUIRED:")
        ))
        return [_problem(
            f"upgrade or migration signals ({active}) require an {BLOCK_NAME} block"
        )]

    problems: list[str] = []
    if isinstance(block, dict) and block.get("schema_version") not in (
        None,
        SCHEMA_VERSION,
    ):
        problems.append(_problem(
            f"{BLOCK_NAME}.schema_version must be {SCHEMA_VERSION!r} when supplied"
        ))

    records = _records(block)
    if records is None:
        return problems + [_problem(
            f"{BLOCK_NAME} must contain a dimensions list of disposition records"
        )]

    by_dimension: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            problems.append(_problem(
                f"{BLOCK_NAME}.dimensions[{index}] must be an object"
            ))
            continue
        dimension = str(record.get("dimension") or "").strip().upper()
        if dimension not in DIMENSIONS:
            problems.append(_problem(
                f"{BLOCK_NAME}.dimensions[{index}].dimension must be one of "
                + ", ".join(DIMENSIONS)
            ))
            continue
        if dimension in by_dimension:
            problems.append(_problem(
                f"{BLOCK_NAME} contains duplicate {dimension} records"
            ))
            continue
        by_dimension[dimension] = record

    for dimension in DIMENSIONS:
        if dimension not in by_dimension:
            problems.append(_problem(
                f"{BLOCK_NAME} is silent for {dimension}; record COVERED_BY_AC, "
                "OPEN_QUESTION, or NOT_APPLICABLE with a concrete reason"
            ))

    ac_records = _plan_records(plan_body, "AC")
    oq_records = _plan_records(plan_body, "OQ")
    mixed_required = _mixed_state_required(signals)

    for dimension in DIMENSIONS:
        record = by_dimension.get(dimension)
        if record is None:
            continue
        disposition = str(record.get("disposition") or "").strip().upper()
        reason = str(record.get("reason") or "").strip()
        if disposition not in DISPOSITIONS:
            problems.append(_problem(
                f"{dimension}.disposition must be one of {', '.join(sorted(DISPOSITIONS))}"
            ))
            continue
        if not _reason_is_concrete(reason):
            problems.append(_problem(
                f"{dimension} must include a concrete, non-placeholder reason"
            ))

        if disposition == "NOT_APPLICABLE":
            continue

        if disposition == "OPEN_QUESTION" and dimension not in OPEN_QUESTION_DIMENSIONS:
            problems.append(_problem(
                f"{dimension} must be covered by an AC when applicable; "
                "OPEN_QUESTION is not an allowed applicable disposition"
            ))
            continue

        if disposition == "COVERED_BY_AC":
            ac_refs = _as_string_list(record.get("ac_refs"))
            if not ac_refs:
                problems.append(_problem(
                    f"{dimension} COVERED_BY_AC requires non-empty ac_refs"
                ))
                continue
            unknown = [ref for ref in ac_refs if ref not in ac_records]
            if unknown:
                problems.append(_problem(
                    f"{dimension} references ACs not present in the plan: {', '.join(unknown)}"
                ))
                continue
            coverage_text = "\n".join(ac_records[ref] for ref in ac_refs)
        else:
            oq_ref = str(record.get("open_question_ref") or "").strip().upper()
            if not oq_ref:
                problems.append(_problem(
                    f"{dimension} OPEN_QUESTION requires open_question_ref"
                ))
                continue
            if oq_ref not in oq_records:
                problems.append(_problem(
                    f"{dimension} references {oq_ref}, but that Open Question is not present in the plan"
                ))
                continue
            coverage_text = oq_records[oq_ref]
            if not re.search(r"\bQA\s+impact\s*:", coverage_text, re.IGNORECASE):
                problems.append(_problem(
                    f"{dimension} {oq_ref} must include an explicit QA impact"
                ))
                continue

        missing = _validate_dimension_text(
            dimension,
            coverage_text,
            mixed_state_required=mixed_required,
        )
        if missing:
            problems.append(_problem(
                f"{dimension} {disposition} mapping does not address: {'; '.join(missing)}"
            ))

    return problems


def summarize(
    plan_body: str = "", manifest: dict[str, Any] | None = None
) -> str:
    if not is_present(plan_body, manifest):
        return "UpgradeMigrationCoverage: NOT_APPLICABLE (no migration activation signal)"
    signals = detect_signals(plan_body, manifest)
    problems = validate(plan_body, manifest)
    lines = [f"UpgradeMigrationCoverage: {'CLEAN' if not problems else 'ISSUES'}"]
    lines.append(
        "  signals: "
        + (
            ", ".join(
                f"{dimension}={'+'.join(labels)}"
                for dimension, labels in signals.items()
            )
            or "explicit block"
        )
    )
    lines.extend(f"  {problem}" for problem in problems)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Signal-activated AEM Guides upgrade/migration coverage gate"
    )
    parser.add_argument("--plan")
    parser.add_argument("--manifest")
    args = parser.parse_args()

    plan_body = Path(args.plan).read_text(encoding="utf-8") if args.plan else ""
    manifest: dict[str, Any] = {}
    if args.manifest:
        loaded = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("manifest root must be a JSON object")
        manifest = loaded
    print(summarize(plan_body, manifest))
    return 0 if not validate(plan_body, manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
