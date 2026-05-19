"""Jira issue enrichment: domain, DITA entities, customers, QA signals (pre-embedding)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.aem_guides_taxonomy import (
    get_customer_label_exclude_patterns,
    get_domain_specs,
    get_entity_patterns,
    get_feature_signals,
    get_output_signals,
)
from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_client import extract_description_from_issue
from app.services.jira_qa_automation_rubric import score_automation_fit

# --- Dynamic customer detection (custom fields, labels, text hints; optional DB aliases) ---

CUSTOMER_LABEL_EXCLUDE_PATTERNS: frozenset[str] = get_customer_label_exclude_patterns()

_PLAIN_LABEL_STOPWORDS: frozenset[str] = frozenset(
    {
        "noise",
        "misc",
        "unknown",
        "general",
        "various",
        "other",
        "na",
        "n_a",
        "tbd",
        "wip",
        "test",
        "testing",
    }
)

_TEXT_TOKEN_STOPWORDS: frozenset[str] = frozenset(
    {
        "pdf",
        "uuid",
        "aem",
        "api",
        "xml",
        "dita",
        "html",
        "http",
        "https",
        "native",
        "metadata",
        "glossary",
        "preview",
        "output",
        "publish",
        "error",
        "steps",
        "step",
        "note",
        "notes",
        "issue",
        "ticket",
        "jira",
        "guides",
        "bug",
        "task",
        "story",
        "login",
        "actual",
        "expected",
        "open",
        "major",
        "minor",
        "critical",
        "from",
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "when",
        "team",
        "using",
        "into",
        "escalation",
        "router",
    }
)

_CANONICAL_BRAND_MAP: dict[str, str] = {
    "pwc": "PwC",
    "ibm": "IBM",
    "hp": "HP",
    "sap": "SAP",
    "aws": "AWS",
    "bbc": "BBC",
    "ge": "GE",
    "lg": "LG",
}

_FIELDS_SKIP_FOR_CUSTOMER: frozenset[str] = frozenset(
    {
        "summary",
        "description",
        "labels",
        "components",
        "issuetype",
        "status",
        "priority",
        "resolution",
        "project",
        "reporter",
        "assignee",
        "creator",
        "comment",
        "attachment",
        "subtasks",
        "issuelinks",
        "worklog",
        "watches",
        "votes",
        "updated",
        "created",
        "duedate",
        "lastviewed",
        "environment",
        "fixversions",
        "versions",
        "parent",
        "security",
        "flagged",
    }
)

_STANDARD_CUSTOMER_FIELD_KEYS_NORM: frozenset[str] = frozenset(
    {
        "customer",
        "customername",
        "customer_name",
        "account",
        "organization",
        "organisation",
        "reportedbycustomer",
        "impactedcustomer",
        "requestparticipants",
    }
)

_LABEL_PREFIX_RE = re.compile(r"^(customer|cust|account|org|client)\s*[:#=_-]\s*(.+)$", re.I)
_TEXT_CUSTOMER_HINT_RE = re.compile(
    r"(?:customer|client|account|org|organization|organisation|escalation|reported\s+by|impacted\s+customer)\b.{0,40}$",
    re.I,
)

_customer_alias_cache: dict[str, str] | None = None


def _normalize_jira_field_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _field_key_suggests_customer(key: str) -> bool:
    nk = _normalize_jira_field_key(key)
    if nk in _STANDARD_CUSTOMER_FIELD_KEYS_NORM:
        return True
    hints = (
        "customer",
        "account",
        "organization",
        "organisation",
        "reportedby",
        "impactedcustomer",
        "impacted",
        "participant",
        "company",
        "clientname",
        "companyname",
        "orgname",
        "enduser",
        "customeraccount",
    )
    return any(h in nk for h in hints)


def _flatten_jira_field_value(val: Any, max_depth: int = 6) -> list[str]:
    if max_depth < 0:
        return []
    if val is None:
        return []
    if isinstance(val, str):
        t = val.strip()
        return [t] if t and len(t) <= 500 else []
    if isinstance(val, (bool,)):
        return []
    if isinstance(val, (int, float)):
        s = str(val)
        return [s] if s else []
    if isinstance(val, list):
        out: list[str] = []
        for x in val[:80]:
            out.extend(_flatten_jira_field_value(x, max_depth - 1))
        return out
    if isinstance(val, dict):
        preferred_keys = ("displayName", "displayname", "name", "value", "label", "text", "emailAddress")
        out = []
        for kk in preferred_keys:
            if kk in val:
                out.extend(_flatten_jira_field_value(val[kk], max_depth - 1))
        if out:
            return out
        skip_subkeys = frozenset(
            {"self", "id", "avatarUrls", "icon", "accountId", "key", "href", "size", "mimeType"}
        )
        for kk, vv in val.items():
            if str(kk) in skip_subkeys:
                continue
            out.extend(_flatten_jira_field_value(vv, max_depth - 1))
        return out
    return []


def _label_norm_tokens(label: str) -> list[str]:
    n = label.lower().replace("-", "_")
    parts = [p for p in re.split(r"[_\s:]+", n) if p]
    return parts if parts else [n]


def _label_excluded(label: str) -> bool:
    collapsed = label.lower().replace("-", "_").replace(" ", "_")
    parts = _label_norm_tokens(label)
    for pat in CUSTOMER_LABEL_EXCLUDE_PATTERNS:
        if pat == collapsed:
            return True
        if pat in parts:
            return True
        if f"_{pat}_" in f"_{collapsed}_":
            return True
    return False


def _token_excluded_low(word_lower: str) -> bool:
    if word_lower in CUSTOMER_LABEL_EXCLUDE_PATTERNS:
        return True
    if word_lower in _TEXT_TOKEN_STOPWORDS:
        return True
    return False


def _plain_label_valid(label: str) -> bool:
    s = label.strip()
    if len(s) < 2 or len(s) > 80:
        return False
    collapsed = s.lower().replace("-", "_").replace(" ", "_")
    if collapsed in _PLAIN_LABEL_STOPWORDS:
        return False
    if _label_excluded(s):
        return False
    if re.fullmatch(r"\d+", s):
        return False
    return True


def _normalize_customer_display(raw: str, alias_map: dict[str, str]) -> str:
    s = raw.strip().strip(",.;:")
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    if len(s) > 120:
        s = s[:120].rstrip()
    lk = s.lower()
    lk_underscore = lk.replace(" ", "_")
    if lk in alias_map:
        return alias_map[lk]
    if lk_underscore in alias_map:
        return alias_map[lk_underscore]
    simple = re.sub(r"[^a-z0-9]", "", lk)
    if simple in alias_map:
        return alias_map[simple]
    words = s.split()
    out_words: list[str] = []
    for w in words:
        wl = w.lower()
        if wl in _CANONICAL_BRAND_MAP:
            out_words.append(_CANONICAL_BRAND_MAP[wl])
            continue
        if not w:
            continue
        if len(w) >= 2 and w[0].isupper() and w[1:].islower():
            out_words.append(w)
            continue
        if w.isupper() and 2 <= len(w) <= 5:
            out_words.append(w)
            continue
        out_words.append(w[:1].upper() + w[1:].lower() if len(w) > 1 else w.upper())
    result = " ".join(out_words).strip()
    rl = result.lower().replace(" ", "_")
    if rl in CUSTOMER_LABEL_EXCLUDE_PATTERNS:
        return ""
    if _token_excluded_low(result.lower()):
        return ""
    return result


def _alias_matches_raw_customer(raw: str, alias_map: dict[str, str]) -> bool:
    lk = (raw or "").strip().lower()
    if not lk:
        return False
    lk_underscore = lk.replace(" ", "_")
    simple = re.sub(r"[^a-z0-9]", "", lk)
    return lk in alias_map or lk_underscore in alias_map or simple in alias_map or lk in _CANONICAL_BRAND_MAP


def _text_context_allows_customer(blob: str, start: int, raw: str, alias_map: dict[str, str]) -> bool:
    if _alias_matches_raw_customer(raw, alias_map):
        return True
    prefix = blob[max(0, start - 80) : start]
    return bool(_TEXT_CUSTOMER_HINT_RE.search(prefix))


def _add_customer_candidate(
    raw: str,
    *,
    alias_map: dict[str, str],
    candidates: dict[str, str],
    debug_list: list[str],
    debug_entry: str,
) -> None:
    chunk = re.split(r"[,;|/]\s*", raw)
    de_trunc = debug_entry[:200]
    for piece in chunk:
        p = piece.strip()
        if len(p) < 2:
            continue
        norm = _normalize_customer_display(p, alias_map)
        if not norm:
            continue
        candidates[norm.lower()] = norm
        if de_trunc not in debug_list:
            debug_list.append(de_trunc)


def _get_customer_alias_map() -> dict[str, str]:
    global _customer_alias_cache
    if _customer_alias_cache is not None:
        return _customer_alias_cache
    try:
        from app.db.jira_enrichment_repository import load_customer_aliases
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            _customer_alias_cache = load_customer_aliases(db)
        finally:
            db.close()
    except Exception:
        _customer_alias_cache = {}
    return _customer_alias_cache


def detect_customers_dynamic_with_debug(
    jira: dict[str, Any],
    *,
    alias_map: dict[str, str] | None = None,
) -> tuple[list[str], dict[str, list[str]]]:
    """
    Discover customer names from Jira issue dict (fields, labels, summary/description hints).
    Returns sorted unique display names and a debug dict suitable for persistence.
    """
    amap = dict(alias_map) if alias_map is not None else _get_customer_alias_map()
    fields = jira.get("fields") if isinstance(jira.get("fields"), dict) else {}

    debug: dict[str, list[str]] = {
        "from_custom_fields": [],
        "from_labels": [],
        "excluded_labels": [],
        "final_customers": [],
    }
    candidates: dict[str, str] = {}

    for fk, fv in fields.items():
        fks = str(fk)
        if fks in _FIELDS_SKIP_FOR_CUSTOMER:
            continue
        if not _field_key_suggests_customer(fks):
            continue
        for s in _flatten_jira_field_value(fv):
            _add_customer_candidate(
                s,
                alias_map=amap,
                candidates=candidates,
                debug_list=debug["from_custom_fields"],
                debug_entry=f"{fk}:{s[:120]}",
            )

    raw_labels = fields.get("labels") or []
    labels_list: list[str] = []
    if isinstance(raw_labels, list):
        labels_list = [str(x).strip() for x in raw_labels if x is not None and str(x).strip()]

    for lb in labels_list:
        if _label_excluded(lb):
            debug["excluded_labels"].append(lb[:200])
            continue
        m = _LABEL_PREFIX_RE.match(lb.strip())
        if m:
            inner = m.group(2).strip()
            if inner and not _label_excluded(inner):
                _add_customer_candidate(
                    inner,
                    alias_map=amap,
                    candidates=candidates,
                    debug_list=debug["from_labels"],
                    debug_entry=f"label_prefix:{lb[:200]}",
                )
            continue
        if not _plain_label_valid(lb):
            debug["excluded_labels"].append(lb[:200])
            continue
        _add_customer_candidate(
            lb,
            alias_map=amap,
            candidates=candidates,
            debug_list=debug["from_labels"],
            debug_entry=f"label_plain:{lb[:200]}",
        )

    summary = str(fields.get("summary") or "")
    desc_plain = extract_description_from_issue(jira)
    blob = "\n".join(x for x in (summary, desc_plain) if x)

    for m in re.finditer(
        r"(?is)(?:customer|account|client|organization|organisation)\s*[:#]\s*([^\n,;]{2,80})",
        blob,
    ):
        _add_customer_candidate(
            m.group(1).strip(),
            alias_map=amap,
            candidates=candidates,
            debug_list=debug["from_custom_fields"],
            debug_entry=f"text_key:{m.group(1).strip()[:120]}",
        )

    for m in re.finditer(r"\b([A-Z][a-z]{2,})\b", blob):
        w = m.group(1)
        wl = w.lower()
        if _token_excluded_low(wl):
            continue
        if not _text_context_allows_customer(blob, m.start(), w, amap):
            continue
        norm = _normalize_customer_display(w, amap)
        if not norm:
            continue
        candidates[norm.lower()] = norm
        entry = f"text_cap:{w}"
        if entry not in debug["from_labels"]:
            debug["from_labels"].append(entry[:200])

    for m in re.finditer(r"\b([A-Z]{2,5})\b", blob):
        w = m.group(1)
        wl = w.lower()
        if len(wl) < 2 or _token_excluded_low(wl):
            continue
        if wl in _TEXT_TOKEN_STOPWORDS:
            continue
        if not _text_context_allows_customer(blob, m.start(), w, amap):
            continue
        norm = _normalize_customer_display(w, amap)
        if not norm:
            continue
        candidates[norm.lower()] = norm
        entry = f"text_acr:{w}"
        if entry not in debug["from_labels"]:
            debug["from_labels"].append(entry[:200])

    for m in re.finditer(r"\b([a-z]{1,3}[A-Z][A-Za-z]*)\b", blob):
        w = m.group(1)
        wl = w.lower()
        if _token_excluded_low(wl):
            continue
        if not _text_context_allows_customer(blob, m.start(), w, amap):
            continue
        norm = _normalize_customer_display(w, amap)
        if not norm:
            continue
        candidates[norm.lower()] = norm
        entry = f"text_mixed:{w}"
        if entry not in debug["from_labels"]:
            debug["from_labels"].append(entry[:200])

    final_sorted = sorted(candidates.values(), key=lambda x: x.lower())
    debug["final_customers"] = list(final_sorted)
    return final_sorted, debug


def detect_customers_dynamic(jira: dict[str, Any]) -> list[str]:
    names, _ = detect_customers_dynamic_with_debug(jira)
    return names


def _norm_labels(labels: list[str]) -> list[str]:
    out: list[str] = []
    for x in labels:
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def classify_domain(text: str, labels: list[str]) -> dict[str, Any]:
    """
    Score AEM Guides–oriented domains from body + labels.
    Returns: domain, sub_domain (runner-up label), scores (optional diagnostics).
    """
    blob = f"{text}\n{' '.join(_norm_labels(labels))}".lower()
    scores: dict[str, float] = {}
    hits: dict[str, list[str]] = {}

    for dom, kws, weight in get_domain_specs():
        matched: list[str] = []
        s = 0.0
        for kw in kws:
            if kw.lower() in blob:
                s += weight
                matched.append(kw)
        if s > 0:
            scores[dom] = s
            hits[dom] = matched

    if not scores:
        return {"domain": "unknown", "sub_domain": "", "scores": {}, "hits": {}}

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_dom, best_score = ordered[0]
    sub = ""
    if len(ordered) > 1:
        second_dom, second_score = ordered[1]
        if second_score >= 0.35 * best_score and second_dom != best_dom:
            sub = second_dom

    return {"domain": best_dom, "sub_domain": sub, "scores": scores, "hits": hits}


def extract_dita_entities(text: str) -> list[str]:
    """Rule-based DITA / product entity mentions (canonical labels)."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for label, pat in get_entity_patterns():
        if pat.search(text) and label not in seen:
            seen.add(label)
            out.append(label)
    return out


