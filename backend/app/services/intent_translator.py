from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


INTENT_TYPES = {
    "troubleshooting_task": {
        "label": "Troubleshooting task",
        "description": "User-facing fix procedure for a bug or failure.",
        "dita_type": "task",
        "audience": "user",
        "sections": ["shortdesc", "context", "steps", "result", "postreq"],
    },
    "configuration_task": {
        "label": "Configuration task",
        "description": "Step-by-step setup or configuration instructions.",
        "dita_type": "task",
        "audience": "administrator",
        "sections": ["shortdesc", "prereq", "steps", "result", "postreq"],
    },
    "feature_concept": {
        "label": "Feature concept",
        "description": "Overview of a feature, why it matters, and how it works.",
        "dita_type": "concept",
        "audience": "user",
        "sections": ["shortdesc", "conbody", "section", "example"],
    },
    "api_reference": {
        "label": "API reference",
        "description": "API or parameter reference information.",
        "dita_type": "reference",
        "audience": "developer",
        "sections": ["shortdesc", "refbody", "section", "example"],
    },
    "release_note": {
        "label": "Release note",
        "description": "Version-specific change note.",
        "dita_type": "concept",
        "audience": "user",
        "sections": ["shortdesc", "section", "section"],
    },
    "glossentry": {
        "label": "Glossary entry",
        "description": "Definition of a term used in documentation.",
        "dita_type": "glossentry",
        "audience": "all",
        "sections": ["glossterm", "glossdef"],
    },
}


@dataclass
class IntentSuggestion:
    intent_type: str
    label: str
    description: str
    dita_type: str
    confidence: float
    reasoning: str
    is_primary: bool

    def to_dict(self) -> dict:
        return {
            "intent_type": self.intent_type,
            "label": self.label,
            "description": self.description,
            "dita_type": self.dita_type,
            "confidence": round(self.confidence, 2),
            "reasoning": self.reasoning,
            "is_primary": self.is_primary,
        }


@dataclass
class AuthoringIntent:
    intent_type: str
    dita_type: str
    audience: str
    dita_title: str
    jira_title: str
    context_content: str
    solution_hints: list[str]
    result_content: str
    version_note: str
    generation_brief: str
    sections: list[str]
    confidence: float
    reasoning: str

    def to_dict(self) -> dict:
        return {
            "intent_type": self.intent_type,
            "dita_type": self.dita_type,
            "audience": self.audience,
            "dita_title": self.dita_title,
            "jira_title": self.jira_title,
            "context_content": self.context_content,
            "solution_hints": self.solution_hints,
            "result_content": self.result_content,
            "version_note": self.version_note,
            "generation_brief": self.generation_brief,
            "sections": self.sections,
            "confidence": round(self.confidence, 2),
            "reasoning": self.reasoning,
        }


