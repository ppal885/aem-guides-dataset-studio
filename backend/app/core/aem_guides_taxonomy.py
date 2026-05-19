"""Central AEM Guides / DITA taxonomy for Jira enrichment (YAML under ``backend/config/``)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

_TAXONOMY_CACHE: dict[str, Any] | None = None


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def taxonomy_yaml_path() -> Path:
    return _backend_root() / "config" / "aem_guides_taxonomy.yaml"


def _fallback_taxonomy() -> dict[str, Any]:
    """Tiny inline defaults if the YAML file is missing or invalid."""
    return {
        "version": 1,
        "defaults": {"keyword_weight": 2.5},
        "customer_detection": {"label_exclude_extras": ["regression", "automation", "qa", "bug", "smoke"]},
        "feature_signals": {
            "translation": ["translation", "xliff"],
            "review": ["review", "annotation"],
            "search": ["search", "solr"],
            "workflow": ["workflow"],
        },
        "domains": {
            "publishing": {
                "keyword_weight": 1.8,
                "keywords": ["publish", "publishing", "dita ot", "dita-ot"],
                "entities": ["topicref"],
                "outputs": [{"name": "DITA-OT", "phrases": ["dita-ot", "dita ot"]}],
                "test_layers": ["Publishing"],
            },
            "editor": {
                "keyword_weight": 2.0,
                "keywords": ["web editor", "author view"],
                "entities": ["preview"],
                "outputs": [{"name": "preview", "phrases": ["preview"]}],
                "test_layers": ["UI"],
            },
        },
    }


def load_taxonomy() -> dict[str, Any]:
    global _TAXONOMY_CACHE
    if _TAXONOMY_CACHE is not None:
        return _TAXONOMY_CACHE
    path = taxonomy_yaml_path()
    data: dict[str, Any]
    try:
        raw = path.read_text(encoding="utf-8")
        loaded = yaml.safe_load(raw)
        if not isinstance(loaded, dict):
            raise ValueError("taxonomy root must be a mapping")
        if not isinstance(loaded.get("domains"), dict):
            raise ValueError("taxonomy must contain a 'domains' mapping")
        data = loaded
    except Exception as exc:
        logger.warning_structured(
            "aem_guides_taxonomy_yaml_unavailable",
            extra_fields={"path": str(path), "error": str(exc), "fallback": True},
        )
        data = _fallback_taxonomy()
    _TAXONOMY_CACHE = data
    return data


@lru_cache(maxsize=1)
def get_domain_specs() -> tuple[tuple[str, tuple[str, ...], float], ...]:
    data = load_taxonomy()
    default_w = float((data.get("defaults") or {}).get("keyword_weight") or 2.5)
    rows: list[tuple[str, tuple[str, ...], float]] = []
    domains = data.get("domains") or {}
    if not isinstance(domains, dict):
        return tuple()
    for dom_id, spec in domains.items():
        if not isinstance(spec, dict):
            continue
        kws_raw = spec.get("keywords") or []
        if not isinstance(kws_raw, list):
            continue
        kws = tuple(str(x).strip() for x in kws_raw if str(x).strip())
        if not kws:
            continue
        w = float(spec.get("keyword_weight", default_w))
        rows.append((str(dom_id), kws, w))
    return tuple(rows)


def _compile_entity_entry(entry: Any) -> tuple[str, re.Pattern[str]] | None:
    if isinstance(entry, str):
        label = entry.strip()
        if not label:
            return None
        if " " in label:
            parts = [re.escape(p) for p in label.split()]
            pat = r"\b" + r"\s+".join(parts) + r"\b"
        else:
            pat = r"\b" + re.escape(label) + r"\b"
        return label, re.compile(pat, re.I)
    if isinstance(entry, dict):
        label = str(entry.get("label") or entry.get("name") or "").strip()
        expr = str(entry.get("regex") or entry.get("pattern") or "").strip()
        if not label or not expr:
            return None
        return label, re.compile(expr, re.I)
    return None


@lru_cache(maxsize=1)
def get_entity_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    data = load_taxonomy()
    domains = data.get("domains") or {}
    seen: set[str] = set()
    out: list[tuple[str, re.Pattern[str]]] = []
    if not isinstance(domains, dict):
        return tuple()
    for _dom_id, spec in domains.items():
        if not isinstance(spec, dict):
            continue
        ent_raw = spec.get("entities") or []
        if not isinstance(ent_raw, list):
            continue
        for ent in ent_raw:
            compiled = _compile_entity_entry(ent)
            if compiled is None:
                continue
            label, pat = compiled
            if label in seen:
                continue
            seen.add(label)
            out.append((label, pat))
    return tuple(out)


def _normalize_output_entries(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list):
        out: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                phrases = item.get("phrases") or item.get("match") or []
                if name and isinstance(phrases, list):
                    out.append({"name": name, "phrases": [str(p) for p in phrases if str(p).strip()]})
            elif isinstance(item, str) and item.strip():
                s = item.strip()
                out.append({"name": s, "phrases": [s.lower()]})
        return out
    return []


@lru_cache(maxsize=1)
def get_output_signals() -> tuple[tuple[str, tuple[str, ...]], ...]:
    data = load_taxonomy()
    domains = data.get("domains") or {}
    accum: dict[str, set[str]] = {}
    if isinstance(domains, dict):
        for spec in domains.values():
            if not isinstance(spec, dict):
                continue
            for od in _normalize_output_entries(spec.get("outputs")):
                name = od["name"]
                phrases = od.get("phrases") or []
                accum.setdefault(name, set()).update(p.lower() for p in phrases if p)
    ordered_names = sorted(accum.keys(), key=lambda x: x.lower())
    return tuple((name, tuple(sorted(accum[name]))) for name in ordered_names if accum[name])


@lru_cache(maxsize=1)
def get_feature_signals() -> tuple[tuple[str, tuple[str, ...]], ...]:
    data = load_taxonomy()
    fs = data.get("feature_signals") or {}
    out: list[tuple[str, tuple[str, ...]]] = []
    if isinstance(fs, dict):
        for feat_id, needles in fs.items():
            if not isinstance(needles, list):
                continue
            ph = tuple(str(x).strip().lower() for x in needles if str(x).strip())
            if ph:
                out.append((str(feat_id), ph))
    return tuple(sorted(out, key=lambda x: x[0].lower()))


@lru_cache(maxsize=1)
def get_customer_label_exclude_patterns() -> frozenset[str]:
    data = load_taxonomy()
    merged: set[str] = set()
    domains = data.get("domains") or {}
    if isinstance(domains, dict):
        for k in domains:
            s = str(k).strip()
            if not s:
                continue
            merged.add(s)
            merged.add(s.lower())
            merged.add(s.lower().replace(" ", "_").replace("-", "_"))
    extras_raw = ((data.get("customer_detection") or {}).get("label_exclude_extras")) or []
    if isinstance(extras_raw, list):
        for x in extras_raw:
            t = str(x).strip()
            if not t:
                continue
            merged.add(t)
            merged.add(t.lower())
            merged.add(t.lower().replace(" ", "_").replace("-", "_"))
    return frozenset(merged)


def get_test_layers_for_domain(domain_id: str) -> tuple[str, ...]:
    data = load_taxonomy()
    spec = (data.get("domains") or {}).get(domain_id)
    if not isinstance(spec, dict):
        return tuple()
    tl = spec.get("test_layers") or []
    if not isinstance(tl, list):
        return tuple()
    return tuple(str(x).strip() for x in tl if str(x).strip())


@lru_cache(maxsize=1)
def taxonomy_bullet_summary_for_prompt() -> str:
    """Compact domain keyword lines from YAML for LLM grounding (drift-aligned with enrichment)."""
    data = load_taxonomy()
    domains = data.get("domains") or {}
    if not isinstance(domains, dict):
        return ""
    lines: list[str] = ["Taxonomy domains (keywords from aem_guides_taxonomy.yaml):"]
    for dom_id in sorted(domains.keys(), key=lambda x: str(x).lower()):
        spec = domains.get(dom_id)
        if not isinstance(spec, dict):
            continue
        kws = spec.get("keywords") or []
        if not isinstance(kws, list):
            continue
        shown = ", ".join(str(x) for x in kws[:5] if str(x).strip())
        if shown:
            lines.append(f"- {dom_id}: {shown}")
    return "\n".join(lines)


def reload_taxonomy() -> dict[str, Any]:
    """Clear in-memory and derived caches, then reload from disk (tests / hotfix)."""
    global _TAXONOMY_CACHE
    _TAXONOMY_CACHE = None
    get_domain_specs.cache_clear()
    get_entity_patterns.cache_clear()
    get_output_signals.cache_clear()
    get_feature_signals.cache_clear()
    get_customer_label_exclude_patterns.cache_clear()
    taxonomy_bullet_summary_for_prompt.cache_clear()
    return load_taxonomy()
