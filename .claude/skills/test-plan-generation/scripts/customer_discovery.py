"""Corpus-side customer checklists: supporting investigation, never scope or ACs.

Customer identities live in retrieved/profile data, not this skill's rules. A
packaged client can supply the same versioned profile packet in its manifest;
offline clients can read the corpus-side packet in their Dataset Studio checkout.
No network call, index mutation, Human approval or positive verdict is made here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import coverage_hypotheses


SCHEMA_VERSION = "aem-guides-customer-discovery-map-v1"
PROFILE_PATH = Path("scripts/uac_eval/customer_profiles.json")
MAX_BYTES = 1_000_000
VALID_AXES = set(coverage_hypotheses.COVERAGE_DIMENSIONS) | set(
    coverage_hypotheses.DISCOVERY_DIMENSION_BY_AXIS
)


def _strings(values):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [str(v.get("name", "") if isinstance(v, dict) else v).strip()
            for v in values if isinstance(v, (str, dict))]


def _fold(value):
    return " ".join(value.casefold().split())


def _text_list(value):
    return (isinstance(value, list) and 0 < len(value) <= 100
            and all(isinstance(v, str) and 0 < len(v.strip()) <= 200 for v in value))


def _matches(term, text):
    # Word boundaries prevent partial customer/input examples from matching.
    return bool(re.search(r"(?<!\w)" + re.escape(_fold(term)) + r"(?!\w)", _fold(text)))


def load_profiles(manifest):
    """Return a packet and an honest gap. Explicit packets never fall back silently."""
    if "customer_discovery_profiles" in manifest:
        return manifest["customer_discovery_profiles"], "explicit customer profile packet is null"
    starts = [Path(__file__).resolve(), Path.cwd()]
    configured = os.environ.get("AEM_STUDIO_REPO", "").strip()
    if configured:
        starts = [Path(configured).expanduser()]
    for start in starts:
        for root in (start, *start.parents):
            if not (root / "backend/app/services").is_dir():
                continue
            path = root / PROFILE_PATH
            try:
                if path.stat().st_size > MAX_BYTES:
                    return None, "customer profile packet exceeds size limit"
                return json.loads(path.read_text(encoding="utf-8")), ""
            except (OSError, ValueError):
                return None, "customer profile packet unavailable or invalid; no advice fabricated"
    return None, "no corpus-side customer profile packet; supply a versioned manifest packet"


def validate_packet(packet):
    try:
        encoded = json.dumps(packet, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        return ["customer profile packet must be finite JSON data"]
    if len(encoded) > MAX_BYTES:
        return ["customer profile packet exceeds size limit"]
    if not isinstance(packet, dict) or packet.get("schema_version") != SCHEMA_VERSION:
        return ["unsupported customer discovery schema"]
    profiles = packet.get("profiles")
    if not isinstance(profiles, list) or len(profiles) > 100:
        return ["profiles must be a bounded list"]
    errors = []
    seen = set()
    for p in profiles:
        if not isinstance(p, dict):
            errors.append("invalid profile")
            continue
        pid = p.get("profile_id")
        if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", pid) or pid in seen:
            errors.append("unique profile_id required")
        seen.add(str(pid))
        if p.get("source") != "LEARNED" or p.get("promotion_state") != "VALIDATING":
            errors.append("customer checklist must remain LEARNED/VALIDATING")
        confidence = p.get("confidence")
        if type(confidence) not in (float, int) or not 0 <= confidence <= 0.3:
            errors.append("advisory confidence must be between zero and 0.3")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(p.get("source_hash", ""))):
            errors.append("CSV source hash required")
        if not isinstance(p.get("source_ref"), str) or not 1 <= len(p["source_ref"].strip()) <= 1000:
            errors.append("CSV provenance required")
        if not _text_list(p.get("labels")) or not isinstance(p.get("customer"), str) or not p.get("customer", "").strip():
            errors.append("explicit customer/label metadata required")
        context = p.get("semantic_match")
        if not isinstance(context, dict) or not _text_list(context.get("components")) or not _text_list(context.get("any_terms")):
            errors.append("semantic match needs component AND input examples")
        items = p.get("dimensions")
        if not isinstance(items, list) or not 1 <= len(items) <= 30:
            errors.append("bounded dimension list required")
            continue
        ids = set()
        for item in items:
            if not isinstance(item, dict):
                errors.append("invalid dimension")
                continue
            iid = item.get("id")
            if not isinstance(iid, str) or not re.fullmatch(r"[A-Za-z0-9_/-]{1,80}", iid) or iid in ids:
                errors.append("unique dimension id required")
            ids.add(str(iid))
            if not isinstance(item.get("axis"), str) or item["axis"] not in VALID_AXES:
                errors.append("invalid generic axis")
            if not isinstance(item.get("candidate"), str) or not 1 <= len(item["candidate"]) <= 800:
                errors.append("bounded investigation wording required")
            if not _text_list(item.get("case_refs")) or len(set(_strings(item.get("case_refs")))) < 2:
                errors.append("at least two source case references required; not proof of independence")
    return errors


def discover(manifest, evidence_pairs):
    manifest = manifest if isinstance(manifest, dict) else {}
    evidence_pairs = [(pair[0], pair[1]) for pair in (evidence_pairs or [])
                      if isinstance(pair, (tuple, list)) and len(pair) == 2
                      and all(isinstance(v, str) for v in pair)]
    packet, gap = load_profiles(manifest)
    if packet is None:
        return {"candidates": [], "gaps": [gap]}
    errors = validate_packet(packet)
    if errors:
        return {"candidates": [], "gaps": sorted(set(errors))}
    version = hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False,
                                        separators=(",", ":")).encode("utf-8")).hexdigest()
    issue = manifest.get("issue")
    issue = issue if isinstance(issue, dict) else {}
    labels = {_fold(s) for s in _strings(issue.get("labels"))}
    components = {_fold(s) for s in _strings(issue.get("components") or issue.get("component") or manifest.get("component"))}
    candidates = []
    for profile in packet["profiles"]:
        context = profile["semantic_match"]
        label_hit = bool(labels & {_fold(s) for s in profile["labels"]})
        hits = [(label, term) for label, text in evidence_pairs
                for term in context["any_terms"] if _matches(term, text)]
        semantic_hit = bool(components & {_fold(s) for s in context["components"]}) and bool(hits)
        if not (label_hit or semantic_hit):
            continue
        matched = ["issue.labels"] if label_hit else sorted({label for label, _ in hits})
        for item in profile["dimensions"]:
            axis = item["axis"]
            candidates.append({
                "hypothesis_id": "", "generator": "CUSTOMER_PROFILE",
                "dimension": coverage_hypotheses.DISCOVERY_DIMENSION_BY_AXIS.get(axis, axis),
                "implied_dimension_axis": axis, "candidate": item["candidate"],
                "feature": item["id"], "component": item.get("component", ""),
                "reason": "customer-label or component/input context matched a mined checklist; investigate current applicability",
                "technical_basis": [f"CUSTOMER_PROFILE:{profile['profile_id']}:{item['id']}",
                                    *matched, profile["source_ref"]],
                "current_evidence": matched, "status": "INVESTIGATION_CANDIDATE",
                "requires_more_evidence": True, "confidence": profile["confidence"],
                "equivalence_key": f"CUSTOMER_PROFILE:{profile['profile_id']}:{item['id']}:{version}",
                "profile_version": version, "profile_source_hash": profile["source_hash"],
                "source": "LEARNED", "source_label": "CUSTOMER_JIRA_PROFILE",
                "authority_class": "SUPPORTING_DISCOVERY", "non_authoritative": True,
                "advisory_only": True, "promotion_state": "VALIDATING",
                "auto_author_ac": False, "auto_promote": False,
                "source_case_refs": list(item["case_refs"]),
            })
    return {"candidates": candidates, "gaps": [], "profile_version": version}


def candidates_for(manifest, evidence_pairs):
    return discover(manifest, evidence_pairs)["candidates"]