def infer_intent(issue: dict) -> list[IntentSuggestion]:
    issue_type = (issue.get("issue_type") or "").lower()
    summary = (issue.get("summary") or "").lower()
    description = (issue.get("description") or "").lower()
    labels = [label.lower() for label in (issue.get("labels") or [])]
    corpus = f"{summary} {description} {' '.join(labels)}"

    scores: dict[str, float] = {}
    reasons: dict[str, str] = {}

    if issue_type in {"bug", "defect", "incident"}:
        scores["troubleshooting_task"] = 0.82
        reasons["troubleshooting_task"] = "Bug-like issue type points to a user-facing fix procedure."
        scores["release_note"] = 0.35
        reasons["release_note"] = "Resolved defects can also warrant a release note."
    if issue_type in {"story", "feature", "epic"}:
        scores["feature_concept"] = 0.72
        reasons["feature_concept"] = "Feature work usually maps to overview or concept content."
        scores["configuration_task"] = 0.45
        reasons["configuration_task"] = "Feature work often also needs setup instructions."
    if issue_type in {"task", "sub-task", "improvement"}:
        scores["configuration_task"] = max(scores.get("configuration_task", 0), 0.68)
        reasons["configuration_task"] = "Task and improvement issues usually become procedural content."

    label_map = {
        "concept": ("feature_concept", 0.92, "Explicit concept label."),
        "overview": ("feature_concept", 0.88, "Overview label."),
        "reference": ("api_reference", 0.9, "Reference label."),
        "api": ("api_reference", 0.87, "API label."),
        "troubleshoot": ("troubleshooting_task", 0.94, "Troubleshooting label."),
        "howto": ("configuration_task", 0.9, "How-to label."),
        "release-note": ("release_note", 0.94, "Release-note label."),
        "glossary": ("glossentry", 0.95, "Glossary label."),
    }
    for label in labels:
        if label in label_map:
            intent_type, score, reason = label_map[label]
            scores[intent_type] = score
            reasons[intent_type] = reason

    if sum(keyword in corpus for keyword in ("error", "fails", "broken", "cannot", "not working")) >= 2:
        scores["troubleshooting_task"] = max(scores.get("troubleshooting_task", 0), 0.7)
        reasons.setdefault("troubleshooting_task", "Failure signals in the issue content.")
    if sum(keyword in corpus for keyword in ("configure", "setup", "install", "enable")) >= 2:
        scores["configuration_task"] = max(scores.get("configuration_task", 0), 0.65)
        reasons.setdefault("configuration_task", "Configuration signals in the issue content.")
    if sum(keyword in corpus for keyword in ("api", "endpoint", "parameter", "schema")) >= 2:
        scores["api_reference"] = max(scores.get("api_reference", 0), 0.7)
        reasons.setdefault("api_reference", "API/reference signals in the issue content.")

    if not scores:
        scores["configuration_task"] = 0.4
        reasons["configuration_task"] = "Fallback to procedure when the signal is weak."

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:3]
    suggestions: list[IntentSuggestion] = []
    for index, (intent_type, confidence) in enumerate(ranked):
        meta = INTENT_TYPES[intent_type]
        suggestions.append(
            IntentSuggestion(
                intent_type=intent_type,
                label=meta["label"],
                description=meta["description"],
                dita_type=meta["dita_type"],
                confidence=confidence,
                reasoning=reasons.get(intent_type, ""),
                is_primary=index == 0,
            )
        )
    return suggestions


