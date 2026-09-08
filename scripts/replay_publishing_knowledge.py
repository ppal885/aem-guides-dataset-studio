"""Replay the nine publishing URLs through the reviewed VM runtime; default is --check."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
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


def load_live_configuration(snapshot):
    """Reproduce app.main's loader without importing or starting the application."""
    from dotenv import load_dotenv

    process = Path("/proc") / snapshot["aem-backend.service"]["MainPID"]
    argv = process.joinpath("cmdline").read_bytes().split(b"\0")
    require(str(PYTHON).encode() in argv and process.joinpath("exe").resolve() == PYTHON.resolve(),
            "ACTIVE_CANDIDATE_MISMATCH")
    require(process.joinpath("cwd").resolve() == ROOT / "backend", "SERVICE_WORKING_DIRECTORY_MISMATCH")
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
    require(os.environ.get("USE_AZURE_EMBEDDING", "false").lower() in {"false", "0", "no", "off"}
            and os.environ.get("DITA_EMBEDDING_MODEL_PATH") == str(MODEL), "REVIEWED_LOCAL_MODEL_REQUIRED")
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


def check():
    require(sys.platform == "linux" and os.geteuid() == 0, "RUN_AS_ROOT_ON_VM")
    require(ROOT == Path("/root/aem-guides-dataset-studio") and Path(sys.executable) == PYTHON
            and sys.version_info.releaselevel == "final", "REVIEWED_INTERPRETER_REQUIRED")
    snapshot = service_snapshot()
    token = load_live_configuration(snapshot)
    urls = read_urls(URL_FILE)
    configured = json.loads((ROOT / "backend/config/aem_guides_crawl_urls.json").read_text())["urls"]
    require(set(urls).issubset(configured), "PULL_UPDATED_CRAWL_CONFIG_FIRST")
    identity = shared_identity(token)
    import httpx
    import ssl
    with httpx.Client(timeout=30, follow_redirects=True, verify=ssl.create_default_context(cafile=CA)) as client:
        for url in urls:
            response = client.get(url)
            require(response.status_code == 200 and response.url.scheme == "https"
                    and response.url.host == "experienceleague.adobe.com"
                    and "text/html" in response.headers.get("content-type", "").lower(), "PAGE_PREFLIGHT_FAILED")
    require(service_snapshot() == snapshot, "SERVICE_CHANGED_DURING_CHECK")
    return {"urls": urls, "token": token, "services": snapshot, "identity": identity}


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
    mode.add_argument("--apply", action="store_true", help="Check, compare sampled vectors, ingest and verify all nine URLs")
    parser.add_argument("--output-parent", type=Path, default=Path("/root"))
    args = parser.parse_args(argv)
    receipt = {"status": "STOP", "phase": "PREFLIGHT", "mode": "apply" if args.apply else "check"}
    try:
        context = check()
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
