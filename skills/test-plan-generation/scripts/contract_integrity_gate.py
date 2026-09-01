"""Fail closed when a material source fact disappears from the visible plan."""

from __future__ import annotations

import re
from collections.abc import Mapping


def _ac_text(plan_text):
    records = {}
    in_acceptance = False
    for line in str(plan_text or "").splitlines():
        heading = re.fullmatch(r"\*\*(.+?)\*\*", line.strip())
        if heading:
            in_acceptance = heading.group(1) == "Acceptance Criteria"
            continue
        if not in_acceptance:
            continue
        match = re.match(r"^- (AC-\d{2})\b.*?:\s*(.+)$", line.strip())
        if match:
            records[match.group(1)] = match.group(2)
    return records


def _oq_text(plan_text):
    records = {}
    for line in str(plan_text or "").splitlines():
        match = re.match(r"^- (OQ-\d{2}):\s*(.+)$", line.strip())
        if match:
            records[match.group(1)] = match.group(2)
    return records


def validate_integrity(block, plan_text):
    problems = []
    if not isinstance(block, Mapping):
        return ["contract_facts must be present before contract integrity can run"]
    acs = _ac_text(plan_text)
    oqs = _oq_text(plan_text)
    whole = str(plan_text or "")
    for fact in block.get("facts", []) or []:
        if not isinstance(fact, Mapping) or fact.get("material") is not True:
            continue
        fact_id = fact.get("fact_id", "?")
        destination = fact.get("destination")
        if destination == "ACCEPTANCE_CRITERION":
            ref = str(fact.get("ac_ref", ""))
            target = acs.get(ref, "")
            if not target:
                problems.append(f"{fact_id}: material contract fact maps to missing {ref or 'AC'}")
                continue
        elif destination == "OPEN_QUESTION":
            ref = str(fact.get("open_question_ref", ""))
            target = oqs.get(ref, "")
            if not target:
                problems.append(f"{fact_id}: ambiguous contract fact maps to missing {ref or 'Open Question'}")
                continue
        else:
            target = whole

        for term in fact.get("protected_terms", []) or []:
            if str(term).casefold() not in target.casefold():
                problems.append(
                    f"{fact_id}: protected source term {term!r} was silently lost from {destination}"
                )

        if fact.get("integrity") == "PRESERVED":
            literal = str(fact.get("literal", "")).strip()
            # Exact source prose need not be copied into an AC.  At least the normalized
            # meaning or every explicitly protected term must survive.
            normalized = str(fact.get("normalized", "")).strip()
            protected = fact.get("protected_terms", []) or []
            if not protected and literal.casefold() not in target.casefold() and normalized.casefold() not in target.casefold():
                problems.append(
                    f"{fact_id}: PRESERVED fact is absent from its destination; use NORMALIZED_WITHOUT_SEMANTIC_CHANGE "
                    "when wording changes"
                )
    return problems
