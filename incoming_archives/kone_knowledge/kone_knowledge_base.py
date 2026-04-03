"""
KONE Knowledge Base — product context, terminology, and style rules
that the AI must know to write accurate KONE documentation.

This is what bridges the gap between generic AI output and
content that actually sounds like it was written by a KONE tech writer.

The knowledge base has 4 layers:
1. Product terminology — KONE-specific names, never generic
2. Audience profiles — who reads what, what they know, what they need
3. Component → product mapping — Jira component → KONE product context
4. Style rules — how your team writes, enforced via generation brief

Place at: backend/app/services/kone_knowledge_base.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

# ── 1. KONE Product Terminology ───────────────────────────────────────────────
# AI must use these exact names — never generic equivalents
# Update this as KONE product names change

KONE_TERMINOLOGY = {
    # Elevator platforms
    "elevator":           "KONE elevator",
    "dx class":           "KONE DX Class elevator",
    "monospace":          "KONE MonoSpace elevator",
    "minispace":          "KONE MiniSpace elevator",
    "transys":            "KONE TranSys elevator",

    # Escalators
    "escalator":          "KONE escalator",
    "travelmaster":       "KONE TravelMaster escalator",
    "travelmaster_90":    "KONE TravelMaster 90 escalator",

    # Connected services
    "24/7":               "KONE 24/7 Connected Services",
    "connected services": "KONE 24/7 Connected Services",
    "remote monitoring":  "KONE 24/7 Connected Services",
    "iot platform":       "KONE 24/7 Connected Services platform",

    # Maintenance
    "kone care":          "KONE Care maintenance service",
    "maintenance portal": "KONE Care portal",
    "service portal":     "KONE Care portal",

    # APIs
    "elevator api":       "KONE Equipment API",
    "connect api":        "KONE Connect API",
    "api v2":             "KONE Connect API v2",
    "equipment api":      "KONE Equipment API",

    # Software
    "aem":                "AEM Guides",
    "oxygen":             "Oxygen XML Editor",
    "authoring tool":     "AEM Guides authoring environment",

    # Generic → KONE-specific replacements
    "the device":         "the elevator unit",
    "the system":         "the KONE system",
    "the platform":       "the KONE Connect platform",
    "the portal":         "the KONE Care portal",
    "the application":    "the KONE application",
}

# Terms that should NEVER appear in KONE documentation
FORBIDDEN_GENERIC_TERMS = [
    "the device",
    "IoT device",
    "connected device",
    "smart elevator",  # use "KONE DX Class" or specific model
    "our product",
    "this feature",    # always name the feature
    "the user",        # always specify: field technician / building manager / developer
]


# ── 2. Audience Profiles ──────────────────────────────────────────────────────
# Each audience has different knowledge, vocabulary, and needs
# AI must calibrate writing level to these profiles exactly

AUDIENCE_PROFILES = {

    "field_technician": {
        "label":        "Field technician",
        "description":  "KONE-trained service engineer who installs and maintains equipment",
        "knowledge":    [
            "Deep mechanical knowledge of KONE elevator components",
            "Familiar with KONE Care portal and service tools",
            "Uses mobile device on-site, often offline",
            "Follows strict safety protocols (KONE Safety Regulations)",
            "Not a software developer — minimal IT knowledge",
        ],
        "vocabulary":   [
            "use technical KONE component names (brake pad, traction sheave, door operator)",
            "use KONE Care portal navigation paths exactly",
            "reference KONE Safety Regulations when relevant",
            "use 'Navigate to' not 'Go to'",
            "use 'Select' not 'Click' (touch interface)",
        ],
        "avoid":        [
            "software/API concepts",
            "XML or DITA terminology",
            "abstract concepts without physical examples",
        ],
        "step_detail":  "very detailed — include exact menu paths, button names, confirmation dialogs",
        "shortdesc_pattern": "Verb + what they do + outcome. E.g. 'Inspect and replace the door operator drive belt to restore normal door operation.'",
        "jira_labels":  ["field-tech", "field-technician", "maintenance", "on-site", "technician"],
        "jira_components": ["Field Services", "Maintenance", "On-site Tools", "KONE Care Mobile"],
    },

    "building_manager": {
        "label":        "Building manager / facility manager",
        "description":  "Responsible for elevator operations in a building — non-technical",
        "knowledge":    [
            "No technical elevator knowledge",
            "Uses KONE online portals and dashboards",
            "Focused on uptime, service requests, compliance",
            "Business-oriented — cares about SLAs and reports",
        ],
        "vocabulary":   [
            "use plain language — no technical jargon",
            "refer to 'KONE Online portal' not 'KONE Care portal'",
            "use 'elevator' not 'unit' or 'equipment'",
            "focus on outcomes: 'your elevator will be back in service within...'",
        ],
        "avoid":        [
            "component-level technical detail",
            "maintenance procedures",
            "safety regulation references",
        ],
        "step_detail":  "high level — focus on what to do in the portal, expected outcomes",
        "shortdesc_pattern": "Outcome first. E.g. 'View real-time elevator status and request service through the KONE Online portal.'",
        "jira_labels":  ["building-manager", "facility", "end-user", "portal", "dashboard"],
        "jira_components": ["KONE Online Portal", "Customer Dashboard", "Service Requests"],
    },

    "developer": {
        "label":        "Software developer / integrator",
        "description":  "Integrates KONE APIs into building management systems",
        "knowledge":    [
            "Strong software development skills",
            "Familiar with REST APIs, JSON, authentication patterns",
            "Building BMS or facility management integrations",
            "May not know KONE elevator specifics",
        ],
        "vocabulary":   [
            "use precise API terminology: endpoint, payload, response code",
            "include code examples where helpful",
            "reference KONE Connect API documentation",
            "use HTTP method names: GET, POST, PUT",
            "specify exact field names from API spec",
        ],
        "avoid":        [
            "elevator mechanical terminology",
            "field service procedures",
            "non-technical business language",
        ],
        "step_detail":  "technical and precise — include request/response examples, error codes",
        "shortdesc_pattern": "What the API/method does + key parameter. E.g. 'Retrieve real-time operational status for a specified elevator using the KONE Connect API.'",
        "jira_labels":  ["developer", "api", "integration", "sdk", "developer-portal"],
        "jira_components": ["KONE Connect API", "Developer Portal", "API Gateway", "Webhooks"],
    },

    "aem_author": {
        "label":        "AEM Guides technical author",
        "description":  "Documentation team member authoring in AEM Guides",
        "knowledge":    [
            "DITA authoring expertise",
            "AEM Guides environment and publishing",
            "KONE documentation standards and style guide",
            "Oxygen XML Editor proficiency",
        ],
        "vocabulary":   [
            "use DITA element names correctly",
            "reference AEM Guides features by exact name",
            "follow KONE DITA style guide patterns",
        ],
        "avoid":        [
            "end-user language",
            "hardware/technical field service content",
        ],
        "step_detail":  "precise DITA/AEM steps — include element names, UI paths in AEM Guides",
        "shortdesc_pattern": "Action + context. E.g. 'Configure keyscope attributes to enable cross-map keyref resolution in AEM Guides 4.2.'",
        "jira_labels":  ["authoring", "dita", "aem-guides", "documentation", "content"],
        "jira_components": ["AEM Guides", "Documentation", "Content Management", "DITA"],
    },
}


# ── 3. Component → Product + Audience Mapping ─────────────────────────────────
# Jira component → which KONE product + which audience reads this content

COMPONENT_MAPPING = {
    # Field service components
    "Field Services":        {"product": "KONE Care maintenance service",    "audience": "field_technician"},
    "Maintenance":           {"product": "KONE Care maintenance service",    "audience": "field_technician"},
    "On-site Tools":         {"product": "KONE Care Mobile app",             "audience": "field_technician"},
    "KONE Care Mobile":      {"product": "KONE Care Mobile app",             "audience": "field_technician"},
    "Diagnostics":           {"product": "KONE diagnostic system",           "audience": "field_technician"},

    # Building manager components
    "KONE Online Portal":    {"product": "KONE Online portal",               "audience": "building_manager"},
    "Customer Dashboard":    {"product": "KONE Online customer dashboard",   "audience": "building_manager"},
    "Service Requests":      {"product": "KONE Online service request system","audience": "building_manager"},
    "24/7 Connected":        {"product": "KONE 24/7 Connected Services",     "audience": "building_manager"},

    # Developer components
    "KONE Connect API":      {"product": "KONE Connect API",                 "audience": "developer"},
    "Developer Portal":      {"product": "KONE Developer Portal",            "audience": "developer"},
    "API Gateway":           {"product": "KONE Connect API gateway",         "audience": "developer"},
    "Webhooks":              {"product": "KONE Connect webhooks",            "audience": "developer"},
    "Equipment API":         {"product": "KONE Equipment API",               "audience": "developer"},

    # AEM / documentation
    "AEM Guides":            {"product": "AEM Guides authoring environment", "audience": "aem_author"},
    "Documentation":         {"product": "KONE documentation platform",     "audience": "aem_author"},
    "DITA":                  {"product": "KONE DITA content",                "audience": "aem_author"},
    "Content Management":    {"product": "KONE content management system",   "audience": "aem_author"},

    # Elevator products
    "DX Class":              {"product": "KONE DX Class elevator",           "audience": "field_technician"},
    "MonoSpace":             {"product": "KONE MonoSpace elevator",          "audience": "field_technician"},
    "Escalator":             {"product": "KONE escalator",                   "audience": "field_technician"},
}


# ── 4. KONE DITA Style Rules ──────────────────────────────────────────────────
# These are enforced in the generation brief so every topic follows them

KONE_STYLE_RULES = """
=== KONE DITA STYLE GUIDE (MANDATORY) ===

