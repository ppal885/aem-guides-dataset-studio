"""Replay the reviewed URLs, or append one missing Guides URL; default is --check."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
import importlib
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import stat
import struct
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
URL_FILE = ROOT / "scripts/data/publishing-knowledge-urls-20260909.txt"
PYTHON = Path("/opt/aem-backend-candidate-sPxFr6YU/venv/bin/python")
MODEL = ROOT / "backend/models/all-MiniLM-L6-v2"
MODEL_HASH = "056b49a923ab30123c99a4e06daf0bd4875f894fa75f53c3d68f84df1411e61a"
ROUTING = {"CHROMA_HOST": "127.0.0.1", "CHROMA_PORT": "8000", "CHROMA_SSL": "false"}
CA = "/etc/ssl/certs/ca-certificates.crt"


class ReplayError(RuntimeError):
    """A fixed diagnostic code safe to include in the public receipt."""


def require(condition, code):
    if not condition:
        raise ReplayError(code)


def helper(name):
    sys.path.insert(0, str(ROOT / "scripts/uac_eval"))
    return importlib.import_module(name)


def ingest_helper():
    # Also works under the reviewed -I invocation, without backend imports.
    sys.path.insert(0, str(ROOT / "scripts"))
    return importlib.import_module("ingest_urls")


def read_urls(path):
    urls = path.read_text(encoding="utf-8").splitlines()
    require(len(urls) == len(set(urls)) == 9, "NINE_UNIQUE_URLS_REQUIRED")
    for url in urls:
        parts = urlsplit(url)
        require(parts.scheme == "https" and parts.netloc == "experienceleague.adobe.com"
                and parts.path.startswith("/en/docs/experience-manager-guides/")
                and not parts.query and not parts.fragment, "UNEXPECTED_URL")
    return urls


def service_snapshot():
    result = {}
    for service in ("aem-backend.service", "chroma.service"):
        output = subprocess.check_output(
            ["systemctl", "show", service, "-p", "MainPID", "-p", "InvocationID", "-p", "ActiveState"],
            text=True, stderr=subprocess.DEVNULL)
        values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        require(values.get("ActiveState") == "active" and values.get("MainPID", "0").isdigit()
                and int(values["MainPID"]) > 0 and bool(values.get("InvocationID")), "SERVICE_NOT_ACTIVE")
        result[service] = values
    return result


def validate_model_configuration(environment, service_cwd):
    """Accept equivalent paths to the reviewed artifact, never a model fallback."""
    provider = environment.get("USE_AZURE_EMBEDDING", "false")
    require(isinstance(provider, str) and provider.lower() in {"false", "0", "no", "off"},
            "EMBEDDING_PROVIDER_NOT_LOCAL")
    configured = environment.get("DITA_EMBEDDING_MODEL_PATH", "")
    require(isinstance(configured, str) and bool(configured.strip()), "MODEL_PATH_NOT_CONFIGURED")
    require(service_cwd.is_absolute(), "SERVICE_WORKING_DIRECTORY_MISMATCH")
    try:
        expected = MODEL.resolve(strict=True)
        expected_is_directory = expected.is_dir()
    except (OSError, RuntimeError, ValueError):
        raise ReplayError("REVIEWED_MODEL_DIRECTORY_UNAVAILABLE") from None
    require(expected_is_directory, "REVIEWED_MODEL_DIRECTORY_UNAVAILABLE")
    try:
        # embedding_service strips this value and resolves relative paths in the
        # backend's cwd, not in the operator's shell cwd. Do not expand variables,
        # ~ or literal quotes; no bundled-model/download fallback is authorized.
        selected = Path(configured.strip())
        if not selected.is_absolute():
            selected = service_cwd / selected
        selected = selected.resolve(strict=True)
        selected_is_directory = selected.is_dir()
    except (OSError, RuntimeError, ValueError):
        raise ReplayError("MODEL_PATH_UNAVAILABLE") from None
    require(selected_is_directory, "MODEL_PATH_UNAVAILABLE")
    require(selected == expected, "MODEL_PATH_TARGET_MISMATCH")
    return selected


def load_live_configuration(snapshot):
    """Reproduce app.main's loader without importing or starting the application."""
    from dotenv import load_dotenv

    process = Path("/proc") / snapshot["aem-backend.service"]["MainPID"]
    argv = process.joinpath("cmdline").read_bytes().split(b"\0")
    require(str(PYTHON).encode() in argv and process.joinpath("exe").resolve() == PYTHON.resolve(),
            "ACTIVE_CANDIDATE_MISMATCH")
    service_cwd = process.joinpath("cwd").resolve()
    require(service_cwd == ROOT / "backend", "SERVICE_WORKING_DIRECTORY_MISMATCH")
    operator_token = os.environ.get("AEM_STUDIO_TOKEN", "")
    launch_env = dict(item.decode().split("=", 1) for item in process.joinpath("environ").read_bytes().split(b"\0")
                      if b"=" in item)
    os.environ.clear()
    os.environ.update(launch_env)
    for path in (ROOT / ".env", ROOT / "backend/.env"):
        if path.exists():
            load_dotenv(path, override=True, encoding="utf-8-sig")
    docker = ROOT / "backend/.env.docker"
    if docker.exists():
        for line in docker.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip():
                    os.environ[key.strip()] = value.strip()
    require(all(os.environ.get(k) == v for k, v in ROUTING.items()), "SHARED_HTTP_CONFIGURATION_REQUIRED")
    validate_model_configuration(os.environ, service_cwd)
    writers = helper("repair_vm_chroma_routing").WRITERS
    require(all(os.environ.get(k, "").lower() in {"false", "0", "no", "off"} for k in writers),
            "BACKGROUND_WRITER_PAUSE_NOT_CONFIRMED")
    require(MODEL.is_dir() and Path(CA).is_file(), "MODEL_OR_OS_CA_MISSING")
    os.environ.update({**ROUTING, "USE_AZURE_EMBEDDING": "false", "DITA_EMBEDDING_MODEL_PATH": str(MODEL),
                       "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
                       "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2",
                       "SSL_CERT_FILE": CA, "REQUESTS_CA_BUNDLE": CA})
    # DATABASE_URL and graph capture settings stay as loaded; never print/persist the environment.
    return operator_token or os.environ.get("AEM_STUDIO_TOKEN", "")


