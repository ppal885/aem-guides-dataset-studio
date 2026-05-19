"""Rule-based + optional LLM refinement pass for UAC drafts."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Sequence

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_retrieval_service import RetrievedJira
from app.services.uac_evidence_gate import (
    apply_uac_evidence_gate,
    is_generic_statement,
    uac_claim_passes,
)
from app.services.llm_service import generate_text, is_llm_available

logger = logging.getLogger(__name__)

_SECTION_PAT = re.compile(r"^###\s*(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
_HIST_KEYS = re.compile(r"^\s*\*\*([A-Z][A-Z0-9]+-\d+)\*\*\s*$", re.MULTILINE)


def _norm_dedupe(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    t = re.sub(r"^\s*[\d]+[.)]\s+", "", t)
    t = re.sub(r"^\s*[-*•]\s+", "", t)
    return t


def _as_enriched(obj: JiraEnrichedDocument | dict[str, Any]) -> JiraEnrichedDocument:
    if isinstance(obj, JiraEnrichedDocument):
        return obj
    return JiraEnrichedDocument.model_validate(obj)


def _as_retrieved(obj: RetrievedJira | dict[str, Any]) -> RetrievedJira:
    if isinstance(obj, RetrievedJira):
        return obj
    raw = dict(obj) if isinstance(obj, dict) else {}
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    ret = raw.get("retrieval") if isinstance(raw.get("retrieval"), dict) else {}
    why = str(raw.get("why_similar") or ret.get("why_similar") or "")
    score = float(raw.get("score") or ret.get("final_score") or 0.0)
    return RetrievedJira(
        jira_key=str(raw.get("jira_key") or ""),
        title=str(raw.get("title") or meta.get("title") or ""),
        chunk_type=str(raw.get("chunk_type") or meta.get("chunk_type") or ""),
        document=str(raw.get("document") or ""),
        metadata=meta,
        vector_score=float(raw.get("vector_score") or ret.get("vector_score") or 0.0),
        keyword_score=float(raw.get("keyword_score") or ret.get("keyword_score") or 0.0),
        metadata_score=float(raw.get("metadata_score") or ret.get("metadata_score") or 0.0),
        final_score=float(raw.get("final_score") or score),
        why_similar=why,
    )


def _run_async(coro):  # noqa: ANN001
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(asyncio.run, coro)
        return fut.result()


def _split_sections(s: str) -> tuple[str, dict[int, str]]:
    """Return preamble before first ### heading, and map section_no -> body including title line."""
    if not (s or "").strip():
        return "", {}
    mlist = list(_SECTION_PAT.finditer(s))
    if not mlist:
        return s.strip(), {}
    preamble = s[: mlist[0].start()].rstrip()
    out: dict[int, str] = {}
    for i, m in enumerate(mlist):
        sec_no = int(m.group(1))
        start = m.start()
        end = mlist[i + 1].start() if i + 1 < len(mlist) else len(s)
        chunk = s[start:end].strip()
        out[sec_no] = chunk
    return preamble, out


def _section_heading_line(chunk: str) -> str:
    first = (chunk or "").splitlines()[0] if chunk else ""
    return first.strip()


def _body_without_heading(chunk: str) -> str:
    lines = (chunk or "").splitlines()
    if not lines:
        return ""
    return "\n".join(lines[1:]).strip()


def _refine_risk_section(body: str, en: JiraEnrichedDocument, similar: list[RetrievedJira]) -> str:
    bullets = [l for l in (body or "").splitlines() if l.strip().startswith("-")]
    if not bullets:
        return (body or "").strip()
    res = apply_uac_evidence_gate(en, similar, "\n".join(bullets))
    cleaned = res.cleaned_answer or ""
    lines = [ln for ln in cleaned.splitlines() if ln.strip()]
    lines = lines[:5]
    return "\n".join(lines) if lines else (body or "").strip()


