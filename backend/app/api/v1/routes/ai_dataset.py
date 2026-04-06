"""AI dataset routes - generate DITA from text, feedback, RAG, etc."""
import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException, Depends, Query, Request, Body
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.agentic_config import agentic_config
from app.core.content_validation import validate_generate_text
from app.core.validation import validate_jira_id, sanitize_error_for_client
from app.utils.api_rate_limit import check_generate_from_text_limit
from app.core.schemas_ai import GeneratorInvocationPlan, SelectedRecipe
from app.db.session import get_db, SessionLocal
from app.db.dataset_run_models import DatasetRun
from app.db.run_feedback_models import RunFeedback
from app.services.feedback_analysis_service import analyze_validation_errors
from app.services.feedback_aggregation_service import aggregate_feedback_insights, compute_prompt_overrides_from_feedback, save_prompt_overrides
from app.utils.evidence_extractor import pre_extract_representative_xml
from app.services.ai_executor_service import execute_plan
from app.services.dita_enrichment_service import enrich_dita_folder
from app.services.recipe_pipeline_service import run_recipe_pipeline
from app.services.dita_auto_fix_service import auto_fix_dita_folder
from app.services.bundle_builder_service import build_bundle
from app.services.dataset_packager_service import package_bundle
from app.utils.dita_validator import validate_dita_folder
from app.services.doc_retriever_service import check_rag_readiness
from app.services.jira_generate_resolve import resolve_text_for_generate_from_text
from app.storage import get_storage
from app.core.structured_logging import get_structured_logger
from app.core.observability import get_observability_logger
from app.evaluation.run_eval import run_evaluation
from app.training.recipe_feedback_pairs import export_feedback_pairs_for_eval
from app.services.llm_service import _get_prompt_versions

logger = get_structured_logger(__name__)
obs_log = get_observability_logger("dita_generation")

router = APIRouter(prefix="/ai", tags=["AI"])

# In-memory progress store for async generate; keyed by run_id
_generate_progress: dict[str, dict] = {}

GENERATE_FROM_TEXT_USE_PIPELINE = os.environ.get("GENERATE_FROM_TEXT_USE_PIPELINE", "false").lower() in ("true", "1", "yes")
GENERATE_FROM_TEXT_USE_INTENT_PIPELINE = os.environ.get(
    "GENERATE_FROM_TEXT_USE_INTENT_PIPELINE", "true"
).lower() in ("true", "1", "yes")


