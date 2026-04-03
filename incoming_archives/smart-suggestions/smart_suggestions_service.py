"""
Smart Suggestions Service — detects content issues and generates fixes.

Runs at 4 trigger points:
1. After generation (proactive scan)
2. Mid-edit (called when author pauses typing)
3. On section hover (inline suggestions)
4. Before publish (final checklist)

Detects:
- Missing required elements (shortdesc, result, steps)
- Weak shortdesc (starts with "This topic", too long)
- Vague steps ("check the settings", "verify it works")
- Missing audience terminology
- Version/product not mentioned
- Duplicate content

Each suggestion has:
- severity: error | warning | info
- section:  which DITA element it affects
- why:      explanation for the author
- before:   the problematic text
- after:    the fixed version
- fix_type: one_click | preview | generate

Place at: backend/app/services/smart_suggestions_service.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Suggestion:
    id:          str
    severity:    str          # error | warning | info
    section:     str          # shortdesc | steps | result | context | note | prereq
    title:       str          # short title shown in card header
    why:         str          # explanation for the author
    before:      str          # problematic text (shown in before/after)
    after:       str          # fixed version (shown in before/after)
    fix_type:    str          # one_click | preview | generate | add
    fix_prompt:  str          # prompt to send to LLM for fix generation
    confidence:  float        # 0-1 how confident we are this is an issue
    rule_id:     str          # which rule triggered this

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "severity":   self.severity,
            "section":    self.section,
            "title":      self.title,
            "why":        self.why,
            "before":     self.before[:300],
            "after":      self.after[:300],
            "fix_type":   self.fix_type,
            "confidence": round(self.confidence, 2),
            "rule_id":    self.rule_id,
        }


@dataclass
class SuggestionReport:
    total:        int
    errors:       int
    warnings:     int
    suggestions:  list[Suggestion]
    score_delta:  int          # estimated score improvement if all fixed
    refine_completions: list[str]  # for the refine bar dropdown

    def to_dict(self) -> dict:
        return {
            "total":       self.total,
            "errors":      self.errors,
            "warnings":    self.warnings,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "score_delta": self.score_delta,
            "refine_completions": self.refine_completions,
        }


# ── DITA content parser ───────────────────────────────────────────────────────

def _parse_sections(xml: str) -> dict[str, str]:
    """Extract named sections from DITA XML."""
    sections = {}
    patterns = {
        "title":     r"<title>(.*?)</title>",
        "shortdesc": r"<shortdesc>(.*?)</shortdesc>",
        "prereq":    r"<prereq>(.*?)</prereq>",
        "context":   r"<context>(.*?)</context>",
        "steps":     r"<steps>(.*?)</steps>",
        "result":    r"<r>(.*?)</r>",
        "postreq":   r"<postreq>(.*?)</postreq>",
        "note":      r"<note[^>]*>(.*?)</note>",
        "example":   r"<example>(.*?)</example>",
        "conbody":   r"<conbody>(.*?)</conbody>",
        "refbody":   r"<refbody>(.*?)</refbody>",
    }
    for name, pattern in patterns.items():
        match = re.search(pattern, xml, re.DOTALL | re.IGNORECASE)
        if match:
            text = re.sub(r"<[^>]+>", " ", match.group(1))
            text = re.sub(r"\s+", " ", text).strip()
            sections[name] = text
    return sections


def _get_dita_type(xml: str) -> str:
    if re.search(r"DOCTYPE\s+task", xml, re.IGNORECASE): return "task"
    if re.search(r"DOCTYPE\s+concept", xml, re.IGNORECASE): return "concept"
    if re.search(r"DOCTYPE\s+reference", xml, re.IGNORECASE): return "reference"
    if re.search(r"DOCTYPE\s+glossentry", xml, re.IGNORECASE): return "glossentry"
    if re.search(r"<task[\s>]", xml, re.IGNORECASE): return "task"
    if re.search(r"<concept[\s>]", xml, re.IGNORECASE): return "concept"
    return "task"


def _extract_steps_list(xml: str) -> list[str]:
    """Extract individual step cmd texts."""
    cmds = re.findall(r"<cmd>(.*?)</cmd>", xml, re.DOTALL | re.IGNORECASE)
    return [re.sub(r"<[^>]+>", "", c).strip() for c in cmds]


# ── Detection rules ───────────────────────────────────────────────────────────

def _check_missing_elements(sections: dict, dita_type: str) -> list[Suggestion]:
    suggestions = []

    REQUIRED = {
        "task":      ["shortdesc", "steps", "result"],
        "concept":   ["shortdesc", "conbody"],
        "reference": ["shortdesc", "refbody"],
        "glossentry":["glossterm", "glossdef"],
    }
    OPTIONAL_SUGGEST = {
        "task": ["prereq", "context", "note"],
    }

    for element in REQUIRED.get(dita_type, []):
        if element not in sections:
            suggestions.append(Suggestion(
                id         = f"missing_{element}",
                severity   = "error",
                section    = element,
                title      = f"Missing required <{element}>",
                why        = (
                    f"<{element}> is required for {dita_type} topics in DITA 1.3. "
                    f"Publishing without it may cause validation errors in AEM Guides."
                ),
                before     = f"No <{element}> section present",
                after      = _generate_placeholder(element, sections),
                fix_type   = "generate",
                fix_prompt = f"Generate a {element} section for this {dita_type} topic.",
                confidence = 1.0,
                rule_id    = f"req_{element}",
            ))

    return suggestions


def _generate_placeholder(element: str, sections: dict) -> str:
    title = sections.get("title", "this topic")
    PLACEHOLDERS = {
        "result":    f"The issue is resolved. Verify the fix in your target output.",
        "shortdesc": f"Resolve {title} by following these steps.",
        "prereq":    "Ensure required tools and access permissions are available before starting.",
        "context":   f"This procedure is needed when {title.lower()}.",
        "conbody":   f"<p>{title} describes...</p>",
        "refbody":   "<section><title>Overview</title><p>Reference content here.</p></section>",
    }
    return PLACEHOLDERS.get(element, f"Add {element} content here.")


def _check_weak_shortdesc(sections: dict) -> list[Suggestion]:
    suggestions = []
    shortdesc = sections.get("shortdesc", "")
    if not shortdesc:
        return suggestions

    # Rule: starts with "This topic"
    if re.match(r"^this (topic|document|article|page)", shortdesc, re.IGNORECASE):
        suggestions.append(Suggestion(
            id         = "shortdesc_this_topic",
            severity   = "warning",
            section    = "shortdesc",
            title      = "Shortdesc starts with 'This topic'",
            why        = (
                "Starting with 'This topic...' is against DITA style guides. "
                "The shortdesc should start with an action verb that immediately "
                "tells the user what the topic does."
            ),
            before     = shortdesc,
            after      = _fix_shortdesc_starts_with(shortdesc),
            fix_type   = "one_click",
            fix_prompt = f"Rewrite this shortdesc to start with an action verb: {shortdesc}",
            confidence = 1.0,
            rule_id    = "shortdesc_this_topic",
        ))

    # Rule: too long (> 50 words)
    word_count = len(shortdesc.split())
    if word_count > 50:
        suggestions.append(Suggestion(
            id         = "shortdesc_too_long",
            severity   = "warning",
            section    = "shortdesc",
            title      = f"Shortdesc too long ({word_count} words)",
            why        = (
                f"shortdesc should be one sentence, max 50 words. "
                f"Yours is {word_count} words. Long shortdescs appear truncated "
                f"in search results and AEM topic lists."
            ),
            before     = shortdesc,
            after      = " ".join(shortdesc.split()[:35]) + ".",
            fix_type   = "preview",
            fix_prompt = f"Shorten this shortdesc to under 50 words: {shortdesc}",
            confidence = 1.0,
            rule_id    = "shortdesc_length",
        ))

    # Rule: passive voice
    if re.search(r"\b(is used to|can be used|is designed to)\b", shortdesc, re.IGNORECASE):
        suggestions.append(Suggestion(
            id         = "shortdesc_passive",
            severity   = "info",
            section    = "shortdesc",
            title      = "Passive voice in shortdesc",
            why        = "Active voice is clearer. 'Configure X to...' is better than 'X is used to...'",
            before     = shortdesc,
            after      = re.sub(r"is used to", "enables", shortdesc, flags=re.IGNORECASE),
            fix_type   = "preview",
            fix_prompt = f"Rewrite to active voice: {shortdesc}",
            confidence = 0.8,
            rule_id    = "shortdesc_passive",
        ))

    return suggestions


def _fix_shortdesc_starts_with(text: str) -> str:
    """Quick fix: remove 'This topic...' opener."""
    cleaned = re.sub(
        r"^this (topic|document|article|page)\s+(explains?|describes?|covers?|provides?|tells?)\s+(how to|you|the|about)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
        if not cleaned.endswith("."): cleaned += "."
    return cleaned


def _check_vague_steps(steps: list[str]) -> list[Suggestion]:
    suggestions = []

    VAGUE_PATTERNS = [
        (r"^check (the|your)?\s*(settings?|config|configuration)\.?$",
         "Too vague — specify exactly where and what to check"),
        (r"^verify (it|that it|the)\s*(works?|is correct)\.?$",
         "Too vague — specify what to verify and where"),
        (r"^open the (file|document|application)\.?$",
         "Specify which file/application and how"),
        (r"^update (the|your)?\s*(settings?|config|values?)\.?$",
         "Specify exactly which setting, where it is, and what to change it to"),
        (r"^(save|submit|apply)\.?$",
         "Too brief — explain what is being saved and where"),
        (r"^click (ok|yes|confirm|apply)\.?$",
         "Specify the exact button label and dialog context"),
        (r"^navigate (to|into) the (portal|page|section)\.?$",
         "Specify exact path: App > Menu > Submenu"),
    ]

    vague_steps = []
    for i, step in enumerate(steps):
        for pattern, reason in VAGUE_PATTERNS:
            if re.match(pattern, step.strip(), re.IGNORECASE):
                vague_steps.append({
                    "index":  i + 1,
                    "text":   step,
                    "reason": reason,
                })
                break

    if vague_steps:
        step_list = "\n".join(f"Step {s['index']}: {s['text']} — {s['reason']}" for s in vague_steps)
        suggestions.append(Suggestion(
            id         = "vague_steps",
            severity   = "warning",
            section    = "steps",
            title      = f"{len(vague_steps)} vague step{'s' if len(vague_steps) > 1 else ''}",
            why        = (
                f"Steps should be specific enough for a user to follow without guessing. "
                f"Each cmd should include: exact tool/app name, exact UI path, and expected outcome."
            ),
            before     = step_list,
            after      = "AI will generate specific steps with exact paths and tool names.",
            fix_type   = "generate",
            fix_prompt = f"Rewrite these vague steps to be specific: {step_list}",
            confidence = 0.9,
            rule_id    = "vague_steps",
        ))

    return suggestions


def _check_missing_terminology(
    sections: dict,
    terminology: dict,  # {generic: client_specific}
    audience_id: str,
) -> list[Suggestion]:
    """Check if client-specific terminology is being used."""
    suggestions = []
    all_text  = " ".join(sections.values()).lower()
    violations = []

    for generic, specific in list(terminology.items())[:20]:
        if generic.lower() in all_text and specific.lower() not in all_text:
            violations.append((generic, specific))

    if violations:
        examples = violations[:3]
        suggestions.append(Suggestion(
            id         = "missing_terminology",
            severity   = "info",
            section    = "content",
            title      = f"{len(violations)} terminology issue{'s' if len(violations) > 1 else ''}",
            why        = (
                f"Found generic terms that should use client-specific names. "
                f"This maintains brand consistency and avoids ambiguity."
            ),
            before     = ", ".join(f"'{g}'" for g, s in examples),
            after      = ", ".join(f"'{s}'" for g, s in examples),
            fix_type   = "one_click",
            fix_prompt = "Replace generic terms with client-specific terminology.",
            confidence = 0.85,
            rule_id    = "terminology",
        ))

    return suggestions


def _check_version_context(sections: dict, xml: str) -> list[Suggestion]:
    """Check if version is mentioned where needed."""
    suggestions = []
    all_text = " ".join(sections.values()).lower()

    # Version-related keywords without version numbers
    has_version_keywords = any(kw in all_text for kw in [
        "version", "release", "upgrade", "update", "changed", "deprecated",
    ])
    has_version_number = bool(re.search(r"\d+\.\d+", all_text))
    has_note = "note" in sections

    if has_version_keywords and not has_version_number:
        suggestions.append(Suggestion(
            id         = "missing_version_number",
            severity   = "info",
            section    = "note",
            title      = "Version mentioned but number missing",
            why        = "Version keywords found but no specific version number. Users need exact versions to know if this applies to them.",
            before     = "Version mentioned without number",
            after      = "Add specific version number (e.g. 'AEM Guides 4.2 and later')",
            fix_type   = "preview",
            fix_prompt = "Add specific version numbers where version keywords are used.",
            confidence = 0.75,
            rule_id    = "version_number",
        ))

    return suggestions


def _check_missing_suggested_elements(sections: dict, dita_type: str) -> list[Suggestion]:
    """Suggest optional elements that would improve the topic."""
    suggestions = []
    all_text = " ".join(sections.values()).lower()

    if dita_type == "task":
        # Suggest prereq if tool names detected
        TOOL_SIGNALS = [
            "oxygen xml editor", "oxygen", "aem guides", "editor",
            "xcode", "visual studio", "terminal", "command line",
        ]
        if any(tool in all_text for tool in TOOL_SIGNALS) and "prereq" not in sections:
            suggestions.append(Suggestion(
                id         = "suggest_prereq",
                severity   = "info",
                section    = "prereq",
                title      = "Add prereq section?",
                why        = "Tool names detected in steps — users need to know required tools before starting.",
                before     = "No prereq section",
                after      = "prereq section listing required tools and access",
                fix_type   = "generate",
                fix_prompt = "Generate prereq section listing required tools mentioned in steps.",
                confidence = 0.7,
                rule_id    = "suggest_prereq",
            ))

        # Suggest note for version change
        if re.search(r"\b(4\.[0-9]|version \d)\b", all_text) and "note" not in sections:
            suggestions.append(Suggestion(
                id         = "suggest_version_note",
                severity   = "info",
                section    = "note",
                title      = "Add version compatibility note?",
                why        = "Version number detected — consider adding a note for users on other versions.",
                before     = "No version note present",
                after      = "note element clarifying version applicability",
                fix_type   = "generate",
                fix_prompt = "Generate a note element for version compatibility based on the content.",
                confidence = 0.65,
                rule_id    = "suggest_note",
            ))

    return suggestions


# ── Refine bar completions ────────────────────────────────────────────────────

def _build_refine_completions(
    sections:    dict,
    suggestions: list[Suggestion],
    dita_type:   str,
    terminology: dict,
) -> list[str]:
    """Build smart completions for the refine bar dropdown."""
    completions = []

    # From suggestions
    for sug in suggestions[:4]:
        if sug.severity == "error":
            completions.append(f"Add {sug.section} section")
        elif "shortdesc" in sug.rule_id:
            completions.append("Strengthen the shortdesc — remove 'This topic'")
        elif "steps" in sug.rule_id:
            completions.append("Make steps more specific — add exact UI paths")

    # Always-available completions
    base = [
        "Add a troubleshooting note",
        "Add version compatibility note",
        "Make shortdesc more concise",
        "Add related links section",
        "Make steps more specific",
        "Add example",
    ]

    # Terminology completions
    for generic, specific in list(terminology.items())[:3]:
        completions.append(f"Replace '{generic}' with '{specific}'")

    completions.extend(base)
    return list(dict.fromkeys(completions))[:8]  # deduplicate, max 8


# ── Main analysis function ────────────────────────────────────────────────────

async def analyse_content(
    xml:         str,
    issue:       dict,
    tenant_id:   str = "kone",
    audience_id: str = "",
) -> SuggestionReport:
    """
    Full content analysis — detects all issues and generates suggestions.
    Called after generation, mid-edit, and before publish.
    """
    sections  = _parse_sections(xml)
    dita_type = _get_dita_type(xml)
    steps     = _extract_steps_list(xml)

    # Load tenant terminology
    terminology = {}
    try:
        from app.services.tenant_service import get_tenant
        cfg = get_tenant(tenant_id)
        terminology = cfg.terminology or {}
    except Exception:
        try:
            from app.services.kone_knowledge_base import KONE_TERMINOLOGY
            terminology = KONE_TERMINOLOGY
        except Exception:
            pass

    all_suggestions: list[Suggestion] = []

    # Run all checks
    all_suggestions += _check_missing_elements(sections, dita_type)
    all_suggestions += _check_weak_shortdesc(sections)
    all_suggestions += _check_vague_steps(steps)
    all_suggestions += _check_missing_terminology(sections, terminology, audience_id)
    all_suggestions += _check_version_context(sections, xml)
    all_suggestions += _check_missing_suggested_elements(sections, dita_type)

    # Sort: errors first, then warnings, then info
    sev_order = {"error": 0, "warning": 1, "info": 2}
    all_suggestions.sort(key=lambda s: sev_order.get(s.severity, 3))

    # Estimate score delta
    score_delta = sum({
        "error":   8,
        "warning": 5,
        "info":    2,
    }.get(s.severity, 0) for s in all_suggestions)

    errors   = sum(1 for s in all_suggestions if s.severity == "error")
    warnings = sum(1 for s in all_suggestions if s.severity == "warning")

    completions = _build_refine_completions(sections, all_suggestions, dita_type, terminology)

    logger.info_structured(
        "Content analysis complete",
        extra_fields={
            "issue_key":   issue.get("issue_key"),
            "suggestions": len(all_suggestions),
            "errors":      errors,
            "warnings":    warnings,
            "score_delta": score_delta,
        },
    )

    return SuggestionReport(
        total       = len(all_suggestions),
        errors      = errors,
        warnings    = warnings,
        suggestions = all_suggestions,
        score_delta = score_delta,
        refine_completions = completions,
    )


async def apply_fix(
    xml:        str,
    suggestion: dict,
    issue:      dict,
    tenant_id:  str = "kone",
) -> str:
    """
    Apply a specific fix to the XML.
    Returns the updated XML.
    """
    rule_id    = suggestion.get("rule_id", "")
    section    = suggestion.get("section", "")
    fix_prompt = suggestion.get("fix_prompt", "")

    # Rule-based fixes (fast, no LLM)
    if rule_id == "shortdesc_this_topic":
        sections = _parse_sections(xml)
        old_sd   = sections.get("shortdesc", "")
        new_sd   = _fix_shortdesc_starts_with(old_sd)
        return xml.replace(f"<shortdesc>{old_sd}</shortdesc>",
                          f"<shortdesc>{new_sd}</shortdesc>")

    # LLM-based fixes
    try:
        from app.services.dita_generation_prompt import build_refinement_prompt
        from app.services.llm_service import generate_text, is_llm_available
        from app.services.intent_translator import translate_intent

        if not is_llm_available():
            return xml

        intent = await translate_intent(issue)
        prompt = build_refinement_prompt(
            current_dita  = xml,
            instruction   = fix_prompt,
            issue         = issue,
            intent        = intent.to_dict(),
        )
        updated = await generate_text(
            "You are a DITA technical writer. Apply the fix exactly.",
            prompt,
            max_tokens   = 1500,
            step_name    = "apply_fix",
        )
        return updated.strip() if updated else xml

    except Exception as e:
        logger.warning_structured("Fix application failed", extra_fields={"error": str(e)})
        return xml
