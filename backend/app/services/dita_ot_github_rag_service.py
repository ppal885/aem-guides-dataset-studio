"""Index and retrieve dita-ot/dita-ot GitHub issues for DITA Open Toolkit–focused RAG.

Fetches only from the fixed REST path for the **public** repo ``/repos/dita-ot/dita-ot/issues`` (no
user-controlled URLs, no auth required). Optional ``GITHUB_TOKEN`` / ``GH_TOKEN`` only helps avoid
GitHub rate limits on large index runs.

A small set of **curated reference issues** is loaded from ``config/dita_ot_github_reference_issues.json``
(override path with ``DITA_OT_GITHUB_REFERENCE_JSON``). Entries are merged into retrieval for toolkit-like
queries so chat RAG has a baseline without indexing the full issues list.
"""

from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import httpx

from app.core.structured_logging import get_structured_logger
from app.services.embedding_service import embed_query, embed_texts_batched, is_embedding_available
from app.services.prompt_router_service import (
    _DITA_OT_ENGINE_PATTERN,
    is_native_pdf_dita_ot_argument_query,
)
from app.services.vector_store_service import (
    CHROMA_COLLECTION_DITA_OT_GITHUB,
    add_documents,
    delete_collection,
    get_collection_count,
    is_chroma_available,
    query_collection,
)

logger = get_structured_logger(__name__)

GITHUB_REPO_ISSUES_URL = "https://api.github.com/repos/dita-ot/dita-ot/issues"
ISSUE_HTML_BASE = "https://github.com/dita-ot/dita-ot/issues"
PER_PAGE_MAX = 100

_DEFAULT_MAX_ISSUES = int(os.getenv("DITA_OT_GITHUB_INDEX_MAX_ISSUES", "3500"))

# Labels whose presence causes an issue to be skipped at index time.
# Comma-separated env override: DITA_OT_GITHUB_SKIP_LABELS
_SKIP_LABELS: frozenset[str] = frozenset(
    l.strip().lower()
    for l in os.getenv("DITA_OT_GITHUB_SKIP_LABELS", "invalid,won't fix").split(",")
    if l.strip()
)

# Issues whose cleaned body is shorter than this are not indexed (likely empty/placeholder).
_MIN_BODY_CHARS: int = int(os.getenv("DITA_OT_GITHUB_MIN_BODY_CHARS", "150"))

# Minimum cosine similarity for a curated reference item to be included in results.
# 0.50 prevents semantically adjacent but off-topic entries (e.g. ditavalref "empty output"
# matching a chunking query via shared "no HTML" semantics) from occupying curated slots.
_CURATED_REF_MIN_SIM: float = float(os.getenv("DITA_OT_GITHUB_REF_MIN_SIM", "0.50"))

# Maximum curated reference slots when Chroma is available.
# Prevents the 6 curated entries from filling all k slots and blocking the broader corpus.
# In the no-Chroma fallback this cap is not applied (all relevant curated refs are returned).
_CURATED_REF_MAX_SLOTS: int = int(os.getenv("DITA_OT_GITHUB_CURATED_MAX_SLOTS", "2"))

# Patterns stripped from issue bodies before embedding and storage.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_CC_MENTION_LINE_RE = re.compile(r"^\s*(cc|ping|ref|/cc)\s+@\S.*$", re.MULTILINE | re.IGNORECASE)
_FIXES_LINE_RE = re.compile(r"^\s*(fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#\d+\s*$", re.MULTILINE | re.IGNORECASE)
_EXCESS_BLANK_RE = re.compile(r"\n{3,}")


def _clean_body(body: str) -> str:
    """Strip low-signal noise from a GitHub issue body before embedding/storage."""
    text = _HTML_COMMENT_RE.sub("", body)
    text = _CC_MENTION_LINE_RE.sub("", text)
    text = _FIXES_LINE_RE.sub("", text)
    text = _EXCESS_BLANK_RE.sub("\n\n", text)
    return text.strip()


def _should_index_issue(issue: dict[str, Any]) -> bool:
    """Return False for issues that add noise to the RAG index.

    Skips issues whose labels intersect _SKIP_LABELS, or whose cleaned body
    is shorter than _MIN_BODY_CHARS — these are typically invalid reports,
    declined issues, or blank placeholders.
    """
    labels_raw = issue.get("labels") or []
    if isinstance(labels_raw, list):
        issue_labels = {
            str(lb["name"]).strip().lower()
            for lb in labels_raw
            if isinstance(lb, dict) and lb.get("name")
        }
        if issue_labels & _SKIP_LABELS:
            return False
    body = _clean_body(str(issue.get("body") or ""))
    return len(body) >= _MIN_BODY_CHARS


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_REFERENCE_REL = Path("config") / "dita_ot_github_reference_issues.json"


