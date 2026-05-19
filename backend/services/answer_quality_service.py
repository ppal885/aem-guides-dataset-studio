"""Heuristic anti-generic answer scoring for Jira-grounded QA narratives (e.g. UAC drafts)."""

from __future__ import annotations

import re
from typing import Any

_GENERIC_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\btest everything\b",
        r"\btest regression\b",
        r"\bvalidate thoroughly\b",
        r"\bvalidate functionality\b",
        r"\bverify ui\b",
        r"\btest positive and negative scenarios\b",
        r"\bgeneral regression\b",
        r"\bit depends\b",
        r"\bas appropriate\b",
        r"\bwork with your team\b",
        r"\bfollow best practices\b",
        r"\bensure quality\b",
        r"\bmakes? sure that everything\b",
        r"\bcoverage should be comprehensive\b",
        r"\bn?eeds? more information\b",
        r"\bwithout more detail\b",
        r"\bcannot determine\b",
        r"\bcould not find\b(?!\s*\(similar:)",
        r"\bTBD\b",
        r"\bto be decided\b",
        r"\bhigh-level(ly)?\b",
        r"\bgeneric(?:ly)?\s+test",
        r"\ball scenarios\b",
    )
)

_TEST_LAYER_MARKERS: tuple[str, ...] = (
    "behave",
    "selenium",
    "e2e",
    "api test",
    "integration test",
    "ui automation",
    "publishing",
    "output preset",
    "native pdf",
    "dita ot",
    "regression suite",
    "smoke",
)

_DITA_AEM_MARKERS: tuple[str, ...] = (
    "dita",
    "ditamap",
    "map ",
    "topicref",
    "conref",
    "keyref",
    "bookmap",
    "aem guides",
    "experience manager guides",
    "oxygen",
    "baseline",
)

_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9_]{1,10}-\d+\b")


def _lower(s: str) -> str:
    return (s or "").strip().lower()


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _normalize_current_jira(current_jira: dict[str, Any] | None) -> dict[str, Any]:
    cj = dict(current_jira or {})
    missing = _as_list(cj.get("missing_info")) or _as_list(cj.get("missing_info_flags"))
    return {
        "jira_key": _as_str(cj.get("jira_key")),
        "summary": _as_str(cj.get("summary")),
        "description": _as_str(cj.get("description")),
        "domain": _as_str(cj.get("domain")) or "unknown",
        "sub_domain": _as_str(cj.get("sub_domain")),
        "labels": _as_list(cj.get("labels")),
        "components": _as_list(cj.get("components")),
        "customer_names": _as_list(cj.get("customer_names")),
        "affected_outputs": _as_list(cj.get("affected_outputs")),
        "affected_features": _as_list(cj.get("affected_features")),
        "dita_entities": _as_list(cj.get("dita_entities")),
        "missing_info": missing,
        "expected_behavior": _as_str(cj.get("expected_behavior")),
        "actual_behavior": _as_str(cj.get("actual_behavior")),
    }