SHORTDESC RULES:
- Maximum 50 words, one sentence
- Start with a verb in present tense: "Configure...", "Resolve...", "View..."
- Include the KONE product name: "...in KONE Care portal", "...using KONE Connect API"
- Do NOT start with "This topic..." or "This document..."
- Do NOT use "you can" — state the action directly

TITLE RULES:
- Troubleshooting topics: Start with "Resolve" or "Troubleshoot" — e.g. "Resolve Keyref Resolution Failures"
- Concept topics: Start with "Understanding" or "About" — e.g. "Understanding KONE 24/7 Connected Services"
- Task topics: Start with an imperative verb — e.g. "Configure Baseline Settings in AEM Guides"
- Reference topics: Noun phrase — e.g. "KONE Connect API Response Codes"

STEP RULES:
- Each cmd element must start with an imperative verb
- Include exact UI path where applicable: "Navigate to KONE Care portal > Maintenance > Diagnostics"
- Field technician steps: include safety note if working near moving parts
- Developer steps: include code snippet in a codeblock element
- Maximum 8 steps per task — split into subtasks if more

TERMINOLOGY RULES:
- Always write "KONE elevator" not just "elevator" on first mention
- Always write "KONE Care portal" not "the portal" or "the app"
- Always write "KONE Connect API" not "the API" or "Connect API"
- "field technician" not "user", "technician", "engineer" alone
- "building manager" not "customer", "user", "facility manager"

