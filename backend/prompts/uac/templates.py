"""Filesystem-backed UAC template loader."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


def _template_dir() -> Path:
    return Path(__file__).resolve().parent


def _normalize_domain(domain: str | None) -> str:
    normalized = (domain or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "conkeyref": "keyref",
        "nativepdf": "native_pdf",
        "native_pdf_publishing": "native_pdf",
        "image": "image_rendition",
        "image_handling": "image_rendition",
        "rendition": "image_rendition",
        "post_processing": "post_processing",
        "postprocessor": "post_processing",
        "uuid_reference": "uuid",
    }
    return aliases.get(normalized, normalized)


@lru_cache(maxsize=64)
def load_uac_domain_template(domain: str | None) -> str:
    """Load base + domain-specific prompt hints.

    TODO: allow tenant-specific prompt packs once model/provider routing is
    externalized from the FastAPI service layer.
    """

    root = _template_dir()
    base = root / "base.md"
    dom = root / f"{_normalize_domain(domain)}.md"
    parts: list[str] = []
    if base.exists():
        parts.append(base.read_text(encoding="utf-8").strip())
    if dom.exists():
        parts.append(dom.read_text(encoding="utf-8").strip())
    return "\n\n".join(p for p in parts if p)


__all__ = ["load_uac_domain_template"]
