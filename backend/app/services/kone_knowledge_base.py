from __future__ import annotations

import json
from pathlib import Path

from app.storage import get_storage

KONE_TERMINOLOGY = {
    "elevator": "KONE elevator",
    "dx class": "KONE DX Class elevator",
    "monospace": "KONE MonoSpace elevator",
    "minispace": "KONE MiniSpace elevator",
    "transys": "KONE TranSys elevator",
    "escalator": "KONE escalator",
    "travelmaster": "KONE TravelMaster escalator",
    "connected services": "KONE 24/7 Connected Services",
    "remote monitoring": "KONE 24/7 Connected Services",
    "maintenance portal": "KONE Care portal",
    "service portal": "KONE Care portal",
    "equipment api": "KONE Equipment API",
    "connect api": "KONE Connect API",
    "api v2": "KONE Connect API v2",
    "aem": "AEM Guides",
    "oxygen": "Oxygen XML Editor",
    "authoring tool": "AEM Guides authoring environment",
    "the device": "the elevator unit",
    "the system": "the KONE system",
    "the portal": "the KONE Care portal",
    "the application": "the KONE application",
}

FORBIDDEN_GENERIC_TERMS = [
    "the device",
    "iot device",
    "connected device",
    "smart elevator",
    "our product",
    "this feature",
    "the user",
]

AUDIENCE_PROFILES = {
    "field_technician": {
        "label": "Field technician",
        "description": "KONE-trained service engineer who installs and maintains equipment.",
        "knowledge": [
            "Deep mechanical knowledge of KONE elevator components.",
            "Familiar with KONE Care portal and service tools.",
            "Uses a mobile device on-site, often offline.",
            "Follows strict safety protocols.",
        ],
        "vocabulary": [
            "Use technical KONE component names.",
            "Use exact KONE Care portal navigation paths.",
            "Use 'Navigate to' instead of 'Go to'.",
            "Use 'Select' instead of 'Click' for touch interfaces.",
        ],
        "avoid": [
            "software or API-heavy explanations",
            "DITA implementation jargon",
            "abstract concepts without physical examples",
        ],
        "step_detail": "very detailed with exact menu paths and confirmation dialogs",
        "shortdesc_pattern": "Verb + what they do + outcome.",
        "jira_labels": ["field-tech", "field-technician", "maintenance", "on-site", "technician"],
        "jira_components": ["Field Services", "Maintenance", "On-site Tools", "KONE Care Mobile"],
    },
    "building_manager": {
        "label": "Building manager",
        "description": "Responsible for elevator operations in a building with limited technical depth.",
        "knowledge": [
            "No deep elevator engineering knowledge.",
            "Uses KONE portals and dashboards.",
            "Focused on uptime, service requests, and compliance.",
        ],
        "vocabulary": [
            "Use plain language.",
            "Refer to KONE Online portal by name.",
            "Focus on outcomes and status visibility.",
        ],
        "avoid": [
            "component-level technical detail",
            "maintenance procedures",
            "safety-regulation implementation detail",
        ],
        "step_detail": "high level and portal-focused",
        "shortdesc_pattern": "Outcome first.",
        "jira_labels": ["building-manager", "facility", "end-user", "portal", "dashboard"],
        "jira_components": ["KONE Online Portal", "Customer Dashboard", "Service Requests"],
    },
    "developer": {
        "label": "Developer",
        "description": "Software developer integrating KONE APIs.",
        "knowledge": [
            "Strong software development skills.",
            "Familiar with REST APIs, JSON, and authentication patterns.",
            "May not know KONE elevator specifics.",
        ],
        "vocabulary": [
            "Use precise API terminology.",
            "Reference HTTP methods, payloads, and response codes.",
            "Include exact field names and endpoint paths.",
        ],
        "avoid": [
            "field service procedures",
            "generic marketing language",
        ],
        "step_detail": "technical and precise",
        "shortdesc_pattern": "What the API does + key parameter or outcome.",
        "jira_labels": ["developer", "api", "integration", "sdk", "developer-portal"],
        "jira_components": ["KONE Connect API", "Developer Portal", "API Gateway", "Webhooks"],
    },
    "aem_author": {
        "label": "AEM Guides author",
        "description": "Technical writer authoring in AEM Guides and DITA.",
        "knowledge": [
            "DITA authoring expertise.",
            "AEM Guides environment and publishing workflow.",
            "KONE documentation standards and style rules.",
        ],
        "vocabulary": [
            "Use DITA element names correctly.",
            "Reference AEM Guides features by exact name.",
            "Follow structural patterns precisely.",
        ],
        "avoid": [
            "end-user phrasing",
            "field-service implementation detail without context",
        ],
        "step_detail": "precise DITA and AEM steps",
        "shortdesc_pattern": "Action + context.",
        "jira_labels": ["authoring", "dita", "aem-guides", "documentation", "content"],
        "jira_components": ["AEM Guides", "Documentation", "Content Management", "DITA"],
    },
}