def shared_identity(token):
    probe = helper("verify_vm_search_embeddings")
    first = probe.checked_status(probe.read_json(8001, "status", token=token))["index_identity"]
    second = probe.checked_status(probe.read_json(4502, "status", token=token))["index_identity"]
    require(first == second, "BACKEND_GATEWAY_IDENTITY_MISMATCH")
    for name, expected in first["collections"].items():
        actual = probe.read_json(8000, "collection", name)
        require(actual["id"] == expected["id"]
                and probe.read_json(8000, "count", actual["id"]) == expected["count"], "DIRECT_IDENTITY_MISMATCH")
    return first


def parse_success(stdout, urls):
    require(not re.search(r"^(?:FAIL|SKIP)\b", stdout, re.MULTILINE), "INGEST_REPORTED_FAILURE")
    matches = re.findall(r"^OK\s+(\d+) chunks  (\S+)\s*$", stdout, re.MULTILINE)
    require(len(matches) == len(urls) and {url for _, url in matches} == set(urls)
            and all(int(count) > 0 for count, _ in matches), "NINE_SUCCESSFUL_INGESTS_REQUIRED")
    return {url: int(count) for count, url in matches}


def verify_records(records, url, expected_ids):
    require(len(records["ids"]) == len(expected_ids) and set(records["ids"]) == set(expected_ids),
            "INGEST_RECORDS_MISSING")
    require(len(records.get("documents") or []) == len(expected_ids)
            and len(records.get("metadatas") or []) == len(expected_ids), "INGEST_READBACK_INCOMPLETE")
    require(all(isinstance(doc, str) and doc.strip() for doc in records["documents"])
            and all(isinstance(meta, dict) and meta.get("url") == url for meta in records["metadatas"]),
            "INGEST_READBACK_INVALID")


