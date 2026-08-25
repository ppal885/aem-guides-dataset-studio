"""Fail-closed fidelity for reporter-enumerated source requirements.

``enumerated_requirements`` proves that every reporter item has a disposition.
This ledger proves that the disposition still carries the source meaning.  It is
independent of acceptance authority: Proposed and Confirmed items are checked by
the same rules, even when ``accepted_uac_present`` is false.

Manifest shape (``aem-guides-source-requirement-ledger-v1``)::

    {
      "schema_version": "aem-guides-source-requirement-ledger-v1",
      "sources": [{
        "id": "SRC-01", "type": "jira_description", "locator": "...",
        "raw_text": "...", "sha256": "<sha256 of exact UTF-8 raw_text>",
        "artifact_path": "<absolute path to the exact acquisition capture>",
        "artifact_sha256": "<sha256 of the artifact bytes>"
      }],
      "items": [{
        "id": "REQ-01", "source_id": "SRC-01", "source_index": 1,
        "verbatim_text": "...", "text": "...", "authority": "Proposed",
        "disposition": "AC", "ac_refs": ["AC-01"],
        "protected_exact": ["optional exact token"],
        "semantic_atoms": [{
          "id": "ATOM-01", "text": "exact source phrase",
          "required_terms_all": ["term that must survive"],
          "required_terms_any": ["one", "accepted alternative"]
        }]
      }]
    }

An atom that conflicts with implementation evidence may instead declare
``evidence_conflict: true`` and a real ``open_question_ref``.  The question must
still contain the atom's required terms, so a conflict cannot become a silent
semantic substitution.  OUT-OF-SCOPE items trace their atoms and protected
identifiers to their explicit reason rather than to an AC or Open Question.
Both item ``text`` and atom ``text`` remain verbatim source excerpts; they are
not fields for normalized summaries.

Every source uses a dedicated UTF-8 acquisition artifact whose complete bytes
equal ``raw_text``.  A logical locator plus a manifest-owned hash is insufficient:
otherwise a truncated source can be re-hashed inside the same manifest and pass.
"""

from __future__ import annotations

import copy
import hashlib
import math
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path


SCHEMA_VERSION = "aem-guides-source-requirement-ledger-v1"
DISPOSITIONS = {"AC", "OQ", "OOS"}
AUTHORITIES = {"Proposed", "Confirmed"}

_SOURCE_ID_RE = re.compile(r"SRC-\d{2,}")
_REQUIREMENT_ID_RE = re.compile(r"REQ-\d{2,}")
_ATOM_ID_RE = re.compile(r"ATOM-\d{2,}")
_AC_ID_RE = re.compile(r"AC-\d{2}")
_OQ_ID_RE = re.compile(r"OQ-\d{2}")

# Exact technical tokens are protected automatically.  ``protected_exact`` can
# add product-specific identifiers that do not have a distinctive syntax.
_URL_RE = re.compile(r"https?://[^\s<>()]+")
_WINDOWS_PATH_RE = re.compile(
    r"\b[A-Za-z]:\\(?:[^\\\s\r\n:*?\"<>|]+\\)*[^\\\s\r\n:*?\"<>|]+"
)
_POSIX_PATH_RE = re.compile(r"(?<![\w.])/(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+")
_BACKTICK_RE = re.compile(r"`([^`\r\n]+)`")
_TECH_TOKEN_RE = re.compile(
    r"\b(?:[A-Za-z][A-Za-z0-9]*(?:[._:][A-Za-z0-9_-]+)+|"
    r"[a-z][a-z0-9]*(?:[A-Z][A-Za-z0-9]*)+)\b"
)
_SCOPE_TOKEN_RE = re.compile(
    r"\b(?:[A-Za-z][A-Za-z0-9]*-level|per-[A-Za-z][A-Za-z0-9]*)\b",
    re.IGNORECASE,
)
_SEMANTIC_TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+(?:[-_:][A-Za-z0-9]+)*"
)
_SEMANTIC_CLAUSE_SPLIT_RE = re.compile(
    r"(?<=[.!?;])\s+|\s+(?:but|however|otherwise|except)\s+",
    re.IGNORECASE,
)
_SEMANTIC_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "were",
        "when",
        "with",
    }
)
_SEMANTIC_CRITICAL_TOKENS = frozenset(
    {
        "after",
        "all",
        "any",
        "automatically",
        "before",
        "during",
        "each",
        "every",
        "fallback",
        "immediately",
        "never",
        "no",
        "not",
        "only",
        "preserve",
        "preserved",
        "reload",
        "retained",
        "until",
        "upgrade",
        "without",
    }
)
# Preserve every source clause through verbatim atoms, but require only a
# substantial lexical bridge from each atom into its AC/OQ.  Requiring every
# source word in tester-facing text recreates the long, review-rejected prose
# this skill is meant to simplify.  High-risk modifiers and exact identifiers
# remain mandatory below.
_MIN_TRACE_TOKEN_RATIO = 0.45


