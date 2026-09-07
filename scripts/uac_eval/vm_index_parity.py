"""Read-only VM index routing check; identity equality is not a corpus audit.

Uses the existing MCP check_rag_status over fixed VM-loopback endpoints. No
backend imports, Chroma clients, embedding calls, reindex, or service changes.
Exit 0 means the reported routing identities match, NOT permission to migrate
or proof that different stores contain identical documents/embeddings.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

from diagnose_vm_customer_index import check_backend, check_direct_chroma

SCHEMA = "chroma-index-identity-v1"
COLLECTIONS = ("jira_qa", "aem_guides", "dita_spec")
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


class ParityError(RuntimeError):
    """Only fixed reason codes, never server exception bodies or credentials."""


def checked_identity(value, *, require_remote=False, collections=COLLECTIONS):
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA:
        raise ParityError("RUNTIME_IDENTITY_UNAVAILABLE_DEPLOY_OBSERVABILITY_FIRST")
    if value.get("status") not in {"OK", "PARTIAL"}:
        raise ParityError("RUNTIME_IDENTITY_UNAVAILABLE")
    if value.get("mode") not in {"REMOTE", "EMBEDDED"}:
        raise ParityError("RUNTIME_STORAGE_MODE_UNKNOWN")
    if require_remote and value["mode"] != "REMOTE":
        raise ParityError("BACKEND_EMBEDDED_STOP_IMPORT_UNTIL_SHARED_STORE_IS_VERIFIED")
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("target_fingerprint", ""))):
        raise ParityError("TARGET_IDENTITY_UNAVAILABLE")
    for field in ("tenant", "database"):
        if not isinstance(value.get(field), str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value[field]):
            raise ParityError("TENANT_OR_DATABASE_UNAVAILABLE")
    entries = value.get("collections")
    if not isinstance(entries, dict):
        raise ParityError("COLLECTION_IDENTITY_UNAVAILABLE")
    for name in collections:
        entry = entries.get(name)
        if not isinstance(entry, dict) or entry.get("status") != "OK":
            raise ParityError("COLLECTION_IDENTITY_UNAVAILABLE")
        if not re.fullmatch(UUID, str(entry.get("id", ""))):
            raise ParityError("COLLECTION_UUID_UNAVAILABLE")
        if type(entry.get("count")) is not int or entry["count"] < 0:
            raise ParityError("COLLECTION_COUNT_UNAVAILABLE")
    return value


def require_same_index(expected, observed, *, require_remote=False, collections=COLLECTIONS,
                       compare_counts=True):
    """Check target AND UUID, so cloned collections on another target don't pass."""
    expected = checked_identity(expected, require_remote=require_remote, collections=collections)
    observed = checked_identity(observed, require_remote=require_remote, collections=collections)
    for field in ("mode", "target_fingerprint", "tenant", "database"):
        if expected[field] != observed[field]:
            raise ParityError("INDEX_TARGET_MISMATCH")
    for name in collections:
        first, second = expected["collections"][name], observed["collections"][name]
        if first["id"] != second["id"]:
            raise ParityError("COLLECTION_UUID_MISMATCH")
        if compare_counts and first["count"] != second["count"]:
            raise ParityError("COLLECTION_COUNT_CHANGED_QUIESCE_WRITERS_AND_RECHECK")


def live_backend_identity(token="", *, require_remote=False):
    """Fresh HTTP observations, not an old diagnostic JSON supplied as authority."""
    backend = check_backend(8001, token).get("rag_status", {})
    gateway = check_backend(4502, token).get("rag_status", {})
    if backend.get("status") != "OK" or gateway.get("status") != "OK":
        raise ParityError("LIVE_BACKEND_OR_GATEWAY_UNAVAILABLE")
    expected, observed = backend.get("index_identity"), gateway.get("index_identity")
    require_same_index(expected, observed, require_remote=require_remote)
    return expected


def direct_comparison(identity, direct):
    """Direct public route is supplementary; import never trusts this alone."""
    identity = checked_identity(identity)
    if direct.get("status") != "COUNT_OBSERVED":
        return {"status": "UNAVAILABLE", "reason": "DIRECT_CHROMA_UNAVAILABLE"}
    local = identity["collections"]["jira_qa"]
    if direct.get("collection_id") != local["id"]:
        return {"status": "MISMATCH", "reason": "DIRECT_COLLECTION_UUID_MISMATCH"}
    if type(direct.get("jira_qa_count")) is not int or direct["jira_qa_count"] != local["count"]:
        return {"status": "MISMATCH", "reason": "DIRECT_COLLECTION_COUNT_MISMATCH"}
    # UUIDs can be copied with a database. Direct route reveals no target hash.
    return {"status": "UUID_AND_COUNT_MATCH", "reason": "TARGET_AND_CONTENT_PARITY_NOT_PROVEN"}