def _refine_similar_history(body: str) -> str:
    """Keep at most 5 **KEY** entry blocks."""
    text = body or ""
    matches = list(_HIST_KEYS.finditer(text))
    if not matches:
        return text.strip()
    intro = text[: matches[0].start()].strip()
    blocks: list[str] = []
    for i, m in enumerate(matches[:5]):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append(text[start:end].strip())
    parts = ([intro] if intro else []) + blocks
    return "\n\n".join(parts)


def _parse_scenarios(body: str) -> list[dict[str, str]]:
    """Parse Scenario / Why / Evidence / Test Layer blocks (best-effort)."""
    raw = (body or "").splitlines()
    blocks: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    field: str | None = None

    def flush() -> None:
        nonlocal cur
        if cur and cur.get("scenario"):
            blocks.append(cur)
        cur = None

    for line in raw:
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("scenario:"):
            flush()
            cur = {"scenario": stripped.split(":", 1)[1].strip(), "why": "", "evidence": "", "layer": ""}
            field = "scenario"
        elif cur is not None and low.startswith("why:"):
            cur["why"] = stripped.split(":", 1)[1].strip()
            field = "why"
        elif cur is not None and low.startswith("evidence:"):
            cur["evidence"] = stripped.split(":", 1)[1].strip()
            field = "evidence"
        elif cur is not None and low.startswith("test layer:"):
            cur["layer"] = stripped.split(":", 1)[1].strip()
            field = "layer"
        elif cur is not None and stripped and field:
            if field == "scenario":
                cur["scenario"] = (cur["scenario"] + " " + stripped).strip()
            elif field in cur:
                cur[field] = (cur[field] + " " + stripped).strip()
    flush()
    return blocks


def _format_scenario(b: dict[str, str]) -> str:
    layer = (b.get("layer") or "Manual").strip()
    if "|" in layer:
        layer = layer.split("|")[0].strip()
    return (
        f"Scenario: {b.get('scenario', '').strip()}\n"
        f"Why: {b.get('why', '').strip()}\n"
        f"Evidence: {b.get('evidence', '').strip()}\n"
        f"Test Layer: {layer}"
    )


def _refine_scenarios(body: str, en: JiraEnrichedDocument, similar: list[RetrievedJira]) -> str:
    blocks = _parse_scenarios(body)
    jk = (en.jira_key or "").strip()
    seen: set[str] = set()
    kept: list[dict[str, str]] = []

    for b in blocks:
        blob = "\n".join(b.values())
        scenario_line = b.get("scenario", "").strip()
        if jk and jk.lower() not in scenario_line.lower():
            b["scenario"] = f"{jk}: {scenario_line}".strip()

        merged = _format_scenario(b)
        nd = _norm_dedupe(scenario_line)
        if nd in seen:
            continue
        if is_generic_statement(merged) or not uac_claim_passes(merged, en, similar):
            continue
        seen.add(nd)
        kept.append(b)
        if len(kept) >= 7:
            break

    if not kept:
        return "Insufficient evidence from indexed Jira data for grounded must-test scenarios."
    return "\n\n".join(_format_scenario(x) for x in kept)


def _question_lines(text: str) -> list[str]:
    out: list[str] = []
    for line in (text or "").splitlines():
        t = line.strip()
        if not t:
            continue
        if t.startswith(("-", "*", "•")) or re.match(r"^\d+[\.)]\s+", t):
            out.append(re.sub(r"^[-*•]\s+", "", re.sub(r"^\d+[\.)]\s+", "", t)).strip())
    return out


def _refine_questions(body: str, en: JiraEnrichedDocument, similar: list[RetrievedJira]) -> str:
    lines = _question_lines(body)
    seen: set[str] = set()
    kept: list[str] = []
    for q in lines:
        nd = _norm_dedupe(q)
        if not q or nd in seen:
            continue
        if is_generic_statement(q) or not uac_claim_passes(q, en, similar):
            continue
        seen.add(nd)
        kept.append(q)
        if len(kept) >= 5:
            break
    if not kept:
        return "- Insufficient evidence from indexed Jira data to list specific UAC clarifications."
    return "\n".join(f"- {k}" for k in kept)


