"""Generic issue-domain routing and domain-profile activation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path


SCHEMA_VERSION = "aem-guides-issue-domains-v1"
DATA_SCHEMA_VERSION = "aem-guides-domain-profiles-v1"
ROUTE_STATUSES = ("ACTIVE", "NOT_APPLICABLE", "UNRESOLVED")


def _load_profiles():
    path = Path(__file__).with_name("data") / "domain_profiles.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != DATA_SCHEMA_VERSION:
        raise ValueError(f"domain profile schema must be {DATA_SCHEMA_VERSION}")
    domains = payload.get("domains")
    if not isinstance(domains, dict) or "OTHER" not in domains:
        raise ValueError("domain profiles must be a non-empty object containing OTHER")
    return domains


PROFILES = _load_profiles()
DOMAINS = tuple(PROFILES)


_NEGATIVE_CONTAINER_KEYS = frozenset({
    "out_of_scope", "outofscope", "not_applicable", "excluded", "exclusions",
    "unaffected", "no_impact", "negative_scope",
})


def _flatten(value):
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        parts = []
        for key, child in value.items():
            normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if normalized_key in _NEGATIVE_CONTAINER_KEYS:
                continue
            parts.append(_flatten(child))
        return "\n".join(parts)
    if isinstance(value, (list, tuple)):
        return "\n".join(_flatten(v) for v in value)
    return ""


_NEGATIVE_SCOPE = re.compile(
    r"\b(?:not\s+(?:in\s+scope|affected|applicable|required)|out\s+of\s+scope|"
    r"outside\s+(?:the\s+)?scope|not\s+part\s+of\s+(?:the\s+)?scope|not\s+relevant|"
    r"unaffected|does\s+not\s+affect|no(?:\s+\w+){0,3}\s+impact|"
    r"not\s+(?:a|an)\s+[^.;]{0,60}\b(?:issue|change|area)|(?:must|should)?\s*not\s+be\s+"
    r"(?:tested|considered|included)|do\s+not\s+test)\b",
    re.I,
)


def _positive_sentences(text):
    for sentence in re.split(
        r"(?<=[.!?;])\s+|[\r\n]+|\b(?:but|however)\b",
        str(text or ""),
        flags=re.I,
    ):
        sentence = sentence.strip()
        if sentence and not _NEGATIVE_SCOPE.search(sentence):
            yield sentence.casefold()


def _signal_pattern(signal):
    words = signal.casefold().split()
    patterns = []
    for word in words:
        if word == "publish":
            patterns.append(r"publish(?:es|ed|ing)?")
        elif word == "api":
            patterns.append(r"apis?")
        elif word == "document":
            patterns.append(r"documents?")
        else:
            patterns.append(re.escape(word))
    return r"(?<![\w-])" + r"\s+".join(patterns) + r"(?![\w-])"


def _positive_issue_text(manifest):
    parts = []
    if not isinstance(manifest, Mapping):
        return ""
    parts.append(_flatten(manifest.get("issue")))
    accepted = manifest.get("accepted_uac")
    if accepted is not None:
        parts.append(_flatten(accepted))
    facts = manifest.get("contract_facts")
    if isinstance(facts, Mapping):
        for fact in facts.get("facts", []) or []:
            if not isinstance(fact, Mapping):
                continue
            if fact.get("material") is False:
                continue
            if fact.get("category") == "OUT_OF_SCOPE" or fact.get("destination") == "OUT_OF_SCOPE":
                continue
            parts.append(str(fact.get("literal") or fact.get("normalized") or ""))
    return "\n".join(_positive_sentences("\n".join(parts)))


def _large_workload_signal(text):
    for match in re.finditer(
        r"\b(?P<count>\d[\d,]*(?:\.\d+)?)(?P<k>k)?\s*"
        r"(?:documents?|topics?|maps?|assets?|files?)\b",
        text,
        re.I,
    ):
        raw = match.group("count").replace(",", "")
        try:
            count = float(raw) * (1000 if match.group("k") else 1)
        except ValueError:
            continue
        if count >= 1000:
            return True
    return False


def classify(manifest, plan_text=""):
    """Return evidence-signalled domains; OTHER is never inferred."""
    # Routing is based on canonical issue evidence, never on the generated plan or
    # validator-produced reasoning blocks (which would create a self-activating loop).
    del plan_text
    haystack = _positive_issue_text(manifest)
    matches = []
    for domain, profile in PROFILES.items():
        if domain == "OTHER":
            continue
        for signal in profile.get("signals", []):
            if re.search(_signal_pattern(signal), haystack):
                matches.append(domain)
                break
    # Phrase order and pluralization should not hide material API/bulk-scale facts.
    if re.search(r"\bpublish(?:es|ed|ing)?\s+in\s+bulk\b", haystack):
        if "PUBLISHING" not in matches:
            matches.append("PUBLISHING")
        if "PERFORMANCE" not in matches:
            matches.append("PERFORMANCE")
    if re.search(r"\bapis?\b", haystack) and "API" not in matches:
        matches.append("API")
    if _large_workload_signal(haystack) and "PERFORMANCE" not in matches:
        matches.append("PERFORMANCE")
    # Preserve registry order regardless of which generic detector fired.
    order = {name: index for index, name in enumerate(PROFILES)}
    matches = sorted(set(matches), key=lambda name: order[name])
    return matches


def active_domains(block):
    if not isinstance(block, Mapping):
        return []
    return [
        route.get("domain")
        for route in block.get("routes", []) or []
        if isinstance(route, Mapping) and route.get("status") == "ACTIVE"
    ]


def required_dimensions(block):
    result = []
    for domain in active_domains(block):
        for dimension in PROFILES.get(domain, {}).get("required_dimensions", []):
            if dimension not in result:
                result.append(dimension)
    return result


def required_blocks(block):
    result = []
    for domain in active_domains(block):
        for name in PROFILES.get(domain, {}).get("required_blocks", []):
            if name not in result:
                result.append(name)
    return result


def validate_issue_domains(block, *, manifest=None, plan_text="", open_question_ids=None):
    problems = []
    if not isinstance(block, Mapping):
        return ["issue_domains must be an object"]
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"issue_domains.schema_version must be {SCHEMA_VERSION}")
    primary = block.get("primary_domain")
    if primary not in DOMAINS:
        problems.append(f"issue_domains.primary_domain must be one of {', '.join(DOMAINS)}")
    routes = block.get("routes")
    if not isinstance(routes, list) or not routes:
        return problems + ["issue_domains.routes must be a non-empty list"]
    seen = set()
    active = set()
    unresolved = []
    oq_ids = None if open_question_ids is None else set(open_question_ids)
    for index, route in enumerate(routes):
        tag = f"issue_domains.routes[{index}]"
        if not isinstance(route, Mapping):
            problems.append(f"{tag} must be an object")
            continue
        domain = route.get("domain")
        if domain not in DOMAINS:
            problems.append(f"{tag}.domain must be one of {', '.join(DOMAINS)}")
        elif domain in seen:
            problems.append(f"{tag}.domain duplicates {domain}")
        else:
            seen.add(domain)
        status = route.get("status")
        if status not in ROUTE_STATUSES:
            problems.append(f"{tag}.status must be one of {', '.join(ROUTE_STATUSES)}")
        if status == "ACTIVE":
            active.add(domain)
        if not str(route.get("reason", "")).strip():
            problems.append(f"{tag}.reason must be non-empty")
        evidence = route.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(str(x).strip() for x in evidence):
            problems.append(f"{tag}.evidence must be a non-empty list")
        if status == "UNRESOLVED":
            ref = str(route.get("open_question_ref", ""))
            unresolved.append(ref)
            if not ref or (oq_ids is not None and ref not in oq_ids):
                problems.append(f"{tag}: UNRESOLVED domain requires a declared open_question_ref")
    if primary not in active:
        problems.append("issue_domains.primary_domain must have an ACTIVE route")
    if not active:
        problems.append("issue_domains requires at least one ACTIVE route")

    detected = classify(manifest or {}, plan_text)
    undeclared = [domain for domain in detected if domain not in active]
    if undeclared:
        problems.append(
            "evidence-signalled domain(s) are not ACTIVE: " + ", ".join(undeclared)
        )
    for name in required_blocks(block):
        if not isinstance((manifest or {}).get(name), Mapping):
            problems.append(f"active domain requires manifest block {name!r}")
    return problems


def is_present(manifest):
    return isinstance(manifest, Mapping) and isinstance(manifest.get("issue_domains"), Mapping)
