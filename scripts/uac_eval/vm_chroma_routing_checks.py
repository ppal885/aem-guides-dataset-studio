"""Bounded, read-only HTTP checks for the VM Chroma routing cutover.

Importing this stdlib-only module performs no I/O and loads no backend modules.
Successful checks establish routing, collection UUIDs and counts only. They do
not establish equality of documents, metadata or vectors. All public failures
contain fixed reason codes; reports copy only validated identity fields.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import math
import re


MAX_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 8
COLLECTIONS = ("jira_qa", "aem_guides", "dita_spec")
TENANT = "default_tenant"
DATABASE = "default_database"
CHROMA_COLLECTIONS = "/api/v2/tenants/default_tenant/databases/default_database/collections"
CHROMA_PREFIX = CHROMA_COLLECTIONS + "/"
UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
NAME = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
IDENTITY_SCHEMA = "chroma-index-identity-v1"


def _mcp_request():
    # Construct the authorization template afresh: mutating the public request
    # object must never extend the tool/method allowlist.
    return {"jsonrpc": "2.0", "id": "chroma-routing-check", "method": "tools/call",
            "params": {"name": "check_rag_status", "arguments": {}}}


MCP_REQUEST = _mcp_request()
# Match vector_store_service._remember_client_identity's canonical serialization,
# without importing the backend, reading its environment or creating a client.
TARGET_FINGERPRINT = hashlib.sha256(json.dumps(
    {"mode": "REMOTE", "target": {"host": "127.0.0.1", "port": 8000, "ssl": False},
     "tenant": TENANT, "database": DATABASE},
    sort_keys=True, separators=(",", ":"),
).encode("utf-8")).hexdigest()


class RoutingCheckError(RuntimeError):
    """A fixed, non-sensitive diagnostic code suitable for an operator report."""

    def __init__(self, code):
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", code):
            code = "ROUTING_CHECK_FAILED"
        self.code = code
        super().__init__(code)


def _require(condition, code):
    if not condition:
        raise RoutingCheckError(code)


def _reject_constant(_value):
    raise ValueError("INVALID_JSON")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("INVALID_JSON")
        result[key] = value
    return result


def _decode_json(raw):
    try:
        return json.loads(raw, parse_constant=_reject_constant,
                          object_pairs_hook=_unique_object)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise RoutingCheckError("INVALID_JSON_RESPONSE") from None


def _finite_number(value):
    try:
        return type(value) in {int, float} and math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _valid_vector(value):
    # Bound memory use without assuming an embedding model or dimension of 384.
    return (isinstance(value, list) and 1 <= len(value) <= 65536
            and all(_finite_number(component) for component in value))


def _allowed_vector_read(port, method, path, body):
    if port != 8000 or method != "POST" or not isinstance(body, dict):
        return False
    if re.fullmatch(re.escape(CHROMA_PREFIX) + UUID + r"/get", path):
        return (set(body) == {"limit", "include"} and type(body.get("limit")) is int
                and body["limit"] == 1 and body.get("include") == ["embeddings"])
    if re.fullmatch(re.escape(CHROMA_PREFIX) + UUID + r"/query", path):
        vectors = body.get("query_embeddings")
        return (set(body) == {"query_embeddings", "n_results", "include"}
                and type(body.get("n_results")) is int and 1 <= body["n_results"] <= 3
                and body.get("include") == ["distances"]
                and isinstance(vectors, list) and len(vectors) == 1
                and _valid_vector(vectors[0]))
    return False


def http_json(port, method, path, body=None, token=""):
    """Return decoded JSON from an allowlisted loopback request or raise.

    The transport ignores proxies, never follows redirects and never sends a
    backend bearer token to a Chroma endpoint. Callers must select report fields
    from the decoded data, which can include untrusted collection metadata.
    """
    _require(type(port) is int and port in {8000, 4502, 8001}
             and isinstance(method, str) and isinstance(path, str),
             "REQUEST_NOT_ALLOWLISTED")
    chroma_path = (
        path in {"/api/v2/heartbeat", CHROMA_COLLECTIONS}
        or re.fullmatch(re.escape(CHROMA_PREFIX) + NAME, path) is not None
        or re.fullmatch(re.escape(CHROMA_PREFIX) + UUID + r"/count", path) is not None
    )
    allowed_get = method == "GET" and body is None and (
        (port in {8000, 4502} and chroma_path)
        or (port in {8001, 4502} and path in {"/health", "/mcp/health"})
    )
    allowed_post = (port in {8001, 4502} and method == "POST"
                    and path == "/mcp" and body == _mcp_request())
    vector_read = _allowed_vector_read(port, method, path, body)
    _require(allowed_get or allowed_post or vector_read, "REQUEST_NOT_ALLOWLISTED")
    _require(isinstance(token, str) and len(token) <= 8192
             and re.search(r"[\x00-\x20\x7f]", token) is None, "INVALID_AUTH_TOKEN")
    _require(not token or not (chroma_path or vector_read), "BACKEND_TOKEN_NOT_ALLOWED_FOR_CHROMA")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        # Only these strictly constrained read payloads can reach the transport.
        payload = json.dumps(body if vector_read else _mcp_request(),
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        _require(len(payload) <= MAX_BYTES, "REQUEST_TOO_LARGE")

    connection = None
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port,
                                                timeout=TIMEOUT_SECONDS)
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        _require(response.status == 200, "HTTP_STATUS_NOT_OK")
        length = response.getheader("Content-Length")
        if length is not None:
            _require(isinstance(length, str) and re.fullmatch(r"[0-9]{1,10}", length)
                     is not None, "INVALID_RESPONSE_LENGTH")
            _require(int(length) <= MAX_BYTES, "RESPONSE_TOO_LARGE")
        _require(response.getheader("Content-Encoding", "identity") == "identity",
                 "UNSUPPORTED_RESPONSE_ENCODING")
        raw = response.read(MAX_BYTES + 1)
        _require(len(raw) <= MAX_BYTES, "RESPONSE_TOO_LARGE")
        return _decode_json(raw)
    except (OSError, ValueError, TypeError, http.client.HTTPException):
        raise RoutingCheckError("HTTP_REQUEST_FAILED") from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except (OSError, http.client.HTTPException):
                pass


def _uuid(value, code):
    _require(isinstance(value, str) and re.fullmatch(UUID, value) is not None, code)
    return value.lower()


def _count(value, code):
    _require(type(value) is int and value >= 0, code)
    return value


def _expected_inventory(expected):
    _require(isinstance(expected, dict) and len(expected) == 7
             and all(name in expected for name in COLLECTIONS),
             "EXPECTED_SEVEN_COLLECTIONS_REQUIRED")
    result = {}
    for name, row in expected.items():
        _require(isinstance(name, str) and re.fullmatch(NAME, name) is not None
                 and isinstance(row, dict), "INVALID_EXPECTED_INVENTORY")
        result[name] = {
            "id": _uuid(row.get("id"), "INVALID_EXPECTED_COLLECTION_UUID"),
            "count": _count(row.get("count"), "INVALID_EXPECTED_COLLECTION_COUNT"),
        }
    _require(len({row["id"] for row in result.values()}) == 7,
             "DUPLICATE_EXPECTED_COLLECTION_UUID")
    return result


def inspect_inventory(port, expected):
    """Require exactly the seven expected names, UUIDs and counts at this route."""
    expected = _expected_inventory(expected)
    _require(type(port) is int and port in {8000, 4502}, "INVENTORY_PORT_NOT_ALLOWLISTED")
    heartbeat = http_json(port, "GET", "/api/v2/heartbeat")
    _require(isinstance(heartbeat, dict)
             and type(heartbeat.get("nanosecond heartbeat")) is int
             and heartbeat["nanosecond heartbeat"] > 0, "CHROMA_HEARTBEAT_NOT_CONFIRMED")
    listed = http_json(port, "GET", CHROMA_COLLECTIONS)
    _require(isinstance(listed, list) and len(listed) == len(expected),
             "COLLECTION_SET_MISMATCH")
    names = []
    for row in listed:
        _require(isinstance(row, dict) and isinstance(row.get("name"), str),
                 "INVALID_COLLECTION_LIST")
        names.append(row["name"])
    _require(len(set(names)) == len(names) and set(names) == set(expected),
             "COLLECTION_SET_MISMATCH")
    for row in listed:
        _require(_uuid(row.get("id"), "COLLECTION_UUID_UNAVAILABLE")
                 == expected[row["name"]]["id"], "COLLECTION_UUID_MISMATCH")

    observed = {}
    for name, row in expected.items():
        collection = http_json(port, "GET", CHROMA_PREFIX + name)
        _require(isinstance(collection, dict) and collection.get("name") == name,
                 "COLLECTION_NAME_MISMATCH")
        identifier = _uuid(collection.get("id"), "COLLECTION_UUID_UNAVAILABLE")
        _require(identifier == row["id"], "COLLECTION_UUID_MISMATCH")
        total = _count(http_json(port, "GET", CHROMA_PREFIX + identifier + "/count"),
                       "COLLECTION_COUNT_UNAVAILABLE")
        _require(total == row["count"], "COLLECTION_COUNT_MISMATCH")
        observed[name] = {"id": identifier, "count": total}
    return {"status": "MATCH", "port": port, "tenant": TENANT, "database": DATABASE,
            "heartbeat_confirmed": True, "collections": observed,
            "full_content_validation": False}


def _mcp_status(packet):
    _require(isinstance(packet, dict) and packet.get("jsonrpc") == "2.0"
             and packet.get("id") == _mcp_request()["id"] and packet.get("error") is None,
             "INVALID_MCP_RESPONSE")
    result = packet.get("result")
    _require(isinstance(result, dict) and result.get("isError", False) is False,
             "MCP_TOOL_ERROR")
    content = result.get("content")
    _require(isinstance(content, list) and 1 <= len(content) <= 16,
             "MCP_STATUS_UNAVAILABLE")
    candidates = []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = item.get("text")
        _require(isinstance(text, str), "INVALID_MCP_TEXT")
        try:
            text_size = len(text.encode("utf-8"))
        except UnicodeError:
            raise RoutingCheckError("INVALID_MCP_TEXT") from None
        _require(text_size <= MAX_BYTES, "INVALID_MCP_TEXT")
        data = _decode_json(text)
        if isinstance(data, dict) and "collections" in data:
            candidates.append(data)
    _require(len(candidates) == 1, "MCP_STATUS_UNAVAILABLE_OR_AMBIGUOUS")
    data = candidates[0]
    _require(data.get("status") == "ok" and data.get("chroma_available") is True,
             "CHROMA_AVAILABILITY_NOT_CONFIRMED")
    return data


def _checked_identity(value, expected):
    _require(isinstance(value, dict) and value.get("schema_version") == IDENTITY_SCHEMA
             and value.get("status") == "OK", "RUNTIME_IDENTITY_UNAVAILABLE")
    _require(value.get("mode") == "REMOTE", "RUNTIME_NOT_REMOTE")
    _require(value.get("tenant") == TENANT and value.get("database") == DATABASE,
             "RUNTIME_SCOPE_MISMATCH")
    _require(value.get("target_fingerprint") == TARGET_FINGERPRINT,
             "RUNTIME_TARGET_MISMATCH")
    entries = value.get("collections")
    _require(isinstance(entries, dict), "RUNTIME_COLLECTIONS_UNAVAILABLE")
    observed = {}
    for name in COLLECTIONS:
        row = entries.get(name)
        _require(isinstance(row, dict) and row.get("status") == "OK",
                 "RUNTIME_COLLECTION_UNAVAILABLE")
        identifier = _uuid(row.get("id"), "RUNTIME_COLLECTION_UUID_UNAVAILABLE")
        total = _count(row.get("count"), "RUNTIME_COLLECTION_COUNT_UNAVAILABLE")
        _require(identifier == expected[name]["id"], "RUNTIME_COLLECTION_UUID_MISMATCH")
        _require(total == expected[name]["count"], "RUNTIME_COLLECTION_COUNT_MISMATCH")
        observed[name] = {"status": "OK", "id": identifier, "count": total}
    return {"schema_version": IDENTITY_SCHEMA, "status": "OK", "mode": "REMOTE",
            "target_fingerprint": TARGET_FINGERPRINT, "tenant": TENANT,
            "database": DATABASE, "collections": observed}


def verify_backend(expected, token=""):
    """Check fresh backend and gateway MCP identities against the intended store."""
    expected = _expected_inventory(expected)
    observations = {}
    for name, port in (("backend", 8001), ("gateway", 4502)):
        health = http_json(port, "GET", "/mcp/health", token=token)
        _require(isinstance(health, dict) and health.get("status") == "alive",
                 "BACKEND_HEALTH_NOT_CONFIRMED")
        status = _mcp_status(http_json(port, "POST", "/mcp", _mcp_request(), token))
        observations[name] = _checked_identity(status.get("index_identity"), expected)
        counts = status.get("collections")
        _require(isinstance(counts, dict), "MCP_COUNTS_UNAVAILABLE")
        for collection in COLLECTIONS:
            total = _count(counts.get(collection), "MCP_COLLECTION_COUNT_UNAVAILABLE")
            _require(total == expected[collection]["count"], "MCP_COLLECTION_COUNT_MISMATCH")
    _require(observations["backend"] == observations["gateway"],
             "BACKEND_GATEWAY_IDENTITY_MISMATCH")
    return {"status": "MATCH", "backend": observations["backend"],
            "gateway": observations["gateway"], "full_content_validation": False}


def _valid_record_id(value):
    return (isinstance(value, str) and 1 <= len(value) <= 4096
            and re.search(r"[\x00-\x1f\x7f]", value) is None)


def smoke_vector_queries(expected):
    """Query one existing vector per nonempty collection without an embedder.

    Only a sample's dimension and result count enter the report. Record IDs,
    vectors, documents and metadata never enter it. A successful sample is not
    an exhaustive content audit or proof of embedding-model compatibility.
    """
    expected = _expected_inventory(expected)
    observed = {}
    for name, row in expected.items():
        if row["count"] == 0:
            observed[name] = {"status": "SKIPPED_EMPTY", "sampled_vectors": 0}
            continue
        prefix = CHROMA_PREFIX + row["id"]
        sample = http_json(8000, "POST", prefix + "/get",
                           {"limit": 1, "include": ["embeddings"]})
        _require(isinstance(sample, dict), "VECTOR_SAMPLE_UNAVAILABLE")
        ids, vectors = sample.get("ids"), sample.get("embeddings")
        _require(isinstance(ids, list) and len(ids) == 1 and _valid_record_id(ids[0])
                 and isinstance(vectors, list) and len(vectors) == 1
                 and _valid_vector(vectors[0]), "VECTOR_SAMPLE_INVALID")
        limit = min(3, row["count"])
        result = http_json(8000, "POST", prefix + "/query",
                           {"query_embeddings": [vectors[0]], "n_results": limit,
                            "include": ["distances"]})
        _require(isinstance(result, dict), "VECTOR_QUERY_UNAVAILABLE")
        result_ids, distances = result.get("ids"), result.get("distances")
        _require(isinstance(result_ids, list) and len(result_ids) == 1
                 and isinstance(result_ids[0], list) and 1 <= len(result_ids[0]) <= limit
                 and all(_valid_record_id(value) for value in result_ids[0]),
                 "VECTOR_QUERY_IDS_INVALID")
        _require(len(set(result_ids[0])) == len(result_ids[0]), "VECTOR_QUERY_IDS_INVALID")
        _require(isinstance(distances, list) and len(distances) == 1
                 and isinstance(distances[0], list) and len(distances[0]) == len(result_ids[0])
                 and all(_finite_number(value) for value in distances[0]),
                 "VECTOR_QUERY_DISTANCES_INVALID")
        observed[name] = {"status": "QUERY_SUCCEEDED", "sampled_vectors": 1,
                          "dimension": len(vectors[0]), "result_count": len(result_ids[0])}
    return {"status": "PASS", "port": 8000, "collections": observed,
            "query_smoke_only": True, "full_content_validation": False}
