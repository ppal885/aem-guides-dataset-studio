"""Check that one discovered relationship has an evidence-bound disposition.

This is a REVIEW-only completeness helper, not a planner or acceptance gate.
Exact tags identify a candidate; tags, broad axes, and NOT_APPLICABLE claims do
not prove investigation. Existing hypothesis, verification and disposition
validators own their schemas. This helper connects those records to discovery.

Only explicitly catalogued local code files are read, for SHA-256 verification.
No network, source-tree scan, mutation, authority promotion or AC generation is
performed. Hashes prove bytes, not semantic relevance or exhaustive discovery.
"""

from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import urlsplit

import acceptance_promotion
import behavioral_completeness
import coverage_hypotheses
import disposition_classifier
import evidence_binding
import hypothesis_verifier
import missing_questions
from scaffold_support import pending_review
import verify_evidence


_CODE_LINE = re.compile(r"^(.*[\\/].+):(\d+)(?:-(\d+))?$")
_QUESTIONS = frozenset({"OPEN_QUESTION", "PRODUCT_SCOPE_QUESTION", "ENGINEERING_DESIGN_DECISION"})
_REJECTIONS = frozenset({"INVESTIGATED_AND_REJECTED", "OUT_OF_SCOPE"})
_AC_DISPOSITIONS = frozenset({"ACCEPTANCE_CONTRACT", "PROPOSED_ACCEPTANCE_CONTRACT"})
_HUMAN_SCOPE_AUTHORITIES = frozenset({
    "HUMAN_ACCEPTED_AC", "APPROVED_PRODUCT_DECISION", "EXPLICIT_HUMAN_DECISION",
    "CURRENT_ACCEPTED_PRODUCT_CONTRACT",
})


def _strings(value):
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _records(manifest, name):
    value = manifest.get(name, [])
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{name} must be a list of records")
    return value


def _identity(value):
    return value.strip().casefold() if isinstance(value, str) else ""


def _locator(value):
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if urlsplit(value).scheme in {"http", "https"}:
        return value
    match = _CODE_LINE.fullmatch(value)
    return match.group(1).replace("\\", "/") if match else value.replace("\\", "/")


def _source_matches(discovered, catalogued):
    """Keep citation ranges when binding; a whole-file record covers any range."""
    if not isinstance(discovered, str) or not isinstance(catalogued, str):
        return False
    discovered, catalogued = discovered.strip(), catalogued.strip()
    if not discovered or not catalogued:
        return False
    if any(urlsplit(value).scheme in {"http", "https"} for value in (discovered, catalogued)):
        return discovered == catalogued
    ranges = []
    paths = []
    for value in (discovered, catalogued):
        match = _CODE_LINE.fullmatch(value)
        if match:
            if len(match.group(2)) > 12 or len(match.group(3) or "") > 12:
                return False
            start, end = int(match.group(2)), int(match.group(3) or match.group(2))
            if start < 1 or end < start:
                return False
            ranges.append((start, end))
        else:
            ranges.append(None)
        path = _locator(value)
        if re.match(r"^[A-Za-z]:/", path) or path.startswith("//"):
            path = path.casefold()
        paths.append(path)
    if paths[0] != paths[1]:
        return False
    return (any(bounds is None for bounds in ranges)
            or ranges[0][0] <= ranges[1][1] and ranges[1][0] <= ranges[0][1])


