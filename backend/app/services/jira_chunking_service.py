"""Smart, high-signal Jira chunks for embedding (not one monolithic blob)."""

from __future__ import annotations

import os
import re
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.customer_tokens import clean_customer_tokens
from app.services.jira_client import extract_description_from_issue, _adf_to_plain_text
from app.services.jira_enrichment_service import (
    enrich_jira,
    enrichment_embed_prefix,
    enrichment_metadata_json,
)
from app.services.jira_uac_analysis_service import (
    HISTORICAL_UAC_CHUNK_TYPES,
    analyze_historical_uac,
    build_historical_uac_chunks,
    extract_explicit_root_cause_evidence,
    extract_explicit_test_evidence,
    extract_release_scope_evidence,
    is_explicit_final_scope_comment,
    is_no_uac_sentinel,
    resolve_historical_uac_text,
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
        "acceptance_criteria_chunk",
        "uac_status_chunk",
        "resolution_rca_chunk",
        "test_evidence_chunk",
        "linked_issue_chunk",
        "attachment_signal_chunk",
        "learning_behavior_chunk",
        *HISTORICAL_UAC_CHUNK_TYPES,
    }
)

_MAX_CHUNK_CHARS = int(os.getenv("JIRA_SMART_CHUNK_MAX_CHARS", "4000"))
_PROBLEM_SLICE = int(os.getenv("JIRA_SMART_PROBLEM_SLICE", "2800"))
# Overlap between consecutive slices of one long field, so a sentence cut at a boundary is still
# whole in one of the two chunks.
_SLICE_OVERLAP = int(os.getenv("JIRA_SMART_SLICE_OVERLAP", "200"))
# Safety cap on continuation parts per field; anything beyond is flagged ``chunk_truncated``.
_MAX_PARTS_PER_FIELD = int(os.getenv("JIRA_SMART_MAX_PARTS_PER_FIELD", "24"))
# Per-clause UAC chunk types get content-addressed ids so a re-index never re-points an id at a
# different clause (saved evidence references chunk ids).
_STABLE_ID_CHUNK_TYPES: frozenset[str] = frozenset(
    {
        "historical_uac_clause_chunk",
        "historical_uac_out_of_scope_chunk",
        "historical_uac_reference_chunk",
        "historical_uac_context_chunk",
    }
)
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


_DIGEST_MAX_REGULAR_COMMENTS = 40
_DIGEST_REGULAR_COMMENT_CHARS = 900


def _comment_sort_key(created: str, index: int) -> tuple[int, float, str, int]:
    """Chronological key: parsed timestamp when possible, otherwise the raw string, then position."""
    from app.services.jira_sync_state import parse_jira_timestamp

    parsed = parse_jira_timestamp(created) if created else None
    if parsed is not None:
        return (1, parsed.timestamp(), "", index)
    return (0, 0.0, created, index)


