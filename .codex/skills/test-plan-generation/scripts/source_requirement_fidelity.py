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
AUTHORITATIVE_SOURCE_COVERAGE_SCHEMA = (
    "aem-guides-authoritative-source-coverage-v1"
)
DISPOSITIONS = {"AC", "OQ", "OOS"}
AUTHORITIES = {"Proposed", "Confirmed"}
AUTHORITATIVE_SOURCE_KINDS = {
    "JIRA_DESCRIPTION",
    "JIRA_COMMENT",
    "ANALYSED_ATTACHMENT",
}
AUTHORITATIVE_FACT_DESTINATIONS = {
    "ACCEPTANCE_CRITERION",
    "OPEN_QUESTION",
    "OUT_OF_SCOPE",
    "NOT_MATERIAL",
}

_SOURCE_ID_RE = re.compile(r"SRC-\d{2,}")
_REQUIREMENT_ID_RE = re.compile(r"REQ-\d{2,}")
_ATOM_ID_RE = re.compile(r"ATOM-\d{2,}")
_AUTHORITATIVE_SOURCE_ID_RE = re.compile(r"TSRC-\d{2,}")
_AUTHORITATIVE_FACT_ID_RE = re.compile(r"TSF-\d{2,}")
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


def _issue_key(manifest: dict) -> str:
    issue = manifest.get("issue")
    if isinstance(issue, dict):
        value = issue.get("key")
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("jira_key", "issue_key"):
        value = manifest.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _comment_records(value: object) -> list[object]:
    if isinstance(value, dict):
        for field in ("comments", "values"):
            nested = value.get(field)
            if isinstance(nested, list):
                return nested
        return [value]
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _comment_text(record: object) -> str:
    if isinstance(record, str):
        return record
    if not isinstance(record, dict):
        return ""
    for field in ("body_text", "body", "raw_text", "text", "comment"):
        value = record.get(field)
        if isinstance(value, str) and value:
            return value
    return ""


def _stable_source_part(record: object, index: int) -> str:
    if isinstance(record, dict):
        for field in ("id", "comment_id", "source_ref", "filename", "name"):
            value = record.get(field)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()
    return str(index)


def authoritative_ticket_sources(manifest: object) -> list[dict]:
    """Return the exact ticket sources that must be atomized before coverage.

    These are current Jira intake sources, not discovery hypotheses.  A source
    record carries aliases only to accommodate the stable source references used
    by existing ``contract_facts`` records; the canonical ``source_ref`` remains
    deterministic and source-specific.
    """
    if not isinstance(manifest, dict):
        return []

    issue = manifest.get("issue")
    issue = issue if isinstance(issue, dict) else {}
    issue_key = _issue_key(manifest)
    records: list[dict] = []

    description = issue.get("description")
    if isinstance(description, str) and description:
        aliases = {"issue.description"}
        if issue_key:
            aliases.add(f"Jira description {issue_key}")
        records.append(
            {
                "source_ref": "issue.description",
                "source_kind": "JIRA_DESCRIPTION",
                "raw_text": description,
                "aliases": aliases,
            }
        )

    comments_value = issue.get("comments")
    comments_prefix = "issue.comments"
    if not _comment_records(comments_value):
        comments_value = manifest.get("jira_comments")
        comments_prefix = "jira_comments"
    for index, comment in enumerate(_comment_records(comments_value), 1):
        text = _comment_text(comment)
        if not text:
            continue
        part = _stable_source_part(comment, index)
        source_ref = f"{comments_prefix}[{part}]"
        aliases = {source_ref}
        if issue_key:
            aliases.add(f"Jira comment {part} {issue_key}")
        records.append(
            {
                "source_ref": source_ref,
                "source_kind": "JIRA_COMMENT",
                "raw_text": text,
                "aliases": aliases,
            }
        )

    attachments = manifest.get("attachments")
    if isinstance(attachments, list):
        for index, attachment in enumerate(attachments, 1):
            if not isinstance(attachment, dict):
                continue
            if attachment.get("analyzed") is not True and attachment.get("analysed") is not True:
                continue
            part = _stable_source_part(attachment, index)
            supplied_ref = attachment.get("source_ref")
            source_ref = (
                str(supplied_ref).strip()
                if isinstance(supplied_ref, str) and supplied_ref.strip()
                else f"attachment:{part}"
            )
            raw_text = next(
                (
                    attachment.get(field)
                    for field in (
                        "raw_text",
                        "extracted_text",
                        "ocr_text",
                        "text",
                        "analysis_text",
                        "analysis",
                    )
                    if isinstance(attachment.get(field), str)
                    and str(attachment.get(field)).strip()
                ),
                None,
            )
            aliases = {source_ref, str(part)}
            for field in ("id", "name", "filename"):
                value = attachment.get(field)
                if isinstance(value, (str, int)) and str(value).strip():
                    aliases.add(str(value).strip())
            records.append(
                {
                    "source_ref": source_ref,
                    "source_kind": "ANALYSED_ATTACHMENT",
                    "raw_text": raw_text,
                    "aliases": aliases,
                }
            )
    return records


