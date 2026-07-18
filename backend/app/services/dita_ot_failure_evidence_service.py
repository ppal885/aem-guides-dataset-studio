"""Failure evidence lookup for DITA-OT publishing runs.

When PDF/HTML5 publishing fails, stderr alone is not enough for QA. This module
searches upstream DITA-OT issue evidence and AEM Guides Jira signals using the
same query so chat and MCP callers receive comparable triage hints.
"""

from __future__ import annotations

import re
from typing import Any


def _clean_text(value: str, *, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:limit].rstrip()


def _failure_snippet(publish: dict[str, Any]) -> str:
    parts: list[str] = []
    for fmt, payload in publish.items():
        if not isinstance(payload, dict) or payload.get("ok"):
            continue
        stderr = _clean_text(str(payload.get("stderr") or ""))
        stdout = _clean_text(str(payload.get("stdout") or ""))
        message = stderr or stdout
        if message:
            parts.append(f"{fmt}: {message}")
    return _clean_text(" ".join(parts), limit=1200)


def build_dita_ot_failure_query(
    *,
    prompt: str,
    formats: list[str],
    detected_constructs: list[str],
    publish: dict[str, Any],
) -> str:
    constructs = ", ".join(detected_constructs or [])
    format_text = ", ".join(formats or [])
    failure = _failure_snippet(publish)
    query_parts = [
        "DITA-OT publishing failure",
        f"formats: {format_text}" if format_text else "",
        f"constructs: {constructs}" if constructs else "",
        f"user scenario: {_clean_text(prompt, limit=500)}" if prompt else "",
        f"stderr stdout: {failure}" if failure else "",
    ]
    return _clean_text(" ".join(part for part in query_parts if part), limit=1800)


def lookup_dita_ot_failure_evidence(
    *,
    prompt: str,
    formats: list[str],
    detected_constructs: list[str],
    publish: dict[str, Any],
    tenant_id: str = "kone",
    max_results: int = 5,
) -> dict[str, Any]:
    """Return related DITA-OT GitHub and AEM Guides Jira evidence for a failed run."""
    query = build_dita_ot_failure_query(
        prompt=prompt,
        formats=formats,
        detected_constructs=detected_constructs,
        publish=publish,
    )
    result: dict[str, Any] = {
        "query": query,
        "trigger": "dita_ot_publish_failure",
        "dita_ot_github_issues": [],
        "jira_issues": [],
        "jira_source": "unavailable",
        "errors": [],
        "guidance": [
            "Compare related issue symptoms with this map, DITAVAL/filter usage, DITA-OT version, and generated temp files.",
            "Treat matches as risk signals, not proof; reproduce with the generated ZIP and DITA-OT command before filing or linking a bug.",
        ],
    }
    try:
        from app.services.dita_ot_github_rag_service import retrieve_dita_ot_github_for_query

        result["dita_ot_github_issues"] = retrieve_dita_ot_github_for_query(query, k=max_results) or []
    except Exception as exc:  # noqa: BLE001 - evidence lookup must never hide publish failure
        result["errors"].append(f"DITA-OT GitHub issue lookup failed: {exc}")

    try:
        from app.services.jira_chat_search_service import search_related_jira_issues

        jira_result = search_related_jira_issues(query, tenant_id=tenant_id, max_results=max_results)
        result["jira_issues"] = jira_result.get("issues") or []
        result["jira_source"] = jira_result.get("source") or "unavailable"
        result["jira_message"] = jira_result.get("message") or ""
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"AEM Guides Jira lookup failed: {exc}")

    return result