def check(single_url=None):
    require(sys.platform == "linux" and os.geteuid() == 0, "RUN_AS_ROOT_ON_VM")
    require(ROOT == Path("/root/aem-guides-dataset-studio") and Path(sys.executable) == PYTHON
            and sys.version_info.releaselevel == "final", "REVIEWED_INTERPRETER_REQUIRED")
    snapshot = service_snapshot()
    token = load_live_configuration(snapshot)
    if single_url is None:
        urls = read_urls(URL_FILE)
    else:
        try:
            urls = [ingest_helper().validate_guides_url(single_url)]
        except ValueError:
            raise ReplayError("UNEXPECTED_URL") from None
    configured = json.loads((ROOT / "backend/config/aem_guides_crawl_urls.json").read_text())["urls"]
    require(set(urls).issubset(configured), "PULL_UPDATED_CRAWL_CONFIG_FIRST")
    identity = shared_identity(token)
    prepared = None
    if single_url is not None:
        # Freeze the successful response now. Apply never refetches this page.
        try:
            prepared = ingest_helper().prepare_guides_page(urls[0], cafile=CA)
        except ValueError:
            raise ReplayError("SINGLE_URL_PAGE_PREFLIGHT_FAILED") from None
    else:
        import httpx
        import ssl
        with httpx.Client(timeout=30, follow_redirects=True, verify=ssl.create_default_context(cafile=CA)) as client:
            for url in urls:
                response = client.get(url)
                require(response.status_code == 200 and response.url.scheme == "https"
                        and response.url.host == "experienceleague.adobe.com"
                        and "text/html" in response.headers.get("content-type", "").lower(), "PAGE_PREFLIGHT_FAILED")
    require(service_snapshot() == snapshot, "SERVICE_CHANGED_DURING_CHECK")
    return {"urls": urls, "token": token, "services": snapshot, "identity": identity, "prepared": prepared}


@contextmanager
def missing_url_lock():
    """Serialize cooperating one-URL imports; never delete a lock another process uses."""
    import fcntl
    descriptor = os.open(ROOT.parent / ".aem-guides-missing-url.lock",
                         os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        details = os.fstat(descriptor)
        require(stat.S_ISREG(details.st_mode) and details.st_uid == 0
                and not details.st_mode & 0o077, "UNSAFE_IMPORT_LOCK")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ReplayError("ANOTHER_SINGLE_URL_IMPORT_RUNNING") from None
        yield
    finally:
        os.close(descriptor)


def require_page_absent(collection, prepared):
    """Check both source locators and stable IDs, regardless of existing ID scheme."""
    for url in {prepared["url"], prepared["final_url"]}:
        for locator in {url, url.rstrip("/") + "/"}:
            for field in ("url", "source_url", "source"):
                records = collection.get(where={field: locator}, limit=1, include=["metadatas"])
                require(isinstance(records, dict) and isinstance(records.get("ids"), list),
                        "ABSENCE_RESPONSE_INVALID")
                require(not records["ids"], "URL_ALREADY_PRESENT_NO_WRITE")
    records = collection.get(ids=prepared["ids"], include=["metadatas"])
    require(isinstance(records, dict) and isinstance(records.get("ids"), list), "ABSENCE_RESPONSE_INVALID")
    require(not records["ids"], "INGEST_ID_ALREADY_PRESENT_NO_WRITE")


def checked_vectors(vectors, expected):
    """Require actual finite, nonzero local embeddings before any add request."""
    if hasattr(vectors, "tolist"):
        vectors = vectors.tolist()
    require(isinstance(vectors, list) and len(vectors) == expected, "EMBEDDINGS_INVALID")
    result = []
    for vector in vectors:
        if hasattr(vector, "tolist"):
            vector = vector.tolist()
        require(isinstance(vector, (list, tuple)) and len(vector) == 384
                and all(type(value) in (int, float) and math.isfinite(value) for value in vector)
                and any(value != 0 for value in vector), "EMBEDDINGS_INVALID")
        try:
            encoded = struct.pack("<384f", *vector)
        except (OverflowError, struct.error):
            raise ReplayError("EMBEDDINGS_INVALID") from None
        require(all(math.isfinite(value) for value in struct.unpack("<384f", encoded)), "EMBEDDINGS_INVALID")
        result.append(list(vector))
    return result


def verify_exact_payload(records, prepared, vectors):
    verify_records(records, prepared["url"], prepared["ids"])
    stored = checked_vectors(records.get("embeddings"), len(prepared["ids"]))
    actual = {key: index for index, key in enumerate(records["ids"])}
    for index, key in enumerate(prepared["ids"]):
        position = actual[key]
        require(records["documents"][position] == prepared["documents"][index]
                and records["metadatas"][position] == prepared["metadatas"][index]
                and struct.pack("<384f", *stored[position]) == struct.pack("<384f", *vectors[index]),
                "EXACT_PAYLOAD_READBACK_MISMATCH")


def capture_graph_events_safely(queue_events, prepared):
    """Do not expose downstream DB/import exception text from this CLI process.

    Existing graph policy is unchanged. Restore logging after this narrow call;
    running backend/Chroma processes are not affected. Public result is fixed-code.
    """
    previous = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink), redirect_stderr(sink):
            try:
                return queue_events("aem_guides", ids=prepared["ids"], documents=prepared["documents"],
                                    metadatas=prepared["metadatas"], event_type="upsert") is True
            except Exception:
                return False
    finally:
        logging.disable(previous)