def transform_summary_to_title(summary: str, intent_type: str) -> str:
    if not summary:
        return summary
    cleaned = summary.strip()
    cleaned = re.sub(r"^(bug|defect|issue|fix)\s*[:\-]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+not\s+(working|resolving|loading|showing)\b", "", cleaned, flags=re.IGNORECASE).strip()
    if intent_type in {"feature_concept", "api_reference", "release_note"}:
        cleaned = re.sub(
            r"^(add|implement|support|update|improve|fix|resolve|enable)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
    words = cleaned.split()
    technical_terms = {"aem", "dita", "api", "xml", "json", "keyref", "keyscope", "conref", "uuid"}
    normalized_words = []
    for word in words:
        lowered = word.lower()
        if lowered in technical_terms:
            normalized_words.append(word.upper())
        elif any(char.isupper() for char in word[1:]) or any(char.isdigit() for char in word):
            normalized_words.append(word)
        else:
            normalized_words.append(word.capitalize())
    title = " ".join(normalized_words)
    prefix = {
        "troubleshooting_task": "Resolve",
        "configuration_task": "Configure",
        "release_note": "What's New:",
    }.get(intent_type, "")
    if prefix and not title.lower().startswith(prefix.lower().rstrip(":")):
        return f"{prefix} {title}".strip()
    return title


def extract_context_from_description(description: str) -> str:
    if not description:
        return ""
    lines = []
    keep_patterns = ("root cause", "because", "background", "context", "introduced", "changed", "since version", "since aem")
    for raw_line in description.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower_line = line.lower()
        if any(token in lower_line for token in ("steps to reproduce", "expected result", "actual result", "environment", "stack trace")):
            continue
        if re.match(r"^\d+\.\s", line):
            continue
        if any(pattern in lower_line for pattern in keep_patterns):
            lines.append(line)
    if not lines:
        sentences = re.split(r"(?<=[.!?])\s+", description.strip())
        fallback = [sentence for sentence in sentences if 30 <= len(sentence) <= 220][:2]
        lines.extend(fallback)
    return " ".join(lines)[:500].strip()


def extract_solution_hints_from_comments(comments: list[dict]) -> list[str]:
    hints: list[str] = []
    for comment in comments or []:
        text = comment.get("body_text") or ""
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            trimmed = sentence.strip()
            if not trimmed:
                continue
            lower_sentence = trimmed.lower()
            if any(keyword in lower_sentence for keyword in ("fix", "workaround", "solution", "set", "update", "change", "prefix", "attribute")):
                hints.append(trimmed[:220])
    unique: list[str] = []
    for hint in hints:
        if hint not in unique:
            unique.append(hint)
    return unique[:6]


def extract_result_from_acceptance_criteria(description: str) -> str:
    if not description:
        return ""
    match = re.search(r"(acceptance criteria|definition of done|done when)[:\n](.*?)(?:\n\n|\Z)", description, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    text = re.sub(r"^(verify|ensure|check)\s+that\s+", "", match.group(2).strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if text and not text.endswith("."):
        text += "."
    return text[:260]


def build_generation_brief(intent: AuthoringIntent, research_context: str = "") -> str:
    lines = [
        "=== AUTHORING INTENT ===",
        f"Write a {INTENT_TYPES[intent.intent_type]['label']} for the target audience: {intent.audience}.",
        f"DITA type: {intent.dita_type}",
        f"DITA title: {intent.dita_title}",
        f"Original Jira title: {intent.jira_title}",
        "",
        "=== RULES ===",
        "Do not copy Jira bug-report language verbatim.",
        "Write from the user or operator perspective, not QA reproduction steps.",
        "Keep the shortdesc concise and action-oriented.",
        "Use the transformed context and solution hints below as the source of truth for authoring.",
        "",
        "=== CONTEXT ===",
        intent.context_content or "Focus on why the issue matters and what changed.",
    ]
    if intent.solution_hints:
        lines.extend(["", "=== SOLUTION HINTS ===", *[f"- {hint}" for hint in intent.solution_hints]])
    if intent.result_content:
        lines.extend(["", "=== RESULT ===", intent.result_content])
    if intent.version_note:
        lines.extend(["", "=== VERSION NOTE ===", intent.version_note])
    if research_context:
        lines.extend(["", "=== RESEARCH CONTEXT ===", research_context[:1800]])
    return "\n".join(lines)


async def translate_intent(
    issue: dict,
    chosen_intent: Optional[str] = None,
    custom_title: Optional[str] = None,
    research_context: str = "",
) -> AuthoringIntent:
    suggestions = infer_intent(issue)
    if chosen_intent:
        primary = next((item for item in suggestions if item.intent_type == chosen_intent), None)
        confidence = primary.confidence if primary else 0.95
        reasoning = "Author confirmed the authoring intent."
    else:
        primary = suggestions[0]
        chosen_intent = primary.intent_type
        confidence = primary.confidence
        reasoning = primary.reasoning

    meta = INTENT_TYPES[chosen_intent]
    title = custom_title or transform_summary_to_title(issue.get("summary", ""), chosen_intent)
    context = extract_context_from_description(issue.get("description", ""))
    if not context:
        try:
            from app.services.llm_service import generate_text, is_llm_available

            if is_llm_available():
                context = await generate_text(
                    system_prompt="Extract brief background context for a DITA topic. Do not include repro steps.",
                    user_prompt=f"Summary: {issue.get('summary', '')}\nDescription: {(issue.get('description') or '')[:800]}",
                    max_tokens=200,
                    step_name="intent_context",
                    jira_id=issue.get("issue_key"),
                )
        except Exception:
            context = ""

    intent = AuthoringIntent(
        intent_type=chosen_intent,
        dita_type=meta["dita_type"],
        audience=meta["audience"],
        dita_title=title,
        jira_title=issue.get("summary", ""),
        context_content=context,
        solution_hints=extract_solution_hints_from_comments(issue.get("comments", [])),
        result_content=extract_result_from_acceptance_criteria(issue.get("description", "")),
        version_note=((issue.get("fix_versions") or [""])[0]),
        generation_brief="",
        sections=meta["sections"],
        confidence=confidence,
        reasoning=reasoning,
    )
    intent.generation_brief = build_generation_brief(intent, research_context)
    logger.info_structured(
        "Translated authoring intent",
        extra_fields={"issue_key": issue.get("issue_key"), "intent_type": chosen_intent},
    )
    return intent


def get_intent_suggestions(issue: dict) -> list[dict]:
    return [suggestion.to_dict() for suggestion in infer_intent(issue)]
