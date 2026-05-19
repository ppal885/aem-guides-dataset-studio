"""Focused UAC clarification questions (stdlib only)."""

from __future__ import annotations

import re

_GENERIC_Q = re.compile(
    r"(?i)^\s*(what\s+is\s+(the\s+)?expected\s+behavior|"
    r"what\s+should\s+happen|is\s+requirements?\s+clear|"
    r"are\s+requirements?\s+clear)\s*\??\s*$"
)

_ALLOWED_WHOM = frozenset({"PM", "Dev", "QA", "Tech Writer"})


def _norm_q(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _collect_verbatim_anchors(en: dict) -> list[str]:
    out: list[str] = []
    for field in ("dita_entities", "affected_outputs", "components", "customer_names"):
        raw = en.get(field)
        if isinstance(raw, list):
            for x in raw:
                t = str(x).strip()
                if t and t not in out:
                    out.append(t)
    jk = str(en.get("jira_key") or "").strip()
    if jk:
        out.append(jk)
    return out


def _similar_keys(similar: list) -> list[str]:
    keys: list[str] = []
    for s in similar or []:
        if isinstance(s, dict):
            k = str(s.get("jira_key") or "").strip()
            if k:
                keys.append(k)
    return keys


def _question_grounded(q: str, anchors: list[str], sim_keys: list[str]) -> bool:
    blob = q or ""
    for a in anchors:
        if a and (a in blob or a.lower() in blob.lower()):
            return True
    up = blob.upper()
    for k in sim_keys:
        if k and k.upper() in up:
            return True
    return False


def generate_uac_questions(enriched_jira: dict, similar_jiras: list) -> list[dict]:
    """
    Up to 5 non-generic UAC clarification questions grounded in entities/outputs/etc.
    """
    if not isinstance(enriched_jira, dict):
        enriched_jira = {}
    if not isinstance(similar_jiras, list):
        similar_jiras = []

    anchors = _collect_verbatim_anchors(enriched_jira)
    sim_keys = _similar_keys(similar_jiras)
    missing = enriched_jira.get("missing_info")
    if not isinstance(missing, list):
        missing = []

    outs: list[dict] = []
    jk = str(enriched_jira.get("jira_key") or "").strip()

    if not anchors and not sim_keys and not missing:
        return []

    ents = [str(x) for x in (enriched_jira.get("dita_entities") or []) if str(x).strip()]
    outs_raw = [str(x) for x in (enriched_jira.get("affected_outputs") or []) if str(x).strip()]

    # missing_info-driven
    for mi in missing[:3]:
        t = str(mi).strip()
        if not t:
            continue
        rel = next((a for a in anchors if a in t or t.lower().find(a.lower()) >= 0), jk or (anchors[0] if anchors else "scope"))
        q = f"Given {jk + ': ' if jk else ''}{t}, what is the exact acceptance criterion engineering should implement?"
        outs.append(
            {
                "question": q[:500],
                "why_it_matters": "Without this, UAC sign-off can block on ambiguous scope.",
                "who_should_answer": "PM",
                "related_entity": rel[:120],
                "risk_if_unanswered": "Build or QA may optimize for the wrong behavior and rework the release candidate.",
            }
        )

    # Output × entity pairing (cap)
    pairs = 0
    for o in outs_raw[:4]:
        for e in ents[:4]:
            if pairs >= 3:
                break
            if _GENERIC_Q.match(f"expected behavior for {o}"):
                continue
            q = (
                f"For {o}, should {e} behave as visible authored content, conditional-only, "
                f"or metadata-only in final deliverables?"
            )
            outs.append(
                {
                    "question": q[:500],
                    "why_it_matters": "Publishing contracts differ by output; wrong assumption breaks customer PDF/Sites parity.",
                    "who_should_answer": "Tech Writer" if any(x in e.lower() for x in ("gloss", "term", "title", "nav")) else "Dev",
                    "related_entity": e[:120],
                    "risk_if_unanswered": "Verification passes against the wrong rendering contract; escape defects to production.",
                }
            )
            pairs += 1
        if pairs >= 3:
            break

    # Similar-ticket delta
    if sim_keys and jk:
        top = sim_keys[0]
        mo = similar_jiras[0].get("matching_outputs") if similar_jiras and isinstance(similar_jiras[0], dict) else None
        me = similar_jiras[0].get("matching_entities") if similar_jiras and isinstance(similar_jiras[0], dict) else None
        tie = ""
        if isinstance(mo, list) and mo:
            tie = str(mo[0])
        elif isinstance(me, list) and me:
            tie = str(me[0])
        elif outs_raw:
            tie = outs_raw[0]
        elif ents:
            tie = ents[0]
        else:
            tie = "shared output/entity"
        q = f"Does {jk} need to match resolution behavior documented for {top} regarding {tie}?"
        outs.append(
            {
                "question": q[:500],
                "why_it_matters": "Historical ticket context sets precedent for customer expectations.",
                "who_should_answer": "QA",
                "related_entity": tie[:120],
                "risk_if_unanswered": "Regression passes while customer-facing behavior diverges from prior fixes.",
            }
        )

    # Component scope
    comps = [str(c) for c in (enriched_jira.get("components") or []) if str(c).strip()]
    for c in comps[:1]:
        q = f"Which Guides release line and {c} configuration are in scope for acceptance of {jk or 'this issue'}?"
        outs.append(
            {
                "question": q[:500],
                "why_it_matters": "Environment drift invalidates UAC tested on the wrong build matrix.",
                "who_should_answer": "PM",
                "related_entity": c[:120],
                "risk_if_unanswered": "Sign-off on an unreproducible configuration; reopen escalations post-release.",
            }
        )

    # Filter generic + ungrounded + dedupe
    seen: set[str] = set()
    good: list[dict] = []
    all_anchors = _collect_verbatim_anchors(enriched_jira)
    for row in outs:
        q = row.get("question") or ""
        if _GENERIC_Q.match(q.strip()):
            continue
        if not _question_grounded(q, all_anchors, sim_keys):
            if not any(m and m in q for m in missing if isinstance(m, str)):
                continue
        nd = _norm_q(q)
        if nd in seen:
            continue
        seen.add(nd)
        whom = row.get("who_should_answer") or "QA"
        if whom not in _ALLOWED_WHOM:
            whom = "QA"
        row["who_should_answer"] = whom
        good.append(row)
        if len(good) >= 5:
            break

    return good[:5]