def _source_problem(entry):
    if verify_evidence._entry_unavailable(entry):
        return "source is marked unavailable"
    ref = entry.get("source_ref")
    if not isinstance(ref, str) or not ref.strip():
        return "catalog source_ref is missing"
    is_remote = urlsplit(ref).scheme in {"http", "https"}
    is_code = (verify_evidence._entry_kind(entry) == "code" or (
        not is_remote and _locator(ref).lower().endswith(verify_evidence._CATALOG_SOURCE_EXTS)))
    if not is_code:
        return ""
    digest = entry.get("source_hash")
    match = verify_evidence._SHA256_RE.fullmatch(digest) if isinstance(digest, str) else None
    if match is None:
        return "code source_hash must be sha256-bound"
    path = Path(_locator(ref))
    # Do not interpret source strings as shell commands or resolve implicit roots.
    if not path.is_absolute() or not path.is_file():
        return "code source_ref must name an existing absolute file"
    try:
        before = path.stat()
        actual = verify_evidence._sha256_file(path)
        after = path.stat()
    except OSError:
        return "code source cannot be read"
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        return "code source changed while checking its hash"
    return "" if actual == match.group(1) else "code source_hash no longer matches"


def _origin_ids(candidate, catalog):
    """Resolve recorded identities, not similarity or invented semantic links."""
    concrete = {candidate[name].strip() for name in ("source_ref", "retrieved_url", "discovered_source")
                if isinstance(candidate.get(name), str) and candidate[name].strip()}
    locators = {ref.strip() for ref in candidate.get("reference_urls", []) if isinstance(ref, str)}
    for basis in candidate["technical_basis"]:
        for prefix in ("source_ref:", "reference_url:"):
            if basis.startswith(prefix):
                target = concrete if prefix == "source_ref:" else locators
                target.add(basis[len(prefix):].strip())
    concrete.discard("")
    locators.discard("")
    # A catalog ID or advisory URL must not override a concrete discovered source.
    locators = concrete or locators

    def matches(entry):
        return any(_source_matches(locator, entry.get(field))
                   for locator in locators for field in ("source_ref", "url"))

    ids = {ref for ref in candidate["current_evidence"] if ref in catalog
           and (not concrete or matches(catalog[ref]))}
    for eid, entry in catalog.items():
        if matches(entry):
            ids.add(eid)
        # Historical IDs identify the retrieved incident only, never a routing rule.
        if not concrete and candidate.get("jira_key") and entry.get("jira_key") == candidate["jira_key"]:
            ids.add(eid)
        # Generic model/Jira labels identify the activating signal, not a
        # retrieved document. An author may explicitly bind this exact candidate
        # to newly inspected evidence; broad dimensions/labels do not suffice.
        # Recorded concrete source locators cannot be replaced with such aliases.
        if not concrete:
            refs = entry.get("discovery_refs", [])
            if _strings(refs) and _identity(candidate.get("equivalence_key")) in {_identity(ref) for ref in refs}:
                ids.add(eid)
    return ids


def _check_destination(verification, disposition, hypothesis_id, manifest, oq_ids):
    verdict, destination = verification["verdict"], disposition.get("disposition")
    route = verification.get("disposition")
    if verdict == "UNRESOLVED" or route == "OPEN_QUESTION":
        oq = verification.get("open_question_ref")
        if destination not in _QUESTIONS or disposition.get("open_question_ref") != oq or oq not in oq_ids:
            return "unresolved candidate needs the same declared Open Question in verification and disposition"
    elif verdict == "REJECTED":
        if destination not in _REJECTIONS or not str(disposition.get("reason", "")).strip():
            return "rejected candidate needs an explicit evidence-grounded rejection/out-of-scope reason"
    elif route == "REGRESSION":
        if destination in _QUESTIONS | _REJECTIONS | _AC_DISPOSITIONS | {"UNSUPPORTED_INFERENCE"}:
            return "regression verification and coverage disposition disagree"
        if disposition.get("maps_to_ac"):
            return "regression verification cannot automatically map to an AC"
    elif route in {"ACCEPTANCE_CRITERION", "INFERRED_AC"}:
        if destination not in _AC_DISPOSITIONS:
            return "acceptance verification and coverage disposition disagree"
        block = manifest.get("acceptance_promotions")
        rows = block.get("records", []) if isinstance(block, dict) else []
        matching = [row for row in rows if isinstance(row, dict) and row.get("candidate_ref") == hypothesis_id]
        if len(matching) != 1:
            return "acceptance destination needs one existing promotion record for this candidate"
        row = matching[0]
        if row.get("decision") not in {"PROMOTED_CONFIRMED", "PROMOTED_PROPOSED"}:
            return "acceptance destination has no promoted acceptance record"
        problems = acceptance_promotion.validate_acceptance_promotions(
            {"schema_version": block.get("schema_version"), "records": matching},
            known_candidate_ids={hypothesis_id},
            candidate_authorities={hypothesis_id: verification.get("supporting_authorities", [])},
            candidate_subjects={hypothesis_id: verification.get("subject")},
            dispositions=[disposition], accepted_uac_present=manifest.get("accepted_uac_present"),
        )
        if problems:
            return "acceptance promotion is incomplete or inconsistent"
    return ""


