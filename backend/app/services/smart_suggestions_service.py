from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

_STOPWORDS = {
    "a", "an", "and", "or", "the", "to", "for", "from", "with", "without", "this", "that", "these",
    "those", "into", "onto", "over", "under", "issue", "topic", "guides", "guide", "user", "users",
    "page", "document", "article", "task", "story", "feature", "bug", "fix", "update", "add",
}

_GENERIC_ISSUE_TERMS = {"concept", "reference", "task", "story", "feature", "bug", "improvement"}

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

_SAFE_RULE_IDS = {
    "validation_xml_declaration",
    "validation_dtd_header",
    "missing_shortdesc",
    "validation_xml_lang",
    "validation_taskbody",
    "validation_steps",
    "validation_cmd",
    "validation_conbody",
    "validation_refbody",
    "validation_body",
    "validation_glossdef",
    "reuse_title_conref",
    "reuse_add_keywords",
    "reuse_add_keyref",
    "reuse_add_conkeyref",
    "quality_add_note",
    "quality_add_example",
    "quality_add_xref",
    "quality_add_codeblock",
    "quality_add_media_object",
    "quality_add_dita_feature",
    "research_version_note",
    "research_tool_alignment",
}

_VALIDATION_RULES = {
    "XML declaration present": {
        "rule_id": "validation_xml_declaration",
        "section": "document",
        "title": "Missing XML declaration",
        "why": "AEM Guides import and XML tooling are more reliable when the XML declaration is present.",
        "after": '<?xml version="1.0" encoding="UTF-8"?>',
        "fix_prompt": "Add the XML declaration at the start of the document.",
        "impact": "High: parsing and import compatibility improve immediately.",
    },
    "Required DTD header present": {
        "rule_id": "validation_dtd_header",
        "section": "document",
        "title": "Missing AEM Guides DTD header",
        "why": "The output should start with the exact AEM Guides DTD for the topic type.",
        "after": "Add the exact topic-specific DTD header immediately after the XML declaration.",
        "fix_prompt": "Add the correct AEM Guides DTD header for this topic type.",
        "impact": "High: the topic becomes safer for validation and import.",
    },
    "shortdesc present": {
        "rule_id": "missing_shortdesc",
        "section": "shortdesc",
        "title": "Missing shortdesc",
        "why": "A strong shortdesc improves search, topic lists, and authoring clarity.",
        "after": "Add a concise, outcome-focused shortdesc.",
        "fix_prompt": "Add a concise, user-facing shortdesc for this topic.",
        "impact": "Medium: topic readability and navigation improve.",
    },
    "xml:lang present": {
        "rule_id": "validation_xml_lang",
        "section": "document",
        "title": "Missing xml:lang on the root element",
        "why": "Language metadata improves downstream publishing and AEM handling.",
        "after": 'Add xml:lang="en-US" to the root element.',
        "fix_prompt": "Add xml:lang=\"en-US\" to the root topic element.",
        "impact": "Medium: publishing and metadata quality improve.",
    },
    "taskbody present": {
        "rule_id": "validation_taskbody",
        "section": "taskbody",
        "title": "Task topic is missing taskbody",
        "why": "Task topics should wrap the main procedure in <taskbody>.",
        "after": "Add <taskbody> with context, steps, and result.",
        "fix_prompt": "Wrap the procedural content in a valid taskbody.",
        "impact": "High: the task becomes structurally valid.",
    },
    "steps present": {
        "rule_id": "validation_steps",
        "section": "steps",
        "title": "Task topic is missing steps",
        "why": "Procedural topics should contain explicit ordered steps.",
        "after": "Add actionable steps with one clear action per step.",
        "fix_prompt": "Add concrete ordered steps for the procedure.",
        "impact": "High: the topic becomes actionable.",
    },
    "cmd in steps": {
        "rule_id": "validation_cmd",
        "section": "steps",
        "title": "Steps are missing cmd elements",
        "why": "Each step should contain a command the reader can act on.",
        "after": "Add a <cmd> to each step.",
        "fix_prompt": "Ensure every step contains a cmd element.",
        "impact": "High: the steps become valid task instructions.",
    },
    "conbody present": {
        "rule_id": "validation_conbody",
        "section": "conbody",
        "title": "Concept topic is missing conbody",
        "why": "Concept topics need a conbody for the explanatory content.",
        "after": "Add conbody with a concise conceptual explanation.",
        "fix_prompt": "Add a conbody to this concept topic.",
        "impact": "High: the concept becomes structurally complete.",
    },
    "refbody present": {
        "rule_id": "validation_refbody",
        "section": "refbody",
        "title": "Reference topic is missing refbody",
        "why": "Reference topics need a refbody for structured reference details.",
        "after": "Add refbody with an overview section.",
        "fix_prompt": "Add a refbody to this reference topic.",
        "impact": "High: the reference becomes structurally complete.",
    },
    "body present": {
        "rule_id": "validation_body",
        "section": "body",
        "title": "Topic is missing body",
        "why": "Generic topics need a body element for the main content.",
        "after": "Add a body element with the main content.",
        "fix_prompt": "Add a body element to this topic.",
        "impact": "High: the topic becomes structurally complete.",
    },
    "glossdef present": {
        "rule_id": "validation_glossdef",
        "section": "glossdef",
        "title": "Glossary entry is missing glossdef",
        "why": "Glossary entries need a glossdef to define the term.",
        "after": "Add a glossdef with a concise definition.",
        "fix_prompt": "Add a glossdef to this glossary entry.",
        "impact": "High: the glossary entry becomes complete.",
    },
}


@dataclass
class Suggestion:
    id: str
    severity: str
    section: str
    title: str
    why: str
    before: str
    after: str
    fix_type: str
    fix_prompt: str
    confidence: float
    rule_id: str
    impact: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "section": self.section,
            "title": self.title,
            "why": self.why,
            "before": self.before[:300],
            "after": self.after[:300],
            "fix_type": self.fix_type,
            "fix_prompt": self.fix_prompt,
            "confidence": round(self.confidence, 2),
            "rule_id": self.rule_id,
            "impact": self.impact,
            "evidence": self.evidence[:3],
        }


@dataclass
class SuggestionReport:
    total: int
    errors: int
    warnings: int
    suggestions: list[Suggestion] = field(default_factory=list)
    score_delta: int = 0
    refine_completions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": [suggestion.to_dict() for suggestion in self.suggestions],
            "score_delta": self.score_delta,
            "refine_completions": self.refine_completions,
        }


def is_safe_rule(rule_id: str) -> bool:
    return (rule_id or "").strip() in _SAFE_RULE_IDS


def _summarize_change(suggestion: dict, changed: bool) -> str:
    title = str(suggestion.get("title") or suggestion.get("rule_id") or "Fix").strip()
    if not changed:
        return f"{title} produced no XML change."
    return str(suggestion.get("after") or title).strip()[:220]


def _compute_changed_ranges(before: str, after: str) -> list[dict[str, int]]:
    before_lines = (before or "").splitlines()
    after_lines = (after or "").splitlines()
    matcher = SequenceMatcher(a=before_lines, b=after_lines)
    ranges: list[dict[str, int]] = []

    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if after_lines:
            start_line = min(max(1, j1 + 1), len(after_lines))
            end_line = min(max(start_line, j2 if j2 > j1 else j1 + 1), len(after_lines))
            changed_lines = after_lines[j1:j2] or [after_lines[start_line - 1]]
        else:
            start_line = 1
            end_line = 1
            changed_lines = [""]
        end_column = max((len(line) + 1 for line in changed_lines), default=1)
        ranges.append(
            {
                "startLineNumber": start_line,
                "endLineNumber": end_line,
                "startColumn": 1,
                "endColumn": end_column,
            }
        )

    merged: list[dict[str, int]] = []
    for item in ranges:
        if not merged:
            merged.append(item)
            continue
        previous = merged[-1]
        if item["startLineNumber"] <= previous["endLineNumber"] + 1:
            previous["endLineNumber"] = max(previous["endLineNumber"], item["endLineNumber"])
            previous["endColumn"] = max(previous["endColumn"], item["endColumn"])
        else:
            merged.append(item)
    return merged[:8]


def _strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _parse_sections(xml: str) -> dict[str, str]:
    patterns = {
        "title": r"<title[^>]*>(.*?)</title>",
        "shortdesc": r"<shortdesc[^>]*>(.*?)</shortdesc>",
        "prereq": r"<prereq[^>]*>(.*?)</prereq>",
        "context": r"<context[^>]*>(.*?)</context>",
        "steps": r"<steps[^>]*>(.*?)</steps>",
        "result": r"<result[^>]*>(.*?)</result>",
        "postreq": r"<postreq[^>]*>(.*?)</postreq>",
        "note": r"<note[^>]*>(.*?)</note>",
        "example": r"<example[^>]*>(.*?)</example>",
        "conbody": r"<conbody[^>]*>(.*?)</conbody>",
        "refbody": r"<refbody[^>]*>(.*?)</refbody>",
        "glossterm": r"<glossterm[^>]*>(.*?)</glossterm>",
        "glossdef": r"<glossdef[^>]*>(.*?)</glossdef>",
    }
    sections: dict[str, str] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, xml, re.IGNORECASE | re.DOTALL)
        if match:
            sections[name] = _strip_tags(match.group(1))
    return sections


def _get_dita_type(xml: str) -> str:
    for candidate in ("glossentry", "reference", "concept", "task"):
        if re.search(rf"<{candidate}[\s>]", xml, re.IGNORECASE) or re.search(rf"DOCTYPE\s+{candidate}", xml, re.IGNORECASE):
            return candidate
    return "task"


def _extract_steps(xml: str) -> list[str]:
    matches = re.findall(r"<cmd[^>]*>(.*?)</cmd>", xml, re.IGNORECASE | re.DOTALL)
    return [_strip_tags(match) for match in matches if _strip_tags(match)]


def _required_elements(dita_type: str) -> list[str]:
    mapping = {
        "task": ["shortdesc", "steps", "result"],
        "concept": ["shortdesc", "conbody"],
        "reference": ["shortdesc", "refbody"],
        "glossentry": ["glossterm", "glossdef"],
    }
    return mapping.get(dita_type, ["shortdesc"])


def _generate_placeholder(element: str, sections: dict[str, str]) -> str:
    title = sections.get("title") or "this topic"
    placeholders = {
        "shortdesc": f"Complete {title.lower()} by following these steps.",
        "prereq": "Ensure required tools, permissions, and environment access are available before you begin.",
        "context": f"This procedure is needed when {title.lower()}.",
        "result": "The task completes successfully and the expected behavior is restored.",
        "conbody": "<p>Provide the conceptual explanation here.</p>",
        "refbody": "<section><title>Overview</title><p>Reference details go here.</p></section>",
        "glossterm": title,
        "glossdef": "Definition goes here.",
    }
    return placeholders.get(element, f"Add {element} content here.")