def is_present(manifest: object) -> bool:
    return isinstance(manifest, dict) and isinstance(
        manifest.get("source_requirement_ledger"), dict
    )


def is_required(manifest: object) -> bool:
    if not isinstance(manifest, dict):
        return False
    enumerated = manifest.get("enumerated_requirements")
    return isinstance(enumerated, dict) and enumerated.get("active") is True


def sha256_text(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _semantic_tokens(text: str) -> set[str]:
    return {
        match.group(0).casefold()
        for match in _SEMANTIC_TOKEN_RE.finditer(text)
        if match.group(0).casefold() not in _SEMANTIC_STOP_WORDS
    }


def _semantic_clauses(text: str) -> list[str]:
    return [
        clause.strip(" \t\r\n-*")
        for clause in _SEMANTIC_CLAUSE_SPLIT_RE.split(text)
        if clause.strip(" \t\r\n-*")
    ]


def _automatic_semantic_coverage(
    verbatim_text: str, atoms: list[dict], *, tag: str
) -> list[str]:
    """Reject atom sets that preserve only a convenient fragment of the source.

    Atoms collectively cover every meaningful token in every source clause.  In
    addition, each atom's trace terms must carry a substantial share of its
    meaningful tokens, and all high-risk modifiers must be explicit.  This
    remains domain-neutral: the vocabulary is extracted from the source at
    runtime.
    """
    problems: list[str] = []
    atom_token_union: set[str] = set()
    for atom in atoms:
        if isinstance(atom, dict) and isinstance(atom.get("text"), str):
            atom_token_union.update(_semantic_tokens(atom["text"]))

    for clause_index, clause in enumerate(_semantic_clauses(verbatim_text)):
        clause_tokens = _semantic_tokens(clause)
        if not clause_tokens:
            continue
        missing = sorted(clause_tokens - atom_token_union)
        if missing:
            problems.append(
                f"{tag} semantic clause {clause_index + 1} is not fully represented by atoms; "
                f"missing source tokens {missing!r}"
            )

    for atom_index, atom in enumerate(atoms):
        if not isinstance(atom, dict):
            continue
        atom_text = atom.get("text")
        if not isinstance(atom_text, str) or not atom_text.strip():
            continue
        atom_tokens = _semantic_tokens(atom_text)
        if not atom_tokens:
            continue
        all_terms = _string_list(atom.get("required_terms_all", [])) or []
        invented_all_terms = [
            term for term in all_terms if not _contains_folded(atom_text, term)
        ]
        if invented_all_terms:
            problems.append(
                f"{tag}.semantic_atoms[{atom_index}].required_terms_all must come "
                f"from atom text; invented terms {invented_all_terms!r}"
            )
        any_terms = _string_list(atom.get("required_terms_any", [])) or []
        source_any_terms = [
            term for term in any_terms if _contains_folded(atom_text, term)
        ]
        if len(source_any_terms) > 1:
            problems.append(
                f"{tag}.semantic_atoms[{atom_index}].required_terms_any contains "
                f"multiple independent source terms {source_any_terms!r}; move them "
                "to required_terms_all so one target alternative cannot hide another"
            )
        required_tokens = _semantic_tokens(
            "\n".join([*all_terms, *source_any_terms[:1]])
        )
        required_count = len(atom_tokens & required_tokens)
        minimum = max(1, math.ceil(len(atom_tokens) * _MIN_TRACE_TOKEN_RATIO))
        if required_count < minimum:
            problems.append(
                f"{tag}.semantic_atoms[{atom_index}] has weak semantic trace terms; "
                f"it carries {required_count}/{len(atom_tokens)} semantic tokens, "
                f"but at least {minimum} are required"
            )
        missing_critical = sorted(
            token
            for token in atom_tokens
            if (
                token in _SEMANTIC_CRITICAL_TOKENS
                or token.endswith("-level")
                or token.startswith("per-")
            )
            and token not in required_tokens
        )
        if missing_critical:
            problems.append(
                f"{tag}.semantic_atoms[{atom_index}] omits critical source terms "
                f"from required_terms_all: {missing_critical!r}"
            )
    return problems


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return None
    return list(value)


def _contains_folded(text: str, term: str) -> bool:
    """Match a semantic term as a phrase, not as part of another word.

    This prevents critical terms such as ``not`` or ``user`` from being
    satisfied by unrelated words such as ``notice`` or ``username``. Exact
    paths and identifiers are protected separately by ``_protected_exact``.
    """
    normalized = term.strip()
    if not normalized:
        return False
    simple_words = re.fullmatch(
        r"[A-Za-z0-9_-]+(?:\s+[A-Za-z0-9_-]+)*", normalized
    )
    if simple_words:
        patterns = []
        for word in normalized.split():
            suffix = r"(?:s|es|ed|d|ing|ly)?" if len(word) >= 3 else ""
            patterns.append(re.escape(word) + suffix)
        phrase = r"\s+".join(patterns)
    else:
        phrase = re.escape(normalized)
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9]){phrase}(?![A-Za-z0-9])",
            text,
            re.IGNORECASE,
        )
    )


