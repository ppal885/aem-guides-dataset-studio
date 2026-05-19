"""
Customer Intelligence Engine for Jira QA Copilot.

Customer identity is inferred from Jira labels (e.g. swift, ABS, Cisco), optional custom fields,
and description heuristics. Enriched metadata is stored on Chroma chunks for retrieval and reporting.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from typing import Any

from app.services.jira_qa_chunking_service import extract_customer_from_fields
from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, get_documents_where


def _parse_json_list(raw: str) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _load_label_alias_map() -> dict[str, str]:
    """
    Map lowercase label token -> canonical customer display name.
    Override with env ``JIRA_QA_CUSTOMER_LABEL_ALIASES`` as JSON object, e.g.
    ``{"corp_acme":"Corp Acme"}`` (keys lowercased at lookup time).
    """
    raw = (os.getenv("JIRA_QA_CUSTOMER_LABEL_ALIASES") or "").strip()
    if raw:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return {str(k).strip().lower(): str(v).strip() for k, v in obj.items() if k and v}
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "swift": "Swift",
        "abs": "ABS",
        "topcon": "Topcon",
        "cisco": "Cisco",
        "internal": "Internal",
    }


_LABEL_ALIASES = _load_label_alias_map()

_ESCALATION_LABELS = frozenset(
    x.strip().lower()
    for x in (os.getenv("JIRA_QA_ESCALATION_LABELS") or "customer-escalation,escalation,p1-escalation,sev-1").split(",")
    if x.strip()
)


def detect_customer_labels_from_issue(labels: list[str]) -> list[str]:
    """Return ordered unique canonical customer names detected from label strings."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in labels or []:
        token = str(raw).strip().lower()
        if not token or token in _ESCALATION_LABELS:
            continue
        if token == "customer-escalation":
            continue
        display = _LABEL_ALIASES.get(token)
        if not display:
            continue
        key = display.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(display)
    return out


def infer_escalation(labels: list[str], summary: str = "", description: str = "") -> bool:
    blob = " ".join(str(x).lower() for x in labels) + " " + (summary or "").lower() + " " + (description or "").lower()
    for marker in _ESCALATION_LABELS:
        if marker and marker in blob:
            return True
    if re.search(r"\b(sev[- ]?1|p0|blocker)\b", blob):
        return True
    return False


def infer_customer_type(labels: list[str], issue_type: str = "", priority: str = "") -> str:
    low = {str(x).strip().lower() for x in labels if x}
    if "internal" in low:
        return "internal"
    if detect_customer_labels_from_issue(list(labels)):
        # External named customers default to enterprise in this product context
        return "enterprise"
    it = (issue_type or "").lower()
    pr = (priority or "").lower()
    if "bug" in it and ("blocker" in pr or "critical" in pr):
        return "enterprise"
    return "unknown"


def extract_customer_metadata_from_issue(fields: dict[str, Any]) -> dict[str, Any]:
    """
    Build customer-facing metadata for indexing and API payloads.

    Returns JSON-serializable dict including ``customer_escalation`` as bool for APIs;
    Chroma indexing should pass ints for scalar safety where needed.
    """
    labels = fields.get("labels") or []
    if not isinstance(labels, list):
        labels = []
    label_strs = [str(l).strip() for l in labels if str(l).strip()]
    summary = str(fields.get("summary") or "")
    desc = ""
    try:
        from app.services.jira_client import extract_description_from_issue

        desc = extract_description_from_issue({"fields": fields})
    except Exception:
        desc = ""

    field_customer = extract_customer_from_fields(fields)
    from_labels = detect_customer_labels_from_issue(label_strs)
    primary = field_customer.strip() or (from_labels[0] if from_labels else "")
    customer_key = primary.strip().lower().replace(" ", "_")[:120] if primary else ""

    it = fields.get("issuetype") or {}
    issue_type = str(it.get("name") or "") if isinstance(it, dict) else ""
    pr = fields.get("priority") or {}
    priority = str(pr.get("name") or "") if isinstance(pr, dict) else ""

    esc = infer_escalation(label_strs, summary, desc)
    ctype = infer_customer_type(label_strs, issue_type, priority)

    return {
        "customer": primary[:200] if primary else "",
        "customer_key": customer_key,
        "customer_labels": from_labels,
        "customer_type": ctype,
        "customer_escalation": esc,
    }


