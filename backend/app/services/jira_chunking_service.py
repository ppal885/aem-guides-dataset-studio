"""Smart, high-signal Jira chunks for embedding (not one monolithic blob)."""

from __future__ import annotations

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

SMART_JIRA_CHUNK_TYPES: frozenset[str] = frozenset(
    {
        "summary_chunk",
        "problem_chunk",
        "expected_actual_chunk",
        "comment_chunk",
        "reproduction_chunk",
        "qa_signal_chunk",
        "customer_signal_chunk",
        "domain_entity_chunk",
    }
)

_MAX_CHUNK_CHARS = int(os.getenv("JIRA_SMART_CHUNK_MAX_CHARS", "4000"))
_PROBLEM_SLICE = int(os.getenv("JIRA_SMART_PROBLEM_SLICE", "2800"))
_COMMENT_MIN_LEN = 40
_MEANINGFUL_HINTS = (
    "verified",
    "repro",
    "regression",
    "workaround",
    "fix",
    "merged",
    "baseline",
    "publish",
    "pdf",
    "customer",
    "blocking",
    "still",
    "fails",
    "error",
    "confirmed",
)


def build_comments_digest(comments: list[dict[str, Any]] | None, *, max_chars: int = 3200) -> str:
    """Compact, meaningful-only comment text for ``comments_digest``."""
    if not comments:
        return ""
    lines: list[str] = []
    for c in comments[:40]:
        if not isinstance(c, dict):
            continue
        body = str(c.get("body_text") or "").strip()
        if not body and isinstance(c.get("body"), dict):
            body = _adf_to_plain_text(c["body"]).strip()
        if len(body) < _COMMENT_MIN_LEN:
            continue
        blob = body.lower()
        if not any(h in blob for h in _MEANINGFUL_HINTS) and len(body) < 120:
            continue
        author = str(c.get("author") or "").strip()
        created = str(c.get("created") or "").strip()
        lines.append(f"[{created}] {author}: {body[:900]}")
        if sum(len(x) + 1 for x in lines) >= max_chars:
            break
    return "\n".join(lines)[:max_chars].strip()


def _core_fields(enriched: JiraEnrichedDocument) -> dict[str, Any]:
    return {
        "jira_key": enriched.jira_key.strip(),
        "domain": (enriched.domain or "unknown")[:80],
        "customer_names": list(enriched.customer_names or []),
        "affected_outputs": list(enriched.affected_outputs or []),
        "dita_entities": list(enriched.dita_entities or []),
    }


def _append_chunk(
    out: list[dict[str, Any]],
    *,
    chunk_type: str,
    chunk_text: str,
    enriched: JiraEnrichedDocument,
) -> None:
    text = (chunk_text or "").strip()
    if not text:
        return
    row = {"chunk_type": chunk_type, "chunk_text": text[:_MAX_CHUNK_CHARS], **_core_fields(enriched)}
    out.append(row)


def _extract_repro_from_description(description: str) -> str:
    d = description or ""
    m = re.search(
        r"(?is)(?:steps?\s+to\s+reproduce|repro(?:duction)?\s+steps?)\s*[:.]?\s*(.+?)(?=(?:\n\n(?:expected|actual))|(?:\Z))",
        d,
    )
    if m:
        return m.group(1).strip()[:3500]
    # Numbered list heuristic
    lines = []
    for ln in d.splitlines():
        if re.match(r"^\s*\d+[\).\s]", ln):
            lines.append(ln.strip())
    if len(lines) >= 2:
        return "\n".join(lines[:40])[:3500]
    return ""


def _problem_body_without_expected_actual(description: str, enriched: JiraEnrichedDocument) -> str:
    """Prefer description minus blocks already surfaced as expected/actual."""
    d = (description or "").strip()
    if not d:
        return ""
    # Strip leading expected/actual paragraphs if duplicated in enriched fields
    for block in (enriched.expected_behavior, enriched.actual_behavior):
        b = (block or "").strip()
        if len(b) > 30 and b in d:
            d = d.replace(b, "", 1).strip()
    d = re.sub(r"\s+", " ", d)
    return d.strip()