def _protected_exact(verbatim_text: str, declared: object) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    declared_values = _string_list(declared)
    if declared is None:
        declared_values = []
    elif declared_values is None:
        problems.append("protected_exact must be a list of non-empty strings")
        declared_values = []

    found: list[str] = []
    for pattern in (
        _URL_RE,
        _WINDOWS_PATH_RE,
        _POSIX_PATH_RE,
        _TECH_TOKEN_RE,
        _SCOPE_TOKEN_RE,
    ):
        found.extend(match.group(0).rstrip(".,;)") for match in pattern.finditer(verbatim_text))
    found.extend(match.group(1) for match in _BACKTICK_RE.finditer(verbatim_text))
    for value in declared_values:
        if value not in verbatim_text:
            problems.append(f"protected_exact value {value!r} is not present verbatim in source text")
        found.append(value)
    ordinary_abbreviations = {"e.g", "i.e"}
    return list(
        dict.fromkeys(
            value
            for value in found
            if value and value.casefold() not in ordinary_abbreviations
        )
    ), problems


def _target_text(
    refs: list[str], mapping: Mapping[str, str] | None, *, label: str
) -> tuple[str, list[str]]:
    if mapping is None:
        return "", []
    missing = [ref for ref in refs if not str(mapping.get(ref, "")).strip()]
    if missing:
        return "", [f"references unknown or empty {label}: {', '.join(missing)}"]
    return "\n".join(str(mapping[ref]) for ref in refs), []


def _trace_atom(atom: dict, target_text: str, *, tag: str) -> list[str]:
    problems: list[str] = []
    all_terms = _string_list(atom.get("required_terms_all", []))
    any_terms = _string_list(atom.get("required_terms_any", []))
    if all_terms is None:
        problems.append(f"{tag}.required_terms_all must be a list of non-empty strings")
        all_terms = []
    if any_terms is None:
        problems.append(f"{tag}.required_terms_any must be a list of non-empty strings")
        any_terms = []
    if not all_terms and not any_terms:
        problems.append(
            f"{tag} requires required_terms_all and/or required_terms_any for semantic traceability"
        )
        return problems
    missing_all = [term for term in all_terms if not _contains_folded(target_text, term)]
    if missing_all:
        problems.append(
            f"{tag} loses required_terms_all {missing_all!r} from its fidelity target"
        )
    if any_terms and not any(_contains_folded(target_text, term) for term in any_terms):
        problems.append(
            f"{tag} loses every required_terms_any alternative {any_terms!r} from its fidelity target"
        )
    return problems