def _light_generic_strip(body: str) -> str:
    """Drop obviously generic bullet lines; keep classification / automation structure intact."""
    out: list[str] = []
    for line in (body or "").splitlines():
        t = line.strip()
        if t.startswith("-") and is_generic_statement(t.lstrip("-").strip()):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _rule_based_critique(
    draft_answer: str,
    en: JiraEnrichedDocument,
    similar: list[RetrievedJira],
) -> str:
    preamble, sections = _split_sections(draft_answer)
    if not sections:
        res = apply_uac_evidence_gate(en, similar, draft_answer)
        return res.cleaned_answer or ""

    order = sorted(sections.keys())
    rebuilt: list[str] = []
    if preamble:
        rebuilt.append(preamble.strip())

    for sec in order:
        chunk = sections[sec]
        title = _section_heading_line(chunk)
        body = _body_without_heading(chunk)

        if sec == 2:
            body = _refine_risk_section(body, en, similar)
        elif sec == 3:
            body = _refine_similar_history(body)
        elif sec == 4:
            body = _refine_scenarios(body, en, similar)
        elif sec == 5:
            body = _refine_questions(body, en, similar)
        else:
            body = _light_generic_strip(body)

        rebuilt.append(f"{title}\n\n{body}".strip())

    return "\n\n".join(x for x in rebuilt if x.strip())


def _evidence_pack_compact(en: JiraEnrichedDocument, similar: list[RetrievedJira], *, max_chars: int = 12000) -> str:
    payload = {
        "current": en.model_dump(),
        "similar": [r.model_dump() for r in similar[:5]],
    }
    raw = json.dumps(payload, ensure_ascii=False, default=str)
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 1] + "…"


async def _llm_refine_uac_async(
    *,
    en: JiraEnrichedDocument,
    similar: list[RetrievedJira],
    rule_based_answer: str,
) -> str:
    system = (
        "You are an editorial critic for AEM Guides UAC briefs. "
        "Tighten the draft using ONLY the evidence JSON. "
        "Remove generic QA platitudes, repetition, and unsupported claims. "
        "Merge duplicate must-test scenarios. Cap: 5 risky bullets, 5 similar tickets, 7 scenarios, 5 questions. "
        "Preserve the same Markdown section headings (### 1. … through ### 6. …). "
        "Output only the refined document — no preamble."
    )
    user = (
        "## Evidence\n```json\n"
        + _evidence_pack_compact(en, similar)
        + "\n```\n\n## Rule-based draft\n"
        + rule_based_answer
    )
    return (await generate_text(system, user, max_tokens=6000, step_name="uac_critic_refine")).strip()


def critic_refine_uac_answer(
    current_jira: JiraEnrichedDocument | dict[str, Any],
    similar_jiras: Sequence[RetrievedJira | dict[str, Any]],
    draft_answer: str,
) -> str:
    """
    Refine a UAC draft: rule-based cleanup always; optional LLM pass when configured and available.

    Env ``UAC_CRITIC_USE_LLM`` (default ``true``): when truthy and ``is_llm_available()``, runs a second LLM pass.
    """
    en = _as_enriched(current_jira)
    similar = [_as_retrieved(x) for x in (similar_jiras or [])]
    base = _rule_based_critique((draft_answer or "").strip(), en, similar)

    use_llm = os.getenv("UAC_CRITIC_USE_LLM", "true").lower() in ("1", "true", "yes", "on")
    if use_llm and is_llm_available() and base.strip():
        min_len = max(200, len(base) // 5)
        try:
            refined = _run_async(_llm_refine_uac_async(en=en, similar=similar, rule_based_answer=base))
            if refined and len(refined) >= min_len:
                return refined
            if refined:
                logger.warning(
                    "UAC critic LLM output too short (%d chars, min %d); falling back to rule-based.",
                    len(refined),
                    min_len,
                )
        except Exception as exc:
            logger.warning("UAC critic LLM refinement failed: %s", exc, exc_info=True)
    return base
