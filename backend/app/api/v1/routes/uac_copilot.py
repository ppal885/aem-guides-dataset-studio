"""UAC Copilot API — grounded UAC brief from enriched Jira + hybrid similar-ticket retrieval."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.auth import CurrentUser
from app.core.schemas_uac_intelligence import UacIntelligenceAnalyzeRequest, UacRequirementIntelligenceResponse
from app.core.schemas_uac_ui import UacAnalyzeApiResponse
from app.core.validation import validate_jira_id
from app.core.structured_logging import get_structured_logger
from app.services.jira_generate_resolve import extract_issue_key_from_shortcut
from app.services.uac_copilot_analyze_service import run_uac_analyze
from services.uac.uac_orchestrator import run_requirement_intelligence

logger = get_structured_logger(__name__)

router = APIRouter(prefix="/ai/uac", tags=["uac-copilot"], dependencies=[CurrentUser])


@router.get("/ping")
def uac_ping():
    """Lightweight route check — if this 404s, the UAC router is not mounted or the wrong backend is proxied."""
    return {"ok": True, "service": "uac-copilot"}


class UacAnalyzeRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "jira_key": "GUIDES-1234",
                    "include_similar": True,
                    "max_similar": 8,
                    "debug": False,
                    "include_qa_handoff": False,
                },
                {
                    "jira_key": "GUIDES-9999",
                    "include_similar": True,
                    "max_similar": 12,
                    "debug": True,
                    "include_qa_handoff": True,
                },
            ]
        }
    )

    jira_key: str = Field(..., min_length=3, max_length=2048, examples=["GUIDES-1234"])
    include_similar: bool = True
    max_similar: int = Field(8, ge=0, le=24)
    debug: bool = False
    include_qa_handoff: bool = Field(
        False,
        description="When true, runs a second LLM pass for structured QA handoff (smoke vs deep, sign-off blockers, Jira test outline). Extra tokens/latency.",
    )


@router.post("/analyze", response_model=UacAnalyzeApiResponse)
async def uac_analyze(body: UacAnalyzeRequest) -> UacAnalyzeApiResponse:
    jk_in = body.jira_key.strip()
    jk = extract_issue_key_from_shortcut(jk_in) or jk_in.strip()
    err = validate_jira_id(jk)
    if err:
        raise HTTPException(status_code=400, detail=err)

    try:
        payload = await run_uac_analyze(
            jk,
            include_similar=body.include_similar,
            max_similar=body.max_similar,
            debug=body.debug,
            include_qa_handoff=body.include_qa_handoff,
        )
        return UacAnalyzeApiResponse.model_validate(payload)
    except ValueError as e:
        logger.warning_structured("uac_analyze_bad_request", extra_fields={"jira_key": jk, "error": str(e)})
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error_structured(
            "uac_analyze_unexpected_error",
            extra_fields={"jira_key": jk, "error_type": type(e).__name__, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="UAC analysis failed") from None


async def _execute_uac_requirement_intelligence(
    request: Request,
    body: UacIntelligenceAnalyzeRequest,
) -> UacRequirementIntelligenceResponse:
    """Shared handler for enterprise UAC intelligence (RAG + analyzers, evidence manifest)."""
    jk_in = body.jira_key.strip()
    jk = extract_issue_key_from_shortcut(jk_in) or jk_in.strip()
    err = validate_jira_id(jk)
    if err:
        raise HTTPException(status_code=400, detail=err)

    cid_hdr = request.headers.get("x-correlation-id") or request.headers.get("X-Correlation-ID")
    cid = (cid_hdr or "").strip() or None

    try:
        raw = await asyncio.to_thread(
            run_requirement_intelligence,
            jk,
            debug=body.debug,
            include_docs=body.include_docs,
            max_similar_jiras=body.max_similar_jiras,
            correlation_id=cid,
        )
    except ValueError as e:
        logger.warning_structured(
            "uac_intelligence_bad_request",
            extra_fields={"jira_key": jk, "error": str(e)},
        )
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        logger.error_structured(
            "uac_intelligence_unexpected_error",
            extra_fields={"jira_key": jk, "error_type": type(e).__name__, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="UAC requirement intelligence failed") from None

    try:
        return UacRequirementIntelligenceResponse.model_validate(raw)
    except ValidationError:
        logger.error_structured(
            "uac_intelligence_response_validation_failed",
            extra_fields={"jira_key": jk, "keys_sample": list(raw.keys())[:24] if isinstance(raw, dict) else []},
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Intelligence engine produced an invalid payload",
        ) from None


@router.post(
    "/requirement-intelligence",
    response_model=UacRequirementIntelligenceResponse,
    summary="UAC requirement intelligence (enterprise)",
    description=(
        "Structured, evidence-backed requirement analysis for PM/QA/Dev UAC alignment. "
        "Distinct from legacy POST /ai/uac/analyze (Copilot brief). "
        "Optional header: X-Correlation-ID (echoed in response.correlation_id when provided)."
    ),
)
async def uac_requirement_intelligence(
    request: Request,
    body: UacIntelligenceAnalyzeRequest,
) -> UacRequirementIntelligenceResponse:
    return await _execute_uac_requirement_intelligence(request, body)


@router.post(
    "/intelligence",
    response_model=UacRequirementIntelligenceResponse,
    summary="Alias of /requirement-intelligence",
    description="Same request body, headers, and response as POST /ai/uac/requirement-intelligence.",
)
async def uac_requirement_intelligence_alias(
    request: Request,
    body: UacIntelligenceAnalyzeRequest,
) -> UacRequirementIntelligenceResponse:
    return await _execute_uac_requirement_intelligence(request, body)