def _enumerated_items(block: object) -> list[dict]:
    if not isinstance(block, dict) or not isinstance(block.get("items"), list):
        return []
    return [item for item in block["items"] if isinstance(item, dict)]


def validate_manifest(
    manifest: object,
    *,
    ac_text_by_id: Mapping[str, str] | None = None,
    open_question_text_by_id: Mapping[str, str] | None = None,
) -> list[str]:
    """Validate ledger structure, source binding, and optional plan traceability.

    Passing AC/OQ maps activates semantic trace checks against the actual plan.
    Omitting them still validates the fail-closed source/hash/item contract.
    """
    if not isinstance(manifest, dict):
        return ["manifest must be an object"]
    enumerated = manifest.get("enumerated_requirements")
    required = is_required(manifest)
    ledger = manifest.get("source_requirement_ledger")
    if required and not isinstance(ledger, dict):
        return [
            "active enumerated_requirements requires source_requirement_ledger; "
            "fidelity applies even when accepted_uac_present is false"
        ]
    if ledger is None:
        return []
    if not isinstance(ledger, dict):
        return ["source_requirement_ledger must be a versioned JSON object"]

    problems: list[str] = []
    if ledger.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"source_requirement_ledger.schema_version must be {SCHEMA_VERSION}")

    sources = ledger.get("sources")
    if not isinstance(sources, list) or not sources:
        return problems + ["source_requirement_ledger.sources must be a non-empty list"]
    source_by_id: dict[str, dict] = {}
    for index, source in enumerate(sources):
        tag = f"source_requirement_ledger.sources[{index}]"
        if not isinstance(source, dict):
            problems.append(f"{tag} must be an object")
            continue
        source_id = str(source.get("id", ""))
        if not _SOURCE_ID_RE.fullmatch(source_id):
            problems.append(f"{tag}.id must use stable SRC-## form")
        elif source_id in source_by_id:
            problems.append(f"{tag}.id duplicates {source_id}")
        source_type = str(source.get("type", ""))
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", source_type):
            problems.append(f"{tag}.type must be a stable lower-case source type")
        if not str(source.get("locator", "")).strip():
            problems.append(f"{tag}.locator must be non-empty")
        raw_text = source.get("raw_text")
        if not isinstance(raw_text, str) or not raw_text:
            problems.append(f"{tag}.raw_text must be the exact non-empty source text")
            raw_text = ""
        expected_hash = sha256_text(raw_text)
        actual_hash = str(source.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", actual_hash):
            problems.append(f"{tag}.sha256 must be a lower-case SHA-256 hex digest")
        elif actual_hash != expected_hash:
            problems.append(f"{tag}.sha256 does not match the exact UTF-8 raw_text")

        artifact_path_text = str(source.get("artifact_path", "")).strip()
        artifact_hash = str(source.get("artifact_sha256", ""))
        artifact_bytes: bytes | None = None
        if not artifact_path_text:
            problems.append(
                f"{tag}.artifact_path must bind the source to a durable acquisition artifact"
            )
        else:
            artifact_path = Path(artifact_path_text)
            if not artifact_path.is_absolute():
                problems.append(f"{tag}.artifact_path must be absolute")
            elif not artifact_path.is_file():
                problems.append(f"{tag}.artifact_path does not exist or is not a file")
            else:
                try:
                    artifact_bytes = artifact_path.read_bytes()
                except OSError as exc:
                    problems.append(f"{tag}.artifact_path could not be read: {exc}")
        if not re.fullmatch(r"[0-9a-f]{64}", artifact_hash):
            problems.append(
                f"{tag}.artifact_sha256 must be a lower-case SHA-256 hex digest"
            )
        elif artifact_bytes is not None and artifact_hash != sha256_bytes(artifact_bytes):
            problems.append(
                f"{tag}.artifact_sha256 does not match the acquisition artifact bytes"
            )
        if artifact_bytes is not None and artifact_bytes != raw_text.encode("utf-8"):
            problems.append(
                f"{tag}.raw_text must exactly equal the complete UTF-8 acquisition artifact; "
                "a manifest-only truncation or rewrite is not allowed"
            )
        if source_id and source_id not in source_by_id:
            source_by_id[source_id] = source

    items = ledger.get("items")
    if not isinstance(items, list) or not items:
        return problems + ["source_requirement_ledger.items must be a non-empty ordered list"]
    enum_items = _enumerated_items(enumerated)
    if required and len(items) != len(enum_items):
        problems.append(
            "source_requirement_ledger.items must contain exactly one item for each "
            f"enumerated requirement; ledger={len(items)}, enumerated={len(enum_items)}"
        )

    seen_item_ids: set[str] = set()
    seen_atom_ids: set[str] = set()
    expected_disposition = {
        "COVERED_BY_AC": "AC",
        "OPEN_QUESTION": "OQ",
        "OUT_OF_SCOPE": "OOS",
    }
    for index, item in enumerate(items):
        tag = f"source_requirement_ledger.items[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{tag} must be an object")
            continue
        item_id = str(item.get("id", ""))
        if not _REQUIREMENT_ID_RE.fullmatch(item_id):
            problems.append(f"{tag}.id must use stable REQ-## form")
        elif item_id in seen_item_ids:
            problems.append(f"{tag}.id duplicates {item_id}")
        seen_item_ids.add(item_id)

        enum_item = enum_items[index] if index < len(enum_items) else None
        if enum_item is not None:
            enum_id = str(enum_item.get("id", ""))
            if item_id != enum_id:
                problems.append(
                    f"{tag}.id must preserve enumerated source order; expected {enum_id!r}"
                )
            if item.get("source_index") != enum_item.get("source_index"):
                problems.append(
                    f"{tag}.source_index must exactly match the corresponding enumerated requirement"
                )
            if item.get("text") != enum_item.get("text"):
                problems.append(
                    f"{tag}.text must exactly match enumerated requirement {enum_id or index + 1} text"
                )
        source_index = item.get("source_index")
        if not isinstance(source_index, int) or isinstance(source_index, bool) or source_index < 1:
            problems.append(f"{tag}.source_index must be a positive integer")

        source_id = str(item.get("source_id", ""))
        source = source_by_id.get(source_id)
        if source is None:
            problems.append(f"{tag}.source_id must reference a declared source record")
            raw_text = ""
        else:
            raw_text = str(source.get("raw_text", ""))
        verbatim = item.get("verbatim_text")
        if not isinstance(verbatim, str) or not verbatim:
            problems.append(f"{tag}.verbatim_text must be non-empty")
            verbatim = ""
        elif verbatim not in raw_text:
            problems.append(f"{tag}.verbatim_text is not an exact substring of source {source_id}")
        if not isinstance(item.get("text"), str) or not item.get("text"):
            problems.append(f"{tag}.text must be non-empty")
        elif item.get("text") != verbatim:
            problems.append(
                f"{tag}.text must exactly equal verbatim_text; normalized or rewritten source text is not fidelity"
            )

        authority = item.get("authority")
        if authority not in AUTHORITIES:
            problems.append(
                f"{tag}.authority must be Proposed or Confirmed; authority is separate from fidelity"
            )
        disposition = item.get("disposition")
        if disposition not in DISPOSITIONS:
            problems.append(f"{tag}.disposition must be one of {sorted(DISPOSITIONS)}")
            disposition = ""
        if enum_item is not None:
            expected = expected_disposition.get(enum_item.get("disposition"))
            if expected and disposition != expected:
                problems.append(
                    f"{tag}.disposition {disposition!r} does not match enumerated disposition {expected!r}"
                )

        target_text = ""
        refs: list[str] = []
        target_failures: list[str] = []
        if disposition == "AC":
            refs = _string_list(item.get("ac_refs"))
            if not refs or any(not _AC_ID_RE.fullmatch(ref) for ref in refs):
                problems.append(f"{tag}: AC disposition requires canonical non-empty ac_refs")
                refs = []
            if enum_item is not None and refs != list(enum_item.get("ac_refs") or []):
                problems.append(f"{tag}.ac_refs must exactly match the enumerated AC mapping")
            target_text, target_failures = _target_text(
                refs, ac_text_by_id, label="AC references"
            )
        elif disposition == "OQ":
            oq_ref = str(item.get("open_question_ref", ""))
            if not _OQ_ID_RE.fullmatch(oq_ref):
                problems.append(f"{tag}: OQ disposition requires a canonical open_question_ref")
                refs = []
            else:
                refs = [oq_ref]
            if enum_item is not None and oq_ref != str(enum_item.get("open_question_ref", "")):
                problems.append(
                    f"{tag}.open_question_ref must exactly match the enumerated Open Question mapping"
                )
            target_text, target_failures = _target_text(
                refs, open_question_text_by_id, label="Open Question references"
            )
        elif disposition == "OOS":
            reason = str(item.get("reason", ""))
            if not reason.strip():
                problems.append(f"{tag}: OOS disposition requires a non-empty reason")
            target_text = reason
        problems.extend(f"{tag} {failure}" for failure in target_failures)

        atoms = item.get("semantic_atoms")
        if not isinstance(atoms, list) or not atoms:
            problems.append(f"{tag}.semantic_atoms must be a non-empty list")
            atoms = []
        fidelity_targets: list[str] = [target_text] if target_text else []
        conflict_targets: list[tuple[str, str, str]] = []
        for atom_index, atom in enumerate(atoms):
            atom_tag = f"{tag}.semantic_atoms[{atom_index}]"
            if not isinstance(atom, dict):
                problems.append(f"{atom_tag} must be an object")
                continue
            atom_id = str(atom.get("id", ""))
            if not _ATOM_ID_RE.fullmatch(atom_id):
                problems.append(f"{atom_tag}.id must use stable ATOM-## form")
            elif atom_id in seen_atom_ids:
                problems.append(f"{atom_tag}.id duplicates {atom_id}")
            seen_atom_ids.add(atom_id)
            atom_text = atom.get("text")
            if not isinstance(atom_text, str) or not atom_text.strip():
                problems.append(f"{atom_tag}.text must be non-empty")
            elif atom_text not in verbatim:
                problems.append(
                    f"{atom_tag}.text must be an exact substring of the item's verbatim source text"
                )

            atom_target = target_text
            if atom.get("evidence_conflict") is True:
                if disposition == "AC":
                    if authority != "Proposed":
                        problems.append(
                            f"{atom_tag}: an AC evidence_conflict requires authority Proposed"
                        )
                    if ac_text_by_id is not None:
                        non_proposed = [
                            ref
                            for ref in refs
                            if "[Proposed]" not in str(ac_text_by_id.get(ref, ""))
                        ]
                        if non_proposed:
                            problems.append(
                                f"{atom_tag}: evidence_conflict AC references must remain "
                                f"[Proposed]: {non_proposed}"
                            )
                        problems.extend(
                            _trace_atom(
                                atom,
                                target_text,
                                tag=f"{atom_tag} Proposed AC",
                            )
                        )
                oq_ref = str(atom.get("open_question_ref", ""))
                if not _OQ_ID_RE.fullmatch(oq_ref):
                    problems.append(
                        f"{atom_tag}: evidence_conflict requires a canonical open_question_ref"
                    )
                    atom_target = ""
                else:
                    atom_target, oq_failures = _target_text(
                        [oq_ref], open_question_text_by_id, label="conflict Open Question"
                    )
                    problems.extend(f"{atom_tag} {failure}" for failure in oq_failures)
                if atom_target:
                    fidelity_targets.append(atom_target)
                if disposition == "AC":
                    conflict_targets.append((target_text, atom_target, atom_tag))
            elif atom.get("evidence_conflict") not in (None, False):
                problems.append(f"{atom_tag}.evidence_conflict must be true or false")

            # Structural validation runs without plan maps; trace validation starts
            # only when the relevant map was provided by run_gates.
            trace_enabled = disposition == "OOS" or (
                atom.get("evidence_conflict") is True
                and open_question_text_by_id is not None
            ) or (
                atom.get("evidence_conflict") is not True
                and (
                    (disposition == "AC" and ac_text_by_id is not None)
                    or (disposition == "OQ" and open_question_text_by_id is not None)
                )
            )
            if trace_enabled:
                problems.extend(_trace_atom(atom, atom_target, tag=atom_tag))
            else:
                # Still require a declared trace contract before plan text is available.
                all_terms = _string_list(atom.get("required_terms_all", []))
                any_terms = _string_list(atom.get("required_terms_any", []))
                if all_terms is None or any_terms is None or not (all_terms or any_terms):
                    problems.append(
                        f"{atom_tag} requires required_terms_all and/or required_terms_any"
                    )

        problems.extend(
            _automatic_semantic_coverage(
                verbatim,
                [atom for atom in atoms if isinstance(atom, dict)],
                tag=tag,
            )
        )

        protected, protected_problems = _protected_exact(
            verbatim, item.get("protected_exact")
        )
        problems.extend(f"{tag}.{problem}" for problem in protected_problems)
        if disposition == "OOS" or ac_text_by_id is not None or open_question_text_by_id is not None:
            surviving_text = "\n".join(fidelity_targets)
            for exact in protected:
                if exact not in surviving_text:
                    problems.append(
                        f"{tag} drops protected exact identifier/path {exact!r} from its AC/OQ/OOS disposition"
                    )
                for ac_target, oq_target, atom_tag in conflict_targets:
                    if exact not in ac_target:
                        problems.append(
                            f"{atom_tag} drops protected exact identifier/path {exact!r} "
                            "from the Proposed AC"
                        )
                    if exact not in oq_target:
                        problems.append(
                            f"{atom_tag} drops protected exact identifier/path {exact!r} "
                            "from the conflict Open Question"
                        )

    return problems


