from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import httpx

from app.api.routes import remote_mcp
from app.core.schemas_qe_pattern_mcp import ResolveQePatternsResponse


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_claude_mcp_server():
    module_path = REPOSITORY_ROOT / "mcp_server" / "server.py"
    spec = importlib.util.spec_from_file_location(
        "pfix01_claude_mcp_server", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_remote_mcp_exposes_additive_structured_resolver_contract() -> None:
    tools = {tool["name"]: tool for tool in remote_mcp._tools()}

    assert "resolve_qe_patterns" in tools
    resolver = tools["resolve_qe_patterns"]
    schema = resolver["inputSchema"]
    assert schema["required"] == ["domain"]
    assert schema["additionalProperties"] is False
    assert schema["anyOf"] == [
        {
            "required": ["change_surfaces"],
            "properties": {"change_surfaces": {"minItems": 1}},
        },
        {
            "required": ["abstract_signals"],
            "properties": {"abstract_signals": {"minItems": 1}},
        },
    ]
    assert "change_surfaces" in schema["properties"]
    assert "abstract_signals" in schema["properties"]
    assert "scope_constraints" in schema["properties"]


def test_remote_mcp_resolver_is_fail_closed_for_unapproved_train_patterns() -> None:
    result = remote_mcp._resolve_qe_patterns(
        {
            "domain": "Publishing",
            "change_surfaces": ["STATE_PARTITION"],
            "include_analysis_candidates": False,
        }
    )

    assert result["schema_version"] == "aem-guides-qe-pattern-mcp-v1"
    assert result["pattern_count"] == 33
    assert result["validated_production_pattern_count"] == 0
    assert result["provider_status"] == "EMPTY"
    assert result["matched_patterns"] == []


def test_analysis_candidates_are_observable_but_non_influential() -> None:
    result = remote_mcp._resolve_qe_patterns(
        {
            "domain": "Publishing",
            "change_surfaces": ["STATE_PARTITION"],
            "include_analysis_candidates": True,
        }
    )

    assert result["provider_status"] == "SUCCESS"
    assert result["matched_patterns"]
    assert all(
        match["influence_allowed"] is False and match["blocking_recommendations"] == []
        for match in result["matched_patterns"]
    )
    assert all("final_ac" not in match for match in result["matched_patterns"])


def test_remote_mcp_invalid_request_is_redacted_and_schema_valid() -> None:
    result = remote_mcp._resolve_qe_patterns(
        {
            "domain": "Publishing",
            "change_surfaces": ["output hierarchy"],
            "include_analysis_candidates": "false",
        }
    )
    response = ResolveQePatternsResponse.model_validate(result)

    assert response.provider_status == "INVALID_REQUEST"
    assert response.error_code == "QE_PATTERN_REQUEST_VALIDATION_FAILED"
    assert response.pattern_count == 0
    assert response.matched_patterns == []


def test_remote_mcp_rejects_unknown_request_fields() -> None:
    result = remote_mcp._resolve_qe_patterns(
        {
            "domain": "Publishing",
            "change_surfaces": ["output hierarchy"],
            "typoed_scope_field": "must not be ignored",
        }
    )
    response = ResolveQePatternsResponse.model_validate(result)

    assert response.provider_status == "INVALID_REQUEST"
    assert response.error_code == "QE_PATTERN_REQUEST_VALIDATION_FAILED"
    assert response.matched_patterns == []


def test_claude_desktop_server_uses_same_backend_resolver_route() -> None:
    source = (REPOSITORY_ROOT / "mcp_server" / "server.py").read_text(encoding="utf-8")

    assert 'name="resolve_qe_patterns"' in source
    assert 'if name == "resolve_qe_patterns"' in source
    assert '"/api/v1/mcp/resolve-qe-patterns"' in source


def test_claude_desktop_server_redacts_backend_validation_details(monkeypatch) -> None:
    module = _load_claude_mcp_server()

    async def invalid_post(path: str, body: dict):
        request = httpx.Request("POST", f"http://backend.test{path}")
        response = httpx.Response(
            422,
            request=request,
            text='{"detail":[{"input":"confidential current decision"}]}',
        )
        raise httpx.HTTPStatusError(
            "invalid",
            request=request,
            response=response,
        )

    monkeypatch.setattr(module, "_post", invalid_post)
    result = asyncio.run(
        module._dispatch(
            "resolve_qe_patterns",
            {
                "domain": "Publishing",
                "change_surfaces": ["output hierarchy"],
            },
        )
    )
    response = ResolveQePatternsResponse.model_validate(result)

    assert response.provider_status == "INVALID_REQUEST"
    assert response.error_code == "QE_PATTERN_REQUEST_VALIDATION_FAILED"
    assert "confidential" not in str(result)


def test_existing_mcp_tools_remain_available() -> None:
    tool_names = {tool["name"] for tool in remote_mcp._tools()}

    assert {
        "ask_dita_expert",
        "generate_dita_ot_output",
        "search_jira_history",
        "audit_jira_corpus",
    }.issubset(tool_names)
