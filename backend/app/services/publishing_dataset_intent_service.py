"""Shared DITA-OT publishing dataset intent detection.

This module is the single routing contract for publishing-behavior datasets.
Chat, slash commands, and MCP tools should use this layer before execution so
single-topic authoring stays separate from DITA-OT PDF/HTML evidence generation.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.services.dita_publishing_construct_registry import (
    detect_output_format,
    detect_publishing_constructs,
)


_GENERATION_SIGNAL = re.compile(
    r"\b(generate|create|build|make|produce|prepare|want|need|get|give|show|run|publish|transform)\b",
    re.IGNORECASE,
)
_STRONG_GENERATION_SIGNAL = re.compile(
    r"\b(generate|create|build|make|produce|prepare|run|publish|transform)\b",
    re.IGNORECASE,
)
_DATASET_SIGNAL = re.compile(
    r"\b(dataset|data|test\s+data|sample|corpus|bundle|same|above|combination|scenario)\b",
    re.IGNORECASE,
)
_QA_ANSWER_SIGNAL = re.compile(
    r"^\s*(how|what|why|when|where|which|explain|describe|tell\s+me)\b|\b(give|with)\s+evidence\b",
    re.IGNORECASE,
)
_DITA_OT_SIGNAL = re.compile(
    r"\b(dita[-\s]?ot|dita\s+open\s+toolkit|open\s+toolkit|pdf2|html5|xhtml|classic\s+html)\b",
    re.IGNORECASE,
)
_PUBLISH_OUTPUT_SIGNAL = re.compile(
    r"\b(pdf|pdf2|html5|xhtml|classic\s+html|html|transform|transformation|publish|publishing|output)\b",
    re.IGNORECASE,
)
_EXPLICIT_FORMAT_SIGNAL = re.compile(
    r"\b(pdf|pdf2|html5|xhtml|classic\s+html|html|all)\b",
    re.IGNORECASE,
)
_PRIOR_CONTEXT_SIGNAL = re.compile(
    r"\b(above|same|this|that|previous|earlier|combination|scenario|case)\b",
    re.IGNORECASE,
)
_PUBLISHING_BEHAVIOR_SIGNAL = re.compile(
    r"\b(branch[-\s]?filter(?:ing)?|profil(?:e|ing)|ditaval|conditional\s+processing|"
    r"copy-to|copy\s+to|copyto|xml:lang|xml\s+lang|chunk|chunking|conref|conkeyref|"
    r"conrefpush|conrefend|keyref|keys|xref|topicref|mapref|reltable|scope|format|"
    r"processing-role|resource-only|search\s+title|searchtitle|titlealts?|titlealt|"
    r"metadata\s+cascad(?:e|ing)|cascad(?:e|ing)|topicmeta|lockmeta|metadata|"
    r"map\s+attributes?|all\s+(?:the\s+)?attributes?)\b",
    re.IGNORECASE,
)


def safe_title_fragment(value: str, max_chars: int = 60) -> str:
    fragment = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip()).strip("-")
    return (fragment or "dita-ot-publishing-dataset")[:max_chars]


def references_prior_context(prompt: str) -> bool:
    return bool(_PRIOR_CONTEXT_SIGNAL.search(prompt or ""))


def has_publishing_behavior_terms(prompt: str) -> bool:
    text = prompt or ""
    return bool(detect_publishing_constructs(text) or _PUBLISHING_BEHAVIOR_SIGNAL.search(text))


def _detect_format_with_current_prompt_precedence(
    prompt: str,
    expanded_prompt: str,
    *,
    default: str,
) -> str:
    if _EXPLICIT_FORMAT_SIGNAL.search(prompt or ""):
        return detect_output_format(prompt, default=default)
    return detect_output_format(expanded_prompt, default=default)


def is_publishing_dataset_request(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text or text.startswith("/"):
        return False

    strong_generation = bool(_STRONG_GENERATION_SIGNAL.search(text))
    weak_generation = bool(_GENERATION_SIGNAL.search(text))
    wants_dataset_or_context = bool(_DATASET_SIGNAL.search(text) or references_prior_context(text))
    wants_dita_ot = bool(_DITA_OT_SIGNAL.search(text))
    wants_publish_output = bool(_PUBLISH_OUTPUT_SIGNAL.search(text))
    has_construct_or_context = bool(has_publishing_behavior_terms(text) or references_prior_context(text))
    wants_generation = weak_generation

    if _QA_ANSWER_SIGNAL.search(text) and not strong_generation and not wants_dataset_or_context:
        return False

    return bool(
        wants_generation
        and wants_publish_output
        and has_construct_or_context
        and (wants_dita_ot or wants_dataset_or_context or "publishing" in text.lower())
    )


def expand_prompt_with_prior_context(
    prompt: str,
    *,
    prior_messages: list[str] | tuple[str, ...] | None = None,
    max_chars: int = 4000,
) -> str:
    base = (prompt or "").strip()
    if not base or not references_prior_context(base) or has_publishing_behavior_terms(base):
        return base

    prior_context = "\n\n".join(str(item).strip() for item in (prior_messages or []) if str(item).strip())
    if not prior_context:
        return base

    return (
        f"{base}\n\nPrevious user context to preserve for DITA generation:\n"
        f"{prior_context[-max_chars:]}"
    ).strip()


def build_publishing_tool_intent(prompt: str, *, tool_name: str = "generate_dita_ot_pdf") -> dict[str, Any] | None:
    text = (prompt or "").strip()
    if not is_publishing_dataset_request(text):
        return None

    return {
        "name": tool_name,
        "args": {
            "prompt": text,
            "output_format": detect_output_format(text, default="pdf"),
            "package_name": safe_title_fragment(text, max_chars=60),
            "detected_constructs": detect_publishing_constructs(text),
        },
        "source": "auto_publishing_dataset",
    }


def detect_publishing_dataset_intent(prompt: str) -> dict[str, Any] | None:
    return build_publishing_tool_intent(prompt, tool_name="generate_dita_ot_pdf")


def expand_publishing_tool_args_with_context(
    tool_args: dict[str, Any],
    *,
    user_content: str = "",
    prior_messages: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    prompt = str(tool_args.get("prompt") or user_content or "").strip()
    expanded_prompt = expand_prompt_with_prior_context(prompt, prior_messages=prior_messages)
    if expanded_prompt == prompt:
        return tool_args

    expanded = copy.deepcopy(tool_args)
    expanded["prompt"] = expanded_prompt
    expanded["detected_constructs"] = detect_publishing_constructs(expanded_prompt)
    expanded["output_format"] = _detect_format_with_current_prompt_precedence(
        prompt,
        expanded_prompt,
        default=str(expanded.get("output_format") or "pdf"),
    )
    if not str(expanded.get("package_name") or "").strip():
        expanded["package_name"] = safe_title_fragment(expanded_prompt, max_chars=60)
    return expanded


def normalize_publishing_request(
    *,
    prompt: str,
    output_format: str = "pdf",
    package_name: str = "",
    prior_messages: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    expanded_prompt = expand_prompt_with_prior_context(prompt, prior_messages=prior_messages)
    normalized_format = _detect_format_with_current_prompt_precedence(
        prompt,
        expanded_prompt,
        default=output_format or "pdf",
    )
    return {
        "prompt": expanded_prompt or "DITA-OT PDF smoke test",
        "output_format": normalized_format,
        "package_name": (package_name or safe_title_fragment(expanded_prompt, max_chars=60)).strip(),
        "detected_constructs": detect_publishing_constructs(expanded_prompt),
        "references_prior_context": references_prior_context(prompt),
    }
