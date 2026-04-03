"""HTTP client for Dataset Studio API (JSON and SSE chat streams)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from mcp_api_adapter.config import Settings, get_settings


def _iter_sse_json_objects(response: httpx.Response) -> Iterator[dict[str, Any]]:
    """Parse Server-Sent Events lines into JSON objects (chat API)."""
    for line in response.iter_lines():
        if not line:
            continue
        raw = line.strip()
        if not raw.startswith("data:"):
            continue
        payload = raw[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


class DatasetStudioApiClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._base = self.settings.base_url
        self._timeout = httpx.Timeout(self.settings.timeout_seconds)
        self._client = httpx.Client(timeout=self._timeout, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def _json_headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/json",
            **self.settings.extra_headers,
        }
        if self.settings.bearer_token:
            h["Authorization"] = f"Bearer {self.settings.bearer_token}"
        return h

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        url = f"{self._base}{path}"
        headers = self._json_headers()
        if json_body is not None:
            headers = {**headers, "Content-Type": "application/json"}
        try:
            response = self._client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=headers,
            )
        except httpx.TimeoutException:
            return {"ok": False, "status_code": 0, "detail": "Request timed out"}
        except httpx.RequestError as exc:
            return {"ok": False, "status_code": 0, "detail": str(exc)}
        return self._parse_json_response(response)

    def _parse_json_response(self, response: httpx.Response) -> Any:
        if response.status_code < 400:
            if not response.content:
                return {}
            try:
                return response.json()
            except json.JSONDecodeError:
                return {"raw": (response.text or "")[:5000]}

        return {
            "ok": False,
            "status_code": response.status_code,
            "detail": _extract_error_detail(response),
        }

    def post_sse_chat(
        self,
        path: str,
        json_body: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        headers = {
            **self._json_headers(),
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        assistant_chunks: list[str] = []
        tool_events: list[dict[str, Any]] = []
        errors: list[str] = []
        event_count = 0
        try:
            with self._client.stream(
                "POST",
                url,
                json=json_body,
                headers=headers,
                timeout=self._timeout,
            ) as response:
                if response.status_code >= 400:
                    raw = response.read()
                    detail: Any
                    try:
                        data = json.loads(raw.decode("utf-8", errors="replace"))
                        if isinstance(data, dict) and "detail" in data:
                            detail = data["detail"]
                        else:
                            detail = data
                    except Exception:
                        detail = raw.decode("utf-8", errors="replace")[:2000]
                    return {
                        "ok": False,
                        "status_code": response.status_code,
                        "detail": detail,
                    }

                for obj in _iter_sse_json_objects(response):
                    event_count += 1
                    etype = obj.get("type")
                    if etype == "chunk":
                        assistant_chunks.append(str(obj.get("content") or ""))
                    elif etype in ("tool", "tool_start", "tool_use"):
                        tool_events.append(obj)
                    elif etype == "error":
                        errors.append(str(obj.get("message") or obj))

        except httpx.TimeoutException:
            return {
                "ok": False,
                "status_code": 0,
                "detail": "SSE stream timed out",
                "partial_assistant_text": "".join(assistant_chunks)[:8000],
            }
        except httpx.RequestError as exc:
            return {"ok": False, "status_code": 0, "detail": str(exc)}

        full_text = "".join(assistant_chunks)
        max_chars = self.settings.sse_max_assistant_chars
        truncated = len(full_text) > max_chars
        if truncated:
            full_text = full_text[:max_chars]

        return {
            "ok": True,
            "assistant_text": full_text,
            "truncated": truncated,
            "tool_events": tool_events[:50],
            "errors": errors,
            "event_count": event_count,
        }

    def iter_chat_sse(
        self,
        path: str,
        json_body: dict[str, Any],
    ) -> Iterator[dict[str, Any]]:
        """Stream chat SSE events one at a time (for real-time terminals).

        Yields the same event dicts the API sends (``chunk``, ``done``, ``error``, ``tool``, …).
        On HTTP error, yields a single synthetic event::
            ``{"type": "http_error", "status_code": int, "detail": ...}``
        """
        url = f"{self._base}{path}"
        headers = {
            **self._json_headers(),
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        try:
            with self._client.stream(
                "POST",
                url,
                json=json_body,
                headers=headers,
                timeout=self._timeout,
            ) as response:
                if response.status_code >= 400:
                    raw = response.read()
                    try:
                        data = json.loads(raw.decode("utf-8", errors="replace"))
                        detail: Any = data.get("detail", data) if isinstance(data, dict) else data
                    except Exception:
                        detail = raw.decode("utf-8", errors="replace")[:2000]
                    yield {
                        "type": "http_error",
                        "status_code": response.status_code,
                        "detail": detail,
                    }
                    return

                yield from _iter_sse_json_objects(response)

        except httpx.TimeoutException:
            yield {"type": "error", "message": "Request timed out"}
        except httpx.RequestError as exc:
            yield {"type": "error", "message": str(exc)}


def _extract_error_detail(response: httpx.Response) -> Any:
    try:
        data = response.json()
        if isinstance(data, dict) and "detail" in data:
            return data["detail"]
        return data
    except Exception:
        return (response.text or "")[:2000]
