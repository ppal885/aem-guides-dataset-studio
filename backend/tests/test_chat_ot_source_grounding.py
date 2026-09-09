"""Offline boundary regressions; no app startup, database, model, or provider calls.

Load the actual source-gate, candidate conversion and orchestration definitions by AST.
Importing the application test conftest starts migrations against configured storage;
these tests deliberately avoid that and fake only external calls and pack scoring.
Run: python -B backend/tests/test_chat_ot_source_grounding.py
"""
import ast
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import re
import runpy
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
import unittest
from urllib.parse import urlsplit


SOURCE = Path(__file__).resolve().parents[1] / "app/services/chat_service.py"
DEFINITIONS = {
    "_GroundingCandidate", "_OT_SOURCE_DOMAIN_RE", "_OT_OFFICIAL_LABEL_RE",
    "_OT_OFFICIAL_URL_RE", "_is_official_ot_url", "_apply_docs_source_domain_gate",
    "_tool_result_summary", "_extract_attribute_syntax_line",
    "_has_strong_direct_dita_tool_evidence", "_append_grounding_candidate",
    "_tool_result_to_grounding_candidates", "_build_grounded_tool_evidence_pack",
}


def load_boundary():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    body = []
    for node in tree.body:
        names = {getattr(node, "name", "")}
        if isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        if names & DEFINITIONS:
            body.append(node)
    namespace = dict(globals())
    namespace.update({k: v for k, v in runpy.run_path(str(SOURCE.with_name("dita_evidence_routing.py"))).items()
                      if not k.startswith("__")})
    exec(compile(ast.Module(body=body, type_ignores=[]), str(SOURCE), "exec",
                 dont_inherit=True), namespace)
    return namespace


def doc_result(url, title="DITA-OT processing", text="Retrieved documentation."):
    return {"query": title, "summary": text,
            "results": [{"url": url, "title": title, "snippet": text}], "count": 1}


def spec_result():
    return {
        "status": "success", "query_type": "element", "element_name": "xref",
        "content_model_summary": "Cross references can contain display text.",
        "source_url": "https://docs.oasis-open.org/dita/xref.html",
        "sources": ["DITA specification"],
    }


def load_real_scoring():
    """Use unchanged scoring/dedup with only its logging and unused LLM imports stubbed."""
    path = SOURCE.with_name("grounding_service.py")
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app."))]
    module = ModuleType("_offline_ot_grounding_scoring")
    module.__dict__["get_structured_logger"] = lambda name: SimpleNamespace()
    sys.modules[module.__name__] = module
    try:
        exec(compile(tree, str(path), "exec"), module.__dict__)
    finally:
        sys.modules.pop(module.__name__, None)
    return module.build_evidence_pack


class OtSourceGroundingTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_boundary()
        self.calls = []

    def candidate(self, url="", source="aem_guides", label="DITA-OT base parameters: args.draft"):
        return self.ns["_GroundingCandidate"](
            source=source, label=label, text="Retrieved documentation.", url=url)

    def gate(self, candidates, query="DITA-OT PDF2 cross-reference processing"):
        return self.ns["_apply_docs_source_domain_gate"](query, candidates)

    def run_pack(self, initial=None, retry=None, query="DITA-OT PDF2 cross-reference processing",
                 status="abstain", session="", expanded=None, real_scoring=False):
        if initial is None:
            initial = [("lookup_dita_spec", spec_result())]
        queued = {name: result for name, result in initial}
        self.ns["_grounded_tool_requests"] = lambda *args: [(n, {}) for n, _ in initial]
        self.ns["_expand_follow_up_retrieval_query"] = lambda *args: expanded or query

        async def run_tool(name, params, **kwargs):
            self.calls.append((name, params, kwargs))
            if name in queued:
                return queued.pop(name)
            return retry or {"results": [], "count": 0}

        def build_pack(**kwargs):
            candidates = kwargs["candidates"]
            self.scored_candidates = list(candidates)
            self.scored_query = kwargs["query"]
            return SimpleNamespace(
                chunks=[SimpleNamespace(uri=c.url, content=c.text) for c in candidates],
                decision=SimpleNamespace(status=status, confidence=0.42, thin_evidence=True,
                                         source_kinds=[], reason="Original score",
                                         has_conflict=status == "conflict"))

        self.ns["run_tool"] = run_tool
        self.ns["build_evidence_pack"] = load_real_scoring() if real_scoring else build_pack
        return asyncio.run(self.ns["_build_grounded_tool_evidence_pack"](
            answer_mode="grounded_dita_answer", user_content=query,
            tenant_id="test-tenant", user_id="test-user", session_id=session))

    def test_label_and_query_are_not_source_authority(self):
        _, debug = self.gate([self.candidate()])
        self.assertFalse(debug["official_evidence_found"])

    def test_url_host_must_really_be_official(self):
        for url in ("https://dita-ot.org.example.com/docs", "https://example.com/dita-ot.org",
                    "https://dita-ot.org@example.com/docs", "file://dita-ot.org/docs",
                    "https://example.com/?source=dita-ot.org", "https://[invalid"):
            with self.subTest(url=url):
                _, debug = self.gate([self.candidate(url)])
                self.assertFalse(debug["official_evidence_found"])

    def test_official_document_url_is_recognized(self):
        for url in ("https://www.dita-ot.org/dev/reference/preprocess-topicpull",
                    "https://dita-ot.org/4.3/parameters/parameters-base"):
            _, debug = self.gate([self.candidate(url)])
            self.assertTrue(debug["official_evidence_found"])

    def test_spec_with_parameter_in_label_is_still_not_ot_evidence(self):
        selected, debug = self.gate([self.candidate(source="dita_spec")])
        self.assertEqual(selected, [])
        self.assertTrue(debug["rejected_candidates"])

    def test_general_dita_query_keeps_spec(self):
        spec = self.candidate(source="dita_spec")
        selected, _ = self.gate([spec], query="What is an xref?")
        self.assertEqual(selected, [spec])

    def test_retry_with_aem_only_evidence_is_not_official(self):
        aem = doc_result("https://experienceleague.adobe.com/en/docs/experience-manager-guides",
                         "DITA-OT base parameters: args.draft")
        pack, meta, _ = self.run_pack(
            initial=[("lookup_dita_spec", spec_result()), ("lookup_aem_guides", aem)],
            retry=aem, status="grounded")
        self.assertNotEqual(pack.decision.status, "grounded")
        self.assertFalse(meta["official_docs_retry"])
        self.assertFalse(meta["retrieval_debug"]["official_evidence_found"])
        self.assertTrue(meta["retrieval_debug"]["official_docs_retry_attempted"])
        self.assertTrue(meta["retrieval_debug"]["rejected_candidates"])

    def test_spec_only_requests_still_attempt_document_retrieval(self):
        _, meta, _ = self.run_pack()
        self.assertEqual([call[0] for call in self.calls], ["lookup_dita_spec", "lookup_aem_guides"])
        self.assertFalse(meta["official_docs_retry"])
        self.assertEqual(self.scored_candidates, [])

    def test_empty_initial_retrieval_still_attempts_ot_docs(self):
        pack, _, _ = self.run_pack(initial=[("lookup_dita_spec", {})])
        self.assertIsNotNone(pack)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(pack.decision.status, "abstain")

    def test_empty_versioned_spec_retains_honest_retrieval_receipt(self):
        trace = {"indexed_query_executed": False, "indexed_status": "EMPTY_COLLECTION",
                 "mode": "SEED_LEXICAL_FALLBACK", "result_count": 0}
        pack, meta, _ = self.run_pack(
            initial=[("lookup_dita_spec", {"spec_chunks": [], "sources": [], "retrieval": trace})],
            query="DITA 1.3 specification for <xref>")
        self.assertIsNotNone(pack)
        self.assertEqual(pack.decision.status, "abstain")
        self.assertEqual(meta["retrieval_debug"]["dita_spec_retrieval"], trace)

    def test_retry_does_not_force_processing_question_into_cli_parameters(self):
        self.run_pack()
        retry_query = self.calls[-1][1]["query"]
        self.assertIn("cross-reference processing", retry_query)
        self.assertNotIn("command-line parameter", retry_query)

    def test_official_retry_does_not_override_scoring_or_conflict(self):
        for status in ("abstain", "partial", "conflict", "grounded"):
            with self.subTest(status=status):
                pack, meta, _ = self.run_pack(
                    retry=doc_result("https://www.dita-ot.org/dev/reference/preprocess-topicpull"),
                    status=status)
                self.assertEqual(pack.decision.status, status)
                self.assertEqual(pack.decision.confidence, 0.42)
                self.assertTrue(meta["official_docs_retry"])

    def test_followup_uses_engine_context_for_gate_and_retry(self):
        self.run_pack(query="What about display text?", session="test-session",
                      expanded="DITA-OT PDF2: What about display text?")
        self.assertEqual(len(self.calls), 2)
        self.assertIn("PDF2", self.calls[-1][1]["query"])
        self.assertIn("PDF2", self.scored_query)

    def test_general_spec_direct_evidence_promotion_is_unchanged(self):
        pack, _, _ = self.run_pack(query="What is an xref?")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(pack.decision.status, "grounded")

    def test_existing_official_document_needs_no_retry(self):
        pack, meta, _ = self.run_pack(initial=[("lookup_aem_guides", doc_result(
            "https://www.dita-ot.org/dev/reference/preprocess-topicpull"))])
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(meta["official_docs_retry"])
        self.assertEqual(pack.decision.status, "abstain")

    def test_real_scoring_keeps_official_citation_without_forced_promotion(self):
        url = "https://www.dita-ot.org/dev/reference/preprocess-topicpull"
        pack, meta, _ = self.run_pack(retry=doc_result(
            url, text="Cross-reference processing retrieves the title when link text is empty."),
            real_scoring=True)
        self.assertTrue(meta["official_docs_retry"])
        self.assertTrue(meta["retrieval_debug"]["official_evidence_in_pack"])
        self.assertIn(url, [c.uri for c in pack.citations()])
        self.assertNotEqual(pack.decision.confidence, 0.88)
        self.assertNotEqual(pack.decision.status, "grounded")

    def test_real_scoring_abstains_when_only_rejected_spec_is_available(self):
        pack, meta, _ = self.run_pack(real_scoring=True)
        self.assertEqual(pack.chunks, [])
        self.assertEqual(pack.decision.status, "abstain")
        self.assertEqual(pack.decision.confidence, 0)
        self.assertTrue(meta["retrieval_debug"]["rejected_candidates"])

    def test_provider_error_does_not_become_evidence(self):
        pack, meta, _ = self.run_pack(retry={"error": "unavailable"}, real_scoring=True)
        self.assertEqual(pack.chunks, [])
        self.assertFalse(meta["official_docs_retry"])
        self.assertNotIn("unavailable", str(meta))

    def test_official_source_lost_during_dedup_cannot_claim_complete_grounding(self):
        text = "DITA-OT PDF2 cross-reference processing retrieves titles when display text is empty."
        initial = doc_result("https://experienceleague.adobe.com/en/docs/experience-manager-guides", text=text)
        retry = doc_result("https://www.dita-ot.org/dev/reference/preprocess-topicpull", text=text)
        pack, meta, _ = self.run_pack(initial=[("lookup_aem_guides", initial)],
                                     retry=retry, real_scoring=True)
        self.assertTrue(meta["retrieval_debug"]["official_evidence_found"])
        self.assertFalse(meta["retrieval_debug"]["official_evidence_in_pack"])
        self.assertNotEqual(pack.decision.status, "grounded")

    def test_retrieved_spec_semantics_survive_but_cannot_prove_ot_behavior(self):
        result = {"sources": [{"url": "https://docs.oasis-open.org/dita/spec.pdf#page=42",
                               "label": "Cross references", "snippet": "DITA semantic evidence.",
                               "evidence_role": "DITA_SEMANTICS_ONLY"}],
                  "retrieval": {"indexed_query_executed": True, "mode": "CHROMA_HYBRID"}}
        pack, meta, _ = self.run_pack(initial=[("lookup_dita_spec", result)], status="grounded")
        self.assertEqual(len(pack.chunks), 1)
        self.assertEqual(pack.decision.status, "partial")
        self.assertTrue(meta["retrieval_debug"]["dita_spec_retrieval"]["indexed_query_executed"])
        self.assertFalse(meta["retrieval_debug"]["official_evidence_in_pack"])

    def test_pdf_two_spaced_name_still_requires_ot_docs(self):
        self.run_pack(query="How does PDF 2 render xref display text?")
        self.assertEqual(len(self.calls), 2)

    def test_versioned_spec_request_does_not_force_registry_confidence(self):
        pack, _, _ = self.run_pack(query="DITA 1.3 specification for <xref>")
        self.assertEqual(pack.decision.status, "abstain")
        self.assertEqual(pack.decision.confidence, 0.42)


if __name__ == "__main__":
    unittest.main()
