"""Next best QA questions: short, non-repeating, gap and risk aware."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.llm_service import generate_text, is_llm_available


def _norm_q(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _words_len(s: str) -> int:
    return len([w for w in re.findall(r"\S+", s or "")])


def _norm_avoid_key(s: str) -> str:
    """Normalize suggested-question text for dedupe against prior chips."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())[:500]


class DynamicQuestionEngine:
    async def next_questions(
        self,
        *,
        answer: str,
        reasoning: dict[str, Any],
        gaps: dict[str, Any],
        risk: dict[str, Any],
        history: list[dict[str, Any]] | None,
        intent: str,
        avoid_normalized: set[str] | None = None,
        label_intel: dict[str, Any] | None = None,
        persona_mode_id: str | None = None,
    ) -> list[str]:
        asked: set[str] = set()
        for turn in history or []:
            if str(turn.get("role") or "").lower() in {"user", "human"}:
                asked.add(_norm_q(str(turn.get("content") or "")))

        avoid = avoid_normalized or set()
        out: list[str] = []
        seen: set[str] = set()

        def is_blocked(raw: str, nq_key: str) -> bool:
            if not nq_key:
                return True
            if nq_key in seen:
                return True
            if nq_key in asked:
                return True
            if _norm_avoid_key(raw) in avoid:
                return True
            return False

        seed: list[str] = []
        for g in (gaps.get("gaps") if isinstance(gaps, dict) else None) or []:
            if isinstance(g, dict):
                q = str(g.get("question_to_ask") or "").strip()
                if q and _words_len(q) <= 20:
                    seed.append(q)
        for m in (reasoning.get("missing_information") if isinstance(reasoning, dict) else None) or []:
            mq = str(m).strip().rstrip(".") + "?"
            if _words_len(mq) <= 20:
                seed.append(mq)
        for area in (risk.get("risk_areas") if isinstance(risk, dict) else None) or []:
            rq = f"What coverage for {area}?"
            if _words_len(rq) <= 20:
                seed.append(rq)

        for q in seed:
            nq = _norm_q(q)
            if is_blocked(q, nq):
                continue
            seen.add(nq)
            out.append(q[:300])
            if len(out) >= 5:
                return out[:5]

        if is_llm_available():
            try:
                system = (
                    "Generate 3-5 short discussion prompts for QA, PM, and Dev together on the ticket or topic. "
                    "Focus on scope, risk, acceptance, and dependencies—not a post-job retrospective. "
                    'JSON only: {"questions":["..."]} Each question MUST be under 20 words, unique, '
                    "actionable, not generic. Target gaps/risks. No numbering."
                )
                li_tail = ""
                if isinstance(label_intel, dict) and label_intel:
                    li_tail = f"\nlabel_intel:{json.dumps(label_intel, ensure_ascii=False)[:2200]}"
                persona_tail = ""
                if persona_mode_id:
                    persona_tail = f"\npersona_mode:{persona_mode_id}"
                user = (
                    f"intent:{intent}\nanswer_excerpt:{(answer or '')[:2000]}\n"
                    f"gaps:{json.dumps(gaps)[:2500]}\nrisk:{json.dumps(risk)[:1500]}\n"
                    f"reasoning:{json.dumps(reasoning)[:2000]}{li_tail}{persona_tail}"
                )
                raw = await generate_text(system, user, max_tokens=220, step_name="jira_copilot_dynamic_q")
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                data = json.loads(raw)
                qs = data.get("questions") if isinstance(data, dict) else None
                if isinstance(qs, list):
                    for q in qs:
                        s = str(q).strip()
                        if _words_len(s) > 20:
                            s = " ".join(re.findall(r"\S+", s)[:20])
                        nq = _norm_q(s)
                        if is_blocked(s, nq):
                            continue
                        seen.add(nq)
                        out.append(s)
                        if len(out) >= 5:
                            break
            except Exception:
                pass

        if len(out) < 3:
            fallback = [
                "Which AEM Guides versions are in scope?",
                "What exact acceptance criteria are signed off?",
                "Which publish outputs must we validate end-to-end?",
            ]
            for f in fallback:
                nf = _norm_q(f)
                if is_blocked(f, nf):
                    continue
                seen.add(nf)
                out.append(f)
                if len(out) >= 3:
                    break
        return out[:5]