def detect_customers(text: str, labels: list[str]) -> list[str]:
    """
    Back-compat helper: treat ``text`` as summary-like content plus ``labels``.
    Prefer ``detect_customers_dynamic`` with a full Jira payload when available.
    """
    jira = {
        "fields": {
            "summary": text or "",
            "description": "",
            "labels": _norm_labels(labels),
        }
    }
    return detect_customers_dynamic(jira)


def extract_expected_actual(text: str) -> dict[str, str]:
    """Pull expected vs actual behavior from description text.

    Tries explicit 'Expected:'/'Actual:' section headers first; falls back to
    sentence-level detection of failure-mode and expected-behavior language so
    that narrative Jira descriptions (no explicit headers) are not silently lost.
    """
    t = text or ""
    expected = ""
    actual = ""

    # --- Pass 1: explicit section headers ---
    em = re.search(
        r"(?is)(?:expected|expect)\s*(?:behavior|result)?\s*[:.\s]*(.+?)(?=(?:\n\s*(?:actual|current|steps))|(?:\Z))",
        t,
    )
    if em:
        expected = em.group(1).strip()[:8000]
    am = re.search(
        r"(?is)(?:actual|current)\s*(?:behavior|result)?\s*[:.\s]*(.+?)(?=(?:\n\s*(?:expected|steps))|(?:\Z))",
        t,
    )
    if am:
        actual = am.group(1).strip()[:8000]

    # --- Pass 2: narrative fallback when headers are absent ---
    if not actual:
        failure_sentences: list[str] = []
        for m in re.finditer(
            r"[^.!?\n]{10,}(?:incorrectly|unexpectedly|fails?\s+to|does\s+not|doesn['']t"
            r"|is\s+not\s+(?:working|showing|rendering|displayed)"
            r"|not\s+(?:working|showing|rendering|correct)"
            r"|both\s+the\s+\w+\s+and|displays?\s+both"
            r"|wrong(?:ly)?|invalid|broken|missing)[^.!?\n]{0,200}[.!?]",
            t,
            re.I,
        ):
            s = m.group(0).strip()
            if len(s) > 20 and s not in failure_sentences:
                failure_sentences.append(s)
            if len(failure_sentences) >= 5:
                break
        if failure_sentences:
            actual = " ".join(failure_sentences)[:8000]

    if not expected:
        expected_sentences: list[str] = []
        for m in re.finditer(
            r"[^.!?\n]{10,}(?:should\s+(?:only\s+)?(?:display|show|render|be|work|contain)"
            r"|expected\s+to|in\s+contrast|as\s+intended|works?\s+(?:correctly|as\s+expected)"
            r"|only\s+(?:display|show|render)|correct(?:ly)?\s+(?:display|show|render))[^.!?\n]{0,200}[.!?]",
            t,
            re.I,
        ):
            s = m.group(0).strip()
            if len(s) > 20 and s not in expected_sentences:
                expected_sentences.append(s)
            if len(expected_sentences) >= 5:
                break
        if expected_sentences:
            expected = " ".join(expected_sentences)[:8000]

    return {"expected_behavior": expected, "actual_behavior": actual}


