"""Senior DITA chatbot quality gates for prompt shaping and retrieval context."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_OUTPUT_PATTERNS: list[tuple[str, str]] = [
    ("Native PDF", r"\bnative\s+pdf\b"),
    ("PDF / PDF2", r"\bpdf2?\b|\bxsl-fo\b|\bfop\b|\bformatter\b"),
    ("HTML5", r"\bhtml5\b|\bhtml\b|\bwebhelp\b|\bweb\s+help\b"),
]

_TOOL_PATTERNS: list[tuple[str, str]] = [
    ("AEM Guides", r"\baem\s+guides\b|\bexperience\s+manager\s+guides\b|\boutput preset\b|\bmap dashboard\b"),
    ("Oxygen", r"\boxygen\b|\bauthor\s+mode\b|\bweb\s+author\b|\btransformation scenario\b"),
    ("Command-line DITA-OT", r"\bdita-ot\b|\bdita\s+ot\b|\bdita\s+--|\bargs\.|\btranstype\b|\b--format\b"),
    ("CI", r"\bci\b|\bjenkins\b|\bdocker\b|\bpipeline\b|\bgithub actions\b|\bbuild agent\b"),
    ("Jira", r"\bjira\b|\b[A-Z][A-Z0-9]+-\d+\b"),
]

_ROOT_MAP_PATTERN = re.compile(r"\b(root map|rootmap|ditamap|\.ditamap|map context|active map)\b", re.I)
_FILTER_PATTERN = re.compile(r"\bditaval|ditavalref|filter(?:ing)?|profile|audience|platform|product\b", re.I)
_VERSION_PATTERN = re.compile(r"\b(?:dita-ot|dita\s+ot|aem guides|oxygen|dita)\s*(?:version|release)?\s*(\d+(?:\.\d+){0,3})\b", re.I)
_TROUBLESHOOTING_PATTERN = re.compile(
    r"\b(debug|troubleshoot|diagnose|fails?|failed|error|warning|missing|not resolving|broken|works.*but|html.*pdf|pdf.*html)\b",
    re.I,
)
_EXAMPLE_PATTERN = re.compile(r"\b(example|show|xml|snippet|sample|full)\b", re.I)
_COMPARISON_PATTERN = re.compile(r"\b(compare|difference|versus|vs\.?|which one|when should)\b", re.I)
_PARAMETER_PATTERN = re.compile(r"\b(args\.[a-z0-9_.-]+|--[a-z0-9_.-]+|transtype|pdf\.formatter|nav-toc|\.ditaotrc|local\.properties)\b", re.I)


@dataclass(frozen=True)
class SeniorChatContext:
    question_type: str
    domain: str
    output_type: str = "unspecified"
    tool_contexts: list[str] = field(default_factory=list)
    has_root_map_context: bool = False
    has_filter_context: bool = False
    version_mentions: list[str] = field(default_factory=list)
    parameter_mentions: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        contexts = ", ".join(self.tool_contexts) if self.tool_contexts else "not specified"
        versions = ", ".join(self.version_mentions) if self.version_mentions else "not specified"
        params = ", ".join(f"`{value}`" for value in self.parameter_mentions[:8]) if self.parameter_mentions else "none detected"
        return (
            "SENIOR CHAT CONTEXT:\n"
            f"- Detected domain: {self.domain}\n"
            f"- Question type: {self.question_type}\n"
            f"- Output type: {self.output_type}\n"
            f"- Tool/context: {contexts}\n"
            f"- Root map context supplied: {'yes' if self.has_root_map_context else 'no'}\n"
            f"- Filter/profile context supplied: {'yes' if self.has_filter_context else 'no'}\n"
            f"- Version context: {versions}\n"
            f"- DITA-OT parameter signals: {params}\n"
            "\n"
            "SENIOR ANSWER GATE:\n"
            "- If retrieved evidence is about a different construct, reject it instead of answering from it.\n"
            "- Always distinguish DITA specification behavior from DITA-OT, AEM Guides, Oxygen, CI, or Jira behavior.\n"
            "- For DITA-OT parameters, treat the answer as implementation/configuration behavior, not a DITA spec rule.\n"
            "- For troubleshooting, use: expected behavior, probable causes, deterministic checks, files/logs/temp output to inspect, and prevention.\n"
            "- For element/attribute questions, include direct answer, scope note, full XML when relevant, related concepts, and common mistakes.\n"
            "- If root map, filter profile, output type, version, or processor context is missing and affects the answer, state the dependency explicitly.\n"
        )


def detect_senior_chat_context(query: str) -> SeniorChatContext:
    text = str(query or "")
    lowered = text.lower()
    output_type = "unspecified"
    for label, pattern in _OUTPUT_PATTERNS:
        if re.search(pattern, text, re.I):
            output_type = label
            break

    tool_contexts = [label for label, pattern in _TOOL_PATTERNS if re.search(pattern, text, re.I)]
    if "dita-ot" in lowered or "dita ot" in lowered or _PARAMETER_PATTERN.search(text):
        domain = "DITA-OT publishing"
    elif "aem" in lowered or "guides" in lowered:
        domain = "AEM Guides"
    elif "jira" in lowered or re.search(r"\b[A-Z][A-Z0-9]+-\d+\b", text):
        domain = "Jira issue understanding"
    elif "oxygen" in lowered:
        domain = "Oxygen/DITA authoring"
    else:
        domain = "DITA"

    if _TROUBLESHOOTING_PATTERN.search(text):
        question_type = "troubleshooting"
    elif _COMPARISON_PATTERN.search(text):
        question_type = "comparison"
    elif _EXAMPLE_PATTERN.search(text):
        question_type = "example"
    elif _PARAMETER_PATTERN.search(text):
        question_type = "configuration"
    else:
        question_type = "conceptual"

    version_mentions = []
    for match in _VERSION_PATTERN.finditer(text):
        value = match.group(0).strip()
        if value not in version_mentions:
            version_mentions.append(value)

    parameter_mentions = []
    for match in _PARAMETER_PATTERN.finditer(text):
        value = match.group(1).strip()
        if value not in parameter_mentions:
            parameter_mentions.append(value)

    return SeniorChatContext(
        question_type=question_type,
        domain=domain,
        output_type=output_type,
        tool_contexts=tool_contexts,
        has_root_map_context=bool(_ROOT_MAP_PATTERN.search(text)),
        has_filter_context=bool(_FILTER_PATTERN.search(text)),
        version_mentions=version_mentions,
        parameter_mentions=parameter_mentions,
    )


def build_senior_chat_context_block(query: str) -> str:
    return detect_senior_chat_context(query).to_prompt_block()


def senior_answer_policy_block() -> str:
    return (
        "\n\nSENIOR DITA EXPERT ANSWER POLICY:\n"
        "- Do not answer as a search-result summarizer. Synthesize like a senior DITA architect.\n"
        "- Start with the answer, not citations or caveats.\n"
        "- Use retrieved knowledge as evidence, but apply expert reasoning to connect cause, processing phase, and fix.\n"
        "- Prefer approved learned-QA examples when they directly match the user's DITA/AEM/DITA-OT intent.\n"
        "- If evidence conflicts, name the scope: DITA spec, DITA-OT docs, AEM Guides docs, Oxygen/editor behavior, Jira/community issue.\n"
        "- For weak or mismatched retrieval, say what cannot be verified and ask for the missing context instead of guessing.\n"
        "- For DITA-OT failures, always mention command/preset, temp files, logs, DITAVAL, root map, plug-ins, Java/fonts/OS when relevant.\n"
        "- For XML examples, show valid enclosing context whenever the construct is not standalone.\n"
    )


def judge_retrieval_match(query: str, rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Lightweight retrieval health summary for UI/debug prompt context."""
    rows = rows or []
    context = detect_senior_chat_context(query)
    if not rows:
        return {
            "status": "missing",
            "confidence": "low",
            "reason": "No approved learned-QA matches were retrieved.",
            "context": context,
        }
    top = rows[0]
    try:
        score = float(top.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    source_type = str(top.get("source_type") or "")
    prompt = str(top.get("prompt") or "")
    text = f"{prompt}\n{top.get('final_answer') or ''}\n{' '.join(top.get('tags') or [])}".lower()
    query_lower = str(query or "").lower()

    status = "usable"
    reason = "Top learned-QA match is usable."
    confidence = "high" if score >= 0.86 else "medium" if score >= 0.72 else "low"

    parameter_mentions = set(context.parameter_mentions)
    if score < 0.62:
        status = "weak"
        reason = "Top learned-QA score is below the safe threshold."
    elif context.domain == "DITA-OT publishing" and source_type == "dita_attribute_questions" and parameter_mentions:
        matched_parameters = {param for param in parameter_mentions if param.lower() in text}
        if not matched_parameters:
            status = "mismatch"
            confidence = "low"
            reason = "A DITA attribute record matched a DITA-OT parameter/configuration question without the exact parameter."
    elif context.domain == "DITA-OT publishing" and source_type == "dita_attribute_questions" and ("dita-ot" not in text and "args." not in text):
        status = "mismatch"
        confidence = "low"
        reason = "A DITA attribute record matched a DITA-OT implementation/configuration question."
    elif any(term in query_lower for term in ("pdf", "html5", "output", "publish")) and "topic> is the base information unit" in text:
        status = "mismatch"
        confidence = "low"
        reason = "A generic topic-definition record matched an output troubleshooting question."

    return {
        "status": status,
        "confidence": confidence,
        "reason": reason,
        "top_source_type": source_type,
        "top_prompt": prompt,
        "top_score": round(score, 4),
        "context": context,
    }
