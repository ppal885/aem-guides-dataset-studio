"""
Prompt interface: treat prompts as structured, composable specs rather than raw strings.
Defines Protocol, PromptSpec, and Builder for versioned, section-based prompts.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

import json


@dataclass
class PromptSpec:
    """
    Structured prompt specification. Sections are composed in order.
    Dynamic blocks (user_context, rag_context) are injected by the builder.
    """

    id: str
    version: str
    sections: dict[str, str] = field(default_factory=dict)
    section_order: list[str] = field(default_factory=list)

    def get_section(self, name: str) -> str:
        return self.sections.get(name, "")

    def render_base(self) -> str:
        """Render base sections in order, excluding dynamic slots."""
        order = self.section_order or list(self.sections.keys())
        parts = []
        for name in order:
            if name in ("user_context", "rag_context"):
                continue
            content = self.sections.get(name, "").strip()
            if content:
                parts.append(content)
        return "\n\n".join(parts)


class IPromptProvider(Protocol):
    """Protocol for prompt providers. Implementations load and return PromptSpec."""

    def get_spec(self, prompt_id: str, version: Optional[str] = None) -> Optional[PromptSpec]:
        """Load and return a PromptSpec by id and optional version."""
        ...


class PromptBuilder:
    """
    Builds final prompt string from spec + dynamic blocks.
    Supports injection of user_context and rag_context.
    """

    def __init__(self, spec: PromptSpec):
        self.spec = spec

    def build(
        self,
        user_context: str = "",
        rag_context: str = "",
    ) -> str:
        """Compose final prompt from base sections + dynamic blocks."""
        parts = [self.spec.render_base()]
        if user_context.strip():
            parts.append(user_context)
        if rag_context.strip():
            parts.append(rag_context)
        return "\n\n".join(p for p in parts if p.strip())


def load_prompt_spec(
    prompts_dir: Path,
    prompt_id: str,
    version: str = "v1",
) -> Optional[PromptSpec]:
    """
    Load PromptSpec from JSON. Falls back to .txt if no .json.
    JSON format: { "id": "...", "version": "...", "sections": {...}, "section_order": [...] }
    """
    version_clean = version.lstrip("v")
    for path in [
        prompts_dir / f"{prompt_id}_v{version_clean}.json",
        prompts_dir / f"{prompt_id}.json",
    ]:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return PromptSpec(
                    id=data.get("id", prompt_id),
                    version=data.get("version", version),
                    sections=data.get("sections", {}),
                    section_order=data.get("section_order", []),
                )
            except (json.JSONDecodeError, TypeError) as e:
                from app.core.structured_logging import get_structured_logger
                get_structured_logger(__name__).warning_structured(
                    "Failed to load prompt spec JSON",
                    extra_fields={"path": str(path), "error": str(e)},
                )
                break

    # Fallback: load from .txt as single section
    txt_path = prompts_dir / f"{prompt_id}.txt"
    if txt_path.exists():
        content = txt_path.read_text(encoding="utf-8")
        return PromptSpec(
            id=prompt_id,
            version=version,
            sections={"base": content},
            section_order=["base"],
        )
    return None
