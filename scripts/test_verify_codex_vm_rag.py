"""Offline checks for fresh-stdio routing proof; no MCP process or network."""
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from scripts import verify_codex_vm_rag as probe


class ProofTests(unittest.TestCase):
    def test_profile_selects_thin_read_only_client(self):
        fixture = {"mcp_servers": {"aem_dataset_studio": {
            "args": [str(probe.ROOT / "release-artifacts/aem-guides-mcp-client-windows/server.py")],
            "command": "fixture-python", "enabled_tools": sorted(probe.READ_TOOLS),
            "env": {"AEM_STUDIO_READ_ONLY": "true", "AEM_STUDIO_TOKEN": "",
                    "AEM_STUDIO_EXPECTED_INDEX_FINGERPRINT": "a" * 64}}}}
        with mock.patch.object(probe.tomllib, "loads", return_value=fixture), \
                mock.patch.object(probe.Path, "read_text", return_value=""), \
                mock.patch.object(probe.Path, "is_file", return_value=True):
            profile = probe.load_profile()
        self.assertIn("mcp-client-windows", profile["args"][0])
        self.assertEqual(profile["env"]["AEM_STUDIO_TOKEN"], "")

    def test_non_json_and_mcp_errors_do_not_pass(self):
        with self.assertRaises(ValueError):
            probe.unpack(SimpleNamespace(isError=True, content=[]))
        with self.assertRaises(ValueError):
            probe.unpack(SimpleNamespace(isError=False, content=[SimpleNamespace(type="text", text="ERROR")]))

    def test_status_requires_remote_identity(self):
        value = {"index_identity": {"status": "OK", "mode": "EMBEDDED", "target_fingerprint": "a" * 64}}
        with self.assertRaisesRegex(ValueError, "VM_IDENTITY_MISMATCH"):
            probe.identity(value, "a" * 64)

    def test_empty_variables_result_is_a_gap_not_fabricated_hit(self):
        summary = probe.evidence_summary({"aem_guides_evidence": {"results": []}}, probe.VARIABLES_URL)
        self.assertFalse(summary["exact_source_returned"])
        self.assertEqual(summary["result_count"], 0)

    def test_language_variables_is_not_variables(self):
        packet = {"aem_guides_evidence": {"results": [{"source": probe.LANGUAGE_URL, "text": "Variables"}]}}
        self.assertFalse(probe.evidence_summary(packet, probe.VARIABLES_URL)["exact_source_returned"])

    def test_exact_source_with_anchor_is_detected(self):
        packet = {"aem_guides_evidence": {"results": [{"source": probe.VARIABLES_URL + "#example"}]}}
        self.assertTrue(probe.evidence_summary(packet, probe.VARIABLES_URL)["exact_source_returned"])

    def test_failed_lookup_is_not_empty_success(self):
        with self.assertRaisesRegex(ValueError, "PRODUCT_LOOKUP_FAILED"):
            probe.evidence_summary({"aem_guides_evidence": {"error": "unavailable"}}, probe.VARIABLES_URL)

    def test_error_json_is_not_a_successful_tool_payload(self):
        with self.assertRaisesRegex(ValueError, "INVALID_TOOL_PAYLOAD"):
            probe.unpack(SimpleNamespace(isError=False, content=[SimpleNamespace(
                type="text", text=json.dumps({"error": "VM unavailable"}))]))


if __name__ == "__main__":
    unittest.main()