def build_comments_digest(comments: list[dict[str, Any]] | None, *, max_chars: int = 3200) -> str:
    """Compact, meaningful-only comment text for ``comments_digest``.

    The latest explicit final-scope comment comes first. The rest of the budget goes to the
    *newest* meaningful comments (verification, final fix, sign-off usually come last), emitted in
    chronological order. Whole comment lines are kept or dropped; a line is never cut midway to
    fit the budget.
    """
    if not comments:
        return ""
    regular: list[tuple[tuple[int, float, str, int], str]] = []
    scope: list[tuple[tuple[int, float, str, int], str]] = []
    for index, c in enumerate(comments):
        if not isinstance(c, dict):
            continue
        body = str(c.get("body_text") or "").strip()
        if not body and isinstance(c.get("body"), dict):
            body = _adf_to_plain_text(c["body"]).strip()
        if len(body) < _COMMENT_MIN_LEN:
            continue
        explicit_scope = is_explicit_final_scope_comment(body)
        blob = body.lower()
        if not explicit_scope and not any(h in blob for h in _MEANINGFUL_HINTS) and len(body) < 120:
            continue
        author = str(c.get("author") or "").strip()
        created = str(c.get("created") or "").strip()
        key = _comment_sort_key(created, index)
        if explicit_scope:
            scope.append((key, f"[{created}] {author}: {body}"))
        else:
            regular.append((key, f"[{created}] {author}: {body[:_DIGEST_REGULAR_COMMENT_CHARS]}"))

    lines: list[str] = []
    remaining = max_chars
    if scope:
        # The accepted scope is the acceptance authority, but it may use at most two thirds of the
        # budget so the latest regular comments are not crowded out entirely.
        scope_line = max(scope, key=lambda item: item[0])[1]
        scope_cap = max_chars if not regular else max(1, (max_chars * 2) // 3)
        scope_line = scope_line[:scope_cap].rstrip()
        lines.append(scope_line)
        remaining -= len(scope_line)

    regular.sort(key=lambda item: item[0])
    picked: list[str] = []
    for _, line in reversed(regular[-_DIGEST_MAX_REGULAR_COMMENTS:]):
        cost = len(line) + 1  # newline separator
        if cost > remaining:
            continue
        picked.append(line)
        remaining -= cost
    lines.extend(reversed(picked))
    return "\n".join(lines).strip()


def _core_fields(enriched: JiraEnrichedDocument) -> dict[str, Any]:
    return {
        "jira_key": enriched.jira_key.strip(),
        "domain": (enriched.domain or "unknown")[:80],
        "resolution": (enriched.resolution or "")[:120],
        "source_type": (enriched.source_type or "jira_api")[:80],
        "customer_names": clean_customer_tokens(list(enriched.customer_names or [])),
        "affected_outputs": list(enriched.affected_outputs or []),
        "dita_entities": list(enriched.dita_entities or []),
    }


def split_text_slices(text: str, limit: int, *, overlap: int = _SLICE_OVERLAP) -> list[str]:
    """Split ``text`` into slices of at most ``limit`` chars that cover all of it.

    Cuts prefer a paragraph break, then a line break, then a sentence end, then whitespace, in the
    back half of the window; consecutive slices overlap by about ``overlap`` chars. Always makes
    progress, whatever ``overlap`` is configured to.
    """
    text = (text or "").strip()
    limit = max(1, int(limit))
    if len(text) <= limit:
        return [text] if text else []
    overlap = max(0, min(int(overlap), limit // 2))
    slices: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + limit)
        if end < len(text):
            window = text[start:end]
            floor = len(window) // 2
            cut = -1
            for sep in ("\n\n", "\n", ". ", "? ", "! ", "; ", " "):
                pos = window.rfind(sep, floor)
                if pos > 0:
                    cut = pos + len(sep)
                    break
            if cut > 0:
                end = start + cut
        piece = text[start:end].strip()
        if piece:
            slices.append(piece)
        if end >= len(text):
            break
        next_start = max(end - overlap, start + 1)
        # Start the overlap on a word boundary rather than mid-word.
        space = text.find(" ", next_start, end)
        start = space + 1 if 0 <= space < end - 1 else next_start
    return slices


def _append_chunk(
    out: list[dict[str, Any]],
    *,
    chunk_type: str,
    chunk_text: str,
    enriched: JiraEnrichedDocument,
) -> list[dict[str, Any]]:
    """Append one chunk, or numbered continuation parts when the text exceeds the chunk limit.

    Returns the appended rows (empty when the text is blank) so callers attach metadata to
    exactly these rows rather than to ``out[-1]``, which would be a previous chunk after a skip.
    """
    text = (chunk_text or "").strip()
    if not text:
        return []
    if len(text) <= _MAX_CHUNK_CHARS:
        row = {"chunk_type": chunk_type, "chunk_text": text, **_core_fields(enriched)}
        out.append(row)
        return [row]
    header_room = 24
    parts = split_text_slices(text, _MAX_CHUNK_CHARS - header_room)
    max_parts = max(1, _MAX_PARTS_PER_FIELD)
    truncated = len(parts) > max_parts
    parts = parts[:max_parts]
    rows: list[dict[str, Any]] = []
    for number, part in enumerate(parts, start=1):
        row = {
            "chunk_type": chunk_type,
            "chunk_text": f"[part {number}/{len(parts)}]\n{part}",
            **_core_fields(enriched),
            "chunk_part": number,
            "chunk_part_count": len(parts),
            "chunk_truncated": truncated and number == len(parts),
        }
        out.append(row)
        rows.append(row)
    return rows


def _extract_repro_from_description(description: str) -> str:
    d = description or ""
    m = re.search(
        r"(?is)\b(?:steps?\s+to\s+reproduce|repro(?:duction)?\s+steps?)\s*[:.]?\s*(.+?)"
        # Stop at the next section heading on its own line, blank line before it or not.
        r"(?=\n\s*(?:expected|actual|current|observed|result|environment|workaround|notes?|"
        r"acceptance|root\s+cause|additional|attachments?)\b(?:[ \t]+\w+){0,2}[ \t]*(?::|\n|\Z)|\Z)",
        d,
    )
    if m:
        return m.group(1).strip()
    # Numbered list heuristic
    lines = []
    for ln in d.splitlines():
        if re.match(r"^\s*\d+[\).\s]", ln):
            lines.append(ln.strip())
    if len(lines) >= 2:
        return "\n".join(lines)
    return ""


def _problem_body_without_expected_actual(description: str, enriched: JiraEnrichedDocument) -> str:
    """Prefer description minus blocks already surfaced as expected/actual."""
    d = (description or "").strip()
    if not d:
        return ""
    # Remove expected/actual text already surfaced in its own chunk: every occurrence, and
    # tolerant of whitespace/line-break differences between the field and the description.
    for block in (enriched.expected_behavior, enriched.actual_behavior):
        b = (block or "").strip()
        if len(b) <= 30:
            continue
        pattern = r"\s+".join(re.escape(token) for token in b.split())
        d = re.sub(pattern, "", d).strip()
    # Keep line structure (numbered steps, lists); only squeeze runs of spaces and blank lines.
    d = re.sub(r"[ \t\f\v]+", " ", d)
    d = re.sub(r" *\n *", "\n", d)
    d = re.sub(r"\n{3,}", "\n\n", d)
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
    # Overlapping slices over the whole description (previously only the first two slices were
    # kept and the rest was dropped).
    body_slices = split_text_slices(body, _PROBLEM_SLICE)
    max_slices = max(1, _MAX_PARTS_PER_FIELD)
    problem_truncated = len(body_slices) > max_slices
    body_slices = body_slices[:max_slices]
    if body_slices:
        prob_lines.append(body_slices[0])
    problem_rows: list[dict[str, Any]] = []
    if prob_lines:
        problem_rows += _append_chunk(out, chunk_type="problem_chunk", chunk_text="\n".join(prob_lines), enriched=e)
    for number, rest in enumerate(body_slices[1:], start=2):
        problem_rows += _append_chunk(
            out,
            chunk_type="problem_chunk",
            chunk_text=f"Description continued ({number}/{len(body_slices)}):\n{rest}",
            enriched=e,
        )
    if problem_truncated and problem_rows:
        # Flag the last retained row, even when only the first slice was kept. Set-only: never
        # clear a flag _append_chunk already set on its own parts.
        problem_rows[-1]["chunk_truncated"] = True

    # 3) expected / actual
    ea_lines = []
    if (e.expected_behavior or "").strip():
        ea_lines.append("Expected: " + e.expected_behavior.strip())
    if (e.actual_behavior or "").strip():
        ea_lines.append("Actual: " + e.actual_behavior.strip())
    if ea_lines:
        _append_chunk(out, chunk_type="expected_actual_chunk", chunk_text="\n".join(ea_lines), enriched=e)

    # 4) comments (digest only)
    if (e.comments_digest or "").strip():
        _append_chunk(
            out,
            chunk_type="comment_chunk",
            chunk_text="Discussion:\n" + e.comments_digest.strip(),
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

    # 7) customer signal — cleaned tokens only, matching the ``enrich_customers`` metadata
    customers = clean_customer_tokens(list(e.customer_names or []))
    if customers:
        _append_chunk(
            out,
            chunk_type="customer_signal_chunk",
            chunk_text="Customers: " + ", ".join(customers) + " | labels: " + ", ".join(e.labels[:20]),
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

    resolved_uac_text, resolved_uac_source = resolve_historical_uac_text(
        acceptance_criteria=e.acceptance_criteria,
        labels=e.labels,
        description=e.description,
        raw_text=e.raw_text,
        comment_documents=[e.comments_digest],
    )
    if resolved_uac_text:
        for row in _append_chunk(
            out,
            chunk_type="acceptance_criteria_chunk",
            chunk_text="Acceptance criteria:\n" + resolved_uac_text,
            enriched=e,
        ):
            row["uac_source_origin"] = resolved_uac_source
        uac_root_cause, uac_root_cause_source = extract_explicit_root_cause_evidence(
            field_value=e.root_cause,
            comment_documents=[e.comments_digest],
        )
        uac_test_evidence, uac_test_evidence_source = extract_explicit_test_evidence(
            field_value=e.test_plan,
            comment_documents=[e.comments_digest],
        )
        uac_release_scope, uac_release_scope_source = extract_release_scope_evidence(
            comment_documents=[e.comments_digest],
        )
        uac_analysis = analyze_historical_uac(
            jira_key=e.jira_key,
            acceptance_criteria=resolved_uac_text,
            status=e.status,
            resolution=e.resolution,
            labels=e.labels,
            root_cause=uac_root_cause,
            test_evidence=uac_test_evidence,
            root_cause_source=uac_root_cause_source,
            test_evidence_source=uac_test_evidence_source,
            release_scope_evidence=uac_release_scope,
            release_scope_source=uac_release_scope_source,
            acceptance_source=resolved_uac_source,
        )
        if uac_analysis is not None:
            for uac_chunk in build_historical_uac_chunks(uac_analysis):
                uac_meta = {
                    key: value for key, value in uac_chunk.items() if key not in {"chunk_type", "chunk_text"}
                }
                for row in _append_chunk(
                    out,
                    chunk_type=str(uac_chunk["chunk_type"]),
                    chunk_text=str(uac_chunk["chunk_text"]),
                    enriched=e,
                ):
                    row.update(uac_meta)
                    if row.get("chunk_truncated"):
                        # The stored contract no longer holds every clause.
                        row["uac_contract_complete"] = False
    elif resolved_uac_source == "jira_no_uac_sentinel" or (
        e.acceptance_criteria.strip() and is_no_uac_sentinel(e.acceptance_criteria)
    ):
        _append_chunk(
            out,
            chunk_type="uac_status_chunk",
            chunk_text="Acceptance criteria status: no accepted UAC is required for this Jira.",
            enriched=e,
        )

    resolution_parts = []
    if e.resolution.strip():
        resolution_parts.append("Resolution: " + e.resolution.strip())
    if e.root_cause.strip():
        resolution_parts.append("Root cause: " + e.root_cause.strip())
    if resolution_parts:
        _append_chunk(
            out,
            chunk_type="resolution_rca_chunk",
            chunk_text="\n".join(resolution_parts),
            enriched=e,
        )

    if e.test_plan.strip():
        _append_chunk(
            out,
            chunk_type="test_evidence_chunk",
            chunk_text="Test plan and evidence:\n" + e.test_plan.strip(),
            enriched=e,
        )

    if e.linked_issue_refs:
        _append_chunk(
            out,
            chunk_type="linked_issue_chunk",
            chunk_text="Linked Jira issues: " + ", ".join(e.linked_issue_refs[:80]),
            enriched=e,
        )

    if e.attachment_filenames:
        _append_chunk(
            out,
            chunk_type="attachment_signal_chunk",
            chunk_text="Attachment filenames: " + ", ".join(e.attachment_filenames[:50]),
            enriched=e,
        )

    from app.services.jira_learning_chunk_service import build_learning_chunk_from_enriched

    learning = build_learning_chunk_from_enriched(e)
    if learning:
        learning_meta = {key: value for key, value in learning.items() if key not in {"chunk_type", "chunk_text"}}
        for row in _append_chunk(
            out,
            chunk_type=str(learning["chunk_type"]),
            chunk_text=str(learning["chunk_text"]),
            enriched=e,
        ):
            row.update(learning_meta)

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
    used_ids: set[str] = set()
    for sc in smart_chunks:
        ctype = str(sc.get("chunk_type") or "unknown").strip()
        body = str(sc.get("chunk_text") or "").strip()
        if not body:
            continue
        idx = counts.get(ctype, 0)
        counts[ctype] = idx + 1
        id_suffix = str(idx)
        stable_key = str(sc.get("uac_clause_stable_key") or "")
        if ctype in _STABLE_ID_CHUNK_TYPES and stable_key:
            # ``jira:KEY:uac:<digest>`` -> ``<digest>``; content-addressed, so inserting a clause
            # does not shift the ids of the clauses after it.
            id_suffix = stable_key.rsplit(":", 1)[-1]
            if sc.get("chunk_part"):
                id_suffix = f"{id_suffix}-p{int(sc['chunk_part'])}"
        cid = f"{issue_key}::{ctype}::{id_suffix}"
        if cid in used_ids:  # identical clause text twice in one UAC
            dup = 2
            while f"{cid}-{dup}" in used_ids:
                dup += 1
            cid = f"{cid}-{dup}"
        used_ids.add(cid)

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
                "resolution": enriched.resolution[:120],
                "jira_updated_at": enriched.jira_updated_at[:80],
                "import_source_type": enriched.source_type[:80],
                "source_file_hash": enriched.source_file_hash[:64],
                "source_file_hashes": _json_meta(enriched.source_file_hashes[:50]),
                "company_names": _json_meta(enriched.company_names[:50]),
                "customer_cohorts": _json_meta(enriched.customer_cohorts[:20]),
                "resolutions": _json_meta(enriched.resolutions[:50]),
                "importer_version": "customer-intelligence-v2" if enriched.source_type == "jira_csv" else "",
                "import_evidence_archive": _json_meta(enriched.evidence_archive),
                "enrich_domain": enriched.domain[:120],
                "domain_ranking_policy": "soft_boost_only",
                "domain_schema_version": "jira-domain-v2",
                "enrich_sub_domain": (enriched.sub_domain or "")[:120],
                "enrich_customers": _json_meta(clean_customer_tokens(enriched.customer_names)),
                "enrich_entities": _json_meta(enriched.dita_entities[:40]),
                "enrich_outputs": _json_meta(enriched.affected_outputs[:20]),
                "enrich_features": _json_meta(enriched.affected_features[:40]),
                "editor_variant": "new_editor" if "new_editor" in enriched.affected_features else "",
                "enrich_automation_fit": enriched.automation_fit[:200],
                "enrich_profile_json": je_profile,
                "smart_customer_names": _json_meta(clean_customer_tokens(sc.get("customer_names") or [])),
                "smart_affected_outputs": _json_meta(sc.get("affected_outputs") or []),
                "smart_dita_entities": _json_meta(sc.get("dita_entities") or []),
                "learning_confidence": str(sc.get("learning_confidence") or ""),
                "historical_outcome": str(sc.get("historical_outcome") or ""),
                "is_verified_fix": bool(sc.get("is_verified_fix") or False),
                "evidence_facets": _json_meta(sc.get("evidence_facets") or []),
                "learning_strategy_version": str(sc.get("learning_strategy_version") or ""),
                "behavior_contract_source": str(sc.get("behavior_contract_source") or ""),
                "behavior_contract_complete": bool(sc.get("behavior_contract_complete") or False),
                "root_cause_source": str(sc.get("root_cause_source") or ""),
                "qa_oracle_source": str(sc.get("qa_oracle_source") or ""),
                "resolution_mechanism": str(sc.get("resolution_mechanism") or ""),
                "resolution_evidence_source": str(sc.get("resolution_evidence_source") or ""),
            }
        )
        for key in (
            "uac_schema_version",
            "uac_analysis_method",
            "uac_source_hash",
            "uac_source_authority",
            "uac_source_origin",
            "uac_reuse_tier",
            "uac_historical_outcome",
            "uac_root_cause_source",
            "uac_test_evidence_source",
            "uac_clause_id",
            "uac_clause_stable_key",
            "uac_clause_kind",
            "uac_clause_reuse_tier",
            "uac_dimension",
        ):
            meta[key] = str(sc.get(key) or "")
        for key in (
            "uac_llm_used",
            "uac_source_truncated",
            "uac_contract_complete",
            "uac_issue_closed",
            "uac_performance_matters",
            "uac_performance_complete",
            "uac_clause_unresolved",
            "uac_dimension_has_unresolved",
        ):
            meta[key] = bool(sc.get(key) or False)
        for key in (
            "uac_clause_count",
            "uac_out_of_scope_count",
            "uac_reference_count",
            "uac_context_count",
            "uac_unresolved_count",
            "uac_contradiction_count",
        ):
            meta[key] = int(sc.get(key) or 0)
        meta["uac_dimensions"] = _json_meta(sc.get("uac_dimensions") or [])
        meta["chunk_part"] = int(sc.get("chunk_part") or 0)
        meta["chunk_part_count"] = int(sc.get("chunk_part_count") or 0)
        meta["chunk_truncated"] = bool(sc.get("chunk_truncated") or False)
        rows.append({"chunk_id": cid, "document": doc, "metadata": meta})
    return rows


_LINKED_SUMMARY_CHARS = 160
_ATTACHMENT_TEXT_MAX_BLOBS = 5
_ATTACHMENT_TEXT_CHUNK_CHARS = 3000


def _linked_issue_text(refs: list[str], linked_issues: list[dict[str, Any]] | None) -> str:
    """Linked keys with their fetched summaries; keys without a summary are still listed."""
    summaries: dict[str, str] = {}
    order: list[str] = []
    for ref in refs or []:
        key = str(ref or "").strip()
        if key and key not in summaries:
            summaries[key] = ""
            order.append(key)
    for item in linked_issues or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        if key not in summaries:
            order.append(key)
        summaries[key] = " ".join(str(item.get("summary") or "").split())[:_LINKED_SUMMARY_CHARS]
    if not order:
        return ""
    order = order[:80]
    if not any(summaries[key] for key in order):
        return "Linked Jira issues: " + ", ".join(order)
    lines = ["Linked Jira issues:"]
    used = len(lines[0])
    overflow: list[str] = []
    for key in order:
        line = f"{key}: {summaries[key]}" if summaries[key] else key
        if used + len(line) + 1 > _MAX_CHUNK_CHARS - 200:
            overflow.append(key)
            continue
        lines.append(line)
        used += len(line) + 1
    if overflow:
        lines.append("Also linked: " + ", ".join(overflow))
    return "\n".join(lines)


def _augment_with_bundle_context(
    smart: list[dict[str, Any]],
    enriched: JiraEnrichedDocument,
    *,
    linked_issues: list[dict[str, Any]] | None,
    attachment_search_blobs: list[str] | None,
) -> list[dict[str, Any]]:
    """Add linked-issue summaries and extracted attachment text the enriched doc does not carry."""
    out = list(smart)
    linked_text = _linked_issue_text(list(enriched.linked_issue_refs or []), linked_issues)
    if linked_text:
        out = [chunk for chunk in out if chunk.get("chunk_type") != "linked_issue_chunk"]
        _append_chunk(out, chunk_type="linked_issue_chunk", chunk_text=linked_text, enriched=enriched)
    for blob in [b for b in (attachment_search_blobs or []) if str(b or "").strip()][:_ATTACHMENT_TEXT_MAX_BLOBS]:
        text = str(blob).strip()[:_ATTACHMENT_TEXT_CHUNK_CHARS]
        _append_chunk(
            out,
            chunk_type="attachment_signal_chunk",
            chunk_text="Attachment text:\n" + text,
            enriched=enriched,
        )
    return out


def build_smart_chroma_chunks(
    issue_key: str,
    issue_dict: dict[str, Any],
    *,
    enriched: JiraEnrichedDocument | None = None,
    comments: list[dict[str, Any]] | None = None,
    linked_issues: list[dict[str, Any]] | None = None,
    attachment_search_blobs: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Enrich (if needed), attach comment digest, run smart chunking, return Chroma rows.

    ``linked_issues`` (``{"key", "summary"}``) and ``attachment_search_blobs`` (extracted
    attachment text) come from the fetched issue bundle and are indexed alongside the smart chunks.
    """
    enr = enriched if enriched is not None else enrich_jira(issue_dict)
    if issue_key and not (enr.jira_key or "").strip():
        enr = enr.model_copy(update={"jira_key": issue_key.strip()})
    digest = build_comments_digest(comments or [])
    if digest:
        enr = enr.model_copy(update={"comments_digest": digest})
    smart = create_jira_chunks(enr)
    smart = _augment_with_bundle_context(
        smart,
        enr,
        linked_issues=linked_issues,
        attachment_search_blobs=attachment_search_blobs,
    )
    return smart_chunks_to_chroma_rows(issue_key, issue_dict, enr, smart)
