"""Canonical contract-fact schema used before semantic expansion.

The extractor itself may be model-assisted, but its output is deterministic and
source-bound.  This module deliberately does not guess product behaviour from
keywords.  It validates that every recorded fact preserves the literal wording,
subject authority, protected exact tokens, materiality, and final destination.
"""

from __future__ import annotations

import re
from collections.abc import Mapping


SCHEMA_VERSION = "aem-guides-contract-facts-v1"

CONTRACT_STATES = (
    "HUMAN_ACCEPTED_CONTRACT",
    "PARTIAL_HUMAN_CONTRACT",
    "EVIDENCE_BACKED_PROPOSED_CONTRACT",
    "INSUFFICIENT_EVIDENCE_FOR_CONTRACT",
)

FACT_CATEGORIES = (
    "DIRECT_EXPECTED_BEHAVIOR",
    "IN_SCOPE",
    "OUT_OF_SCOPE",
    "PRIMARY_PRODUCT_AREA",
    "PRIMARY_OUTPUT_TYPE",
    "PRESET_TYPE",
    "DITA_OT_PROCESSING_STATE",
    "DEPLOYMENT_MODE",
    "PRODUCT_VERSION",
    "FEATURE_STATE",
    "EXACT_LABELS",
    "EXACT_DEFAULTS",
    "EXACT_VALUES",
    "EXACT_STATUS_NAMES",
    "COLORS",
    "COUNTS",
    "LIMITS",
    "HUMAN_TERMINOLOGY",
    "COMPATIBILITY_REQUIREMENTS",
    "EXPLICIT_NEGATIVE_REQUIREMENTS",
    "HUMAN_OPEN_QUESTIONS",
    "ENGINEERING_DESIGN_QUESTIONS",
)

INTEGRITY_DISPOSITIONS = (
    "PRESERVED",
    "NORMALIZED_WITHOUT_SEMANTIC_CHANGE",
    "EXPLICITLY_FLAGGED_AS_AMBIGUOUS",
)

DESTINATIONS = (
    "ACCEPTANCE_CRITERION",
    "OPEN_QUESTION",
    "OUT_OF_SCOPE",
    "SCOPE_RESOLUTION",
    "CONTEXT_ONLY",
)

SUBJECTS = ("PRODUCT_CONTRACT", "DITA_SEMANTICS", "ACTUAL_IMPLEMENTATION", "CURRENT_UI")

AUTHORITIES = (
    "HUMAN_ACCEPTED_AC",
    "APPROVED_PRODUCT_DECISION",
    "EXPLICIT_HUMAN_DECISION",
    "JIRA_EXPECTED_BEHAVIOR",
    "CUSTOMER_EXPLICIT_REQUEST",
    "CURRENT_ACCEPTED_PRODUCT_CONTRACT",
    "DITA_SPEC",
    "AEM_GUIDES_DOC",
    "DITA_OT",
    "CURRENT_RUNTIME",
    "CURRENT_IMPLEMENTATION",
    "PR_IMPLEMENTATION",
    "CURRENT_TESTS",
    "DOCUMENTATION",
    "HISTORICAL_JIRA",
    "HISTORICAL_IMPLEMENTATION",
    "INFERENCE",
)

EXACT_CATEGORIES = frozenset(
    {
        "PRIMARY_OUTPUT_TYPE",
        "PRESET_TYPE",
        "DITA_OT_PROCESSING_STATE",
        "DEPLOYMENT_MODE",
        "PRODUCT_VERSION",
        "FEATURE_STATE",
        "EXACT_LABELS",
        "EXACT_DEFAULTS",
        "EXACT_VALUES",
        "EXACT_STATUS_NAMES",
        "COLORS",
        "COUNTS",
        "LIMITS",
        "HUMAN_TERMINOLOGY",
    }
)


def _strings(value):
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _ref_for_destination(fact):
    destination = fact.get("destination")
    if destination == "ACCEPTANCE_CRITERION":
        return fact.get("ac_ref")
    if destination == "OPEN_QUESTION":
        return fact.get("open_question_ref")
    if destination == "OUT_OF_SCOPE":
        return fact.get("out_of_scope_ref")
    if destination == "SCOPE_RESOLUTION":
        return fact.get("scope_ref")
    return fact.get("context_ref")


