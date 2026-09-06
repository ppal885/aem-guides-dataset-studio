#!/usr/bin/env python3
"""Read-only VM query smoke test, NOT a model-parity or import authorization.

Uses existing loopback MCP search/status and Chroma collection/get/count APIs.
No backend import, local Chroma open, ingestion, model reset or synthesis call.
Normal backend query handling may update caches/logs or initialize embeddings.
Prints an allowlisted report only; never prints source text, tokens or vectors.
See vm_search_embeddings_runbook.md for the proof boundaries and VM commands.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
import os


def _sibling(name):
    # Fixed reviewed stdlib modules, independent of cwd/PYTHONPATH under -I.
    if name not in {"vm_chroma_routing_checks", "test_verify_vm_search_embeddings"}:
        raise ValueError("UNKNOWN_DIAGNOSTIC_MODULE")
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


routing = _sibling("vm_chroma_routing_checks")
ProbeError = routing.RoutingCheckError
require = routing._require
COLLECTIONS = routing.COLLECTIONS
SCHEMA = "vm-search-embedding-diagnostic-v1"
MAX_BYTES = 2 * 1024 * 1024
SOCKET_TIMEOUT = 45
RUN_BUDGET_SECONDS = 360
TOP_K = 3
# The existing history service retrieves at most top_k * 3 candidates, then
# applies same-mechanism qualification. Rejected discovery is not a failed query.
MAX_HISTORY_CANDIDATES = TOP_K * 3
REJECTION_EVIDENCE_TYPES = frozenset({
    "area_or_semantic_overlap_only", "cross_surface_scroll_overlap_only",
})
PROBES = (
    ("table_editing", "Table editing: inserting and deleting table rows and columns changes the table structure."),
    ("map_title", "Map references display the topic title incorrectly after a referenced topic title is changed."),
    ("publishing", "Native PDF publishing fails when generating output using an output preset and template."),
)


def fingerprint(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def decode_json(raw):
    def finite_float(text):
        value = float(text)
        if not routing._finite_number(value):
            raise ValueError("NONFINITE_JSON_NUMBER")
        return value

    try:
        return json.loads(raw, parse_constant=routing._reject_constant,
                          parse_float=finite_float, object_pairs_hook=routing._unique_object)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ProbeError("INVALID_JSON_RESPONSE") from None


def request_spec(kind, selector=""):
    """An immutable operation allowlist, not an arbitrary URL/tool client."""
    if kind == "status" and selector == "":
        return "POST", "/mcp", routing._mcp_request()
    if kind == "history" and selector in dict(PROBES):
        return "POST", "/mcp", {
            "jsonrpc": "2.0", "id": "vm-search-" + selector, "method": "tools/call",
            "params": {"name": "search_jira_history", "arguments": {
                "query": dict(PROBES)[selector], "top_k": TOP_K}}}
    if kind == "collection" and selector in COLLECTIONS:
        return "GET", routing.CHROMA_PREFIX + selector, None
    if isinstance(selector, str) and re.fullmatch(routing.UUID, selector):
        if kind == "count":
            return "GET", routing.CHROMA_PREFIX + selector + "/count", None
        if kind == "vector_sample":
            return "POST", routing.CHROMA_PREFIX + selector + "/get", {
                "limit": 3, "include": ["embeddings"]}
    raise ProbeError("REQUEST_NOT_ALLOWLISTED")


def read_json(port, kind, selector="", *, token="", deadline=None):
    method, path, body = request_spec(kind, selector)
    backend_request = kind in {"status", "history"}
    require(type(port) is int and port in ({8001, 4502} if backend_request else {8000}),
            "PORT_NOT_ALLOWLISTED")
    require(isinstance(token, str) and len(token) <= 8192
            and re.search(r"[\x00-\x20\x7f]", token) is None, "INVALID_AUTH_TOKEN")
    require(not token or backend_request, "BACKEND_TOKEN_NOT_ALLOWED_FOR_CHROMA")
    remaining = SOCKET_TIMEOUT if deadline is None else min(SOCKET_TIMEOUT, deadline - time.monotonic())
    require(remaining > 0, "DIAGNOSTIC_BUDGET_EXHAUSTED")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
    connection = None
    try:
        # http.client uses neither proxy environment variables nor redirects.
        # Plain HTTP is restricted to the existing VM's numeric loopback only.
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=remaining)
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        if response.status in {401, 403}:
            raise ProbeError("AUTHENTICATION_OR_AUTHORIZATION_FAILED")
        require(response.status == 200, "HTTP_STATUS_NOT_OK")
        require(response.getheader("Content-Encoding", "identity") == "identity",
                "UNSUPPORTED_RESPONSE_ENCODING")
        content_type = response.getheader("Content-Type", "")
        require(isinstance(content_type, str), "JSON_CONTENT_TYPE_REQUIRED")
        content_type = content_type.split(";", 1)[0].strip().lower()
        require(content_type == "application/json", "JSON_CONTENT_TYPE_REQUIRED")
        length = response.getheader("Content-Length")
        if length is not None:
            require(isinstance(length, str) and re.fullmatch(r"[0-9]{1,10}", length),
                    "INVALID_RESPONSE_LENGTH")
            require(int(length) <= MAX_BYTES, "RESPONSE_TOO_LARGE")
        raw = response.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, "RESPONSE_TOO_LARGE")
        require(deadline is None or time.monotonic() < deadline, "DIAGNOSTIC_BUDGET_EXHAUSTED")
        return decode_json(raw)
    except TimeoutError:
        raise ProbeError("HTTP_TIMEOUT") from None
    except (OSError, ValueError, TypeError, http.client.HTTPException):
        raise ProbeError("HTTP_REQUEST_FAILED") from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass


def mcp_object(packet, request_id):
    require(isinstance(packet, dict) and packet.get("jsonrpc") == "2.0"
            and packet.get("id") == request_id and packet.get("error") is None,
            "INVALID_MCP_RESPONSE")
    result = packet.get("result")
    require(isinstance(result, dict) and result.get("isError", False) is False, "MCP_TOOL_ERROR")
    content = result.get("content")
    require(isinstance(content, list) and len(content) == 1, "AMBIGUOUS_MCP_CONTENT")
    item = content[0]
    require(isinstance(item, dict) and item.get("type") == "text"
            and isinstance(item.get("text"), str), "INVALID_MCP_CONTENT")
    value = decode_json(item["text"])
    require(isinstance(value, dict), "MCP_OBJECT_REQUIRED")
    require(value.get("error") is None, "BACKEND_REPORTED_ERROR")
    return value


def checked_status(packet):
    data = mcp_object(packet, routing._mcp_request()["id"])
    require(data.get("status") == "ok" and data.get("chroma_available") is True,
            "CHROMA_NOT_AVAILABLE")
    require(type(data.get("embedding_available")) is bool, "EMBEDDING_AVAILABILITY_NOT_REPORTED")
    identity = data.get("index_identity")
    require(isinstance(identity, dict) and isinstance(identity.get("collections"), dict),
            "RUNTIME_IDENTITY_UNAVAILABLE")
    expected = {}
    for name in COLLECTIONS:
        entry = identity["collections"].get(name)
        require(isinstance(entry, dict), "RUNTIME_COLLECTION_UNAVAILABLE")
        expected[name] = {"id": routing._uuid(entry.get("id"), "COLLECTION_UUID_UNAVAILABLE"),
                          "count": routing._count(entry.get("count"), "COLLECTION_COUNT_UNAVAILABLE")}
        require(isinstance(data.get("collections"), dict)
                and type(data["collections"].get(name)) is int
                and data["collections"][name] == expected[name]["count"], "MCP_COUNT_MISMATCH")
    require(len({row["id"] for row in expected.values()}) == len(COLLECTIONS),
            "DUPLICATE_COLLECTION_UUID")
    # Reuse the published guard for exact REMOTE loopback target + tenant/db.
    normalized = routing._checked_identity(identity, expected)
    return {"index_identity": normalized, "embedding_available_reported": data["embedding_available"]}


def vector_summary(data, expected_count):
    require(isinstance(data, dict), "VECTOR_SAMPLE_INVALID")
    ids, vectors = data.get("ids"), data.get("embeddings")
    require(isinstance(ids, list) and isinstance(vectors, list)
            and len(ids) == len(vectors) == min(3, expected_count)
            and all(routing._valid_record_id(item) for item in ids)
            and len(set(ids)) == len(ids), "VECTOR_SAMPLE_INVALID")
    require(all(routing._valid_vector(vector) for vector in vectors), "VECTOR_SAMPLE_INVALID")
    dimensions = {len(vector) for vector in vectors}
    require(len(dimensions) == 1, "STORED_SAMPLE_DIMENSIONS_CONFLICT")
    require(all(any(value != 0 for value in vector) for vector in vectors), "ZERO_STORED_VECTOR")
    return {"status": "FINITE_STORED_VECTOR_SAMPLE", "samples": len(ids),
            "dimension": next(iter(dimensions)), "current_query_dimension": None,
            "current_encoder_verified": False}


def search_summary(packet, probe_id, expected_count):
    query = dict(PROBES)[probe_id]
    data = mcp_object(packet, "vm-search-" + probe_id)
    require(data.get("schema_version") == "jira-history-search-v2", "SEARCH_SCHEMA_NOT_SUPPORTED")
    require(data.get("query_fingerprint") == fingerprint(query), "QUERY_FINGERPRINT_MISMATCH")
    require(type(data.get("searched_jira_qa")) is bool, "SEARCH_STATE_NOT_REPORTED")
    require(type(data.get("indexed_chunks")) is int and data["indexed_chunks"] == expected_count,
            "SEARCH_INDEX_COUNT_MISMATCH")
    require(data.get("component_filter") is None and data.get("customer_filter") is None,
            "UNEXPECTED_SEARCH_FILTER")
    results = data.get("results")
    count = data.get("match_count")
    require(type(count) is int and 0 <= count <= TOP_K
            and isinstance(results, list) and len(results) == count, "SEARCH_RESULTS_INVALID")
    rejected = data.get("rejected_candidate_count")
    require(type(rejected) is int and 0 <= rejected <= MAX_HISTORY_CANDIDATES
            and count + rejected <= MAX_HISTORY_CANDIDATES, "SEARCH_REJECTION_COUNT_INVALID")
    require(data["searched_jira_qa"] or count == rejected == 0, "SEARCH_STATE_CONTRADICTS_RESULTS")
    rows, keys = [], set()
    for result in results:
        require(isinstance(result, dict), "SEARCH_RESULT_INVALID")
        key = result.get("jira_key")
        require(isinstance(key, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}-[0-9]{1,16}", key),
                "SEARCH_RESULT_REFERENCE_INVALID")
        require(key not in keys, "DUPLICATE_SEARCH_RESULT")
        keys.add(key)
        text = result.get("document")
        require(isinstance(text, str) and 0 < len(text) <= 6000, "SEARCH_RESULT_DOCUMENT_INVALID")
        retrieval = result.get("retrieval")
        require(isinstance(retrieval, dict), "RETRIEVAL_EVIDENCE_NOT_REPORTED")
        scores = {}
        for field in ("vector_score", "keyword_score", "metadata_score", "final_score"):
            value = retrieval.get(field)
            require(routing._finite_number(value) and 0 <= value <= 1, "RETRIEVAL_SCORE_INVALID")
            scores[field] = value
        rows.append({"reference_sha256": fingerprint(key), "document_sha256": fingerprint(text),
                     "document_chars": len(text), "scores": scores})
    rejected_items = data.get("rejected_candidates", [] if rejected == 0 else None)
    require(isinstance(rejected_items, list) and len(rejected_items) == rejected,
            "SEARCH_REJECTION_DETAILS_INVALID")
    rejected_rows = []
    for item in rejected_items:
        require(isinstance(item, dict), "SEARCH_REJECTION_DETAILS_INVALID")
        key = item.get("jira_key")
        require(isinstance(key, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}-[0-9]{1,16}", key),
                "SEARCH_REJECTION_REFERENCE_INVALID")
        require(key not in keys, "DUPLICATE_OR_CONFLICTING_SEARCH_REJECTION")
        keys.add(key)
        match = item.get("historical_match")
        require(isinstance(match, dict) and match.get("schema_version") == "jira-history-match-v2"
                and match.get("qualified") is False and match.get("strength") == "unproven",
                "SEARCH_REJECTION_MATCH_INVALID")
        score, types = match.get("mechanism_score"), match.get("evidence_types")
        require(routing._finite_number(score) and 0 <= score <= 1,
                "SEARCH_REJECTION_SCORE_INVALID")
        require(isinstance(types, list) and 1 <= len(types) <= len(REJECTION_EVIDENCE_TYPES)
                and all(isinstance(value, str) and value in REJECTION_EVIDENCE_TYPES for value in types)
                and len(set(types)) == len(types), "SEARCH_REJECTION_TYPES_INVALID")
        # Do not serialize reasons, summaries, source text or technical identifiers.
        rejected_rows.append({"reference_sha256": fingerprint(key), "historical_match": {
            "qualified": False, "strength": "unproven", "mechanism_score": score,
            "evidence_types": list(types)}})
    status = "RETURNED_RESULTS" if count else "INCONCLUSIVE_EMPTY_RESULTS"
    if count == 0 and rejected_rows:
        status = "CANDIDATES_REJECTED_BY_POLICY"
    if not data["searched_jira_qa"]:
        status = "RETRIEVAL_UNAVAILABLE"
    return {"status": status, "query_sha256": fingerprint(query), "indexed_chunks": expected_count,
            "searched_jira_qa_reported": data["searched_jira_qa"], "result_count": count,
            "rejected_candidate_count": rejected, "results": rows, "rejected_candidates": rejected_rows,
            "qualified_history_match_returned": count > 0,
            "fresh_embedding_verified": False, "semantic_relevance_human_verified": False}


def run_diagnostic(*, token="", reader=read_json):
    started = time.monotonic()
    deadline = started + RUN_BUDGET_SECONDS
    report = {
        "schema_version": SCHEMA, "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_QUERY_SMOKE", "status": "BLOCKED", "phase": "BEFORE_ROUTING",
        "scope": {"text_search": "JIRA_HISTORY_MCP_ONLY", "stored_vector_samples": list(COLLECTIONS),
                  "aem_guides_and_dita_text_search_tested": False,
                  "legacy_rest_bridge_and_external_client_setup_tested": False},
        "actions": {"index_write_requests": False, "backend_module_import": False,
                    "local_chroma_open": False, "model_reset": False, "synthesis_request": False,
                    "service_restart": False, "config_change": False, "report_file_write": False},
        "backend_query_side_effects": "NORMAL_CACHE_LOGGING_AND_LAZY_EMBEDDING_EFFECTS_POSSIBLE",
        "queries": [], "stored_vector_samples": {},
        "embedding_verification": {
            "active_encoder_identity": "NOT_EXPOSED_BY_EXISTING_READ_CONTRACT",
            "query_vector_readback": "NOT_EXPOSED_BY_EXISTING_READ_CONTRACT",
            "stored_document_reencoding": "NOT_PERFORMED",
            "model_parity_proven": False, "fresh_embedding_verified": False},
        "full_live_payload_equality_verified": False, "ranking_parity_proven": False,
        "qualified_history_search_smoke_passed": False,
        "team_client_authentication_verified": False, "import_authorized": False,
        "resume_writers_authorized": False,
    }

    def read(port, kind, selector=""):
        require(time.monotonic() < deadline, "DIAGNOSTIC_BUDGET_EXHAUSTED")
        return reader(port, kind, selector, token=token if port != 8000 else "", deadline=deadline)

    def statuses():
        values = {}
        for name, port in (("backend_8001", 8001), ("gateway_4502", 4502)):
            report["endpoint"] = name
            values[name] = checked_status(read(port, "status"))
        require(values["backend_8001"]["index_identity"] == values["gateway_4502"]["index_identity"],
                "BACKEND_GATEWAY_ROUTING_MISMATCH")
        return values

    def direct_inventory(expected):
        for name in COLLECTIONS:
            report["endpoint"] = "chroma_8000_" + name
            row = read(8000, "collection", name)
            require(isinstance(row, dict) and row.get("name") == name
                    and routing._uuid(row.get("id"), "DIRECT_UUID_INVALID") == expected[name]["id"],
                    "DIRECT_COLLECTION_MISMATCH")
            count = read(8000, "count", expected[name]["id"])
            require(type(count) is int and count == expected[name]["count"], "DIRECT_COUNT_MISMATCH")

    try:
        before = report["routing_before"] = statuses()
        expected = before["backend_8001"]["index_identity"]["collections"]
        report["phase"] = "DIRECT_INVENTORY_AND_SAMPLES"
        direct_inventory(expected)
        for name in COLLECTIONS:
            report["endpoint"] = "chroma_8000_" + name
            count = expected[name]["count"]
            if count:
                report["stored_vector_samples"][name] = vector_summary(
                    read(8000, "vector_sample", expected[name]["id"]), count)
            else:
                report["stored_vector_samples"][name] = {"status": "EMPTY_COLLECTION", "samples": 0}
        report["phase"] = "TEXT_SEARCH"
        for probe_id, _query in PROBES:
            item = {"probe_id": probe_id, "routes": {}}
            report["queries"].append(item)
            for name, port in (("backend_8001", 8001), ("gateway_4502", 4502)):
                report["endpoint"] = name
                item["routes"][name] = search_summary(
                    read(port, "history", probe_id), probe_id, expected["jira_qa"]["count"])
            first, second = (item["routes"][name] for name in ("backend_8001", "gateway_4502"))
            item["returned_reference_overlap_count"] = len(
                {row["reference_sha256"] for row in first["results"]}
                & {row["reference_sha256"] for row in second["results"]})
            item["ranking_comparison"] = "INFORMATIONAL_ONLY_RUNTIME_HAS_RECENCY_AND_EMBEDDING_CACHES"
        report["phase"] = "AFTER_ROUTING"
        after = report["routing_after"] = statuses()
        for name in before:
            require(before[name]["index_identity"] == after[name]["index_identity"], "INDEX_CHANGED_DURING_PROBE")
        direct_inventory(expected)
        report["routing_identity_and_counts_stable"] = True
        all_hits = all(route["status"] == "RETURNED_RESULTS"
                       for query in report["queries"] for route in query["routes"].values())
        all_query_evidence = all(route["status"] in {"RETURNED_RESULTS", "CANDIDATES_REJECTED_BY_POLICY"}
                                 for query in report["queries"] for route in query["routes"].values())
        all_available = all(row["embedding_available_reported"] for snapshot in (before, after)
                            for row in snapshot.values())
        report["qualified_history_search_smoke_passed"] = all_hits and all_available
        if all_hits and all_available:
            report["status"] = "PASS_QUERY_SMOKE_ONLY"
        elif all_query_evidence and all_available:
            report["status"] = "PASS_FILTERED_QUERY_SMOKE_ONLY"
        else:
            report["status"] = "PARTIAL_QUERY_SMOKE"
        report["phase"] = "COMPLETE"
        report.pop("endpoint", None)
    except ProbeError as exc:
        report["reason"] = exc.code
    except Exception:
        report["reason"] = "UNEXPECTED_DIAGNOSTIC_FAILURE"
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["next_step"] = "Share this redacted report. No import, merge or writer resume is authorized."
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Mocked tests; no VM/network required")
    args = parser.parse_args(argv)
    if args.self_test:
        return _sibling("test_verify_vm_search_embeddings").run_self_tests()
    if sys.platform != "linux":
        print("STOP: RUN_ON_VM_LINUX_LOOPBACK_REQUIRED", file=sys.stderr)
        return 1
    result = run_diagnostic(token=os.environ.get("AEM_STUDIO_TOKEN", ""))
    print(json.dumps(result, indent=2, allow_nan=False))
    return {"PASS_QUERY_SMOKE_ONLY": 0, "PASS_FILTERED_QUERY_SMOKE_ONLY": 0,
            "PARTIAL_QUERY_SMOKE": 2}.get(result["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
