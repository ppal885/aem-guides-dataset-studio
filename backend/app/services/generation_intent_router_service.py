"""Shared routing for DITA generation versus publishing-behavior datasets.

This is the architecture boundary that keeps review-first single-topic DITA
authoring separate from deterministic DITA-OT publishing corpora. Chat, slash
commands, tools, and MCP should call this before executing a generation tool.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.services.publishing_dataset_intent_service import (
    detect_publishing_dataset_intent,
    expand_prompt_with_prior_context,
    has_publishing_behavior_terms,
    references_prior_context,
)


_CONTEXTUAL_DITA_DATASET_REQUEST = re.compile(
    r"\b(generate|create|build|make|need|want|get|give|show|prepare|produce)\b"
    r".*\b(data|dataset|test\s+data|sample|corpus|bundle|dita|map|topics?|examples?)\b",
    re.IGNORECASE,
)


def route_generation_intent(
    user_content: str,
    *,
    prior_messages: list[str] | tuple[str, ...] | None = None,
    requested_tool: str = "",
    source: str = "generation_router",
    tool_args: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a replacement tool intent when generation must be rerouted.

    Returns ``None`` when the original caller should continue with its normal
    path, usually plain ``generate_dita`` single-topic authoring.
    """

    text = (user_content or "").strip()
    args = copy.deepcopy(tool_args or {})
    requested = (requested_tool or "").strip()
    if not text and requested == "generate_dita":
        text = str(args.get("text") or args.get("prompt") or args.get("prompt_text") or "").strip()
    if not text:
        return None

    expanded = expand_prompt_with_prior_context(text, prior_messages=prior_messages)
    publishing_intent = detect_publishing_dataset_intent(expanded)
    if publishing_intent:
        publishing_intent["source"] = _source_name(source, "redirected_to_dita_ot")
        return publishing_intent

    if (
        references_prior_context(text)
        and _CONTEXTUAL_DITA_DATASET_REQUEST.search(text)
        and has_publishing_behavior_terms(expanded)
    ):
        return {
            "name": "create_job",
            "args": {
                "recipe_type": "freeform",
                "subject": "DITA construct behavior dataset",
                "prompt_text": expanded,
            },
            "source": _source_name(source, "redirected_to_freeform_dataset"),
        }

    return None


def normalize_generation_tool_intent(
    tool_intent: dict[str, Any] | None,
    *,
    user_content: str = "",
    prior_messages: list[str] | tuple[str, ...] | None = None,
    source: str = "tool",
) -> dict[str, Any] | None:
    """Normalize any explicit generation intent through the shared router."""

    if not tool_intent:
        return None
    tool_name = str(tool_intent.get("name") or "").strip()
    args = tool_intent.get("args") if isinstance(tool_intent.get("args"), dict) else {}
    if tool_name != "generate_dita":
        return tool_intent
    text = str(args.get("text") or user_content or "").strip()
    redirected = route_generation_intent(
        text,
        prior_messages=prior_messages,
        requested_tool=tool_name,
        source=str(tool_intent.get("source") or source),
        tool_args=args,
    )
    return redirected or tool_intent


def _source_name(source: str, suffix: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", (source or "generation_router").strip()).strip("_")
    return f"{base or 'generation_router'}_{suffix}"
