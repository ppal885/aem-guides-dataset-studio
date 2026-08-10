"""
Backfill closed UAC Jira issues into the jira_qa ChromaDB index.

Usage:
    python backfill_uac_index.py [--jql JQL] [--batch-size N] [--dry-run]

Default JQL fetches closed DXML/GUIDES issues with resolution, ordered by updated desc.
"""
import argparse
import os
import sys
import time
from pathlib import Path

# Make sure backend is on sys.path
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("ALLOW_DEV_AUTH_BYPASS", "true")

# Load .env from backend root so JIRA_URL / JIRA_USERNAME / etc. are available
_ENV_FILE = _BACKEND / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_FILE, override=False)
    except ImportError:
        # dotenv not installed — parse manually for essential vars
        for _line in _ENV_FILE.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_uac")


# ── defaults ──────────────────────────────────────────────────────────────────
DEFAULT_JQL = (
    'project in (DXML, GUIDES) AND status in (Closed, Resolved, Done) '
    'AND resolution is not EMPTY '
    'ORDER BY updated DESC'
)
DEFAULT_BATCH = 50
CHROMA_BATCH = 200   # chunk rows per ChromaDB upsert call


def _import_services():
    from app.services.jira_client import JiraClient
    from app.services.jira_qa_chunking_service import build_jira_qa_chunks
    from app.services.vector_store_service import (
        add_documents,
        CHROMA_COLLECTION_JIRA_QA,
        is_chroma_available,
    )
    from app.services.embedding_service import embed_texts_batched, is_embedding_available
    from app.services.jira_enrichment_service import enrich_jira
    from app.db.session import SessionLocal
    from app.db.jira_models import JiraIssue
    from app.services.jira_index_service import upsert_issue_from_search_result
    return (
        JiraClient, build_jira_qa_chunks, add_documents,
        CHROMA_COLLECTION_JIRA_QA, is_chroma_available,
        embed_texts_batched, is_embedding_available,
        enrich_jira, SessionLocal, JiraIssue,
        upsert_issue_from_search_result,
    )


def _already_indexed(chroma_collection, issue_key: str) -> bool:
    """Return True if at least one chunk for this key is already in ChromaDB."""
    try:
        from app.services.vector_store_service import query_collection
        results = query_collection(
            chroma_collection,
            query_texts=[issue_key],
            n_results=1,
            where={"issue_key": issue_key},
        )
        return bool(results and results.get("ids") and results["ids"][0])
    except Exception:
        return False


def _flush_batch(rows: list[dict], embed_fn, add_fn, collection_name: str) -> tuple[int, list[str]]:
    """Embed + upsert a list of chunk rows. Returns (indexed_count, errors)."""
    if not rows:
        return 0, []
    texts = [r["document"] for r in rows]
    embeddings = embed_fn(texts, batch_size=48)
    if embeddings is None:
        return 0, ["embedding batch failed"]
    ids = [r["chunk_id"] for r in rows]
    metadata = [
        {k: v for k, v in r["metadata"].items() if isinstance(v, (str, int, float, bool))}
        for r in rows
    ]
    vectors = [embeddings[i].tolist() for i in range(len(ids))]
    docs = [r["document"] for r in rows]
    for attempt in range(1, 4):
        ok = add_fn(collection_name, ids, docs, metadata, vectors)
        if ok:
            return len(ids), []
        if attempt < 3:
            time.sleep(0.5 * attempt)
    return 0, ["chroma upsert failed after 3 attempts"]


