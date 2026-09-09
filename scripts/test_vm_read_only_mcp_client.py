"""Offline transport contracts for the packaged VM-only evidence profile.

Run with python -B scripts/test_vm_read_only_mcp_client.py. All HTTP uses fakes.
"""

import asyncio
import ast
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

import httpx


ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATHS = [ROOT / "release-artifacts" / name / "server.py" for name in (
    "aem-guides-mcp-client-windows", "aem-guides-mcp-client-unix")]
REAL_CLIENT = httpx.AsyncClient
PIN = "a" * 64


def load_client(path):
    spec = importlib.util.spec_from_file_location("read_only_vm_client", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def status_result(pin=PIN):
    return {"status": "ok", "index_identity": {
        "schema_version": "chroma-index-identity-v1", "status": "OK",
        "mode": "REMOTE",
        "target_fingerprint": pin,
    }}


def rpc_result(value, name="check_rag_status"):
    return {"jsonrpc": "2.0", "id": f"team-wrapper-{name}", "result": {
        "content": [{"type": "text", "text": json.dumps(value)}],
    }}


class ReadOnlyVmClientTests(unittest.IsolatedAsyncioTestCase):
    def error_text(self, result):
        self.assertIsInstance(result, self.client.types.CallToolResult)
        self.assertTrue(result.isError)
        return result.content[0].text

    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "AEM_STUDIO_URL": "https://vm.example.test", "AEM_STUDIO_TOKEN": "",
            "AEM_STUDIO_READ_ONLY": "true", "AEM_STUDIO_ALLOW_INSECURE_HTTP": "",
            "AEM_STUDIO_EXPECTED_INDEX_FINGERPRINT": "", "AEM_STUDIO_TIMEOUT_SECONDS": "300",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = load_client(CLIENT_PATHS[0])
        self.requests = []
        self.options = []

    def http(self, handler):
        def record(request):
            self.requests.append(request)
            return handler(request)

        def factory(**kwargs):
            self.options.append(kwargs)
            return REAL_CLIENT(transport=httpx.MockTransport(record), **kwargs)

        return patch.object(self.client.httpx, "AsyncClient", factory)

    async def test_only_four_read_tools_are_advertised(self):
        self.assertEqual({tool.name for tool in await self.client.list_tools()}, self.client.READ_ONLY_TOOLS)
        self.assertEqual(self.client.AUTH_TOKEN, "")

    async def test_legacy_installer_http_token_is_rejected_before_network(self):
        # The legacy full-client installer profile must migrate explicitly;
        # neither an old setup nor HTTP opt-in may leak a credential.
        with patch.object(self.client, "READ_ONLY", False), \
                patch.object(self.client, "BACKEND_URL", "http://10.42.46.78:4502"), \
                patch.object(self.client, "AUTH_TOKEN", "dev-bypass"), \
                self.http(lambda request: self.fail("Credential sent over HTTP")):
            os.environ["AEM_STUDIO_ALLOW_INSECURE_HTTP"] = "true"
            with self.assertRaises(self.client.TransportConfigurationError):
                await self.client._post("/mcp", {})
        self.assertEqual(self.requests, [])

    async def test_all_mutations_and_unknown_tools_are_rejected_before_delivery(self):
        with patch.object(self.client, "_post", AsyncMock()) as delivery:
            for name in (*self.client.FEEDBACK_TOOL_NAMES, "upload_dataset_to_aem", "invented"):
                with self.subTest(tool=name), self.assertRaises(self.client.TransportConfigurationError):
                    await self.client._dispatch(name, {})
            delivery.assert_not_called()

    async def test_transport_itself_enforces_route_and_rpc_allowlists(self):
        with self.http(lambda request: self.fail("Unexpected delivery")):
            for path, body in (("/api/v1/admin/index", {}), ("/mcp", {
                    "method": "tools/call", "params": {"name": "capture_uac_feedback"}}),
                    ("/mcp", {"method": "initialize", "params": {"name": "check_rag_status"}})):
                with self.subTest(path=path), self.assertRaises(self.client.TransportConfigurationError):
                    await self.client._post(path, body)
        self.assertEqual(self.requests, [])

    async def test_read_profile_requires_explicit_origin(self):
        os.environ.pop("AEM_STUDIO_URL")
        with self.assertRaises(self.client.TransportConfigurationError):
            await self.client._dispatch("check_rag_status", {})

    async def test_invalid_origin_is_rejected_without_echoing_it(self):
        for origin in ("https://private-user:private-password@vm.example.test", "file:///private/path",
                       "https://vm.example.test/other", "https://vm.example.test?private-query",
                       "https://vm.example.test#private-fragment", "https://vm.example.test:99999",
                       "https://vm.example.test:", "https://vm.example.test\n", "https://vm.example.test\\evil"):
            with self.subTest(origin=origin), patch.object(self.client, "BACKEND_URL", origin):
                answer = await self.client.call_tool("check_rag_status", {})
                self.assertIn("ERROR", self.error_text(answer))
                self.assertNotIn("private", self.error_text(answer))

    async def test_plaintext_vm_requires_explicit_opt_in(self):
        with patch.object(self.client, "BACKEND_URL", "http://10.42.46.78:4502"):
            with self.assertRaises(self.client.TransportConfigurationError):
                self.client._headers()
            os.environ["AEM_STUDIO_ALLOW_INSECURE_HTTP"] = "true"
            self.assertNotIn("Authorization", self.client._headers())

    async def test_plaintext_vm_never_receives_credentials_even_with_opt_in(self):
        os.environ["AEM_STUDIO_ALLOW_INSECURE_HTTP"] = "true"
        with patch.object(self.client, "BACKEND_URL", "http://10.42.46.78:4502"), \
                patch.object(self.client, "AUTH_TOKEN", "synthetic-personal-credential"):
            with self.assertRaises(self.client.TransportConfigurationError):
                self.client._headers()

    async def test_https_and_loopback_allow_explicit_token_without_authentication_claims(self):
        with patch.object(self.client, "AUTH_TOKEN", "synthetic-personal-credential"):
            for origin in ("https://vm.example.test", "http://127.0.0.1:9000", "http://[::1]:9000"):
                with self.subTest(origin=origin), patch.object(self.client, "BACKEND_URL", origin):
                    self.assertEqual(self.client._headers()["Authorization"], "Bearer synthetic-personal-credential")

    async def test_no_default_token_or_proxy_and_bounded_timeout(self):
        with self.http(lambda request: httpx.Response(200, json=rpc_result(status_result()))):
            result = await self.client._dispatch("check_rag_status", {"tenant_id": "tenant-a"})
        self.assertEqual(result["index_identity"]["target_fingerprint"], PIN)
        self.assertNotIn("authorization", self.requests[0].headers)
        self.assertEqual(self.options[0], {"timeout": 30.0, "follow_redirects": False, "trust_env": False})
        self.assertNotIn("authenticated", result)

    async def test_redirect_is_not_followed_and_body_is_redacted(self):
        with self.http(lambda request: httpx.Response(302, headers={"location": "https://other.example.test"},
                                                     text="private-response")):
            answer = await self.client.call_tool("check_rag_status", {})
        self.assertEqual(len(self.requests), 1)
        self.assertIn("HTTP 302", self.error_text(answer))
        self.assertNotIn("private-response", self.error_text(answer))

    async def test_error_response_body_is_redacted(self):
        with self.http(lambda request: httpx.Response(503, text="private-response private-credential")):
            answer = await self.client.call_tool("check_rag_status", {})
        self.assertIn("HTTP 503", self.error_text(answer))
        self.assertNotIn("private", self.error_text(answer))

    async def test_response_size_is_bounded(self):
        with patch.object(self.client, "MAX_READ_RESPONSE_BYTES", 64), \
                self.http(lambda request: httpx.Response(200, text='{"data":"' + "x" * 100 + '"}')):
            answer = await self.client.call_tool("check_rag_status", {})
        self.assertIn("size limit", self.error_text(answer))

    async def test_invalid_json_is_redacted(self):
        with self.http(lambda request: httpx.Response(200, text="private-invalid-json")):
            answer = await self.client.call_tool("check_rag_status", {})
        self.assertIn("invalid JSON", self.error_text(answer))
        self.assertNotIn("private", self.error_text(answer))

    async def test_network_timeout_and_error_details_are_redacted(self):
        for error in (httpx.ConnectError("private-origin private-credential"),
                      httpx.ReadTimeout("private-origin private-credential")):
            with self.subTest(error=type(error).__name__), patch.object(self.client, "_post", AsyncMock(side_effect=error)):
                answer = await self.client.call_tool("check_rag_status", {})
                self.assertIn("ERROR", self.error_text(answer))
                self.assertNotIn("private", self.error_text(answer))

    async def test_mcp_errors_cannot_be_returned_as_successful_evidence(self):
        for response in ({"error": {"message": "private-rejection"}},
                         {"result": {"isError": True, "content": [{"text": "private-rejection"}]}}, []):
            with self.subTest(response=response), self.http(lambda request: httpx.Response(200, json=response)):
                answer = await self.client.call_tool("check_rag_status", {})
                self.assertIn("ERROR", self.error_text(answer))
                self.assertNotIn("private", self.error_text(answer))

    async def test_mcp_envelope_requires_exact_version_request_id_and_result(self):
        responses = [
            {}, {"result": rpc_result(status_result())["result"]},
            dict(rpc_result(status_result()), jsonrpc="1.0"),
            dict(rpc_result(status_result()), id="wrong-request"),
            {"jsonrpc": "2.0", "id": "team-wrapper-check_rag_status"},
        ]
        for response in responses:
            with self.subTest(response=response), self.http(lambda request: httpx.Response(200, json=response)):
                answer = await self.client.call_tool("check_rag_status", {})
                self.assertIn("ERROR", self.error_text(answer))

    async def test_empty_or_unstructured_mcp_content_is_an_error(self):
        results = [{}, {"content": []}, {"content": [{"type": "image", "text": "{}"}]}]
        results += [{"content": [{"type": "text", "text": text}]}
                    for text in ("", "private-response", "{}", "[]", "null", '"private-response"')]
        results += [{"structuredContent": value} for value in ({}, [], "private-response", None)]
        for result in results:
            response = dict(rpc_result(status_result()), result=result)
            with self.subTest(result=result), self.http(lambda request: httpx.Response(200, json=response)):
                answer = await self.client.call_tool("check_rag_status", {})
                self.assertIn("ERROR", self.error_text(answer))
                self.assertNotIn("private", self.error_text(answer))

    async def test_structured_mcp_result_and_empty_result_rows_are_supported(self):
        for result in ({"structuredContent": {"rows": []}},
                       {"content": [{"type": "text", "text": '{"rows": []}'}]}):
            response = dict(rpc_result({"rows": []}, "search_jira_history"), result=result)
            with self.subTest(result=result), self.http(lambda request: httpx.Response(200, json=response)):
                self.assertEqual(await self.client._dispatch("search_jira_history", {"query": "fixture"}), {"rows": []})

    async def test_total_deadline_cancels_slow_responses(self):
        async def slow_response(request):
            await asyncio.sleep(1)
            return httpx.Response(200, json=rpc_result(status_result()))

        with patch.object(self.client, "TIMEOUT_SECONDS", 0.01), self.http(slow_response):
            answer = await self.client.call_tool("check_rag_status", {})
        self.assertIn("VM transport request failed", self.error_text(answer))

    async def test_python_310_syntax_and_request_without_asyncio_timeout(self):
        ast.parse(CLIENT_PATHS[0].read_text(encoding="utf-8"), feature_version=(3, 10))
        with patch.object(self.client.asyncio, "timeout", None, create=True), \
                self.http(lambda request: httpx.Response(200, json=rpc_result(status_result()))):
            self.assertEqual(await self.client._dispatch("check_rag_status", {}), status_result())

    async def test_ask_uses_actual_rest_lookups_without_local_fallback(self):
        with self.http(lambda request: httpx.Response(200, json={"results": [{"source": "VM fixture"}]})), \
                patch.object(self.client, "_run_local_aem_upload", side_effect=AssertionError("local operation")):
            result = await self.client._dispatch("ask_dita_expert", {"question": "Explain <topic> @id", "tenant_id": "tenant-a"})
        self.assertEqual(result["tenant_id"], "tenant-a")
        self.assertEqual({request.url.path for request in self.requests}, self.client.READ_ONLY_LOOKUPS)
        self.assertEqual(len(self.requests), 3)

    async def test_failed_rest_lookup_is_explicit_unavailable_evidence(self):
        with self.http(lambda request: httpx.Response(500, text="private-response")):
            result = await self.client._dispatch("ask_dita_expert", {"question": "Explain topics"})
        for key in ("aem_guides_evidence", "dita_spec_evidence"):
            self.assertIn("unavailable", result[key]["error"])
            self.assertNotIn("private", result[key]["error"])

    async def test_pin_checked_before_each_retrieval_and_tenant_preserved(self):
        os.environ["AEM_STUDIO_EXPECTED_INDEX_FINGERPRINT"] = PIN

        def handler(request):
            params = json.loads(request.content)["params"]
            return httpx.Response(200, json=rpc_result(
                status_result() if params["name"] == "check_rag_status" else {"rows": []}, params["name"]))

        with self.http(handler):
            for _ in range(2):
                await self.client._dispatch("search_jira_history", {"query": "fixture", "tenant_id": "tenant-a"})
        calls = [json.loads(request.content)["params"] for request in self.requests]
        self.assertEqual([call["name"] for call in calls], ["check_rag_status", "search_jira_history"] * 2)
        self.assertTrue(all(call["arguments"]["tenant_id"] == "tenant-a" for call in calls))

    async def test_mismatch_or_missing_identity_blocks_retrieval_and_status_success(self):
        os.environ["AEM_STUDIO_EXPECTED_INDEX_FINGERPRINT"] = PIN
        for status in (status_result("b" * 64), {"status": "ok"}):
            for name in ("search_jira_history", "check_rag_status", "ask_dita_expert", "query_test_evidence_graph"):
                self.requests.clear()
                with self.subTest(name=name, status=status), self.http(lambda request: httpx.Response(200, json=rpc_result(status))):
                    answer = await self.client.call_tool(name, {"query": "fixture", "question": "fixture"})
                self.assertIn("fingerprint pin", self.error_text(answer))
                self.assertEqual(len(self.requests), 1)
                self.assertEqual(json.loads(self.requests[0].content)["params"]["name"], "check_rag_status")

    async def test_malformed_pin_and_timeout_fail_without_delivery(self):
        os.environ["AEM_STUDIO_EXPECTED_INDEX_FINGERPRINT"] = "private-invalid-pin"
        with self.http(lambda request: self.fail("Unexpected delivery")):
            answer = await self.client.call_tool("check_rag_status", {})
        self.assertNotIn("private", self.error_text(answer))
        os.environ["AEM_STUDIO_EXPECTED_INDEX_FINGERPRINT"] = ""
        for timeout in (float("nan"), float("inf"), 0, -1):
            with self.subTest(timeout=timeout), patch.object(self.client, "TIMEOUT_SECONDS", timeout):
                with self.assertRaises(self.client.TransportConfigurationError):
                    await self.client._post("/mcp", {"method": "tools/call", "params": {"name": "check_rag_status"}})

    async def test_matching_pin_still_requires_remote_index_mode(self):
        os.environ["AEM_STUDIO_EXPECTED_INDEX_FINGERPRINT"] = PIN
        for mode in ("EMBEDDED", "UNKNOWN", None):
            status = status_result()
            status["index_identity"]["mode"] = mode
            with self.subTest(mode=mode), self.http(lambda request: httpx.Response(200, json=rpc_result(status))):
                answer = await self.client.call_tool("check_rag_status", {})
                self.assertIn("fingerprint pin", self.error_text(answer))

    async def test_partial_remote_identity_remains_visible_when_target_pin_matches(self):
        os.environ["AEM_STUDIO_EXPECTED_INDEX_FINGERPRINT"] = PIN
        status = status_result()
        status["index_identity"]["status"] = "PARTIAL"
        with self.http(lambda request: httpx.Response(200, json=rpc_result(status))):
            result = await self.client._dispatch("check_rag_status", {})
        self.assertEqual(result["index_identity"]["status"], "PARTIAL")

    async def test_profile_off_preserves_other_tool_dispatch(self):
        with patch.object(self.client, "READ_ONLY", False), \
                patch.object(self.client, "AUTH_TOKEN", "synthetic-personal-credential"), \
                patch.object(self.client, "_remote_mcp_tool", AsyncMock(return_value={"fixture": True})) as remote:
            names = {tool.name for tool in await self.client.list_tools()}
            self.assertIn("upload_dataset_to_aem", names)
            self.assertTrue(self.client.FEEDBACK_TOOL_NAMES <= names)
            args = {"tenant_id": "tenant-a"}
            self.assertEqual(await self.client._dispatch("get_uac_feedback_readiness", args), {"fixture": True})
            remote.assert_awaited_once_with("get_uac_feedback_readiness", args)

    async def test_profile_off_does_not_manufacture_a_development_identity(self):
        with patch.object(self.client, "READ_ONLY", False):
            with self.assertRaises(self.client.TransportConfigurationError):
                self.client._headers()

    async def test_packaged_clients_are_identical(self):
        self.assertEqual(CLIENT_PATHS[0].read_bytes(), CLIENT_PATHS[1].read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