def validate_contract_facts(block, *, open_question_ids=None, source_texts=None):
    problems = []
    if not isinstance(block, Mapping):
        return ["contract_facts must be an object"]
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"contract_facts.schema_version must be {SCHEMA_VERSION}")
    state = block.get("contract_state")
    if state not in CONTRACT_STATES:
        problems.append(
            "contract_facts.contract_state must be one of " + ", ".join(CONTRACT_STATES)
        )
    source_refs = block.get("source_refs")
    if not _strings(source_refs) or not source_refs:
        problems.append("contract_facts.source_refs must be a non-empty string list")
    facts = block.get("facts")
    if not isinstance(facts, list):
        return problems + ["contract_facts.facts must be a list"]
    if not facts and state != "INSUFFICIENT_EVIDENCE_FOR_CONTRACT":
        problems.append("contract_facts.facts cannot be empty for a usable contract state")
    if not facts and not str(block.get("empty_reason", "")).strip():
        problems.append("empty contract_facts requires empty_reason")

    source_ref_set = set(source_refs or []) if isinstance(source_refs, list) else set()
    seen = set()
    # ``None`` means the caller has no authoritative Open Question registry.
    # An empty iterable means the registry is known and contains no valid refs.
    oq_ids = None if open_question_ids is None else set(open_question_ids)
    source_text_by_ref = None
    if source_texts is not None:
        if not isinstance(source_texts, Mapping):
            return problems + ["contract fact source_texts must be a mapping"]
        source_text_by_ref = {
            str(ref): str(text)
            for ref, text in source_texts.items()
            if str(ref).strip() and isinstance(text, str)
        }
    ordered = []
    for index, fact in enumerate(facts):
        tag = f"contract_facts.facts[{index}]"
        if not isinstance(fact, Mapping):
            problems.append(f"{tag} must be an object")
            continue
        fact_id = str(fact.get("fact_id", "")).strip()
        if not re.fullmatch(r"CF-\d{2}", fact_id):
            problems.append(f"{tag}.fact_id must use stable CF-## form")
        elif fact_id in seen:
            problems.append(f"{tag}.fact_id duplicates {fact_id}")
        else:
            seen.add(fact_id)
            ordered.append(fact_id)
        if fact.get("category") not in FACT_CATEGORIES:
            problems.append(f"{tag}.category must be one of {', '.join(FACT_CATEGORIES)}")
        for field in ("literal", "normalized", "source_ref"):
            if not str(fact.get(field, "")).strip():
                problems.append(f"{tag}.{field} must be non-empty")
        if fact.get("source_ref") and fact.get("source_ref") not in source_ref_set:
            problems.append(f"{tag}.source_ref must be declared in contract_facts.source_refs")
        source_ref = str(fact.get("source_ref", ""))
        if source_text_by_ref is not None and source_ref:
            source_text = source_text_by_ref.get(source_ref)
            if source_text is None:
                problems.append(
                    f"{tag}.source_ref {source_ref!r} is not bound to canonical source text"
                )
            elif str(fact.get("literal", "")) not in source_text:
                problems.append(
                    f"{tag}.literal is not an exact excerpt of canonical source {source_ref!r}"
                )
        if fact.get("subject") not in SUBJECTS:
            problems.append(f"{tag}.subject must be one of {', '.join(SUBJECTS)}")
        if fact.get("authority") not in AUTHORITIES:
            problems.append(f"{tag}.authority is not a recognized subject authority")
        if not isinstance(fact.get("material"), bool):
            problems.append(f"{tag}.material must be a boolean")
        protected = fact.get("protected_terms", [])
        if not _strings(protected):
            problems.append(f"{tag}.protected_terms must be a string list")
        elif fact.get("material") is True and not protected:
            problems.append(f"{tag}: every material contract fact requires protected_terms")
        elif fact.get("category") in EXACT_CATEGORIES and not protected:
            problems.append(f"{tag} is an exact-value category and requires protected_terms")
        elif any(term.casefold() not in str(fact.get("literal", "")).casefold() for term in protected):
            problems.append(f"{tag}.protected_terms must occur literally in the source wording")
        integrity = fact.get("integrity")
        if integrity not in INTEGRITY_DISPOSITIONS:
            problems.append(
                f"{tag}.integrity must be one of {', '.join(INTEGRITY_DISPOSITIONS)}"
            )
        destination = fact.get("destination")
        if destination not in DESTINATIONS:
            problems.append(f"{tag}.destination must be one of {', '.join(DESTINATIONS)}")
        reference = str(_ref_for_destination(fact) or "").strip()
        if not reference:
            problems.append(f"{tag} must provide the reference required by destination {destination}")
        if integrity == "EXPLICITLY_FLAGGED_AS_AMBIGUOUS" and destination != "OPEN_QUESTION":
            problems.append(f"{tag}: ambiguous facts must be routed to OPEN_QUESTION")
        if destination == "OPEN_QUESTION" and oq_ids is not None and reference not in oq_ids:
            problems.append(f"{tag}.open_question_ref {reference!r} is not declared")
        if fact.get("material") is False and destination == "ACCEPTANCE_CRITERION":
            problems.append(f"{tag}: a non-material fact must not be promoted to an AC")

    expected = [f"CF-{i:02d}" for i in range(1, len(ordered) + 1)]
    if ordered != expected:
        problems.append("contract fact IDs must be contiguous and ordered starting at CF-01")

    if state == "INSUFFICIENT_EVIDENCE_FOR_CONTRACT":
        refs = block.get("open_question_refs")
        if not _strings(refs) or not refs:
            problems.append(
                "INSUFFICIENT_EVIDENCE_FOR_CONTRACT requires open_question_refs; uncertainty must be exposed"
            )
        elif oq_ids is not None and any(ref not in oq_ids for ref in refs):
            problems.append("contract_facts.open_question_refs contains an undeclared Open Question")
    return problems


def material_fact_ids(block):
    if not isinstance(block, Mapping):
        return []
    return [
        str(fact.get("fact_id"))
        for fact in block.get("facts", [])
        if isinstance(fact, Mapping) and fact.get("material") is True
    ]


def is_present(manifest):
    return isinstance(manifest, Mapping) and isinstance(manifest.get("contract_facts"), Mapping)
