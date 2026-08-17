"""Pre-UAC product context — explain the Guides feature area before acceptance criteria."""

from __future__ import annotations

import re
from typing import Any

from app.core.schemas_test_plan_pipeline import PreUacProductBrief, TicketBrief
from app.services.draft_test_plan_content_service import dedupe_clarifications
from app.services.ticket_workflow_profile_service import render_workflow_markdown

_TOPIC_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "baseline",
        "title": "AEM Guides Baseline",
        "keywords": (
            "baseline",
            "baseline table",
            "baseline v2",
            "baseline panel",
            "version comment",
            "baseline dashboard",
            "baseline export",
            "baseline rebuild",
        ),
        "entry_points": (
            "Web Editor -> Baseline panel (baseline v2)",
            "Map console / Assets UI -> Baselines page (legacy dashboard)",
            "REST API under /bin/guides/v1/baseline/*",
        ),
        "plain_intro": (
            "A baseline is a named snapshot of map/topic versions used for publishing, comparison, "
            "and release governance. The Baseline table lists topics/assets in that snapshot with "
            "fixed columns (title, version, labels, etc.)."
        ),
        "known_behavior": (
            "Authors create a baseline from a DITA map to freeze topic versions for a release or audit.",
            "The Baseline table lists each topic/asset in the snapshot with standard columns (title, version, labels, etc.).",
            "Baselines support UI filtering and CSV export; the visible column set is fixed in current product behavior.",
            "Version comment is an OOTB topic property; it is editable in topic metadata but is not a Baseline table column today.",
            "Static baselines pin explicit versions; dynamic baselines resolve versions by date/label rules at rebuild time.",
            "REST baseline/detail returns paginated baseline contents and supports label-based filtering for API validation.",
        ),
        "rag_query_lines": (
            "AEM Guides baseline table UI columns filter sort CSV export",
            "Work with baseline version label snapshot publishing governance",
            "Web Editor baseline panel baseline v2 dashboard",
            "Version comment property topic metadata baseline",
            "/bin/guides/v1/baseline/detail paginated filter export",
        ),
        "evidence_boost_keywords": (
            "baseline table",
            "work with baseline",
            "baseline panel",
            "csv export",
            "filter",
            "sort",
            "version comment",
            "version label",
            "paginated",
            "baseline/detail",
            "static baseline",
            "dynamic baseline",
            "web-editor-baseline",
        ),
    },
    {
        "id": "asset_status",
        "title": "Asset Status API",
        "keywords": ("/assets/status", "asset status", "guides:assetStatus", "post-processing"),
        "entry_points": ("REST POST/GET /bin/guides/v1/assets/status"),
        "plain_intro": (
            "The Asset Status API starts an async job to read post-processing status for DAM paths "
            "and returns per-asset status when polling completes."
        ),
        "known_behavior": (
            "POST starts an async asset-status job; GET polls job status until completion or failure.",
            "Request body carries DAM paths; responses report post-processing state per asset.",
        ),
        "rag_query_lines": (
            "AEM Guides Asset Status REST API /bin/guides/v1/assets/status",
            "guides:assetStatus post-processing polling job",
        ),
        "evidence_boost_keywords": (
            "/assets/status",
            "asset status",
            "post-processing",
            "polling",
            "job",
        ),
    },
    {
        "id": "publishing",
        "title": "AEM Guides Publishing",
        "keywords": ("publish", "publishing", "output preset", "native pdf", "dita-ot", "html5"),
        "entry_points": ("Map console publishing", "Output presets", "Native PDF / DITA-OT"),
        "plain_intro": "Publishing transforms DITA maps/topics into customer outputs (PDF, HTML, Sites, etc.).",
        "known_behavior": (
            "Publishing uses output presets and may honor a selected baseline for version selection.",
        ),
        "rag_query_lines": ("AEM Guides publishing output preset baseline publish workflow",),
        "evidence_boost_keywords": ("output preset", "publish", "baseline for publishing"),
    },
    {
        "id": "web_editor",
        "title": "AEM Guides Web Editor",
        "keywords": ("web editor", "editor", "authoring", "folder profile", "ui_config"),
        "entry_points": ("Guides editor UI on Author/Publish"),
        "plain_intro": "The Web Editor is the primary authoring surface for maps, topics, and metadata.",
        "known_behavior": (
            "Authors edit maps/topics and metadata (including version comment) in the Web Editor.",
        ),
        "rag_query_lines": ("AEM Guides Web Editor authoring metadata properties",),
        "evidence_boost_keywords": ("web editor", "authoring", "metadata", "properties"),
    },
)