def _write_scenario_metadata(
    scenario_dir: Path,
    jira_id: str,
    scenario_type: str,
    generator_recipes: list[str],
    evidence: list[str],
) -> None:
    """Write metadata.json into scenario folder."""
    metadata = {
        "jira_id": jira_id,
        "scenario_type": scenario_type,
        "generator_recipes": generator_recipes,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "evidence": evidence,
    }
    (scenario_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


class GenerateFromTextRequest(BaseModel):
    """Request to generate DITA from raw text (ChatGPT-style: paste Jira text, get DITA)."""
    text: str
    instructions: str | None = None  # Optional additional instructions (GPT-like: user-provided guidance)


@router.get("/datasets/search")
def search_datasets(
    jira_id: str | None = Query(None, description="Filter by Jira issue key"),
    scenario_type: str | None = Query(None, description="Filter by scenario type"),
    recipe: str | None = Query(None, description="Filter by recipe id used"),
    date_from: str | None = Query(None, description="Start date (ISO format)"),
    date_to: str | None = Query(None, description="End date (ISO format)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    session: Session = Depends(get_db),
):
    """Search dataset runs with filters. Returns paginated results."""
    q = session.query(DatasetRun)
    if jira_id:
        q = q.filter(DatasetRun.jira_id == jira_id)
    if scenario_type:
        q = q.filter(DatasetRun.scenario_type == scenario_type)
    if recipe:
        q = q.filter(DatasetRun.recipes_used.contains(f'"{recipe}"'))
    if date_from:
        try:
            s = date_from.replace("Z", "").replace("+00:00", "").strip()
            dt_from = datetime.fromisoformat(s)
            q = q.filter(DatasetRun.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            s = date_to.replace("Z", "").replace("+00:00", "").strip()
            dt_to = datetime.fromisoformat(s)
            q = q.filter(DatasetRun.created_at <= dt_to)
        except ValueError:
            pass

    total = q.count()
    offset = (page - 1) * limit
    rows = q.order_by(DatasetRun.created_at.desc()).offset(offset).limit(limit).all()

    items = [
        {
            "id": r.id,
            "jira_id": r.jira_id,
            "scenario_type": r.scenario_type,
            "recipes_used": json.loads(r.recipes_used) if r.recipes_used else [],
            "bundle_zip": r.bundle_zip,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit else 0,
    }


@router.get("/bundle/{jira_id}/{run_id}/download")
def download_ai_bundle(jira_id: str, run_id: str):
    """Download the AI-generated dataset bundle ZIP for a Jira run."""
    err = validate_jira_id(jira_id)
    if err:
        raise HTTPException(status_code=400, detail=err)
    try:
        UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="run_id must be a valid UUID")

    storage = get_storage()
    zip_path = storage.base_path / "zips" / jira_id / run_id / f"{jira_id}_bundle.zip"
    if not zip_path.exists() or not zip_path.is_file():
        raise HTTPException(status_code=404, detail="Bundle not found")

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"{jira_id}_bundle.zip",
        headers={"Content-Disposition": f'attachment; filename="{jira_id}_bundle.zip"'},
    )


def _extract_jira_field(text: str, pattern: str) -> str:
    """Extract a single-line field value from formatted Jira text."""
    m = re.search(pattern, text, re.IGNORECASE)
    return (m.group(1) or "").strip() if m else ""


def _extract_jira_section(text: str, heading_pattern: str) -> str:
    """Extract a multi-line section following a heading pattern."""
    m = re.search(heading_pattern, text, re.IGNORECASE)
    if not m:
        return ""
    start = m.end()
    # Find next section heading
    next_h = re.search(
        r"\n(?:##\s|h[1-6]\.\s|(?:Issue\s+(?:Summary|Description)|Steps?\s+to|Expected|Actual|Acceptance|Environment|Comments?)\s*\n)",
        text[start:],
        re.IGNORECASE,
    )
    end = start + next_h.start() if next_h else len(text)
    return text[start:end].strip()[:3000]


def _build_evidence_pack_from_text(
    text: str, run_id: str, forced_issue_key: str | None = None
) -> dict:
    """
    Parse raw Jira-style text into evidence_pack for generate-from-text.
    Extracts structured fields (issue_type, priority, steps_to_reproduce, acceptance_criteria, etc.)
    so downstream intent analysis and generation planning can use them.
    """
    text = (text or "").strip()
    if not text:
        return {"primary": {"summary": "", "description": "", "issue_key": "TEXT"}, "similar": []}

    issue_key = forced_issue_key or f"TEXT-{run_id[:8]}"

    # Extract structured metadata fields from formatted Jira text
    issue_type = _extract_jira_field(text, r"^Issue\s+Type:\s*(.+)$")
    priority = _extract_jira_field(text, r"^Priority:\s*(.+)$")
    status = _extract_jira_field(text, r"^Status:\s*(.+)$")
    labels_raw = _extract_jira_field(text, r"^Labels:\s*(.+)$")
    labels = [l.strip() for l in labels_raw.split(",") if l.strip()] if labels_raw else []
    components_raw = _extract_jira_field(text, r"^Components:\s*(.+)$")
    components = [c.strip() for c in components_raw.split(",") if c.strip()] if components_raw else []

    # Extract structured sections
    acceptance_criteria = _extract_jira_section(text, r"##\s*Acceptance\s+Criteria\s*\n")
    steps_to_reproduce = _extract_jira_section(text, r"##\s*Steps?\s+to\s+Reproduce\s*\n")
    expected_behavior = _extract_jira_section(text, r"##\s*Expected\s+(?:Behavior|Result|Outcome)\s*\n")
    actual_behavior = _extract_jira_section(text, r"##\s*(?:Actual\s+(?:Behavior|Result|Outcome)|Current\s+Behavior)\s*\n")
    environment = _extract_jira_section(text, r"##\s*Environment\s*\n")

    # Extract summary and description (main content sections)
    summary = ""
    description = text

    if forced_issue_key:
        sum_m = re.search(
            r"##\s*Issue\s+Summary\s*\n(.*?)(?=\n\s*##\s*Issue\s+Description|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        desc_m = re.search(r"##\s*Issue\s+Description\s*\n(.*?)(?=\n\s*##\s|\Z)", text, re.IGNORECASE | re.DOTALL)
        if sum_m:
            summary = (sum_m.group(1) or "").strip()[:500]
        if desc_m:
            description = (desc_m.group(1) or "").strip()
    else:
        # Jira-style headings: h3. Issue Description, h3. Issue Summary, etc.
        desc_match = re.search(
            r"(?:h3\.\s*)?Issue\s+Description\s*\n",
            text,
            re.IGNORECASE,
        )
        sum_match = re.search(
            r"(?:h3\.\s*)?Issue\s+Summary\s*\n",
            text,
            re.IGNORECASE,
        )

        if desc_match or sum_match:
            parts = re.split(r"\n(?:h3\.\s*)?(?:Issue\s+Summary|Issue\s+Description)\s*\n", text, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) >= 2:
                summary = (parts[0] or "").strip()[:500]
                description = (parts[1] or "").strip()
            else:
                summary = (parts[0] or "").strip()[:500]
                description = ""
        else:
            summary = text[:500].strip()
            description = text[500:].strip() if len(text) > 500 else ""

    primary: dict = {
        "summary": summary,
        "description": description,
        "issue_key": issue_key,
    }
    # Attach structured fields so intent analysis + generation plan can use them
    if issue_type:
        primary["issue_type"] = issue_type
    if priority:
        primary["priority"] = priority
    if status:
        primary["status"] = status
    if labels:
        primary["labels"] = labels
    if components:
        primary["components"] = components
    if acceptance_criteria:
        primary["acceptance_criteria"] = acceptance_criteria
    if steps_to_reproduce:
        primary["steps_to_reproduce"] = steps_to_reproduce
    if expected_behavior:
        primary["expected_behavior"] = expected_behavior
    if actual_behavior:
        primary["actual_behavior"] = actual_behavior
    if environment:
        primary["environment"] = environment

    return {"primary": primary, "similar": []}


def _update_generate_progress(run_id: str, **kwargs) -> None:
    """Update progress dict for run_id. Merges kwargs into existing state."""
    if run_id not in _generate_progress:
        _generate_progress[run_id] = {}
    _generate_progress[run_id].update(kwargs)


async def _run_generate_from_text(
    body: GenerateFromTextRequest,
    run_id: str,
    request: Request | None,
    skip_rag_check: bool = False,
    progress_run_id: str | None = None,
) -> dict:
    """
    ChatGPT-style generate: paste text or natural language -> LLM interprets intent and generates DITA.
    Always uses llm_generated_dita so the LLM understands natural language (e.g. "create a task topic
    about printer installation") instead of deterministic recipes that ignore user intent.
    When progress_run_id is set, updates _generate_progress at each stage for streaming/polling.
    """
    pid = progress_run_id or run_id
    resolved_text, real_jira_id, resolution_warning = resolve_text_for_generate_from_text(body.text)
    jira_id = real_jira_id or f"TEXT-{run_id[:8]}"
    _update_generate_progress(pid, status="running", stage="planning", jira_id=jira_id, scenarios_total=1, scenarios_done=0)

    trace_id = str(uuid4())
    start_time = time.perf_counter()
    obs_log.info(
        "dita_generation_started",
        run_id=run_id,
        session_id=progress_run_id or run_id,
        trace_id=trace_id,
        topic_count=1,
        scenarios_total=1,
    )
    evidence_pack = _build_evidence_pack_from_text(
        resolved_text, run_id, forced_issue_key=real_jira_id
    )

    # Merge instructions into evidence description so LLM sees full context (refinements, clarifications)
    instructions = (body.instructions or "").strip() or None
    if instructions:
        primary = evidence_pack.get("primary") or {}
        desc = (primary.get("description") or "").strip()
        merged_desc = f"{desc}\n\nAdditional instructions / refinements:\n{instructions}" if desc else instructions
        evidence_pack = {
            **evidence_pack,
            "primary": {**primary, "description": merged_desc},
        }

    rag_status = check_rag_readiness()
    if not skip_rag_check:
        if not rag_status["any_ready"]:
            raise HTTPException(
                status_code=503,
                detail=rag_status["message"],
            )
    elif not rag_status["any_ready"]:
        # When skip_rag_check=True (default for paste flow), include warning in result
        rag_status["rag_warning"] = (
            "RAG sources not indexed. For better DITA accuracy, run POST /api/v1/ai/crawl-aem-guides "
            "and POST /api/v1/ai/index-dita-pdf, then retry."
        )

    storage = get_storage()
    temp_base = storage.base_path / "ai_runs" / jira_id / run_id
    temp_base.mkdir(parents=True, exist_ok=True)
    scenario_dir = temp_base / "S1_MIN_REPRO"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    exec_result: dict | None = None
    plan: GeneratorInvocationPlan | None = None
    pipeline_out: dict | None = None

    # Plan + execute: intent pipeline OR Jira-style recipe pipeline OR direct LLM (then execute if not already run)
    if GENERATE_FROM_TEXT_USE_INTENT_PIPELINE:
        from app.services.dita_pipeline_orchestrator import run_intent_pipeline_with_execution

        _update_generate_progress(pid, stage="intent_pipeline", message="Analyzing intent and selecting recipe...")
        pipeline_out = await run_intent_pipeline_with_execution(
            evidence_pack,
            jira_id,
            scenario_dir,
            seed=run_id,
            trace_id=trace_id,
            user_instructions=instructions,
        )
        inv = pipeline_out.get("invocation_plan")
        if inv is not None:
            plan = inv
        exec_result = pipeline_out["exec_result"]
        sem = pipeline_out.get("semantic_report")
        if sem and not sem.ok and exec_result:
            for v in sem.violations:
                exec_result.setdefault("warnings", []).append(
                    f"semantic:{v.rule_id}: {v.message}"
                )
    elif GENERATE_FROM_TEXT_USE_PIPELINE:
        pipeline_result = await run_recipe_pipeline(
            evidence_pack, jira_id, trace_id=trace_id
        )
        per_scenario = pipeline_result.get("per_scenario") or {}
        plan_dict = (per_scenario.get("S1_MIN_REPRO") or {}).get("plan") or {}
        plan = GeneratorInvocationPlan.model_validate(plan_dict)
    else:
        rep_xml = pre_extract_representative_xml(evidence_pack.get("primary") or {})
        plan = GeneratorInvocationPlan(
            recipes=[
                SelectedRecipe(
                    recipe_id="llm_generated_dita",
                    params={
                        "evidence_pack": evidence_pack,
                        "representative_xml": rep_xml or [],
                        "trace_id": trace_id,
                        "jira_id": jira_id,
                        "additional_instructions": None,
                    },
                    evidence_used=[],
                )
            ],
            selection_rationale=["generate-from-text: natural language chat"],
        )

    if exec_result is None:
        assert plan is not None
        _update_generate_progress(pid, stage="generating", message="Generating DITA...")
        exec_result = await asyncio.to_thread(
            execute_plan,
            plan,
            str(scenario_dir),
            seed=run_id[:8],
            skip_experience_league_companion=True,
        )

    _update_generate_progress(pid, stage="enriching", message="Enriching DITA...")
    await asyncio.to_thread(enrich_dita_folder, scenario_dir)
    await asyncio.to_thread(auto_fix_dita_folder, scenario_dir)

    # --- Phase E1: Generate images for DITA topics ---
    from app.services.image_generation_service import (
        DITA_IMAGE_GENERATION_ENABLED,
        generate_images_for_dita,
    )
    if DITA_IMAGE_GENERATION_ENABLED:
        _update_generate_progress(pid, stage="images", message="Generating images...")
        try:
            dita_files = list(scenario_dir.glob("**/*.dita")) + list(scenario_dir.glob("**/*.xml"))
            for dita_file in dita_files:
                dita_xml = dita_file.read_text(encoding="utf-8", errors="replace")
                await generate_images_for_dita(
                    dita_xml=dita_xml,
                    output_dir=dita_file.parent,
                    topic_title=dita_file.stem,
                )
        except Exception as img_err:
            logger.warning_structured(
                "Image generation failed (non-fatal)",
                extra_fields={"error": str(img_err)},
            )

    _update_generate_progress(pid, stage="validating", message="Validating...")
    val_result = await asyncio.to_thread(validate_dita_folder, scenario_dir)

    plans = {
        "S1_MIN_REPRO": {
            "recipes_executed": exec_result.get("recipes_executed", ["llm_generated_dita"]),
            "warnings": exec_result.get("warnings", []),
        }
    }
    validation_results = {"S1_MIN_REPRO": val_result or {"errors": [], "warnings": []}}
    scenario_outputs = {"S1_MIN_REPRO": scenario_dir}

    _write_scenario_metadata(
        scenario_dir,
        jira_id=jira_id,
        scenario_type="MIN_REPRO",
        generator_recipes=plans["S1_MIN_REPRO"].get("recipes_executed", []),
        evidence=[],
    )

    _update_generate_progress(pid, stage="bundling", message="Building bundle...")
    bundle_path = await asyncio.to_thread(
        build_bundle,
        jira_id,
        run_id,
        scenario_outputs,
        evidence_pack,
        plans,
        validation_results,
    )
    zip_path = await asyncio.to_thread(package_bundle, bundle_path, jira_id, run_id)

    try:
        topic_count = sum(len(list(p.glob("**/*.dita*"))) for p in scenario_outputs.values() if p.exists())
    except Exception:
        topic_count = len(scenario_outputs)

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    obs_log.info(
        "dita_generation_completed",
        run_id=run_id,
        session_id=pid,
        trace_id=trace_id,
        topic_count=topic_count,
        duration_ms=duration_ms,
        jira_id=jira_id,
    )

    result = {
        "jira_id": jira_id,
        "run_id": run_id,
        "resolved_source_text": resolved_text,
        "trace_id": trace_id,
        "scenarios": list(scenario_outputs.keys()),
        "bundle": {
            "zip_path": str(zip_path),
            "bundle_dir": str(bundle_path),
        },
        "manifest": {
            "jira_id": jira_id,
            "run_id": run_id,
            "scenarios": ["S1_MIN_REPRO"],
        },
    }
    if pipeline_out is not None:
        result["generation_debug"] = {
            "trace_path": pipeline_out.get("generation_trace_path"),
            "outcome": pipeline_out.get("generation_outcome"),
        }
    if rag_status.get("rag_warning"):
        result["rag_warning"] = rag_status["rag_warning"]
    if resolution_warning:
        result["resolution_warning"] = resolution_warning
    result["download_url"] = f"/api/v1/ai/bundle/{jira_id}/{run_id}/download"
    _generate_progress[pid] = {"status": "completed", "result": result}
    return result


@router.get("/prompt-versions")
def get_prompt_versions():
    """Return current prompt versions from versions.json. Use for A/B testing and iteration."""
    return _get_prompt_versions()


@router.get("/pipeline-metrics")
def get_pipeline_metrics(
    limit: int = Query(100, ge=1, le=500, description="Max feedback records to aggregate"),
    session: Session = Depends(get_db),
):
    """Return pipeline metrics for observability: validation rate, top failed recipes, recent run count."""
    from collections import defaultdict
    q = session.query(RunFeedback).filter(RunFeedback.eval_metrics.isnot(None)).order_by(RunFeedback.created_at.desc()).limit(limit).all()
    passed = failed = 0
    recipe_failures = defaultdict(int)
    run_ids = set()
    for row in q:
        try:
            metrics = json.loads(row.eval_metrics or "{}")
            if metrics.get("validation_passed"):
                passed += 1
            else:
                failed += 1
                for rid in metrics.get("recipes_used", []):
                    if rid:
                        recipe_failures[rid] += 1
            if row.run_id:
                run_ids.add(row.run_id)
        except (json.JSONDecodeError, TypeError):
            continue
    total = passed + failed
    validation_rate = (passed / total * 100) if total else 0
    top_failed = sorted(recipe_failures.items(), key=lambda x: -x[1])[:5]
    return {
        "validation_rate_pct": round(validation_rate, 1),
        "passed": passed,
        "failed": failed,
        "total_runs": len(run_ids),
        "top_failed_recipes": [{"recipe_id": r, "count": c} for r, c in top_failed],
    }


@router.get("/agentic-config")
def get_agentic_config():
    """Return current agentic config (base + runtime overrides)."""
    cfg = agentic_config
    return {
        "max_validation_retries": cfg.max_validation_retries,
        "max_execution_retries": cfg.max_execution_retries,
        "max_scenarios_per_run": cfg.max_scenarios_per_run,
        "recipe_candidates_k": cfg.recipe_candidates_k,
        "recipe_candidates_k_per_retry": cfg.recipe_candidates_k_per_retry,
        "consecutive_failures_to_stop": cfg.consecutive_failures_to_stop,
        "similar_issues_k": cfg.similar_issues_k,
        "attachment_max_files": cfg.attachment_max_files,
        "index_min_issues": cfg.index_min_issues,
        "index_fallback_limit": cfg.index_fallback_limit,
        "llm_timeout_seconds": cfg.llm_timeout_seconds,
        "use_llm_retrieval": cfg.use_llm_retrieval,
        "prompt_overrides_enabled": cfg.prompt_overrides_enabled,
        "use_deterministic_pipeline": getattr(cfg, "use_deterministic_pipeline", True),
        "min_confidence_threshold": getattr(cfg, "min_confidence_threshold", 0.0),
        "overrides": agentic_config.get_overrides(),
    }


@router.patch("/agentic-config")
def patch_agentic_config(overrides: dict[str, int | float] = Body(default_factory=dict)):
    """Apply runtime config overrides (e.g. max_validation_retries, recipe_candidates_k). Resets on restart."""
    for k, v in overrides.items():
        if isinstance(v, (int, float)):
            agentic_config.set_override(k, v)
    return {"overrides": agentic_config.get_overrides()}


class CrawlRequest(BaseModel):
    """Optional body for crawl-aem-guides. When urls provided, crawl only those; otherwise use config."""

    urls: list[str] | None = None


class IndexDitaPdfRequest(BaseModel):
    """Optional body for index-dita-pdf. When urls provided, index only those; otherwise use defaults (1.2 + 1.3 Part 1 Base)."""

    urls: list[str] | None = None


class IndexGithubDitaRequest(BaseModel):
    """Index DITA from a GitHub repo subtree (zip via codeload) into tenant examples/RAG and optionally into global `aem_guides` for chat."""

    tenant_id: str = "default"
    source_url: str | None = None
    index_all: bool = False
    max_files: int = 400
    include_maps: bool = True
    index_into_rag: bool = True

    @field_validator("tenant_id", mode="before")
    @classmethod
    def _coerce_tenant_id(cls, v: object) -> str:
        if v is None:
            return "default"
        s = str(v).strip()
        return s if s else "default"


@router.post("/crawl-aem-guides")
async def crawl_aem_guides(body: CrawlRequest | None = Body(None)):
    """Crawl AEM Guides documentation from Experience League, index chunks, and store for RAG.
    Run this before using doc enrichment in Jira analysis. Returns pages_crawled, chunks_stored, errors.
    Optional body: { \"urls\": [\"https://...\"] } to crawl specific URLs; omit to use config file."""
    try:
        from app.services.crawl_service import crawl_and_index
        urls = body.urls if body and body.urls else None
        stats = await asyncio.to_thread(crawl_and_index, urls=urls)
        return stats
    except Exception as e:
        logger.error_structured(
            "AEM Guides crawl failed",
            extra_fields={"error": str(e)},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=sanitize_error_for_client(e))


def _check_crawl_status() -> dict:
    """Check Playwright availability, Chromium install, and crawl output files."""
    result = {
        "playwright_available": False,
        "chromium_installed": False,
        "structured_by_url_exists": False,
        "chunks_file_exists": False,
        "chunks_with_structured_count": 0,
        "last_crawl_errors": [],
    }
    try:
        import playwright
        result["playwright_available"] = True
    except ImportError:
        return result

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                result["chromium_installed"] = True
            except Exception:
                pass
    except Exception:
        pass

    storage = get_storage()
    from app.services.crawl_service import (
        DOC_CHUNKS_FILENAME,
        STRUCTURED_BY_URL_FILENAME,
    )
    structured_path = storage.base_path / STRUCTURED_BY_URL_FILENAME
    chunks_path = storage.base_path / DOC_CHUNKS_FILENAME
    result["structured_by_url_exists"] = structured_path.exists() and structured_path.is_file()
    result["chunks_file_exists"] = chunks_path.exists() and chunks_path.is_file()

    if result["chunks_file_exists"]:
        try:
            data = json.loads(chunks_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                result["chunks_with_structured_count"] = sum(
                    1 for r in data
                    if isinstance(r, dict) and (
                        (r.get("paragraphs") or []) or
                        (r.get("list_items") or []) or
                        (r.get("codeph") or []) or
                        (r.get("codeblocks") or []) or
                        (r.get("tables") or [])
                    )
                )
        except (json.JSONDecodeError, OSError):
            pass

    return result


@router.get("/crawl-status")
def get_crawl_status():
    """Return Playwright/chromium availability and crawl output diagnostics.
    Use before running crawl to verify Playwright is working."""
    return _check_crawl_status()


@router.get("/rag-status")
def get_rag_status(tenant_id: str = Query("default", description="Tenant for GitHub DITA registry summary")):
    """Return RAG source status: ChromaDB collection counts for AEM Guides (Experience League) and DITA PDF.
    When counts are 0, run POST /api/v1/ai/crawl-aem-guides, POST /api/v1/ai/index-dita-pdf, and optionally
    POST /api/v1/ai/index-github-dita-examples (for Oxygen GitHub DITA / dev_guide in the same collection)."""
    from app.services.vector_store_service import (
        CHROMA_COLLECTION_AEM_GUIDES,
        CHROMA_COLLECTION_DITA_SPEC,
        get_collection_count,
        is_chroma_available,
    )
    from app.services.github_dita_examples_service import get_github_dita_rag_summary
    from app.services.tavily_search_service import get_tavily_rag_status
    from app.utils.evidence_extractor import USE_AEM_DOCS_ENRICHMENT

    def _payload(chroma_ok: bool, aem_count: int, dita_count: int, err: str | None = None) -> dict:
        try:
            tavily = get_tavily_rag_status()
        except Exception as ex:
            tavily = {
                "configured": False,
                "chat_enabled": False,
                "hint": "Set TAVILY_API_KEY in backend/.env or project-root .env, then restart the backend.",
            }
            err = f"{err}; tavily: {ex}" if err else str(ex)
        try:
            github_dita = get_github_dita_rag_summary(tenant_id=tenant_id)
        except Exception as ex:
            merge_github = os.getenv("GITHUB_DITA_ALSO_MERGE_TO_AEM_RAG", "true").lower() in ("true", "1", "yes")
            github_dita = {
                "source": "Oxygen userguide & other GitHub DITA trees (zip download)",
                "indexed_subtrees": 0,
                "merged_into_aem_guides_chunks": 0,
                "merge_into_aem_guides_enabled": merge_github,
                "source_labels": [],
                "last_indexed_at": "",
                "populate_via": "POST /api/v1/ai/index-github-dita-examples",
            }
            err = f"{err}; github_dita summary: {ex}" if err else str(ex)
        return {
            "chroma_available": chroma_ok,
            "error": err,
            "tavily": tavily,
            "aem_guides": {
                "source": "Experience League crawl; optional GitHub DITA examples can merge into this same collection.",
                "collection": CHROMA_COLLECTION_AEM_GUIDES,
                "chunk_count": aem_count,
                "count_scope": (
                    "This number is only embeddings in Chroma `aem_guides`. "
                    "DITA spec PDFs live in `dita_spec` (see below). "
                    "Recipe definitions are not stored as RAG chunks here."
                ),
                "used_in": ["mechanism_classifier", "pattern_classifier", "evidence_extractor", "chat_rag"],
                "populate_via": "POST /api/v1/ai/crawl-aem-guides; GitHub DITA: POST /api/v1/ai/index-github-dita-examples",
                "enrichment_enabled": USE_AEM_DOCS_ENRICHMENT,
            },
            "dita_spec": {
                "source": "DITA 1.2 + 1.3 Part 1 Base PDFs (LangChain PyPDFLoader)",
                "collection": CHROMA_COLLECTION_DITA_SPEC,
                "chunk_count": dita_count,
                "count_scope": "Embeddings in Chroma `dita_spec` only (separate from `aem_guides`).",
                "used_in": ["scenario_expander", "plan_for_scenario"],
                "populate_via": "POST /api/v1/ai/index-dita-pdf",
            },
            "github_dita": github_dita,
        }

    try:
        chroma_ok = is_chroma_available()
        aem_count = get_collection_count(CHROMA_COLLECTION_AEM_GUIDES) if chroma_ok else 0
        dita_count = get_collection_count(CHROMA_COLLECTION_DITA_SPEC) if chroma_ok else 0
        return _payload(chroma_ok, aem_count, dita_count, None)
    except Exception as e:
        logger.warning_structured("RAG status failed", extra_fields={"error": str(e)})
        # Always return the same shape so Settings UI can show all sections (with zeros).
        try:
            return _payload(False, 0, 0, str(e))
        except Exception as e2:
            logger.warning_structured("RAG status fallback failed", extra_fields={"error": str(e2)})
            return {
                "chroma_available": False,
                "error": f"{e}; fallback: {e2}",
                "aem_guides": {"chunk_count": 0, "source": "", "populate_via": ""},
                "dita_spec": {"chunk_count": 0, "source": "", "populate_via": ""},
                "github_dita": {"indexed_subtrees": 0, "merged_into_aem_guides_chunks": 0},
                "tavily": {
                    "configured": False,
                    "chat_enabled": False,
                    "hint": "Set TAVILY_API_KEY in backend/.env or project-root .env, then restart the backend.",
                },
            }


@router.post("/index-dita-pdf")
async def index_dita_pdf(body: IndexDitaPdfRequest | None = Body(None)):
    """Index DITA 1.2 and 1.3 Part 1 Base PDFs (or custom urls). Download, load with LangChain, split, embed, and store in ChromaDB for RAG.
    Run this to enable DITA spec retrieval. Returns pages_loaded, chunks_stored, sources_indexed, errors."""
    try:
        from app.services.dita_pdf_index_service import index_dita_pdf as index_dita_pdf_fn
        urls = body.urls if body and body.urls else None
        stats = await asyncio.to_thread(index_dita_pdf_fn, pdf_urls=urls)
        return stats
    except Exception as e:
        logger.error_structured(
            "DITA PDF index failed",
            extra_fields={"error": str(e)},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=sanitize_error_for_client(e))


@router.post("/index-github-dita-examples")
async def index_github_dita_examples_route(body: IndexGithubDitaRequest | None = Body(None)):
    """Index DITA files from a GitHub folder (e.g. Oxygen userguide `DITA` or `DITA/dev_guide`) into ChromaDB.
    Uses codeload zip, not HTML crawl. When `index_all` is true, indexes `GITHUB_DITA_SOURCE_URL` plus defaults
    (including dev_guide) and `GITHUB_DITA_ADDITIONAL_SOURCE_URLS`. Merges into global `aem_guides` for chat when
    `GITHUB_DITA_ALSO_MERGE_TO_AEM_RAG` is true."""
    try:
        from app.services.github_dita_examples_service import (
            DEFAULT_GITHUB_DITA_SOURCE_URL,
            index_all_github_dita_examples,
            index_github_dita_examples,
        )

        b = body or IndexGithubDitaRequest()
        if b.index_all:
            results = await index_all_github_dita_examples(
                tenant_id=b.tenant_id,
                max_files=b.max_files,
                include_maps=b.include_maps,
                index_into_rag=b.index_into_rag,
            )
            return {
                "index_all": True,
                "sources": [r.to_dict() for r in results],
                "errors": [e for r in results for e in r.errors],
            }
        src = (b.source_url or DEFAULT_GITHUB_DITA_SOURCE_URL).strip()
        result = await index_github_dita_examples(
            tenant_id=b.tenant_id,
            source_url=src,
            max_files=b.max_files,
            include_maps=b.include_maps,
            index_into_rag=b.index_into_rag,
        )
        out = result.to_dict()
        out["index_all"] = False
        return out
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error_structured(
            "GitHub DITA index failed",
            extra_fields={"error": str(e)},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=sanitize_error_for_client(e))


@router.get("/feedback")
def list_feedback(
    jira_id: str | None = Query(None, description="Filter by Jira issue key"),
    run_id: str | None = Query(None, description="Filter by run ID"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    session: Session = Depends(get_db),
):
    """List RunFeedback records for debugging and analysis."""
    q = session.query(RunFeedback)
    if jira_id:
        q = q.filter(RunFeedback.jira_id == jira_id)
    if run_id:
        q = q.filter(RunFeedback.run_id == run_id)
    rows = q.order_by(RunFeedback.created_at.desc()).limit(limit).all()
    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "run_id": r.run_id,
            "jira_id": r.jira_id,
            "scenario_id": r.scenario_id,
            "user_rating": r.user_rating,
            "expected_recipe_id": r.expected_recipe_id,
            "selected_feature": r.selected_feature,
            "selected_pattern": r.selected_pattern,
            "recipes_used": json.loads(r.recipes_used) if r.recipes_used else [],
            "validation_errors": json.loads(r.validation_errors) if r.validation_errors else [],
            "eval_metrics": json.loads(r.eval_metrics) if r.eval_metrics else {},
            "suggested_updates": json.loads(r.suggested_updates) if r.suggested_updates else {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return {"items": items, "total": len(items)}


@router.get("/feedback/insights")
def get_feedback_insights(
    jira_id: str | None = Query(None, description="Filter by Jira issue key"),
    limit: int = Query(200, ge=1, le=1000, description="Max feedback records to aggregate"),
    session: Session = Depends(get_db),
):
    """Aggregate RunFeedback across runs for cross-run learning and recommendations."""
    return aggregate_feedback_insights(session, limit=limit, jira_id=jira_id)


@router.post("/feedback/apply-overrides")
def apply_feedback_overrides(
    limit: int = Query(200, ge=1, le=1000, description="Max feedback records to aggregate"),
    jira_id: str | None = Query(None, description="Filter by Jira issue key"),
    session: Session = Depends(get_db),
):
    """Compute prompt overrides from RunFeedback and persist. Trigger manually or via cron."""
    overrides = compute_prompt_overrides_from_feedback(session, limit=limit, jira_id=jira_id)
    save_prompt_overrides(overrides)
    planner = overrides.get("generator_invocation_planner", {})
    return {
        "applied": True,
        "deprioritize_recipes": planner.get("deprioritize_recipes", []),
        "append_rules_count": len(planner.get("append_rules", [])),
    }


@router.post("/feedback/export-pairs")
def export_feedback_pairs(
    limit: int = Query(200, ge=1, le=1000, description="Max feedback records to export"),
    session: Session = Depends(get_db),
):
    """Export (evidence, recipe_id, label) pairs to JSON for eval retrieval accuracy. Returns path and count."""
    output_path = str(get_storage().base_path / "recipe_feedback_pairs.json")
    count = export_feedback_pairs_for_eval(session, output_path, limit=limit)
    return {"path": output_path, "count": count}


class FeedbackSubmitRequest(BaseModel):
    run_id: str
    scenario_id: str | None = None
    user_rating: str  # thumbs_down | thumbs_up | wrong_recipe
    expected_recipe_id: str | None = None


@router.post("/feedback/submit")
def submit_feedback(
    body: FeedbackSubmitRequest,
    session: Session = Depends(get_db),
):
    """Submit user feedback (thumbs up/down, expected recipe) for a run. Auto-applies overrides when AI_AUTO_APPLY_FEEDBACK=true."""
    if body.user_rating not in ("thumbs_up", "thumbs_down", "wrong_recipe"):
        raise HTTPException(status_code=400, detail="user_rating must be thumbs_up, thumbs_down, or wrong_recipe")
    try:
        UUID(body.run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="run_id must be a valid UUID")

    q = session.query(RunFeedback).filter(RunFeedback.run_id == body.run_id)
    if body.scenario_id:
        q = q.filter(RunFeedback.scenario_id == body.scenario_id)
    rows = q.all()

    if rows:
        for r in rows:
            r.user_rating = body.user_rating
            r.expected_recipe_id = body.expected_recipe_id
    else:
        feedback = RunFeedback(
            id=str(uuid4()),
            run_id=body.run_id,
            jira_id=None,
            scenario_id=body.scenario_id,
            user_rating=body.user_rating,
            expected_recipe_id=body.expected_recipe_id,
            created_at=datetime.utcnow(),
        )
        session.add(feedback)
    session.commit()

    auto_apply = os.getenv("AI_AUTO_APPLY_FEEDBACK", "true").lower() in ("true", "1", "yes")
    if auto_apply:
        try:
            overrides = compute_prompt_overrides_from_feedback(session, limit=200, jira_id=None)
            save_prompt_overrides(overrides)
        except Exception as e:
            logger.warning_structured("Auto-apply feedback overrides failed", extra_fields={"error": str(e)})

    return {"status": "ok"}


@router.get("/feedback/for-run/{run_id}")
def get_feedback_for_run(run_id: str, session: Session = Depends(get_db)):
    """Return feedback records for a run (for UI to show existing feedback)."""
    rows = session.query(RunFeedback).filter(RunFeedback.run_id == run_id).order_by(RunFeedback.created_at.desc()).all()
    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "run_id": r.run_id,
            "jira_id": r.jira_id,
            "scenario_id": r.scenario_id,
            "user_rating": r.user_rating,
            "expected_recipe_id": r.expected_recipe_id,
            "selected_feature": r.selected_feature,
            "selected_pattern": r.selected_pattern,
            "recipes_used": json.loads(r.recipes_used) if r.recipes_used else [],
            "validation_errors": json.loads(r.validation_errors) if r.validation_errors else [],
            "eval_metrics": json.loads(r.eval_metrics) if r.eval_metrics else {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return {"items": items, "total": len(items)}


@router.get("/feedback/{feedback_id}")
def get_feedback(feedback_id: str, session: Session = Depends(get_db)):
    """Get a single RunFeedback record by ID."""
    row = session.query(RunFeedback).filter(RunFeedback.id == feedback_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {
        "id": row.id,
        "run_id": row.run_id,
        "jira_id": row.jira_id,
        "scenario_id": row.scenario_id,
        "user_rating": row.user_rating,
        "expected_recipe_id": row.expected_recipe_id,
        "selected_feature": row.selected_feature,
        "selected_pattern": row.selected_pattern,
        "recipes_used": json.loads(row.recipes_used) if row.recipes_used else [],
        "validation_errors": json.loads(row.validation_errors) if row.validation_errors else [],
        "eval_metrics": json.loads(row.eval_metrics) if row.eval_metrics else {},
        "suggested_updates": json.loads(row.suggested_updates) if row.suggested_updates else {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("/run-eval")
async def run_eval(
    run_execution: bool = Query(True, description="Run dataset execution and validation (set false for planning-only eval)"),
):
    """Run evaluation on eval_cases.json and return metrics report."""
    report = await run_evaluation(run_execution=run_execution)
    return report


@router.get("/generate-status/{run_id}")
def get_generate_status(run_id: str):
    """Poll generate progress. Returns status, current_scenario, scenarios_done/total, and result when completed."""
    if run_id not in _generate_progress:
        raise HTTPException(status_code=404, detail="Run not found")
    return _generate_progress[run_id]


@router.get("/generate-stream/{run_id}")
async def get_generate_stream(run_id: str):
    """SSE stream of generate progress. Emits events when progress updates. Closes when completed or failed."""
    if run_id not in _generate_progress:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        last_sent = None
        poll_interval = 1.0
        while True:
            data = _generate_progress.get(run_id, {})
            status = data.get("status", "unknown")
            if data != last_sent:
                last_sent = dict(data)
                yield f"data: {json.dumps(last_sent)}\n\n"
            if status in ("completed", "failed"):
                break
            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _generate_from_text_background_task(body: GenerateFromTextRequest, run_id: str, skip_rag_check: bool = False) -> None:
    """Run generate-from-text in background; updates _generate_progress."""
    try:
        await _run_generate_from_text(body, run_id, request=None, skip_rag_check=skip_rag_check)
    except Exception as e:
        _generate_progress[run_id] = {"status": "failed", "error": str(e)}
        logger.error_structured(
            "Background generate-from-text failed",
            extra_fields={"run_id": run_id, "error": str(e)},
            exc_info=True,
        )


@router.post("/generate-from-text")
async def generate_from_text(
    request: Request,
    body: GenerateFromTextRequest,
    async_mode: bool = Query(False, alias="async", description="If true, return immediately and poll /generate-status/{run_id}"),
    skip_rag_check: bool = Query(True, description="Skip RAG readiness check (default True so paste works without indexing)"),
):
    """ChatGPT-style: paste raw Jira text -> DITA directly via LLM (no mechanism/pattern pipeline)."""
    err = check_generate_from_text_limit(request)
    if err:
        raise HTTPException(status_code=429, detail=err)
    err = validate_generate_text(body.text, body.instructions)
    if err:
        raise HTTPException(status_code=400, detail=err)

    run_id = str(uuid4())
    if async_mode:
        _generate_progress[run_id] = {
            "status": "running",
            "jira_id": f"TEXT-{run_id[:8]}",
            "scenarios_total": 1,
            "scenarios_done": 0,
            "current_scenario": None,
        }
        asyncio.create_task(_generate_from_text_background_task(body, run_id, skip_rag_check))
        return {"run_id": run_id, "status": "running", "message": f"Poll GET /ai/generate-status/{run_id} for progress"}
    return await _run_generate_from_text(body, run_id, request=request, skip_rag_check=skip_rag_check)