def authoritative_source_coverage_required(manifest: object) -> bool:
    return bool(
        isinstance(manifest, dict)
        and manifest.get("schema_version") == "aem-guides-evidence-manifest-v3"
        and manifest.get("behaviour_matters", True) is not False
        and authoritative_ticket_sources(manifest)
    )


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


def _concrete_reason(value: object) -> bool:
    text = str(value or "").strip()
    return len(text) >= 12 and text.casefold().rstrip(".") not in {
        "not material",
        "out of scope",
        "not applicable",
        "unrelated",
    }


def _authoritative_fact_coverage(
    raw_text: str, atoms: list[dict], *, tag: str
) -> list[str]:
    """Require atoms to account for every meaningful source clause.

    This is deliberately source-completeness validation, not an NLP claim that
    every word is an acceptance requirement. Authors can retain non-material
    context with a concrete reason, but they cannot silently omit a clause from
    the intake record.
    """
    problems: list[str] = []
    atom_tokens: set[str] = set()
    for atom in atoms:
        text = atom.get("verbatim_text") if isinstance(atom, dict) else None
        if isinstance(text, str):
            atom_tokens.update(_semantic_tokens(text))
    for index, clause in enumerate(_semantic_clauses(raw_text), 1):
        clause_tokens = _semantic_tokens(clause)
        if not clause_tokens:
            continue
        missing = sorted(clause_tokens - atom_tokens)
        if missing:
            problems.append(
                f"{tag} source clause {index} is not fully atomized; missing "
                f"source tokens {missing!r}"
            )
    return problems


def _fact_destination_ref(fact: Mapping) -> tuple[str, list[str]]:
    destination = str(fact.get("destination", ""))
    if destination == "ACCEPTANCE_CRITERION":
        value = str(fact.get("ac_ref", "")).strip()
        return destination, [value] if value else []
    if destination == "OPEN_QUESTION":
        value = str(fact.get("open_question_ref", "")).strip()
        return destination, [value] if value else []
    if destination == "OUT_OF_SCOPE":
        value = str(fact.get("out_of_scope_ref", "")).strip()
        return destination, [value] if value else []
    return destination, []