def _normalize_similar(jiras: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in jiras or []:
        if not isinstance(raw, dict):
            continue
        rk = _as_str(raw.get("jira_key"))
        title = _as_str(raw.get("title"))
        ex = _as_str(raw.get("document_excerpt") or raw.get("chunk_excerpt") or raw.get("document") or "")
        out.append({"jira_key": rk, "title": title, "excerpt": ex[:1200]})
    return out


def _generic_phrases_found(text: str) -> list[str]:
    found: list[str] = []
    for pat in _GENERIC_PATTERNS:
        if pat.search(text):
            found.append(pat.pattern)
    return found


def generic_phrase_patterns_in_text(text: str) -> list[str]:
    """Regex pattern strings for generic-QA phrases detected in ``text`` (same detector as scoring)."""
    return list(_generic_phrases_found(text or ""))


def generic_phrases_removed_between(before: str, after: str) -> list[str]:
    """Pattern strings that matched ``before`` but no longer match ``after`` (e.g. critic or gate trimmed them)."""
    b = set(generic_phrase_patterns_in_text(before))
    if not b:
        return []
    a = set(generic_phrase_patterns_in_text(after))
    return sorted(b - a)


def _repetition_penalty(text: str) -> tuple[int, list[str]]:
    lines = [re.sub(r"\s+", " ", ln.strip().lower()) for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return 0, []
    seen: dict[str, int] = {}
    for ln in lines:
        if len(ln) < 24:
            continue
        seen[ln] = seen.get(ln, 0) + 1
    dups = [ln for ln, c in seen.items() if c > 1]
    pen = min(18, 4 * sum(c - 1 for c in seen.values() if c > 1))
    notes: list[str] = []
    for t in dups[:8]:
        n = seen[t]
        snippet = (t[:100] + "…") if len(t) > 100 else t
        notes.append(f"Repeated line ({n}×): {snippet}")
    return pen, notes[:5]


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z][a-z0-9]{2,}", _lower(s)) if len(t) > 3}


def _overlap_score(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def score_answer_specificity(
    answer: str,
    current_jira: dict[str, Any],
    similar_jiras: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Score how specific / grounded an answer is w.r.t. current + similar Jiras.
    Returns score 0–100, phrase hits, missing dimensions, and accept|rewrite|reject.
    """
    text = answer or ""
    low = _lower(text)
    cj = _normalize_current_jira(current_jira)
    sims = _normalize_similar(similar_jiras)

    generic_hits = _generic_phrases_found(text)
    missing: list[str] = []

    base = 58

    # Penalties (additive to "missing" narrative; subtract from base via pen_*)
    pen = 0

    gmult = min(22, 4 * len(generic_hits))
    pen += gmult
    if generic_hits:
        missing.append("Answer uses generic QA phrasing; prefer concrete artifacts, keys, and outputs from evidence.")

    rpen, rnotes = _repetition_penalty(text)
    pen += rpen
    missing.extend(rnotes[:3])

    jk = cj["jira_key"]
    keys_in_answer = _JIRA_KEY_RE.findall(text)
    if jk:
        jk_low = jk.lower()
        if jk_low not in low and not any(k.lower() == jk_low for k in keys_in_answer):
            pen += 14
            missing.append(f"Answer should mention Jira key {jk} (or cite similar keys from evidence).")
    elif keys_in_answer:
        base += 4

    dom = cj["domain"]
    if dom and dom != "unknown":
        if dom.lower() not in low and (not cj["sub_domain"] or cj["sub_domain"].lower() not in low):
            pen += 8
            missing.append("Answer should reflect domain / sub-domain from current Jira when present.")

    entities = [e for e in cj["dita_entities"] if len(e) > 2]
    ent_hit = False
    for e in entities[:40]:
        if e.lower() in low:
            ent_hit = True
            break
    if entities and not ent_hit:
        pen += 10
        missing.append("Answer should name at least one DITA/AEM entity from current evidence (or cite insufficient evidence explicitly).")

    outputs = [o for o in cj["affected_outputs"] if len(o) > 2]
    out_hit = any(o.lower() in low for o in outputs[:30])
    if outputs and not out_hit:
        pen += 10
        missing.append("Answer should reference affected output types from current Jira (verbatim where possible).")

    cust = cj["customer_names"]
    comps = cj["components"]
    has_anchor = bool(cust or comps)
    cust_hit = any(n.lower() in low for n in cust[:15] if len(n) > 1)
    comp_hit = any(n.lower() in low for n in comps[:25] if len(n) > 1)
    lbl_hit = any(l.lower() in low for l in cj["labels"][:30] if len(l) > 2)
    if has_anchor and not (cust_hit or comp_hit):
        pen += 7
        missing.append("Answer should mention a customer or component from current Jira when evidence lists them.")
    elif lbl_hit or comp_hit or cust_hit:
        base += 6

    sim_keys = [s["jira_key"] for s in sims if s.get("jira_key")]
    sim_text_blob = " ".join(_lower(s["title"] + " " + s["excerpt"]) for s in sims)
    sim_tokens = _tokens(sim_text_blob)
    ans_tokens = _tokens(text)

    used_similar_key = False
    for sk in sim_keys[:12]:
        if sk and sk.lower() in low:
            used_similar_key = True
            break
    sim_overlap = _overlap_score(ans_tokens, sim_tokens) if sim_tokens else 0.0
    if sims and not used_similar_key and sim_overlap < 0.04:
        pen += 12
        missing.append("Answer should cite similar Jira key(s) or reuse distinctive terms from similar ticket excerpts when retrieval is non-empty.")

    # Rewards
    bonus = 0
    for m in _DITA_AEM_MARKERS:
        if m in low:
            bonus += 2
    bonus = min(10, bonus)

    tl_hits = sum(1 for m in _TEST_LAYER_MARKERS if m in low)
    if tl_hits:
        bonus += min(8, 2 * tl_hits)

    if _overlap_score(ans_tokens, _tokens(cj["summary"] + " " + cj["description"][:2000])) >= 0.06:
        bonus += 7

    if outputs and out_hit:
        bonus += 6
    if entities and ent_hit:
        bonus += 5
    if used_similar_key or (sims and sim_overlap >= 0.06):
        bonus += min(12, 4 + int(sim_overlap * 40))

    miss_flags = cj["missing_info"]
    if miss_flags:
        if "?" in text and any(m[:20].lower() in low for m in miss_flags if len(m) > 4):
            bonus += 6
        else:
            pen += 4
            missing.append("Call out concrete missing clarifications tied to missing_info flags from Jira.")

    score = int(round(max(0, min(100, base - pen + bonus))))

    if score >= 70:
        rec = "accept"
    elif score >= 48:
        rec = "rewrite"
    else:
        rec = "reject"

    return {
        "score": score,
        "generic_phrases_found": generic_hits[:25],
        "missing_specificity": missing[:20],
        "recommendation": rec,
    }