_EVIDENCE_KEYWORDS = re.compile(
    r"\b(baseline|asset status|publishing|web editor|version comment|baseline table)\b",
    re.I,
)
_OPENAPI_JSON_RE = re.compile(r'\{\s*"type"\s*:\s*"object"')
_CSS_BASELINE_FALSE_POSITIVE = re.compile(r"vertical-align\s*:\s*baseline")
_OFF_TOPIC_API_FOR_BASELINE = re.compile(
    r"(translation api|reports api|guides-translation|guides-reports|metadataexport|"
    r"createtranslationproject|reportrequest|urls\.primaryname=translation|urls\.primaryname=reports|"
    r"publishing api|urls\.primaryname=publishing)",
    re.I,
)
_DTO_NAME_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9]+(?:Request|Response|Export|Creation|Rebuild)?Dto)\b"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_MIN_DOCUMENTED_SNIPPET_SCORE = 5


def detect_product_topics(text: str) -> list[dict[str, Any]]:
    lowered = (text or "").lower()
    hits: list[tuple[int, dict[str, Any]]] = []
    for topic in _TOPIC_CATALOG:
        score = sum(1 for kw in topic["keywords"] if kw in lowered)
        if score:
            hits.append((score, topic))
    hits.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in hits[:3]]


def _issue_text(packet: dict[str, Any], brief: TicketBrief) -> str:
    issue = packet.get("issue") or {}
    parts = [
        brief.summary,
        brief.current_behavior,
        brief.expected_behavior,
        brief.component,
        brief.scope_hint,
        str(issue.get("description") or ""),
        " ".join(brief.labels),
        " ".join(str(c) for c in (issue.get("components") or [])),
    ]
    return "\n".join(p for p in parts if p)


def _normalize_snippet(doc: dict[str, Any], *, source: str) -> dict[str, str]:
    return {
        "source": source,
        "title": str(doc.get("title") or "Product behavior"),
        "url": str(doc.get("source_url") or doc.get("canonical_url") or doc.get("url") or ""),
        "snippet": str(doc.get("snippet") or "")[:800],
    }


def _collect_packet_evidence_snippets(packet: dict[str, Any], topic_ids: set[str]) -> list[dict[str, str]]:
    snippets: list[dict[str, str]] = []
    for doc in packet.get("experience_league_evidence") or []:
        if not isinstance(doc, dict) or doc.get("skipped"):
            continue
        blob = f"{doc.get('title', '')} {doc.get('snippet', '')}".lower()
        if not _evidence_matches_topics(blob, topic_ids):
            continue
        snippets.append(_normalize_snippet(doc, source="experience_league"))
    learned = packet.get("learned_behavior_evidence") or {}
    for item in learned.get("results") or []:
        if not isinstance(item, dict):
            continue
        blob = str(item.get("snippet") or item.get("title") or "").lower()
        if not _evidence_matches_topics(blob, topic_ids):
            continue
        snippets.append(_normalize_snippet(item, source="learned_behavior"))
    return snippets


def _build_topic_rag_query(topics: list[dict[str, Any]], ticket_text: str) -> str:
    parts: list[str] = []
    for topic in topics[:2]:
        parts.extend(topic.get("rag_query_lines") or ())
    if ticket_text.strip():
        parts.append(ticket_text.strip()[:600])
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return "\n".join(ordered)


