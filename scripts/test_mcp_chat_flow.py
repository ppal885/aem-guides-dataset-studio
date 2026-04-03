#!/usr/bin/env python3
"""Exercise chat via the same HTTP paths as mcp_api_adapter (stdio MCP).

Prerequisites:
  - FastAPI backend running (default http://127.0.0.1:8000)
  - LLM configured (same as UI chat)

Usage (from repo root):
  python scripts/test_mcp_chat_flow.py
  set DATASET_STUDIO_API_BASE_URL / DATASET_STUDIO_API_BEARER_TOKEN if needed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Repo root on path for `mcp_api_adapter`
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_api_adapter.config import get_settings  # noqa: E402
from mcp_api_adapter.http_client import DatasetStudioApiClient  # noqa: E402


def main() -> int:
    settings = get_settings()
    print("API base:", settings.base_url)
    print("Bearer set:", bool(settings.bearer_token))
    client = DatasetStudioApiClient(settings)

    created = client.request_json("POST", "/api/v1/chat/sessions", json_body={})
    if isinstance(created, dict) and created.get("ok") is False:
        print("FAIL create session:", json.dumps(created, indent=2))
        client.close()
        return 1
    session_id = created.get("session_id") if isinstance(created, dict) else None
    if not session_id:
        print("FAIL unexpected create response:", created)
        client.close()
        return 1
    print("session_id:", session_id)

    r1 = client.post_sse_chat(
        f"/api/v1/chat/sessions/{session_id}/messages",
        {"content": "Reply with exactly one word: ALPHA"},
    )
    print("\n--- send_chat_message ---")
    print(json.dumps(r1, indent=2, default=str)[:4000])
    if not r1.get("ok"):
        client.close()
        return 1
    if r1.get("errors"):
        print(
            "WARN: SSE error events present:",
            r1.get("errors"),
            "\n      If you see 'not enough values to unpack', restart the backend after pulling "
            "the latest llm_service streaming fix (Anthropic/Bedrock cleanup after text).",
        )

    r2 = client.post_sse_chat(
        f"/api/v1/chat/sessions/{session_id}/messages",
        {"content": "Reply with exactly one word: BETA"},
    )
    print("\n--- second message ---")
    print(json.dumps(r2, indent=2, default=str)[:4000])
    if not r2.get("ok"):
        client.close()
        return 1

    regen = client.post_sse_chat(
        f"/api/v1/chat/sessions/{session_id}/regenerate",
        {},
    )
    print("\n--- regenerate_chat_response ---")
    print(json.dumps(regen, indent=2, default=str)[:4000])
    if not regen.get("ok"):
        detail = regen.get("detail")
        if regen.get("status_code") == 404 and detail == "Not Found":
            print(
                "\nNOTE: Regenerate returned 404 — your API process is likely an older build "
                "(no /chat/sessions/{id}/regenerate in OpenAPI). Restart the backend to load "
                "the current routes."
            )
        else:
            client.close()
            return 1

    hist = client.request_json("GET", f"/api/v1/chat/sessions/{session_id}")
    print("\n--- GET session (history) ---")
    if isinstance(hist, dict) and hist.get("messages"):
        print("message count:", len(hist["messages"]))
        for m in hist["messages"][-4:]:
            role = m.get("role")
            content = (m.get("content") or "")[:120]
            print(f"  {role}: {content!r}")
    else:
        print(json.dumps(hist, indent=2, default=str)[:2000])

    client.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