def _reference_config_path() -> Path:
    """Resolved path to curated-issue JSON (never uses arbitrary user URLs — local path only)."""
    override = (os.getenv("DITA_OT_GITHUB_REFERENCE_JSON") or "").strip()
    if override:
        p = Path(override)
        return p if p.is_absolute() else _BACKEND_ROOT / p
    return _BACKEND_ROOT / _DEFAULT_REFERENCE_REL


def _coerce_reference_items(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        refs = raw.get("references")
        if isinstance(refs, list):
            return refs
    raise ValueError("config must be a JSON array or an object with a 'references' array")


def _normalize_reference_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    try:
        num = int(item["issue_number"])
    except (KeyError, TypeError, ValueError):
        return None
    if num <= 0:
        return None
    title = str(item.get("title") or "").strip()
    snippet = str(item.get("snippet") or "").strip()
    if not title or not snippet:
        return None
    url = str(item.get("url") or "").strip()
    if not url:
        url = f"{ISSUE_HTML_BASE}/{num}"
    elif not url.startswith("https://github.com/dita-ot/dita-ot/"):
        return None
    return {
        "url": url,
        "title": title[:2000],
        "issue_number": num,
        "snippet": snippet[:12000],
        "source": "dita_ot_github_reference",
    }


@lru_cache(maxsize=32)
def _load_reference_issues_cached(path_resolved: str, mtime_ns: int) -> tuple[dict[str, Any], ...]:
    path = Path(path_resolved)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning_structured(
            "dita_ot_github_reference_config_read_failed",
            extra_fields={"path": path_resolved, "error": str(exc)},
        )
        return ()
    try:
        items = _coerce_reference_items(raw)
    except ValueError as exc:
        logger.warning_structured(
            "dita_ot_github_reference_config_invalid_shape",
            extra_fields={"path": path_resolved, "error": str(exc)},
        )
        return ()

    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in items:
        row = _normalize_reference_item(item)
        if row is None:
            continue
        n = row["issue_number"]
        if n in seen:
            continue
        seen.add(n)
        out.append(row)
    out.sort(key=lambda r: int(r["issue_number"]))
    return tuple(out)


def get_dita_ot_github_reference_issues() -> tuple[dict[str, Any], ...]:
    """Curated DITA-OT GitHub issue rows for RAG (from JSON; no network)."""
    path = _reference_config_path()
    try:
        st = path.stat()
        return _load_reference_issues_cached(str(path.resolve()), int(st.st_mtime_ns))
    except OSError:
        logger.warning_structured(
            "dita_ot_github_reference_config_missing",
            extra_fields={"path": str(path)},
        )
        return ()


def _github_headers() -> dict[str, str]:
    """Headers for the fixed public REST URL ``/repos/dita-ot/dita-ot/issues`` (no auth required).

    Optional ``GITHUB_TOKEN`` / ``GH_TOKEN`` only increases GitHub API rate limits; omit for anonymous access.
    """
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "aem-guides-dataset-studio-dita-ot-rag",
    }
    token = (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _trunc(s: str, n: int) -> str:
    t = (s or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 3] + "..."


def _issue_document(issue: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]]:
    """Return (embed_text, doc_text, stable_id, metadata) for Chroma.

    embed_text is kept within all-MiniLM-L6-v2's 256-token (~1000-char) encoding window so the
    full title + labels + body summary are all captured in the vector.  doc_text is the richer
    stored document returned as snippet context to the LLM.
    """
    num = int(issue.get("number") or 0)
    if num <= 0:
        raise ValueError("invalid issue number")
    title = str(issue.get("title") or "").strip()
    body = _clean_body(str(issue.get("body") or ""))
    state = str(issue.get("state") or "").strip()
    labels_raw = issue.get("labels") or []
    label_names: list[str] = []
    if isinstance(labels_raw, list):
        for lb in labels_raw:
            if isinstance(lb, dict) and lb.get("name"):
                label_names.append(str(lb["name"]))
    labels_str = ", ".join(label_names[:24])
    url = f"{ISSUE_HTML_BASE}/{num}"

    # Compact text for embedding — title + labels + first 600 chars of body keeps
    # within the 256-token window so every field contributes to the vector.
    embed_text = (
        f"Title: {title}\n"
        f"State: {state} | Labels: {labels_str if labels_str else '(none)'}\n\n"
        f"{_trunc(body, 600)}"
    )

    # Richer text stored in Chroma and returned as LLM context snippet.
    doc_text = "\n".join(
        [
            f"Title: {title}",
            f"State: {state} | Issue: #{num}",
            f"Labels: {labels_str}" if labels_str else "Labels: (none)",
            f"URL: {url}",
            "",
            "Body:",
            _trunc(body, 3000),
        ]
    )

    meta: dict[str, Any] = {
        "url": url,
        "title": _trunc(title, 500),
        "issue_number": num,
        "state": state,
        "labels": _trunc(labels_str, 800),
        "source": "dita_ot_github",
    }
    return embed_text, doc_text, f"dita_ot_gh_{num}", meta


