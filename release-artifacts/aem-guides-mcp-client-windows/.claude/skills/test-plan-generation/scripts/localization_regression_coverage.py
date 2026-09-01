"""Signal-activated localization regression coverage gate for AEM Guides plans.

The gate is backward-compatible for plans that do not touch content, metadata,
references, publishing, or localization.  Once a strong signal exists, an
explicit ``localization_coverage`` ledger must disposition every localization
dimension.  The gate validates only dimension coverage and traceability; the
normal AC/OQ validators continue to own presentation and wording policy.

The project-type and translation-status values are documented product
enumerations from the skill's Translation Project API UAC Reference.

Generic only.  Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PREFIX = "LOCALIZATION GATE:"
SCHEMA_VERSION = "aem-guides-localization-coverage-v1"
DIMENSIONS = ("TRANSLATION_STATE", "XLIFF_ROUNDTRIP", "PROJECT_TYPES")
DISPOSITIONS = {"COVERED_BY_AC", "OPEN_QUESTION", "NOT_APPLICABLE"}

# Documented in SKILL.md, "Translation Project API UAC Reference".  Keep these
# as complete sets so a single familiar project type cannot satisfy the gate.
TRANSLATION_STATUS_VALUES = (
    "Out of Date",
    "In Progress",
    "In Sync",
    "Out of Sync",
    "Missing copy",
)
REQUIRED_TRANSLATION_STATES = ("Out of Sync", "Missing copy")
PROJECT_TYPES = (
    "newTranslationProject",
    "xliffTranslationProject",
    "newMultiLingualTranslationProject",
    "addToExistingProject",
    "newScopingTranslationProject",
)
TRANSLATION_STATUS_SET = frozenset(TRANSLATION_STATUS_VALUES)
PROJECT_TYPE_SET = frozenset(PROJECT_TYPES)


GENERAL_SIGNALS = (
    (
        "LOCALIZATION_NAMED",
        re.compile(
            r"\b(?:translation|locali[sz]ation|multi[-\s]?lingual)\b|xliff",
            re.IGNORECASE,
        ),
    ),
    (
        "CONTENT_OR_TOPIC_BODY",
        re.compile(
            r"\bcontent\b|\b(?:dita\s+)?(?:topic|map)\s+(?:body|content)\b|"
            r"\b(?:change|edit|update|modify|insert|remove|delete|copy|paste|save)"
            r"(?:d|s|ing)?\b.{0,60}\b(?:dita\s+)?(?:topic|map)\b|"
            r"\b(?:dita\s+)?(?:topic|map)\b.{0,60}"
            r"\b(?:body|content|change|edit|update|modify|insert|remove|delete|copy|paste|save)"
            r"(?:d|s|ing)?\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "METADATA_OR_PROPERTY",
        re.compile(
            r"\b(?:meta[-\s]?data|propert(?:y|ies)|front\s+matter)\b|"
            r"\bjcr:content/metadata\b",
            re.IGNORECASE,
        ),
    ),
    (
        "REUSE_OR_REFERENCE",
        re.compile(
            r"\b(?:conref|conkeyref|keyref|keydef|reuse|reusable\s+content)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "PUBLISHING_OR_OUTPUT",
        re.compile(
            r"\b(?:publish|publishes|published|publishing|output|"
            r"output\s+preset|output\s+generation)\b",
            re.IGNORECASE,
        ),
    ),
)

STRUCTURE_SIGNALS = (
    (
        "XLIFF_NAMED",
        re.compile(r"xliff", re.IGNORECASE),
    ),
    (
        "CONTENT_OR_MARKUP_STRUCTURE_CHANGE",
        re.compile(
            r"\b(?:markup|content\s+(?:model|structure)|structural\s+change|"
            r"xml\s+structure|dita\s+structure|element|tag)\b|"
            r"\b(?:add|insert|remove|delete|rename|move|wrap|unwrap|transform)"
            r"(?:d|s|ing)?\b.{0,60}\b(?:element|tag|markup|structure|content\s+model)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)

_PROJECT_TYPE_PATTERN = "|".join(re.escape(value) for value in PROJECT_TYPES)
PROJECT_SIGNALS = (
    (
        "DOCUMENTED_PROJECT_TYPE",
        re.compile(_PROJECT_TYPE_PATTERN, re.IGNORECASE),
    ),
    (
        "PROJECT_CREATION_OR_SCOPE",
        re.compile(
            r"\b(?:create|creates|created|creating|creation|add|adds|adding|"
            r"scope|scopes|scoped|scoping|project\s+type)\b.{0,90}"
            r"\b(?:translation|locali[sz]ation|multi[-\s]?lingual)\s+project\b|"
            r"\b(?:translation|locali[sz]ation|multi[-\s]?lingual)\s+project\b"
            r".{0,90}\b(?:create|creates|created|creating|creation|add|adds|adding|"
            r"scope|scopes|scoped|scoping|project\s+type)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)

TRANSLATION_PROJECT_CONTEXT_RE = re.compile(
    r"\b(?:existing|already|current|previously|within|inside|in|added\s+to)\b"
    r".{0,80}\btranslation\s+project\b|"
    r"\btranslation\s+project\b.{0,80}"
    r"\b(?:existing|already|current|previously|contains?|content|topic|map)\b",
    re.IGNORECASE | re.DOTALL,
)
XLIFF_RE = re.compile(r"xliff", re.IGNORECASE)
XLIFF_EXPORT_RE = re.compile(r"\bexport(?:ed|s|ing)?\b", re.IGNORECASE)
XLIFF_IMPORT_RE = re.compile(r"\bimport(?:ed|s|ing)?\b", re.IGNORECASE)
ROUNDTRIP_INTEGRITY_RE = re.compile(
    r"\bround[-\s]?trip\b|\bintegrity\b|\bpreserv(?:e|es|ed|ing|ation)\b|"
    r"\b(?:without|no)\s+(?:content|markup|structure|data)\s+loss\b|"
    r"\b(?:content|markup|structure)\s+(?:remains?|is)\s+unchanged\b",
    re.IGNORECASE,
)

_IGNORED_MANIFEST_KEYS = {
    "localization_coverage",
    "security_coverage",
    "block_waivers",
}


def _problem(message: str) -> str:
    return f"{PREFIX} {message}"


def _manifest_text(value: Any) -> list[str]:
    """Collect evidence text without letting coverage ledgers activate the gate."""
    if isinstance(value, dict):
        collected: list[str] = []
        for key, child in value.items():
            if str(key).strip().lower() in _IGNORED_MANIFEST_KEYS:
                continue
            collected.extend(_manifest_text(child))
        return collected
    if isinstance(value, list):
        collected = []
        for child in value:
            collected.extend(_manifest_text(child))
        return collected
    return [value] if isinstance(value, str) else []


def _matched_labels(text: str, patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> list[str]:
    return [label for label, pattern in patterns if pattern.search(text)]


def detect_signals(
    plan_body: str = "", manifest: dict[str, Any] | None = None
) -> dict[str, list[str]]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    haystack = "\n".join([plan_body or "", *_manifest_text(manifest_data)])

    general = _matched_labels(haystack, GENERAL_SIGNALS)
    structure = _matched_labels(haystack, STRUCTURE_SIGNALS)
    project = _matched_labels(haystack, PROJECT_SIGNALS)

    detected: dict[str, list[str]] = {}
    state_labels = list(dict.fromkeys([*general, *structure, *project]))
    if state_labels:
        detected["TRANSLATION_STATE"] = state_labels
    if structure:
        detected["XLIFF_ROUNDTRIP"] = structure
    if project:
        detected["PROJECT_TYPES"] = project
    return detected


def _block(manifest: dict[str, Any] | None) -> Any:
    return manifest.get("localization_coverage") if isinstance(manifest, dict) else None


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
    normalized = re.sub(r"\s+", " ", reason.strip()).lower().rstrip(".")
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


def _validate_dimension_text(dimension: str, text: str) -> list[str]:
    if dimension == "TRANSLATION_STATE":
        missing: list[str] = []
        if not TRANSLATION_PROJECT_CONTEXT_RE.search(text):
            missing.append("content already in a translation project")
        for state in REQUIRED_TRANSLATION_STATES:
            if not re.search(rf"\b{re.escape(state)}\b", text, re.IGNORECASE):
                missing.append(f"{state} status transition or detection")
        return missing

    if dimension == "XLIFF_ROUNDTRIP":
        missing = []
        if not XLIFF_RE.search(text):
            missing.append("XLIFF")
        if not XLIFF_EXPORT_RE.search(text):
            missing.append("XLIFF export")
        if not XLIFF_IMPORT_RE.search(text):
            missing.append("XLIFF import")
        if not ROUNDTRIP_INTEGRITY_RE.search(text):
            missing.append("round-trip integrity for the affected construct")
        return missing

    if dimension == "PROJECT_TYPES":
        folded = text.casefold()
        missing_types = [value for value in PROJECT_TYPES if value.casefold() not in folded]
        return [
            "the complete supported project-type set: " + ", ".join(missing_types)
        ] if missing_types else []

    return ["an unknown localization dimension was supplied"]


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
        active = ", ".join(signals)
        return [_problem(
            f"localization signals activate {active}, but the localization_coverage block is missing"
        )]

    problems: list[str] = []
    if isinstance(block, dict) and block.get("schema_version") not in (None, SCHEMA_VERSION):
        problems.append(_problem(
            f"localization_coverage.schema_version must be {SCHEMA_VERSION!r} when supplied"
        ))

    records = _records(block)
    if records is None:
        return problems + [_problem(
            "localization_coverage must contain a dimensions list of disposition records"
        )]

    by_dimension: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            problems.append(_problem(
                f"localization_coverage.dimensions[{index}] must be an object"
            ))
            continue
        dimension = str(record.get("dimension") or "").strip().upper()
        if dimension not in DIMENSIONS:
            problems.append(_problem(
                f"localization_coverage.dimensions[{index}].dimension must be one of "
                + ", ".join(DIMENSIONS)
            ))
            continue
        if dimension in by_dimension:
            problems.append(_problem(
                f"localization_coverage contains duplicate {dimension} records"
            ))
            continue
        by_dimension[dimension] = record

    for dimension in DIMENSIONS:
        if dimension not in by_dimension:
            problems.append(_problem(
                f"localization_coverage is silent for {dimension}; record COVERED_BY_AC, "
                "OPEN_QUESTION, or NOT_APPLICABLE with a concrete reason"
            ))

    ac_records = _plan_records(plan_body, "AC")
    oq_records = _plan_records(plan_body, "OQ")

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

        missing = _validate_dimension_text(dimension, coverage_text)
        if missing:
            problems.append(_problem(
                f"{dimension} {disposition} mapping does not address: {'; '.join(missing)}"
            ))

    return problems


def summarize(
    plan_body: str = "", manifest: dict[str, Any] | None = None
) -> str:
    if not is_present(plan_body, manifest):
        return "LocalizationRegressionCoverage: NOT_APPLICABLE (no localization activation signal)"
    signals = detect_signals(plan_body, manifest)
    problems = validate(plan_body, manifest)
    lines = [f"LocalizationRegressionCoverage: {'CLEAN' if not problems else 'ISSUES'}"]
    lines.append(
        "  signals: "
        + (
            ", ".join(f"{key}={'+'.join(value)}" for key, value in signals.items())
            or "explicit block"
        )
    )
    lines.extend(f"  {problem}" for problem in problems)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Signal-activated AEM Guides localization regression coverage gate"
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
