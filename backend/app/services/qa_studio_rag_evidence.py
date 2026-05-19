"""Assemble grouped RAG evidence for QA Studio plan responses (bundled RAG + stubs until full index)."""

from __future__ import annotations

import os
from typing import Any

from app.services.qa_studio_bundled import load_dom_patterns_bundle, search_playbooks


def _ref_gherkin(kind: str, index: int, preview: str) -> dict[str, Any]:
    k = kind.lower()
    label = {"given": "Given", "when": "When", "then": "Then"}.get(k, k)
    return {
        "kind": f"gherkin_{k}",
        "index": index,
        "summary": f"{label} #{index + 1} — {preview[:120]}{'…' if len(preview) > 120 else ''}",
    }


def _ref_assertion(index: int, then_preview: str) -> dict[str, Any]:
    return {
        "kind": "assertion_trace",
        "index": index,
        "summary": f"Then / assertion #{index + 1} — {then_preview[:120]}{'…' if len(then_preview) > 120 else ''}",
    }


def _ref_locator(index: int, preview: str) -> dict[str, Any]:
    return {
        "kind": "locator_decision",
        "index": index,
        "summary": f"Locator decision #{index + 1} — {preview[:120]}{'…' if len(preview) > 120 else ''}",
    }


def _ref_none(summary: str) -> dict[str, Any]:
    return {"kind": "none", "index": -1, "summary": summary}


def _item(
    *,
    evidence_id: str,
    source_collection: str,
    title: str,
    relevance: float,
    disposition: str,
    reason: str,
    linked_plan_ref: dict[str, Any],
    excerpt: str | None = None,
    trace_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": evidence_id,
        "source_collection": source_collection,
        "title": title,
        "relevance": round(max(0.0, min(1.0, relevance)), 3),
        "disposition": disposition,
        "reason": reason,
        "linked_plan_ref": linked_plan_ref,
    }
    if excerpt:
        row["excerpt"] = excerpt
    if trace_meta:
        row.update(trace_meta)
    return row


def _first_then_step_label(plan_draft: dict[str, Any] | None) -> str:
    raw = (plan_draft or {}).get("assertion_traceability")
    if not isinstance(raw, list) or not raw:
        return "Primary outcome"
    first = raw[0]
    if not isinstance(first, dict):
        return "Primary outcome"
    return str(first.get("then_step") or "Primary outcome")