def fetch_dita_ot_issues(
    *,
    max_issues: int,
    state: str = "all",
    since: str | None = None,
    timeout_sec: float = 60.0,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (issues_json_list, errors). Only issues (not PRs). Fixed URL only.

    Args:
        since: ISO 8601 timestamp (e.g. ``"2025-01-01T00:00:00Z"``) — only returns issues
               updated at or after this time. Useful for incremental re-indexing.
    """
    errors: list[str] = []
    collected: list[dict[str, Any]] = []
    page = 1
    headers = _github_headers()

    with httpx.Client(timeout=timeout_sec, follow_redirects=False) as client:
        while len(collected) < max_issues and page <= 200:
            remaining = max_issues - len(collected)
            per_page = min(PER_PAGE_MAX, remaining)
            if per_page <= 0:
                break
            params: dict[str, Any] = {"state": state, "per_page": str(per_page), "page": str(page)}
            if since:
                params["since"] = since
            try:
                resp = None
                for attempt in range(3):
                    resp = client.get(GITHUB_REPO_ISSUES_URL, headers=headers, params=params)
                    if resp.status_code in (429, 403):
                        reset_ts = resp.headers.get("X-RateLimit-Reset")
                        if reset_ts:
                            wait = max(0, int(reset_ts) - int(time.time())) + 2
                        else:
                            wait = float(resp.headers.get("Retry-After") or (15 * (2 ** attempt)))
                        wait = min(wait, 120)
                        errors.append(
                            f"GitHub rate limited (HTTP {resp.status_code}) on page {page}; "
                            f"sleeping {wait:.0f}s (attempt {attempt + 1}/3)"
                        )
                        time.sleep(wait)
                        continue
                    break
                if resp is None:
                    break
                resp.raise_for_status()
                batch = resp.json()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"fetch page {page}: {exc}")
                break

            if not isinstance(batch, list) or not batch:
                break

            for issue in batch:
                if not isinstance(issue, dict):
                    continue
                if issue.get("pull_request"):
                    continue
                collected.append(issue)
                if len(collected) >= max_issues:
                    break

            if len(collected) % 500 == 0 and len(collected) > 0:
                logger.info_structured(
                    "dita_ot_github_fetch_progress",
                    extra_fields={"fetched": len(collected), "page": page},
                )

            if len(batch) < per_page:
                break
            page += 1
            time.sleep(0.15)

    return collected, errors


def index_dita_ot_github_issues(
    *,
    max_issues: int | None = None,
    force_reindex: bool = False,
    state: str = "all",
    since: str | None = None,
) -> dict[str, Any]:
    """Download issues from dita-ot/dita-ot, embed, upsert into Chroma ``dita_ot_github``.

    Args:
        since: ISO 8601 timestamp for incremental re-indexing (only issues updated after this date).
               Leave ``None`` for a full index.

    Returns stats dict with indexed count and errors (no secrets).
    """
    cap = max(1, min(int(max_issues or _DEFAULT_MAX_ISSUES), 5000))
    out: dict[str, Any] = {
        "collection": CHROMA_COLLECTION_DITA_OT_GITHUB,
        "requested_max": cap,
        "indexed": 0,
        "skipped": 0,
        "errors": [],
        "chroma": is_chroma_available(),
        "embedding_available": is_embedding_available(),
        "skip_labels": sorted(_SKIP_LABELS),
        "min_body_chars": _MIN_BODY_CHARS,
    }

    if not out["chroma"]:
        out["errors"].append("ChromaDB unavailable — cannot index.")
        return out
    if not out["embedding_available"]:
        out["errors"].append("Embedding model unavailable — set DITA_EMBEDDING_MODEL_PATH and retry.")
        return out

    issues, fetch_errors = fetch_dita_ot_issues(max_issues=cap, state=state, since=since)
    out["errors"].extend(fetch_errors)

    rows: list[tuple[str, str, str, dict[str, Any]]] = []
    for issue in issues:
        if not _should_index_issue(issue):
            out["skipped"] += 1
            continue
        try:
            embed_text, doc_text, doc_id, meta = _issue_document(issue)
            rows.append((embed_text, doc_text, doc_id, meta))
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"skip issue parse: {exc}")

    if not rows:
        out["errors"].append("No issues fetched or parsed — check network, token, or repo access.")
        return out

    if force_reindex:
        delete_collection(CHROMA_COLLECTION_DITA_OT_GITHUB)

    embed_texts_list = [r[0] for r in rows]
    doc_texts = [r[1] for r in rows]
    ids = [r[2] for r in rows]
    metas = []
    for _et, _dt, _i, m in rows:
        clean = {k: v for k, v in m.items() if isinstance(v, (str, int, float, bool))}
        metas.append(clean)

    embeddings = embed_texts_batched(embed_texts_list, batch_size=32)
    if embeddings is None:
        out["errors"].append("Embedding batch failed.")
        return out

    emb_list = [embeddings[i].tolist() for i in range(len(ids))]
    ok = add_documents(CHROMA_COLLECTION_DITA_OT_GITHUB, ids, doc_texts, metas, emb_list)
    if not ok:
        out["errors"].append("Chroma upsert failed.")
        return out

    out["indexed"] = len(ids)
    logger.info_structured(
        "dita_ot_github_index_done",
        extra_fields={
            "indexed": len(ids),
            "skipped": out["skipped"],
            "force_reindex": force_reindex,
            "since": since,
            "skip_labels": sorted(_SKIP_LABELS),
        },
    )
    return out


_PUBLISHING_QUERY_RE = re.compile(
    r"(?i)\b("
    r"dita[-\s]?ot|open\s+toolkit"                                # identity
    r"|ditamaps?|ditaval|ditavalref|topicrefs?|maprefs?|reltables?|bookmap"  # structure
    r"|transtype|transform(?:ation|ing|ed|s)?"                    # pipeline (+ inflections)
    r"|preprocess(?:ing|ed|or)?"
    r"|pdf2|chunk(?:ed|ing|s)?"
    r"|publish(?:ing|ed|er|es)?"
    r"|output|html5|eclipsehelp|dotj|dotx"
    r"|keyrefs?|keyscopes?|conrefs?|conkeyref"                    # referencing (+ plurals, keyscope)
    r"|filter(?:ing|ed|s)?|flag(?:s|ging|ged)?"                   # conditional processing
    r"|ant|build\s+logs?"
    r"|subject\s*schemes?|subjectschemes?"                        # subject scheme (+ plural)
    r"|hierarchical|propagat(?:ion|e(?:s|d)?|ing)|enumerationdef" # filtering spec
    r"|plugins?|integrat(?:or|ion|ing|ed)?"                       # plugin / integrator
    r"|xslt?|xsl-?fo|fop"                                        # stylesheet / PDF renderer
    r"|specializ(?:ation|ed|ing|es)?"                             # DITA specialization
    r")\b"
)


def should_query_dita_ot_github_rag(query: str) -> bool:
    """True when the question is about DITA Open Toolkit core usage, build args, publishing, or related filtering.

    Reuses ``_DITA_OT_ENGINE_PATTERN`` / Native PDF + OT argument heuristics from ``prompt_router_service``
    so this slice aligns with \"core OT\" detection (not only transtype/ditaval-style keywords).
    """
    q = (query or "").strip()
    if not q:
        return False
    if _PUBLISHING_QUERY_RE.search(q):
        return True
    if _DITA_OT_ENGINE_PATTERN.search(q):
        return True
    if is_native_pdf_dita_ot_argument_query(q):
        return True
    return False


def _chroma_rows_to_results(
    rows: list[dict[str, Any]],
    seen_nums: set[int],
    limit: int,
) -> list[dict[str, Any]]:
    """Convert Chroma result rows to result dicts, skipping already-seen issue numbers."""
    results: list[dict[str, Any]] = []
    for row in rows:
        if len(results) >= limit:
            break
        meta = row.get("metadata") or {}
        doc = row.get("document") or ""
        url = str(meta.get("url") or "")
        title = str(meta.get("title") or "")
        num = meta.get("issue_number")
        inum = int(num) if isinstance(num, int) else None
        if inum is not None and inum in seen_nums:
            continue
        if inum is not None:
            seen_nums.add(inum)
        results.append(
            {
                "url": url,
                "title": title or url,
                "snippet": str(doc)[:1200],
                "issue_number": inum,
            }
        )
    return results


def _score_curated_refs(
    query_vec: list[float],
    refs: tuple[dict[str, Any], ...],
) -> list[tuple[float, dict[str, Any]]]:
    """Return curated refs that are semantically relevant to query_vec, sorted by similarity.

    Embeds title + first 600 chars of each ref's snippet (same budget as _issue_document
    embed_text), computes cosine similarity against query_vec, and filters out refs below
    _CURATED_REF_MIN_SIM so off-topic entries never occupy result slots.
    """
    if not refs:
        return []
    texts = [
        f"{r.get('title', '')}\n{str(r.get('snippet', ''))[:600]}"
        for r in refs
    ]
    embs = embed_texts_batched(texts)
    if embs is None:
        return []
    qv = np.array(query_vec, dtype=float)
    qnorm = float(np.linalg.norm(qv))
    if qnorm == 0:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for i, ref in enumerate(refs):
        rv = np.array(embs[i], dtype=float)
        rnorm = float(np.linalg.norm(rv))
        sim = float(np.dot(qv, rv) / (qnorm * rnorm)) if rnorm > 0 else 0.0
        if sim >= _CURATED_REF_MIN_SIM:
            scored.append((sim, dict(ref)))
    return sorted(scored, key=lambda x: x[0], reverse=True)


def retrieve_dita_ot_github_for_query(query: str, k: int = 4) -> list[dict[str, Any]]:
    """Return semantically relevant GitHub issues for a DITA-OT publishing query.

    Result ordering:
      1. Curated reference issues whose cosine similarity to the query ≥ _CURATED_REF_MIN_SIM
         (sorted by similarity, most relevant first).
      2. Open issues from Chroma (current known limitations — most actionable for QA).
      3. Closed issues from Chroma filling remaining slots (historical fix context).

    Falls back to returning all curated refs (no scoring) when Chroma or the embedding
    model is unavailable, so answers remain grounded without a full index.
    """
    if not query or not str(query).strip():
        return []
    if not should_query_dita_ot_github_rag(query):
        return []

    k = max(1, min(int(k), 12))
    out: list[dict[str, Any]] = []
    seen_nums: set[int] = set()

    refs = get_dita_ot_github_reference_issues()

    # --- Fallback: no Chroma or embedding model available ---
    if not is_chroma_available() or not is_embedding_available() \
            or get_collection_count(CHROMA_COLLECTION_DITA_OT_GITHUB) <= 0:
        for ref in refs:
            if len(out) >= k:
                break
            out.append(dict(ref))
        return out

    # --- Embed query once; reuse for curated scoring AND Chroma lookup ---
    emb = embed_query(str(query).strip()[:4000])
    if emb is None:
        for ref in refs:
            if len(out) >= k:
                break
            out.append(dict(ref))
        return out

    vec = emb.tolist() if hasattr(emb, "tolist") else list(emb)

    # 1. Curated refs — top semantically relevant entries, capped at _CURATED_REF_MAX_SLOTS
    #    so the broader Chroma corpus always contributes at least (k - cap) slots.
    curated_cap = min(_CURATED_REF_MAX_SLOTS, max(1, k - 1))
    for _sim, ref in _score_curated_refs(vec, refs):
        if len(out) >= curated_cap:
            break
        out.append(ref)
        n = ref.get("issue_number")
        if isinstance(n, int):
            seen_nums.add(n)

    # 2. Open issues — current known limitations most actionable for QA.
    remaining = k - len(out)
    if remaining > 0:
        fetch_n = min(remaining + len(seen_nums) + 4, 24)
        open_rows = query_collection(
            CHROMA_COLLECTION_DITA_OT_GITHUB,
            query_embedding=vec,
            k=fetch_n,
            where={"state": {"$eq": "open"}},
        )
        out.extend(_chroma_rows_to_results(open_rows, seen_nums, remaining))

    # 3. Closed issues fill remaining slots — historical fixes and root-cause context.
    still_remaining = k - len(out)
    if still_remaining > 0:
        fetch_n2 = min(still_remaining + len(seen_nums) + 4, 24)
        closed_rows = query_collection(
            CHROMA_COLLECTION_DITA_OT_GITHUB,
            query_embedding=vec,
            k=fetch_n2,
            where={"state": {"$eq": "closed"}},
        )
        out.extend(_chroma_rows_to_results(closed_rows, seen_nums, still_remaining))

    return out[:k]


__all__ = [
    "CHROMA_COLLECTION_DITA_OT_GITHUB",
    "get_dita_ot_github_reference_issues",
    "GITHUB_REPO_ISSUES_URL",
    "index_dita_ot_github_issues",
    "retrieve_dita_ot_github_for_query",
    "should_query_dita_ot_github_rag",
]


def __getattr__(name: str) -> Any:
    if name == "DITA_OT_GITHUB_REFERENCE_ISSUES":
        return get_dita_ot_github_reference_issues()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
