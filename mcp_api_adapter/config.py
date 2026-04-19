"""Environment-based settings for the REST MCP adapter."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv_optional() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parent.parent
    for env_path in (root / ".env", root / "backend" / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=False, encoding="utf-8-sig")


@dataclass(frozen=True)
class Settings:
    base_url: str
    bearer_token: str | None
    timeout_seconds: float
    extra_headers: dict[str, str]
    sse_max_assistant_chars: int


def get_settings() -> Settings:
    load_dotenv_optional()
    base = (os.getenv("DATASET_STUDIO_API_BASE_URL") or "http://127.0.0.1:8001").rstrip("/")
    raw_token = (os.getenv("DATASET_STUDIO_API_BEARER_TOKEN") or os.getenv("API_BEARER_TOKEN") or "").strip()
    bearer_token = raw_token or None
    timeout_seconds = float(os.getenv("DATASET_STUDIO_API_TIMEOUT_SECONDS") or "120")
    sse_max = int(os.getenv("DATASET_STUDIO_API_SSE_MAX_CHARS") or "120000")

    extra: dict[str, str] = {}
    raw_headers = (os.getenv("DATASET_STUDIO_API_EXTRA_HEADERS_JSON") or "").strip()
    if raw_headers:
        try:
            parsed = json.loads(raw_headers)
            if isinstance(parsed, dict):
                extra = {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            pass

    return Settings(
        base_url=base,
        bearer_token=bearer_token,
        timeout_seconds=timeout_seconds,
        extra_headers=extra,
        sse_max_assistant_chars=sse_max,
    )