def customer_index_metadata_for_chunks(fields: dict[str, Any]) -> dict[str, Any]:
    """Flatten for Chroma metadata (str / int only)."""
    meta = extract_customer_metadata_from_issue(fields)
    labels_json = json.dumps(meta.get("customer_labels") or [], ensure_ascii=False)[:4000]
    return {
        "customer": str(meta.get("customer") or "")[:200],
        "customer_key": str(meta.get("customer_key") or "")[:120],
        "customer_labels": labels_json,
        "customer_type": str(meta.get("customer_type") or "unknown")[:40],
        "customer_escalation": 1 if meta.get("customer_escalation") else 0,
    }


def customer_metadata_from_issue_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """
    API-friendly customer metadata from indexed issue chunks (first row with customer signals).
    """
    for c in chunks or []:
        m = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        if not m:
            continue
        cust = str(m.get("customer") or "").strip()
        ck = str(m.get("customer_key") or "").strip()
        if not cust and not ck:
            continue
        esc_raw = m.get("customer_escalation", 0)
        try:
            esc = bool(int(esc_raw))
        except (TypeError, ValueError):
            esc = bool(esc_raw)
        return {
            "customer": cust or (ck.replace("_", " ").title() if ck else ""),
            "customer_type": str(m.get("customer_type") or "unknown")[:40],
            "escalation": esc,
        }
    return {"customer": "", "customer_type": "unknown", "escalation": False}


