"""Build multi-type text chunks + Chroma-safe metadata for Jira QA RAG."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_client import extract_description_from_issue, _adf_to_plain_text
from app.services.jira_enrichment_service import (
    enrich_jira,
    enrichment_embed_prefix,
    enrichment_metadata_json,
)

JIRA_QA_CUSTOMER_FIELD_ID = (os.getenv("JIRA_QA_CUSTOMER_FIELD_ID") or "").strip()

CHUNK_TYPES = frozenset(
    {
        "full_ticket_summary",
        "customer_problem",
        "steps_expected_actual",
        "comments_discussion",
        "qa_testing_scope",
        "regression_risks",
        "automation_feasibility",
        "uac_discussion_points",
        "test_case_candidates",
        "attachment_log_signals",
        "similar_ticket_signals",
        "description_long_part",
    }
)

# Overlapping windows over long descriptions (chunk_id suffix 0 .. max-1).
JIRA_QA_DESCRIPTION_LONG_PART_MAX = 8
_DESCRIPTION_LONG_THRESHOLD = 6000
_DESCRIPTION_LONG_WINDOW = 6000
_DESCRIPTION_LONG_STRIDE = 4500

_MAX_DOC_CHARS = 12000


def _json_meta(val: Any) -> str:
    try:
        return json.dumps(val, ensure_ascii=False)[:4000]
    except (TypeError, ValueError):
        return "[]"


def _infer_automation_candidate(summary: str, desc: str, labels: list[str]) -> str:
    blob = f"{summary} {desc} {' '.join(labels)}".lower()
    if any(x in blob for x in ("manual only", "exploratory", "cannot automate", "not automatable")):
        return "No"
    if any(x in blob for x in ("api test", "automated test", "selenium", "regression suite")):
        return "Yes"
    return "Partial"


def extract_customer_from_fields(fields: dict[str, Any]) -> str:
    if JIRA_QA_CUSTOMER_FIELD_ID:
        raw = fields.get(JIRA_QA_CUSTOMER_FIELD_ID)
        if raw is None:
            pass
        elif isinstance(raw, dict):
            for k in ("value", "name", "displayName"):
                if raw.get(k):
                    return str(raw[k])[:500]
            return str(raw)[:500]
        elif isinstance(raw, list) and raw:
            first = raw[0]
            if isinstance(first, dict) and first.get("value"):
                return str(first["value"])[:500]
            return str(first)[:500]
        else:
            return str(raw)[:500]
    # Heuristic: "Customer: X" in description
    desc = extract_description_from_issue({"fields": fields})
    m = re.search(r"(?:customer|account)\s*[:]\s*([^\n]+)", desc, re.I)
    if m:
        return m.group(1).strip()[:500]
    return ""


def _components_list(fields: dict) -> list[str]:
    components = fields.get("components") or []
    if not isinstance(components, list):
        return []
    return [str(c.get("name", "")).strip() for c in components if isinstance(c, dict) and c.get("name")]


def _labels_list(fields: dict) -> list[str]:
    labels = fields.get("labels") or []
    if isinstance(labels, list):
        return [str(l).strip() for l in labels if l]
    return []


def _versions(fields: dict, key: str) -> list[str]:
    raw = fields.get(key) or []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for v in raw:
        if isinstance(v, dict) and v.get("name"):
            out.append(str(v["name"]))
        elif isinstance(v, str):
            out.append(v)
    return out


def _build_base_metadata(
    *,
    jira_key: str,
    fields: dict[str, Any],
    chunk_type: str,
    customer: str,
    customer_index: dict[str, Any] | None,
    automation_candidate: str,
    updated_at: str,
) -> dict[str, Any]:
    summary = str(fields.get("summary") or "")[:500]
    it = fields.get("issuetype") or {}
    issue_type = str(it.get("name") or "") if isinstance(it, dict) else ""
    st = fields.get("status") or {}
    status = str(st.get("name") or "") if isinstance(st, dict) else ""
    pr = fields.get("priority") or {}
    priority = str(pr.get("name") or "") if isinstance(pr, dict) else ""

    components = _components_list(fields)
    labels = _labels_list(fields)
    meta: dict[str, Any] = {
        "source_type": "jira",
        "jira_key": jira_key,
        "title": summary,
        "customer": customer[:200] if customer else "",
        "issue_type": issue_type,
        "status": status,
        "priority": priority,
        "components": _json_meta(components),
        "labels": _json_meta(labels),
        "fix_versions": _json_meta(_versions(fields, "fixVersions")),
        "affected_versions": _json_meta(_versions(fields, "versions")),
        "updated_at": updated_at[:80],
        "chunk_type": chunk_type,
        "product_area": "AEM Guides",
        "qa_domain": "UAC",
        "automation_candidate": automation_candidate,
    }
    if customer_index is not None:
        ci = customer_index
    else:
        from app.services.customer_intelligence_engine import customer_index_metadata_for_chunks

        ci = customer_index_metadata_for_chunks(fields)
    for k, v in ci.items():
        if isinstance(v, (str, int, float, bool)):
            meta[k] = v
    if not str(meta.get("customer") or "").strip() and customer:
        meta["customer"] = customer[:200]
    return meta


def build_jira_qa_chunks(
    issue_key: str,
    issue_dict: dict[str, Any],
    *,
    comments: list[dict[str, Any]] | None = None,
    linked_issues: list[dict[str, str]] | None = None,
    attachment_search_blobs: list[str] | None = None,
    enriched: JiraEnrichedDocument | None = None,
) -> list[dict[str, Any]]:
    """Return list of {chunk_id, document, metadata} for Chroma upsert."""
    use_smart = os.getenv("JIRA_SMART_CHUNKING", "true").lower() in ("true", "1", "yes")
    if use_smart:
        from app.services.jira_chunking_service import build_smart_chroma_chunks

        en = enriched if enriched is not None else enrich_jira(issue_dict)
        return build_smart_chroma_chunks(
            issue_key,
            issue_dict,
            enriched=en,
            comments=comments or [],
        )

    fields = issue_dict.get("fields") or {}
    if not isinstance(fields, dict):
        fields = {}

    summary = str(fields.get("summary") or "").strip()
    desc_plain = extract_description_from_issue(issue_dict)
    from app.services.customer_intelligence_engine import customer_index_metadata_for_chunks

    ci_flat = customer_index_metadata_for_chunks(fields)
    customer = str(ci_flat.get("customer") or "")
    labels = _labels_list(fields)
    components = _components_list(fields)
    automation_guess = _infer_automation_candidate(summary, desc_plain, labels)

    enriched = enriched if enriched is not None else enrich_jira(issue_dict)
    embed_prefix = enrichment_embed_prefix(enriched)
    je_profile = enrichment_metadata_json(enriched)

    updated = fields.get("updated") or ""
    updated_at = str(updated)[:80]

    base_kw = dict(
        jira_key=issue_key,
        fields=fields,
        customer=customer,
        customer_index=ci_flat,
        automation_candidate=automation_guess,
        updated_at=updated_at,
    )

    chunks: list[dict[str, Any]] = []

    def add(chunk_type: str, idx: int, text: str, meta_override: dict | None = None) -> None:
        text = (text or "").strip()
        if not text:
            return
        doc_body = text[:_MAX_DOC_CHARS]
        if embed_prefix:
            doc = f"[Enrichment: {embed_prefix}]\n\n{doc_body}"
            if len(doc) > _MAX_DOC_CHARS:
                doc = doc[:_MAX_DOC_CHARS]
        else:
            doc = doc_body
        meta = _build_base_metadata(chunk_type=chunk_type, **base_kw)
        meta.update(
            {
                "enrich_domain": enriched.domain[:120],
                "enrich_sub_domain": (enriched.sub_domain or "")[:120],
                "enrich_customers": _json_meta(enriched.customer_names),
                "enrich_entities": _json_meta(enriched.dita_entities[:40]),
                "enrich_outputs": _json_meta(enriched.affected_outputs[:20]),
                "enrich_automation_fit": enriched.automation_fit[:200],
                "enrich_profile_json": je_profile,
            }
        )
        if meta_override:
            meta.update(meta_override)
        cid = f"{issue_key}::{chunk_type}::{idx}"
        chunks.append({"chunk_id": cid, "document": doc, "metadata": meta})

    # full_ticket_summary
    it = fields.get("issuetype") or {}
    st = fields.get("status") or {}
    pr = fields.get("priority") or {}
    lines = [
        f"Issue: {issue_key}",
        f"Summary: {summary}",
        f"Type: {it.get('name') if isinstance(it, dict) else ''}",
        f"Status: {st.get('name') if isinstance(st, dict) else ''}",
        f"Priority: {pr.get('name') if isinstance(pr, dict) else ''}",
        f"Components: {', '.join(components)}",
        f"Labels: {', '.join(labels)}",
    ]
    if customer:
        lines.append(f"Customer: {customer}")
    if desc_plain:
        lines.append("")
        lines.append("Description:")
        lines.append(desc_plain[:8000])
    add("full_ticket_summary", 0, "\n".join(lines))

    # customer_problem — first ~4k of description + summary context
    prob_parts = [summary] if summary else []
    if desc_plain:
        prob_parts.append(desc_plain[:6000])
    add("customer_problem", 0, "\n\n".join(prob_parts))

    # Long description windows (overlapping) for RAG when body exceeds summary truncation
    if len(desc_plain) > _DESCRIPTION_LONG_THRESHOLD:
        pos = 0
        part_i = 0
        while pos < len(desc_plain) and part_i < JIRA_QA_DESCRIPTION_LONG_PART_MAX:
            slice_ = desc_plain[pos : pos + _DESCRIPTION_LONG_WINDOW]
            body = (
                f"Issue: {issue_key}\nSummary: {summary}\n"
                f"Description segment (chars {pos}-{pos + len(slice_)} of {len(desc_plain)}):\n{slice_}"
            )
            add("description_long_part", part_i, body)
            pos += _DESCRIPTION_LONG_STRIDE
            part_i += 1

    # steps_expected_actual — heuristic sections
    expected = re.findall(
        r"(?is)(?:expected|expect)\s*(?:behavior|result)?\s*[:.\s]*([^\n]+(?:\n(?!(?:actual|current))[^\n]+)*)",
        desc_plain,
    )
    actual = re.findall(
        r"(?is)(?:actual|current)\s*(?:behavior|result)?\s*[:.\s]*([^\n]+(?:\n(?!(?:expected|steps))[^\n]+)*)",
        desc_plain,
    )
    sea_lines: list[str] = []
    if expected:
        sea_lines.append("Expected:\n" + "\n".join(s.strip() for s in expected[:3]))
    if actual:
        sea_lines.append("Actual / current:\n" + "\n".join(s.strip() for s in actual[:3]))
    steps_m = re.findall(r"(?is)(?:steps?\s+to\s+reproduce|repro\s+steps)\s*[:.]?\s*(.+?)(?:\n\n|$)", desc_plain)
    if steps_m:
        sea_lines.append("Steps to reproduce:\n" + steps_m[0].strip()[:4000])
    add("steps_expected_actual", 0, "\n\n".join(sea_lines))

    # comments_discussion
    comm_texts: list[str] = []
    for c in comments or []:
        if not isinstance(c, dict):
            continue
        author = str(c.get("author") or "").strip()
        body = str(c.get("body_text") or "").strip()
        if not body and isinstance(c.get("body"), dict):
            body = _adf_to_plain_text(c["body"])
        created = str(c.get("created") or "").strip()
        if body:
            comm_texts.append(f"[{created}] {author}: {body[:2000]}")
    add("comments_discussion", 0, "\n\n".join(comm_texts[:40]))

    # qa_testing_scope — keyword-focused excerpt
    qa_hints = []
    for kw in (
        "test",
        "testing",
        "verify",
        "validation",
        "acceptance",
        "uac",
        "regression",
        "baseline",
        "publish",
        "web editor",
        "dita",
    ):
        if kw.lower() in desc_plain.lower():
            qa_hints.append(kw)
    qa_blob = f"Issue: {issue_key}\nSummary: {summary}\nTesting keywords found: {', '.join(sorted(set(qa_hints)))}\n\nExcerpt:\n{desc_plain[:4500]}"
    add("qa_testing_scope", 0, qa_blob)

    # regression_risks
    risk_blob = f"{summary}\n\n{desc_plain[:5000]}\n\nComponents: {components}\nLabels: {labels}"
    add("regression_risks", 0, risk_blob)

    # automation_feasibility (textual signals only; scoring in rubric module)
    add("automation_feasibility", 0, f"{summary}\n\n{desc_plain[:6000]}")

    # uac_discussion_points
    add("uac_discussion_points", 0, f"{summary}\n\n{desc_plain[:6000]}")

    # test_case_candidates
    add("test_case_candidates", 0, f"{summary}\n\n{desc_plain[:7000]}")

    # attachment_log_signals
    att_meta: list[str] = []
    attachments = fields.get("attachment") or []
    if isinstance(attachments, list):
        for a in attachments[:25]:
            if not isinstance(a, dict):
                continue
            fn = str(a.get("filename") or "")
            sz = a.get("size")
            mime = str(a.get("mimeType") or "")
            if fn:
                att_meta.append(f"{fn} ({mime}, {sz} bytes)")
    if attachment_search_blobs:
        for blob in attachment_search_blobs[:5]:
            b = (blob or "").strip()[:1500]
            if b:
                att_meta.append("Extracted text snippet: " + b)
    add("attachment_log_signals", 0, "\n".join(att_meta))

    # similar_ticket_signals — compact embedding-friendly line
    link_parts = []
    for li in linked_issues or []:
        if isinstance(li, dict) and li.get("key"):
            link_parts.append(f"{li.get('key')}: {li.get('summary', '')[:120]}")
    sim_line = " | ".join(
        [
            issue_key,
            summary[:200],
            ",".join(components[:8]),
            ",".join(labels[:12]),
            desc_plain[:400],
            "links: " + "; ".join(link_parts[:15]),
        ]
    )
    add("similar_ticket_signals", 0, sim_line)

    return chunks
