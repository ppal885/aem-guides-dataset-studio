"""
QA Challenge Mode — proactive pushback on weak Jira tickets (AC, validation, assumptions, edge cases).
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.llm_service import generate_text, is_llm_available


def _empty() -> dict[str, Any]:
    return {
        "challenge_points": [],
        "hidden_risks": [],
        "potential_misunderstandings": [],
        "questions_qa_should_push_back_on": [],
    }


def _dedupe_append(bucket: list[str], text: str, *, cap: int = 10) -> None:
    t = (text or "").strip()
    if len(t) < 12 or len(bucket) >= cap:
        return
    key = t[:100].lower()
    if any(key == (x[:100].lower()) for x in bucket):
        return
    bucket.append(t[:500])


def _rule_based(
    *,
    context_blob: str,
    gap_analysis: dict[str, Any],
    reasoning: dict[str, Any],
    labels: list[str],
) -> dict[str, Any]:
    out = _empty()
    t = (context_blob or "").lower()
    lab = " ".join(str(x).lower() for x in labels)

    # Gaps from analyzer → challenge material
    for g in (gap_analysis or {}).get("gaps") or []:
        if not isinstance(g, dict):
            continue
        desc = str(g.get("description") or "").strip()
        q = str(g.get("question_to_ask") or "").strip()
        impact = str(g.get("impact") or "").lower()
        if desc:
            _dedupe_append(out["challenge_points"], f"Gap signal ({impact or 'unknown'}): {desc[:400]}")
        if q:
            _dedupe_append(out["questions_qa_should_push_back_on"], q)

    for m in (reasoning or {}).get("missing_information") or []:
        s = str(m).strip()
        if s:
            _dedupe_append(out["challenge_points"], f"Missing clarity called out by reasoning: {s[:400]}")
            _dedupe_append(out["questions_qa_should_push_back_on"], f"Please document: {s[:280]}?")

    for a in (reasoning or {}).get("assumptions") or []:
        s = str(a).strip()
        if s:
            _dedupe_append(out["hidden_risks"], f"Ticket may rely on unstated assumption: {s[:400]}")
            _dedupe_append(out["potential_misunderstandings"], f"Teams may interpret differently: {s[:400]}")

    has_ac = "acceptance criteria" in t or "acceptance criterion" in t or "given when then" in t
    if not has_ac or (has_ac and len(t) < 220):
        _dedupe_append(
            out["challenge_points"],
            "Acceptance criteria look thin or absent; objective pass/fail is unclear for QA sign-off.",
        )
        _dedupe_append(
            out["questions_qa_should_push_back_on"],
            "What explicit acceptance criteria (environment, data, and outputs) define done for this ticket?",
        )

    val_kw = ("validat", "schema", "dtd", "error message", "reject", "assert", "invalid")
    if not any(k in t for k in val_kw):
        _dedupe_append(
            out["challenge_points"],
            "No validation rules described (invalid payloads, error surfaces, or rejection behavior).",
        )
        _dedupe_append(
            out["hidden_risks"],
            "Invalid or partial inputs might be accepted silently, hiding data corruption until publish or export.",
        )

    edge_kw = ("negative", "edge case", "boundary", "empty", "large file", "concurrent", "offline", "timeout")
    if not any(k in t for k in edge_kw):
        _dedupe_append(out["challenge_points"], "Edge and negative paths are not enumerated in indexed text.")
        _dedupe_append(
            out["questions_qa_should_push_back_on"],
            "Which negative, boundary, and concurrency scenarios are in scope vs explicitly unsupported?",
        )

    if "expected" not in t and "should" not in t and "must" not in t:
        _dedupe_append(out["potential_misunderstandings"], "Expected behavior is not stated in normative terms (expected/should/must).")
        _dedupe_append(
            out["questions_qa_should_push_back_on"],
            "What is the single canonical expected outcome for the primary workflow?",
        )

    if ("works" in t or "fixed" in t) and ("not work" in t or "still broken" in t or "does not" in t):
        _dedupe_append(out["challenge_points"], "Indexed text suggests conflicting outcomes; reconcile before testing.")
        _dedupe_append(out["potential_misunderstandings"], "Comment or description threads may disagree on current behavior.")

    if "workflow" in t and "unsupported" not in t and "out of scope" not in t:
        _dedupe_append(out["hidden_risks"], "Workflow coverage may be assumed universal without calling out unsupported paths.")
        _dedupe_append(
            out["questions_qa_should_push_back_on"],
            "Which workflows are explicitly unsupported or out of scope for this change?",
        )

    if any(x in t for x in ("svg", "vector", "eps", "illustrator")) and "mime" not in t and "unsupported" not in t:
        _dedupe_append(
            out["challenge_points"],
            "Behavior for external vector assets is undefined in indexed text.",
        )
        _dedupe_append(out["hidden_risks"], "MIME/type handling and fallbacks for vector assets may be unspecified.")

    if any(x in t for x in ("upgrade", "migration", "from 4.", "to 4.")) and "backward" not in t and "compat" not in t:
        _dedupe_append(out["challenge_points"], "No backward compatibility expectation mentioned for upgrade/migration context.")
        _dedupe_append(
            out["questions_qa_should_push_back_on"],
            "What backward compatibility guarantees apply to existing content and configs?",
        )

    if any(x in t for x in ("publish", "pdf", "output", "dita-ot")) and "pixel" not in t and "attachment" not in t and len(t) < 500:
        _dedupe_append(out["challenge_points"], "No publishing expectation defined beyond high-level success (outputs, fonts, attachments).")
        _dedupe_append(
            out["questions_qa_should_push_back_on"],
            "What output characteristics (PDF/Sites) are mandatory vs best-effort for this fix?",
        )

    if any(x in t for x in ("save", "reopen", "reload", "refresh")) and "persist" not in t and "draft" not in t:
        _dedupe_append(out["challenge_points"], "No save/reopen persistence validation mentioned in indexed text.")
        _dedupe_append(
            out["questions_qa_should_push_back_on"],
            "After save, close, and reopen, which fields and references must round-trip unchanged?",
        )

    if "regression" in lab or "blocker" in lab:
        _dedupe_append(out["hidden_risks"], "Severity/regression labels imply high blast radius; ensure AC covers regression suite triggers.")

    return out


def _normalize_llm(raw: dict[str, Any]) -> dict[str, Any]:
    out = _empty()
    for key in out:
        rows = raw.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows[:10]:
            if isinstance(row, str) and row.strip():
                _dedupe_append(out[key], row)
            elif isinstance(row, dict):
                txt = str(row.get("text") or row.get("point") or row.get("question") or "").strip()
                if txt:
                    _dedupe_append(out[key], txt)
    return out


def _merge(rule: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    merged = _empty()
    for key in merged:
        seen: set[str] = set()
        for src in (rule.get(key) or []) + (llm.get(key) or []):
            s = str(src).strip()
            if not s or len(s) < 8:
                continue
            k = s[:120].lower()
            if k in seen:
                continue
            seen.add(k)
            merged[key].append(s[:500])
            if len(merged[key]) >= 10:
                break
    return merged


def format_qa_challenge_markdown(bundle: dict[str, Any], *, max_chars: int = 4500) -> str:
    lines = ["\n### QA Challenge Mode (push back on weak tickets)\n"]
    titles = {
        "challenge_points": "Challenge points",
        "hidden_risks": "Hidden risks",
        "potential_misunderstandings": "Potential misunderstandings",
        "questions_qa_should_push_back_on": "Questions QA should push back on",
    }
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


class QAChallengeEngine:
    """Surface weak-ticket patterns so QA can challenge before execution."""

    async def build(
        self,
        *,
        context_blob: str,
        gap_analysis: dict[str, Any],
        reasoning: dict[str, Any],
        labels: list[str],
        jira_key: str | None = None,
    ) -> dict[str, Any]:
        rule = _rule_based(
            context_blob=context_blob or "",
            gap_analysis=gap_analysis or {},
            reasoning=reasoning or {},
            labels=labels or [],
        )

        llm_pack: dict[str, Any] | None = None
        if is_llm_available():
            try:
                system = (
                    "You are a senior QA reviewer challenging a weak Jira ticket. Return JSON ONLY with keys: "
                    "challenge_points, hidden_risks, potential_misunderstandings, questions_qa_should_push_back_on. "
                    "Each value is an array of short strings (max 6 items each), grounded only in the evidence; "
                    "no ticket IDs unless present in evidence. Cover weak acceptance criteria, missing validation rules, "
                    "hidden assumptions, missing edge cases, vague expected behavior, contradictory statements, "
                    "unsupported workflows where evidenced. No markdown outside JSON."
                )
                user = (
                    f"jira_key:{jira_key or 'n/a'}\nlabels:{json.dumps(labels)[:600]}\n"
                    f"gaps:{json.dumps(gap_analysis, ensure_ascii=False)[:3500]}\n"
                    f"reasoning:{json.dumps(reasoning, ensure_ascii=False)[:3500]}\n"
                    f"context_excerpt:{(context_blob or '')[:7000]}"
                )
                raw_txt = await generate_text(system, user, max_tokens=900, step_name="jira_qa_challenge_mode")
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
