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
    include_repository_evidence: bool = True,
    max_repo_matches: int = 30,
) -> dict[str, Any]:
    """Return a complete MCP evidence packet for Claude Code plan generation."""
    key = normalize_jira_key(jira_key)
    issue = _lookup_issue(key, tenant_id=tenant_id)
    query_text = _issue_query_text(key, issue)
    docs = _retrieve_aem_docs(query_text, k=evidence_k)
    learned_behavior = _retrieve_learned_behavior_evidence(query_text, k=evidence_k)
    planning_seeds = _derive_planning_seeds(issue, learned_behavior)
    dita_chunks = _retrieve_dita_chunks(query_text, k=min(5, evidence_k))
    publishing_context = _build_publishing_transform_context(issue, query_text, k=min(6, evidence_k))
    repo_contract = _build_repository_evidence_contract(issue, planning_seeds)
    repository_evidence = (
        _collect_repository_evidence(issue, planning_seeds, repo_contract, max_matches=max_repo_matches)
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
        "experience_league_evidence": docs,
        "learned_behavior_evidence": learned_behavior,
        "planning_seeds": planning_seeds,
        "repository_evidence_contract": repo_contract,
        "repository_evidence": repository_evidence,
        "repo_evidence_status": repository_evidence.get("repo_evidence_status") or repository_evidence.get("status"),
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
            "Use planning_seeds, including repository_evidence_seed, as mandatory inputs for blast radius, bug hypotheses, areas to test, automation strength, and regression risks.",
            "Use repository_evidence from local clone scanning; if unavailable, keep the plan Draft and list missing repo evidence.",
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


def _derive_planning_seeds(issue: dict[str, Any], learned_behavior: dict[str, Any]) -> dict[str, Any]:
    results = list(learned_behavior.get("results") or []) if isinstance(learned_behavior, dict) else []
    snippets = "\n\n".join(str(item.get("snippet") or "") for item in results if isinstance(item, dict))
    issue_text = "\n".join(
        str(issue.get(key) or "")
        for key in ("issue_key", "summary", "title", "description", "snippet", "status")
    )
    combined_text = "\n\n".join(part for part in (issue_text, snippets) if part.strip())
    lowered = combined_text.lower()
    source_ids = [
        str(item.get("chunk_id") or item.get("source_url") or item.get("canonical_url") or "").strip()
        for item in results
        if isinstance(item, dict) and str(item.get("chunk_id") or item.get("source_url") or item.get("canonical_url") or "").strip()
    ][:8]

    features = _augment_features_from_issue(_extract_seed_values(snippets, "Learned feature behavior"), lowered)
    constructs = _augment_constructs_from_issue(_extract_seed_values(snippets, "Detected DITA constructs and attributes"), lowered)
    outputs = _augment_outputs_from_issue(_extract_seed_values(snippets, "Publishing/output contexts"), lowered)
    evidence = source_ids or ["learned_behavior_evidence"]

    blast_radius = _build_blast_radius_seed(features, constructs, outputs, lowered, evidence)
    bug_hypotheses = _build_bug_hypothesis_seed(constructs, outputs, lowered, evidence)
    test_areas = _build_test_area_seed(features, constructs, outputs, lowered, evidence)
    regression_risks = _build_regression_risk_seed(features, constructs, outputs, lowered, evidence)

    if not results:
        missing_reason = "No scraped Experience League learned-behavior chunks were retrieved for this Jira/query."
        blast_radius.append(_seed("BR-MISSING-BEHAVIOR", "Observability/Recovery", "High", missing_reason, evidence))
        bug_hypotheses.append(_seed("BH-MISSING-BEHAVIOR", "Evidence gap", "P1", missing_reason, evidence))
        test_areas.append(_seed("TA-MISSING-BEHAVIOR", "Evidence intake", "P1", missing_reason, evidence))
        regression_risks.append(_seed("RR-MISSING-BEHAVIOR", "Release confidence", "P1", missing_reason, evidence))

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


def _build_repository_evidence_contract(issue: dict[str, Any], planning_seeds: dict[str, Any]) -> dict[str, Any]:
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
            "fallback_path_hints": ["../dxml-it-tests", "../dxml-it", "../integration-tests"],
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
        focus_queries.extend(["/bin/fmdita/config/snippets", "snippets", "colwidth", "URLDecoder", "application/x-www-form-urlencoded"])
    if "broken links" in lowered or "report" in lowered:
        focus_queries.extend(["Broken Links Report", "Fetching details for broken links", "reports", "large map", "pagination", "lazy loading"])
    if "schematron" in lowered:
        focus_queries.extend(["schematron", "/bin/dxml/schematron", "Workspace Settings", "validate on save", "XSLT"])
    if "publishing" in lowered or "html5" in lowered or "pdf" in lowered:
        focus_queries.extend(["output preset", "DITA-OT", "Native PDF", "HTML5", "publishing"])

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
    if "application/x-www-form-urlencoded" in lowered or "urlencoded" in lowered or "url-encoded" in lowered:
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
    boundary = "|".join(re.escape(item) for item in boundary_labels if item.lower() != label.lower())
    pattern = re.compile(rf"{re.escape(label)}:\s*(.+?)(?=\s+(?:{boundary}):|\Z)", re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(text or ""):
        raw = re.sub(r"\s+", " ", match.group(1)).strip().strip(".")
        for part in re.split(r"[,;]", raw):
            value = part.strip(" .`")
            if value and value.lower() not in {"not explicit in this page", "not output-specific"}:
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
        _seed("BR-ENTRYPOINT", "Direct", "High", "Validate the documented user entry point and workflow touched by the Jira.", evidence),
        _seed("BR-ERROR-CONTRACT", "Observability/Recovery", "High", "Verify user-facing error message, network/API response, logs/jobs, and recovery path.", evidence),
    ]
    for feature in features[:4]:
        seeds.append(_seed(f"BR-FEATURE-{_seed_slug(feature)}", "Shared-path", "Medium", f"Shared feature behavior may regress: {feature}.", evidence))
    for construct in constructs[:5]:
        seeds.append(_seed(f"BR-CONSTRUCT-{_seed_slug(construct)}", "Compatibility", "Medium", f"DITA construct/attribute interaction may affect parsing, validation, publishing, or persistence: {construct}.", evidence))
    for output in outputs[:4]:
        seeds.append(_seed(f"BR-OUTPUT-{_seed_slug(output)}", "Downstream", "High", f"Downstream output context must be verified: {output}.", evidence))
    if "workspace" in lowered or "settings" in lowered:
        seeds.append(_seed("BR-CONFIG-INHERITANCE", "Shared-path", "High", "Workspace/folder/profile configuration inheritance can change the effective validation or publishing context.", evidence))
    if "publish" in lowered or "output" in lowered or outputs:
        seeds.append(_seed("BR-PUBLISHING-PIPELINE", "Downstream", "High", "Publishing pipeline behavior can diverge across Native PDF, DITA-OT PDF, HTML/HTML5, and AEM Sites.", evidence))
    if "/bin/fmdita/config/snippets" in lowered or "snippet" in lowered:
        seeds.append(_seed("BR-SNIPPET-API", "Direct", "High", "Snippet create/read/update path can fail before DITA validation when request decoding or persistence changes.", evidence))
    if "application/x-www-form-urlencoded" in lowered or "urldecoder" in lowered or "illegal hex" in lowered or "%" in lowered:
        seeds.append(_seed("BR-FORM-DECODING", "Shared-path", "High", "Form-urlencoded request decoding is a shared boundary for raw percent characters, encoded values, and malformed escape sequences.", evidence))
    return _dedupe_seed_dicts(seeds)


def _build_bug_hypothesis_seed(constructs: list[str], outputs: list[str], lowered: str, evidence: list[str]) -> list[dict[str, Any]]:
    seeds = [
        _seed("BH-NULL-EMPTY-MISSING", "Null/empty/missing input", "P1", "Null, empty, missing, or malformed input may be mapped to a misleading generic error.", evidence),
        _seed("BH-PARTIAL-FAILURE", "Partial failure", "P1", "One failing config/resource may block valid sibling resources or hide useful findings.", evidence),
        _seed("BH-RECOVERY-STALE-STATE", "Recovery/cache", "P1", "After correcting the input/config, stale cache or persisted state may keep the failure visible.", evidence),
    ]
    if any("schematron" in item.lower() for item in constructs) or "schematron" in lowered:
        seeds.append(_seed("BH-SCHEMATRON-XSLT-EXCEPTION", "Exception mapping", "P0", "Schematron/XSLT transform failure may surface as a misleading topic-content error instead of a configuration error.", evidence))
    if "urldecoder" in lowered or "illegal hex" in lowered or "application/x-www-form-urlencoded" in lowered or "%" in lowered:
        seeds.append(_seed("BH-PERCENT-DECODE-ESCAPE", "Encoding/decoding", "P0", "Raw `%` inside form-urlencoded embedded XML may be interpreted as an incomplete URL escape and fail before snippet creation.", evidence))
        seeds.append(_seed("BH-DOUBLE-DECODE", "Encoding/decoding", "P1", "A fix may double-decode `%25`, store `%25` instead of `%`, or corrupt valid encoded XML payloads.", evidence))
    if "snippet" in lowered:
        seeds.append(_seed("BH-SNIPPET-PERSISTENCE-CORRUPTION", "Persistence", "P1", "Snippet creation may report success while storing modified or truncated embedded XML.", evidence))
    if any(item for item in outputs) or re.search(r"\b(pdf|html5|output|publishing)\b", lowered):
        seeds.append(_seed("BH-OUTPUT-DIVERGENCE", "Backend/UI/output mismatch", "P1", "Backend preprocessing can succeed or fail differently from final PDF/HTML5/AEM Sites output review.", evidence))
    for construct in constructs[:5]:
        seeds.append(_seed(f"BH-CONSTRUCT-{_seed_slug(construct)}", "Construct interaction", "P2", f"{construct} can interact with adjacent branches, inherited config, or output transforms in non-obvious ways.", evidence))
    return _dedupe_seed_dicts(seeds)


def _build_test_area_seed(
    features: list[str],
    constructs: list[str],
    outputs: list[str],
    lowered: str,
    evidence: list[str],
) -> list[dict[str, Any]]:
    seeds = [
        _seed("TA-REPRODUCTION", "Reproduction", "P0", "Reproduce the reported behavior with minimal controlled data.", evidence),
        _seed("TA-CONTROL", "R0 control", "P0", "Verify unchanged valid behavior still passes with known-good data.", evidence),
        _seed("TA-NEGATIVE", "Negative/error handling", "P1", "Exercise invalid, empty, missing, malformed, and mixed valid/invalid inputs.", evidence),
        _seed("TA-RECOVERY", "Recovery", "P1", "Verify correction/removal/retry restores expected behavior without stale state.", evidence),
    ]
    for feature in features[:4]:
        seeds.append(_seed(f"TA-FEATURE-{_seed_slug(feature)}", "Feature workflow", "P1", f"Cover documented feature workflow: {feature}.", evidence))
    for construct in constructs[:6]:
        seeds.append(_seed(f"TA-CONSTRUCT-{_seed_slug(construct)}", "DITA construct data", "P1", f"Generate focused data for construct/attribute: {construct}.", evidence))
    for output in outputs[:4]:
        seeds.append(_seed(f"TA-OUTPUT-{_seed_slug(output)}", "Output review", "P1", f"Review generated output context: {output}.", evidence))
    if "qa checklist" in lowered:
        seeds.append(_seed("TA-DOC-QA-CHECKLIST", "Documentation-derived QA", "P1", "Convert scraped QA checklist guidance into explicit scenario oracles.", evidence))
    if "urldecoder" in lowered or "illegal hex" in lowered or "%" in lowered:
        seeds.append(_seed("TA-ENCODING-MATRIX", "API encoding matrix", "P0", "Test raw `%`, encoded `%25`, malformed `%ZZ`, percent in adjacent fields, and normal no-percent controls.", evidence))
    if "snippet" in lowered:
        seeds.append(_seed("TA-SNIPPET-ROUNDTRIP", "Persistence round trip", "P1", "Create, retrieve/list, and use the snippet to prove embedded XML is preserved exactly.", evidence))
    if "colwidth" in lowered or "colspec" in lowered:
        seeds.append(_seed("TA-TABLE-COLWIDTH-DATA", "DITA table data", "P1", "Generate table snippets with `colspec/@colwidth` percentage, proportional, absolute, and malformed variants.", evidence))
    return _dedupe_seed_dicts(seeds)


def _build_regression_risk_seed(
    features: list[str],
    constructs: list[str],
    outputs: list[str],
    lowered: str,
    evidence: list[str],
) -> list[dict[str, Any]]:
    seeds = [
        _seed("RR-R0-CONTROL", "PR Gate", "P0", "Known-good unchanged behavior must remain green.", evidence),
        _seed("RR-DIRECT-FIX", "Component Regression", "P1", "Direct fix path must reject the original failure and preserve clear error contracts.", evidence),
        _seed("RR-RECOVERY", "Nightly", "P1", "Recovery after bad data/config is removed must not require server restart or cache clearing unless documented.", evidence),
    ]
    if outputs or re.search(r"\b(pdf|html5|aem sites|output|publishing)\b", lowered):
        seeds.append(_seed("RR-PUBLISHING-OUTPUTS", "Release Regression", "P1", "PDF/HTML5/AEM Sites output behavior can regress even when editor/API behavior passes.", evidence))
    if constructs:
        seeds.append(_seed("RR-CONSTRUCT-MATRIX", "Component Regression", "P1", "Construct/attribute combinations need targeted pairwise coverage instead of one happy path.", evidence))
    if "snippet" in lowered:
        seeds.append(_seed("RR-SNIPPET-API-UI-PARITY", "Component Regression", "P1", "Snippet API, snippet listing, and editor insertion must remain consistent after the fix.", evidence))
    if "application/x-www-form-urlencoded" in lowered or "%" in lowered:
        seeds.append(_seed("RR-ENCODING-BACKWARD-COMPAT", "PR Gate", "P1", "Existing clients that send encoded form data must not regress while raw percent payloads are handled safely.", evidence))
    if features:
        seeds.append(_seed("RR-FEATURE-ADJACENCY", "Exploratory", "P2", "Adjacent documented feature workflows may share services, configuration, or output processors.", evidence))
    return _dedupe_seed_dicts(seeds)


def _seed(seed_id: str, category: str, priority: str, rationale: str, evidence: list[str]) -> dict[str, Any]:
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
                    str(repo.get("owner_role") or repo.get("evidence_type") or "repository"),
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
                    [str(repo.get("missing_reason") or "No repository evidence found.")],
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


def _render_prompt(packet: dict[str, Any]) -> str:
    key = packet.get("jira_key", "")
    return f"""Generate an evidence-grounded AEM Guides test plan for `{key}`.

Mandatory:
- Use `claude-skills/aem-guides-test-scenario-generator/SKILL.md`.
- Include the exact heading `## 4. Blast radius and risk analysis`.
- Do blast-radius analysis before scenario design.
- Cite Experience League `source_url` / `canonical_url` from the MCP packet.
- Use `learned_behavior_evidence` to derive expected behavior, test data, QA checklist, PDF/HTML5 review areas, and validation oracles from scraped DITA docs.
- Use `planning_seeds.blast_radius_seed`, `bug_hypothesis_seed`, `test_area_seed`, and `regression_risk_seed` as mandatory inputs; map each P0/P1 seed to a scenario or evidence-backed exclusion.
- Use `repository_evidence` from local clone scanning. Cite exact paths/lines from `xmleditor`, `starling`, `guides-ui-tests`, and `dxml-it-tests`; missing or weak repo evidence means Draft.
- Apply owner gates: frontend requires `xmleditor` + `guides-ui-tests`, backend requires `starling` + `dxml-it-tests`, and cross-layer changes require both.
- If `publishing_transform_context.enabled=true`, include DITA-OT publishing/PDF2/HTML5 evidence and map related risks/tests to it.
- Separate confirmed evidence from unknowns.
- Cover or explicitly exclude every P0/P1 Direct, Shared-path, Downstream, Compatibility, and Observability/Recovery risk.
- Include at least one R0 unchanged-behavior control scenario.
- Finish as Draft unless the required evidence, traceability, and validator gates are satisfied.
"""


def _json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n```"