def _fetch_supplemental_topic_evidence(
    topics: list[dict[str, Any]],
    ticket_text: str,
    *,
    k: int = 8,
    mcp_fast: bool = False,
) -> list[dict[str, str]]:
    """Topic-focused semantic retrieval beyond the generic Jira RAG packet."""
    if mcp_fast or not topics:
        return []
    query = _build_topic_rag_query(topics, ticket_text)
    if not query.strip():
        return []
    try:
        from app.services.doc_retriever_service import retrieve_relevant_docs_with_diagnostics

        payload = retrieve_relevant_docs_with_diagnostics(
            query,
            k=max(k * 2, 10),
            allowed_host_suffixes=("experienceleague.adobe.com", "adobeaemcloud.com"),
        )
    except Exception:
        return []
    out: list[dict[str, str]] = []
    for doc in payload.get("results") or []:
        if not isinstance(doc, dict):
            continue
        out.append(_normalize_snippet(doc, source="topic_rag"))
    return out


def _is_off_topic_for_baseline(snippet: dict[str, str]) -> bool:
    text = f"{snippet.get('title', '')} {snippet.get('snippet', '')} {snippet.get('url', '')}".lower()
    if "guides-baseline" in text or "urls.primaryname=baseline" in text:
        return False
    if "work with baseline" in text or "baseline table" in text or "baseline panel" in text:
        return False
    if "documented purpose" in text and "baseline" in text:
        return False
    return bool(_OFF_TOPIC_API_FOR_BASELINE.search(text))


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\r", " ")).strip()


def _strip_trailing_source_urls(text: str) -> str:
    return re.sub(r"\s*Source:\s*https?://\S+", "", text, flags=re.I).strip()


def _summarize_openapi_snippet(title: str, snippet: str, url: str) -> str:
    dto_match = _DTO_NAME_RE.search(f"{title} {snippet}")
    dto_name = dto_match.group(1) if dto_match else "API schema"
    purpose = "REST contract checks"
    lowered = f"{title} {snippet} {url}".lower()
    if "export" in lowered:
        purpose = "baseline export / filter contract checks"
    elif "detail" in lowered or "paginated" in lowered:
        purpose = "baseline detail / pagination contract checks"
    elif "creation" in lowered or "rebuild" in lowered:
        purpose = "baseline create/rebuild contract checks"
    return f"OpenAPI schema for {dto_name} — use for {purpose}."


def clean_evidence_snippet_text(snippet: dict[str, str], *, max_chars: int = 280) -> str:
    """Turn raw RAG/scrape chunks into readable Pre-UAC bullets."""
    title = _collapse_whitespace(snippet.get("title") or "")
    body = _strip_trailing_source_urls(_collapse_whitespace(snippet.get("snippet") or ""))
    url = (snippet.get("url") or "").strip()

    if _OPENAPI_JSON_RE.search(body) or (
        body.startswith("{") and '"properties"' in body
    ):
        return _summarize_openapi_snippet(title, body, url)

    if title and body.lower().startswith(title.lower()):
        body = body[len(title) :].lstrip(" .-|")

    sentences: list[str] = []
    for part in _SENTENCE_SPLIT_RE.split(body):
        cleaned = _collapse_whitespace(part)
        if len(cleaned) < 20:
            continue
        if _CSS_BASELINE_FALSE_POSITIVE.search(cleaned):
            continue
        if cleaned.lower().startswith("source api:"):
            continue
        sentences.append(cleaned)
        joined = " ".join(sentences)
        if len(joined) >= max_chars:
            break

    summary = " ".join(sentences) if sentences else body[:max_chars]
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3].rsplit(" ", 1)[0] + "..."
    if title and title not in summary:
        return f"{title}: {summary}"
    return summary


def score_evidence_snippet(snippet: dict[str, str], primary: dict[str, Any] | None) -> int:
    """Rank RAG snippets: UI/product prose up; raw OpenAPI JSON and false positives down."""
    text = f"{snippet.get('title', '')} {snippet.get('snippet', '')} {snippet.get('url', '')}".lower()
    score = 0

    if snippet.get("source") == "experience_league":
        score += 10
    if snippet.get("source") == "topic_rag":
        score += 6

    if primary:
        for kw in primary.get("evidence_boost_keywords") or ():
            if kw in text:
                score += 12

    if _OPENAPI_JSON_RE.search(snippet.get("snippet", "")):
        score -= 30
    if _CSS_BASELINE_FALSE_POSITIVE.search(text):
        score -= 60
    if primary and primary.get("id") == "baseline" and _is_off_topic_for_baseline(snippet):
        score -= 90
    if "translation api" in text and "baseline" not in text:
        score -= 45
    if primary and primary.get("id") == "baseline":
        if "documented purpose" in text and "baseline" in text:
            score += 18
        if "baseline table" in text or "work with baseline" in text:
            score += 20
        if re.search(r"\bcolumn(s)?\b", text) and "baseline" in text and not _OFF_TOPIC_API_FOR_BASELINE.search(text):
            score += 10
        if "guides-baseline" in text or "urls.primaryname=baseline" in text:
            score += 8

    if len(snippet.get("snippet", "")) < 40:
        score -= 15

    return score


