"""Verify that evidence cited in a test plan is real, not hallucinated.

This is a factual audit, complementary to validate_test_plan.py (which only
checks structure). It confirms that every cited source-file path actually
exists on disk and that every cited line number is within that file's length.

Scope of what is checked (deliberately narrow to avoid false positives):
- Only absolute paths (for example C:\\starling\\..., C:/starling/..., or
  /home/user/starling/...).
- Only paths ending in a known source extension. Directory roots, runtime
  paths such as /var/dxml/btree, relative test paths, and proposed new files
  (which are cited relatively by convention) are treated as unverifiable-by-
  design and skipped, not failed.
- Line references (Lnnn, Lnnn-mmm) are checked only when exactly one existing
  file path appears on the line, to keep path/line association unambiguous.

Jira keys can be cross-checked against an optional manifest of keys that were
actually fetched this session, catching invented ticket numbers.

Exit code is non-zero when any cited source file is missing or any cited line
is out of range. Unverifiable-by-design citations never fail the run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


SOURCE_EXTENSIONS = (
    ".java",
    ".py",
    ".json",
    ".xml",
    ".js",
    ".ts",
    ".tsx",
    ".feature",
    ".yaml",
    ".yml",
    ".md",
    ".properties",
)
ABS_PATH_RE = re.compile(r"(?<![\w.:/-])(?:[A-Za-z]:[\\/]|/)[^\s`,;)]+")
BACKTICK_PATH_RE = re.compile(r"`((?:[A-Za-z]:[\\/]|/)[^`\n]+)`")
LINE_REF_RE = re.compile(r"\bL(\d+)")
JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
TRAILING_PUNCT = ".,;:)]}"


_file_text_cache: dict[str, str] = {}

# Distinctive code identifiers, low false-positive against prose:
#   lower-camelCase with a hump (moveInBatches, processParentMaps)
#   ALL_CAPS_WITH_UNDERSCORE constants (PARENT_MAPS_FIELD_NAME)
_CAMEL_RE = re.compile(r"\b[a-z][a-z0-9]*(?:[A-Z][A-Za-z0-9]*)+\b")
_CONST_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")


def _extract_code_symbols(line: str) -> set[str]:
    # Strip filenames/paths so path fragments are not treated as cited symbols.
    without_paths = ABS_PATH_RE.sub(" ", BACKTICK_PATH_RE.sub(" ", line))
    without_paths = re.sub(r"[\w./\\-]+\.\w+", " ", without_paths)  # drop bare filenames like Foo.java
    symbols = set(_CAMEL_RE.findall(without_paths)) | set(_CONST_RE.findall(without_paths))
    return symbols


def _normalize(candidate: str) -> str:
    stripped = candidate.strip()
    while stripped and stripped[-1] in TRAILING_PUNCT:
        stripped = stripped[:-1]
    return stripped


def _is_source_file_citation(path: str) -> bool:
    return path.lower().endswith(SOURCE_EXTENSIONS)


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def verify(text: str, jira_keys: set[str] | None = None) -> tuple[list[str], list[str]]:
    """Return (failures, notes). Failures are hard; notes are informational."""
    failures: list[str] = []
    notes: list[str] = []
    verified = 0
    skipped = 0

    for number, line in enumerate(text.splitlines(), start=1):
        # Backtick-delimited paths are unambiguous even when they contain spaces
        # (for example `C:\api automation\...\Foo.java`); the whitespace-split
        # regex only reliably handles space-free paths.
        candidates: list[str] = []
        for match in BACKTICK_PATH_RE.finditer(line):
            candidate = _normalize(match.group(1))
            if candidate not in candidates:
                candidates.append(candidate)
        for match in ABS_PATH_RE.finditer(line):
            candidate = _normalize(match.group(0))
            if candidate not in candidates:
                candidates.append(candidate)
        file_paths = [p for p in candidates if _is_source_file_citation(p)]
        skipped += len(candidates) - len(file_paths)

        existing_on_line: list[Path] = []
        for cited in file_paths:
            path = Path(cited)
            if path.is_file():
                verified += 1
                existing_on_line.append(path)
            else:
                failures.append(f"line {number}: cited source file does not exist: {cited}")

        if len(existing_on_line) == 1:
            target = existing_on_line[0]
            total = _line_count(target)
            for ref in LINE_REF_RE.findall(line):
                if int(ref) > total:
                    failures.append(
                        f"line {number}: cited line L{ref} is beyond end of "
                        f"{target} (file has {total} lines)"
                    )
            # Symbol-level check: distinctive code identifiers cited next to a single
            # file must actually appear in that file, catching a real file cited with
            # an invented method/constant name (not just a valid line number).
            body_text = _file_text_cache.get(str(target))
            if body_text is None:
                body_text = target.read_text(encoding="utf-8", errors="replace")
                _file_text_cache[str(target)] = body_text
            for symbol in _extract_code_symbols(line):
                if symbol not in body_text:
                    failures.append(
                        f"line {number}: cited symbol '{symbol}' not found in {target}"
                    )

    notes.append(f"verified {verified} source-file citation(s); skipped {skipped} unverifiable-by-design path(s)")

    covered_present = ("Partially covered" in text) or bool(re.search(r"\bCovered\b", text))
    if covered_present and "```" not in text:
        failures.append(
            "Automation shows Covered/Partially covered items but the file has no fenced code evidence; "
            "produce Appendix A with the real code quoted from the cited files and run this check on the "
            "combined plan+appendix deliverable"
        )

    if jira_keys is not None:
        cited_keys = set(JIRA_KEY_RE.findall(text))
        invented = sorted(cited_keys - jira_keys)
        for key in invented:
            failures.append(f"Jira key {key} was cited but is not in the fetched-keys manifest")
        notes.append(f"cross-checked {len(cited_keys)} Jira key(s) against manifest of {len(jira_keys)}")

    return failures, notes


def _load_manifest(path: str | None) -> set[str] | None:
    if not path:
        return None
    return set(JIRA_KEY_RE.findall(Path(path).read_text(encoding="utf-8")))


def verify_attachments(manifest_path: str) -> tuple[list[str], list[str]]:
    """Ground-check an evidence manifest of Jira attachments.

    The manifest is JSON of the form:
      {"issue": "GUIDES-####",
       "attachments": [
         {"id": "...", "filename": "...", "downloaded_to": "<abs path>", "analyzed": true, "note": "..."}
       ]}

    Hard failures (checkable against disk / the manifest itself):
    - a declared attachment whose downloaded_to file is not present on disk
      (proves it was actually fetched, not invented);
    - an attachment left with analyzed != true (explicit attestation missing).

    This proves each listed attachment was downloaded and attested; it cannot
    prove the Jira attachment list is complete or that analysis was genuine.
    """
    failures: list[str] = []
    notes: list[str] = []
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"evidence manifest could not be read: {exc}"], notes

    rag = data.get("rag_probes")
    if rag is not None:
        if not isinstance(rag, list):
            failures.append("evidence manifest 'rag_probes' must be a list of probe questions")
        elif data.get("behaviour_matters", True) and len(rag) < 3:
            failures.append(
                f"only {len(rag)} RAG probe(s) recorded; run at least three focused ask_dita_expert probes "
                f"when behaviour matters (a single noisy probe is not 'RAG unavailable' - reformulate and retry), "
                f"or set behaviour_matters=false with a reason if RAG genuinely does not apply"
            )
        else:
            notes.append(f"manifest records {len(rag)} RAG probe(s)")

    jira_queries = data.get("jira_history_queries")
    if jira_queries is not None:
        if not isinstance(jira_queries, list):
            failures.append("evidence manifest 'jira_history_queries' must be a list")
        elif jira_queries:
            notes.append(f"manifest records {len(jira_queries)} search_jira_history query(s)")
        elif not str(data.get("jira_history_unavailable_reason", "")).strip():
            failures.append(
                "no search_jira_history queries recorded and no jira_history_unavailable_reason supplied"
            )

    attachments = data.get("attachments", [])
    if not isinstance(attachments, list):
        return ["evidence manifest 'attachments' must be a list"], notes

    analyzed_count = 0
    for index, entry in enumerate(attachments):
        ident = entry.get("id") or entry.get("filename") or f"#{index}"
        downloaded_to = entry.get("downloaded_to")
        if not downloaded_to:
            failures.append(f"attachment {ident}: manifest entry has no downloaded_to path")
        elif not Path(downloaded_to).is_file():
            failures.append(f"attachment {ident}: declared download not found on disk: {downloaded_to}")
        if entry.get("analyzed") is not True:
            failures.append(f"attachment {ident}: not attested as analyzed (analyzed must be true)")
        else:
            analyzed_count += 1

    notes.append(f"manifest declares {len(attachments)} attachment(s); {analyzed_count} attested analyzed and present")
    return failures, notes


# A dotted lower-case config/OSGi key: >=3 dot-separated segments keeps false
# positives (bare filenames, two-word prose) low while matching real keys such as
# `duplicate.uuid.move.old.file` and `create.version.newly.uploaded.content`.
_CONFIG_KEY_RE = re.compile(r"\b[a-z][a-z0-9]+(?:\.[a-z0-9]+){2,}\b")


def verify_config_keys(manifest_path: str, clone_roots: list[str] | None) -> tuple[list[str], list[str]]:
    """Prove that every config key an implementation_grounding config_key artifact
    marks CODE/OSGI-verified actually exists in the clone. A key claimed
    code-verified but not found is the reporter-key bug class (a typo/transposition
    like `uuid.duplicate.move.old` vs `duplicate.uuid.move.old.file`). Skipped when
    no clone root is reachable."""
    failures: list[str] = []
    notes: list[str] = []
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    ig = data.get("implementation_grounding")
    if not isinstance(ig, dict):
        return [], []

    def _reachable_git_repo(root: str) -> bool:
        try:
            r = subprocess.run(["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
                               capture_output=True, text=True, timeout=15)
            return r.returncode == 0 and r.stdout.strip() == "true"
        except (OSError, subprocess.SubprocessError):
            return False

    roots = [r for r in (clone_roots or []) if r and _reachable_git_repo(r)]
    if not roots:
        return [], ["config-key reality check skipped (no reachable clone root to grep against)"]
    checked = 0
    for art in (ig.get("named_artifacts") or []):
        if not isinstance(art, dict) or art.get("kind") != "config_key" or not art.get("material", True):
            continue
        if str(art.get("key_provenance", "")).strip() not in ("CODE", "OSGI_CONFIG"):
            continue
        blob = " ".join([str(art.get("artifact", ""))] + [str(e) for e in (art.get("evidence") or [])])
        keys = _CONFIG_KEY_RE.findall(blob)
        key = max(keys, key=len) if keys else ""
        if not key:
            continue
        found = False
        for root in roots:
            try:
                r = subprocess.run(["git", "-C", root, "grep", "-Fq", key],
                                   capture_output=True, text=True, timeout=30)
                if r.returncode == 0:
                    found = True
                    break
            except (OSError, subprocess.SubprocessError):
                continue
        checked += 1
        if not found:
            failures.append(
                f"config_key '{key}' is marked {art.get('key_provenance')} (code-verified) but the exact key string "
                f"was not found in any inspected clone - grep it and correct it; a reporter/ticket-supplied key is "
                f"frequently a typo or transposition"
            )
    notes.append(f"config-key reality: grepped {checked} CODE/OSGI-provenance key(s) against the clone")
    return failures, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit cited evidence in a test plan.")
    parser.add_argument("plan", help="Markdown test-plan file to audit")
    parser.add_argument(
        "--jira-keys",
        dest="jira_keys",
        default=None,
        help="Optional file listing Jira keys actually fetched this session (any text; keys are extracted)",
    )
    parser.add_argument(
        "--attachments-manifest",
        dest="attachments_manifest",
        default=None,
        help="Optional JSON manifest of Jira attachments (id/filename/downloaded_to/analyzed) to ground-check",
    )
    args = parser.parse_args()

    text = Path(args.plan).read_text(encoding="utf-8")
    manifest = _load_manifest(args.jira_keys)
    failures, notes = verify(text, manifest)

    if args.attachments_manifest:
        att_failures, att_notes = verify_attachments(args.attachments_manifest)
        failures.extend(att_failures)
        notes.extend(att_notes)

    for note in notes:
        print(f"NOTE: {note}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: all verifiable evidence citations resolve on disk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
