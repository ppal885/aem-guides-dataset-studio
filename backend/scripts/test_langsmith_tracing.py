"""Smoke test: chat_turn should appear in LangSmith project data_set_studio."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")

BASE = os.getenv("AEM_STUDIO_URL", "http://127.0.0.1:8001").rstrip("/")
TOKEN = os.getenv("AEM_STUDIO_TOKEN", "dev-bypass")
API_KEY = (os.getenv("LANGSMITH_API_KEY") or "").strip()
PROJECT = (os.getenv("LANGSMITH_PROJECT") or "data_set_studio").strip()
LS_ENDPOINT = (os.getenv("LANGSMITH_ENDPOINT") or "https://api.smith.langchain.com").rstrip("/")


def _request(method: str, url: str, data: dict | None = None, headers: dict | None = None) -> tuple[int, str]:
    body = json.dumps(data).encode() if data is not None else None
    hdrs = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def _stream_chat(session_id: str, content: str) -> dict:
    payload = json.dumps({"content": content, "human_prompts": True}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1/chat/sessions/{session_id}/messages",
        data=payload,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    done = False
    error = None
    with urllib.request.urlopen(req, timeout=180) as resp:
        buffer = ""
        for raw in resp:
            buffer += raw.decode(errors="replace")
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                for line in block.splitlines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "done":
                        done = True
                    elif event.get("type") == "error":
                        error = event.get("message")
    return {"done": done, "error": error}


def _query_langsmith_runs(*, since_minutes: int = 10) -> list[dict]:
    if not API_KEY:
        return []
    since = time.time() - since_minutes * 60
    payload = {
        "session": [],
        "project_name": PROJECT,
        "filter": 'and(eq(name, "chat_turn"), gt(start_time, "' + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(since)) + '"))',
        "limit": 5,
        "order": "desc",
    }
    req = urllib.request.Request(
        f"{LS_ENDPOINT}/runs/query",
        data=json.dumps(payload).encode(),
        headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    runs = data.get("runs") if isinstance(data, dict) else data
    return runs if isinstance(runs, list) else []


def main() -> int:
    print("=== LangSmith tracing smoke test ===")
    print(f"Backend: {BASE}")
    print(f"LangSmith project: {PROJECT}")
    print(f"Tracing enabled env: LANGSMITH_TRACING={os.getenv('LANGSMITH_TRACING')} LANGCHAIN_TRACING_V2={os.getenv('LANGCHAIN_TRACING_V2')}")

    status, health = _request("GET", f"{BASE}/health")
    print(f"Health: {status}")
    if status != 200:
        print(health)
        return 1

    status, body = _request("POST", f"{BASE}/api/v1/chat/sessions", {})
    if status != 200:
        print("Create session failed:", status, body)
        return 1
    session_id = json.loads(body)["session_id"]
    print(f"Session: {session_id}")

    question = "LangSmith trace test: what is a DITA conref in one sentence?"
    print(f"Sending chat: {question[:60]}...")
    started = time.time()
    result = _stream_chat(session_id, question)
    elapsed = round(time.time() - started, 1)
    print(f"Chat finished in {elapsed}s — done={result['done']} error={result.get('error')}")

    # Give LangSmith ingest a moment
    time.sleep(3)

    status, pairs_body = _request("GET", f"{BASE}/api/v1/chat/eval/pairs?limit=5&search=LangSmith")
    pair_trace = None
    if status == 200:
        items = json.loads(pairs_body).get("items") or []
        for item in items:
            if "LangSmith trace test" in (item.get("question") or ""):
                pair_trace = {
                    "assistant_message_id": item.get("assistant_message_id"),
                    "langsmith_run_id": item.get("langsmith_run_id"),
                    "langsmith_trace_url": item.get("langsmith_trace_url"),
                }
                break

    print("\n--- Eval dashboard quality row ---")
    if pair_trace:
        print(json.dumps(pair_trace, indent=2))
    else:
        print("(no matching eval pair yet)")

    print("\n--- LangSmith API (chat_turn runs) ---")
    try:
        runs = _query_langsmith_runs(since_minutes=15)
        if not runs:
            print("No recent chat_turn runs found in project (may need a few seconds, or check project name/API key).")
        for run in runs[:3]:
            rid = run.get("id")
            name = run.get("name")
            start = run.get("start_time")
            status_r = run.get("status")
            url = f"https://smith.langchain.com/public/{rid}/r" if rid else None
            print(f"  run_id={rid} name={name} status={status_r} start={start}")
            if url:
                print(f"  url={url}")
    except Exception as exc:
        print(f"LangSmith API query failed: {exc}")

    ok_api = bool(runs) if "runs" in dir() else False
    ok_db = bool(pair_trace and pair_trace.get("langsmith_run_id")) if pair_trace else False
    print("\n=== Result ===")
    print(f"LangSmith API saw chat_turn: {'YES' if ok_api else 'NO'}")
    print(f"Eval row has trace id:       {'YES' if ok_db else 'NO'}")
    return 0 if (ok_api or ok_db) else 2


if __name__ == "__main__":
    raise SystemExit(main())