def _symptoms_from_text(text: str, limit: int = 8) -> list[str]:
    t = text or ""
    out: list[str] = []
    for pat in (
        r"(?m)^.{0,240}?(?:error|exception|failed|failure|unable to|cannot|does not|doesn't)\b.{0,120}$",
        r"(?i)\b(?:http\s*\d{3}|status\s*code\s*\d+)\b.{0,80}",
    ):
        for m in re.finditer(pat, t):
            s = m.group(0).strip()
            if len(s) > 12 and s not in out:
                out.append(s[:400])
            if len(out) >= limit:
                return out
    return out[:limit]


def _qa_risk_tags(text: str, labels: list[str]) -> list[str]:
    blob = f"{text}\n{' '.join(labels)}".lower()
    tags: list[str] = []
    checks = (
        ("regression", "regression"),
        ("blocker", "blocker"),
        ("critical", "critical"),
        ("production", "production"),
        ("customer-facing", "customer"),
        ("data-loss", "data loss"),
        ("security", "security"),
    )
    for tag, needle in checks:
        if needle in blob and tag not in tags:
            tags.append(tag)
    return tags


def _affected_outputs(text: str) -> list[str]:
    t = (text or "").lower()
    out: list[str] = []
    for label, kws in get_output_signals():
        if any(k in t for k in kws) and label not in out:
            out.append(label)
    return out


