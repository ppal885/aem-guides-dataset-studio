#!/usr/bin/env python3
"""Interactive terminal chat with live SSE streaming (same API as the web UI).

Reads from stdin, POSTs to ``/api/v1/chat/sessions/.../messages``, prints assistant
tokens as they arrive.

Usage (repo root, backend running):

  python scripts/chat_realtime.py

Optional:

  python scripts/chat_realtime.py --session <uuid>   # continue an existing session

Environment (same as ``mcp_api_adapter``):

  DATASET_STUDIO_API_BASE_URL   default http://127.0.0.1:8001
  DATASET_STUDIO_API_BEARER_TOKEN or API_BEARER_TOKEN

Commands (input line):

  /exit, /quit, /q     — stop
  /new                 — start a new chat session
  /session             — print current session id
  /regenerate, /re     — stream a new reply for the last user message

On Windows, prefer ``set PYTHONUTF8=1`` for reliable Unicode in the console.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_api_adapter.config import get_settings  # noqa: E402
from mcp_api_adapter.http_client import DatasetStudioApiClient  # noqa: E402


def _print_stream(client: DatasetStudioApiClient, path: str, json_body: dict) -> None:
    sys.stdout.write("Assistant: ")
    sys.stdout.flush()
    for ev in client.iter_chat_sse(path, json_body):
        t = ev.get("type")
        if t == "chunk":
            sys.stdout.write(str(ev.get("content") or ""))
            sys.stdout.flush()
        elif t == "done":
            sys.stdout.write("\n")
            sys.stdout.flush()
        elif t == "http_error":
            sys.stdout.write(
                f"\n[HTTP {ev.get('status_code')}] {ev.get('detail')}\n"
            )
            sys.stdout.flush()
        elif t == "error":
            sys.stdout.write(f"\n[Error] {ev.get('message')}\n")
            sys.stdout.flush()
        elif t in ("tool", "tool_start", "tool_use"):
            name = ev.get("name") or ""
            extra = f" {name}" if name else ""
            sys.stdout.write(f"\n[{t}{extra}]\nAssistant: ")
            sys.stdout.flush()
        elif t == "tool_result":
            sys.stdout.write("\n[tool_result]\nAssistant: ")
            sys.stdout.flush()


def _create_session(client: DatasetStudioApiClient) -> str:
    out = client.request_json("POST", "/api/v1/chat/sessions", json_body={})
    if isinstance(out, dict) and out.get("ok") is False:
        raise RuntimeError(f"Create session failed: {out}")
    sid = out.get("session_id") if isinstance(out, dict) else None
    if not sid:
        raise RuntimeError(f"Unexpected response: {out}")
    return str(sid)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream chat against Dataset Studio API")
    parser.add_argument(
        "--session",
        help="Existing chat session UUID (otherwise a new session is created)",
    )
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    settings = get_settings()
    print(f"API: {settings.base_url}", file=sys.stderr)
    client = DatasetStudioApiClient(settings)

    try:
        session_id = args.session or _create_session(client)
        if not args.session:
            print(f"New session: {session_id}", file=sys.stderr)
        print("Type a message. Commands: /exit /new /session /regenerate", file=sys.stderr)

        while True:
            try:
                line = input("You: ")
            except EOFError:
                print(file=sys.stderr)
                break
            text = (line or "").strip()
            if not text:
                continue
            low = text.lower()
            if low in ("/exit", "/quit", "/q"):
                break
            if low == "/new":
                session_id = _create_session(client)
                print(f"New session: {session_id}", file=sys.stderr)
                continue
            if low == "/session":
                print(session_id, file=sys.stderr)
                continue
            if low in ("/regenerate", "/re"):
                path = f"/api/v1/chat/sessions/{session_id}/regenerate"
                _print_stream(client, path, {})
                continue

            path = f"/api/v1/chat/sessions/{session_id}/messages"
            _print_stream(client, path, {"content": text})

    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
