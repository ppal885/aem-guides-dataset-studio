"""Fail when regression-example identities leak into production skill reasoning.

Historical Jira examples belong only in explicit regression/evaluation fixtures.  This
audit scans active instructions, references, scripts, and data while excluding the
fixture catalogs and self-tests.  It deliberately checks identity/fingerprint leakage,
not ordinary Jira integration vocabulary or source-backed numeric validation.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


EXCLUDED_RELATIVE_PATHS = {
    Path("references/golden-benchmark.md"),
    Path("references/uac-reference-examples.md"),
    Path("scripts/audit_production_hardcoding.py"),
    Path("scripts/test_skill_scripts.py"),
}
EXCLUDED_TOP_LEVEL = {"analysis", "__pycache__"}
TEXT_SUFFIXES = {".md", ".py", ".json"}

FORBIDDEN_PATTERNS = (
    ("concrete GUIDES issue key", re.compile(r"\bGUIDES-\d+\b")),
    ("historical customer fingerprint", re.compile(r"\b(?:Hyundai|Red Hat)\b", re.I)),
    ("historical service-pack fingerprint", re.compile(r"\bSP2[12]\b", re.I)),
    (
        "historical workload/threshold fingerprint",
        re.compile(
            r"\b411\b|\b200\s+concurrent\s+users\b|\b200\s+assets\b|\bunder\s+100\b|"
            r"\bmap2\b|\bseven[-\s]node\b|\b6[-\s]row\s+by\s+5[-\s]column\b|\b6\s+by\s+3\b",
            re.I,
        ),
    ),
    ("historical example authority heading", re.compile(r"\b(?:Gold|Caution) Reference\b", re.I)),
    (
        "historical API example fingerprint",
        re.compile(
            r"POST\s+/bin/fmdita/xmleditor/create|POST\s+/bin/guides/assets/delete|"
            r"operation=(?:getdita|postDita)",
            re.I,
        ),
    ),
)


def _active_files(skill_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in skill_root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(skill_root)
        if relative in EXCLUDED_RELATIVE_PATHS:
            continue
        if relative.parts and relative.parts[0] in EXCLUDED_TOP_LEVEL:
            continue
        if "__pycache__" in relative.parts:
            continue
        files.append(path)
    return sorted(files)


def audit(skill_root: Path) -> list[str]:
    failures: list[str] = []
    for path in _active_files(skill_root):
        relative = path.relative_to(skill_root)
        text = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                failures.append(
                    f"{relative}:{line}: {label}: {match.group(0)!r}"
                )
        if relative == Path("scripts/component_reference_router.py") and (
            "references/uac-reference-examples.md" in text
        ):
            failures.append(
                f"{relative}: production router must not return the historical example catalog"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    failures = audit(args.skill_root.resolve())
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: no historical Jira identity or known fixture threshold appears in production reasoning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
