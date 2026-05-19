"""
Cisco-style enterprise task authoring: detect reference patterns and drive serialization + planning hints.

Detection uses structural signals only (no copying of business text). Output always uses new generated IDs.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.core.schemas_chat_authoring import ChatAuthoringPattern, ReferenceStyleProfile
from app.services.dita_xml_headers import extract_declared_doctype_line, strip_xml_prolog


def _ln(tag: str) -> str:
    if not tag:
        return ""
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower()


def _step_level_signals(root: ET.Element) -> list[str]:
    sig: list[str] = []
    for step in root.iter():
        if _ln(step.tag) != "step":
            continue
        for child in list(step):
            loc = _ln(child.tag)
            if loc == "info":
                sig.append("uses_step_info")
            if loc == "substeps":
                sig.append("uses_substeps_in_step")
    return list(dict.fromkeys(sig))


def analyze_task_xml_for_cisco_signals(raw_text: str) -> tuple[int, list[str]]:
    """
    Return (score 0..10, signal tags) for Cisco-like enterprise task patterns.
    Does not persist or return element text.
    """
    body = strip_xml_prolog(raw_text or "")
    if not body.strip():
        return 0, []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return 0, []
    if _ln(root.tag) != "task":
        return 0, []
    score = 2
    tags = {_ln(e.tag) for e in root.iter()}
    step_sigs = _step_level_signals(root)
    if "taskbody" in tags:
        score += 1
    if "prereq" in tags:
        score += 2
    if "context" in tags:
        score += 1
    if "steps" in tags:
        score += 1
    if "result" in tags:
        score += 1
    if "example" in tags:
        score += 1
    if "postreq" in tags:
        score += 1
    if "prolog" in tags:
        score += 1
    if "uses_step_info" in step_sigs:
        score += 2
    if "uses_substeps_in_step" in step_sigs:
        score += 1
    return min(score, 10), step_sigs


def cisco_style_score_from_profile(profile: ReferenceStyleProfile | None, xml_score: int, step_sigs: list[str]) -> int:
    """Combine parsed XML score with sanitized profile habits."""
    if not profile:
        return xml_score
    s = xml_score
    if profile.root_local_name == "task":
        s += 1
    habits = set(profile.structural_habits or [])
    if "uses_prereq" in habits:
        s += 2
    if "uses_context" in habits:
        s += 1
    if "uses_substeps" in habits or "uses_substeps_in_step" in habits or "uses_substeps_in_step" in step_sigs:
        s += 1
    if "uses_step_info" in habits:
        s += 2
    if profile.uses_prolog:
        s += 1
    ui = profile.inline_element_usage or {}
    if (ui.get("uicontrol") or 0) > 0:
        s += 1
    if (ui.get("codeph") or 0) > 0:
        s += 1
    if profile.tone_hint == "terse":
        s += 1
    return min(s, 14)


def analyze_reference_xml_for_cisco_signals(raw_text: str) -> tuple[int, list[str]]:
    """Return (score 0..14, signal tags) for Cisco-like enterprise *reference* patterns."""
    body = strip_xml_prolog(raw_text or "")
    if not body.strip():
        return 0, []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return 0, []
    if _ln(root.tag) != "reference":
        return 0, []
    tags = {_ln(e.tag) for e in root.iter()}
    sigs: list[str] = []
    score = 2
    if "refbody" in tags:
        score += 1
        sigs.append("uses_refbody")
    if "section" in tags:
        sigs.append("uses_section")
    if "table" in tags:
        score += 2
        sigs.append("uses_table")
    if "tgroup" in tags:
        score += 2
        sigs.append("uses_tgroup")
    if "thead" in tags:
        score += 1
    if "tbody" in tags:
        score += 1
    if "prolog" in tags:
        score += 1
    if "dl" in tags:
        score += 1
        sigs.append("uses_dl")
    if "codeph" in tags or "synph" in tags:
        score += 1
    if any("feature-id" in (el.attrib or {}) for el in root.iter()):
        score += 1
    if "cisco" in (extract_declared_doctype_line(raw_text or "") or "").lower():
        score += 2
    return min(score, 14), list(dict.fromkeys(sigs))


def cisco_reference_style_score_from_profile(profile: ReferenceStyleProfile | None, xml_score: int) -> int:
    if not profile:
        return xml_score
    s = xml_score
    if profile.root_local_name == "reference":
        s += 1
    habits = set(profile.structural_habits or [])
    if "uses_table" in habits or "uses_tgroup" in habits:
        s += 2
    if "uses_section" in habits:
        s += 1
    if "uses_properties" in habits:
        s += 1
    if "uses_dl" in habits:
        s += 1
    if profile.uses_prolog:
        s += 1
    ui = profile.inline_element_usage or {}
    if (ui.get("codeph") or 0) > 0:
        s += 1
    if "cisco" in (profile.declared_doctype_line or "").lower():
        s += 2
    return min(s, 18)


def resolve_effective_authoring_pattern(
    pattern: ChatAuthoringPattern,
    *,
    reference_text: str,
    style_profile: ReferenceStyleProfile | None,
) -> ChatAuthoringPattern:
    """Resolve ``auto`` using reference signals; task → ``cisco_task``, reference → ``cisco_reference``."""
    if pattern != "auto":
        return pattern
    if not (reference_text or "").strip() or not style_profile:
        return "default"

    if style_profile.root_local_name == "task":
        xml_score, step_sigs = analyze_task_xml_for_cisco_signals(reference_text)
        total = cisco_style_score_from_profile(style_profile, xml_score, step_sigs)
        if total >= 10:
            return "cisco_task"
        return "default"

    if style_profile.root_local_name == "reference":
        ref_score, _ = analyze_reference_xml_for_cisco_signals(reference_text)
        total_ref = cisco_reference_style_score_from_profile(style_profile, ref_score)
        if total_ref >= 9:
            return "cisco_reference"
        return "default"

    return "default"


def cisco_reference_semantic_plan_instructions() -> str:
    return (
        "CISCO_STYLE_REFERENCE_MODE:\n"
        "- Output a semantic plan for a DITA <reference> topic (refbody).\n"
        "- Use concise enterprise reference tone: specification-style, no marketing language.\n"
        "- Prefer section-based organization; names like overview, parameters, settings, limits, or related are fine when they match the screenshot.\n"
        "- When the UI shows tabs, grouped fields, or parameter grids, plan sections that mirror that structure (labels from the screenshot only).\n"
        "- Do NOT paste or paraphrase proprietary sentences from the reference topic title, shortdesc, or body; use it only as structural/style signal.\n"
        "- Use section details as short lines suitable for CALS tables or definition lists when the UI is tabular.\n"
        "- Do not include xref, conref, keyref, or href targets in any field.\n"
    )


def cisco_semantic_plan_instructions(
    profile: ReferenceStyleProfile | None = None,
    *,
    xref_placeholders: bool = False,
) -> str:
    """
    Planning hints for enterprise / Cisco-style tasks.

    When a reference topic is attached, ``structural_outline_hints`` and ``taskbody_top_level_sequence``
    provide **live structural context** (not prose). Optional xref basename allowlist applies only when
    ``xref_placeholders`` is enabled in generation options.
    """
    core = (
        "CISCO_STYLE_TASK_MODE:\n"
        "- Output a semantic plan for a DITA <task> only.\n"
        "- Use concise enterprise procedural tone. Short sentences. No marketing language.\n"
        "- Include sections when appropriate: 'prereq', 'context', 'steps', 'result', optional 'example', "
        "'postreq', and optional 'acceptance criteria' for verification-style postreq.\n"
        "- prereq: assumptions from the **screenshot** only; if multiple bullets, use one detail string per bullet.\n"
        "- context: describe goal from the **screenshot**; if both GUI and CLI apply, use two detail lines prefixed "
        "exactly 'GUI: ' and 'CLI: ' on each.\n"
        "- steps: one detail string per numbered step from the **screenshot**. Prefix a step with 'GUI: ' or 'CLI: ' "
        "to mark ui-type when both modes exist.\n"
        "- Use multiple ' || ' segments on one line for multiple <info> paragraphs under the same step (rare; max 4 segments).\n"
        "- example: optional section; put multi-line sample commands or CLI output in details (plain text).\n"
        "- postreq: short next-step narrative from the screenshot only.\n"
        "- Do NOT paste or paraphrase proprietary sentences from the reference title, shortdesc, or body. "
        "Use reference only for structure/vocabulary hints below.\n"
        "- Section names: prereq, context, steps, result, example, postreq (lowercase).\n"
    )
    if profile and profile.structural_outline_hints:
        core += "\nREFERENCE_LIVE_STRUCTURE (from attached file; patterns only, not wording to copy):\n"
        for hint in profile.structural_outline_hints[:14]:
            core += f"  • {hint}\n"
    if profile and profile.taskbody_top_level_sequence:
        core += (
            "\nREFERENCE_TASKBODY_ORDER: "
            + " → ".join(profile.taskbody_top_level_sequence)
            + " — mirror this ordering in your sections when it fits the screenshot.\n"
        )
    if xref_placeholders and profile and profile.reference_xref_basenames:
        bas = ", ".join(profile.reference_xref_basenames[:28])
        core += (
            "\nXREF_ALLOWLIST (basename only; from reference xrefs): "
            f"{bas}\n"
            "You MAY name these files in source_notes as 'see also: filename.xml' for downstream XML; "
            "do not paste full paragraphs from the reference.\n"
        )
    else:
        core += "\n- Omit xref/conref/keyref targets in plan fields unless XREF_ALLOWLIST is shown above.\n"
    return core


__all__ = [
    "analyze_reference_xml_for_cisco_signals",
    "analyze_task_xml_for_cisco_signals",
    "cisco_reference_semantic_plan_instructions",
    "cisco_reference_style_score_from_profile",
    "cisco_semantic_plan_instructions",
    "cisco_style_score_from_profile",
    "resolve_effective_authoring_pattern",
]
