"""Offline routing regression tests; no application startup or corpus writes.

Run: python -B backend/tests/test_dita_rag_routing.py
Definitions are read from the actual modules; only provider/registry boundaries
are faked. This avoids the application conftest's configured-storage migrations.
"""
import ast
import asyncio
from pathlib import Path
import re
import runpy
from types import SimpleNamespace
from typing import Any, Optional
import unittest

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "backend/app/services"
POLICY = runpy.run_path(str(SERVICES / "dita_evidence_routing.py"))


def load(path, names, context=None):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    nodes = []
    for node in tree.body:
        found = {getattr(node, "name", "")}
        if isinstance(node, ast.Assign):
            found.update(t.id for t in node.targets if isinstance(t, ast.Name))
        if found & names:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node.decorator_list = []
                # Inject the real dependency boundaries explicitly, without importing app.
                node.body = [n for n in node.body if not isinstance(n, ast.ImportFrom)]
            nodes.append(node)
    ns = dict(globals())
    ns.update({k: v for k, v in POLICY.items() if not k.startswith("__")})
    ns.update(context or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
    return ns


class DitaRagRoutingTests(unittest.TestCase):
    def test_processing_questions_are_not_registry_only(self):
        ns = load(ROOT / "mcp_server.py", {
            "_DITA_PRODUCT_EVIDENCE_QUESTION", "_should_use_dita_construct_fast_path",
            "_is_explicit_dita_construct_reference"})
        for q in ("What does <xref> do in DITA-OT PDF2?",
                  "What does <xref> do according to the DITA 1.3 PDF specification?"):
            with self.subTest(q=q):
                self.assertFalse(ns["_should_use_dita_construct_fast_path"](q, ["xref"]))
        self.assertTrue(ns["_should_use_dita_construct_fast_path"]("What is <xref>?", ["xref"]))

    def test_policy_keeps_native_pdf_separate_from_pdf2(self):
        q = "Why does Native PDF render <xref> with footnote text?"
        self.assertTrue(POLICY["requires_indexed_dita_evidence"](q))
        self.assertFalse(POLICY["requires_dita_ot_documentation"](q))
        self.assertTrue(POLICY["requires_dita_ot_documentation"](q + " with DITA-OT processing?"))
        self.assertFalse(POLICY["requires_indexed_dita_evidence"]("How to save a Native PDF preset?"))

    def run_lookup(self, query, *, attribute=False, retrieved=None):
        self.lookups = []
        self.registry_calls = []
        rows = retrieved if retrieved is not None else [{
            "element_name": "dita_spec", "text_content": "Spec evidence from the indexed PDF.",
            "source_url": "https://docs.oasis-open.org/dita/spec.pdf#page=42"}]

        def retrieve(q, k, **kwargs):
            self.lookups.append(q)
            if kwargs.get("diagnostics") is not None:
                kwargs["diagnostics"].update(indexed_query_executed=True, mode="CHROMA", status="RESULTS")
            return rows

        async def attr(name):
            self.registry_calls.append(name)
            return {"attribute_name": name, "text_content": "Registry definition."}

        def element(*args):
            self.registry_calls.append("element")
            return {"element_name": "xref", "query_type": "element", "text_content": "Registry definition."}

        ns = load(SERVICES / "chat_tools.py", {"execute_lookup_dita_spec"}, {
            "retrieve_dita_knowledge": retrieve, "retrieve_dita_graph_knowledge": lambda **kw: "",
            "_extract_dita_elements_from_query": lambda *a, **kw: ["xref"],
            "_extract_dita_attributes_from_query": lambda q: ["format"] if attribute else [],
            "execute_lookup_dita_attribute": attr, "_build_dita_element_guidance": element,
            "_first_sentence": lambda text: text,
            "logger": SimpleNamespace(warning_structured=lambda *a, **kw: None),
        })
        return asyncio.run(ns["execute_lookup_dita_spec"](query))

    def test_element_processing_query_reads_indexed_spec(self):
        result = self.run_lookup("Why does Native PDF render <xref> with footnote text?")
        self.assertEqual(len(self.lookups), 1)
        self.assertEqual(self.registry_calls, [])
        self.assertIn("spec.pdf#page=42", result["sources"][0]["url"])
        self.assertTrue(result["retrieval"]["indexed_query_executed"])

    def test_attribute_processing_query_reads_indexed_spec(self):
        self.run_lookup("How does @format affect DITA-OT PDF2 processing?", attribute=True)
        self.assertEqual(len(self.lookups), 1)
        self.assertEqual(self.registry_calls, [])

    def test_empty_processing_retrieval_does_not_restore_registry_as_answer(self):
        result = self.run_lookup("DITA 1.3 specification for <xref>", retrieved=[])
        self.assertEqual(len(self.lookups), 1)
        self.assertEqual(result["spec_chunks"], [])
        self.assertEqual(result["sources"], [])

    def test_simple_definition_keeps_registry_fast_path(self):
        result = self.run_lookup("What is <xref>?")
        self.assertEqual(self.lookups, [])
        self.assertEqual(result["query_type"], "element")

    def test_native_pdf_does_not_blanket_suppress_semantic_rag(self):
        ns = load(SERVICES / "chat_service.py", {
            "_should_include_structural_dita_rag", "_DITA_OT_ERROR_PATTERN",
            "_DITA_RELATED_LINKS_TOC_QUERY_PATTERN", "_DITA_STRUCTURAL_QUERY_PATTERN",
            "_AEM_UI_CONFIGURATION_QUERY_PATTERN"}, {"_is_dita_construct_output_query": lambda q: "<xref>" in q})
        self.assertTrue(ns["_should_include_structural_dita_rag"](
            "Why does Native PDF render <xref> with footnote text?"))
        self.assertTrue(ns["_should_include_structural_dita_rag"](
            "How DITA OT Arguments affect draft comment in Native PDF"))
        self.assertFalse(ns["_should_include_structural_dita_rag"]("How to save a Native PDF preset?"))

    def test_product_answer_schedules_spec_before_llm_synthesis(self):
        tree = ast.parse((SERVICES / "chat_service.py").read_text(encoding="utf-8-sig"))
        patterns = {n.targets[0].id for n in tree.body if isinstance(n, ast.Assign)
                    and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Call)
                    and isinstance(n.value.func, ast.Attribute) and isinstance(n.value.func.value, ast.Name)
                    and n.value.func.value.id == "re" and n.value.func.attr == "compile"}
        ns = load(SERVICES / "chat_service.py", patterns | {"_grounded_tool_requests"}, {
            "_should_include_tenant_knowledge_for_aem_query": lambda q: False})
        requests = ns["_grounded_tool_requests"](
            "grounded_aem_answer", "Why does Native PDF render <xref> with footnote text?")
        self.assertIn("lookup_dita_spec", [name for name, _ in requests])
        ui_requests = ns["_grounded_tool_requests"]("grounded_aem_answer", "How to save a Native PDF preset?")
        self.assertNotIn("lookup_dita_spec", [name for name, _ in ui_requests])

    def retriever(self, *, available=True, rows=None):
        self.vector_calls = []

        def query(collection, **kwargs):
            self.vector_calls.append((collection, kwargs))
            return rows if rows is not None else [{
                "id": "spec-fixture", "document": "Specification excerpt.",
                "metadata": {"source_url": "https://docs.oasis-open.org/dita/spec.pdf", "page": "42"}}]

        return load(SERVICES / "dita_knowledge_retriever.py", {
            "_retrieve_dita_chromadb", "retrieve_dita_knowledge"}, {
            "is_chroma_available": lambda: available,
            "is_embedding_available": lambda: True,
            "get_collection_count": lambda c: 1,
            "embed_query": lambda q: [0.1, 0.2], "query_collection": query,
            "CHROMA_COLLECTION_DITA_SPEC": "dita_spec", "DITA_KNOWLEDGE_RETRIEVAL_K": 5,
            "USE_DITA_HYBRID_SEARCH": False, "_search_seed": lambda q, k: [],
            "_retrieve_dita_embedding": lambda q, k: [],
            "logger": SimpleNamespace(info_structured=lambda *a, **kw: None,
                                      warning_structured=lambda *a, **kw: None),
        })

    def test_indexed_pdf_query_and_source_are_recorded(self):
        ns = self.retriever()
        trace = {}
        rows = ns["retrieve_dita_knowledge"]("xref processing", k=3, diagnostics=trace)
        self.assertEqual(len(self.vector_calls), 1)
        self.assertEqual(self.vector_calls[0][0], "dita_spec")
        self.assertTrue(trace["indexed_query_executed"])
        self.assertEqual(trace["mode"], "CHROMA_HYBRID")
        self.assertEqual(rows[0]["chunk_id"], "spec-fixture")
        self.assertIn("#page=42", rows[0]["source_url"])

    def test_unavailable_index_is_not_reported_as_an_indexed_query(self):
        ns = self.retriever(available=False)
        trace = {}
        ns["retrieve_dita_knowledge"]("xref processing", diagnostics=trace)
        self.assertEqual(self.vector_calls, [])
        self.assertFalse(trace["indexed_query_executed"])
        self.assertEqual(trace["indexed_status"], "CHROMA_UNAVAILABLE")
        self.assertEqual(trace["mode"], "EMBEDDING_FALLBACK")

    def test_missing_source_url_is_not_fabricated_as_dita_12_pdf(self):
        ns = self.retriever(rows=[{"document": "Unknown-provenance excerpt", "metadata": {}}])
        rows = ns["retrieve_dita_knowledge"]("xref processing", diagnostics={})
        self.assertEqual(rows[0]["source_url"], "")

    def test_empty_index_result_is_reported_separately_from_fallback(self):
        ns = self.retriever(rows=[])
        trace = {}
        ns["retrieve_dita_knowledge"]("xref processing", diagnostics=trace)
        self.assertTrue(trace["indexed_query_executed"])
        self.assertEqual(trace["indexed_status"], "EMPTY_RESULT")
        self.assertEqual(trace["result_count"], 0)

    def test_old_retrieval_signature_is_still_usable(self):
        ns = self.retriever()
        rows = ns["retrieve_dita_knowledge"]("xref processing", 3)
        self.assertEqual(len(rows), 1)

    def test_receipt_distinguishes_fallback_from_indexed_evidence(self):
        lines = POLICY["dita_retrieval_receipt"]({"source_domain": "dita_ot", "retrieval_debug": {
            "dita_spec_retrieval": {"indexed_query_executed": False,
                                    "mode": "SEED_LEXICAL_FALLBACK", "result_count": 2},
            "official_evidence_in_pack": False}})
        self.assertIn("indexed query=no", lines[0])
        self.assertIn("SEED_LEXICAL_FALLBACK", lines[0])
        self.assertIn("retained in evidence=no", lines[1])
        self.assertEqual(POLICY["dita_retrieval_receipt"]({}), [])

    def test_local_mcp_and_http_mcp_disable_ad_hoc_tool_routing(self):
        for path, name in ((ROOT / "mcp_server.py", "ask_dita_expert"),
                           (ROOT / "backend/app/api/routes/remote_mcp.py", "_ask_dita_expert")):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            fn = next(n for n in tree.body if getattr(n, "name", "") == name)
            calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == "chat_turn"]
            self.assertEqual(len(calls), 1)
            self.assertTrue(any(k.arg == "allow_tool_routing" and isinstance(k.value, ast.Constant)
                                and k.value.value is False for k in calls[0].keywords))


if __name__ == "__main__":
    unittest.main()
