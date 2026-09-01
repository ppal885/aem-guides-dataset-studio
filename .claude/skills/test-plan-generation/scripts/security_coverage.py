"""Signal-activated security coverage gate for XML/DITA product changes.

The gate is deliberately narrow and backward-compatible.  It stays inactive when
neither the plan nor the evidence manifest contains a supported security signal.
Once activated, it requires an explicit ``security_coverage`` ledger and fails
closed when an applicable security dimension is silent, weakly mapped, or marked
not applicable.

Generic only.  Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PREFIX = "SECURITY GATE:"
SCHEMA_VERSION = "aem-guides-security-coverage-v1"
DIMENSIONS = ("INPUT_SAFETY", "REFERENCE_TRAVERSAL", "AUTHZ")
DISPOSITIONS = {"COVERED_BY_AC", "OPEN_QUESTION", "NOT_APPLICABLE"}


INPUT_SAFETY_SIGNALS = (
    (
        "XML_OR_DITA_PARSE",
        re.compile(
            r"\b(?:xml|dita)\s+(?:document\s+|content\s+|file\s+)?"
            r"(?:parser|parsing|ingestion|ingest)\b|"
            r"\b(?:parse|parses|parsing|ingest|ingests|ingesting)\s+"
            r"(?:an?\s+|uploaded\s+|imported\s+|user[-\s]supplied\s+)?(?:xml|dita)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "DITA_UPLOAD_OR_IMPORT",
        re.compile(
            r"\bdita\s+(?:file\s+|map\s+|topic\s+|content\s+)?(?:upload|import|ingest)\b|"
            r"\b(?:upload|import|ingest)(?:ing|ed|s)?\s+(?:an?\s+)?"
            r"(?:dita\s+(?:file|map|topic|content)|ditamap)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "ENTITY_OR_DTD_HANDLING",
        re.compile(
            r"\b(?:xxe|doctype|dtd|external\s+entit(?:y|ies)|entity\s+expansion|"
            r"billion\s+laughs)\b",
            re.IGNORECASE,
        ),
    ),
)

REFERENCE_TRAVERSAL_SIGNALS = (
    (
        "DITA_REFERENCE_RESOLUTION",
        re.compile(
            r"\b(?:conref|conkeyref|keyref|href|xref)s?\b|"
            r"\b(?:resolve|resolves|resolving|resolution)\s+(?:of\s+)?"
            r"(?:dita\s+)?references?\b",
            re.IGNORECASE,
        ),
    ),
)

AUTHZ_SIGNALS = (
    (
        "CONTENT_ACCEPTING_ENDPOINT",
        re.compile(
            r"\b(?:rest|api|servlet|endpoint)\b.{0,80}"
            r"\b(?:accepts?|receives?|uploads?|imports?|posts?|puts?|creates?|updates?)\b"
            r".{0,80}\b(?:user[-\s]supplied|user\s+content|xml|dita|file|payload|body|content)\b|"
            r"\b(?:user[-\s]supplied|user\s+content)\b.{0,80}"
            r"\b(?:rest|api|servlet|endpoint)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "SHARED_PUBLISH_DESTINATION",
        re.compile(
            r"\b(?:publish(?:ing)?|output)\b.{0,80}"
            r"\b(?:shared\s+(?:location|destination|folder|path|repository)|"
            r"common\s+destination|shared\s+output)\b|"
            r"\b(?:shared\s+(?:location|destination|folder|path|repository)|"
            r"common\s+destination)\b.{0,80}\b(?:publish(?:ing)?|output)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "ACL_ROLE_OR_PERMISSION",
        re.compile(
            r"\b(?:acl|access\s+control|authori[sz]ation|permissions?|unauthori[sz]ed|"
            r"forbidden|privilege\s+escalation|role[-\s]based|"
            r"(?:admin|author|reviewer|publisher|user)\s+role)\b",
            re.IGNORECASE,
        ),
    ),
)

SIGNAL_PATTERNS = {
    "INPUT_SAFETY": INPUT_SAFETY_SIGNALS,
    "REFERENCE_TRAVERSAL": REFERENCE_TRAVERSAL_SIGNALS,
    "AUTHZ": AUTHZ_SIGNALS,
}

XXE_COVERAGE_RE = re.compile(
    r"\b(?:xxe|external\s+entit(?:y|ies))\b.{0,140}"
    r"\b(?:disable(?:d)?|block(?:ed)?|reject(?:ed|s)?|prohibit(?:ed)?|"
    r"not\s+(?:resolve|resolved|allowed))\b|"
    r"\b(?:disable(?:d)?|block(?:ed)?|reject(?:ed|s)?|prohibit(?:ed)?)\b"
    r".{0,140}\b(?:xxe|external\s+entit(?:y|ies))\b",
    re.IGNORECASE | re.DOTALL,
)
ENTITY_LIMIT_COVERAGE_RE = re.compile(
    r"\b(?:billion\s+laughs|entity[-\s]expansion|recursive\s+entit(?:y|ies))\b"
    r".{0,180}\b(?:limit(?:ed|s)?|bound(?:ed|s)?|reject(?:ed|s)?|block(?:ed|s)?|"
    r"disable(?:d|s)?|prevent(?:ed|s)?)\b|"
    r"\b(?:limit(?:ed|s)?|bound(?:ed|s)?|reject(?:ed|s)?|block(?:ed|s)?|"
    r"disable(?:d|s)?|prevent(?:ed|s)?)\b.{0,180}"
    r"\b(?:billion\s+laughs|entity[-\s]expansion|recursive\s+entit(?:y|ies))\b|"
    r"\bentity\s+(?:expansion\s+)?(?:depth|count|recursion)\s+limit\b",
    re.IGNORECASE | re.DOTALL,
)
MALFORMED_COVERAGE_RE = re.compile(
    r"\b(?:malformed|invalid|not\s+well[-\s]formed|broken)\s+"
    r"(?:xml|dita|input|content|file)\b.{0,180}"
    r"\b(?:reject(?:ed|s)?|block(?:ed|s)?|fail(?:ed|s)?\s+safely|"
    r"validation\s+(?:error|failure)|not\s+(?:processed|accepted))\b|"
    r"\b(?:reject(?:ed|s)?|block(?:ed|s)?|fail(?:ed|s)?\s+safely|"
    r"validation\s+(?:error|failure)|not\s+(?:processed|accepted))\b.{0,180}"
    r"\b(?:malformed|invalid|not\s+well[-\s]formed|broken)\s+"
    r"(?:xml|dita|input|content|file)\b",
    re.IGNORECASE | re.DOTALL,
)
OVERSIZED_COVERAGE_RE = re.compile(
    r"\b(?:oversized|over[-\s]size|too\s+large|"
    r"(?:file|input|payload)\s+size\s+limit|maximum\s+(?:file|input|payload)\s+size)\b"
    r".{0,180}\b(?:reject(?:ed|s)?|block(?:ed|s)?|fail(?:ed|s)?\s+safely|"
    r"validation\s+(?:error|failure)|not\s+(?:processed|accepted)|enforc(?:ed|es))\b|"
    r"\b(?:reject(?:ed|s)?|block(?:ed|s)?|fail(?:ed|s)?\s+safely|"
    r"validation\s+(?:error|failure)|not\s+(?:processed|accepted)|enforc(?:ed|es))\b"
    r".{0,180}\b(?:oversized|over[-\s]size|too\s+large|"
    r"(?:file|input|payload)\s+size\s+limit|maximum\s+(?:file|input|payload)\s+size)\b",
    re.IGNORECASE | re.DOTALL,
)
TRAVERSAL_COVERAGE_RE = re.compile(
    r"\b(?:path|directory)\s+traversal\b|\bout[-\s]of[-\s]scope\s+reference\b|"
    r"\b(?:reference|conref|conkeyref|keyref|href|xref)\b.{0,90}"
    r"\b(?:cannot|must\s+not|does\s+not|denied|blocked|rejected)\b.{0,50}"
    r"\b(?:outside|beyond|escape)\b.{0,35}\b(?:permitted|allowed|content)\s+scope\b|"
    r"\b(?:outside|beyond|escape)\b.{0,35}\b(?:permitted|allowed|content)\s+scope\b"
    r".{0,90}\b(?:reference|conref|conkeyref|keyref|href|xref)\b",
    re.IGNORECASE | re.DOTALL,
)
UNAUTHORIZED_DENIAL_RE = re.compile(
    r"\b(?:unauthori[sz]ed|insufficient\s+permissions?|without\s+permission|"
    r"forbidden|access\s+denied|denied\s+(?:access|role|user)|"
    r"(?:role|user)\b.{0,40}\bdenied)\b",
    re.IGNORECASE | re.DOTALL,
)
NO_ESCALATION_RE = re.compile(
    r"\b(?:no|without|prevent(?:s|ed)?|cannot|must\s+not|does\s+not)\b.{0,60}"
    r"\b(?:privilege\s+escalation|permission\s+bypass|access[-\s]control\s+bypass|"
    r"bypass\s+(?:authorization|permissions?|access\s+control))\b|"
    r"\b(?:privilege\s+escalation|permission\s+bypass|access[-\s]control\s+bypass)\b"
    r".{0,60}\b(?:prevented|blocked|denied|not\s+possible)\b",
    re.IGNORECASE | re.DOTALL,
)


def _problem(message: str) -> str:
    return f"{PREFIX} {message}"


def _manifest_text(value: Any, *, root: bool = True) -> list[str]:
    """Collect manifest scalar text without letting this gate activate itself."""
    if isinstance(value, dict):
        collected: list[str] = []
        for key, child in value.items():
            if root and key == "security_coverage":
                continue
            collected.extend(_manifest_text(child, root=False))
        return collected
    if isinstance(value, list):
        collected = []
        for child in value:
            collected.extend(_manifest_text(child, root=False))
        return collected
    if isinstance(value, str):
        return [value]
    return []


def detect_signals(plan_body: str = "", manifest: dict[str, Any] | None = None) -> dict[str, list[str]]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    haystack = "\n".join([plan_body or "", *_manifest_text(manifest_data)])
    detected: dict[str, list[str]] = {}
    for dimension, patterns in SIGNAL_PATTERNS.items():
        labels = [label for label, pattern in patterns if pattern.search(haystack)]
        if labels:
            detected[dimension] = labels
    return detected


def _block(manifest: dict[str, Any] | None) -> Any:
    return manifest.get("security_coverage") if isinstance(manifest, dict) else None


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
    if dimension == "INPUT_SAFETY":
        missing = []
        if not XXE_COVERAGE_RE.search(text):
            missing.append("external-entity resolution (XXE) is disabled")
        if not ENTITY_LIMIT_COVERAGE_RE.search(text):
            missing.append("entity-expansion / Billion Laughs limits")
        if not MALFORMED_COVERAGE_RE.search(text):
            missing.append("malformed XML/DITA input handling")
        if not OVERSIZED_COVERAGE_RE.search(text):
            missing.append("oversized XML/DITA input handling")
        return missing
    if dimension == "REFERENCE_TRAVERSAL":
        return [] if TRAVERSAL_COVERAGE_RE.search(text) else [
            "path-traversal / out-of-scope reference resolution is blocked"
        ]
    if dimension == "AUTHZ":
        missing = []
        if not UNAUTHORIZED_DENIAL_RE.search(text):
            missing.append("an unauthorized role is denied")
        if not NO_ESCALATION_RE.search(text):
            missing.append("the changed path cannot cause privilege escalation or permission bypass")
        return missing
    return ["an unknown security dimension was supplied"]


def is_present(plan_body: str = "", manifest: dict[str, Any] | None = None) -> bool:
    return _block(manifest) is not None or bool(detect_signals(plan_body, manifest))


def validate(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    signals = detect_signals(plan_body, manifest_data)
    block = _block(manifest_data)

    if not signals and block is None:
        return []
    if block is None:
        active = ", ".join(signals)
        return [_problem(
            f"security signals activate {active}, but the security_coverage block is missing"
        )]

    problems: list[str] = []
    if isinstance(block, dict) and block.get("schema_version") not in (None, SCHEMA_VERSION):
        problems.append(_problem(
            f"security_coverage.schema_version must be {SCHEMA_VERSION!r} when supplied"
        ))

    records = _records(block)
    if records is None:
        return problems + [_problem(
            "security_coverage must contain a dimensions list of disposition records"
        )]

    by_dimension: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            problems.append(_problem(f"security_coverage.dimensions[{index}] must be an object"))
            continue
        dimension = str(record.get("dimension") or "").strip().upper()
        if dimension not in DIMENSIONS:
            problems.append(_problem(
                f"security_coverage.dimensions[{index}].dimension must be one of {', '.join(DIMENSIONS)}"
            ))
            continue
        if dimension in by_dimension:
            problems.append(_problem(f"security_coverage contains duplicate {dimension} records"))
            continue
        by_dimension[dimension] = record

    for dimension in DIMENSIONS:
        if dimension not in by_dimension:
            problems.append(_problem(
                f"security_coverage is silent for {dimension}; record COVERED_BY_AC, "
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
                problems.append(_problem(f"{dimension} COVERED_BY_AC requires non-empty ac_refs"))
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


def summarize(plan_body: str = "", manifest: dict[str, Any] | None = None) -> str:
    if not is_present(plan_body, manifest):
        return "SecurityCoverage: NOT_APPLICABLE (no security activation signal)"
    signals = detect_signals(plan_body, manifest)
    problems = validate(plan_body, manifest)
    lines = [f"SecurityCoverage: {'CLEAN' if not problems else 'ISSUES'}"]
    lines.append(
        "  signals: "
        + (", ".join(f"{key}={'+'.join(value)}" for key, value in signals.items()) or "explicit block")
    )
    lines.extend(f"  {problem}" for problem in problems)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Signal-activated XML/DITA security coverage gate")
    parser.add_argument("--plan")
    parser.add_argument("--manifest")
    args = parser.parse_args()

    plan_body = Path(args.plan).read_text(encoding="utf-8") if args.plan else ""
    manifest: dict[str, Any] = {}
    if args.manifest:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    print(summarize(plan_body, manifest))
    return 0 if not validate(plan_body, manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