def build_rag_evidence_bundle(
    *,
    blocked: bool,
    plan_draft: dict[str, Any] | None,
    fields: dict[str, Any],
    jira_summary: str,
    target_area: str,
    manual_notes: str,
) -> dict[str, list[dict[str, Any]]]:
    """
    Produce grouped evidence rows. When the full LLM+RAG pipeline is wired, merge/replace
    with retrieval results using the same shape so the UI stays stable.
    """
    ta = (target_area or "").strip()
    js = (jira_summary or "").strip()[:200]
    ac_snippet = (fields.get("acceptance_criteria") or "").strip()[:160]

    playbook_hits: list[dict[str, Any]] = []
    for probe in (ta, js, ac_snippet):
        if not probe:
            continue
        playbook_hits = search_playbooks(query=probe[:200])
        if playbook_hits:
            break
    if not playbook_hits:
        playbook_hits = search_playbooks()
    playbook_hits = playbook_hits[:6]

    playbook_matches: list[dict[str, Any]] = []
    related_pattern_ids: set[str] = set()
    related_ui_ref_ids: set[str] = set()

    for i, pb in enumerate(playbook_hits):
        rel = 0.92 - (i * 0.05)
        disp = "used" if i < 2 and not blocked else "rejected"
        reason = (
            "High lexical / area overlap informs When/Then flow, locator guidance, and scroll strategy."
            if disp == "used"
            else "Lower retrieval rank or coverage for this Jira context; kept for reviewer context only."
        )
        when_preview = "User actions aligned to repro steps"
        outline = (plan_draft or {}).get("gherkin_outline") or {}
        if isinstance(outline, dict) and outline.get("when"):
            when_preview = str(outline["when"][0])[:200]
        playbook_matches.append(
            _item(
                evidence_id=f"playbook-{pb.get('id', i)}",
                source_collection="qa_studio.playbooks",
                title=str(pb.get("title") or pb.get("id") or "Playbook"),
                relevance=rel,
                disposition=disp,
                reason=reason,
                linked_plan_ref=_ref_gherkin("when", 0, when_preview),
                excerpt=(pb.get("steps") or [None])[0] if isinstance(pb.get("steps"), list) else None,
            )
        )
        for pid in pb.get("related_dom_pattern_ids") or []:
            if isinstance(pid, str):
                related_pattern_ids.add(pid)
        for uid in pb.get("related_ui_reference_ids") or []:
            if isinstance(uid, str):
                related_ui_ref_ids.add(uid)

    dom_bundle = load_dom_patterns_bundle()
    patterns_by_id = {p["id"]: p for p in dom_bundle.get("patterns", []) if isinstance(p, dict) and p.get("id")}
    dom_pattern_matches: list[dict[str, Any]] = []

    ta_low = (target_area or "").lower()
    loc_preview = ""
    if plan_draft and isinstance(plan_draft.get("locator_decisions"), list) and plan_draft["locator_decisions"]:
        ld0 = plan_draft["locator_decisions"][0]
        if isinstance(ld0, dict):
            loc_preview = str(ld0.get("rationale") or ld0.get("intent") or "")

    dom_i = 0
    for pid in list(related_pattern_ids)[:8]:
        p = patterns_by_id.get(pid)
        if not p:
            continue
        link_ref = (
            _ref_locator(0, loc_preview)
            if (loc_preview and dom_i == 0)
            else _ref_gherkin("given", 0, "Preconditions from reproduction (Page Object setup)")
        )
        dom_pattern_matches.append(
            _item(
                evidence_id=f"dom-{pid}",
                source_collection="qa_studio.dom_patterns",
                title=str(p.get("description") or pid),
                relevance=0.86,
                disposition="used" if not blocked else "rejected",
                reason=(
                    "Stable XPath examples from bundled DOM pattern library support locator choices "
                    "referenced in playbooks."
                    if not blocked
                    else "Would apply after planning is unblocked; pattern library is still relevant for locator QA."
                ),
                linked_plan_ref=link_ref,
                excerpt=(p.get("stable_xpath_examples") or [None])[0],
            )
        )
        dom_i += 1

    if not dom_pattern_matches and ta_low:
        for p in dom_bundle.get("patterns", []):
            if not isinstance(p, dict):
                continue
            area = str(p.get("aem_guides_area", "")).lower()
            if area and area in ta_low:
                pid = p.get("id", "")
                link_ref = (
                    _ref_locator(0, loc_preview)
                    if (loc_preview and dom_i == 0)
                    else _ref_gherkin("when", 0, "User actions aligned to repro steps")
                )
                dom_pattern_matches.append(
                    _item(
                        evidence_id=f"dom-{pid}",
                        source_collection="qa_studio.dom_patterns",
                        title=str(p.get("description") or pid),
                        relevance=0.78,
                        disposition="used" if not blocked else "rejected",
                        reason="Matched target area keyword to bundled AEM Guides region for pattern hints.",
                        linked_plan_ref=link_ref,
                        excerpt=(p.get("stable_xpath_examples") or [None])[0],
                    )
                )
                dom_i += 1
                if len(dom_pattern_matches) >= 3:
                    break

    ui_reference_matches: list[dict[str, Any]] = []
    ui_labels = {
        "editor-map-view": "Map editor — canvas + repository context",
    }
    for j, uid in enumerate(sorted(related_ui_ref_ids)[:4]):
        ui_reference_matches.append(
            _item(
                evidence_id=f"uiref-{uid}",
                source_collection="ui_references (indexed: pending)",
                title=ui_labels.get(uid, uid.replace("-", " ").title()),
                relevance=0.8 - j * 0.03,
                disposition="used" if not blocked and j == 0 else "rejected",
                reason=(
                    "Structured UI reference aligns screen regions with playbook component_types."
                    if not blocked and j == 0
                    else "Index not fully wired; treat as conceptual anchor until Chroma/ui-reference ingest is enabled."
                ),
                linked_plan_ref=_ref_gherkin("when", 0, "User actions aligned to repro steps"),
            )
        )

    if not ui_reference_matches:
        ui_reference_matches.append(
            _item(
                evidence_id="uiref-none",
                source_collection="ui_references (indexed: pending)",
                title="No playbook-linked UI reference id for this query",
                relevance=0.35,
                disposition="rejected",
                reason="No related_ui_reference_ids on retrieved playbooks, or UI reference collection empty.",
                linked_plan_ref=_ref_none("Plan step link N/A — reference not retrieved"),
            )
        )

    notes_low = (manual_notes or "").lower()
    snapshot_hint = any(
        k in notes_low for k in ("screenshot", "snapshot", "recording", "video", "dom dump", "accessibility tree")
    )
    notes_signal_expected = any(
        p in notes_low
        for p in (
            "expected behavior",
            "expected behaviour",
            "acceptance",
            "acceptance criteria",
            "ac:",
            "uac",
            "golden",
            "baseline",
            "post-fix",
            "fixed behavior",
            "expected fix",
        )
    )
    ui_snapshot_matches: list[dict[str, Any]] = []
    if snapshot_hint and not blocked:
        snap_meta: dict[str, Any] = {}
        if notes_signal_expected:
            snap_meta = {
                "expected_behavior": "Authoring notes tie visual evidence to expected behavior, AC, or post-fix baseline.",
                "ties_to_jira_context": True,
            }
        ui_snapshot_matches.append(
            _item(
                evidence_id="snap-manual",
                source_collection="ui_snapshots (manual_notes)",
                title="Manual snapshot / media noted in authoring notes",
                relevance=0.62,
                disposition="used",
                reason="Authoring notes cite visual or DOM evidence; formal snapshot embedding ingest is pending.",
                linked_plan_ref=_ref_gherkin("then", 0, "Observable outcomes trace to expected behavior"),
                trace_meta=snap_meta,
            )
        )
    ui_snapshot_matches.append(
        _item(
            evidence_id="snap-index",
            source_collection="ui_snapshots (vector index)",
            title="Indexed UI snapshot nearest-neighbor search",
            relevance=0.55 if snapshot_hint else 0.25,
            disposition="rejected",
            reason=(
                "No snapshot chunk passed the similarity gate for this Jira text (index not populated or threshold)."
                if not snapshot_hint
                else "Snapshot index empty or below threshold; manual_notes used as weak evidence only."
            ),
            linked_plan_ref=_ref_gherkin("when", 0, "User actions aligned to repro steps"),
            trace_meta={"is_generic_screen": True},
        )
    )

    xpath_count = int(os.environ.get("QA_STUDIO_XPATH_INDEX_COUNT", "0") or 0)
    page_object_matches: list[dict[str, Any]] = []
    if xpath_count > 0:
        page_object_matches.append(
            _item(
                evidence_id="po-index-hit",
                source_collection="framework.xpath_page_objects",
                title=f"Indexed Page Object / XPath entries (count ≈ {xpath_count})",
                relevance=0.9,
                disposition="used" if not blocked else "rejected",
                reason="Retriever returned candidate PO methods — prefer these over net-new XPath.",
                linked_plan_ref=_ref_gherkin("given", 0, "Preconditions from reproduction (Page Object setup)"),
            )
        )
    else:
        page_object_matches.append(
            _item(
                evidence_id="po-index-empty",
                source_collection="framework.xpath_page_objects",
                title="Page Object / XPath index",
                relevance=0.2,
                disposition="rejected",
                reason=(
                    "QA_STUDIO_XPATH_INDEX_COUNT is 0 — configure QA_STUDIO_UI_TESTS_PATH and indexer "
                    "so PO/XPath retrieval can rank methods before new locators."
                ),
                linked_plan_ref=_ref_none("Awaiting index — no PO retrieval for this plan"),
            )
        )

    assertion_source_matches: list[dict[str, Any]] = []
    quote = (fields.get("source_quote") or "").strip()
    ac = (fields.get("acceptance_criteria") or "").strip()
    exp = (fields.get("expected_fixed_behavior") or "").strip()

    if blocked:
        assertion_source_matches.append(
            _item(
                evidence_id="asrc-blocked",
                source_collection="jira.extraction",
                title="Observable expected outcome",
                relevance=0.15,
                disposition="rejected",
                reason=(
                    "Planning blocked: no acceptance criteria or expected behavior extracted — "
                    "LLM must not invent Then assertions."
                ),
                linked_plan_ref=_ref_assertion(0, "Primary outcome (not generated)"),
            )
        )
    elif quote or ac or exp:
        excerpt = quote or ac or exp
        assertion_source_matches.append(
            _item(
                evidence_id="asrc-jira",
                source_collection="jira.fields",
                title="Jira expected behavior / acceptance criteria (assertion source)",
                relevance=1.0,
                disposition="used",
                reason=(
                    "Then steps and assertions must trace to this quote — explains why each Then is grounded "
                    "and blocks hallucinated expectations."
                ),
                linked_plan_ref=_ref_assertion(0, _first_then_step_label(plan_draft)),
                excerpt=excerpt[:500] + ("…" if len(excerpt) > 500 else ""),
            )
        )
    else:
        assertion_source_matches.append(
            _item(
                evidence_id="asrc-fallback",
                source_collection="jira.fields",
                title="Weak or inferred assertion source",
                relevance=0.5,
                disposition="rejected",
                reason="No explicit source_quote — review extracted_fields before trusting Then mapping.",
                linked_plan_ref=_ref_assertion(0, "Primary outcome"),
            )
        )

    return {
        "playbook_matches": playbook_matches,
        "ui_reference_matches": ui_reference_matches,
        "ui_snapshot_matches": ui_snapshot_matches,
        "dom_pattern_matches": dom_pattern_matches,
        "page_object_matches": page_object_matches,
        "assertion_source_matches": assertion_source_matches,
    }