def issue_labels_components_from_chunks(chunks: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Recover labels/components lists from first chunk carrying metadata."""
    for c in chunks or []:
        m = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        if not m:
            continue
        labels = _parse_json_list(str(m.get("labels") or ""))
        comps = _parse_json_list(str(m.get("components") or ""))
        if labels or comps:
            return labels, comps
    return [], []


def resolve_effective_customer_for_copilot(
    explicit_customer: str | None,
    issue_chunks: list[dict[str, Any]],
) -> str:
    """Prefer UI/API hint; else metadata on indexed issue chunks."""
    ex = (explicit_customer or "").strip()
    if ex:
        return ex
    for c in issue_chunks or []:
        m = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        ck = str(m.get("customer") or "").strip()
        if ck:
            return ck
        alt = str(m.get("customer_key") or "").strip()
        if alt:
            return alt.replace("_", " ").title()
    return ""


def enhance_labels_for_customer_boost(base_labels: list[str], effective_customer: str) -> list[str]:
    """Add normalized tokens so ``_overlap_boost`` can align with indexed label JSON."""
    out = [str(x).strip() for x in (base_labels or []) if str(x).strip()]
    seen = {x.casefold() for x in out}
    ec = (effective_customer or "").strip()
    if ec:
        low = ec.lower()
        if low not in seen:
            out.append(ec)
            seen.add(low)
        for token, display in _LABEL_ALIASES.items():
            if display.casefold() == ec.casefold() and token not in seen:
                out.append(token)
                seen.add(token)
    return out[:40]


class CustomerIntelligenceEngine:
    """
    Aggregate historical signals for one ``customer_key`` (lowercase slug, e.g. ``cisco``).

    Requires chunks indexed with ``customer_key`` (newer index runs). Legacy chunks without
    the field return sparse reports until re-indexed.
    """

    def __init__(self, *, collection: str = CHROMA_COLLECTION_JIRA_QA) -> None:
        self._collection = collection

    def build_intelligence_report(
        self,
        customer: str,
        *,
        recent_related_limit: int = 16,
        fetch_limit: int = 400,
    ) -> dict[str, Any]:
        ck = (customer or "").strip().lower().replace(" ", "_")[:120]
        display = (customer or "").strip() or (ck.replace("_", " ").title() if ck else "")
        if not ck:
            return self._empty_report("")

        rows = get_documents_where(self._collection, {"customer_key": ck}, limit=fetch_limit)
        if not rows:
            # Fallback: try display string stored in customer field (legacy)
            rows = get_documents_where(self._collection, {"customer": display[:200]}, limit=min(120, fetch_limit))

        if not rows:
            return self._empty_report(display or ck)

        return self._aggregate_rows(rows, display_name=display or ck, recent_related_limit=recent_related_limit)

    def _empty_report(self, customer: str) -> dict[str, Any]:
        return {
            "customer": customer or "",
            "historical_patterns": [],
            "repeated_issues": [],
            "high_risk_areas": [],
            "frequently_affected_components": [],
            "common_failure_patterns": [],
            "recent_related_tickets": [],
        }

    def _aggregate_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        display_name: str,
        recent_related_limit: int,
    ) -> dict[str, Any]:
        by_key: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "types": Counter(),
                "components": Counter(),
                "titles": [],
                "snippets": [],
                "updated": "",
            }
        )
        for r in rows:
            m = r.get("metadata") or {}
            jk = str(m.get("jira_key") or "").strip()
            if not jk:
                continue
            ct = str(m.get("chunk_type") or "")
            by_key[jk]["types"][ct] += 1
            doc = (r.get("document") or "")[:400]
            if doc and ct in {"customer_problem", "regression_risks", "full_ticket_summary"}:
                by_key[jk]["snippets"].append(doc[:280])
            comps = _parse_json_list(str(m.get("components") or ""))
            for c in comps:
                by_key[jk]["components"][c.lower()] += 1
            title = str(m.get("title") or "")
            if title and title not in by_key[jk]["titles"]:
                by_key[jk]["titles"].append(title[:240])
            upd = str(m.get("updated_at") or "")
            if upd > (by_key[jk]["updated"] or ""):
                by_key[jk]["updated"] = upd

        # Repeated regression / risk signals (same ticket, multiple risk chunks)
        repeated: list[str] = []
        for jk, data in by_key.items():
            if data["types"].get("regression_risks", 0) >= 2 or (
                data["types"].get("customer_problem", 0) >= 2 and data["types"].get("regression_risks", 0) >= 1
            ):
                t = data["titles"][0] if data["titles"] else jk
                repeated.append(f"{jk}: {t}")

        comp_totals: Counter[str] = Counter()
        for data in by_key.values():
            comp_totals.update(data["components"])

        high_risk_areas = [
            f"{name} ({count} hits)"
            for name, count in comp_totals.most_common(12)
            if count >= 2
        ]

        # Title tokens as lightweight "patterns"
        title_words: Counter[str] = Counter()
        stop = frozenset(
            "the a an and or for of in on at to from with without is are was were be been being it this that".split()
        )
        for data in by_key.values():
            for t in data["titles"]:
                for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", t.lower()):
                    if w not in stop:
                        title_words[w] += 1
        historical_patterns = [f"{w} ({c} tickets)" for w, c in title_words.most_common(10)]

        snippets_joined: list[str] = []
        for data in by_key.values():
            snippets_joined.extend(data["snippets"][:2])
        common_failure_patterns = []
        seen_snip: set[str] = set()
        for s in snippets_joined[:24]:
            key = s[:80].casefold()
            if key in seen_snip:
                continue
            seen_snip.add(key)
            common_failure_patterns.append(s.strip()[:220])

        recent = sorted(by_key.items(), key=lambda kv: kv[1]["updated"], reverse=True)[:recent_related_limit]
        recent_related = [f"{jk} — {(data['titles'][0] if data['titles'] else '')}" for jk, data in recent]

        freq_components = [f"{a} ({b})" for a, b in comp_totals.most_common(15)]

        return {
            "customer": display_name,
            "historical_patterns": historical_patterns,
            "repeated_issues": repeated[:20],
            "high_risk_areas": high_risk_areas[:20],
            "frequently_affected_components": freq_components,
            "common_failure_patterns": common_failure_patterns[:15],
            "recent_related_tickets": recent_related,
        }