def _issue_text(issue: dict) -> str:
    parts = [
        issue.get("summary") or "",
        issue.get("description") or "",
        " ".join(str(item) for item in (issue.get("components") or [])),
        " ".join(str(item) for item in (issue.get("labels") or [])),
    ]
    return " ".join(part for part in parts if part).strip()


def _extract_issue_terms(issue: dict, limit: int = 6) -> list[str]:
    summary = issue.get("summary") or ""
    components = [str(item).strip() for item in (issue.get("components") or []) if str(item).strip()]
    labels = [str(item).strip() for item in (issue.get("labels") or []) if str(item).strip()]
    candidates: list[str] = []
    candidates.extend(components[:3])
    candidates.extend(label for label in labels if len(label) > 3)
    candidates.extend(re.findall(r"\b[A-Za-z][A-Za-z0-9._/-]{3,}\b", summary))

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = str(candidate).strip()
        lowered = value.lower()
        if not value or lowered in seen or lowered in _STOPWORDS or lowered in _GENERIC_ISSUE_TERMS:
            continue
        seen.add(lowered)
        unique.append(value)
    return unique[:limit]


def _extract_versions(text: str) -> list[str]:
    seen: set[str] = set()
    versions: list[str] = []
    for match in re.finditer(r"\b\d+(?:\.\d+){1,2}\b", text or ""):
        version = match.group(0)
        if version not in seen:
            seen.add(version)
            versions.append(version)
    return versions[:5]


def _extract_research_highlights(research_context: dict | None) -> dict[str, Any]:
    if not isinstance(research_context, dict):
        return {"snippets": [], "versions": [], "tools": [], "urls": []}

    snippets: list[str] = []
    urls: list[str] = []
    tools: list[str] = []
    tool_candidates = {"circleci", "oxygen", "aem guides", "experience league", "keyref", "keyscope", "conref", "dita"}

    for result in research_context.get("results", []) or []:
        summary = str(result.get("summary") or "").strip()
        if summary:
            snippets.append(summary[:220])
        for chunk in (result.get("chunks") or [])[:2]:
            text = str(chunk or "").strip()
            if text:
                snippets.append(text[:220])
        for url in (result.get("urls") or [])[:2]:
            if url:
                urls.append(str(url))

    text_blob = " ".join(snippets)
    lowered_blob = text_blob.lower()
    for candidate in tool_candidates:
        if candidate in lowered_blob:
            tools.append(candidate)

    return {
        "snippets": list(dict.fromkeys(snippets))[:6],
        "versions": _extract_versions(text_blob),
        "tools": tools[:5],
        "urls": list(dict.fromkeys(urls))[:4],
    }


def _context_text(sections: dict[str, str]) -> str:
    return " ".join(value for value in sections.values() if value).strip()


def _section_preview(xml: str, tag: str) -> str:
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _strip_tags(match.group(1))[:200]


def _dedupe_suggestions(suggestions: list[Suggestion]) -> list[Suggestion]:
    best_by_rule: dict[str, Suggestion] = {}
    for suggestion in suggestions:
        existing = best_by_rule.get(suggestion.rule_id)
        if existing is None:
            best_by_rule[suggestion.rule_id] = suggestion
            continue
        existing_rank = (_SEVERITY_ORDER.get(existing.severity, 9), -existing.confidence, -len(existing.evidence))
        candidate_rank = (_SEVERITY_ORDER.get(suggestion.severity, 9), -suggestion.confidence, -len(suggestion.evidence))
        if candidate_rank < existing_rank:
            best_by_rule[suggestion.rule_id] = suggestion
    return list(best_by_rule.values())