def review_reason(candidate, manifest):
    """Return a concise reason for REVIEW, or '' for a bound terminal chain.

    Clearing this one discovery note is not a postable receipt. Full canonical
    gates still validate source authority, second-pass discipline, visible output,
    scope and acceptance promotion. Unresolved evidence can terminate in an OQ,
    never an invented positive or a NOT_APPLICABLE shortcut.
    """
    if not isinstance(candidate, dict) or not isinstance(manifest, dict):
        return "candidate and manifest must be records"
    key, generator = _identity(candidate.get("equivalence_key")), candidate.get("generator")
    if not key or not isinstance(generator, str) or not generator.strip():
        return "discovery identity is missing"
    for field in ("technical_basis", "current_evidence"):
        if not _strings(candidate.get(field)) or (field == "technical_basis" and not candidate[field]):
            return f"discovery {field} is missing"
    try:
        hypotheses = _records(manifest, "coverage_hypotheses")
        matched = [row for row in hypotheses if _identity(row.get("equivalence_key")) == key
                   and row.get("generator") == generator]
        if len(matched) != 1:
            return "needs exactly one matching coverage hypothesis; an axis or feature tag is not a disposition"
        hypothesis = matched[0]
        if pending_review(hypothesis):
            return "hypothesis still contains author-review placeholders"
        for field in ("technical_basis", "current_evidence"):
            if not _strings(hypothesis.get(field)) or not set(candidate[field]) <= set(hypothesis[field]):
                return f"hypothesis must preserve this candidate's {field} identities"
        for field in ("discovered_source", "source_ref", "retrieved_url"):
            if candidate.get(field) and hypothesis.get(field) != candidate[field]:
                return f"hypothesis must preserve this candidate's {field} identity"
        if hypothesis.get("dimension") != candidate.get("dimension"):
            return "hypothesis uses a different discovery dimension"
        if coverage_hypotheses.validate_coverage_block([hypothesis], require_ids=True):
            return "matching coverage hypothesis is incomplete or invalid"
        hid = hypothesis["hypothesis_id"]
        if sum(row.get("hypothesis_id") == hid for row in hypotheses) != 1:
            return "hypothesis ID is not unique"
        verifications = [row for row in _records(manifest, "verifications") if row.get("hypothesis_id") == hid]
        if len(verifications) != 1:
            return "needs exactly one terminal verification for this hypothesis"
        verification = verifications[0]
        if pending_review(verification):
            return "verification still contains author-review placeholders"
        for field in ("supporting_authorities", "supporting_evidence", "disproving_evidence"):
            if not _strings(verification.get(field, [])):
                return "verification evidence/authority fields must be string lists"
        oq_records = _records(manifest, "open_questions")
        oq_ids = {row["id"] for row in oq_records if isinstance(row.get("id"), str)
                  and isinstance(row.get("question"), str) and row["question"].strip()}
        lifecycle = _records(manifest, "evidence_lifecycle")
        problems = hypothesis_verifier.verify_all(
            [hypothesis], verifications, evidence_lifecycle=lifecycle, open_question_ids=oq_ids,
        )
        if problems:
            return "terminal verification or its evidence/OQ binding is invalid"
        dispositions = [row for row in _records(manifest, "dispositions")
                        if hid in behavioral_completeness.disposition_sources([row])]
        if len(dispositions) != 1 or behavioral_completeness.disposition_sources(dispositions).count(hid) != 1:
            return "needs exactly one disposition linked by source_refs to this hypothesis"
        disposition = dispositions[0]
        if pending_review(disposition) or disposition_classifier.validate_dispositions(dispositions):
            return "coverage disposition is incomplete or still requires author review"
        destination_problem = _check_destination(verification, disposition, hid, manifest, oq_ids)
        if destination_problem:
            return destination_problem

        # Missing/unavailable source bytes must not prevent an honest Open
        # Question. We preserve the actual discovery signal and OQ linkage;
        # canonical missing-question gates check attempts/second-pass discipline.
        # This does not claim that absent sources were inspected or USED.
        if verification["verdict"] == "UNRESOLVED":
            return ""

        entries = evidence_binding.catalog_entries(manifest)
        catalog = {evidence_binding.entry_id(row): row for row in entries}
        origins = _origin_ids(candidate, catalog)
        if not origins:
            return "discovered source is not bound to evidence_catalog; re-ground this candidate"
        used_ids = set(verification.get("supporting_evidence", []) + verification.get("disproving_evidence", []))
        used = {row.get("evidence_id"): row for row in lifecycle if row.get("evidence_id") in used_ids}
        # A current Human scope decision may reject this exact discovered lead
        # without first inspecting an unavailable historical implementation.
        # All cited decision evidence still undergoes the complete checks below;
        # this exception skips only unused origin availability/hash checks.
        human_scope_rejection = (
            verification["verdict"] == "REJECTED"
            and verification.get("subject") == "PRODUCT_CONTRACT"
            and any(use.get("authority") in _HUMAN_SCOPE_AUTHORITIES
                    and eid in verification.get("disproving_evidence", [])
                    for eid, use in used.items())
        )
        for eid in used_ids | (set() if human_scope_rejection else origins):
            entry = catalog.get(eid)
            if entry is None:
                return "verification evidence does not resolve to evidence_catalog"
            problem = _source_problem(entry)
            if problem:
                return problem
            if eid not in used:
                continue
            use = used[eid]
            if pending_review(use) or entry.get("content_inspected") is False:
                return "source bytes were retrieved but inspection was not confirmed"
            if missing_questions.validate_evidence_item(missing_questions.EvidenceItem.from_dict(use)):
                return "USED evidence lacks a valid inspection query/source record"
            if use.get("subject") != verification.get("subject") or use.get("authority") not in (
                hypothesis_verifier.SUBJECT_POLICIES.get(verification.get("subject"), {}).get("ranking", [])
            ):
                return "USED evidence lacks a matching subject-specific authority"
            for field in ("source_ref", "source_hash"):
                if use.get(field) and use[field] != entry.get(field):
                    return "USED evidence source locator/hash differs from its catalog entry"
            if entry.get("non_authoritative") is True or entry.get("authority_class") == "SUPPORTING_DISCOVERY":
                return "supporting discovery alone cannot establish a verified decision"
            recorded_authority = entry.get("authority") or entry.get("authority_class")
            if recorded_authority in hypothesis_verifier.ALL_AUTHORITIES and recorded_authority != use.get("authority"):
                return "USED evidence authority differs from the catalogued source authority"
        if verification["verdict"] != "UNRESOLVED" and not origins.intersection(used_ids):
            if not human_scope_rejection:
                return "verification uses unrelated sources; bind this candidate's discovered source"
        return ""
    except (KeyError, TypeError, ValueError, AttributeError):
        # Malformed user-authored records must retain REVIEW, not crash a draft
        # or fall through to a false completeness claim. Never echo raw content.
        return "discovery disposition records are malformed"