COMPONENT_MAPPING = {
    "Field Services": {"product": "KONE Care maintenance service", "audience": "field_technician"},
    "Maintenance": {"product": "KONE Care maintenance service", "audience": "field_technician"},
    "On-site Tools": {"product": "KONE Care Mobile app", "audience": "field_technician"},
    "KONE Care Mobile": {"product": "KONE Care Mobile app", "audience": "field_technician"},
    "KONE Online Portal": {"product": "KONE Online portal", "audience": "building_manager"},
    "Customer Dashboard": {"product": "KONE Online customer dashboard", "audience": "building_manager"},
    "Service Requests": {"product": "KONE Online service request system", "audience": "building_manager"},
    "KONE Connect API": {"product": "KONE Connect API", "audience": "developer"},
    "Developer Portal": {"product": "KONE Developer Portal", "audience": "developer"},
    "API Gateway": {"product": "KONE Connect API gateway", "audience": "developer"},
    "Webhooks": {"product": "KONE Connect webhooks", "audience": "developer"},
    "AEM Guides": {"product": "AEM Guides authoring environment", "audience": "aem_author"},
    "Documentation": {"product": "KONE documentation platform", "audience": "aem_author"},
    "DITA": {"product": "KONE DITA content", "audience": "aem_author"},
    "Content Management": {"product": "KONE content management system", "audience": "aem_author"},
}

KONE_STYLE_RULES = """
=== KONE DITA STYLE GUIDE (MANDATORY) ===

SHORTDESC RULES:
- Maximum 50 words and one sentence.
- Start with a present-tense verb.
- Include the KONE product or platform name when possible.
- Do not start with "This topic" or "This document".

TITLE RULES:
- Troubleshooting: start with Resolve or Troubleshoot.
- Concept: start with Understanding or About.
- Task: start with an imperative verb.
- Reference: use a noun phrase.

STEP RULES:
- Each cmd element starts with an imperative verb.
- Include exact UI paths where applicable.
- Field technician topics include safety notes when relevant.
- Developer topics include request details and schemas when helpful.

TERMINOLOGY RULES:
- Prefer KONE-specific product names over generic equivalents.
- Use audience-specific labels instead of generic "user".
- Keep terminology consistent across title, shortdesc, and steps.

NOTE RULES:
- Safety-critical information belongs in a note.
- Version-specific information should name the version explicitly.
- Prefer reusable conref content for standard safety warnings.
""".strip()

WRITING_PATTERN_EXAMPLES = {
    "shortdesc_field_tech": {
        "wrong": "This topic explains how to fix elevator door issues.",
        "right": "Resolve door operator malfunctions on KONE DX Class elevators by resetting the door control unit in KONE Care portal.",
        "rule": "Use action verb + specific component + KONE product name + tool.",
    },
    "shortdesc_developer": {
        "wrong": "This describes the status endpoint.",
        "right": "Retrieve real-time operational status and fault codes for a specified elevator using the KONE Connect API status endpoint.",
        "rule": "Name the API outcome and the exact surface.",
    },
    "shortdesc_building_manager": {
        "wrong": "Learn about elevator monitoring.",
        "right": "View real-time elevator status, service history, and maintenance schedules from the KONE Online portal dashboard.",
        "rule": "Focus on visible outcomes for the building manager.",
    },
    "step_field_tech": {
        "wrong": "Open the app and check the settings.",
        "right": "In KONE Care Mobile, navigate to Equipment > [Equipment ID] > Diagnostics and select Run Full Diagnostic.",
        "rule": "Use exact application, path, and action.",
    },
    "step_developer": {
        "wrong": "Call the API to get elevator status.",
        "right": "Send a GET request to /v2/equipment/{equipmentId}/status with the Authorization header set to Bearer {access_token}.",
        "rule": "Use method + path + required headers.",
    },
    "context_section": {
        "wrong": "This issue was caused by a bug in the software.",
        "right": "In AEM Guides 4.2, the keyscope resolution engine requires explicit scope prefixes for cross-map keyref resolution, so upgraded topics can show unresolved keyrefs.",
        "rule": "Explain why it happens, what changed, and who is affected.",
    },
}


