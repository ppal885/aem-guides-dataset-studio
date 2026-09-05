"""MCP bridge routes — direct tool invocations for the MCP server.

These endpoints bypass the chat-session layer and invoke backend services
directly so the mcp_server/ subprocess can call them without managing a
streaming chat session.  Not intended for the main frontend.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import CurrentUser, UserIdentity
from app.core.schemas_qe_pattern_mcp import ResolveQePatternsRequest
from app.core.schemas_canonical_test_plan_runtime import (
    ClaudeMissingQuestionSubmission,
)
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class TextQuery(BaseModel):
    query: str


class AttributeQuery(BaseModel):
    attribute_name: str


class XmlPayload(BaseModel):
    xml: str
    filename: str = "topic.dita"


class JiraSearchRequest(BaseModel):
    query: str
    limit: int = 5


class GuidesTestPlanRequest(BaseModel):
    jira_key: str
    tenant_id: str = "kone"
    evidence_k: int = 8
    include_repository_evidence: bool = True
    max_repo_matches: int = 30
    skip_uac_label_gate: bool = False
    full_rag: bool = False
    include_evidence_graph: bool = True
    graph_max_paths: int = 20


class TestPlanPipelineBridgeRequest(BaseModel):
    jira_key: str
    tenant_id: str = "kone"
    evidence_k: int = 8
    include_repository_evidence: bool = True
    max_repo_matches: int = 30
    skip_uac_label_gate: bool = False
    full_rag: bool = True
    include_evidence_graph: bool = True
    graph_max_paths: int = 20
    include_uac_intelligence: bool = True
    compose_draft_plan: bool = True
    write_starling_artifacts: bool = False
    starling_repo_path: str | None = None
    publish_to_team_ui: bool = False
    human_review_threshold: int = 50
    claude_question_submission: ClaudeMissingQuestionSubmission | None = None


# ---------------------------------------------------------------------------
# find-recipes
# ---------------------------------------------------------------------------


@router.post("/find-recipes")
def find_recipes(body: TextQuery, user: UserIdentity = CurrentUser):
    """Search recipe specs by keyword."""
    from app.generator.recipe_manifest import discover_recipe_specs

    query_tokens = body.query.lower().split()
    results = []
    for spec in discover_recipe_specs():
        searchable = " ".join(
            [
                spec.id,
                spec.title,
                spec.description,
                " ".join(spec.tags),
                " ".join(spec.constructs),
                " ".join(spec.intent_tags),
                " ".join(spec.trigger_phrases),
            ]
        ).lower()
        if any(tok in searchable for tok in query_tokens):
            results.append(
                {
                    "id": spec.id,
                    "title": spec.title,
                    "description": spec.description,
                    "tags": spec.tags,
                    "topic_type": spec.topic_type,
                    "complexity": spec.complexity,
                    "mechanism_family": spec.mechanism_family,
                    "params_schema": spec.params_schema,
                    "default_params": spec.default_params,
                }
            )

    return {"recipes": results[:15], "total_matched": len(results)}


# ---------------------------------------------------------------------------
# lookup-dita-spec
# ---------------------------------------------------------------------------


@router.post("/lookup-dita-spec")
def lookup_dita_spec(body: TextQuery, user: UserIdentity = CurrentUser):
    """Return structured element spec + DITA knowledge RAG chunks."""
    from app.services.dita_spec_registry_service import get_element_spec
    from app.services.dita_query_interpreter import extract_element_names
    from app.services.dita_knowledge_retriever import retrieve_dita_knowledge

    element_specs = []
    for el in extract_element_names(body.query)[:3]:
        spec = get_element_spec(el)
        if spec:
            element_specs.append(
                {
                    "element": spec.name,
                    "description": spec.description,
                    "allowed_children": spec.allowed_children[:20],
                    "allowed_parents": spec.allowed_parents[:10],
                    "supported_attributes": spec.supported_attributes[:20],
                    "attribute_usage": spec.attribute_usage,
                    "usage_contexts": spec.usage_contexts,
                    "common_mistakes": spec.common_mistakes,
                    "correct_examples": spec.correct_examples[:3],
                    "source_url": spec.source_url,
                }
            )

    rag_chunks: list[dict] = []
    try:
        raw = retrieve_dita_knowledge(body.query, k=5)
        rag_chunks = [
            {
                "text": c.get("text_content", c.get("snippet", c.get("text", ""))),
                "source": c.get("element_name", c.get("url", c.get("source", ""))),
            }
            for c in (raw or [])[:5]
        ]
    except Exception as exc:
        logger.warning_structured(
            "DITA spec RAG failed", extra_fields={"error": str(exc)}
        )

    return {
        "element_specs": element_specs,
        "rag_chunks": rag_chunks,
        "query": body.query,
    }


# ---------------------------------------------------------------------------
# lookup-aem-guides
# ---------------------------------------------------------------------------


@router.post("/lookup-aem-guides")
def lookup_aem_guides(body: TextQuery, user: UserIdentity = CurrentUser):
    """Retrieve AEM Guides Experience League doc chunks."""
    from app.services.doc_retriever_service import retrieve_relevant_docs

    try:
        chunks = retrieve_relevant_docs(body.query, k=8)
        results = [
            {
                "text": c.get("snippet", c.get("text", "")),
                "source": c.get("url", c.get("source", "")),
            }
            for c in chunks
        ]
    except Exception as exc:
        logger.warning_structured(
            "AEM Guides RAG failed", extra_fields={"error": str(exc)}
        )
        results = []

    return {"results": results, "query": body.query, "count": len(results)}


# ---------------------------------------------------------------------------
# lookup-dita-attribute
# ---------------------------------------------------------------------------


@router.post("/lookup-dita-attribute")
def lookup_dita_attribute(body: AttributeQuery, user: UserIdentity = CurrentUser):
    """Look up a DITA attribute from the catalog."""
    from app.services.dita_attribute_catalog import get_attribute_spec

    spec = get_attribute_spec(body.attribute_name)
    if spec:
        return {
            "attribute": body.attribute_name,
            "spec": {
                "all_valid_values": spec.all_valid_values,
                "supported_elements": spec.supported_elements[:20],
                "combination_attributes": spec.combination_attributes,
                "default_scenarios": spec.default_scenarios[:5],
                "usage_contexts": spec.usage_contexts,
                "common_mistakes": spec.common_mistakes,
                "correct_examples": spec.correct_examples[:3],
                "syntax": spec.syntax,
                "semantic_class": spec.semantic_class,
                "source_url": spec.source_url,
            },
        }

    # Fallback: DITA knowledge RAG
    rag_chunks: list[dict] = []
    try:
        from app.services.dita_knowledge_retriever import retrieve_dita_knowledge

        raw = retrieve_dita_knowledge(f"DITA @{body.attribute_name} attribute", k=4)
        rag_chunks = [
            {
                "text": c.get("text_content", c.get("snippet", c.get("text", ""))),
                "source": c.get("element_name", c.get("url", c.get("source", ""))),
            }
            for c in (raw or [])[:4]
        ]
    except Exception as exc:
        logger.warning_structured(
            "Attribute RAG fallback failed", extra_fields={"error": str(exc)}
        )

    return {"attribute": body.attribute_name, "spec": None, "rag_chunks": rag_chunks}


# ---------------------------------------------------------------------------
# review-dita-xml
# ---------------------------------------------------------------------------


@router.post("/review-dita-xml")
def review_dita_xml(body: XmlPayload, user: UserIdentity = CurrentUser):
    """Validate a DITA XML string and return errors/warnings."""
    import xml.etree.ElementTree as ET
    from app.utils.dita_validator import validate_dita_folder

    with tempfile.TemporaryDirectory() as tmp:
        fpath = Path(tmp) / body.filename
        fpath.write_text(body.xml, encoding="utf-8")
        result = validate_dita_folder(Path(tmp))

    # Ensure parse errors are surfaced even if validator doesn't catch them
    parse_errors: list[str] = []
    try:
        ET.fromstring(body.xml)
    except ET.ParseError as exc:
        parse_errors.append(f"XML parse error: {exc}")

    return {
        "filename": body.filename,
        "parse_errors": parse_errors,
        "validation": result,
        "valid": not parse_errors and not result.get("errors"),
    }


# ---------------------------------------------------------------------------
# fix-dita-xml
# ---------------------------------------------------------------------------


@router.post("/fix-dita-xml")
def fix_dita_xml(body: XmlPayload, user: UserIdentity = CurrentUser):
    """Auto-repair common DITA XML issues and return fixed XML."""
    from app.services.dita_auto_fix_service import auto_fix_dita_folder

    with tempfile.TemporaryDirectory() as tmp:
        fpath = Path(tmp) / body.filename
        fpath.write_text(body.xml, encoding="utf-8")
        fix_result = auto_fix_dita_folder(Path(tmp))
        fixed_xml = fpath.read_text(encoding="utf-8")

    return {"fixed_xml": fixed_xml, "filename": body.filename, "fix_report": fix_result}


# ---------------------------------------------------------------------------
# search-jira
# ---------------------------------------------------------------------------


@router.post("/search-jira")
def search_jira(body: JiraSearchRequest, user: UserIdentity = CurrentUser):
    """Search Jira issues via live Jira API or indexed cache."""
    from app.services.jira_chat_search_service import search_related_jira_issues

    # search_related_jira_issues requires a tenant_id; use default for MCP callers
    result = search_related_jira_issues(
        body.query,
        tenant_id="default",
        max_results=body.limit,
    )
    return result


# ---------------------------------------------------------------------------
# guides-test-plan-generator
# ---------------------------------------------------------------------------


@router.post("/guides-test-plan-generator")
def guides_test_plan_generator(
    body: GuidesTestPlanRequest, user: UserIdentity = CurrentUser
):
    """Run canonical test-plan reasoning for `/guides-test-plan-generator`."""
    from app.services.guides_test_plan_generator_service import (
        build_guides_test_plan_packet,
    )
    from app.services.tenant_service import ensure_user_can_access_tenant

    tenant_id = ensure_user_can_access_tenant(user, body.tenant_id)
    roles = {str(role).strip().casefold() for role in user.roles}
    return build_guides_test_plan_packet(
        body.jira_key,
        tenant_id=tenant_id,
        evidence_k=max(3, min(body.evidence_k, 12)),
        include_repository_evidence=body.include_repository_evidence,
        max_repo_matches=body.max_repo_matches,
        skip_uac_label_gate=body.skip_uac_label_gate,
        full_rag=body.full_rag,
        include_evidence_graph=body.include_evidence_graph,
        graph_max_paths=max(1, min(body.graph_max_paths, 50)),
        allow_cross_customer_graph_details=user.is_admin or "knowledge_reader" in roles,
    )


# ---------------------------------------------------------------------------
# test-plan-pipeline (full orchestrator — HTTP preferred over MCP stdio)
# ---------------------------------------------------------------------------


@router.post("/test-plan-pipeline")
def test_plan_pipeline(
    body: TestPlanPipelineBridgeRequest, user: UserIdentity = CurrentUser
):
    """Run the canonical pipeline and return its retained compatibility DTO."""
    from app.core.schemas_test_plan_pipeline import TestPlanPipelineRequest
    from app.services.test_plan_pipeline_service import run_test_plan_pipeline
    from app.services.tenant_service import ensure_user_can_access_tenant

    tenant_id = ensure_user_can_access_tenant(user, body.tenant_id)
    request = TestPlanPipelineRequest(
        jira_key=body.jira_key,
        tenant_id=tenant_id,
        evidence_k=max(3, min(body.evidence_k, 12)),
        include_repository_evidence=body.include_repository_evidence,
        max_repo_matches=body.max_repo_matches,
        skip_uac_label_gate=body.skip_uac_label_gate,
        full_rag=body.full_rag,
        include_evidence_graph=body.include_evidence_graph,
        graph_max_paths=max(1, min(body.graph_max_paths, 50)),
        include_uac_intelligence=body.include_uac_intelligence,
        compose_draft_plan=body.compose_draft_plan,
        write_starling_artifacts=body.write_starling_artifacts,
        starling_repo_path=body.starling_repo_path,
        publish_to_team_ui=body.publish_to_team_ui,
        human_review_threshold=max(0, min(body.human_review_threshold, 100)),
        claude_question_submission=body.claude_question_submission,
    )
    return run_test_plan_pipeline(request, user=user, entry_point="rest_bridge")


# ---------------------------------------------------------------------------
# screenshot-to-dita (removed)
# ---------------------------------------------------------------------------

_SCREENSHOT_DITA_GONE = (
    "Screenshot-to-DITA authoring is no longer available. "
    "Use AI Chat with /generate_dita, /review_dita, or /fix_dita instead."
)


@router.post("/screenshot-to-dita")
async def screenshot_to_dita(user: UserIdentity = CurrentUser):
    """Legacy MCP endpoint — screenshot authoring was removed from the product."""
    raise HTTPException(status_code=410, detail=_SCREENSHOT_DITA_GONE)


# ---------------------------------------------------------------------------
# search-jira-history  (indexed jira_qa corpus — past UACs / test plans)
# ---------------------------------------------------------------------------


class JiraHistoryRequest(BaseModel):
    query: str
    limit: int = 10
    customer: str | None = None


@router.post("/search-jira-history")
def search_jira_history(body: JiraHistoryRequest, user: UserIdentity = CurrentUser):
    """Semantic search over the indexed jira_qa corpus (past validated UACs / test plans).

    This is the historical-learning corpus — distinct from ``/search-jira`` which hits
    live Jira. Used by the MCP ``search_jira_history`` tool so any teammate can retrieve
    indexed plans (e.g. the whole team's past AEM Guides UAC work) via Claude Desktop/CLI.
    """
    from app.services.jira_qa_retrieval_service import semantic_search_jira_qa

    limit = max(1, min(int(body.limit or 10), 50))
    try:
        hits = semantic_search_jira_qa(body.query, top_k=limit, customer=body.customer)
    except Exception as exc:  # RAG/Chroma/embedding unavailable — degrade, don't 500
        logger.warning_structured(
            "jira_qa history search failed", extra_fields={"error": str(exc)}
        )
        return {"query": body.query, "count": 0, "results": [], "error": str(exc)}

    results = []
    for h in hits or []:
        if not isinstance(h, dict):
            results.append({"text": str(h)})
            continue
        meta = h.get("metadata") or {}
        try:
            score = round(float(h.get("score", h.get("distance", 0) or 0)), 3)
        except (TypeError, ValueError):
            score = None
        results.append(
            {
                "jira_key": h.get("jira_key", meta.get("jira_key", "")),
                "summary": (h.get("summary", "") or "")[:200],
                "section": meta.get("section_title", h.get("chunk_type", "")),
                "component": h.get("component", meta.get("component", "")),
                "score": score,
                "text": (h.get("document") or h.get("text") or "")[:1200],
            }
        )
    return {"query": body.query, "count": len(results), "results": results[:limit]}


# ---------------------------------------------------------------------------
# resolve-qe-patterns  (structured Human-backed reasoning discovery)
# ---------------------------------------------------------------------------


@router.post("/resolve-qe-patterns")
def resolve_qe_patterns_bridge(
    body: ResolveQePatternsRequest,
    user: UserIdentity = CurrentUser,
    tenant_id: str = "kone",
    cutoff_at: datetime | None = None,
    excluded_source_case_ids: list[str] = Query(default=[]),
):
    """Resolve generic QE investigation patterns without generating final ACs."""
    from app.core.schemas_qe_pattern_mcp import SharedLearningContext
    from app.services.qe_pattern_mcp_service import configured_shared_learning_mode, resolve_qe_patterns
    from app.services.tenant_service import ensure_user_can_access_tenant

    tenant = ensure_user_can_access_tenant(user, tenant_id)
    if len(excluded_source_case_ids) > 1000:
        raise HTTPException(400, "At most 1000 source exclusions are supported.")
    context = SharedLearningContext(
        tenant_id=tenant, principal_id=user.id,
        authenticated=user.auth_method == "token",
        mode=configured_shared_learning_mode(), cutoff_at=cutoff_at,
        excluded_source_case_ids=set(excluded_source_case_ids),
        benchmark_isolation=bool(cutoff_at or excluded_source_case_ids),
    )
    return resolve_qe_patterns(body, context=context)


# ---------------------------------------------------------------------------
# index-test-plan  (persist + index a validated plan into jira_qa on this backend)
# ---------------------------------------------------------------------------


class IndexTestPlanRequest(BaseModel):
    key: str
    markdown: str


@router.post("/index-test-plan")
def index_test_plan_bridge(
    body: IndexTestPlanRequest, user: UserIdentity = CurrentUser
):
    """Persist a validated test-plan markdown to this backend's shared store and index it
    into jira_qa, so a teammate can push their own plan to the (VM) backend from Claude
    Desktop/CLI via the MCP ``index_test_plan`` tool. Idempotent — safe to re-run.
    """
    from app.services.test_plan_artifact_service import save_test_plan
    from app.services.test_plan_index_service import index_test_plan

    if not (body.markdown or "").strip():
        raise HTTPException(status_code=400, detail="markdown is empty")
    try:
        saved = save_test_plan(body.key, body.markdown)
    except ValueError as exc:  # bad Jira key / empty content
        raise HTTPException(status_code=400, detail=str(exc))
    indexed = index_test_plan(body.key, markdown=body.markdown)
    saved = saved if isinstance(saved, dict) else {}
    return {
        "key": saved.get("key") or saved.get("jira_key") or body.key,
        "saved_path": saved.get("path") or saved.get("file_path"),
        "indexed": indexed.get("indexed", False),
        "chunks_indexed": indexed.get("chunks_indexed", 0),
        "reason": indexed.get("reason"),
    }