def run_self_tests():
    def identity(mode="REMOTE"):
        return {"schema_version": SCHEMA, "status": "OK", "mode": mode,
                "target_fingerprint": "a" * 64, "tenant": "default_tenant", "database": "default_database",
                "collections": {name: {"status": "OK", "id": f"00000000-0000-0000-0000-{n:012d}",
                                       "count": 20 + n} for n, name in enumerate(COLLECTIONS, 1)}}
    baseline = identity()
    require_same_index(baseline, copy.deepcopy(baseline), require_remote=True)
    tests = [(None, "RUNTIME_IDENTITY_UNAVAILABLE"), (identity("EMBEDDED"), "BACKEND_EMBEDDED")]
    for field, value in (("target_fingerprint", None), ("tenant", ""), ("mode", "UNKNOWN")):
        item = identity(); item[field] = value; tests.append((item, None))
    for field, value in (("id", None), ("count", True), ("count", -1), ("count", None), ("status", "PARTIAL")):
        item = identity(); item["collections"]["jira_qa"][field] = value; tests.append((item, None))
    for item, reason in tests:
        try:
            require_same_index(baseline, item, require_remote=True)
        except ParityError as exc:
            assert reason is None or str(exc).startswith(reason)
        else:
            raise AssertionError("Unknown/unsafe identity passed")
    for field, value, reason in (("id", "ffffffff-ffff-ffff-ffff-ffffffffffff", "COLLECTION_UUID_MISMATCH"),
                                 ("count", 100, "COLLECTION_COUNT_CHANGED")):
        item = identity(); item["collections"]["jira_qa"][field] = value
        try: require_same_index(baseline, item)
        except ParityError as exc: assert str(exc).startswith(reason)
        else: raise AssertionError("Collection drift passed")
    clone = identity(); clone["target_fingerprint"] = "b" * 64
    try: require_same_index(baseline, clone)
    except ParityError as exc: assert str(exc) == "INDEX_TARGET_MISMATCH"
    else: raise AssertionError("Cloned UUID on another target passed")
    same_direct = {"status": "COUNT_OBSERVED", "collection_id": baseline["collections"]["jira_qa"]["id"],
                   "jira_qa_count": baseline["collections"]["jira_qa"]["count"]}
    assert direct_comparison(baseline, same_direct)["reason"] == "TARGET_AND_CONTENT_PARITY_NOT_PROVEN"
    assert direct_comparison(baseline, dict(same_direct, collection_id="ffffffff-ffff-ffff-ffff-ffffffffffff"))["status"] == "MISMATCH"
    assert direct_comparison(baseline, {})["status"] == "UNAVAILABLE"
    original = check_backend
    calls = []
    try:
        def fake(port, token):
            calls.append(port)
            return {"rag_status": {"status": "OK", "index_identity": baseline}}
        globals()["check_backend"] = fake
        assert live_backend_identity(require_remote=True) == baseline and calls == [8001, 4502]
        globals()["check_backend"] = lambda port, token: {"rag_status": {"status": "OK"}}
        try: live_backend_identity()
        except ParityError: pass
        else: raise AssertionError("Legacy response without identity passed")
    finally:
        globals()["check_backend"] = original
    print("PASS: VM parity self-tests (UUIDs, cloned targets, missing identity, embedded guard, counts, fixed live endpoints)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--require-shared", action="store_true", help="Require backend HTTP Chroma before imports")
    args = parser.parse_args(argv)
    if args.self_test:
        run_self_tests(); return 0
    if sys.platform != "linux":
        parser.error("Run on the VM; loopback must refer to the actual shared backend")
    try:
        identity = live_backend_identity(os.environ.get("AEM_STUDIO_TOKEN", ""), require_remote=args.require_shared)
        direct = direct_comparison(identity, check_direct_chroma())
        print(json.dumps({"schema_version": "vm-index-parity-v1", "mcp_backend_routing": "MATCH",
                          "index_identity": identity, "direct_chroma": direct,
                          "content_inventory_verified": False, "embedding_compatibility_verified": False,
                          "import_authorized": False}, indent=2))
        # Missing direct route is not required for team MCP, but a conflicting
        # exposed store is an explicit operator failure rather than a green check.
        return 2 if direct["status"] == "MISMATCH" else 0
    except ParityError as exc:
        print("STOP: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
