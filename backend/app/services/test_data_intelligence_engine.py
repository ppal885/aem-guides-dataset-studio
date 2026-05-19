"""
Test Data Intelligence — infer QA fixtures, corpora, and environment needs from Jira context.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.llm_service import generate_text, is_llm_available

_OUTPUT_KEYS: tuple[str, ...] = (
    "required_topics",
    "required_maps",
    "required_assets",
    "required_metadata",
    "required_conditions",
    "required_baselines",
    "required_versions",
    "required_large_data",
    "required_permissions",
)


def _empty() -> dict[str, Any]:
    return {k: [] for k in _OUTPUT_KEYS}


def _dedupe_append(bucket: list[str], text: str, *, cap: int = 12) -> None:
    t = (text or "").strip()
    if len(t) < 8 or len(bucket) >= cap:
        return
    k = t[:120].lower()
    if any(k == x[:120].lower() for x in bucket):
        return
    bucket.append(t[:400])


def _norm(s: str) -> str:
    return (s or "").lower()


def _blob(context_blob: str, labels: list[str], components: list[str], issue_type: str) -> str:
    lab = " ".join(str(x).lower() for x in labels)
    comp = " ".join(str(x).lower() for x in components)
    it = (issue_type or "").lower()
    return _norm(f"{context_blob}\n{lab}\n{comp}\n{it}")


def _rule_based(
    *,
    context_blob: str,
    labels: list[str],
    components: list[str],
    issue_type: str,
) -> dict[str, Any]:
    out = _empty()
    t = _blob(context_blob, labels, components, issue_type)

    if any(x in t for x in ("publish", "pdf", "dita-ot", "output preset", "sites output", "native pdf")):
        _dedupe_append(out["required_topics"], "Representative DITA topics referenced by the failing publish path")
        _dedupe_append(out["required_maps"], "Root DITAMAP / bookmap used for publish reproduction")
        _dedupe_append(out["required_assets"], "Vector or high-DPI images (SVG/EPS/AI) if publishing layout is implicated")
        _dedupe_append(out["required_metadata"], "Output preset / template metadata matching customer AEM Guides configuration")
        _dedupe_append(out["required_conditions"], "Publishing presets and DITA-OT parameters aligned to the reported environment")

    if any(x in t for x in ("ditaval", "profiling", "audience", "platform", "rev=")):
        _dedupe_append(out["required_conditions"], "DITAVAL and profiling sets exercising include/exclude combinations")

    if any(x in t for x in ("baseline", "version compare", "snapshot", "branch", "merge")):
        _dedupe_append(out["required_baselines"], "Baseline history with at least two labeled snapshots for compare workflows")
        _dedupe_append(out["required_topics"], "Topics modified across baseline boundaries to detect drift")

    if any(x in t for x in ("conref", "keyref", "keydef", "xref", "href", "scope=")):
        _dedupe_append(out["required_topics"], "Topic set with deliberate conref/keyref/keydef graphs and fallbacks")
        _dedupe_append(out["required_maps"], "Map wiring keydefs and scoped references used in the defect")

    if any(x in t for x in ("large", "1000", "thousand", "performance", "slow", "timeout", "huge map")):
        _dedupe_append(out["required_large_data"], "Large map/topic corpus or generated bulk topics to reproduce scale")

    if any(x in t for x in ("locale", "i18n", "translation", "language", "rtl", "unicode", "multilingual")):
        _dedupe_append(out["required_topics"], "Multilingual topic/map samples (RTL/Latin/CJK as applicable)")
        _dedupe_append(out["required_metadata"], "Translated strings / lang attributes on elements under test")

    if any(x in t for x in ("permission", "acl", "impersonat", "read-only", "author", "reviewer", "workflow")):
        _dedupe_append(out["required_permissions"], "Users/roles matching AEM security model (author, reviewer, admin) for reproduction")

    if any(x in t for x in ("aem ", "guides ", "6.5", "6.4", "cloud service", "cs ", "4.2", "4.3", "4.4")):
        _dedupe_append(out["required_versions"], "Exact AEM + AEM Guides build numbers and SP/CFP levels from the ticket")

    if any(x in t for x in ("metadata", "topicmeta", "navtitle", "dc:", "props", "attribute")):
        _dedupe_append(out["required_metadata"], "Topics/maps with rich metadata and conditional props as in production IA")

    if any(x in t for x in ("image", "dam", "svg", "attachment", "mime", "video")):
        _dedupe_append(out["required_assets"], "DAM-linked or embedded media assets including MIME edge types referenced in the issue")

    if "regression" in t or "bug" in t or "defect" in t:
        _dedupe_append(out["required_topics"], "Golden reference topics/maps from pre-change behavior for diff/regression")

    return out


def _normalize_llm(raw: dict[str, Any]) -> dict[str, Any]:
    out = _empty()
    for key in _OUTPUT_KEYS:
        rows = raw.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows[:12]:
            if isinstance(row, str) and row.strip():
                _dedupe_append(out[key], row)
            elif isinstance(row, dict):
                txt = str(row.get("item") or row.get("text") or row.get("description") or "").strip()
                if txt:
                    _dedupe_append(out[key], txt)
    return out


def _merge(rule: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    merged = _empty()
    for key in _OUTPUT_KEYS:
        seen: set[str] = set()
        for src in (rule.get(key) or []) + (llm.get(key) or []):
            s = str(src).strip()
            if len(s) < 8:
                continue
            k = s[:120].lower()
            if k in seen:
                continue
            seen.add(k)
            merged[key].append(s[:400])
            if len(merged[key]) >= 12:
                break
    return merged


def format_test_data_intelligence_markdown(bundle: dict[str, Any], *, max_chars: int = 5000) -> str:
    titles = {
        "required_topics": "Required topics",
        "required_maps": "Required maps",
        "required_assets": "Required assets",
        "required_metadata": "Required metadata",
        "required_conditions": "Required conditions (DITAVAL / presets)",
        "required_baselines": "Required baselines",
        "required_versions": "Required versions",
        "required_large_data": "Required large / scale data",
        "required_permissions": "Required permissions / roles",
    }
    lines = ["\n### Test data intelligence\n"]
    for key, title in titles.items():
        rows = bundle.get(key) or []
        if not rows:
            continue
        lines.append(f"**{title}**")
        for row in rows[:8]:
            lines.append(f"- {row}")
        lines.append("")
    text = "\n".join(lines).strip()
    return text[:max_chars]


class TestDataIntelligenceEngine:
    """Infer datasets and fixtures QA should prepare from labels, issue type, and ticket text."""

    async def build(
        self,
        *,
        context_blob: str,
        labels: list[str],
        components: list[str],
        issue_type: str,
        jira_key: str | None = None,
    ) -> dict[str, Any]:
        rule = _rule_based(
            context_blob=context_blob or "",
            labels=labels or [],
            components=components or [],
            issue_type=issue_type or "",
        )

        llm_pack: dict[str, Any] | None = None
        if is_llm_available():
            try:
                system = (
                    "You are an AEM Guides QA data planner. Return JSON ONLY with keys: "
                    "required_topics, required_maps, required_assets, required_metadata, required_conditions, "
                    "required_baselines, required_versions, required_large_data, required_permissions. "
                    "Each value is an array of short imperative strings (max 5 per key) describing concrete test data, "
                    "corpora, or environment setup implied by the ticket — vector images for publishing tests, DITAVAL "
                    "conditions, baseline history, conref/keyref setup, large maps/topics, multilingual content, "
                    "publishing presets, permissions. Ground in evidence; omit keys with empty arrays if none. "
                    "No markdown, no prose outside JSON."
                )
                user = (
                    f"jira_key:{jira_key or 'n/a'}\nissue_type:{issue_type}\n"
                    f"labels:{json.dumps(labels)[:800]}\ncomponents:{json.dumps(components)[:800]}\n"
                    f"context:{(context_blob or '')[:8000]}"
                )
                raw_txt = await generate_text(system, user, max_tokens=900, step_name="jira_test_data_intelligence")
                raw_txt = raw_txt.strip()
                if raw_txt.startswith("```"):
                    raw_txt = re.sub(r"^```(?:json)?\s*", "", raw_txt)
                    raw_txt = re.sub(r"\s*```$", "", raw_txt)
                parsed = json.loads(raw_txt)
                if isinstance(parsed, dict):
                    llm_pack = _normalize_llm(parsed)
            except Exception:
                llm_pack = None

        if llm_pack:
            return _merge(rule, llm_pack)
        return rule