NOTE ELEMENTS:
- Safety-critical info → <note type="danger"> with KONE Safety Regulations reference
- Version-specific info → <note type="note"> with exact version number
- API deprecation → <note type="attention">

CONREF USAGE:
- Standard safety warnings must use conref from kone-safety-library.dita
- Standard product descriptions must use conref from kone-product-descriptions.dita
"""


# ── 5. Writing pattern examples ───────────────────────────────────────────────
# Concrete before/after examples for the AI to follow

WRITING_PATTERN_EXAMPLES = {

    "shortdesc_field_tech": {
        "wrong":  "This topic explains how to fix elevator door issues.",
        "right":  "Resolve door operator malfunctions on KONE DX Class elevators by resetting the door control unit via KONE Care portal.",
        "rule":   "Include: action verb + specific component + KONE product name + tool/portal used",
    },

    "shortdesc_developer": {
        "wrong":  "This describes the status endpoint.",
        "right":  "Retrieve real-time operational status and fault codes for a specified elevator using the KONE Connect API GET /v2/equipment/status endpoint.",
        "rule":   "Include: HTTP method + endpoint path + what data is returned",
    },

    "shortdesc_building_mgr": {
        "wrong":  "Learn about elevator monitoring.",
        "right":  "View real-time elevator status, service history, and upcoming maintenance schedules from the KONE Online portal dashboard.",
        "rule":   "Focus on what building manager sees/gets — portal name + specific data shown",
    },

    "step_field_tech": {
        "wrong":  "Open the app and check the settings.",
        "right":  "In KONE Care Mobile, navigate to Equipment > [Equipment ID] > Diagnostics and select Run Full Diagnostic.",
        "rule":   "Exact path: App name > Menu > Submenu > Action",
    },

    "step_developer": {
        "wrong":  "Call the API to get elevator status.",
        "right":  "Send a GET request to /v2/equipment/{equipmentId}/status with the Authorization header set to Bearer {access_token}.",
        "rule":   "HTTP method + exact path + required headers/params",
    },

    "context_section": {
        "wrong":  "This issue was caused by a bug in the software.",
        "right":  "In AEM Guides 4.2, the keyscope resolution engine was updated to require explicit scope prefixes for cross-map keyref resolution. Topics published using AEM Guides 4.1 behaviour will show unresolved keyrefs after upgrading.",
        "rule":   "Context = WHY this happens + which version changed + who is affected",
    },
}


# ── Main function: build KONE context for generation ─────────────────────────

def build_kone_context(issue: dict, intent_type: str) -> dict:
    """
    Build the full KONE context object for a Jira issue.
    This is injected into the generation brief alongside the intent.

    Returns:
    {
      "product_context": "specific KONE product this relates to",
      "audience":        audience profile dict,
      "terminology_rules": list of KONE-specific term rules,
      "style_rules":     KONE DITA style guide text,
      "writing_examples": relevant before/after examples,
      "conref_hints":    suggested conref IDs if applicable,
    }
    """
    # Determine audience from Jira signals
    audience_id = _detect_audience(issue)
    audience    = AUDIENCE_PROFILES.get(audience_id, AUDIENCE_PROFILES["aem_author"])

    # Determine product context
    product_context = _detect_product(issue)

    # Select relevant writing examples
    writing_examples = _select_writing_examples(audience_id, intent_type)

    # Build terminology rules for this audience
    terminology_rules = _build_terminology_rules(audience_id, issue)

    # Conref hints
    conref_hints = _suggest_conrefs(issue, intent_type)

    return {
        "product_context":   product_context,
        "audience_id":       audience_id,
        "audience":          audience,
        "terminology_rules": terminology_rules,
        "style_rules":       KONE_STYLE_RULES,
        "writing_examples":  writing_examples,
        "conref_hints":      conref_hints,
        "forbidden_terms":   FORBIDDEN_GENERIC_TERMS,
    }


def _detect_audience(issue: dict) -> str:
    """Detect target audience from Jira signals."""
    labels     = [l.lower() for l in (issue.get("labels") or [])]
    components = [c.lower() for c in (issue.get("components") or [])]
    summary    = (issue.get("summary") or "").lower()
    desc       = (issue.get("description") or "").lower()

    # Check labels first (explicit)
    for label in labels:
        for aud_id, profile in AUDIENCE_PROFILES.items():
            if label in [l.lower() for l in profile["jira_labels"]]:
                return aud_id

    # Check components
    for comp in components:
        for jira_comp, mapping in COMPONENT_MAPPING.items():
            if jira_comp.lower() in comp:
                return mapping["audience"]

    # Check content keywords
    if any(kw in summary + desc for kw in ["api", "endpoint", "sdk", "webhook", "integration"]):
        return "developer"
    if any(kw in summary + desc for kw in ["portal", "dashboard", "service request", "building"]):
        return "building_manager"
    if any(kw in summary + desc for kw in ["technician", "on-site", "maintenance", "inspect", "replace"]):
        return "field_technician"
    if any(kw in summary + desc for kw in ["dita", "keyscope", "keyref", "conref", "aem", "authoring"]):
        return "aem_author"

    return "aem_author"  # default for AEM Guides team


def _detect_product(issue: dict) -> str:
    """Detect KONE product context from Jira issue."""
    components = issue.get("components") or []
    summary    = (issue.get("summary") or "").lower()
    labels     = [l.lower() for l in (issue.get("labels") or [])]
    all_text   = summary + " " + " ".join(labels)

    # Check components first
    for comp in components:
        if comp in COMPONENT_MAPPING:
            return COMPONENT_MAPPING[comp]["product"]

    # Check terminology
    for term, kone_term in KONE_TERMINOLOGY.items():
        if term in all_text:
            return kone_term

    return "AEM Guides authoring environment"


def _build_terminology_rules(audience_id: str, issue: dict) -> list[str]:
    """Build list of terminology rules for the generation prompt."""
    profile = AUDIENCE_PROFILES.get(audience_id, {})
    rules   = list(profile.get("vocabulary", []))

    # Add product-specific replacements
    summary = (issue.get("summary") or "").lower()
    for generic, specific in KONE_TERMINOLOGY.items():
        if generic in summary:
            rules.append(f"Use '{specific}' instead of '{generic}'")

    return rules[:10]


def _select_writing_examples(audience_id: str, intent_type: str) -> list[dict]:
    """Select the most relevant before/after writing examples."""
    examples = []

    # Shortdesc example for this audience
    sd_key = f"shortdesc_{audience_id.replace('_technician','_field_tech')}"
    if sd_key in WRITING_PATTERN_EXAMPLES:
        examples.append({
            "type":   "shortdesc",
            **WRITING_PATTERN_EXAMPLES[sd_key]
        })

    # Step example for this audience
    step_key = f"step_{audience_id.replace('_technician','_field_tech')}"
    if step_key in WRITING_PATTERN_EXAMPLES:
        examples.append({
            "type":   "step",
            **WRITING_PATTERN_EXAMPLES[step_key]
        })

    # Context example
    if intent_type in ("troubleshooting_task", "configuration_task"):
        examples.append({
            "type": "context",
            **WRITING_PATTERN_EXAMPLES["context_section"]
        })

    return examples


def _suggest_conrefs(issue: dict, intent_type: str) -> list[str]:
    """Suggest conref IDs for standard KONE content."""
    conrefs = []
    summary = (issue.get("summary") or "").lower()

    # Safety warning conrefs
    if any(kw in summary for kw in ["brake", "motor", "shaft", "pit", "escalator chain"]):
        conrefs.append("kone-safety-lib/danger-rotating-parts")
        conrefs.append("kone-safety-lib/lockout-tagout-procedure")

    # Product description conrefs
    if "dx class" in summary or "dx" in summary:
        conrefs.append("kone-products/dx-class-shortdesc")
    if "24/7" in summary or "connected services" in summary:
        conrefs.append("kone-products/247-connected-services-shortdesc")
    if "kone care" in summary:
        conrefs.append("kone-products/kone-care-shortdesc")

    return conrefs


# ── Persist custom KONE knowledge ─────────────────────────────────────────────

CUSTOM_KB_PATH = Path(__file__).resolve().parent.parent / "storage" / "kone_kb.json"


def load_custom_kb() -> dict:
    """Load any custom KONE KB additions saved by the team."""
    if not CUSTOM_KB_PATH.exists():
        return {"terms": {}, "rules": [], "examples": []}
    try:
        return json.loads(CUSTOM_KB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"terms": {}, "rules": [], "examples": []}


def save_custom_kb(kb: dict) -> None:
    """Save custom KONE KB additions."""
    CUSTOM_KB_PATH.parent.mkdir(parents=True, exist_ok=True)
    CUSTOM_KB_PATH.write_text(json.dumps(kb, indent=2), encoding="utf-8")


def add_custom_term(generic: str, kone_specific: str) -> None:
    """Add a custom terminology mapping."""
    kb = load_custom_kb()
    kb["terms"][generic.lower()] = kone_specific
    save_custom_kb(kb)


def add_custom_rule(rule: str) -> None:
    """Add a custom style rule."""
    kb = load_custom_kb()
    if rule not in kb["rules"]:
        kb["rules"].append(rule)
    save_custom_kb(kb)
