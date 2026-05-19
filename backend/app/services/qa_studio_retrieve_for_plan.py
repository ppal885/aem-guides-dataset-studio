"""RAG-style retrieval for QA Studio planning: bundled knowledge + optional Jira QA Chroma."""

from __future__ import annotations

import json
from typing import Any

from app.services.qa_studio_bundled import (
    load_action_catalog_bundle,
    load_dom_patterns_bundle,
    search_playbooks,
)


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


def _plan_lite() -> bool:
    import os

    return _truthy(os.getenv("GQS_PLAN_LITE")) or _truthy(os.getenv("QA_STUDIO_PLAN_LITE"))


def build_grounding_digest(
    *,
    fields: dict[str, Any],
    jira_summary: str,
    target_area: str,
    manual_notes: str,
    playbook_limit: int = 4,
) -> str:
    """Deterministic text block injected into LLM prompts (bundled corpora)."""
    parts: list[str] = []
    probes = [
        (target_area or "").strip(),
        (jira_summary or "").strip()[:300],
        (fields.get("acceptance_criteria") or "")[:200],
        (fields.get("expected_fixed_behavior") or "")[:200],
    ]
    hits: list[dict[str, Any]] = []
    for p in probes:
        if not p:
            continue
        hits = search_playbooks(query=p[:200])
        if hits:
            break
    if not hits:
        hits = search_playbooks()
    hits = hits[:playbook_limit]

    parts.append("### Matched playbooks (excerpt)")
    for pb in hits:
        sid = pb.get("id", "")
        parts.append(f"- {sid}: {pb.get('title', '')}")
        for s in (pb.get("steps") or [])[:4]:
            parts.append(f"    step phrase: {s}")
        for nx in (pb.get("anti_patterns") or [])[:2]:
            parts.append(f"    anti-pattern: {nx}")

    ac = load_action_catalog_bundle()
    parts.append("\n### Action catalog (author via these layers)")
    for a in ac.get("actions", [])[:12]:
        parts.append(f"- {a.get('id')}: {a.get('summary')}")

    dom = load_dom_patterns_bundle()
    parts.append("\n### DOM pattern hints")
    ta = (target_area or "").lower()
    pats = dom.get("patterns", [])
    shown = 0
    for pat in pats:
        if not isinstance(pat, dict):
            continue
        area = str(pat.get("aem_guides_area", "")).lower()
        if ta and area and area not in ta and ta not in area:
            continue
        parts.append(f"- {pat.get('id')}: {pat.get('description', '')}")
        ex = pat.get("stable_xpath_examples") or []
        if ex:
            parts.append(f"  example: {ex[0]}")
        shown += 1
        if shown >= 5:
            break
    if shown == 0:
        for pat in pats[:3]:
            if isinstance(pat, dict):
                parts.append(f"- {pat.get('id')}: {pat.get('description', '')}")

    notes = (manual_notes or "").strip()
    if notes:
        parts.append("\n### Author notes / evidence")
        parts.append(notes[:1500])

    if _plan_lite():
        parts.append("\n(Plan lite: prefer fewer steps and minimal new artifacts.)")

    return "\n".join(parts)


def retrieve_jira_similar_for_plan(
    *,
    query_text: str,
    jira_key_exclude: str | None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Optional hybrid retrieval from `jira_qa` Chroma (empty if unavailable)."""
    if not (query_text or "").strip():
        return []
    try:
        from app.services.jira_retrieval_service import retrieve_similar_jiras
    except Exception:
        return []

    try:
        rows = retrieve_similar_jiras(
            query_text[:12000],
            domain=None,
            dita_entities=[],
            affected_outputs=[],
            customer_names=[],
            limit=limit,
            exclude_jira_key=jira_key_exclude,
        )
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "jira_key": r.jira_key,
                "title": r.title,
                "chunk_type": r.chunk_type,
                "score": round(float(r.final_score), 4),
                "excerpt": (r.document or "")[:800],
                "why_similar": (r.why_similar or "")[:500],
            }
        )
    return out


def retrieve_for_plan(
    *,
    fields: dict[str, Any],
    jira_summary: str,
    jira_description: str,
    jira_raw: str,
    repro_steps: str,
    target_area: str,
    manual_notes: str,
    jira_key: str | None,
) -> dict[str, Any]:
    """
    Assemble grounding for planning/generation: digest text + structured similar-Jira rows.
    """
    summary = (jira_summary or "").strip()
    raw = (jira_raw or "").strip()
    blob = "\n\n".join(
        t
        for t in (
            summary,
            jira_description.strip(),
            raw[:4000] if raw else "",
            repro_steps.strip(),
            (fields.get("acceptance_criteria") or "")[:2000],
            (fields.get("expected_fixed_behavior") or "")[:2000],
        )
        if (t or "").strip()
    )
    digest = build_grounding_digest(
        fields=fields,
        jira_summary=summary,
        target_area=target_area,
        manual_notes=manual_notes,
    )
    similar = retrieve_jira_similar_for_plan(
        query_text=blob,
        jira_key_exclude=(jira_key or "").strip() or None,
        limit=5,
    )
    similar_text = ""
    if similar:
        similar_text = "\n### Similar Jira QA chunks (retrieval)\n"
        for s in similar:
            similar_text += f"- {s.get('jira_key')} ({s.get('score')}): {s.get('title')}\n  {s.get('excerpt', '')[:400]}\n"

    return {
        "retrieval_query_excerpt": blob[:2000],
        "grounding_digest": digest + similar_text,
        "jira_similar": similar,
        "digest_json": {
            "playbook_probe": (target_area or summary or "")[:200],
            "jira_similar_keys": [s.get("jira_key") for s in similar],
        },
    }


def format_compact_plan_for_prompt(plan: dict[str, Any]) -> str:
    """Stable JSON string for generation prompts."""
    return json.dumps(plan, ensure_ascii=False, indent=2)[:24000]