def append_missing_page(collection, prepared, embed_texts, queue_events, assert_state, receipt):
    """Add frozen content only. Chroma add cannot overwrite a raced existing ID."""
    require_page_absent(collection, prepared)
    vectors = checked_vectors(embed_texts(prepared["documents"]), len(prepared["ids"]))
    assert_state()
    # A second check closes the long model-load window. An uncooperative writer
    # still can race, so use add (not upsert), then exact payload/count verification.
    require_page_absent(collection, prepared)
    receipt["phase"] = "MISSING_ONLY_ADD"
    receipt["index_write_requested"] = True
    collection.add(ids=prepared["ids"], documents=prepared["documents"],
                   metadatas=prepared["metadatas"], embeddings=vectors)
    receipt["phase"] = "EXACT_READBACK"
    verify_exact_payload(collection.get(ids=prepared["ids"], include=["documents", "metadatas", "embeddings"]),
                         prepared, vectors)
    receipt["exact_payload_readback"] = True
    receipt["phase"] = "GRAPH_EVENT_CAPTURE"
    require(capture_graph_events_safely(queue_events, prepared), "GRAPH_EVENT_CAPTURE_FAILED_AFTER_ADD")


def apply(context, output_parent, receipt):
    """Load/compare sampled embeddings only in the explicit write phase."""
    model_check = helper("verify_local_embedding_canaries")
    require(model_check.model_hash(MODEL) == MODEL_HASH, "MODEL_HASH_CHANGED")
    sys.path.insert(0, str(ROOT / "backend"))
    from app.services import embedding_service, vector_store_service
    client = vector_store_service._get_client()
    require(client is not None, "CHROMA_UNAVAILABLE")
    observed = helper("vm_chroma_routing_checks")._checked_identity(
        vector_store_service.get_index_identity(), context["identity"]["collections"])
    require(observed == context["identity"], "INGEST_CLIENT_IDENTITY_MISMATCH")
    collection = client.get_collection("aem_guides")
    require(str(collection.id) == context["identity"]["collections"]["aem_guides"]["id"], "CLIENT_COLLECTION_MISMATCH")
    samples = collection.get(limit=20, include=["documents", "embeddings"])
    rows, seen = [], set()
    for text, vector in zip(samples["documents"], samples["embeddings"]):
        if isinstance(text, str) and text.strip() and text not in seen:
            rows.append((text, vector.tolist() if hasattr(vector, "tolist") else vector))
            seen.add(text)
        if len(rows) == 3:
            break
    require(len(rows) == 3, "THREE_STORED_CANARIES_REQUIRED")
    receipt["sampled_model_check"] = model_check.compare_canaries(rows, embedding_service.embed_texts, 384)
    require(service_snapshot() == context["services"] and shared_identity(context["token"]) == context["identity"],
            "STATE_CHANGED_BEFORE_INGEST")
    parent = output_parent.resolve()
    require(parent.is_dir() and parent != ROOT and not parent.is_relative_to(ROOT), "OUTPUT_MUST_BE_OUTSIDE_REPO")
    run = Path(tempfile.mkdtemp(prefix="aem-publishing-refresh-", dir=parent))
    receipt["output_directory"] = str(run)
    (run / "crawl-urls.before.json").write_bytes((ROOT / "backend/config/aem_guides_crawl_urls.json").read_bytes())
    if context.get("prepared") is not None:
        prepared = context["prepared"]
        require(context["urls"] == [prepared["url"]], "PREPARED_URL_MISMATCH")
        receipt.update(index_write_requested=False, operation="SINGLE_URL_MISSING_ONLY_ADD",
                       overwrite_requested=False, crawl_config_changed=False,
                       source_page_sha256=prepared["page_sha256"], source_text_sha256=prepared["text_sha256"])
        frozen = (json.dumps(prepared, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        (run / "prepared-page.json").write_bytes(frozen)
        receipt["prepared_payload_sha256"] = hashlib.sha256(frozen).hexdigest()

        def unchanged():
            require(service_snapshot() == context["services"]
                    and shared_identity(context["token"]) == context["identity"], "STATE_CHANGED_BEFORE_ADD")

        with missing_url_lock():
            unchanged()
            append_missing_page(collection, prepared, embedding_service.embed_texts,
                                vector_store_service._queue_evidence_graph_events, unchanged, receipt)
            receipt["phase"] = "IDENTITY_AND_COUNT_READBACK"
            after = shared_identity(context["token"])
            for name, before in context["identity"]["collections"].items():
                actual = after["collections"][name]
                require(actual["id"] == before["id"], "COLLECTION_UUID_CHANGED")
                expected_count = before["count"] + (len(prepared["ids"]) if name == "aem_guides" else 0)
                require(actual["count"] == expected_count, "UNEXPECTED_COUNT_CHANGE")
            require(service_snapshot() == context["services"], "SERVICE_CHANGED_DURING_INGEST")
        receipt.update(status="PASS_SINGLE_URL_APPENDED", phase="COMPLETE",
                       chunks_by_url={prepared["url"]: len(prepared["ids"])}, identity_after=after)
        return
    receipt["phase"] = "INGEST"
    result = subprocess.run([str(PYTHON), "-I", "-B", str(ROOT / "scripts/ingest_urls.py"), *context["urls"]],
                            cwd=ROOT / "backend", env=dict(os.environ), capture_output=True, text=True, timeout=1800)
    receipt["ingest_exit_code"] = result.returncode
    require(result.returncode == 0, "INGEST_PROCESS_FAILED")
    counts = parse_success(result.stdout + "\n" + result.stderr, context["urls"])
    receipt["phase"] = "READBACK"
    for url, count in counts.items():
        key = hashlib.md5(url.encode()).hexdigest()[:10]  # Existing ingest ID contract; not cryptographic use.
        ids = [f"aem_ingest_{key}_{index}" for index in range(count)]
        verify_records(collection.get(ids=ids, include=["documents", "metadatas"]), url, ids)
    after = shared_identity(context["token"])
    for name, before in context["identity"]["collections"].items():
        require(after["collections"][name]["id"] == before["id"], "COLLECTION_UUID_CHANGED")
        require(after["collections"][name]["count"] >= before["count"] if name == "aem_guides"
                else after["collections"][name]["count"] == before["count"], "UNEXPECTED_COUNT_CHANGE")
    require(service_snapshot() == context["services"], "SERVICE_CHANGED_DURING_INGEST")
    receipt.update(status="PASS_APPLIED", phase="COMPLETE", chunks_by_url=counts, identity_after=after)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Default: HTTP/config checks only; no model load/index writes")
    mode.add_argument("--apply", action="store_true", help="Check, compare sampled vectors, ingest and verify selected URLs")
    parser.add_argument("--url", help="Optional single Guides URL: missing-only add, never refresh/overwrite existing records")
    parser.add_argument("--output-parent", type=Path, default=Path("/root"))
    args = parser.parse_args(argv)
    receipt = {"status": "STOP", "phase": "PREFLIGHT", "mode": "apply" if args.apply else "check"}
    try:
        context = check(single_url=args.url) if args.url is not None else check()
        receipt.update(identity_before=context["identity"], url_count=len(context["urls"]),
                       graph_event_capture_enabled=os.environ.get("EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED",
                                                                   os.environ.get("EVIDENCE_GRAPH_ENABLED", "false")).lower()
                       in {"1", "true", "yes", "on"})
        if args.apply:
            receipt["phase"] = "SAMPLED_MODEL_CHECK"
            apply(context, args.output_parent, receipt)
        else:
            receipt.update(status="PASS_CHECK_ONLY", phase="COMPLETE", model_compatibility_checked=False)
    except ReplayError as exc:
        receipt["reason"] = str(exc)
    except Exception:
        receipt["reason"] = "UNEXPECTED_FAILURE"
    if "output_directory" in receipt:
        (Path(receipt["output_directory"]) / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
