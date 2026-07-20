"""Evidence packet builder for the AEM Guides test-plan slash command.

This service intentionally reuses the existing Jira, AEM Guides RAG, DITA spec,
and QA Studio evidence components. It does not create a parallel RAG system and
does not mutate indexes.
"""

from __future__ import annotations

import json
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


def normalize_jira_key(value: str) -> str:
    """Extract and normalize a Jira key from slash-command arguments."""
    match = _JIRA_KEY_RE.search((value or "").strip().upper())
    if not match:
        raise ValueError("Expected a Jira key such as GUIDES-12345.")
    return match.group(0)


def build_guides_test_plan_packet(
    jira_key: str,
    *,
    tenant_id: str = "kone",
    evidence_k: int = 8,
) -> dict[str, Any]:
    """Return a complete MCP evidence packet for Claude Code plan generation."""
    key = normalize_jira_key(jira_key)
    issue = _lookup_issue(key, tenant_id=tenant_id)
    query_text = _issue_query_text(key, issue)
    docs = _retrieve_aem_docs(query_text, k=evidence_k)
    learned_behavior = _retrieve_learned_behavior_evidence(query_text, k=evidence_k)
    dita_chunks = _retrieve_dita_chunks(query_text, k=min(5, evidence_k))
    publishing_context = _build_publishing_transform_context(issue, query_text, k=min(6, evidence_k))
    qa_preview = _qa_preview(key, issue)

    packet = {
        "workflow": "guides-test-plan-generator",
        "jira_key": key,
        "tenant_id": tenant_id,
        "issue": issue,
        "experience_league_evidence": docs,
        "learned_behavior_evidence": learned_behavior,
        "dita_spec_evidence": dita_chunks,
        "publishing_transform_context": publishing_context,
        "qa_studio_preview": qa_preview,
        "required_skill": "aem-guides-test-scenario-generator",
        "required_output_heading": "## 4. Blast radius and risk analysis",
        "instructions": [
            "Use the existing aem-guides-test-scenario-generator skill.",
            "Do not generate scenarios before blast-radius analysis.",
            "Cite official Experience League source_url/canonical_url values.",
            "Use learned_behavior_evidence from scraped Experience League DITA as product-behavior evidence, not as Jira facts.",
            "For publishing/PDF2/HTML/HTML5/DITA-OT tickets, use publishing_transform_context and DITA-OT evidence.",
            "Use JIRA facts only from the returned issue/evidence packet.",
            "Mark the plan Draft if Jira, RAG, repository, or blast-radius evidence is incomplete.",
            "Validate the final plan with scripts/validate_test_plan.py before calling it review-ready.",
        ],
    }
    packet["prompt"] = _render_prompt(packet)
    return packet


def render_guides_test_plan_packet_markdown(packet: dict[str, Any]) -> str:
    """Human-readable MCP return value for Claude Code."""
    key = packet.get("jira_key", "")
    lines = [
        f"# Guides Test Plan Generator Packet: {key}",
        "",
        "Use this packet to generate the final test plan in this Claude Code turn.",
        "",
        "## Required workflow",
        "",
    ]
    for item in packet.get("instructions") or []:
        lines.append(f"- {item}")
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
            "## DITA/spec evidence",
            "",
            _json_block(packet.get("dita_spec_evidence") or []),
            "",
            "## Publishing / DITA-OT evidence",
            "",
            _json_block(packet.get("publishing_transform_context") or {}),
            "",
            "## QA Studio preview",
            "",
            _json_block(packet.get("qa_studio_preview") or {}),
            "",
            "## Execution prompt",
            "",
            packet.get("prompt", ""),
        ]
    )
    return "\n".join(lines)


def _lookup_issue(jira_key: str, *, tenant_id: str) -> dict[str, Any]:
    try:
        from app.services.jira_chat_search_service import search_related_jira_issues

        result = search_related_jira_issues(jira_key, tenant_id=tenant_id, max_results=5)
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
    raw = issue.get("labels") or issue.get("label_names") or issue.get("components") or []
    labels: list[str] = []
    if isinstance(raw, str):
        labels.extend(part.strip() for part in re.split(r"[,;\s]+", raw) if part.strip())
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


def _build_publishing_transform_context(issue: dict[str, Any], query: str, *, k: int) -> dict[str, Any]:
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
        from app.services.dita_ot_github_rag_service import retrieve_dita_ot_github_for_query

        context["dita_ot_evidence"] = retrieve_dita_ot_github_for_query(publishing_query, k=k) or []
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
        from app.services.doc_retriever_service import retrieve_relevant_docs_with_diagnostics

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
    behavior_results = [
        doc
        for doc in raw_results
        if _is_learned_behavior_doc(doc)
    ]
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
                "source": chunk.get("url") or chunk.get("source") or chunk.get("element_name", ""),
                "title": chunk.get("title") or chunk.get("element_name", ""),
                "snippet": chunk.get("text_content") or chunk.get("snippet") or chunk.get("text", ""),
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
            jira_description=str(issue.get("description") or issue.get("snippet") or ""),
            jira_raw=json.dumps(issue, ensure_ascii=False, default=str),
        )
        return anyio.run(authoring_preview, body)
    except Exception as exc:
        return {"preview_unavailable": str(exc)}


def _render_prompt(packet: dict[str, Any]) -> str:
    key = packet.get("jira_key", "")
    return f"""Generate an evidence-grounded AEM Guides test plan for `{key}`.

Mandatory:
- Use `claude-skills/aem-guides-test-scenario-generator/SKILL.md`.
- Include the exact heading `## 4. Blast radius and risk analysis`.
- Do blast-radius analysis before scenario design.
- Cite Experience League `source_url` / `canonical_url` from the MCP packet.
- Use `learned_behavior_evidence` to derive expected behavior, test data, QA checklist, PDF/HTML5 review areas, and validation oracles from scraped DITA docs.
- If `publishing_transform_context.enabled=true`, include DITA-OT publishing/PDF2/HTML5 evidence and map related risks/tests to it.
- Separate confirmed evidence from unknowns.
- Cover or explicitly exclude every P0/P1 Direct, Shared-path, Downstream, Compatibility, and Observability/Recovery risk.
- Include at least one R0 unchanged-behavior control scenario.
- Finish as Draft unless the required evidence, traceability, and validator gates are satisfied.
"""


def _json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n```"