def _rank_and_select_snippets(
    snippets: list[dict[str, str]],
    primary: dict[str, Any] | None,
    *,
    limit: int = 5,
) -> list[dict[str, str]]:
    deduped = _dedupe_sources(snippets)
    ranked = sorted(
        deduped,
        key=lambda s: score_evidence_snippet(s, primary),
        reverse=True,
    )
    selected: list[dict[str, str]] = []
    seen_text: set[str] = set()
    for item in ranked:
        line = item.get("snippet", "").strip()
        if not line:
            continue
        if primary and primary.get("id") == "baseline" and _is_off_topic_for_baseline(item):
            continue
        if score_evidence_snippet(item, primary) < _MIN_DOCUMENTED_SNIPPET_SCORE:
            continue
        key = line[:120]
        if key in seen_text:
            continue
        seen_text.add(key)
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _evidence_matches_topics(blob: str, topic_ids: set[str]) -> bool:
    if not topic_ids:
        return bool(_EVIDENCE_KEYWORDS.search(blob))
    for topic in _TOPIC_CATALOG:
        if topic["id"] not in topic_ids:
            continue
        if any(kw in blob for kw in topic["keywords"]):
            return True
    return False


def _dedupe_sources(snippets: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for s in snippets:
        url = (s.get("url") or "").strip()
        key = url or s.get("snippet", "")[:80] or s.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _format_documented_line(snippet: dict[str, str]) -> str:
    url = snippet.get("url") or ""
    summary = clean_evidence_snippet_text(snippet)
    if url and url not in summary:
        return f"{summary} Source: {url}"
    return summary


def build_pre_uac_clarifications(
    topics: list[dict[str, Any]],
    brief: TicketBrief,
    ranked_snippets: list[dict[str, str]],
    workflow: Any | None = None,
) -> list[str]:
    clarifications: list[str] = []
    primary = topics[0]["title"] if topics else "this feature area"
    category = getattr(workflow, "ticket_category", "") if workflow else ""

    if category == "feature_request":
        if not brief.expected_behavior.strip():
            clarifications.append(
                f"Agree expected behavior for {primary} before UAC sign-off (feature/enhancement request)."
            )
        clarifications.extend(list(getattr(workflow, "workflow_clarifications", []) or [])[:4])
    elif category == "bug":
        clarifications.extend(list(getattr(workflow, "workflow_clarifications", []) or [])[:4])
        if not brief.current_behavior.strip():
            clarifications.append("Confirm customer repro steps and Actual Result on Author before writing AC.")
    else:
        if not brief.expected_behavior.strip():
            clarifications.append(
                f"Agree expected behavior for {primary} before UAC sign-off."
            )
    if "baseline" in {t["id"] for t in topics} and category != "bug":
        clarifications.extend(
            [
                "Which Baseline UI is in scope: Web Editor baseline v2 panel, legacy dashboard, or both?",
                "Should Version comment appear as a new column, custom property slot, or export-only field?",
                "Confirm filter/sort/CSV export must include the new column if added.",
            ]
        )
    ui_evidence = [
        s
        for s in ranked_snippets
        if any(kw in f"{s.get('title','')} {s.get('snippet','')}".lower() for kw in ("baseline table", "work with baseline", "column"))
    ]
    if not ui_evidence and "baseline" in {t["id"] for t in topics}:
        clarifications.append(
            "RAG did not surface strong Baseline table UI docs — validate column/filter/export behavior manually on Author before UAC."
        )
    elif not ranked_snippets:
        clarifications.append(
            f"Pull official Experience League / Swagger evidence for {primary} before writing test oracles."
        )
    return dedupe_clarifications(clarifications)


def build_pre_uac_product_brief(
    packet: dict[str, Any],
    brief: TicketBrief,
    workflow: Any | None = None,
) -> PreUacProductBrief:
    """Build Pre-UAC product context from RAG packet + ticket brief + topic-focused retrieval."""
    text = _issue_text(packet, brief)
    topics = detect_product_topics(text.lower())
    topic_ids = {t["id"] for t in topics}
    primary = topics[0] if topics else None
    mcp_fast = bool(packet.get("mcp_fast_mode"))

    packet_snippets = _collect_packet_evidence_snippets(packet, topic_ids)
    supplemental = _fetch_supplemental_topic_evidence(topics, text, mcp_fast=mcp_fast)
    merged = packet_snippets + supplemental
    ranked = _rank_and_select_snippets(merged, primary, limit=5)

    sources = _dedupe_sources(
        [{"title": s["title"], "url": s["url"]} for s in ranked if s.get("url") or s.get("title")]
    )

    how_it_works: list[str] = []
    if primary:
        how_it_works.extend(f"Entry: {ep}" for ep in primary["entry_points"])

    known_behavior = list(primary.get("known_behavior") or ()) if primary else []
    documented = [_format_documented_line(s) for s in ranked]

    ticket_context = brief.current_behavior or brief.summary
    if brief.summary and brief.current_behavior and brief.summary not in brief.current_behavior:
        ticket_context = f"{brief.summary}\n\nCurrent/limitation: {brief.current_behavior[:1200]}"

    return PreUacProductBrief(
        primary_product_area=primary["title"] if primary else "AEM Guides (general)",
        topic_ids=[t["id"] for t in topics],
        summary_plain_english=primary["plain_intro"] if primary else "Review Jira summary and official docs before UAC.",
        how_it_works=how_it_works[:6],
        known_product_behavior=known_behavior[:8],
        documented_behavior=documented[:6],
        ticket_specific_context=ticket_context[:2000],
        official_sources=sources[:6],
        pre_uac_clarifications=build_pre_uac_clarifications(topics, brief, ranked, workflow),
    )


def render_pre_uac_markdown(brief: PreUacProductBrief, workflow: Any | None = None) -> str:
    from app.services.ticket_workflow_profile_service import render_workflow_markdown

    lines = [
        "## 0. Pre-UAC — product context (read first)",
        "",
    ]
    if workflow is not None:
        lines.append(render_workflow_markdown(workflow))
    lines.extend(
        [
            f"**Product area:** {brief.primary_product_area}",
            "",
            "### What this feature is",
            "",
            brief.summary_plain_english,
            "",
        ]
    )
    if brief.how_it_works:
        lines.extend(["### How users reach it", ""])
        lines.extend(f"- {item}" for item in brief.how_it_works)
        lines.append("")
    if brief.known_product_behavior:
        lines.extend(["### Known product behavior (curated)", ""])
        for idx, item in enumerate(brief.known_product_behavior, start=1):
            lines.append(f"- **KB-{idx}:** {item}")
        lines.append("")
    if brief.documented_behavior:
        lines.extend(["### Documented behavior (RAG — ranked Experience League / API)", ""])
        for idx, item in enumerate(brief.documented_behavior, start=1):
            lines.append(f"- **DB-{idx}:** {item}")
        lines.append("")
    if brief.ticket_specific_context:
        lines.extend(["### What this ticket is asking for", ""])
        lines.append(brief.ticket_specific_context[:1500])
        lines.append("")
    if brief.pre_uac_clarifications:
        lines.extend(["### Pre-UAC clarifications (PM / QA before acceptance criteria)", ""])
        for idx, q in enumerate(brief.pre_uac_clarifications, start=1):
            lines.append(f"- **PU-{idx}:** {q}")
        lines.append("")
    if brief.official_sources:
        lines.extend(["### Official sources", ""])
        for src in brief.official_sources:
            title = src.get("title") or "Source"
            url = src.get("url") or ""
            lines.append(f"- [{title}]({url})" if url else f"- {title}")
        lines.append("")
    return "\n".join(lines)