def _affected_features(text: str) -> list[str]:
    t = (text or "").lower()
    out: list[str] = []
    for label, kws in get_feature_signals():
        if any(k in t for k in kws) and label not in out:
            out.append(label)
    return out


def _missing_info_heuristics(description: str, exp: str, act: str) -> list[str]:
    miss: list[str] = []
    d = (description or "").strip()
    if len(d) < 20:
        miss.append("short_or_empty_description")
    if not exp:
        miss.append("no_expected_section")
    if not act:
        miss.append("no_actual_section")
    if not re.search(r"(?:step\s*\d|steps?\s+to\s+reproduce|repro\s*steps)", d, re.I):
        miss.append("no_repro_steps_detected")
    return miss


def enrich_jira(jira: dict[str, Any]) -> JiraEnrichedDocument:
    """
    Build structured enrichment from a Jira REST issue dict (`{ "fields": {...}, "key": ... }`).
    Uses summary, description (plain), labels, components, type, status, priority only.
    """
    fields = jira.get("fields") if isinstance(jira.get("fields"), dict) else {}
    jira_key = str(jira.get("key") or fields.get("key") or "").strip()

    summary = str(fields.get("summary") or "").strip()
    desc_plain = extract_description_from_issue(jira)

    it = fields.get("issuetype") or {}
    issue_type = str(it.get("name") or "") if isinstance(it, dict) else ""
    st = fields.get("status") or {}
    status = str(st.get("name") or "") if isinstance(st, dict) else ""
    pr = fields.get("priority") or {}
    priority = str(pr.get("name") or "") if isinstance(pr, dict) else ""

    raw_labels = fields.get("labels") or []
    labels: list[str] = []
    if isinstance(raw_labels, list):
        labels = [str(x).strip() for x in raw_labels if x]
    comps_raw = fields.get("components") or []
    components: list[str] = []
    if isinstance(comps_raw, list):
        for c in comps_raw:
            if isinstance(c, dict) and c.get("name"):
                components.append(str(c["name"]).strip())

    blob = "\n".join([summary, desc_plain, " ".join(labels), " ".join(components)])

    cls = classify_domain(blob, labels)
    domain = str(cls.get("domain") or "unknown")
    sub_domain = str(cls.get("sub_domain") or "")

    customers, cust_debug = detect_customers_dynamic_with_debug(jira)
    entities = extract_dita_entities(blob)
    ea = extract_expected_actual(desc_plain)
    rubric = score_automation_fit(blob)
    automation_fit = f"{rubric.fit_label} ({rubric.score_0_10})"

    outputs = _affected_outputs(blob)
    feats = _affected_features(blob)

    symptoms = _symptoms_from_text(desc_plain or summary)
    risks = _qa_risk_tags(blob, labels)
    missing = _missing_info_heuristics(desc_plain, ea["expected_behavior"], ea["actual_behavior"])
    enrichment_debug = {
        "domain_classification": {
            "domain": domain,
            "sub_domain": sub_domain,
            "scores": cls.get("scores") or {},
            "hits": cls.get("hits") or {},
        },
        "customer_detection": cust_debug,
        "detected_outputs": outputs,
        "detected_features": feats,
        "detected_entities": entities,
        "missing_info": missing,
        "qa_risk_tags": risks,
    }

    raw_text = "\n\n".join(
        x for x in (f"Key: {jira_key}", f"Summary: {summary}", f"Description:\n{desc_plain}") if x.strip()
    )[:50000]

    return JiraEnrichedDocument(
        jira_key=jira_key,
        summary=summary[:4000],
        description=desc_plain[:50000],
        issue_type=issue_type[:200],
        status=status[:200],
        priority=priority[:200],
        labels=labels[:100],
        components=components[:100],
        customer_names=customers,
        customer_detection_debug=cust_debug,
        domain=domain,
        sub_domain=sub_domain,
        affected_outputs=outputs[:30],
        affected_features=feats[:40],
        dita_entities=entities[:60],
        symptoms=symptoms,
        expected_behavior=ea["expected_behavior"][:8000],
        actual_behavior=ea["actual_behavior"][:8000],
        qa_risk_tags=risks,
        automation_fit=automation_fit[:120],
        missing_info=missing,
        raw_text=raw_text,
        enrichment_debug=enrichment_debug,
    )


def enrichment_metadata_json(enriched: JiraEnrichedDocument, max_chars: int = 3500) -> str:
    """Single Chroma-safe JSON string (truncated) for full enrichment profile."""
    raw = json.dumps(enriched.model_dump(), ensure_ascii=False)
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 20] + "\n...truncated..."


def enrichment_embed_prefix(enriched: JiraEnrichedDocument, max_len: int = 420) -> str:
    """Short plain-text prefix to prepend before chunk body for embedding."""
    parts = [
        f"domain={enriched.domain}",
        f"sub_domain={enriched.sub_domain}" if enriched.sub_domain else "",
        f"customers={','.join(enriched.customer_names)}" if enriched.customer_names else "",
        f"entities={','.join(enriched.dita_entities[:12])}" if enriched.dita_entities else "",
        f"outputs={','.join(enriched.affected_outputs[:6])}" if enriched.affected_outputs else "",
        f"risks={','.join(enriched.qa_risk_tags)}" if enriched.qa_risk_tags else "",
    ]
    line = " | ".join(p for p in parts if p)
    if len(line) > max_len:
        return line[: max_len - 3] + "..."
    return line
