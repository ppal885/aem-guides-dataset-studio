from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from app.core.auth import CurrentUser, UserIdentity
from app.core.structured_logging import LoggingContext, get_structured_logger
from app.evidence_gateway.models import (
    FetchCodeContextRequest,
    FetchEvidenceRequest,
    GetCodeDiffRequest,
    SearchCodeRequest,
    SearchKnowledgeRequest,
    ToolCallRequest,
)
from app.evidence_gateway.service import EvidenceGatewayService

router = APIRouter(prefix="/mcp", tags=["evidence-mcp"])
logger = get_structured_logger(__name__)


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


def _tools() -> list[dict[str, Any]]:
    return [
        _tool("health", "Return safe operational health for the evidence gateway.", {}),
        _tool("list_corpora", "List knowledge corpora authorized for the current user.", {}),
        _tool("search_knowledge", "Search authorized documentation/specification corpora and return citation metadata.", SearchKnowledgeRequest.model_json_schema()),
        _tool("fetch_evidence", "Fetch selected chunks plus bounded neighboring chunks by stable chunk ID.", FetchEvidenceRequest.model_json_schema()),
        _tool("list_repositories", "List repository aliases authorized for the current user.", {}),
        _tool("search_code", "Search allowlisted repository checkouts using read-only Git grep.", SearchCodeRequest.model_json_schema()),
        _tool("fetch_code_context", "Fetch a bounded source window from an authorized repository revision.", FetchCodeContextRequest.model_json_schema()),
        _tool("get_code_diff", "Return a bounded read-only Git diff between validated revisions.", GetCodeDiffRequest.model_json_schema()),
    ]


def _tool(name: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "description": description, "inputSchema": schema or {"type": "object", "properties": {}}}


@router.get("/live")
def live():
    return {"status": "alive"}


@router.post("")
async def mcp_json_rpc(payload: JsonRpcRequest, request: Request, user: UserIdentity = CurrentUser):
    correlation_id = request.headers.get("x-correlation-id") or str(uuid4())
    with LoggingContext(user_id=user.id, correlation_id=correlation_id):
        try:
            if payload.method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "aem-guides-evidence", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                }
            elif payload.method == "tools/list":
                result = {"tools": _tools()}
            elif payload.method == "tools/call":
                call = ToolCallRequest.model_validate(payload.params)
                result = _call_tool(call, user, correlation_id)
            else:
                return _rpc_error(payload.id, -32601, "Method not found", correlation_id)
            return {"jsonrpc": "2.0", "id": payload.id, "result": result}
        except ValidationError:
            return _rpc_error(payload.id, -32602, "Invalid tool arguments", correlation_id)
        except PermissionError:
            return _rpc_error(payload.id, -32003, "Forbidden", correlation_id)
        except Exception as exc:
            logger.warning_structured(
                "evidence_mcp_call_failed",
                extra_fields={"method": payload.method, "error_type": type(exc).__name__},
            )
            return _rpc_error(payload.id, -32000, "Evidence gateway request failed", correlation_id)


@router.get("/health")
def health(user: UserIdentity = CurrentUser):
    return EvidenceGatewayService().health(user)


def _call_tool(call: ToolCallRequest, user: UserIdentity, correlation_id: str) -> dict[str, Any] | list[dict[str, Any]]:
    service = EvidenceGatewayService()
    if call.name == "health":
        return service.health(user, correlation_id)
    if call.name == "list_corpora":
        return [item.model_dump() for item in service.list_corpora(user)]
    if call.name == "search_knowledge":
        return service.search_knowledge(user, SearchKnowledgeRequest.model_validate(call.arguments), correlation_id).model_dump()
    if call.name == "fetch_evidence":
        return service.fetch_evidence(user, FetchEvidenceRequest.model_validate(call.arguments), correlation_id).model_dump()
    if call.name == "list_repositories":
        return [item.model_dump() for item in service.list_repositories(user)]
    if call.name == "search_code":
        return service.search_code(user, SearchCodeRequest.model_validate(call.arguments), correlation_id).model_dump()
    if call.name == "fetch_code_context":
        return service.fetch_code_context(user, FetchCodeContextRequest.model_validate(call.arguments), correlation_id).model_dump()
    if call.name == "get_code_diff":
        return service.get_code_diff(user, GetCodeDiffRequest.model_validate(call.arguments), correlation_id).model_dump()
    raise HTTPException(status_code=404, detail="Unknown tool")


def _rpc_error(request_id: str | int | None, code: int, message: str, correlation_id: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message, "data": {"correlation_id": correlation_id}},
    }