def create_jira_chunks(enriched_doc: JiraEnrichedDocument) -> list[dict]:
    """
    Build compact, typed chunks. Each dict includes:
    ``jira_key``, ``chunk_type``, ``chunk_text``, ``domain``, ``customer_names``,
    ``affected_outputs``, ``dita_entities``.
    """
    e = enriched_doc
    if not (e.jira_key or "").strip():
        return []

    out: list[dict[str, Any]] = []

    # 1) summary
    head = " | ".join(
        x
        for x in (
            f"Issue {e.jira_key}",
            f"summary: {e.summary}" if e.summary else "",
            f"type={e.issue_type}" if e.issue_type else "",
            f"status={e.status}" if e.status else "",
            f"priority={e.priority}" if e.priority else "",
        )
        if x
    )
    if e.components:
        head += f" | components: {', '.join(e.components[:12])}"
    if e.labels:
        head += f" | labels: {', '.join(e.labels[:16])}"
    _append_chunk(out, chunk_type="summary_chunk", chunk_text=head, enriched=e)

    # 2) problem — symptoms + description (split when very long)
    prob_lines: list[str] = []
    if e.symptoms:
        prob_lines.append("Symptoms: " + "; ".join(s.strip() for s in e.symptoms[:8] if s.strip()))
    body = _problem_body_without_expected_actual(e.description, e)
    if body:
        first = body[:_PROBLEM_SLICE] + ("…" if len(body) > _PROBLEM_SLICE else "")
        prob_lines.append(first)
    if prob_lines:
        _append_chunk(out, chunk_type="problem_chunk", chunk_text="\n".join(prob_lines), enriched=e)
    if body and len(body) > _PROBLEM_SLICE:
        rest = body[_PROBLEM_SLICE : _PROBLEM_SLICE * 2].strip()
        if rest:
            _append_chunk(out, chunk_type="problem_chunk", chunk_text=rest, enriched=e)

    # 3) expected / actual
    ea_lines = []
    if (e.expected_behavior or "").strip():
        ea_lines.append("Expected: " + e.expected_behavior.strip()[:2000])
    if (e.actual_behavior or "").strip():
        ea_lines.append("Actual: " + e.actual_behavior.strip()[:2000])
    if ea_lines:
        _append_chunk(out, chunk_type="expected_actual_chunk", chunk_text="\n".join(ea_lines), enriched=e)

    # 4) comments (digest only)
    if (e.comments_digest or "").strip():
        _append_chunk(
            out,
            chunk_type="comment_chunk",
            chunk_text="Discussion:\n" + e.comments_digest.strip()[:_MAX_CHUNK_CHARS],
            enriched=e,
        )

    # 5) reproduction
    repro = _extract_repro_from_description(e.description)
    if repro:
        _append_chunk(out, chunk_type="reproduction_chunk", chunk_text=repro, enriched=e)

    # 6) QA signals
    qa_bits = []
    if e.qa_risk_tags:
        qa_bits.append("Risks: " + ", ".join(e.qa_risk_tags))
    if (e.automation_fit or "").strip():
        qa_bits.append("Automation fit: " + e.automation_fit.strip())
    if e.missing_info:
        qa_bits.append("Missing info flags: " + ", ".join(e.missing_info[:12]))
    if qa_bits:
        _append_chunk(out, chunk_type="qa_signal_chunk", chunk_text=" | ".join(qa_bits), enriched=e)

    # 7) customer signal
    if e.customer_names:
        _append_chunk(
            out,
            chunk_type="customer_signal_chunk",
            chunk_text="Customers: " + ", ".join(e.customer_names) + " | labels: " + ", ".join(e.labels[:20]),
            enriched=e,
        )

    # 8) synthetic domain + entities
    dom = e.domain or "unknown"
    sub = (e.sub_domain or "").strip()
    ent = ", ".join(e.dita_entities[:14]) if e.dita_entities else "no DITA entity markers detected"
    outs = ", ".join(e.affected_outputs[:8]) if e.affected_outputs else "outputs not classified"
    feats = ", ".join(e.affected_features[:8]) if e.affected_features else ""
    syn = (
        f"Jira {e.jira_key} belongs to {dom}"
        + (f"/{sub}" if sub else "")
        + f" and involves {ent}. Affected outputs: {outs}."
    )
    if feats:
        syn += f" Feature hints: {feats}."
    _append_chunk(out, chunk_type="domain_entity_chunk", chunk_text=syn, enriched=e)

    return out