def validate_authoritative_source_coverage(
    manifest: object,
    *,
    ac_text_by_id: Mapping[str, str] | None = None,
    open_question_text_by_id: Mapping[str, str] | None = None,
) -> list[str]:
    """Verify that authoritative ticket facts reach a direct UAC destination.

    This extends the existing source-fidelity path. It binds the full Jira
    description, comments, and analysed attachment text to ``contract_facts``;
    it does not create a hypothesis-based scope route. Discovery hypotheses may
    widen investigation, but cannot be used as a material source fact's
    destination.
    """
    if not isinstance(manifest, dict):
        return ["manifest must be an object"]

    required = authoritative_source_coverage_required(manifest)
    block = manifest.get("authoritative_source_coverage")
    if required and not isinstance(block, dict):
        return [
            "authoritative Jira intake requires authoritative_source_coverage; "
            "atomize every material description, comment, and analysed-attachment "
            "fact before discovery hypotheses are evaluated"
        ]
    if block is None:
        return []
    if not isinstance(block, dict):
        return ["authoritative_source_coverage must be a versioned JSON object"]

    problems: list[str] = []
    if block.get("schema_version") != AUTHORITATIVE_SOURCE_COVERAGE_SCHEMA:
        problems.append(
            "authoritative_source_coverage.schema_version must be "
            f"{AUTHORITATIVE_SOURCE_COVERAGE_SCHEMA}"
        )

    expected_sources = authoritative_ticket_sources(manifest)
    expected_by_ref: dict[str, dict] = {}
    for source in expected_sources:
        ref = str(source.get("source_ref", ""))
        if ref in expected_by_ref:
            problems.append(
                f"authoritative ticket intake duplicates source reference {ref!r}; "
                "use stable distinct comment or attachment identifiers"
            )
        else:
            expected_by_ref[ref] = source

    sources = block.get("sources")
    if not isinstance(sources, list) or not sources:
        return problems + [
            "authoritative_source_coverage.sources must be a non-empty list"
        ]

    declared_sources: dict[str, dict] = {}
    source_by_id: dict[str, dict] = {}
    for index, source in enumerate(sources):
        tag = f"authoritative_source_coverage.sources[{index}]"
        if not isinstance(source, dict):
            problems.append(f"{tag} must be an object")
            continue
        source_id = str(source.get("source_id", ""))
        if not _AUTHORITATIVE_SOURCE_ID_RE.fullmatch(source_id):
            problems.append(f"{tag}.source_id must use stable TSRC-## form")
        elif source_id in source_by_id:
            problems.append(f"{tag}.source_id duplicates {source_id}")
        source_ref = str(source.get("source_ref", "")).strip()
        if not source_ref:
            problems.append(f"{tag}.source_ref must name the exact Jira intake source")
            continue
        if source_ref in declared_sources:
            problems.append(f"{tag}.source_ref duplicates {source_ref}")
            continue
        declared_sources[source_ref] = source
        source_by_id[source_id] = source
        expected = expected_by_ref.get(source_ref)
        if expected is None:
            problems.append(
                f"{tag}.source_ref {source_ref!r} is not a current Jira description, "
                "comment, or analysed attachment source"
            )
            continue
        expected_kind = expected["source_kind"]
        if source.get("source_kind") != expected_kind:
            problems.append(
                f"{tag}.source_kind must be {expected_kind} for {source_ref}"
            )
        if source.get("source_kind") not in AUTHORITATIVE_SOURCE_KINDS:
            problems.append(
                f"{tag}.source_kind must be one of {sorted(AUTHORITATIVE_SOURCE_KINDS)}"
            )
        expected_text = expected.get("raw_text")
        if not isinstance(expected_text, str) or not expected_text:
            problems.append(
                f"{tag}: analysed attachment {source_ref!r} has no retained "
                "analysis text; preserve the inspected facts in raw_text, "
                "extracted_text, ocr_text, text, analysis_text, or analysis before "
                "it can be atomized"
            )
            expected_text = ""
        raw_text = source.get("raw_text")
        if not isinstance(raw_text, str) or not raw_text:
            problems.append(f"{tag}.raw_text must be the exact non-empty intake text")
            raw_text = ""
        elif raw_text != expected_text:
            problems.append(
                f"{tag}.raw_text must exactly equal current Jira intake source {source_ref!r}"
            )
        actual_hash = str(source.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", actual_hash):
            problems.append(f"{tag}.sha256 must be a lower-case SHA-256 hex digest")
        elif actual_hash != sha256_text(raw_text):
            problems.append(f"{tag}.sha256 does not match the exact UTF-8 raw_text")
        if source.get("inspected") is not True:
            problems.append(
                f"{tag}.inspected must be true; source facts cannot be inferred from "
                "a Jira field name or attachment filename"
            )
        if source.get("atomization_complete") is not True:
            problems.append(
                f"{tag}.atomization_complete must be true after every source clause "
                "has been classified"
            )

    missing_sources = sorted(set(expected_by_ref) - set(declared_sources))
    if missing_sources:
        problems.append(
            "authoritative_source_coverage omits current Jira intake source(s): "
            + ", ".join(missing_sources)
        )

    facts_block = manifest.get("contract_facts")
    facts = facts_block.get("facts") if isinstance(facts_block, dict) else []
    fact_by_id = {
        str(fact.get("fact_id")): fact
        for fact in facts or []
        if isinstance(fact, Mapping) and str(fact.get("fact_id", "")).strip()
    }

    atoms = block.get("facts")
    if not isinstance(atoms, list) or not atoms:
        return problems + [
            "authoritative_source_coverage.facts must be a non-empty ordered list"
        ]

    atoms_by_source: dict[str, list[dict]] = {}
    referenced_fact_ids: set[str] = set()
    seen_atom_ids: set[str] = set()
    for index, atom in enumerate(atoms):
        tag = f"authoritative_source_coverage.facts[{index}]"
        if not isinstance(atom, dict):
            problems.append(f"{tag} must be an object")
            continue
        atom_id = str(atom.get("fact_id", ""))
        if not _AUTHORITATIVE_FACT_ID_RE.fullmatch(atom_id):
            problems.append(f"{tag}.fact_id must use stable TSF-## form")
        elif atom_id in seen_atom_ids:
            problems.append(f"{tag}.fact_id duplicates {atom_id}")
        seen_atom_ids.add(atom_id)

        source_id = str(atom.get("source_id", ""))
        source = source_by_id.get(source_id)
        if source is None:
            problems.append(f"{tag}.source_id must reference a declared source")
            raw_text = ""
            source_ref = ""
        else:
            raw_text = str(source.get("raw_text", ""))
            source_ref = str(source.get("source_ref", ""))
        atoms_by_source.setdefault(source_ref, []).append(atom)

        verbatim = atom.get("verbatim_text")
        if not isinstance(verbatim, str) or not verbatim.strip():
            problems.append(f"{tag}.verbatim_text must be a non-empty exact source excerpt")
            verbatim = ""
        elif verbatim not in raw_text:
            problems.append(
                f"{tag}.verbatim_text is not an exact substring of source {source_id}"
            )
        if not isinstance(atom.get("material"), bool):
            problems.append(f"{tag}.material must explicitly be true or false")
            material = False
        else:
            material = atom["material"]
        destination = str(atom.get("destination", ""))
        if destination not in AUTHORITATIVE_FACT_DESTINATIONS:
            problems.append(
                f"{tag}.destination must be one of "
                f"{sorted(AUTHORITATIVE_FACT_DESTINATIONS)}"
            )
            destination = ""
        if atom.get("hypothesis_refs") not in (None, []):
            problems.append(
                f"{tag}.hypothesis_refs is not allowed: coverage hypotheses may widen "
                "investigation but cannot select or disposition authoritative ticket scope"
            )

        if not material:
            if destination != "NOT_MATERIAL":
                problems.append(
                    f"{tag}: a non-material intake atom must use destination NOT_MATERIAL"
                )
            if not _concrete_reason(atom.get("materiality_reason")):
                problems.append(
                    f"{tag}.materiality_reason must concretely explain why this exact "
                    "source fact is not a ticket contract"
                )
            if atom.get("contract_fact_refs") not in (None, []):
                problems.append(
                    f"{tag}: a non-material intake atom must not map to contract_facts"
                )
            continue

        if destination not in {
            "ACCEPTANCE_CRITERION",
            "OPEN_QUESTION",
            "OUT_OF_SCOPE",
        }:
            problems.append(
                f"{tag}: every material source fact must map to an AC, a genuine "
                "Open Question, or an explicit out-of-scope disposition"
            )
        fact_refs = _string_list(atom.get("contract_fact_refs"))
        if not fact_refs:
            problems.append(
                f"{tag}.contract_fact_refs must bind every material source fact to "
                "the existing contract-facts and promotion path"
            )
            fact_refs = []

        target_text = ""
        refs: list[str] = []
        if destination == "ACCEPTANCE_CRITERION":
            refs = _string_list(atom.get("ac_refs")) or []
            if not refs or any(not _AC_ID_RE.fullmatch(ref) for ref in refs):
                problems.append(
                    f"{tag}: ACCEPTANCE_CRITERION requires canonical non-empty ac_refs"
                )
                refs = []
            target_text, target_problems = _target_text(
                refs, ac_text_by_id, label="AC references"
            )
            problems.extend(f"{tag} {problem}" for problem in target_problems)
        elif destination == "OPEN_QUESTION":
            ref = str(atom.get("open_question_ref", ""))
            if not _OQ_ID_RE.fullmatch(ref):
                problems.append(
                    f"{tag}: OPEN_QUESTION requires a canonical open_question_ref"
                )
            else:
                refs = [ref]
            target_text, target_problems = _target_text(
                refs, open_question_text_by_id, label="Open Question references"
            )
            problems.extend(f"{tag} {problem}" for problem in target_problems)
        elif destination == "OUT_OF_SCOPE":
            target_text = str(atom.get("reason", ""))
            if not _concrete_reason(target_text):
                problems.append(
                    f"{tag}: OUT_OF_SCOPE requires a concrete source-backed reason"
                )

        for fact_ref in fact_refs:
            fact = fact_by_id.get(fact_ref)
            if not isinstance(fact, Mapping):
                problems.append(
                    f"{tag}.contract_fact_refs references unknown contract fact {fact_ref!r}"
                )
                continue
            referenced_fact_ids.add(fact_ref)
            fact_source_ref = str(fact.get("source_ref", ""))
            expected = expected_by_ref.get(source_ref, {})
            aliases = set(expected.get("aliases", set()))
            if fact_source_ref not in aliases:
                problems.append(
                    f"{tag}: contract fact {fact_ref} is bound to {fact_source_ref!r}, "
                    f"not the atomized source {source_ref!r}"
                )
            literal = str(fact.get("literal", ""))
            if literal and literal not in verbatim:
                problems.append(
                    f"{tag}: contract fact {fact_ref}.literal must remain inside this "
                    "exact source atom"
                )
            fact_destination, fact_refs_for_destination = _fact_destination_ref(fact)
            if fact_destination != destination:
                problems.append(
                    f"{tag}: contract fact {fact_ref} destination {fact_destination!r} "
                    f"does not match source-fact destination {destination!r}"
                )
            elif destination in {"ACCEPTANCE_CRITERION", "OPEN_QUESTION"} and not set(
                fact_refs_for_destination
            ).issubset(set(refs)):
                problems.append(
                    f"{tag}: contract fact {fact_ref} destination reference must be "
                    "preserved by the source-fact mapping"
                )
            elif destination == "OUT_OF_SCOPE" and not fact_refs_for_destination:
                problems.append(
                    f"{tag}: contract fact {fact_ref} needs its explicit "
                    "out_of_scope_ref"
                )

        atom_for_trace = {
            "text": verbatim,
            "required_terms_all": atom.get("required_terms_all", []),
            "required_terms_any": atom.get("required_terms_any", []),
        }
        semantic_problems = _automatic_semantic_coverage(
            verbatim, [atom_for_trace], tag=tag
        )
        problems.extend(semantic_problems)
        trace_enabled = destination == "OUT_OF_SCOPE" or (
            destination == "ACCEPTANCE_CRITERION" and ac_text_by_id is not None
        ) or (
            destination == "OPEN_QUESTION" and open_question_text_by_id is not None
        )
        if trace_enabled:
            problems.extend(_trace_atom(atom_for_trace, target_text, tag=tag))
        else:
            all_terms = _string_list(atom.get("required_terms_all", []))
            any_terms = _string_list(atom.get("required_terms_any", []))
            if all_terms is None or any_terms is None or not (all_terms or any_terms):
                problems.append(
                    f"{tag} requires required_terms_all and/or required_terms_any"
                )

        protected, protected_problems = _protected_exact(
            verbatim, atom.get("protected_exact")
        )
        problems.extend(f"{tag}.{problem}" for problem in protected_problems)
        if trace_enabled:
            for exact in protected:
                if exact not in target_text:
                    problems.append(
                        f"{tag} drops protected exact identifier/path {exact!r} "
                        "from its AC/Open Question/out-of-scope disposition"
                    )

    for source_ref, expected in expected_by_ref.items():
        raw_text = expected.get("raw_text")
        source_atoms = atoms_by_source.get(source_ref, [])
        if not source_atoms:
            problems.append(
                f"authoritative source {source_ref!r} has no atomized facts"
            )
            continue
        if isinstance(raw_text, str) and raw_text:
            problems.extend(
                _authoritative_fact_coverage(
                    raw_text,
                    source_atoms,
                    tag=f"authoritative source {source_ref!r}",
                )
            )

        aliases = set(expected.get("aliases", set()))
        for fact_id, fact in fact_by_id.items():
            if (
                fact.get("material") is True
                and str(fact.get("source_ref", "")) in aliases
                and fact_id not in referenced_fact_ids
            ):
                problems.append(
                    f"material contract fact {fact_id} from {source_ref!r} is not "
                    "represented by an authoritative source atom"
                )
    return problems


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
