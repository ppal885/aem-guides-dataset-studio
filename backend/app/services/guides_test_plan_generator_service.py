"""Evidence collection for the canonical AEM Guides Test Plan runtime.

This service intentionally reuses the existing Jira, AEM Guides RAG, DITA spec,
and QA Studio evidence components. It does not create a parallel RAG system and
does not mutate indexes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any


_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_PUBLISHING_LABEL_TERMS = {
    "publishing",
    "publish",
    "pdf",
    "pdf2",
    "native-pdf",
    "native_pdf",
    "html",
    "html5",
    "transformation",
    "transform",
    "dita-ot",
    "dita_ot",
    "output",
    "output-generation",
}
_PUBLISHING_TEXT_RE = re.compile(
    r"\b(publishing|publish|pdf2|native\s+pdf|html5?|dita[-\s]?ot|open\s+toolkit|"
    r"transformation|transform|output\s+generation|output\s+preset|dita-ot)\b",
    re.IGNORECASE,
)
_EVIDENCE_GRAPH_TEST_PLAN_MODES = {"off", "shadow", "augment"}


def _evidence_graph_test_plan_mode(*, requested: bool) -> str:
    if not requested:
        return "off"
    configured = os.getenv("EVIDENCE_GRAPH_TEST_PLAN_MODE", "shadow").strip().lower()
    return configured if configured in _EVIDENCE_GRAPH_TEST_PLAN_MODES else "shadow"


def _evidence_graph_evaluation(graph: dict[str, Any], *, mode: str) -> dict[str, Any]:
    leaf_ids = {
        leaf_id
        for path in graph.get("evidence_paths") or []
        for leaf_id in _leaf_ids(path)
    }
    available = bool(graph.get("available"))
    used_for_plan = mode == "augment" and available
    if mode == "off":
        reason = "Evidence graph was disabled for this request."
    elif mode == "shadow":
        reason = "Evidence graph was measured for traceability only and did not alter plan inputs."
    elif not available:
        reason = "Evidence graph augmentation was requested but unavailable; direct evidence remained authoritative."
    else:
        reason = "Evidence graph findings may augment direct evidence after leaf-source validation."
    return {
        "mode": mode,
        "queried": mode != "off",
        "used_for_plan": used_for_plan,
        "status": graph.get("status"),
        "generation_id": (graph.get("generation") or {}).get("id"),
        "path_count": len(graph.get("evidence_paths") or []),
        "leaf_citation_count": len(leaf_ids),
        "reason": reason,
    }


def normalize_jira_key(value: str) -> str:
    """Extract and normalize a Jira key from slash-command arguments."""
    match = _JIRA_KEY_RE.search((value or "").strip().upper())
    if not match:
        raise ValueError("Expected a Jira key such as GUIDES-12345.")
    return match.group(0)


def _normalized_label(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _build_uac_label_gate(issue: dict[str, Any], *, skip_gate: bool) -> dict[str, Any]:
    labels = _issue_labels(issue)
    normalized = {_normalized_label(label) for label in labels}
    uac_check_present = "uaccheck" in normalized
    uac_done_present = bool(
        normalized & {"uacdone", "uacapproved", "uacaccepted", "uacverified"}
    )
    gate_skipped = bool(skip_gate and not (uac_check_present or uac_done_present))
    satisfied = bool(uac_check_present or uac_done_present or gate_skipped)
    contract = (
        issue.get("current_uac_contract")
        if isinstance(issue.get("current_uac_contract"), dict)
        else {}
    )
    instructions = [
        str(clause.get("text") or "").strip()
        for clause in contract.get("clauses") or []
        if clause.get("kind") == "in_scope" and str(clause.get("text") or "").strip()
    ]
    return {
        "uac_check_present": uac_check_present,
        "uac_done_present": uac_done_present,
        "gate_skipped": gate_skipped,
        "satisfied": satisfied,
        "blocked_reason": ""
        if satisfied
        else "UAC_Check or UAC_Done label is required for full generation.",
        "instructions": instructions,
        "current_contract_present": bool(contract),
        "confirmed_ac_eligible": bool(contract.get("confirmed_ac_eligible")),
        "automation_consumption": str(
            contract.get("automation_consumption") or "blocked"
        ),
    }


def _build_current_uac_contract(issue: dict[str, Any]) -> dict[str, Any]:
    acceptance_criteria = str(issue.get("acceptance_criteria") or "").strip()
    if not acceptance_criteria:
        return {}
    from app.services.jira_uac_analysis_service import (
        analyze_historical_uac,
        current_uac_contract_dict,
        has_accepted_uac_label,
    )

    labels = _issue_labels(issue)
    analysis = analyze_historical_uac(
        jira_key=str(issue.get("issue_key") or ""),
        acceptance_criteria=acceptance_criteria,
        status=str(issue.get("status") or ""),
        resolution=str(issue.get("resolution") or ""),
        labels=labels,
        acceptance_source=str(
            issue.get("acceptance_criteria_source") or "jira_acceptance_field"
        ),
    )
    if analysis is None:
        return {}
    return current_uac_contract_dict(
        analysis,
        accepted_label_present=has_accepted_uac_label(labels),
        field_id=str(issue.get("acceptance_criteria_field_id") or ""),
        field_name=str(
            issue.get("acceptance_criteria_field_name") or "Acceptance Criteria"
        ),
        mutable_fields_verified_live=str(issue.get("source") or "") == "jira_api",
    )


def build_guides_test_plan_packet(
    jira_key: str,
    *,
    tenant_id: str = "kone",
    evidence_k: int = 8,
    include_repository_evidence: bool = True,
    max_repo_matches: int = 30,
    skip_uac_label_gate: bool = False,
    full_rag: bool = True,
    include_evidence_graph: bool = True,
    graph_max_paths: int = 20,
    allow_cross_customer_graph_details: bool = False,
) -> dict[str, Any]:
    """Collect evidence, run the canonical engine, and project its response once."""

    from app.core.schemas_canonical_test_plan_runtime import (
        GenerationProfile,
        RuntimeEntryPoint,
    )
    from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME
    from app.services.test_plan_runtime_adapters import LEGACY_COMPATIBILITY_PROJECTOR

    packet = _collect_guides_test_plan_evidence_packet(
        jira_key,
        tenant_id=tenant_id,
        evidence_k=evidence_k,
        include_repository_evidence=include_repository_evidence,
        max_repo_matches=max_repo_matches,
        skip_uac_label_gate=skip_uac_label_gate,
        full_rag=full_rag,
        include_evidence_graph=include_evidence_graph,
        graph_max_paths=graph_max_paths,
        allow_cross_customer_graph_details=allow_cross_customer_graph_details,
    )
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key=jira_key,
        tenant_id=tenant_id,
        entry_point=RuntimeEntryPoint.LEGACY_PACKET,
        generation_profile=GenerationProfile.LEGACY_PACKET_COMPATIBILITY,
        options={
            "evidence_k": evidence_k,
            "include_repository_evidence": include_repository_evidence,
            "max_repo_matches": max_repo_matches,
            "skip_uac_label_gate": skip_uac_label_gate,
            "full_rag": full_rag,
            "include_evidence_graph": include_evidence_graph,
            "graph_max_paths": graph_max_paths,
        },
    )
    envelope = CANONICAL_TEST_PLAN_RUNTIME.adapt_legacy_packet(
        request=request,
        packet=packet,
    )
    return LEGACY_COMPATIBILITY_PROJECTOR.project_result(
        envelope,
        legacy_packet=packet,
    )


def _collect_guides_test_plan_evidence_packet(
    jira_key: str,
    *,
    tenant_id: str = "kone",
    evidence_k: int = 8,
    include_repository_evidence: bool = True,
    max_repo_matches: int = 30,
    skip_uac_label_gate: bool = False,
    full_rag: bool = True,
    include_evidence_graph: bool = True,
    graph_max_paths: int = 20,
    allow_cross_customer_graph_details: bool = False,
) -> dict[str, Any]:
    """Collect normalized runtime inputs without composing or prompting a plan."""
    key = normalize_jira_key(jira_key)
    issue = _lookup_issue(key, tenant_id=tenant_id)
    current_uac_contract = _build_current_uac_contract(issue)
    if current_uac_contract:
        issue["current_uac_contract"] = current_uac_contract
    uac_label_gate = _build_uac_label_gate(issue, skip_gate=skip_uac_label_gate)
    query_text = _issue_query_text(key, issue)
    docs = _retrieve_aem_docs(query_text, k=evidence_k)
    learned_behavior = _retrieve_learned_behavior_evidence(query_text, k=evidence_k)
    planning_seeds = _derive_planning_seeds(issue, learned_behavior)
    dita_chunks = _retrieve_dita_chunks(query_text, k=min(5, evidence_k))
    publishing_context = _build_publishing_transform_context(
        issue, query_text, k=min(6, evidence_k)
    )
    jira_history_searches = _retrieve_direct_jira_history(
        key,
        issue,
        query_text,
        planning_seeds,
        top_k=min(10, max(3, evidence_k)),
    )
    planning_seeds = _add_direct_jira_history_seeds(
        planning_seeds, jira_history_searches
    )
    graph_mode = _evidence_graph_test_plan_mode(requested=include_evidence_graph)
    evidence_graph = _retrieve_evidence_graph(
        key,
        issue,
        query_text,
        planning_seeds,
        tenant_id=tenant_id,
        enabled=graph_mode != "off",
        max_paths=graph_max_paths,
        allow_cross_customer_details=allow_cross_customer_graph_details,
        influence_mode=graph_mode,
    )
    graph_evaluation = _evidence_graph_evaluation(evidence_graph, mode=graph_mode)
    if graph_evaluation["used_for_plan"]:
        planning_seeds = _add_evidence_graph_seeds(planning_seeds, evidence_graph)
    repo_contract = _build_repository_evidence_contract(issue, planning_seeds)
    repository_evidence = (
        _collect_repository_evidence(
            issue, planning_seeds, repo_contract, max_matches=max_repo_matches
        )
        if include_repository_evidence
        else _repository_evidence_disabled()
    )
    planning_seeds = _add_repository_evidence_seeds(planning_seeds, repository_evidence)
    qa_preview = _qa_preview(key, issue)

    packet = {
        "workflow": "guides-test-plan-generator",
        "jira_key": key,
        "tenant_id": tenant_id,
        "issue": issue,
        "current_uac_contract": current_uac_contract,
        "uac_label_gate": uac_label_gate,
        "generation_mode": "full_rag" if uac_label_gate["satisfied"] else "blocked",
        "experience_league_evidence": docs,
        "learned_behavior_evidence": learned_behavior,
        "planning_seeds": planning_seeds,
        "repository_evidence_contract": repo_contract,
        "repository_evidence": repository_evidence,
        "repo_evidence_status": repository_evidence.get("repo_evidence_status")
        or repository_evidence.get("status"),
        "dita_spec_evidence": dita_chunks,
        "publishing_transform_context": publishing_context,
        "jira_history_searches": jira_history_searches,
        "qa_studio_preview": qa_preview,
        "evidence_graph": evidence_graph,
        "include_evidence_graph": bool(include_evidence_graph),
        "evidence_graph_influence_mode": graph_mode,
        "evidence_graph_evaluation": graph_evaluation,
        "graph_max_paths": max(1, min(int(graph_max_paths or 20), 50)),
        "skip_uac_label_gate": bool(skip_uac_label_gate),
        "full_rag": bool(full_rag),
        "canonical_runtime_contract": {
            "runtime_id": "aem-guides-test-plan-runtime",
            "packet_role": "evidence_only",
            "reasoning_owner": "CanonicalTestPlanRuntime",
            "final_renderer": "FinalQEPlanRenderer",
            "caller_reasoning_allowed": False,
        },
    }
    packet["evidence_snapshot"] = _build_packet_evidence_snapshot(packet)
    return packet


# Evidence collection is an input stage, not another reasoning pipeline.
build_guides_test_plan_evidence_packet = _collect_guides_test_plan_evidence_packet


def _build_packet_evidence_snapshot(packet: dict[str, Any]) -> dict[str, Any]:
    """Freeze evidence identities so later reviews can reproduce what shaped the plan."""
    issue = packet.get("issue") if isinstance(packet.get("issue"), dict) else {}
    graph = (
        packet.get("evidence_graph")
        if isinstance(packet.get("evidence_graph"), dict)
        else {}
    )
    history = packet.get("jira_history_searches") or {}
    history_rows = [
        row
        for scope in ("same_customer", "cross_customer")
        for row in (history.get(scope) or {}).get("results") or []
        if isinstance(row, dict)
    ]
    doc_ids = sorted(
        {
            str(
                row.get("source_hash")
                or row.get("chunk_id")
                or row.get("canonical_url")
                or row.get("source_url")
                or ""
            )
            for row in packet.get("experience_league_evidence") or []
            if isinstance(row, dict)
            and str(
                row.get("source_hash")
                or row.get("chunk_id")
                or row.get("canonical_url")
                or row.get("source_url")
                or ""
            )
        }
    )
    learned_ids = sorted(
        {
            str(
                row.get("source_hash")
                or row.get("chunk_id")
                or row.get("canonical_url")
                or ""
            )
            for row in (packet.get("learned_behavior_evidence") or {}).get("results")
            or []
            if isinstance(row, dict)
            and str(
                row.get("source_hash")
                or row.get("chunk_id")
                or row.get("canonical_url")
                or ""
            )
        }
    )
    graph_leaf_ids = sorted(
        {
            str(citation.get("leaf_id") or citation.get("source_hash") or "")
            for path in graph.get("evidence_paths") or []
            for citation in path.get("leaf_citations") or []
            if str(citation.get("leaf_id") or citation.get("source_hash") or "")
        }
    )
    repo_revisions = sorted(
        {
            str(
                repo.get("post_sync_sha")
                or repo.get("head_sha")
                or repo.get("commit_sha")
                or ""
            )
            for repo in (packet.get("repository_evidence") or {}).get("repositories")
            or []
            if isinstance(repo, dict)
            and str(
                repo.get("post_sync_sha")
                or repo.get("head_sha")
                or repo.get("commit_sha")
                or ""
            )
        }
    )
    issue_payload = {
        "jira_key": packet.get("jira_key"),
        "source": issue.get("source") or issue.get("lookup_source"),
        "status": issue.get("status"),
        "resolution": issue.get("resolution"),
        "affected_versions": issue.get("affected_versions") or [],
        "fix_versions": issue.get("fix_versions") or [],
        "current_uac_snapshot_id": (packet.get("current_uac_contract") or {}).get(
            "source_snapshot_id"
        ),
    }
    snapshot_inputs = {
        "issue": issue_payload,
        "documentation_sources": doc_ids,
        "learned_behavior_sources": learned_ids,
        "history_query_fingerprints": sorted(
            {
                str((history.get(scope) or {}).get("query_fingerprint") or "")
                for scope in ("same_customer", "cross_customer")
                if str((history.get(scope) or {}).get("query_fingerprint") or "")
            }
        ),
        "historical_snapshot_ids": sorted(
            {
                str(row.get("evidence_snapshot_id") or "")
                for row in history_rows
                if str(row.get("evidence_snapshot_id") or "")
            }
        ),
        "graph_generation_id": (graph.get("generation") or {}).get("id"),
        "graph_leaf_ids": graph_leaf_ids,
        "repository_revisions": repo_revisions,
    }
    canonical = json.dumps(
        snapshot_inputs, sort_keys=True, separators=(",", ":"), default=str
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "schema_version": "test-plan-evidence-snapshot-v1",
        "fingerprint": fingerprint,
        "snapshot_id": f"evidence:{packet.get('jira_key')}:{fingerprint}",
        "inputs": snapshot_inputs,
        "mutable_jira_facts_verified_live": str(issue.get("source") or "")
        == "jira_api",
        "immutable": True,
    }


def render_guides_test_plan_packet_markdown(packet: dict[str, Any]) -> str:
    """Render canonical output, or an explicitly non-final evidence diagnostic."""
    if packet.get("projection_version") == "canonical-result-compatibility-v2":
        return str(packet.get("plan_markdown") or "")

    key = packet.get("jira_key", "")
    lines = [
        f"# Canonical Test Plan evidence packet: {key}",
        "",
        "Diagnostic input only. The canonical runtime owns reasoning, gates, and final rendering.",
        "",
        "## Runtime contract",
        "",
        _json_block(packet.get("canonical_runtime_contract") or {}),
    ]
    lines.extend(
        [
            "",
            "## Jira evidence",
            "",
            _json_block(packet.get("issue") or {}),
            "",
            "## Experience League evidence",
            "",
            _json_block(packet.get("experience_league_evidence") or []),
            "",
            "## Learned behavior evidence from scraped DITA",
            "",
            _json_block(packet.get("learned_behavior_evidence") or {}),
            "",
            "## Derived planning seeds",
            "",
            _json_block(packet.get("planning_seeds") or {}),
            "",
            "## Local repository evidence scan",
            "",
            _json_block(packet.get("repository_evidence") or {}),
            "",
            "## Local repository evidence contract",
            "",
            _json_block(packet.get("repository_evidence_contract") or {}),
            "",
            "## DITA/spec evidence",
            "",
            _json_block(packet.get("dita_spec_evidence") or []),
            "",
            "## Publishing / DITA-OT evidence",
            "",
            _json_block(packet.get("publishing_transform_context") or {}),
            "",
            "## Direct Jira history searches",
            "",
            _json_block(packet.get("jira_history_searches") or {}),
            "",
            "## QA Studio preview",
            "",
            _json_block(packet.get("qa_studio_preview") or {}),
            "",
            "## Evidence graph traceability",
            "",
            _json_block(packet.get("evidence_graph") or {}),
            "",
        ]
    )
    return "\n".join(lines)


def _list_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        result = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("name") or item.get("value") or "").strip()
            else:
                text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return [value.strip()]
        return _list_values(parsed)
    return []


def _graph_issue_selectors(
    issue: dict[str, Any], planning_seeds: dict[str, Any]
) -> dict[str, Any]:
    from app.services.jira_component_metadata_service import canonical_component_names

    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    components = canonical_component_names(
        _list_values(issue.get("components")) + _list_values(fields.get("components"))
    )
    customers = []
    for key in ("customer", "customer_name", "customer_names", "company_names"):
        customers.extend(_list_values(issue.get(key)))
    return {
        "customer": customers[0] if customers else "",
        "component": components[0] if components else "",
        "outputs": [
            str(value)
            for value in (planning_seeds.get("outputs") or [])
            if str(value).strip()
        ],
        "dita_entities": [
            str(value)
            for value in (planning_seeds.get("constructs") or [])
            if str(value).strip()
        ],
    }


def _customer_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _history_scope_result(
    result: dict[str, Any],
    *,
    scope: str,
    excluded_customer: str = "",
) -> dict[str, Any]:
    scoped = {**result, "scope": scope}
    rows = []
    excluded_identity = _customer_identity(excluded_customer)
    for raw in result.get("results") or []:
        if not isinstance(raw, dict):
            continue
        row_customers = [
            str(raw.get("customer") or ""),
            *[str(x) for x in raw.get("customers") or []],
        ]
        if excluded_identity and any(
            _customer_identity(value) == excluded_identity for value in row_customers
        ):
            continue
        rows.append(
            {**raw, "evidence_origin": "search_jira_history", "search_scope": scope}
        )
    scoped["results"] = rows
    scoped["match_count"] = len(rows)
    if excluded_customer:
        scoped["excluded_customer"] = excluded_customer
    if result.get("searched_jira_qa"):
        scoped["status"] = "searched"
    else:
        scoped["status"] = "degraded"
    return scoped


def _retrieve_direct_jira_history(
    jira_key: str,
    issue: dict[str, Any],
    query: str,
    planning_seeds: dict[str, Any],
    *,
    top_k: int,
) -> dict[str, Any]:
    selectors = _graph_issue_selectors(issue, planning_seeds)
    customer = str(selectors.get("customer") or "").strip()
    component = str(selectors.get("component") or "").strip()
    from app.services.jira_history_search_service import search_jira_history_evidence

    def safe_search(
        *, selected_customer: str = "", selected_top_k: int = top_k
    ) -> dict[str, Any]:
        try:
            return search_jira_history_evidence(
                query,
                component=component,
                customer=selected_customer,
                exclude_jira_key=jira_key,
                top_k=selected_top_k,
                current_affected_versions=issue.get("affected_versions"),
                current_fix_versions=issue.get("fix_versions"),
            )
        except Exception as exc:
            return {
                "searched_jira_qa": False,
                "indexed_chunks": None,
                "component_filter": component or None,
                "customer_filter": selected_customer or None,
                "match_count": 0,
                "results": [],
                "note": "Jira history retrieval failed; do not infer that matching history is absent.",
                "error": f"{type(exc).__name__}: {exc}",
            }

    if customer:
        same_customer = _history_scope_result(
            safe_search(selected_customer=customer),
            scope="same_customer",
        )
    else:
        same_customer = {
            "scope": "same_customer",
            "status": "not_applicable",
            "searched_jira_qa": False,
            "indexed_chunks": None,
            "component_filter": component or None,
            "customer_filter": None,
            "match_count": 0,
            "results": [],
            "note": "Current Jira customer is unavailable; same-customer history cannot be selected deterministically.",
        }

    cross_customer = _history_scope_result(
        safe_search(selected_top_k=min(30, top_k * 2)),
        scope="cross_customer",
        excluded_customer=customer,
    )
    warnings = []
    for scoped in (same_customer, cross_customer):
        if scoped.get("status") == "degraded":
            warnings.append(
                f"{scoped['scope']} Jira history retrieval was unavailable."
            )
    if same_customer.get("status") == "not_applicable":
        warnings.append(
            "Same-customer Jira history was not searchable because the current customer is unknown."
        )
    return {
        "query": query,
        "selectors": selectors,
        "same_customer": same_customer,
        "cross_customer": cross_customer,
        "warnings": warnings,
    }


def _add_direct_jira_history_seeds(
    planning_seeds: dict[str, Any],
    searches: dict[str, Any],
) -> dict[str, Any]:
    result = {**planning_seeds}
    rows = []
    seen: set[str] = set()
    for scope in ("same_customer", "cross_customer"):
        for item in (searches.get(scope) or {}).get("results") or []:
            jira_key = str(item.get("jira_key") or "").strip().upper()
            if not jira_key or jira_key in seen:
                continue
            seen.add(jira_key)
            rows.append(
                {
                    "jira_key": jira_key,
                    "summary": item.get("summary") or "",
                    "why_similar": item.get("why_similar") or "",
                    "historical_match": item.get("historical_match") or {},
                    "historical_uac_contract": item.get("historical_uac_contract")
                    or {},
                    "version_applicability": item.get("version_applicability") or {},
                    "evidence_snapshot_id": item.get("evidence_snapshot_id") or "",
                    "root_cause": item.get("root_cause") or "",
                    "qa_oracle": item.get("qa_oracle") or "",
                    "historical_outcome": item.get("historical_outcome") or "",
                    "is_verified_fix": item.get("is_verified_fix"),
                    "mutable_facts": item.get("mutable_facts") or {},
                    "search_scope": scope,
                    "evidence_origin": "search_jira_history",
                    "evidence": [f"JIRA:{jira_key}"],
                    "mutable_facts_require_live_validation": True,
                }
            )
    result["direct_jira_history_seed"] = rows[:20]
    return result


def _retrieve_evidence_graph(
    jira_key: str,
    issue: dict[str, Any],
    query: str,
    planning_seeds: dict[str, Any],
    *,
    tenant_id: str,
    enabled: bool,
    max_paths: int,
    allow_cross_customer_details: bool,
    influence_mode: str = "interactive",
) -> dict[str, Any]:
    if not enabled:
        return {
            "available": False,
            "status": "skipped",
            "warnings": ["Evidence graph disabled for this request."],
        }
    if os.getenv("EVIDENCE_GRAPH_ENABLED", "false").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return {
            "available": False,
            "status": "disabled",
            "coverage_gaps": [
                "Evidence graph querying is disabled on this deployment."
            ],
            "warnings": [],
        }
    selectors = _graph_issue_selectors(issue, planning_seeds)
    try:
        from app.services.evidence_graph_query_service import query_test_evidence_graph

        return query_test_evidence_graph(
            query,
            jira_key=jira_key,
            customer=selectors["customer"],
            component=selectors["component"],
            outputs=selectors["outputs"],
            dita_entities=selectors["dita_entities"],
            include_cross_customer=True,
            max_depth=2,
            top_k=10,
            max_paths=max(1, min(int(max_paths or 20), 50)),
            tenant_id=tenant_id,
            allow_cross_customer_details=allow_cross_customer_details,
            actor_id="test-plan-pipeline",
            influence_mode=influence_mode,
        )
    except Exception as exc:
        return {
            "available": False,
            "status": "degraded",
            "coverage_gaps": [
                "Evidence graph query failed; direct Jira/RAG evidence remains authoritative."
            ],
            "warnings": [f"{type(exc).__name__}: {exc}"],
        }


def _leaf_ids(item: dict[str, Any]) -> list[str]:
    return list(
        dict.fromkeys(
            str(citation.get("leaf_id") or "")
            for citation in (item.get("leaf_citations") or [])
            if str(citation.get("leaf_id") or "")
        )
    )


def _add_evidence_graph_seeds(
    planning_seeds: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any]:
    result = {**planning_seeds}
    result["evidence_graph_generation_id"] = (graph.get("generation") or {}).get("id")
    result["evidence_graph_path_ids"] = [
        str(path.get("path_id"))
        for path in (graph.get("evidence_paths") or [])
        if path.get("path_id")
    ]
    result["evidence_graph_leaf_ids"] = list(
        dict.fromkeys(
            leaf_id
            for path in (graph.get("evidence_paths") or [])
            for leaf_id in _leaf_ids(path)
        )
    )
    result["documented_behavior_seed"] = [
        {
            "behavior": item.get("behavior"),
            "trust_tier": item.get("trust_tier"),
            "evidence": _leaf_ids(item),
        }
        for item in (graph.get("documented_behaviors") or [])
        if item.get("behavior") and item.get("trust_tier") != "candidate"
    ][:8]
    result["historical_jira_seed"] = [
        {
            "jira_key": item.get("jira_key"),
            "summary": item.get("summary"),
            "shared_mechanisms": item.get("shared_mechanisms") or [],
            "evidence": _leaf_ids(item),
            "mutable_facts_require_live_validation": True,
        }
        for item in (graph.get("same_mechanism_jira_history") or [])
        if item.get("jira_key")
    ][:10]
    risks = list(result.get("regression_risk_seed") or [])
    existing = {
        str(item.get("rationale") or item) for item in risks if isinstance(item, dict)
    }
    for index, item in enumerate(graph.get("regression_signals") or [], 1):
        signal = str(item.get("signal") or "").strip()
        if not signal or signal in existing:
            continue
        risks.append(
            {
                "id": f"GRAPH-RR-{index:02d}",
                "category": str(item.get("type") or "graph regression signal"),
                "priority": "P1",
                "rationale": signal,
                "evidence": _leaf_ids(item),
                "trust_tier": item.get("trust_tier"),
                "cannot_define_expected_behavior": not bool(
                    item.get("usable_as_expected_behavior")
                ),
            }
        )
        existing.add(signal)
    result["regression_risk_seed"] = risks
    return result


def _lookup_issue(jira_key: str, *, tenant_id: str) -> dict[str, Any]:
    direct = _fetch_issue_direct(jira_key, tenant_id=tenant_id)
    if direct:
        return direct

    try:
        from app.services.jira_chat_search_service import search_related_jira_issues

        result = search_related_jira_issues(
            jira_key, tenant_id=tenant_id, max_results=5
        )
    except Exception as exc:
        return {
            "issue_key": jira_key,
            "lookup_error": str(exc),
            "source": "unavailable",
        }

    issues = result.get("issues") or []
    exact = next(
        (
            issue
            for issue in issues
            if str(issue.get("issue_key") or issue.get("key") or "").upper() == jira_key
        ),
        issues[0] if issues else None,
    )
    if not exact:
        return {
            "issue_key": jira_key,
            "source": result.get("source", "unavailable"),
            "lookup_message": result.get("message", "No matching Jira issue found."),
        }
    issue = dict(exact)
    issue.setdefault("issue_key", jira_key)
    issue["lookup_source"] = result.get("source", "")
    issue["lookup_message"] = result.get("message", "")
    return issue


def _fetch_issue_direct(jira_key: str, *, tenant_id: str) -> dict[str, Any] | None:
    """Fetch explicit Jira keys via REST API (supports JIRA_PAT bearer auth)."""
    if not _JIRA_KEY_RE.fullmatch((jira_key or "").strip().upper()):
        return None
    try:
        from app.services.jira_client import (
            JiraClient,
            extract_description_from_issue,
            extract_named_issue_field,
        )
        from app.services.tenant_service import build_jira_client

        client = build_jira_client(tenant_id)
        if not client.is_configured():
            client = JiraClient()
        if not client.is_configured():
            return None

        get_with_names = getattr(client, "get_issue_with_names", None)
        raw = (
            get_with_names(jira_key)
            if callable(get_with_names)
            else client.get_issue(jira_key)
        )
        fields = raw.get("fields") or {}
        acceptance_criteria, acceptance_field_id, acceptance_field_name = (
            extract_named_issue_field(
                raw,
                ("Acceptance Criteria", "Acceptance Criterion", "UAC"),
                explicit_field_id=os.getenv(
                    "JIRA_ACCEPTANCE_CRITERIA_FIELD_ID", ""
                ).strip(),
            )
        )
        expected_behavior, _, _ = extract_named_issue_field(
            raw,
            ("Expected Result", "Expected Behavior", "Expected Behaviour"),
            explicit_field_id=os.getenv("JIRA_EXPECTED_BEHAVIOR_FIELD_ID", "").strip(),
        )
        actual_behavior, _, _ = extract_named_issue_field(
            raw,
            ("Actual Result", "Actual Behavior", "Actual Behaviour"),
            explicit_field_id=os.getenv("JIRA_ACTUAL_BEHAVIOR_FIELD_ID", "").strip(),
        )
        components = [
            str(item.get("name") or "")
            for item in (fields.get("components") or [])
            if isinstance(item, dict) and item.get("name")
        ]
        return {
            "issue_key": raw.get("key", jira_key),
            "summary": fields.get("summary", ""),
            "description": extract_description_from_issue(raw),
            "status": (fields.get("status") or {}).get("name", ""),
            "issue_type": (fields.get("issuetype") or {}).get("name", ""),
            "priority": (fields.get("priority") or {}).get("name", ""),
            "resolution": (fields.get("resolution") or {}).get("name", ""),
            "labels": fields.get("labels") or [],
            "components": components,
            "fix_versions": [
                str(item.get("name") or "")
                for item in (fields.get("fixVersions") or [])
                if isinstance(item, dict) and item.get("name")
            ],
            "affected_versions": [
                str(item.get("name") or "")
                for item in (fields.get("versions") or [])
                if isinstance(item, dict) and item.get("name")
            ],
            "acceptance_criteria": acceptance_criteria,
            "acceptance_criteria_field_id": acceptance_field_id,
            "acceptance_criteria_field_name": acceptance_field_name,
            "acceptance_criteria_source": "jira_live_named_field"
            if acceptance_criteria
            else "missing",
            "expected_behavior": expected_behavior,
            "actual_behavior": actual_behavior,
            "source": "jira_api",
            "lookup_source": "jira_api_direct",
            "lookup_message": f"Fetched `{raw.get('key', jira_key)}` directly from Jira API.",
            "url": f"{client.base_url.rstrip('/')}/browse/{raw.get('key', jira_key)}"
            if client.base_url
            else "",
        }
    except Exception as exc:
        indexed = _fetch_issue_indexed_by_key(jira_key, tenant_id=tenant_id)
        if indexed:
            indexed["lookup_message"] = (
                f"Live Jira API unavailable ({exc}); using indexed cache for `{jira_key}`."
            )
            return indexed
        return None


def _fetch_issue_indexed_by_key(
    jira_key: str, *, tenant_id: str
) -> dict[str, Any] | None:
    """Exact-key lookup from indexed Jira cache when live REST is unavailable."""
    key = (jira_key or "").strip().upper()
    if not _JIRA_KEY_RE.fullmatch(key):
        return None
    try:
        from app.services.jira_chat_search_service import search_related_jira_issues

        result = search_related_jira_issues(key, tenant_id=tenant_id, max_results=5)
        for issue in result.get("issues") or []:
            issue_key = str(issue.get("issue_key") or issue.get("key") or "").upper()
            if issue_key == key:
                normalized = dict(issue)
                normalized.setdefault("issue_key", key)
                normalized["lookup_source"] = result.get("source", "jira_index")
                normalized.setdefault("source", normalized["lookup_source"])
                return normalized
    except Exception:
        return None
    return None


def _issue_query_text(jira_key: str, issue: dict[str, Any]) -> str:
    labels = _issue_labels(issue)
    parts = [
        jira_key,
        str(issue.get("summary") or ""),
        str(issue.get("title") or ""),
        str(issue.get("description") or ""),
        str(issue.get("snippet") or ""),
        str(issue.get("status") or ""),
        " ".join(labels),
    ]
    return "\n".join(part for part in parts if part.strip()) or jira_key


def _issue_labels(issue: dict[str, Any]) -> list[str]:
    raw = (
        issue.get("labels") or issue.get("label_names") or issue.get("components") or []
    )
    labels: list[str] = []
    if isinstance(raw, str):
        labels.extend(
            part.strip() for part in re.split(r"[,;\s]+", raw) if part.strip()
        )
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                labels.append(item)
            elif isinstance(item, dict):
                value = item.get("name") or item.get("value") or item.get("label")
                if value:
                    labels.append(str(value))
    return sorted(set(labels), key=str.lower)


def is_publishing_transform_ticket(issue: dict[str, Any]) -> bool:
    """True for Jira issues explicitly related to publishing/PDF2/HTML/HTML5/DITA-OT."""
    labels = {label.strip().lower().replace(" ", "-") for label in _issue_labels(issue)}
    if labels & _PUBLISHING_LABEL_TERMS:
        return True
    text = "\n".join(
        str(issue.get(key) or "")
        for key in ("summary", "title", "description", "snippet", "issue_key")
    )
    return bool(_PUBLISHING_TEXT_RE.search(text))


def _build_publishing_transform_context(
    issue: dict[str, Any], query: str, *, k: int
) -> dict[str, Any]:
    labels = _issue_labels(issue)
    enabled = is_publishing_transform_ticket(issue)
    context: dict[str, Any] = {
        "enabled": enabled,
        "gate": "publishing/pdf2/html/html5/dita-ot label-or-text",
        "detected_labels": labels,
        "required_for_test_plan": enabled,
        "dita_ot_evidence": [],
    }
    if not enabled:
        context["message"] = (
            "DITA-OT publishing evidence is gated off because this Jira issue is not "
            "detected as publishing/PDF2/HTML/HTML5/transformation-related."
        )
        return context

    publishing_query = "\n".join(
        part
        for part in [
            query,
            "DITA-OT publishing transformation PDF2 HTML5 output preset native PDF known issue regression",
        ]
        if part.strip()
    )
    try:
        from app.services.dita_ot_github_rag_service import (
            retrieve_dita_ot_github_for_query,
        )

        context["dita_ot_evidence"] = (
            retrieve_dita_ot_github_for_query(publishing_query, k=k) or []
        )
        context["source"] = "dita_ot_github_rag_service"
    except Exception as exc:
        context["error"] = str(exc)
    return context


def _retrieve_aem_docs(query: str, *, k: int) -> list[dict[str, Any]]:
    try:
        from app.services.doc_retriever_service import retrieve_relevant_docs

        docs = retrieve_relevant_docs(
            query,
            k=k,
            allowed_host_suffixes=("experienceleague.adobe.com",),
        )
    except Exception as exc:
        return [{"error": str(exc)}]
    return [
        {
            "chunk_id": doc.get("chunk_id", ""),
            "title": doc.get("title", ""),
            "source_url": doc.get("source_url") or doc.get("url", ""),
            "canonical_url": doc.get("canonical_url") or doc.get("url", ""),
            "snippet": doc.get("snippet", ""),
            "corpus": doc.get("corpus", "aem_guides"),
            "evidence_type": doc.get("evidence_type", ""),
        }
        for doc in docs
    ]


def _retrieve_learned_behavior_evidence(query: str, *, k: int) -> dict[str, Any]:
    behavior_query = "\n".join(
        part
        for part in [
            query,
            "Learned feature behavior from scraped Experience League DITA. "
            "Prefer chunks with Generation requirement, QA checklist, PDF review areas, HTML5 review areas, "
            "negative/risk cases, output preset, publishing, workflow, metadata, baseline, translation, reports.",
        ]
        if part.strip()
    )
    try:
        from app.services.doc_retriever_service import (
            retrieve_relevant_docs_with_diagnostics,
        )

        payload = retrieve_relevant_docs_with_diagnostics(
            behavior_query,
            k=max(k * 2, 8),
            allowed_host_suffixes=("experienceleague.adobe.com",),
        )
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
            "results": [],
            "expected_planner_use": [
                "Keep the plan Draft if scraped Experience League behavior evidence is unavailable.",
            ],
        }

    raw_results = list(payload.get("results") or [])
    behavior_results = [doc for doc in raw_results if _is_learned_behavior_doc(doc)]
    selected = behavior_results[:k] if behavior_results else raw_results[:k]
    return {
        "available": bool(selected),
        "retrieval_mode": payload.get("retrieval_mode", "unknown"),
        "semantic_required": payload.get("semantic_required", False),
        "warnings": payload.get("warnings", []),
        "source": "scraped_experienceleague_dita_behavior_chunks",
        "result_count": len(selected),
        "results": [_normalize_behavior_doc(doc) for doc in selected],
        "expected_planner_use": [
            "Use these chunks to summarize expected AEM Guides behavior before scenario design.",
            "Convert generation requirements into test data, QA checklist items, PDF review areas, HTML5 review areas, negative/risk cases, and validation oracles.",
            "Trace scenarios and residual risks to source_url/canonical_url; do not treat scraped docs as Jira facts.",
            "If this section is unavailable or weak, mark the test plan Draft due to missing RAG behavior evidence.",
        ],
    }


def _is_learned_behavior_doc(doc: dict[str, Any]) -> bool:
    evidence_type = str(doc.get("evidence_type") or "").lower()
    snippet = str(doc.get("snippet") or "").lower()
    return bool(
        "learned_behavior" in evidence_type
        or "enriched_" in evidence_type
        or "learned feature behavior:" in snippet
        or "generation requirement:" in snippet
        or "how to use this in rag:" in snippet
    )


def _normalize_behavior_doc(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": doc.get("chunk_id", ""),
        "title": doc.get("title", ""),
        "source_url": doc.get("source_url") or doc.get("url", ""),
        "canonical_url": doc.get("canonical_url") or doc.get("url", ""),
        "corpus": doc.get("corpus", "aem_guides"),
        "evidence_type": doc.get("evidence_type", ""),
        "snippet": doc.get("snippet", ""),
    }


def _derive_planning_seeds(
    issue: dict[str, Any], learned_behavior: dict[str, Any]
) -> dict[str, Any]:
    results = (
        list(learned_behavior.get("results") or [])
        if isinstance(learned_behavior, dict)
        else []
    )
    snippets = "\n\n".join(
        str(item.get("snippet") or "") for item in results if isinstance(item, dict)
    )
    issue_text = "\n".join(
        str(issue.get(key) or "")
        for key in ("issue_key", "summary", "title", "description", "snippet", "status")
    )
    combined_text = "\n\n".join(part for part in (issue_text, snippets) if part.strip())
    lowered = combined_text.lower()
    source_ids = [
        str(
            item.get("chunk_id")
            or item.get("source_url")
            or item.get("canonical_url")
            or ""
        ).strip()
        for item in results
        if isinstance(item, dict)
        and str(
            item.get("chunk_id")
            or item.get("source_url")
            or item.get("canonical_url")
            or ""
        ).strip()
    ][:8]

    features = _augment_features_from_issue(
        _extract_seed_values(snippets, "Learned feature behavior"), lowered
    )
    constructs = _augment_constructs_from_issue(
        _extract_seed_values(snippets, "Detected DITA constructs and attributes"),
        lowered,
    )
    outputs = _augment_outputs_from_issue(
        _extract_seed_values(snippets, "Publishing/output contexts"), lowered
    )
    evidence = source_ids or ["learned_behavior_evidence"]

    blast_radius = _build_blast_radius_seed(
        features, constructs, outputs, lowered, evidence
    )
    bug_hypotheses = _build_bug_hypothesis_seed(constructs, outputs, lowered, evidence)
    test_areas = _build_test_area_seed(features, constructs, outputs, lowered, evidence)
    regression_risks = _build_regression_risk_seed(
        features, constructs, outputs, lowered, evidence
    )

    if not results:
        missing_reason = "No scraped Experience League learned-behavior chunks were retrieved for this Jira/query."
        blast_radius.append(
            _seed(
                "BR-MISSING-BEHAVIOR",
                "Observability/Recovery",
                "High",
                missing_reason,
                evidence,
            )
        )
        bug_hypotheses.append(
            _seed("BH-MISSING-BEHAVIOR", "Evidence gap", "P1", missing_reason, evidence)
        )
        test_areas.append(
            _seed(
                "TA-MISSING-BEHAVIOR", "Evidence intake", "P1", missing_reason, evidence
            )
        )
        regression_risks.append(
            _seed(
                "RR-MISSING-BEHAVIOR",
                "Release confidence",
                "P1",
                missing_reason,
                evidence,
            )
        )

    return {
        "source": "derived_from_learned_behavior_evidence",
        "evidence_ids": evidence,
        "features": features,
        "constructs": constructs,
        "outputs": outputs,
        "blast_radius_seed": blast_radius,
        "bug_hypothesis_seed": bug_hypotheses,
        "test_area_seed": test_areas,
        "regression_risk_seed": regression_risks,
        "planner_contract": [
            "Each P0/P1 seed must map to a scenario or evidence-backed exclusion.",
            "Blast-radius seeds must appear before scenario design.",
            "Bug hypotheses must influence negative, recovery, or failure-injection coverage.",
            "Regression risks must be split across PR Gate, Component Regression, Nightly, Release Regression, or Exploratory packs.",
            "If learned_behavior_evidence is missing or unrelated, keep Review status as Draft.",
        ],
    }


def _build_repository_evidence_contract(
    issue: dict[str, Any], planning_seeds: dict[str, Any]
) -> dict[str, Any]:
    issue_text = "\n".join(
        str(issue.get(key) or "")
        for key in ("issue_key", "summary", "title", "description", "snippet")
    )
    seed_text = json.dumps(planning_seeds, ensure_ascii=False, default=str)
    lowered = f"{issue_text}\n{seed_text}".lower()

    repos = [
        {
            "id": "xmleditor",
            "owner_role": "frontend",
            "purpose": "AEM Guides XML Editor product code; inspect UI entry points, service calls, state management, error rendering, and editor/report integration.",
            "path_env": "XML_EDITOR_REPO_PATH",
            "fallback_path_hints": ["../xmleditor", "../xml-editor", "../guides-ui"],
            "evidence_to_collect": [
                "Changed files or suspected owners for the feature entry point.",
                "Frontend/backend API call path and request/response contract.",
                "Error handling, loading states, pagination/lazy loading, cache/state cleanup.",
            ],
        },
        {
            "id": "starling",
            "owner_role": "backend",
            "purpose": "Starling/AEM Guides service code; inspect backend endpoints, report/snippet services, persistence, async jobs, and exception mapping.",
            "path_env": "STARLING_REPO_PATH",
            "fallback_path_hints": ["../starling", "../guides-starling", "../dxml"],
            "evidence_to_collect": [
                "Servlet/API endpoint implementation and validators.",
                "Shared callers and downstream services.",
                "Server-side limits, batching, retries, logging, and exception contracts.",
            ],
        },
        {
            "id": "guides-ui-tests",
            "owner_role": "frontend_qa_automation",
            "purpose": "UI automation coverage; inspect existing Playwright/Selenium/Behave/Page Object tests and selectors.",
            "path_env": "GUIDES_UI_TESTS_REPO_PATH",
            "fallback_path_hints": ["../guides-ui-tests", "../ui-tests"],
            "evidence_to_collect": [
                "Existing tests covering the feature or adjacent workflows.",
                "Reusable page objects/selectors and gaps.",
                "Automation strength classification: Exact and strong, weak oracle, partial, obsolete, mocked-only, or missing.",
            ],
        },
        {
            "id": "dxml-it-tests",
            "owner_role": "backend_qa_automation",
            "purpose": "Integration/API test coverage; inspect endpoint, persistence, publishing/report, and regression tests.",
            "path_env": "DXML_IT_TESTS_REPO_PATH",
            "fallback_path_hints": [
                "../dxml-it-tests",
                "../dxml-it",
                "../integration-tests",
            ],
            "evidence_to_collect": [
                "Existing API/integration tests for the affected endpoint or shared service.",
                "Test data builders and environment assumptions.",
                "Regression gaps for negative, recovery, scale, and compatibility coverage.",
            ],
        },
    ]

    focus_queries = [
        str(issue.get("issue_key") or ""),
        str(issue.get("summary") or issue.get("title") or ""),
    ]
    if "snippet" in lowered:
        focus_queries.extend(
            [
                "/bin/fmdita/config/snippets",
                "snippets",
                "colwidth",
                "URLDecoder",
                "application/x-www-form-urlencoded",
            ]
        )
    if "broken links" in lowered or "report" in lowered:
        focus_queries.extend(
            [
                "Broken Links Report",
                "Fetching details for broken links",
                "reports",
                "large map",
                "pagination",
                "lazy loading",
            ]
        )
    if "schematron" in lowered:
        focus_queries.extend(
            [
                "schematron",
                "/bin/dxml/schematron",
                "Workspace Settings",
                "validate on save",
                "XSLT",
            ]
        )
    if "publishing" in lowered or "html5" in lowered or "pdf" in lowered:
        focus_queries.extend(
            ["output preset", "DITA-OT", "Native PDF", "HTML5", "publishing"]
        )

    return {
        "source": "local_clone_required",
        "why_required": (
            "The central VM MCP/RAG can provide Jira and documentation evidence, but it cannot inspect a developer or QA engineer's local cloned product/test repositories unless those paths are mounted or the MCP runs locally."
        ),
        "required_repositories": repos,
        "focus_queries": _dedupe([item for item in focus_queries if item.strip()])[:16],
        "role_based_evidence_gates": [
            {
                "owner_role": "frontend",
                "primary_repo": "xmleditor",
                "must_answer": [
                    "Which UI route/component invokes the affected feature?",
                    "What API payload, loading state, pagination/lazy loading, and error UI behavior changes?",
                    "Which UI automation or page-object coverage proves the user-visible contract?",
                ],
                "automation_repo": "guides-ui-tests",
            },
            {
                "owner_role": "backend",
                "primary_repo": "starling",
                "must_answer": [
                    "Which servlet/service/parser/validator endpoint owns the request?",
                    "What validation, exception mapping, persistence, logging, and scalability contracts change?",
                    "Which API/integration test proves backend behavior and recovery?",
                ],
                "automation_repo": "dxml-it-tests",
            },
            {
                "owner_role": "qa_or_release_owner",
                "primary_repo": "guides-ui-tests + dxml-it-tests",
                "must_answer": [
                    "Do frontend and backend tests assert the same observable oracle?",
                    "Are exact, weak, partial, obsolete, mocked-only, and missing automation paths classified?",
                    "Which risks stay Draft because xmleditor/starling evidence is unavailable?",
                ],
                "automation_repo": "guides-ui-tests + dxml-it-tests",
            },
        ],
        "minimum_evidence_before_review_ready": [
            "Frontend-impacting changes inspect xmleditor and guides-ui-tests, or include an evidence-backed reason they are unavailable.",
            "Backend-impacting changes inspect starling and dxml-it-tests, or include an evidence-backed reason they are unavailable.",
            "Cross-layer changes inspect both xmleditor and starling, plus at least one UI and one API/integration automation path.",
            "Existing coverage classified for each affected direct/shared path.",
            "Missing repo evidence forces Review status: Draft.",
        ],
        "expected_plan_sections_to_update": [
            "Evidence intake",
            "Evidence map",
            "Blast radius and risk analysis",
            "Kill the Fix analysis",
            "Automation strength assessment",
            "Residual Risk and Release Confidence",
        ],
    }


def _augment_features_from_issue(values: list[str], lowered: str) -> list[str]:
    additions: list[str] = []
    if "/bin/fmdita/config/snippets" in lowered or "snippet" in lowered:
        additions.append("snippet-management")
    if (
        "application/x-www-form-urlencoded" in lowered
        or "urlencoded" in lowered
        or "url-encoded" in lowered
    ):
        additions.append("form-urlencoded-api")
    if "urldecoder" in lowered or "illegal hex" in lowered or "%" in lowered:
        additions.append("request-decoding")
    if "api endpoint" in lowered or re.search(r"\bpost\b", lowered):
        additions.append("api-workflow")
    return _dedupe([*values, *additions])


def _augment_constructs_from_issue(values: list[str], lowered: str) -> list[str]:
    additions: list[str] = []
    for token, label in (
        ("colwidth", "colwidth"),
        ("colspec", "colspec"),
        ("tgroup", "tgroup"),
        ("<table", "table"),
        (" table ", "table"),
    ):
        if token in lowered:
            additions.append(label)
    if "%" in lowered or "percentage" in lowered:
        additions.append("percent-character")
    if "xml" in lowered:
        additions.append("embedded-xml-payload")
    return _dedupe([*values, *additions])


def _augment_outputs_from_issue(values: list[str], lowered: str) -> list[str]:
    additions: list[str] = []
    if "cloud" in lowered:
        additions.append("Cloud")
    if "on-prem" in lowered or "on prem" in lowered or "onprem" in lowered:
        additions.append("On-prem")
    if "snippet" in lowered:
        additions.append("Snippet API")
    return _dedupe([*values, *additions])


def _extract_seed_values(text: str, label: str) -> list[str]:
    boundary_labels = (
        "Source page",
        "URL",
        "Documented purpose",
        "Learned feature behavior",
        "Detected DITA constructs and attributes",
        "Publishing/output contexts",
        "How to use this in RAG",
        "Generation requirement",
    )
    values: list[str] = []
    boundary = "|".join(
        re.escape(item) for item in boundary_labels if item.lower() != label.lower()
    )
    pattern = re.compile(
        rf"{re.escape(label)}:\s*(.+?)(?=\s+(?:{boundary}):|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(text or ""):
        raw = re.sub(r"\s+", " ", match.group(1)).strip().strip(".")
        for part in re.split(r"[,;]", raw):
            value = part.strip(" .`")
            if value and value.lower() not in {
                "not explicit in this page",
                "not output-specific",
            }:
                values.append(value)
    return _dedupe(values)[:12]


def _build_blast_radius_seed(
    features: list[str],
    constructs: list[str],
    outputs: list[str],
    lowered: str,
    evidence: list[str],
) -> list[dict[str, Any]]:
    seeds = [
        _seed(
            "BR-ENTRYPOINT",
            "Direct",
            "High",
            "Validate the documented user entry point and workflow touched by the Jira.",
            evidence,
        ),
        _seed(
            "BR-ERROR-CONTRACT",
            "Observability/Recovery",
            "High",
            "Verify user-facing error message, network/API response, logs/jobs, and recovery path.",
            evidence,
        ),
    ]
    for feature in features[:4]:
        seeds.append(
            _seed(
                f"BR-FEATURE-{_seed_slug(feature)}",
                "Shared-path",
                "Medium",
                f"Shared feature behavior may regress: {feature}.",
                evidence,
            )
        )
    for construct in constructs[:5]:
        seeds.append(
            _seed(
                f"BR-CONSTRUCT-{_seed_slug(construct)}",
                "Compatibility",
                "Medium",
                f"DITA construct/attribute interaction may affect parsing, validation, publishing, or persistence: {construct}.",
                evidence,
            )
        )
    for output in outputs[:4]:
        seeds.append(
            _seed(
                f"BR-OUTPUT-{_seed_slug(output)}",
                "Downstream",
                "High",
                f"Downstream output context must be verified: {output}.",
                evidence,
            )
        )
    if "workspace" in lowered or "settings" in lowered:
        seeds.append(
            _seed(
                "BR-CONFIG-INHERITANCE",
                "Shared-path",
                "High",
                "Workspace/folder/profile configuration inheritance can change the effective validation or publishing context.",
                evidence,
            )
        )
    if "publish" in lowered or "output" in lowered or outputs:
        seeds.append(
            _seed(
                "BR-PUBLISHING-PIPELINE",
                "Downstream",
                "High",
                "Publishing pipeline behavior can diverge across Native PDF, DITA-OT PDF, HTML/HTML5, and AEM Sites.",
                evidence,
            )
        )
    if "/bin/fmdita/config/snippets" in lowered or "snippet" in lowered:
        seeds.append(
            _seed(
                "BR-SNIPPET-API",
                "Direct",
                "High",
                "Snippet create/read/update path can fail before DITA validation when request decoding or persistence changes.",
                evidence,
            )
        )
    if (
        "application/x-www-form-urlencoded" in lowered
        or "urldecoder" in lowered
        or "illegal hex" in lowered
        or "%" in lowered
    ):
        seeds.append(
            _seed(
                "BR-FORM-DECODING",
                "Shared-path",
                "High",
                "Form-urlencoded request decoding is a shared boundary for raw percent characters, encoded values, and malformed escape sequences.",
                evidence,
            )
        )
    return _dedupe_seed_dicts(seeds)


def _build_bug_hypothesis_seed(
    constructs: list[str], outputs: list[str], lowered: str, evidence: list[str]
) -> list[dict[str, Any]]:
    seeds = [
        _seed(
            "BH-NULL-EMPTY-MISSING",
            "Null/empty/missing input",
            "P1",
            "Null, empty, missing, or malformed input may be mapped to a misleading generic error.",
            evidence,
        ),
        _seed(
            "BH-PARTIAL-FAILURE",
            "Partial failure",
            "P1",
            "One failing config/resource may block valid sibling resources or hide useful findings.",
            evidence,
        ),
        _seed(
            "BH-RECOVERY-STALE-STATE",
            "Recovery/cache",
            "P1",
            "After correcting the input/config, stale cache or persisted state may keep the failure visible.",
            evidence,
        ),
    ]
    if (
        any("schematron" in item.lower() for item in constructs)
        or "schematron" in lowered
    ):
        seeds.append(
            _seed(
                "BH-SCHEMATRON-XSLT-EXCEPTION",
                "Exception mapping",
                "P0",
                "Schematron/XSLT transform failure may surface as a misleading topic-content error instead of a configuration error.",
                evidence,
            )
        )
    if (
        "urldecoder" in lowered
        or "illegal hex" in lowered
        or "application/x-www-form-urlencoded" in lowered
        or "%" in lowered
    ):
        seeds.append(
            _seed(
                "BH-PERCENT-DECODE-ESCAPE",
                "Encoding/decoding",
                "P0",
                "Raw `%` inside form-urlencoded embedded XML may be interpreted as an incomplete URL escape and fail before snippet creation.",
                evidence,
            )
        )
        seeds.append(
            _seed(
                "BH-DOUBLE-DECODE",
                "Encoding/decoding",
                "P1",
                "A fix may double-decode `%25`, store `%25` instead of `%`, or corrupt valid encoded XML payloads.",
                evidence,
            )
        )
    if "snippet" in lowered:
        seeds.append(
            _seed(
                "BH-SNIPPET-PERSISTENCE-CORRUPTION",
                "Persistence",
                "P1",
                "Snippet creation may report success while storing modified or truncated embedded XML.",
                evidence,
            )
        )
    if any(item for item in outputs) or re.search(
        r"\b(pdf|html5|output|publishing)\b", lowered
    ):
        seeds.append(
            _seed(
                "BH-OUTPUT-DIVERGENCE",
                "Backend/UI/output mismatch",
                "P1",
                "Backend preprocessing can succeed or fail differently from final PDF/HTML5/AEM Sites output review.",
                evidence,
            )
        )
    for construct in constructs[:5]:
        seeds.append(
            _seed(
                f"BH-CONSTRUCT-{_seed_slug(construct)}",
                "Construct interaction",
                "P2",
                f"{construct} can interact with adjacent branches, inherited config, or output transforms in non-obvious ways.",
                evidence,
            )
        )
    return _dedupe_seed_dicts(seeds)


def _build_test_area_seed(
    features: list[str],
    constructs: list[str],
    outputs: list[str],
    lowered: str,
    evidence: list[str],
) -> list[dict[str, Any]]:
    seeds = [
        _seed(
            "TA-REPRODUCTION",
            "Reproduction",
            "P0",
            "Reproduce the reported behavior with minimal controlled data.",
            evidence,
        ),
        _seed(
            "TA-CONTROL",
            "R0 control",
            "P0",
            "Verify unchanged valid behavior still passes with known-good data.",
            evidence,
        ),
        _seed(
            "TA-NEGATIVE",
            "Negative/error handling",
            "P1",
            "Exercise invalid, empty, missing, malformed, and mixed valid/invalid inputs.",
            evidence,
        ),
        _seed(
            "TA-RECOVERY",
            "Recovery",
            "P1",
            "Verify correction/removal/retry restores expected behavior without stale state.",
            evidence,
        ),
    ]
    for feature in features[:4]:
        seeds.append(
            _seed(
                f"TA-FEATURE-{_seed_slug(feature)}",
                "Feature workflow",
                "P1",
                f"Cover documented feature workflow: {feature}.",
                evidence,
            )
        )
    for construct in constructs[:6]:
        seeds.append(
            _seed(
                f"TA-CONSTRUCT-{_seed_slug(construct)}",
                "DITA construct data",
                "P1",
                f"Generate focused data for construct/attribute: {construct}.",
                evidence,
            )
        )
    for output in outputs[:4]:
        seeds.append(
            _seed(
                f"TA-OUTPUT-{_seed_slug(output)}",
                "Output review",
                "P1",
                f"Review generated output context: {output}.",
                evidence,
            )
        )
    if "qa checklist" in lowered:
        seeds.append(
            _seed(
                "TA-DOC-QA-CHECKLIST",
                "Documentation-derived QA",
                "P1",
                "Convert scraped QA checklist guidance into explicit scenario oracles.",
                evidence,
            )
        )
    if "urldecoder" in lowered or "illegal hex" in lowered or "%" in lowered:
        seeds.append(
            _seed(
                "TA-ENCODING-MATRIX",
                "API encoding matrix",
                "P0",
                "Test raw `%`, encoded `%25`, malformed `%ZZ`, percent in adjacent fields, and normal no-percent controls.",
                evidence,
            )
        )
    if "snippet" in lowered:
        seeds.append(
            _seed(
                "TA-SNIPPET-ROUNDTRIP",
                "Persistence round trip",
                "P1",
                "Create, retrieve/list, and use the snippet to prove embedded XML is preserved exactly.",
                evidence,
            )
        )
    if "colwidth" in lowered or "colspec" in lowered:
        seeds.append(
            _seed(
                "TA-TABLE-COLWIDTH-DATA",
                "DITA table data",
                "P1",
                "Generate table snippets with `colspec/@colwidth` percentage, proportional, absolute, and malformed variants.",
                evidence,
            )
        )
    return _dedupe_seed_dicts(seeds)


def _build_regression_risk_seed(
    features: list[str],
    constructs: list[str],
    outputs: list[str],
    lowered: str,
    evidence: list[str],
) -> list[dict[str, Any]]:
    seeds = [
        _seed(
            "RR-R0-CONTROL",
            "PR Gate",
            "P0",
            "Known-good unchanged behavior must remain green.",
            evidence,
        ),
        _seed(
            "RR-DIRECT-FIX",
            "Component Regression",
            "P1",
            "Direct fix path must reject the original failure and preserve clear error contracts.",
            evidence,
        ),
        _seed(
            "RR-RECOVERY",
            "Nightly",
            "P1",
            "Recovery after bad data/config is removed must not require server restart or cache clearing unless documented.",
            evidence,
        ),
    ]
    if outputs or re.search(r"\b(pdf|html5|aem sites|output|publishing)\b", lowered):
        seeds.append(
            _seed(
                "RR-PUBLISHING-OUTPUTS",
                "Release Regression",
                "P1",
                "PDF/HTML5/AEM Sites output behavior can regress even when editor/API behavior passes.",
                evidence,
            )
        )
    if constructs:
        seeds.append(
            _seed(
                "RR-CONSTRUCT-MATRIX",
                "Component Regression",
                "P1",
                "Construct/attribute combinations need targeted pairwise coverage instead of one happy path.",
                evidence,
            )
        )
    if "snippet" in lowered:
        seeds.append(
            _seed(
                "RR-SNIPPET-API-UI-PARITY",
                "Component Regression",
                "P1",
                "Snippet API, snippet listing, and editor insertion must remain consistent after the fix.",
                evidence,
            )
        )
    if "application/x-www-form-urlencoded" in lowered or "%" in lowered:
        seeds.append(
            _seed(
                "RR-ENCODING-BACKWARD-COMPAT",
                "PR Gate",
                "P1",
                "Existing clients that send encoded form data must not regress while raw percent payloads are handled safely.",
                evidence,
            )
        )
    if features:
        seeds.append(
            _seed(
                "RR-FEATURE-ADJACENCY",
                "Exploratory",
                "P2",
                "Adjacent documented feature workflows may share services, configuration, or output processors.",
                evidence,
            )
        )
    return _dedupe_seed_dicts(seeds)


def _seed(
    seed_id: str, category: str, priority: str, rationale: str, evidence: list[str]
) -> dict[str, Any]:
    return {
        "id": seed_id,
        "category": category,
        "priority": priority,
        "rationale": rationale,
        "evidence": evidence[:5],
        "required_mapping": "scenario_or_evidence_backed_exclusion",
    }


def _seed_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip()).strip("-").upper()
    return (slug or "GENERAL")[:36]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _dedupe_seed_dicts(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for value in values:
        key = str(value.get("id") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _retrieve_dita_chunks(query: str, *, k: int) -> list[dict[str, Any]]:
    try:
        from app.services.dita_knowledge_retriever import retrieve_dita_knowledge

        chunks = retrieve_dita_knowledge(query_text=query, k=k) or []
    except Exception as exc:
        return [{"error": str(exc)}]
    out: list[dict[str, Any]] = []
    for chunk in chunks[:k]:
        out.append(
            {
                "source": chunk.get("url")
                or chunk.get("source")
                or chunk.get("element_name", ""),
                "title": chunk.get("title") or chunk.get("element_name", ""),
                "snippet": chunk.get("text_content")
                or chunk.get("snippet")
                or chunk.get("text", ""),
            }
        )
    return out


def _qa_preview(jira_key: str, issue: dict[str, Any]) -> dict[str, Any]:
    """Best-effort non-LLM QA Studio preview; never blocks MCP packet creation."""
    try:
        from app.api.v1.routes.gqs_authoring import authoring_preview
        from app.api.v1.routes.qa_studio import PlanRequest
        import anyio

        body = PlanRequest(
            jira_key=jira_key,
            jira_summary=str(issue.get("summary") or issue.get("title") or ""),
            jira_description=str(
                issue.get("description") or issue.get("snippet") or ""
            ),
            jira_raw=json.dumps(issue, ensure_ascii=False, default=str),
        )
        return anyio.run(authoring_preview, body)
    except Exception as exc:
        return {"preview_unavailable": str(exc)}


def _collect_repository_evidence(
    issue: dict[str, Any],
    planning_seeds: dict[str, Any],
    repo_contract: dict[str, Any],
    *,
    max_matches: int,
) -> dict[str, Any]:
    try:
        from app.services.repository_evidence_service import collect_repository_evidence

        return collect_repository_evidence(
            issue=issue,
            planning_seeds=planning_seeds,
            repo_contract=repo_contract,
            max_matches=max(1, min(int(max_matches), 100)),
        )
    except Exception as exc:
        return {
            "source": "local_repository_scan",
            "status": "missing",
            "repo_evidence_status": "missing",
            "scan_error": str(exc),
            "repositories": [],
            "owner_gates": [],
            "missing_evidence": ["Repository evidence scan failed."],
            "planner_instruction": "Keep Review status: Draft until local repository evidence is available.",
        }


def _repository_evidence_disabled() -> dict[str, Any]:
    return {
        "source": "local_repository_scan",
        "status": "missing",
        "repo_evidence_status": "missing",
        "disabled": True,
        "repositories": [],
        "owner_gates": [],
        "missing_evidence": ["Repository evidence scan disabled by MCP caller."],
        "planner_instruction": "Keep Review status: Draft because repository evidence was not collected.",
    }


def _add_repository_evidence_seeds(
    planning_seeds: dict[str, Any],
    repository_evidence: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(planning_seeds)
    repo_seeds: list[dict[str, Any]] = []
    for repo in repository_evidence.get("repositories") or []:
        repo_id = str(repo.get("id") or "")
        matches = repo.get("matches") or []
        if matches:
            repo_seeds.append(
                _seed(
                    f"REPO-{_seed_slug(repo_id)}",
                    str(
                        repo.get("owner_role")
                        or repo.get("evidence_type")
                        or "repository"
                    ),
                    "P1",
                    (
                        f"{repo_id} has {len(matches)} local evidence match(es); cite file paths in "
                        "blast radius, automation strength, and scenario traceability."
                    ),
                    [
                        f"{match.get('relative_path')}:{match.get('line')} matched {match.get('matched_query')}"
                        for match in matches[:5]
                    ],
                )
            )
        else:
            repo_seeds.append(
                _seed(
                    f"REPO-MISSING-{_seed_slug(repo_id)}",
                    str(repo.get("owner_role") or "repository"),
                    "P1",
                    f"{repo_id} evidence is missing or weak; keep the plan Draft unless this owner gate is evidence-backed as not applicable.",
                    [
                        str(
                            repo.get("missing_reason")
                            or "No repository evidence found."
                        )
                    ],
                )
            )
    for gate in repository_evidence.get("owner_gates") or []:
        if gate.get("status") != "complete":
            repo_seeds.append(
                _seed(
                    f"REPO-GATE-{_seed_slug(str(gate.get('owner_role') or 'OWNER'))}",
                    "Repository owner gate",
                    "P0",
                    f"Owner gate {gate.get('owner_role')} is {gate.get('status')}; missing evidence must map to Residual Risk and Draft status.",
                    [str(item) for item in gate.get("missing_evidence") or []],
                )
            )
    enriched["repository_evidence_seed"] = _dedupe_seed_dicts(repo_seeds)
    return enriched


def _json_block(value: Any) -> str:
    return (
        "```json\n"
        + json.dumps(value, ensure_ascii=False, indent=2, default=str)
        + "\n```"
    )