def summarize(manifest: dict) -> str:
    problems = validate_manifest(manifest)
    lines = [
        "SourceRequirementFidelity: "
        f"required={is_required(manifest)} present={is_present(manifest)}"
    ]
    lines.extend(f"  FAIL {problem}" for problem in problems)
    return "\n".join(lines)


def run_self_tests() -> None:
    """Exercise the hardening invariants without depending on the shared suite."""
    assert not _contains_folded("a notice is shown", "not")
    assert not _contains_folded("the username is saved", "user")
    assert _contains_folded("the logged-in user is active", "user")
    raw_text = "Friendly names are a user-level setting for the logged-in user."
    with tempfile.TemporaryDirectory() as temporary:
        artifact = Path(temporary).resolve() / "source.txt"
        artifact.write_bytes(raw_text.encode("utf-8"))
        manifest = {
            "accepted_uac_present": False,
            "enumerated_requirements": {
                "schema_version": "aem-guides-enumerated-requirements-v1",
                "active": True,
                "source_ref": "durable acquisition capture",
                "source_item_count": 1,
                "source_complete": True,
                "items": [
                    {
                        "id": "REQ-01",
                        "source_index": 1,
                        "text": raw_text,
                        "disposition": "COVERED_BY_AC",
                        "ac_refs": ["AC-01"],
                    }
                ],
            },
            "source_requirement_ledger": {
                "schema_version": SCHEMA_VERSION,
                "sources": [
                    {
                        "id": "SRC-01",
                        "type": "human_feedback",
                        "locator": "durable acquisition capture",
                        "raw_text": raw_text,
                        "sha256": sha256_text(raw_text),
                        "artifact_path": str(artifact),
                        "artifact_sha256": sha256_bytes(artifact.read_bytes()),
                    }
                ],
                "items": [
                    {
                        "id": "REQ-01",
                        "source_id": "SRC-01",
                        "source_index": 1,
                        "verbatim_text": raw_text,
                        "text": raw_text,
                        "authority": "Proposed",
                        "disposition": "AC",
                        "ac_refs": ["AC-01"],
                        "semantic_atoms": [
                            {
                                "id": "ATOM-01",
                                "text": raw_text,
                                "required_terms_all": [
                                    "Friendly names",
                                    "user-level setting",
                                    "logged-in user",
                                ],
                            }
                        ],
                    }
                ],
            },
        }
        proposed_ac = {
            "AC-01": (
                "AC-01 [Proposed]: Friendly names are a user-level setting "
                "for the logged-in user."
            )
        }
        assert validate_manifest(
            manifest,
            ac_text_by_id=proposed_ac,
            open_question_text_by_id={},
        ) == [], "complete artifact-bound source ledger must pass"

        synonym = copy.deepcopy(manifest)
        synonym_atom = synonym["source_requirement_ledger"]["items"][0][
            "semantic_atoms"
        ][0]
        synonym_atom["required_terms_all"] = [
            "Friendly names",
            "user-level setting",
        ]
        synonym_atom["required_terms_any"] = ["logged-in user", "current user"]
        assert validate_manifest(
            synonym,
            ac_text_by_id={
                "AC-01": (
                    "AC-01 [Proposed]: Friendly names are a user-level setting "
                    "for the current user."
                )
            },
            open_question_text_by_id={},
        ) == [], "one source term may declare an explicit target synonym alternative"

        truncated = copy.deepcopy(manifest)
        truncated_text = "Friendly names are a user-level setting."
        truncated_source = truncated["source_requirement_ledger"]["sources"][0]
        truncated_source["raw_text"] = truncated_text
        truncated_source["sha256"] = sha256_text(truncated_text)
        truncation_failures = validate_manifest(truncated)
        assert any(
            "manifest-only truncation" in problem for problem in truncation_failures
        ), "truncating and re-hashing only the manifest must fail artifact binding"

        weak = copy.deepcopy(manifest)
        weak_atom = weak["source_requirement_ledger"]["items"][0]["semantic_atoms"][0]
        weak_atom["text"] = "Friendly names"
        weak_atom["required_terms_all"] = ["Friendly names"]
        weak_failures = validate_manifest(weak)
        assert any(
            "semantic clause" in problem for problem in weak_failures
        ), "weak atom fragments must not stand in for the complete source clause"

        weak_terms = copy.deepcopy(manifest)
        weak_terms_atom = weak_terms["source_requirement_ledger"]["items"][0][
            "semantic_atoms"
        ][0]
        weak_terms_atom["required_terms_all"] = ["Friendly names"]
        weak_term_failures = validate_manifest(weak_terms)
        assert any(
            "weak semantic trace terms" in problem
            for problem in weak_term_failures
        ), "a full atom with an underspecified trace contract must fail"

        bad_artifact_hash = copy.deepcopy(manifest)
        bad_artifact_hash["source_requirement_ledger"]["sources"][0][
            "artifact_sha256"
        ] = "0" * 64
        assert any(
            "artifact_sha256 does not match" in problem
            for problem in validate_manifest(bad_artifact_hash)
        ), "the acquisition artifact hash must be verified"

        conflict = copy.deepcopy(manifest)
        conflict_atom = conflict["source_requirement_ledger"]["items"][0][
            "semantic_atoms"
        ][0]
        conflict_atom["evidence_conflict"] = True
        conflict_atom["open_question_ref"] = "OQ-01"
        conflict_question = {
            "OQ-01": (
                "Are friendly names a user-level setting for the logged-in user? "
                "QA impact: the answer changes user-isolation coverage."
            )
        }
        substituted_ac = {
            "AC-01": (
                "AC-01 [Proposed]: Friendly names use the active folder profile."
            )
        }
        conflict_failures = validate_manifest(
            conflict,
            ac_text_by_id=substituted_ac,
            open_question_text_by_id=conflict_question,
        )
        assert any(
            "Proposed AC" in problem and "required_terms_all" in problem
            for problem in conflict_failures
        ), "a conflict must not replace the Proposed AC with implementation behavior"
        assert validate_manifest(
            conflict,
            ac_text_by_id=proposed_ac,
            open_question_text_by_id=conflict_question,
        ) == [], "source terms in both Proposed AC and conflict question must pass"

        confirmed_conflict = copy.deepcopy(conflict)
        confirmed_conflict["source_requirement_ledger"]["items"][0][
            "authority"
        ] = "Confirmed"
        assert any(
            "authority Proposed" in problem
            for problem in validate_manifest(
                confirmed_conflict,
                ac_text_by_id={
                    "AC-01": proposed_ac["AC-01"].replace(
                        "[Proposed]", "[Confirmed]"
                    )
                },
                open_question_text_by_id=conflict_question,
            )
        ), "an unresolved evidence conflict cannot be a Confirmed AC"


if __name__ == "__main__":
    run_self_tests()
    print("SOURCE REQUIREMENT FIDELITY SELF-TESTS PASSED")