def build_kone_context(issue: dict, intent_type: str) -> dict:
    audience_id = _detect_audience(issue)
    audience = AUDIENCE_PROFILES.get(audience_id, AUDIENCE_PROFILES["aem_author"])
    product_context = _detect_product(issue)
    return {
        "product_context": product_context,
        "audience_id": audience_id,
        "audience": audience,
        "terminology_rules": _build_terminology_rules(audience_id, issue),
        "style_rules": KONE_STYLE_RULES,
        "writing_examples": _select_writing_examples(audience_id, intent_type),
        "conref_hints": _suggest_conrefs(issue),
        "forbidden_terms": FORBIDDEN_GENERIC_TERMS,
    }


def _detect_audience(issue: dict) -> str:
    labels = [label.lower() for label in (issue.get("labels") or [])]
    components = [component.lower() for component in (issue.get("components") or [])]
    summary = (issue.get("summary") or "").lower()
    description = (issue.get("description") or "").lower()
    corpus = f"{summary} {description}"

    for audience_id, profile in AUDIENCE_PROFILES.items():
        profile_labels = {label.lower() for label in profile.get("jira_labels", [])}
        if any(label in profile_labels for label in labels):
            return audience_id

    for component in components:
        for mapped_component, mapping in COMPONENT_MAPPING.items():
            if mapped_component.lower() in component:
                return mapping["audience"]

    if any(token in corpus for token in ("api", "endpoint", "sdk", "webhook", "integration")):
        return "developer"
    if any(token in corpus for token in ("portal", "dashboard", "service request", "building")):
        return "building_manager"
    if any(token in corpus for token in ("technician", "maintenance", "inspect", "replace")):
        return "field_technician"
    return "aem_author"


def _detect_product(issue: dict) -> str:
    components = issue.get("components") or []
    summary = (issue.get("summary") or "").lower()
    labels = [label.lower() for label in (issue.get("labels") or [])]
    corpus = f"{summary} {' '.join(labels)}"

    for component in components:
        if component in COMPONENT_MAPPING:
            return COMPONENT_MAPPING[component]["product"]

    for generic, specific in KONE_TERMINOLOGY.items():
        if generic in corpus:
            return specific
    return "AEM Guides authoring environment"


def _build_terminology_rules(audience_id: str, issue: dict) -> list[str]:
    rules = list(AUDIENCE_PROFILES.get(audience_id, {}).get("vocabulary", []))
    summary = (issue.get("summary") or "").lower()
    for generic, specific in KONE_TERMINOLOGY.items():
        if generic in summary:
            rules.append(f"Use '{specific}' instead of '{generic}'.")
    return rules[:10]


def _select_writing_examples(audience_id: str, intent_type: str) -> list[dict]:
    examples: list[dict] = []
    suffix = audience_id.replace("_technician", "_field_tech")
    shortdesc_key = f"shortdesc_{suffix}"
    step_key = f"step_{suffix}"
    if shortdesc_key in WRITING_PATTERN_EXAMPLES:
        examples.append({"type": "shortdesc", **WRITING_PATTERN_EXAMPLES[shortdesc_key]})
    if step_key in WRITING_PATTERN_EXAMPLES:
        examples.append({"type": "step", **WRITING_PATTERN_EXAMPLES[step_key]})
    if intent_type in {"troubleshooting_task", "configuration_task"}:
        examples.append({"type": "context", **WRITING_PATTERN_EXAMPLES["context_section"]})
    return examples


def _suggest_conrefs(issue: dict) -> list[str]:
    summary = (issue.get("summary") or "").lower()
    conrefs: list[str] = []
    if any(token in summary for token in ("brake", "motor", "shaft", "pit", "escalator chain")):
        conrefs.append("kone-safety-lib/danger-rotating-parts")
    if "dx class" in summary or "dx" in summary:
        conrefs.append("kone-products/dx-class-shortdesc")
    if "connected services" in summary or "24/7" in summary:
        conrefs.append("kone-products/247-connected-services-shortdesc")
    return conrefs


def _custom_kb_path() -> Path:
    path = get_storage().base_path / "kone_kb.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_custom_kb() -> dict:
    path = _custom_kb_path()
    if not path.exists():
        return {"terms": {}, "rules": [], "examples": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"terms": {}, "rules": [], "examples": []}


def save_custom_kb(payload: dict) -> None:
    path = _custom_kb_path()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