def smart_chunks_to_chroma_rows(
    issue_key: str,
    issue_dict: dict[str, Any],
    enriched: JiraEnrichedDocument,
    smart_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map smart chunk dicts to ``{chunk_id, document, metadata}`` for Chroma + SQL inserters."""
    from app.services.customer_intelligence_engine import customer_index_metadata_for_chunks
    from app.services.jira_qa_chunking_service import _build_base_metadata, _json_meta

    fields = issue_dict.get("fields") or {}
    if not isinstance(fields, dict):
        fields = {}
    ci_flat = customer_index_metadata_for_chunks(fields)
    customer = str(ci_flat.get("customer") or "")
    labels = fields.get("labels") or []
    if not isinstance(labels, list):
        labels = []
    components = fields.get("components") or []
    if not isinstance(components, list):
        components = []
    automation_guess = "Partial"
    summary = str(fields.get("summary") or "")
    desc_plain = extract_description_from_issue(issue_dict)
    blob = f"{summary} {desc_plain} {' '.join(str(l) for l in labels)}".lower()
    if any(x in blob for x in ("manual only", "exploratory", "cannot automate", "not automatable")):
        automation_guess = "No"
    elif any(x in blob for x in ("api test", "automated test", "selenium", "regression suite")):
        automation_guess = "Yes"

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

    embed_prefix = enrichment_embed_prefix(enriched)
    je_profile = enrichment_metadata_json(enriched)

    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for sc in smart_chunks:
        ctype = str(sc.get("chunk_type") or "unknown").strip()
        body = str(sc.get("chunk_text") or "").strip()
        if not body:
            continue
        idx = counts.get(ctype, 0)
        counts[ctype] = idx + 1

        doc_body = body[:12000]
        if embed_prefix:
            doc = f"[{issue_key} | {ctype}]\n{embed_prefix}\n\n{doc_body}"
            if len(doc) > 12000:
                doc = doc[:12000]
        else:
            doc = f"[{issue_key} | {ctype}]\n\n{doc_body}"[:12000]

        meta = _build_base_metadata(chunk_type=ctype, **base_kw)
        meta.update(
            {
                "enrich_domain": enriched.domain[:120],
                "enrich_sub_domain": (enriched.sub_domain or "")[:120],
                "enrich_customers": _json_meta(enriched.customer_names),
                "enrich_entities": _json_meta(enriched.dita_entities[:40]),
                "enrich_outputs": _json_meta(enriched.affected_outputs[:20]),
                "enrich_automation_fit": enriched.automation_fit[:200],
                "enrich_profile_json": je_profile,
                "smart_customer_names": _json_meta(sc.get("customer_names") or []),
                "smart_affected_outputs": _json_meta(sc.get("affected_outputs") or []),
                "smart_dita_entities": _json_meta(sc.get("dita_entities") or []),
            }
        )
        cid = f"{issue_key}::{ctype}::{idx}"
        rows.append({"chunk_id": cid, "document": doc, "metadata": meta})
    return rows


def build_smart_chroma_chunks(
    issue_key: str,
    issue_dict: dict[str, Any],
    *,
    enriched: JiraEnrichedDocument | None = None,
    comments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Enrich (if needed), attach comment digest, run smart chunking, return Chroma rows."""
    enr = enriched if enriched is not None else enrich_jira(issue_dict)
    if issue_key and not (enr.jira_key or "").strip():
        enr = enr.model_copy(update={"jira_key": issue_key.strip()})
    digest = build_comments_digest(comments or [])
    if digest:
        enr = enr.model_copy(update={"comments_digest": digest})
    smart = create_jira_chunks(enr)
    return smart_chunks_to_chroma_rows(issue_key, issue_dict, enr, smart)
