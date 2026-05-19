"""OpenAI-compatible chat completions for GQS_LLM_* (Azure, OpenAI, local gateways)."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import httpx

from app.services.gqs_integration_config import gqs_llm_credentials


def _extract_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


async def gqs_chat_completion_json(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    cred = gqs_llm_credentials()
    key = os.getenv("GQS_LLM_API_KEY", "").strip()
    model = os.getenv("GQS_LLM_MODEL", "").strip()
    if not key or not model:
        raise ValueError("GQS_LLM_API_KEY and GQS_LLM_MODEL must be set for GQS OpenAI-compatible calls.")
    base = (cred.get("base_url") or os.getenv("OPENAI_API_BASE", "") or "https://api.openai.com/v1").rstrip("/")
    timeout = cred.get("timeout_secs") or 120.0
    url = f"{base}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": int(max_tokens),
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("LLM response missing choices")
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    parsed = _extract_json(str(content))
    if parsed is None:
        raise ValueError("No valid JSON in LLM response")
    return parsed


async def gqs_chat_completion_text(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 800,
) -> str:
    cred = gqs_llm_credentials()
    key = os.getenv("GQS_LLM_API_KEY", "").strip()
    model = os.getenv("GQS_LLM_MODEL", "").strip()
    if not key or not model:
        raise ValueError("GQS_LLM_API_KEY and GQS_LLM_MODEL must be set.")
    base = (cred.get("base_url") or os.getenv("OPENAI_API_BASE", "") or "https://api.openai.com/v1").rstrip("/")
    timeout = cred.get("timeout_secs") or 120.0
    url = f"{base}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": int(max_tokens),
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return str(msg.get("content") or "").strip()