def run_backfill(
    jql: str = DEFAULT_JQL,
    batch_size: int = DEFAULT_BATCH,
    dry_run: bool = False,
    skip_existing: bool = True,
    max_issues: int | None = None,
) -> dict:
    (
        JiraClient, build_jira_qa_chunks, add_documents,
        CHROMA_COLLECTION_JIRA_QA, is_chroma_available,
        embed_texts_batched, is_embedding_available,
        enrich_jira, SessionLocal, JiraIssue,
        upsert_issue_from_search_result,
    ) = _import_services()

    if not is_chroma_available():
        raise RuntimeError("ChromaDB is not available — start backend first or check storage path.")
    if not is_embedding_available():
        raise RuntimeError("Embedding model not available — set DITA_EMBEDDING_MODEL_PATH.")

    client = JiraClient()
    log.info("Running JQL: %s", jql)

    start_at = 0
    total_fetched = total_indexed = total_skipped = total_errors = 0
    all_errors: list[str] = []

    while True:
        try:
            issues, total_count = client.search_issues_key_page(
                jql=jql, start_at=start_at, page_size=batch_size
            )
        except Exception as exc:
            log.error("Jira search failed at offset %d: %s", start_at, exc)
            break

        if not issues:
            break

        log.info("Fetched %d issues (offset %d / %d total)", len(issues), start_at, total_count)
        chunk_buffer: list[dict] = []

        for issue_dict in issues:
            key = (issue_dict.get("key") or "").strip()
            if not key:
                continue

            total_fetched += 1
            if max_issues and total_fetched > max_issues:
                break

            if skip_existing and _already_indexed(CHROMA_COLLECTION_JIRA_QA, key):
                log.debug("Skipping already-indexed %s", key)
                total_skipped += 1
                continue

            if dry_run:
                log.info("[dry-run] Would index %s", key)
                total_indexed += 1
                continue

            try:
                full_issue = client.get_issue(key)
                comments = client.get_issue_comments(key)
                chunks = build_jira_qa_chunks(key, full_issue, comments=comments)
                if chunks:
                    chunk_buffer.extend(chunks)
                    log.debug("%s → %d chunks buffered", key, len(chunks))
                else:
                    log.warning("%s produced 0 chunks", key)
                    total_skipped += 1
            except Exception as exc:
                log.error("Failed to process %s: %s", key, exc)
                total_errors += 1
                all_errors.append(f"{key}: {exc}")
                continue

            if len(chunk_buffer) >= CHROMA_BATCH:
                n, errs = _flush_batch(chunk_buffer, embed_texts_batched, add_documents, CHROMA_COLLECTION_JIRA_QA)
                total_indexed += n
                total_errors += len(errs)
                all_errors.extend(errs)
                chunk_buffer.clear()
                log.info("Flushed batch → %d chunks indexed so far", total_indexed)

        # flush tail
        if chunk_buffer:
            n, errs = _flush_batch(chunk_buffer, embed_texts_batched, add_documents, CHROMA_COLLECTION_JIRA_QA)
            total_indexed += n
            total_errors += len(errs)
            all_errors.extend(errs)
            chunk_buffer.clear()

        start_at += len(issues)
        if start_at >= total_count:
            break
        if max_issues and total_fetched >= max_issues:
            break
        time.sleep(0.3)  # polite pause

    summary = {
        "fetched": total_fetched,
        "indexed_chunks": total_indexed,
        "skipped": total_skipped,
        "errors": total_errors,
        "error_details": all_errors[:20],
    }
    log.info("Backfill complete: %s", summary)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill closed UAC Jira issues into ChromaDB jira_qa.")
    ap.add_argument("--jql", default=DEFAULT_JQL, help="Jira JQL query")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    ap.add_argument("--max", type=int, default=None, help="Max issues to process (for smoke-test)")
    ap.add_argument("--dry-run", action="store_true", help="Skip actual indexing, just count")
    ap.add_argument("--no-skip-existing", action="store_true", help="Re-index even if already in ChromaDB")
    args = ap.parse_args()

    result = run_backfill(
        jql=args.jql,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        skip_existing=not args.no_skip_existing,
        max_issues=args.max,
    )
    print("\n=== Backfill Summary ===")
    for k, v in result.items():
        if k != "error_details":
            print(f"  {k}: {v}")
    if result["error_details"]:
        print("  First errors:")
        for e in result["error_details"][:5]:
            print(f"    • {e}")


if __name__ == "__main__":
    main()