def _check_missing_elements(sections: dict[str, str], dita_type: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for element in _required_elements(dita_type):
        if element in sections:
            continue
        suggestions.append(
            Suggestion(
                id=f"missing_{element}",
                severity="error",
                section=element,
                title=f"Missing <{element}>",
                why=f"{element} is expected for a {dita_type} topic and improves validation readiness.",
                before=f"No <{element}> section is present.",
                after=_generate_placeholder(element, sections),
                fix_type="generate",
                fix_prompt=f"Add a strong <{element}> section for this {dita_type} topic.",
                confidence=1.0,
                rule_id=f"missing_{element}",
            )
        )
    return suggestions


def _fix_shortdesc_prefix(text: str) -> str:
    cleaned = re.sub(
        r"^this (topic|document|article|page)\s+(explains?|describes?|covers?|provides?)\s*(how to|the|about)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    if not cleaned:
        return text
    if not cleaned.endswith("."):
        cleaned = f"{cleaned}."
    return cleaned[0].upper() + cleaned[1:]


def _check_shortdesc(sections: dict[str, str]) -> list[Suggestion]:
    shortdesc = sections.get("shortdesc", "")
    if not shortdesc:
        return []
    suggestions: list[Suggestion] = []

    if re.match(r"^this (topic|document|article|page)\b", shortdesc, re.IGNORECASE):
        suggestions.append(
            Suggestion(
                id="shortdesc_this_topic",
                severity="warning",
                section="shortdesc",
                title="Shortdesc starts with 'This topic'",
                why="Shortdescs are stronger when they start with a clear action or outcome.",
                before=shortdesc,
                after=_fix_shortdesc_prefix(shortdesc),
                fix_type="one_click",
                fix_prompt=f"Rewrite this shortdesc to start with a verb: {shortdesc}",
                confidence=1.0,
                rule_id="shortdesc_this_topic",
            )
        )

    word_count = len(shortdesc.split())
    if word_count > 50:
        suggestions.append(
            Suggestion(
                id="shortdesc_too_long",
                severity="warning",
                section="shortdesc",
                title=f"Shortdesc is too long ({word_count} words)",
                why="Shortdescs should stay concise for search results, topic lists, and readability.",
                before=shortdesc,
                after=" ".join(shortdesc.split()[:35]).rstrip(".") + ".",
                fix_type="preview",
                fix_prompt=f"Shorten this shortdesc to fewer than 50 words: {shortdesc}",
                confidence=1.0,
                rule_id="shortdesc_length",
            )
        )

    if re.search(r"\b(is used to|can be used to|is designed to)\b", shortdesc, re.IGNORECASE):
        suggestions.append(
            Suggestion(
                id="shortdesc_passive",
                severity="info",
                section="shortdesc",
                title="Shortdesc uses passive phrasing",
                why="Active phrasing is usually clearer for procedural content.",
                before=shortdesc,
                after=re.sub(r"is used to", "enables", shortdesc, flags=re.IGNORECASE),
                fix_type="preview",
                fix_prompt=f"Rewrite this shortdesc in active voice: {shortdesc}",
                confidence=0.8,
                rule_id="shortdesc_passive",
            )
        )
    return suggestions


def _check_vague_steps(steps: list[str]) -> list[Suggestion]:
    vague_patterns = [
        (r"^check (the|your)?\s*(settings?|config|configuration)\.?$", "Specify where and what to check."),
        (r"^verify (it|that it|the)\s*(works?|is correct)\.?$", "Specify what to verify and where."),
        (r"^open the (file|document|application)\.?$", "Name the exact file or application."),
        (r"^(save|submit|apply)\.?$", "Explain what is being saved and where."),
        (r"^click (ok|yes|confirm|apply)\.?$", "Specify the exact dialog or button context."),
    ]
    matches: list[str] = []
    for index, step in enumerate(steps, start=1):
        for pattern, reason in vague_patterns:
            if re.match(pattern, step, re.IGNORECASE):
                matches.append(f"Step {index}: {step} - {reason}")
                break
    if not matches:
        return []
    return [
        Suggestion(
            id="vague_steps",
            severity="warning",
            section="steps",
            title=f"{len(matches)} vague step{'s' if len(matches) != 1 else ''}",
            why="Each cmd should be specific enough to follow without guessing.",
            before="\n".join(matches),
            after="Rewrite the steps with exact paths, tools, and expected outcomes.",
            fix_type="generate",
            fix_prompt="Rewrite these vague steps with specific paths and actions.",
            confidence=0.9,
            rule_id="vague_steps",
        )
    ]


def _check_terminology(sections: dict[str, str], terminology: dict[str, str]) -> list[Suggestion]:
    if not terminology:
        return []
    text = " ".join(sections.values()).lower()
    violations = [
        (generic, specific)
        for generic, specific in list(terminology.items())[:25]
        if generic.lower() in text and specific.lower() not in text
    ]
    if not violations:
        return []
    preview = ", ".join(f"'{generic}' -> '{specific}'" for generic, specific in violations[:3])
    return [
        Suggestion(
            id="tenant_terminology",
            severity="info",
            section="content",
            title=f"{len(violations)} terminology issue{'s' if len(violations) != 1 else ''}",
            why="Client-specific terminology keeps the output aligned with the tenant knowledge base.",
            before=preview,
            after="Replace generic terms with the tenant-approved vocabulary.",
            fix_type="one_click",
            fix_prompt="Replace generic terms with tenant-specific terminology.",
            confidence=0.85,
            rule_id="terminology",
        )
    ]


def _check_version_context(sections: dict[str, str]) -> list[Suggestion]:
    text = " ".join(sections.values()).lower()
    if not any(token in text for token in ("version", "release", "upgrade", "update", "deprecated")):
        return []
    if re.search(r"\b\d+\.\d+\b", text):
        return []
    return [
        Suggestion(
            id="version_number_missing",
            severity="info",
            section="note",
            title="Version is mentioned but the number is missing",
            why="Version-specific content is more actionable when the exact version is stated.",
            before="Version keywords appear without a specific version number.",
            after="Add an explicit version such as 4.2 or 6.5.",
            fix_type="preview",
            fix_prompt="Add the specific version number where version-related wording appears.",
            confidence=0.75,
            rule_id="version_number",
        )
    ]


def _check_suggested_elements(sections: dict[str, str], dita_type: str) -> list[Suggestion]:
    text = " ".join(sections.values()).lower()
    suggestions: list[Suggestion] = []
    if dita_type == "task" and "prereq" not in sections and any(tool in text for tool in ("aem guides", "oxygen", "terminal", "portal")):
        suggestions.append(
            Suggestion(
                id="suggest_prereq",
                severity="info",
                section="prereq",
                title="Consider adding a prereq section",
                why="Tool and environment signals suggest the reader may need setup information first.",
                before="No prereq section is present.",
                after=_generate_placeholder("prereq", sections),
                fix_type="generate",
                fix_prompt="Add a prereq section based on the tools and access implied by the content.",
                confidence=0.7,
                rule_id="suggest_prereq",
            )
        )
    return suggestions


def _body_parent_tag(dita_type: str) -> str:
    return {
        "task": "taskbody",
        "concept": "conbody",
        "reference": "refbody",
        "glossentry": "glossdef",
    }.get(dita_type, "body")


def _first_external_url(research_context: dict | None) -> str:
    signals = _extract_research_highlights(research_context)
    for url in signals.get("urls", []):
        if str(url).startswith(("http://", "https://")):
            return str(url)
    return ""


def _issue_has_video_attachment(issue: dict) -> bool:
    for attachment in issue.get("attachments") or []:
        if isinstance(attachment, dict) and attachment.get("is_video"):
            return True
    return False


def _slugify_fragment(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return value or "reusable-fragment"


def _keyword_terms(issue: dict, sections: dict[str, str], limit: int = 5) -> list[str]:
    candidates: list[str] = []
    candidates.extend(str(item).strip() for item in (issue.get("components") or []) if str(item).strip())
    candidates.extend(str(item).strip() for item in (issue.get("labels") or []) if str(item).strip())
    candidates.extend(_extract_issue_terms(issue, limit=limit + 2))
    title = sections.get("title") or ""
    if "AEM Guides" in title:
        candidates.insert(0, "AEM Guides")

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = re.sub(r"[_-]+", " ", str(candidate)).strip()
        lowered = cleaned.lower()
        if not cleaned or lowered in seen or lowered in _STOPWORDS or lowered in _GENERIC_ISSUE_TERMS:
            continue
        if len(cleaned) < 3:
            continue
        seen.add(lowered)
        unique.append(cleaned)
    return unique[:limit]


def _first_reusable_phrase(xml: str) -> tuple[str, str] | None:
    visible_text = _strip_tags(xml)
    phrases = [
        ("AEM Guides", "aem-guides"),
        ("Experience League", "experience-league"),
        ("CircleCI", "circleci"),
        ("DITA", "dita"),
    ]
    for phrase, key in phrases:
        if phrase in visible_text:
            return phrase, key
    return None


def _check_reuse_opportunities(
    xml: str,
    sections: dict[str, str],
    issue: dict,
    dita_type: str,
    quality_breakdown: dict | None,
) -> list[Suggestion]:
    breakdown = quality_breakdown or {}
    dita_features = int(breakdown.get("dita_features") or 0)
    content_richness = int(breakdown.get("content_richness") or 0)
    xml_lower = xml.lower()
    suggestions: list[Suggestion] = []
    title = sections.get("title", "")
    issue_summary = issue.get("summary") or title or "this topic"

    if title and "<title" in xml_lower and "conref=" not in xml_lower and "conkeyref=" not in xml_lower:
        if dita_features < 16 or title.strip().lower() == (issue.get("summary") or "").strip().lower():
            slug = _slugify_fragment(title)
            suggestions.append(
                Suggestion(
                    id="reuse_title_conref",
                    severity="info",
                    section="title",
                    title="Make the title reusable with conref",
                    why="If multiple topics use the same capability title, a shared title fragment makes updates safer and more consistent.",
                    before=title,
                    after=f'Use a reusable title source such as <title conref="reuse/reusable-titles.dita#reusable_titles/{slug}">{title}</title>.',
                    fix_type="one_click",
                    fix_prompt="Add a conref to the title so the same user-facing title can be reused across related topics.",
                    confidence=0.8,
                    rule_id="reuse_title_conref",
                    impact="Medium: title reuse and consistency improve across the topic set.",
                    evidence=[issue_summary],
                )
            )

    if dita_type in {"task", "concept", "reference"} and "<keywords" not in xml_lower:
        terms = _keyword_terms(issue, sections)
        if terms:
            suggestions.append(
                Suggestion(
                    id="reuse_add_keywords",
                    severity="info",
                    section="prolog",
                    title="Add keywords for findability and reuse",
                    why="Keywords improve search and let the topic carry reusable metadata for maps, filtering, and topic discovery.",
                    before="No <keywords> metadata is present.",
                    after="Add keywords such as: " + ", ".join(terms[:4]) + ".",
                    fix_type="one_click",
                    fix_prompt="Add a keywords block in prolog metadata using the strongest issue and product terms.",
                    confidence=0.84,
                    rule_id="reuse_add_keywords",
                    impact="Medium: metadata quality and discoverability improve.",
                    evidence=terms[:3],
                )
            )

    reusable_phrase = _first_reusable_phrase(xml)
    if reusable_phrase and "keyref=" not in xml_lower:
        phrase, key = reusable_phrase
        suggestions.append(
            Suggestion(
                id="reuse_add_keyref",
                severity="info",
                section="content",
                title="Use keyref for shared product naming",
                why="Keyrefs help keep product names, brands, and shared labels consistent across topics and maps.",
                before=f'The topic hard-codes "{phrase}" in the body text.',
                after=f'Use a key-backed inline phrase such as <ph keyref="{key}">{phrase}</ph> where the shared product name appears.',
                fix_type="one_click",
                fix_prompt=f"Replace one hard-coded '{phrase}' mention with a keyref-backed inline phrase.",
                confidence=0.78,
                rule_id="reuse_add_keyref",
                impact="Medium: terminology becomes easier to govern across the doc set.",
                evidence=[phrase, issue_summary],
            )
        )

    if "conref=" not in xml_lower and "conkeyref=" not in xml_lower and (content_richness < 18 or dita_features < 18):
        fragment_slug = _slugify_fragment(issue_summary)
        suggestions.append(
            Suggestion(
                id="reuse_add_conkeyref",
                severity="info",
                section="reuse",
                title="Reuse shared topic text with conkeyref",
                why="Common setup notes, verification guidance, or scope text are better managed as reusable fragments instead of being duplicated topic by topic.",
                before="No reusable fragment reference is present in the topic body.",
                after=f'Pull a shared fragment into the topic body, for example <note conkeyref="reuse/reusable-blocks/{fragment_slug}-verification"/>.',
                fix_type="one_click",
                fix_prompt="Add a reusable conkeyref-backed note or body fragment for setup or verification guidance.",
                confidence=0.74,
                rule_id="reuse_add_conkeyref",
                impact="Medium: body-text reuse improves and repeated maintenance goes down.",
                evidence=[issue_summary],
            )
        )

    return suggestions


def _check_quality_gap_suggestions(
    xml: str,
    sections: dict[str, str],
    dita_type: str,
    issue: dict,
    research_context: dict | None,
    quality_breakdown: dict | None,
) -> list[Suggestion]:
    breakdown = quality_breakdown or {}
    content_richness = int(breakdown.get("content_richness") or 0)
    dita_features = int(breakdown.get("dita_features") or 0)
    suggestions: list[Suggestion] = []
    issue_summary = issue.get("summary") or "this topic"

    if content_richness < 15 and "<example" not in xml.lower():
        suggestions.append(
            Suggestion(
                id="quality_add_example",
                severity="warning" if content_richness < 10 else "info",
                section="example",
                title="Add a concrete example to improve content richness",
                why="The topic is structurally valid, but it still lacks an example that shows the reader what the issue or outcome looks like.",
                before="No <example> element is present.",
                after=f"Add an <example> that shows {issue_summary.lower()} in a realistic authoring scenario.",
                fix_type="generate",
                fix_prompt="Add a concise example section that demonstrates the issue and the expected outcome in a realistic AEM Guides scenario.",
                confidence=0.9,
                rule_id="quality_add_example",
                impact="Medium: content richness and instructional clarity improve.",
                evidence=[issue_summary],
            )
        )

    if content_richness < 12 and "<note" not in xml.lower():
        suggestions.append(
            Suggestion(
                id="quality_add_note",
                severity="info",
                section="note",
                title="Add a note with scope, caveat, or verification guidance",
                why="A short note can capture validation context, caveats, or when the procedure applies, which improves topic depth without bloating the steps.",
                before="No <note> element is present.",
                after="Add a brief note that explains scope, caveats, or how to verify the fix in AEM Guides.",
                fix_type="generate",
                fix_prompt="Add a short note that clarifies scope, caveats, or verification guidance for this topic.",
                confidence=0.82,
                rule_id="quality_add_note",
                impact="Low: content richness improves and the topic becomes more complete.",
                evidence=[_context_text(sections)[:180]],
            )
        )

    issue_blob = _issue_text(issue).lower()
    config_signals = ("css", "javascript", "circleci", "yaml", "json", "selector", "config", "configuration")
    if content_richness < 12 and "<codeblock" not in xml.lower() and any(signal in issue_blob for signal in config_signals):
        suggestions.append(
            Suggestion(
                id="quality_add_codeblock",
                severity="info",
                section="example",
                title="Consider adding a codeblock or configuration snippet",
                why="This looks like a config or implementation issue, so a short codeblock can make the fix much easier to apply.",
                before="No <codeblock> element is present.",
                after="Add a minimal codeblock or selector snippet that shows the relevant change.",
                fix_type="generate",
                fix_prompt="Add a minimal codeblock that shows the relevant selector, script, or configuration change for this task.",
                confidence=0.78,
                rule_id="quality_add_codeblock",
                impact="Medium: content richness improves and the guidance becomes more actionable.",
                evidence=[issue_summary],
            )
        )

    if dita_features < 10 and "<xref" not in xml.lower():
        url = _first_external_url(research_context)
        if url:
            suggestions.append(
                Suggestion(
                    id="quality_add_xref",
                    severity="info",
                    section="related-links",
                    title="Add an xref to supporting guidance",
                    why="The score is low on DITA features, and the research already found a supporting source that could be linked from the topic.",
                    before="No <xref> element is present.",
                    after=f'Add an xref to the supporting guidance: <xref href="{url}" scope="external" format="html">Related guidance</xref>.',
                    fix_type="one_click",
                    fix_prompt=f"Add an external xref to this supporting guidance: {url}",
                    confidence=0.84,
                    rule_id="quality_add_xref",
                    impact="Medium: DITA feature coverage improves and the topic gains a useful next step.",
                    evidence=[url],
                )
            )

    if dita_features < 10 and "<object" not in xml.lower() and _issue_has_video_attachment(issue):
        suggestions.append(
            Suggestion(
                id="quality_add_media_object",
                severity="warning",
                section="media",
                title="Embed the supporting Jira video with a DITA object",
                why="The issue includes a video attachment, and embedding it makes the topic more concrete while improving DITA feature coverage.",
                before="The Jira issue has a video attachment, but the XML does not reference it.",
                after="Add an <object> element for the attached video in a short Related media section.",
                fix_type="generate",
                fix_prompt="Add a Related media section and embed the attached Jira video with a DITA object element.",
                confidence=0.92,
                rule_id="quality_add_media_object",
                impact="High: DITA feature coverage improves and the topic gains supporting evidence.",
                evidence=[issue_summary],
            )
        )

    if dita_features < 8 and not any(tag in xml.lower() for tag in ("<xref", "<object", "<fig", "keyref=", "conref=")):
        suggestions.append(
            Suggestion(
                id="quality_add_dita_feature",
                severity="info",
                section="content",
                title="Add one more meaningful DITA feature",
                why="The topic is valid, but it still reads like plain XML text. Adding one meaningful DITA construct can improve reuse, navigation, or media richness.",
                before="No xref, object, fig, keyref, or conref is present.",
                after="Add a relevant xref, object, fig, keyref, or conref where it genuinely helps the reader.",
                fix_type="preview",
                fix_prompt="Add one meaningful DITA feature such as an xref, object, fig, keyref, or conref where it adds reader value.",
                confidence=0.76,
                rule_id="quality_add_dita_feature",
                impact="Low: DITA feature score improves and the topic feels more production-ready.",
                evidence=[issue_summary],
            )
        )

    if dita_type in {"task", "concept", "reference"} and "<prolog" not in xml.lower():
        suggestions.append(
            Suggestion(
                id="quality_add_prolog",
                severity="info",
                section="prolog",
                title="Add prolog metadata",
                why="A prolog with basic metadata improves AEM readiness and makes the topic feel more complete.",
                before="No <prolog> metadata block is present.",
                after="Add a prolog with created date and Jira key metadata.",
                fix_type="one_click",
                fix_prompt="Add a prolog with created date and Jira key metadata.",
                confidence=0.8,
                rule_id="quality_add_prolog",
                impact="Medium: structure and AEM readiness both improve.",
                evidence=[issue_summary],
            )
        )

    return suggestions


def _check_validation_findings(validation: list[dict], dita_type: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    for finding in validation or []:
        if finding.get("passing"):
            continue
        label = str(finding.get("label") or "")
        if label.startswith("XML parse error"):
            suggestions.append(
                Suggestion(
                    id="xml_parse_error",
                    severity="error",
                    section="document",
                    title="XML is not well formed",
                    why="The topic cannot be trusted until the XML parses cleanly.",
                    before=label,
                    after="Close the malformed tags and return a single well-formed DITA document.",
                    fix_type="generate",
                    fix_prompt="Repair the malformed XML and return well-formed DITA only.",
                    confidence=1.0,
                    rule_id="xml_parse_error",
                    impact="High: broken XML blocks validation and downstream processing.",
                    evidence=[label],
                )
            )
            continue

        matched = None
        for prefix, config in _VALIDATION_RULES.items():
            if label.startswith(prefix):
                matched = config
                break
        if matched is None:
            continue

        suggestions.append(
            Suggestion(
                id=matched["rule_id"],
                severity="error",
                section=matched["section"],
                title=matched["title"],
                why=matched["why"],
                before=label,
                after=matched["after"],
                fix_type="one_click",
                fix_prompt=matched["fix_prompt"],
                confidence=0.98,
                rule_id=matched["rule_id"],
                impact=matched["impact"],
                evidence=[label],
            )
        )
    return suggestions


def _check_title_alignment(sections: dict[str, str], issue: dict, dita_type: str) -> list[Suggestion]:
    title = sections.get("title", "")
    if not title or not issue.get("summary"):
        return []
    suggestions: list[Suggestion] = []
    try:
        from app.services.intent_translator import infer_intent, transform_summary_to_title

        primary_intent = infer_intent(issue)[0].intent_type
        recommended = transform_summary_to_title(issue.get("summary", ""), primary_intent)
    except Exception:
        recommended = issue.get("summary", "")

    if dita_type != "task" and re.match(r"^(add|implement|support|update|fix|resolve|enable)\b", title, re.IGNORECASE):
        suggestions.append(
            Suggestion(
                id="title_work_item_jargon",
                severity="warning",
                section="title",
                title="Title reads like a Jira work item",
                why="Concept and reference titles are stronger when they describe the capability or subject, not the internal work item.",
                before=title,
                after=recommended,
                fix_type="one_click",
                fix_prompt=f"Rewrite the title to sound like user-facing documentation instead of a Jira task: {title}",
                confidence=0.88,
                rule_id="title_work_item_jargon",
                impact="Medium: the topic feels more production-ready and user-facing.",
                evidence=[issue.get("summary", "")],
            )
        )

    if title.strip().lower() == (issue.get("summary") or "").strip().lower():
        suggestions.append(
            Suggestion(
                id="title_matches_jira_summary",
                severity="info",
                section="title",
                title="Title mirrors the Jira summary exactly",
                why="Generated documentation usually reads better after translating the Jira summary into user-facing wording.",
                before=title,
                after=recommended,
                fix_type="one_click",
                fix_prompt="Rewrite the title to be user-facing and documentation-ready.",
                confidence=0.76,
                rule_id="title_matches_jira_summary",
                impact="Low: readability improves and the topic feels less issue-tracker-driven.",
                evidence=[issue.get("summary", "")],
            )
        )
    return suggestions


def _check_issue_coverage(sections: dict[str, str], issue: dict) -> list[Suggestion]:
    content = _context_text(sections).lower()
    issue_terms = _extract_issue_terms(issue)
    missing = [term for term in issue_terms if term.lower() not in content]
    if len(missing) < 2:
        return []
    return [
        Suggestion(
            id="issue_coverage_gap",
            severity="warning",
            section="content",
            title="Topic misses key issue-specific concepts",
            why="The document should explicitly cover the most important product or feature terms from the Jira issue.",
            before=", ".join(missing[:4]),
            after=f"Work the missing concepts into the title, shortdesc, or body: {', '.join(missing[:3])}.",
            fix_type="generate",
            fix_prompt=f"Revise the topic so it explicitly covers these issue concepts: {', '.join(missing[:4])}.",
            confidence=0.84,
            rule_id="issue_coverage_gap",
            impact="High: the topic will track the actual Jira intent more closely.",
            evidence=[issue.get("summary", "")] + ([issue.get("description", "")[:180]] if issue.get("description") else []),
        )
    ]


def _check_bug_report_language(sections: dict[str, str]) -> list[Suggestion]:
    text = _context_text(sections)
    matches = re.findall(
        r"\b(steps to reproduce|actual result|expected result|jira|ticket|bug|defect|repro|workaround)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not matches:
        return []
    unique = list(dict.fromkeys(match.lower() for match in matches))
    return [
        Suggestion(
            id="bug_report_language",
            severity="warning",
            section="content",
            title="Content still sounds like a bug report",
            why="Production docs should explain the user task or concept, not echo QA or issue-tracker language.",
            before=", ".join(unique[:5]),
            after="Rewrite the affected text from the user perspective and remove issue-tracker phrasing.",
            fix_type="generate",
            fix_prompt="Rewrite the topic so it sounds like documentation, not a bug report.",
            confidence=0.9,
            rule_id="bug_report_language",
            impact="High: tone and usability improve immediately.",
            evidence=[_context_text(sections)[:220]],
        )
    ]


def _check_task_depth(steps: list[str], dita_type: str) -> list[Suggestion]:
    if dita_type != "task":
        return []
    suggestions: list[Suggestion] = []
    if len(steps) < 2:
        suggestions.append(
            Suggestion(
                id="task_steps_too_few",
                severity="warning",
                section="steps",
                title="Task has too few steps",
                why="Most user-facing procedures need at least two concrete actions to be truly usable.",
                before="\n".join(steps) or "No executable steps found.",
                after="Add at least one more concrete step that includes the key action or verification.",
                fix_type="generate",
                fix_prompt="Expand the procedure into at least two clear user-facing steps.",
                confidence=0.86,
                rule_id="task_steps_too_few",
                impact="Medium: the procedure becomes more complete and easier to follow.",
                evidence=steps[:2],
            )
        )

    duplicates = [step for step in steps if steps.count(step) > 1]
    if duplicates:
        suggestions.append(
            Suggestion(
                id="task_duplicate_steps",
                severity="info",
                section="steps",
                title="Task repeats the same step wording",
                why="Duplicate steps make the procedure feel unfinished or unclear.",
                before="\n".join(list(dict.fromkeys(duplicates))[:3]),
                after="Merge or differentiate the repeated steps so each one adds a distinct action.",
                fix_type="generate",
                fix_prompt="Remove duplicate step wording and make each step distinct.",
                confidence=0.73,
                rule_id="task_duplicate_steps",
                impact="Low: step clarity improves.",
                evidence=list(dict.fromkeys(duplicates))[:2],
            )
        )
    return suggestions


def _check_research_alignment(sections: dict[str, str], research_context: dict | None) -> list[Suggestion]:
    if not isinstance(research_context, dict):
        return []
    signals = _extract_research_highlights(research_context)
    content = _context_text(sections).lower()
    suggestions: list[Suggestion] = []

    for version in signals["versions"]:
        if version not in content:
            suggestions.append(
                Suggestion(
                    id="research_version_note",
                    severity="info",
                    section="note",
                    title="Research mentions a version that the topic does not name",
                    why="If the guidance is version-sensitive, the topic should say which version it applies to.",
                    before=f"Research references version {version}, but the XML does not mention it.",
                    after=f"Add a version note such as 'Applies to version {version}.'",
                    fix_type="preview",
                    fix_prompt=f"Add a concise version note for {version} if it is truly relevant to the topic.",
                    confidence=0.74,
                    rule_id="research_version_note",
                    impact="Low: the topic becomes more precise for versioned behavior.",
                    evidence=signals["snippets"][:2],
                )
            )
            break

    if signals["tools"]:
        missing_tools = [tool for tool in signals["tools"] if tool not in content]
        if missing_tools:
            suggestions.append(
                Suggestion(
                    id="research_tool_alignment",
                    severity="info",
                    section="content",
                    title="Research surfaced tools or concepts not reflected in the topic",
                    why="When research repeatedly mentions a product surface or DITA concept, the topic may need to name it explicitly.",
                    before=", ".join(missing_tools[:4]),
                    after=f"Check whether these concepts belong in the topic: {', '.join(missing_tools[:3])}.",
                    fix_type="preview",
                    fix_prompt=f"Review whether these research-backed concepts should be included: {', '.join(missing_tools[:4])}.",
                    confidence=0.67,
                    rule_id="research_tool_alignment",
                    impact="Low: research coverage becomes more visible in the final topic.",
                    evidence=signals["snippets"][:2] + signals["urls"][:1],
                )
            )
    return suggestions


def _build_refine_completions(suggestions: list[Suggestion], terminology: dict[str, str]) -> list[str]:
    completions: list[str] = []
    for suggestion in suggestions[:4]:
        if suggestion.rule_id.startswith("missing_"):
            completions.append(f"Add {suggestion.section} section")
        elif suggestion.rule_id.startswith("shortdesc"):
            completions.append("Strengthen the shortdesc")
        elif suggestion.rule_id == "vague_steps":
            completions.append("Make the steps more specific")
        elif suggestion.rule_id == "issue_coverage_gap":
            completions.append("Cover the missing issue concepts")
        elif suggestion.rule_id == "bug_report_language":
            completions.append("Rewrite in a user-facing tone")
        elif suggestion.rule_id.startswith("title_"):
            completions.append("Make the title user-facing")
        elif suggestion.rule_id == "reuse_title_conref":
            completions.append("Turn the title into a reusable conref")
        elif suggestion.rule_id == "reuse_add_keywords":
            completions.append("Add reusable keywords metadata")
        elif suggestion.rule_id == "reuse_add_keyref":
            completions.append("Replace hard-coded product names with keyrefs")
        elif suggestion.rule_id == "reuse_add_conkeyref":
            completions.append("Pull shared setup text from a conkeyref fragment")
    for generic, specific in list(terminology.items())[:3]:
        completions.append(f"Replace '{generic}' with '{specific}'")
    completions.extend(
        [
            "Add a troubleshooting note",
            "Add version compatibility note",
            "Make the shortdesc more concise",
            "Add a concrete example",
        ]
    )
    return list(dict.fromkeys(completions))[:8]


def _clean_xml(xml: str) -> str:
    cleaned = (xml or "").strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(
            line for line in cleaned.splitlines() if not line.strip().startswith("```")
        ).strip()
    return cleaned


def _extract_issue_key_hint(xml: str) -> str:
    for pattern in (
        r'content="([A-Z][A-Z0-9]+-\d+)"',
        r"\b([A-Z][A-Z0-9]+-\d+)\b",
    ):
        match = re.search(pattern, xml or "")
        if match:
            return match.group(1)
    return ""


def _serialize_research_context(research_context: dict | str | None) -> str:
    if isinstance(research_context, str):
        return research_context.strip()[:4000]
    if not isinstance(research_context, dict):
        return ""

    blocks: list[str] = []
    for result in research_context.get("results", []) or []:
        summary = str(result.get("summary") or "").strip()
        if summary:
            blocks.append(summary)
        for chunk in (result.get("chunks") or [])[:3]:
            text = str(chunk or "").strip()
            if text:
                blocks.append(text)
        for url in (result.get("urls") or [])[:2]:
            text = str(url or "").strip()
            if text:
                blocks.append(f"Source: {text}")
    return "\n".join(blocks)[:4000]


def _root_has_xml_lang(xml: str, dita_type: str) -> bool:
    return bool(re.search(rf"<{dita_type}\b[^>]*\bxml:lang\s*=\s*['\"][^'\"]+['\"]", xml or "", re.IGNORECASE))


def _simple_validation_checks(xml: str, dita_type: str) -> list[dict[str, object]]:
    from app.services.dita_xml_headers import strip_xml_prolog

    cleaned = _clean_xml(xml)
    body = strip_xml_prolog(cleaned)
    checks: list[dict[str, object]] = [
        {"label": "XML declaration present", "passing": cleaned.lstrip().startswith("<?xml")},
        {"label": "Required DTD header present", "passing": "<!DOCTYPE" in cleaned[:260]},
        {"label": "shortdesc present", "passing": bool(re.search(r"<shortdesc\b", body, re.IGNORECASE))},
        {"label": "xml:lang present", "passing": _root_has_xml_lang(body, dita_type)},
    ]
    if dita_type == "task":
        checks.extend(
            [
                {"label": "taskbody present", "passing": bool(re.search(r"<taskbody\b", body, re.IGNORECASE))},
                {"label": "steps present", "passing": bool(re.search(r"<steps\b", body, re.IGNORECASE))},
                {"label": "cmd in steps", "passing": bool(re.search(r"<cmd\b", body, re.IGNORECASE))},
            ]
        )
    elif dita_type == "concept":
        checks.append({"label": "conbody present", "passing": bool(re.search(r"<conbody\b", body, re.IGNORECASE))})
    elif dita_type == "reference":
        checks.append({"label": "refbody present", "passing": bool(re.search(r"<refbody\b", body, re.IGNORECASE))})
    elif dita_type == "glossentry":
        checks.append({"label": "glossdef present", "passing": bool(re.search(r"<glossdef\b", body, re.IGNORECASE))})
    else:
        checks.append({"label": "body present", "passing": bool(re.search(r"<body\b", body, re.IGNORECASE))})
    return checks


def _estimate_quality_breakdown(xml: str, dita_type: str, validation: list[dict[str, object]]) -> dict[str, int]:
    content = (xml or "").lower()
    validation_pass_rate = (
        sum(1 for item in validation if item.get("passing")) / max(len(validation), 1)
    )
    structure = int(round(validation_pass_rate * 100))

    richness_points = 0
    for token in ("<shortdesc", "<context", "<result", "<postreq", "<example", "<note"):
        if token in content:
            richness_points += 1
    content_richness = min(100, richness_points * 18)

    dita_feature_points = 0
    for token in ("<xref", "<codeblock", "<object", " keyref=", " conref=", " conkeyref=", "<keywords"):
        if token in content:
            dita_feature_points += 1
    dita_features = min(100, dita_feature_points * 20)

    readiness = int(round((structure + content_richness + dita_features) / 3))
    if dita_type == "task" and "<taskbody" in content and "<steps" in content:
        readiness = min(100, readiness + 10)

    return {
        "structure": structure,
        "content_richness": content_richness,
        "dita_features": dita_features,
        "aem_readiness": readiness,
    }


async def _evaluate_content_for_response(content: str, dita_type: str, file_hint: str = "") -> dict[str, Any]:
    del file_hint
    validation = _simple_validation_checks(content, dita_type)
    quality_breakdown = _estimate_quality_breakdown(content, dita_type, validation)
    quality_score = int(round(sum(quality_breakdown.values()) / max(len(quality_breakdown), 1)))
    return {
        "quality_score": quality_score,
        "quality_breakdown": quality_breakdown,
        "validation": validation,
        "aem_guides_validation_errors": [],
        "aem_guides_validation_status": {
            "enabled": False,
            "configured": False,
            "success": False,
            "warning": "Authoring validation is not available in chat-only mode.",
        },
    }


def _build_placeholder_shortdesc(issue: dict | None, dita_type: str) -> str:
    title = str((issue or {}).get("summary") or "this topic").strip()
    if dita_type == "task":
        return f"Complete {title.lower()} by following these steps."
    if dita_type == "concept":
        return f"Understand {title.lower()}."
    if dita_type == "reference":
        return f"Reference details for {title.lower()}."
    return f"Overview of {title.lower()}."


def _apply_instruction_refinement(
    content: str,
    instruction: str,
    issue: dict,
    intent: dict,
    research_text: str,
) -> tuple[str, str, list[str]]:
    del intent, research_text
    from app.services.dita_xml_headers import detect_dita_type_from_content

    refined = _clean_xml(content)
    dita_type = detect_dita_type_from_content(refined)
    actions: list[str] = []
    instruction_lower = (instruction or "").lower()
    if "shortdesc" in instruction_lower and "<shortdesc" not in refined.lower():
        replacement = f"\\1\n  <shortdesc>{_build_placeholder_shortdesc(issue, dita_type)}</shortdesc>"
        refined = re.sub(r"(<title[^>]*>.*?</title>)", replacement, refined, count=1, flags=re.IGNORECASE | re.DOTALL)
        actions.append("instruction_refinement")
    return refined, dita_type, actions


def _inject_issue_media(content: str, dita_type: str, issue: dict) -> tuple[str, list[str]]:
    del dita_type, issue
    return content, []


def _apply_structural_repairs(
    content: str,
    dita_type: str,
    issue: dict,
    issue_key: str,
) -> tuple[str, str, list[str]]:
    from app.services.dita_xml_headers import normalize_dita_document

    repaired, resolved_type = normalize_dita_document(_clean_xml(content), dita_type=dita_type or None)
    actions: list[str] = []

    if not _root_has_xml_lang(repaired, resolved_type):
        repaired = re.sub(
            rf"(<{resolved_type}\b)([^>]*?)>",
            rf'\1\2 xml:lang="en-US">',
            repaired,
            count=1,
            flags=re.IGNORECASE,
        )
        actions.append("structural_repair")

    if resolved_type != "glossentry" and "<shortdesc" not in repaired.lower():
        repaired = re.sub(
            r"(<title[^>]*>.*?</title>)",
            rf"\1\n  <shortdesc>{_build_placeholder_shortdesc(issue, resolved_type)}</shortdesc>",
            repaired,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        actions.append("structural_repair")

    if resolved_type == "task":
        if "<taskbody" not in repaired.lower():
            summary = str(issue.get("summary") or issue_key or "the task").strip().rstrip(".")
            snippet = (
                "\n  <taskbody>\n"
                "    <context>\n"
                f"      <p>Use this task when working on {summary.lower()}.</p>\n"
                "    </context>\n"
                "    <steps>\n"
                "      <step>\n"
                "        <cmd>Complete the required action.</cmd>\n"
                "      </step>\n"
                "    </steps>\n"
                "    <result>\n"
                "      <p>The task completes successfully.</p>\n"
                "    </result>\n"
                "  </taskbody>\n"
            )
            repaired = repaired.replace("</task>", f"{snippet}</task>", 1)
            actions.append("structural_repair")
        else:
            if "<steps" not in repaired.lower():
                repaired = _inject_into_parent(
                    repaired,
                    "taskbody",
                    "\n    <steps>\n      <step>\n        <cmd>Complete the required action.</cmd>\n      </step>\n    </steps>",
                    before_tag="result",
                )
                actions.append("structural_repair")
            if "<cmd" not in repaired.lower():
                repaired = re.sub(
                    r"(<step\b[^>]*>)(\s*)(?!<cmd)",
                    r"\1\2<cmd>Complete the required action.</cmd>\n        ",
                    repaired,
                    count=1,
                    flags=re.IGNORECASE,
                )
                actions.append("structural_repair")
            if "<result" not in repaired.lower():
                repaired = _inject_into_parent(
                    repaired,
                    "taskbody",
                    "\n    <result>\n      <p>The task completes successfully.</p>\n    </result>",
                )
                actions.append("structural_repair")
    elif resolved_type == "concept" and "<conbody" not in repaired.lower():
        repaired = repaired.replace(
            "</concept>",
            "\n  <conbody>\n    <p>Provide the conceptual explanation here.</p>\n  </conbody>\n</concept>",
            1,
        )
        actions.append("structural_repair")
    elif resolved_type == "reference" and "<refbody" not in repaired.lower():
        repaired = repaired.replace(
            "</reference>",
            "\n  <refbody>\n    <section><title>Overview</title><p>Reference details go here.</p></section>\n  </refbody>\n</reference>",
            1,
        )
        actions.append("structural_repair")
    elif resolved_type == "glossentry":
        if "<glossterm" not in repaired.lower():
            repaired = repaired.replace(
                "</glossentry>",
                f"\n  <glossterm>{str(issue.get('summary') or issue_key or 'Term').strip()}</glossterm>\n</glossentry>",
                1,
            )
            actions.append("structural_repair")
        if "<glossdef" not in repaired.lower():
            repaired = repaired.replace(
                "</glossentry>",
                "\n  <glossdef><p>Definition goes here.</p></glossdef>\n</glossentry>",
                1,
            )
            actions.append("structural_repair")

    return repaired, resolved_type, list(dict.fromkeys(actions))


async def analyse_content(
    xml: str,
    issue: dict,
    tenant_id: str = "kone",
    audience_id: str = "",
    research_context: dict | None = None,
    validation: list[dict] | None = None,
    quality_breakdown: dict | None = None,
) -> SuggestionReport:
    del audience_id
    sections = _parse_sections(xml)
    dita_type = _get_dita_type(xml)
    steps = _extract_steps(xml)

    terminology: dict[str, str] = {}
    try:
        from app.services.tenant_service import get_tenant

        terminology = get_tenant(tenant_id).terminology or {}
    except Exception:
        try:
            from app.services.kone_knowledge_base import KONE_TERMINOLOGY

            terminology = KONE_TERMINOLOGY
        except Exception:
            terminology = {}

    suggestions: list[Suggestion] = []
    suggestions.extend(_check_validation_findings(validation or [], dita_type))
    suggestions.extend(_check_missing_elements(sections, dita_type))
    suggestions.extend(_check_title_alignment(sections, issue, dita_type))
    suggestions.extend(_check_shortdesc(sections))
    suggestions.extend(_check_vague_steps(steps))
    suggestions.extend(_check_task_depth(steps, dita_type))
    suggestions.extend(_check_issue_coverage(sections, issue))
    suggestions.extend(_check_bug_report_language(sections))
    suggestions.extend(_check_research_alignment(sections, research_context))
    suggestions.extend(_check_terminology(sections, terminology))
    suggestions.extend(_check_version_context(sections))
    suggestions.extend(_check_suggested_elements(sections, dita_type))
    suggestions.extend(_check_reuse_opportunities(xml, sections, issue, dita_type, quality_breakdown))
    suggestions.extend(_check_quality_gap_suggestions(xml, sections, dita_type, issue, research_context, quality_breakdown))

    suggestions = _dedupe_suggestions(suggestions)
    suggestions.sort(
        key=lambda item: (
            _SEVERITY_ORDER.get(item.severity, 9),
            -len(item.evidence),
            -item.confidence,
            item.section,
        )
    )
    score_delta = sum({"error": 8, "warning": 5, "info": 2}.get(item.severity, 0) for item in suggestions)
    errors = sum(1 for item in suggestions if item.severity == "error")
    warnings = sum(1 for item in suggestions if item.severity == "warning")
    report = SuggestionReport(
        total=len(suggestions),
        errors=errors,
        warnings=warnings,
        suggestions=suggestions,
        score_delta=score_delta,
        refine_completions=_build_refine_completions(suggestions, terminology),
    )
    logger.info_structured(
        "Analysed DITA content",
        extra_fields={"issue_key": issue.get("issue_key"), "suggestions": len(suggestions), "errors": errors, "warnings": warnings},
    )
    return report


async def build_review_snapshot(
    *,
    xml: str,
    issue: dict,
    tenant_id: str = "kone",
    audience_id: str = "",
    research_context: dict | None = None,
) -> dict[str, Any]:
    del audience_id
    from app.services.dita_xml_headers import normalize_dita_document

    cleaned = _clean_xml(xml)
    normalized, dita_type = normalize_dita_document(cleaned or xml)
    issue_key = str((issue or {}).get("issue_key") or "").strip() or _extract_issue_key_hint(normalized) or "topic"
    repaired, dita_type, repair_actions = _apply_structural_repairs(normalized, dita_type, issue or {}, issue_key)
    evaluation = await _evaluate_content_for_response(repaired, dita_type, file_hint=issue_key)
    report = await analyse_content(
        xml=repaired,
        issue=issue or {},
        tenant_id=tenant_id,
        research_context=research_context,
        validation=evaluation.get("validation") or [],
        quality_breakdown=evaluation.get("quality_breakdown") or {},
    )
    return {
        "content": repaired,
        "dita_type": dita_type,
        "quality_score": evaluation["quality_score"],
        "quality_breakdown": evaluation["quality_breakdown"],
        "validation": evaluation["validation"],
        "aem_guides_validation_errors": evaluation.get("aem_guides_validation_errors", []),
        "aem_guides_validation_status": evaluation.get("aem_guides_validation_status", {}),
        "sources_used": [
            {"label": "Live XML review", "count": 1, "color": "slate"},
            *(
                [{"label": "Structural repair", "count": len(repair_actions), "color": "rose"}]
                if repair_actions
                else []
            ),
        ],
        "suggestion_totals": {
            "total": report.total,
            "errors": report.errors,
            "warnings": report.warnings,
            "score_delta": report.score_delta,
        },
        "suggestions_report": report.to_dict(),
    }


def _replace_section(xml: str, tag: str, content: str) -> str:
    pattern = re.compile(rf"(<{tag}[^>]*>)(.*?)(</{tag}>)", re.IGNORECASE | re.DOTALL)
    if not pattern.search(xml):
        return xml
    return pattern.sub(lambda match: f"{match.group(1)}{content}{match.group(3)}", xml, count=1)


def _inject_into_parent(xml: str, parent_tag: str, snippet: str, before_tag: str | None = None) -> str:
    pattern = re.compile(rf"(<{parent_tag}[^>]*>)(.*?)(</{parent_tag}>)", re.IGNORECASE | re.DOTALL)
    match = pattern.search(xml)
    if not match:
        return xml
    start_tag, body, end_tag = match.groups()
    new_body = body
    if before_tag and before_tag.lower() != parent_tag.lower():
        sibling_pattern = re.compile(rf"(<{before_tag}\b[^>]*>)", re.IGNORECASE)
        if sibling_pattern.search(body):
            new_body = sibling_pattern.sub(f"{snippet}\n\\1", body, count=1)
        else:
            new_body = f"{body}\n{snippet}"
    else:
        new_body = f"{body}\n{snippet}"
    return f"{xml[:match.start()]}{start_tag}{new_body}{end_tag}{xml[match.end():]}"


def _append_paragraph_to_section(xml: str, tag: str, paragraph: str) -> str:
    pattern = re.compile(rf"(<{tag}[^>]*>)(.*?)(</{tag}>)", re.IGNORECASE | re.DOTALL)
    match = pattern.search(xml)
    if not match:
        return xml
    inner = match.group(2)
    if paragraph.lower() in inner.lower():
        return xml
    addition = f"\n      <p>{paragraph}</p>"
    return f"{xml[:match.start()]}{match.group(1)}{inner}{addition}\n    {match.group(3)}{xml[match.end():]}"


def _append_fragment_to_section(xml: str, tag: str, fragment: str) -> str:
    pattern = re.compile(rf"(<{tag}[^>]*>)(.*?)(</{tag}>)", re.IGNORECASE | re.DOTALL)
    match = pattern.search(xml)
    if not match:
        return xml
    inner = match.group(2)
    if fragment.strip() and fragment.strip() in inner:
        return xml
    return f"{xml[:match.start()]}{match.group(1)}{inner}{fragment}\n    {match.group(3)}{xml[match.end():]}"


def _rewrite_cmd_text(step_text: str, issue: dict | None = None) -> str:
    focus_terms = _extract_issue_terms(issue or {}, limit=3)
    focus = ", ".join(focus_terms) if focus_terms else "the required change"
    replacements = [
        (r"^check (the|your)?\s*(settings?|config|configuration)\.?$", f"Check the AEM Guides settings related to {focus}."),
        (r"^verify (it|that it|the)\s*(works?|is correct)\.?$", f"Verify that {focus} behaves as expected in AEM Guides."),
        (r"^open the (file|document|application)\.?$", f"Open the relevant file or application for {focus}."),
        (r"^(save|submit|apply)\.?$", "Save the change and confirm the expected behavior."),
        (r"^click (ok|yes|confirm|apply)\.?$", "Confirm the dialog and continue with the procedure."),
    ]
    candidate = _strip_tags(step_text)
    for pattern, replacement in replacements:
        if re.match(pattern, candidate, re.IGNORECASE):
            return replacement
    return step_text


def _deduplicate_steps(xml: str) -> str:
    steps_pattern = re.compile(r"(<steps[^>]*>)(.*?)(</steps>)", re.IGNORECASE | re.DOTALL)
    match = steps_pattern.search(xml)
    if not match:
        return xml
    steps_body = match.group(2)
    step_matches = list(re.finditer(r"<step\b[^>]*>.*?</step>", steps_body, re.IGNORECASE | re.DOTALL))
    if not step_matches:
        return xml

    unique_steps: list[str] = []
    seen: set[str] = set()
    for step_match in step_matches:
        step_block = step_match.group(0)
        normalized = _strip_tags(step_block).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_steps.append(step_block.strip())

    if len(unique_steps) == len(step_matches):
        return xml

    replacement = f"{match.group(1)}\n      " + "\n      ".join(unique_steps) + f"\n    {match.group(3)}"
    return f"{xml[:match.start()]}{replacement}{xml[match.end():]}"


def _apply_rule_based_fix(
    xml: str,
    suggestion: dict,
    tenant_id: str,
    issue: dict | None = None,
    research_context: dict | None = None,
) -> str:
    rule_id = suggestion.get("rule_id", "")
    after = suggestion.get("after", "")
    dita_type = _get_dita_type(xml)
    parent_tag = _body_parent_tag(dita_type)

    if rule_id in {"title_work_item_jargon", "title_matches_jira_summary"}:
        return _replace_section(xml, "title", after)

    if rule_id == "reuse_title_conref":
        title_pattern = re.compile(r"<title([^>]*)>(.*?)</title>", re.IGNORECASE | re.DOTALL)

        def add_title_conref(match: re.Match[str]) -> str:
            attrs = match.group(1) or ""
            if "conref=" in attrs.lower() or "conkeyref=" in attrs.lower():
                return match.group(0)
            title_text = _strip_tags(match.group(2)) or "Reusable title"
            slug = _slugify_fragment(title_text)
            return f'<title{attrs} conref="reuse/reusable-titles.dita#reusable_titles/{slug}">{match.group(2)}</title>'

        return title_pattern.sub(add_title_conref, xml, count=1)

    if rule_id in {"shortdesc_this_topic", "shortdesc_length", "shortdesc_passive"}:
        return _replace_section(xml, "shortdesc", after)

    if rule_id == "terminology":
        try:
            from app.services.tenant_service import get_tenant

            terminology = get_tenant(tenant_id).terminology or {}
        except Exception:
            terminology = {}
        updated = xml
        for generic, specific in terminology.items():
            updated = re.sub(rf"\b{re.escape(generic)}\b", specific, updated, flags=re.IGNORECASE)
        return updated

    if rule_id == "missing_shortdesc":
        title_match = re.search(r"(<title[^>]*>.*?</title>)", xml, re.IGNORECASE | re.DOTALL)
        if title_match:
            return xml.replace(title_match.group(1), f"{title_match.group(1)}\n  <shortdesc>{after}</shortdesc>", 1)
        return xml

    if rule_id == "validation_xml_lang":
        root_pattern = re.compile(r"<(task|concept|reference|topic|glossentry)\b([^>]*)>", re.IGNORECASE)

        def add_lang(match: re.Match[str]) -> str:
            root = match.group(1)
            attrs = match.group(2) or ""
            if "xml:lang=" in attrs:
                return match.group(0)
            return f"<{root}{attrs} xml:lang=\"en-US\">"

        return root_pattern.sub(add_lang, xml, count=1)

    if rule_id == "validation_xml_declaration":
        stripped = xml.lstrip()
        if stripped.startswith("<?xml"):
            return xml
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{stripped}'

    if rule_id == "validation_dtd_header":
        try:
            from app.services.dita_xml_headers import normalize_dita_document

            normalized, _ = normalize_dita_document(xml, dita_type=dita_type)
            return normalized
        except Exception:
            return xml

    if rule_id == "quality_add_prolog":
        title_match = re.search(r"(<shortdesc[^>]*>.*?</shortdesc>)", xml, re.IGNORECASE | re.DOTALL)
        if not title_match:
            title_match = re.search(r"(<title[^>]*>.*?</title>)", xml, re.IGNORECASE | re.DOTALL)
        if not title_match:
            return xml
        prolog = (
            "\n  <prolog>\n"
            "    <metadata>\n"
            "      <othermeta name=\"author\" content=\"AEM Guides Dataset Studio\"/>\n"
            "      <othermeta name=\"source\" content=\"Jira authoring flow\"/>\n"
            "    </metadata>\n"
            "  </prolog>"
        )
        return xml.replace(title_match.group(1), f"{title_match.group(1)}{prolog}", 1)

    if rule_id == "bug_report_language":
        replacements = [
            (r"\bsteps to reproduce\b", "Procedure"),
            (r"\bactual result\b", "Observed behavior"),
            (r"\bexpected result\b", "Expected behavior"),
            (r"\bworkaround\b", "Guidance"),
            (r"\brepro\b", "procedure"),
            (r"\bdefect\b", "issue"),
        ]
        updated = xml
        for pattern, replacement in replacements:
            updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)
        return updated

    if rule_id == "reuse_add_keywords":
        if "<keywords" in xml.lower():
            return xml
        terms = _keyword_terms(issue or {}, _parse_sections(xml))
        if not terms:
            terms = ["AEM Guides"]
        keywords_block = "\n".join(f"        <keyword>{term}</keyword>" for term in terms[:5])
        snippet = f"\n      <keywords>\n{keywords_block}\n      </keywords>"

        if re.search(r"<metadata[^>]*>", xml, re.IGNORECASE):
            return re.sub(r"(</metadata>)", f"{snippet}\n\\1", xml, count=1, flags=re.IGNORECASE)

        if re.search(r"<prolog[^>]*>", xml, re.IGNORECASE):
            metadata = f"\n    <metadata>{snippet}\n    </metadata>"
            return re.sub(r"(<prolog[^>]*>)", rf"\1{metadata}", xml, count=1, flags=re.IGNORECASE)

        anchor = re.search(r"(<shortdesc[^>]*>.*?</shortdesc>)", xml, re.IGNORECASE | re.DOTALL)
        if not anchor:
            anchor = re.search(r"(<title[^>]*>.*?</title>)", xml, re.IGNORECASE | re.DOTALL)
        if not anchor:
            return xml
        prolog = f"\n  <prolog>\n    <metadata>{snippet}\n    </metadata>\n  </prolog>"
        return xml.replace(anchor.group(1), f"{anchor.group(1)}{prolog}", 1)

    if rule_id == "reuse_add_keyref":
        reusable_phrase = _first_reusable_phrase(xml)
        if not reusable_phrase:
            return xml
        phrase, key = reusable_phrase
        replacement = f'<ph keyref="{key}">{phrase}</ph>'
        return re.sub(re.escape(phrase), replacement, xml, count=1)

    if rule_id == "reuse_add_conkeyref":
        note_slug = _slugify_fragment((issue or {}).get("summary") or "verification")
        conkeyref_value = f"reuse/reusable-blocks/{note_slug}-verification"
        if re.search(r"<note\b[^>]*con(?:key)?ref=", xml, re.IGNORECASE):
            return xml
        if dita_type == "task":
            note_fragment = (
                f'\n      <note conkeyref="{conkeyref_value}">'
                "\n        <p>Reuse the shared verification guidance for this topic.</p>"
                "\n      </note>"
            )
            if re.search(r"<context\b", xml, re.IGNORECASE):
                return _append_fragment_to_section(xml, "context", note_fragment)
            context_block = (
                "\n    <context>"
                f'{note_fragment}'
                "\n    </context>"
            )
            return _inject_into_parent(xml, "taskbody", context_block, before_tag="steps")

        if re.search(r"<note\b", xml, re.IGNORECASE):
            return re.sub(
                r"<note\b([^>]*)>",
                rf'<note\1 conkeyref="{conkeyref_value}">',
                xml,
                count=1,
                flags=re.IGNORECASE,
            )
        snippet = (
            f'\n    <note conkeyref="{conkeyref_value}">'
            "\n      <p>Reuse the shared verification guidance for this topic.</p>"
            "\n    </note>"
        )
        return _inject_into_parent(xml, parent_tag, snippet, before_tag="result")

    if rule_id == "issue_coverage_gap":
        missing = [term for term in _extract_issue_terms(issue or {}) if term.lower() not in _context_text(_parse_sections(xml)).lower()]
        if not missing:
            return xml
        sentence = f"This topic covers {', '.join(missing[:3])}."
        if dita_type == "task":
            if "<context" in xml.lower():
                return _append_paragraph_to_section(xml, "context", sentence)
            return _inject_into_parent(xml, "taskbody", f"\n    <context>\n      <p>{sentence}</p>\n    </context>", before_tag="steps")
        return _inject_into_parent(xml, parent_tag, f"\n    <p>{sentence}</p>")

    if rule_id == "missing_result":
        return _inject_into_parent(xml, "taskbody", f"\n    <result>\n      <p>{after}</p>\n    </result>", before_tag="taskbody")

    if rule_id in {"missing_prereq", "suggest_prereq"}:
        return _inject_into_parent(xml, "taskbody", f"\n    <prereq>\n      <p>{after}</p>\n    </prereq>", before_tag="steps")

    if rule_id == "missing_context":
        return _inject_into_parent(xml, "taskbody", f"\n    <context>\n      <p>{after}</p>\n    </context>", before_tag="steps")

    if rule_id == "validation_taskbody":
        if "<taskbody" in xml:
            return xml
        return _inject_into_parent(
            xml,
            "task",
            "\n  <taskbody>\n    <context>\n      <p>Add task context here.</p>\n    </context>\n    <steps>\n      <step>\n        <cmd>Complete the required action.</cmd>\n      </step>\n    </steps>\n    <result>\n      <p>The task completes successfully.</p>\n    </result>\n  </taskbody>",
        )

    if rule_id in {"validation_steps", "task_steps_too_few"}:
        if "<steps" not in xml:
            return _inject_into_parent(
                xml,
                "taskbody",
                "\n    <steps>\n      <step>\n        <cmd>Complete the required action.</cmd>\n      </step>\n    </steps>",
                before_tag="result",
            )
        return xml.replace("</steps>", "\n      <step>\n        <cmd>Verify the expected outcome.</cmd>\n      </step>\n    </steps>", 1)

    if rule_id == "vague_steps":
        cmd_pattern = re.compile(r"(<cmd[^>]*>)(.*?)(</cmd>)", re.IGNORECASE | re.DOTALL)

        def rewrite_cmd(match: re.Match[str]) -> str:
            return f"{match.group(1)}{_rewrite_cmd_text(match.group(2), issue)}{match.group(3)}"

        return cmd_pattern.sub(rewrite_cmd, xml)

    if rule_id == "task_duplicate_steps":
        return _deduplicate_steps(xml)

    if rule_id == "validation_cmd":
        return re.sub(
            r"(<step>\s*)(?!<cmd)",
            r"\1<cmd>Complete the required action.</cmd>\n        ",
            xml,
            count=1,
            flags=re.IGNORECASE,
        )

    if rule_id == "missing_conbody":
        return _inject_into_parent(xml, "concept", f"\n  <conbody>{after}</conbody>")

    if rule_id == "missing_refbody":
        return _inject_into_parent(xml, "reference", f"\n  <refbody>{after}</refbody>")

    if rule_id == "missing_glossterm":
        return _inject_into_parent(xml, "glossentry", f"\n  <glossterm>{after}</glossterm>")

    if rule_id == "missing_glossdef":
        return _inject_into_parent(xml, "glossentry", f"\n  <glossdef>{after}</glossdef>")

    if rule_id == "quality_add_note":
        if "<note" in xml.lower():
            return xml
        if dita_type == "task":
            note_fragment = "\n      <note>\n        <p>Verify the behavior in the target AEM Guides environment after applying the change.</p>\n      </note>"
            if "<context" in xml.lower():
                return _append_fragment_to_section(xml, "context", note_fragment)
            return _inject_into_parent(xml, "taskbody", f"\n    <context>{note_fragment}\n    </context>", before_tag="steps")
        snippet = "\n    <note>\n      <p>Verify the behavior in the target AEM Guides environment after applying the change.</p>\n    </note>"
        return _inject_into_parent(xml, parent_tag, snippet, before_tag="result")

    if rule_id == "quality_add_example":
        snippet = (
            "\n    <example>\n"
            "      <title>Example</title>\n"
            "      <p>Use a realistic AEM Guides scenario to show the expected behavior before and after the change.</p>\n"
            "    </example>"
        )
        if "<example" in xml:
            return xml
        return _inject_into_parent(xml, parent_tag, snippet, before_tag="result")

    if rule_id == "quality_add_xref":
        href_match = re.search(r'href="([^"]+)"', after)
        href = href_match.group(1) if href_match else ""
        if not href or "<xref" in xml:
            return xml
        if dita_type == "task":
            postreq_fragment = (
                "\n      <p>\n"
                f"        <xref href=\"{href}\" scope=\"external\" format=\"html\">Related guidance</xref>\n"
                "      </p>"
            )
            if "<postreq" in xml.lower():
                return _append_fragment_to_section(xml, "postreq", postreq_fragment)
            snippet = f"\n    <postreq>{postreq_fragment}\n    </postreq>"
            return _inject_into_parent(xml, "taskbody", snippet)
        snippet = (
            "\n    <p>\n"
            f"      <xref href=\"{href}\" scope=\"external\" format=\"html\">Related guidance</xref>\n"
            "    </p>"
        )
        return _inject_into_parent(xml, parent_tag, snippet)

    if rule_id == "quality_add_codeblock":
        if "<codeblock" in xml.lower():
            return xml
        issue_summary = (issue or {}).get("summary") or "the relevant change"
        snippet = (
            "\n    <example>\n"
            "      <title>Configuration example</title>\n"
            f"      <codeblock outputclass=\"language-text\">Review the relevant selector, script, or config related to {issue_summary}.</codeblock>\n"
            "    </example>"
        )
        return _inject_into_parent(xml, parent_tag, snippet, before_tag="result")

    if rule_id == "quality_add_media_object" and _issue_has_video_attachment(issue or {}):
        if "<object" in xml.lower():
            return xml
        attachment = next(
            (
                item
                for item in (issue or {}).get("attachments", [])
                if item.get("is_video") or str(item.get("mime_type", "")).startswith("video/")
            ),
            None,
        )
        if not attachment:
            return xml
        relative_path = attachment.get("relative_path") or f"jira_attachments/{(issue or {}).get('issue_key', 'ISSUE')}/{attachment.get('filename', 'video')}"
        media_type = attachment.get("mime_type") or "video/mp4"
        filename = attachment.get("filename") or "attached-video"
        snippet = (
            "\n    <example>\n"
            "      <title>Related media</title>\n"
            f"      <p>{filename}</p>\n"
            f"      <object data=\"{relative_path}\" type=\"{media_type}\" outputclass=\"jira-attachment-video\"/>\n"
            "    </example>"
        )
        return _inject_into_parent(xml, parent_tag, snippet)

    if rule_id == "quality_add_dita_feature":
        url = _first_external_url(research_context)
        if url and "<xref" not in xml.lower():
            return _apply_rule_based_fix(
                xml,
                {
                    "rule_id": "quality_add_xref",
                    "after": f'Add an xref to the supporting guidance: <xref href="{url}" scope="external" format="html">Related guidance</xref>.',
                },
                tenant_id,
                issue,
                research_context,
            )
        if _issue_has_video_attachment(issue or {}) and "<object" not in xml.lower():
            return _apply_rule_based_fix(xml, {"rule_id": "quality_add_media_object"}, tenant_id, issue, research_context)
        if "<note" not in xml.lower():
            return _apply_rule_based_fix(xml, {"rule_id": "quality_add_note"}, tenant_id, issue, research_context)
        return xml

    if rule_id == "research_version_note":
        highlights = _extract_research_highlights(research_context)
        version = next((candidate for candidate in highlights["versions"] if candidate not in xml), "")
        if not version:
            return xml
        sentence = f"Applies to version {version} when the behavior matches your environment."
        if dita_type == "task":
            note_fragment = f"\n      <note>\n        <p>{sentence}</p>\n      </note>"
            if "<context" in xml.lower():
                return _append_fragment_to_section(xml, "context", note_fragment)
            return _inject_into_parent(xml, "taskbody", f"\n    <context>{note_fragment}\n    </context>", before_tag="steps")
        if "<note" in xml.lower():
            return _append_paragraph_to_section(xml, "note", sentence)
        return _inject_into_parent(xml, parent_tag, f"\n    <note>\n      <p>{sentence}</p>\n    </note>", before_tag="result")

    if rule_id == "research_tool_alignment":
        highlights = _extract_research_highlights(research_context)
        missing = [tool for tool in highlights["tools"] if tool not in xml.lower()]
        if not missing:
            return xml
        sentence = f"Review whether {missing[0]} should be named explicitly in this topic."
        if dita_type == "task" and "<context" in xml.lower():
            return _append_paragraph_to_section(xml, "context", sentence)
        if dita_type == "task":
            return _inject_into_parent(xml, "taskbody", f"\n    <context>\n      <p>{sentence}</p>\n    </context>", before_tag="steps")
        return _inject_into_parent(xml, parent_tag, f"\n    <p>{sentence}</p>", before_tag="result")

    return xml


async def apply_fix(
    xml: str,
    suggestion: dict,
    issue: dict,
    tenant_id: str = "kone",
    research_context: dict | None = None,
    allow_llm: bool = True,
) -> str:
    def _clean_candidate(candidate: str) -> str:
        cleaned = (candidate or "").strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(line for line in cleaned.splitlines() if not line.strip().startswith("```")).strip()
        return cleaned

    async def _deterministic_refine(candidate_xml: str, apply_instruction: bool = True) -> str:
        try:
            from app.services.dita_xml_headers import normalize_dita_document
            from app.services.intent_translator import translate_intent

            research_text = _serialize_research_context(research_context)
            refined = candidate_xml
            dita_type = _get_dita_type(candidate_xml)

            if apply_instruction:
                intent = await translate_intent(issue=issue or {}, research_context=research_text)
                refined, dita_type, _actions = _apply_instruction_refinement(
                    candidate_xml,
                    suggestion.get("fix_prompt", suggestion.get("after", suggestion.get("title", "Refine the DITA content."))),
                    issue or {},
                    intent.to_dict(),
                    research_text,
                )
            refined, dita_type = normalize_dita_document(refined, dita_type=dita_type)
            refined, _media_actions = _inject_issue_media(refined, dita_type, issue or {})
            refined, dita_type, _repair_actions = _apply_structural_repairs(
                refined,
                dita_type,
                issue or {},
                (issue or {}).get("issue_key") or "topic",
            )
            return refined
        except Exception as exc:
            logger.debug_structured(
                "Deterministic smart suggestion refinement failed",
                extra_fields={"error": str(exc), "rule_id": suggestion.get("rule_id", "")},
            )
            return candidate_xml

    updated = _apply_rule_based_fix(xml, suggestion, tenant_id, issue, research_context)
    updated = _clean_candidate(updated)
    if updated != xml:
        finalized = await _deterministic_refine(updated, apply_instruction=False)
        return finalized if finalized.strip() else updated

    deterministic = await _deterministic_refine(xml)
    deterministic = _clean_candidate(deterministic)
    if deterministic != xml:
        return deterministic

    try:
        from app.services.dita_generation_prompt import build_refinement_prompt
        from app.services.intent_translator import translate_intent
        from app.services.llm_service import generate_text, is_llm_available

        if not allow_llm or not is_llm_available():
            return xml

        research_text = _serialize_research_context(research_context)
        intent = await translate_intent(issue=issue or {}, research_context=research_text)
        prompt = build_refinement_prompt(
            current_dita=xml,
            instruction=suggestion.get("fix_prompt", suggestion.get("title", "Refine the DITA content.")),
            issue=issue or {},
            intent=intent.to_dict(),
            tenant_id=tenant_id,
            research=research_text,
        )
        response = await generate_text(
            system_prompt="You are a DITA technical writer. Apply the requested fix and return XML only.",
            user_prompt=prompt,
            max_tokens=1800,
            step_name="smart_suggestion_fix",
            jira_id=(issue or {}).get("issue_key"),
        )
        cleaned = _clean_candidate(response)
        finalized = await _deterministic_refine(cleaned or xml)
        return finalized or cleaned or xml
    except Exception as exc:
        logger.warning_structured(
            "Failed to apply smart suggestion",
            extra_fields={"error": str(exc), "rule_id": suggestion.get("rule_id", "")},
        )
        return xml


async def apply_fix_with_review(
    *,
    xml: str,
    suggestion: dict,
    issue: dict,
    tenant_id: str = "kone",
    research_context: dict | None = None,
    audience_id: str = "",
    allow_llm: bool = True,
) -> dict[str, Any]:
    updated = await apply_fix(
        xml=xml,
        suggestion=suggestion,
        issue=issue,
        tenant_id=tenant_id,
        research_context=research_context,
        allow_llm=allow_llm,
    )
    changed = updated.strip() != (xml or "").strip()
    review = await build_review_snapshot(
        xml=updated if changed else xml,
        issue=issue or {},
        tenant_id=tenant_id,
        audience_id=audience_id,
        research_context=research_context,
    )
    return {
        "xml": review["content"],
        "changed": changed and review["content"].strip() != (xml or "").strip(),
        "applied_rule_id": suggestion.get("rule_id", ""),
        "change_summary": _summarize_change(suggestion, changed),
        "changed_ranges": _compute_changed_ranges(xml, review["content"]) if changed else [],
        "updated_review": review,
        "suggestions_report": review["suggestions_report"],
        "safe_rule": is_safe_rule(suggestion.get("rule_id", "")),
    }


async def fix_all_safe(
    *,
    xml: str,
    issue: dict,
    tenant_id: str = "kone",
    research_context: dict | None = None,
    audience_id: str = "",
) -> dict[str, Any]:
    current_xml = xml
    applied_rule_ids: list[str] = []
    skipped_rule_ids: list[str] = []
    change_summaries: list[str] = []
    last_changed_ranges: list[dict[str, int]] = []
    seen_states: set[tuple[str, str]] = set()
    fixed_count = 0

    for _ in range(12):
        review = await build_review_snapshot(
            xml=current_xml,
            issue=issue or {},
            tenant_id=tenant_id,
            audience_id=audience_id,
            research_context=research_context,
        )
        report_data = review["suggestions_report"]
        suggestions = report_data.get("suggestions", [])
        safe_suggestion = next(
            (
                suggestion
                for suggestion in suggestions
                if is_safe_rule(suggestion.get("rule_id", ""))
                and suggestion.get("rule_id", "") not in applied_rule_ids
                and suggestion.get("rule_id", "") not in skipped_rule_ids
                and (review["content"], suggestion.get("rule_id", "")) not in seen_states
            ),
            None,
        )
        if not safe_suggestion:
            return {
                "xml": review["content"],
                "fixed_count": fixed_count,
                "applied_rule_ids": applied_rule_ids,
                "skipped_rule_ids": skipped_rule_ids,
                "change_summaries": change_summaries,
                "changed_ranges": last_changed_ranges,
                "updated_review": review,
                "suggestions_report": review["suggestions_report"],
            }

        seen_states.add((review["content"], safe_suggestion.get("rule_id", "")))
        result = await apply_fix_with_review(
            xml=review["content"],
            suggestion=safe_suggestion,
            issue=issue or {},
            tenant_id=tenant_id,
            research_context=research_context,
            audience_id=audience_id,
            allow_llm=False,
        )
        if result["changed"]:
            fixed_count += 1
            applied_rule_ids.append(str(result["applied_rule_id"]))
            change_summaries.append(str(result["change_summary"]))
            current_xml = str(result["xml"])
            last_changed_ranges = result["changed_ranges"]
            continue

        skipped_rule_ids.append(str(safe_suggestion.get("rule_id", "")))

    final_review = await build_review_snapshot(
        xml=current_xml,
        issue=issue or {},
        tenant_id=tenant_id,
        audience_id=audience_id,
        research_context=research_context,
    )
    return {
        "xml": final_review["content"],
        "fixed_count": fixed_count,
        "applied_rule_ids": applied_rule_ids,
        "skipped_rule_ids": skipped_rule_ids,
        "change_summaries": change_summaries,
        "changed_ranges": last_changed_ranges,
        "updated_review": final_review,
        "suggestions_report": final_review["suggestions_report"],
    }
