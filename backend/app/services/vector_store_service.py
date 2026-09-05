"""Unified vector store service using ChromaDB.

Provides persistent storage for embeddings with metadata filtering.
Collections: aem_guides, dita_spec, recipes, jira_issues.
"""
import hashlib
import json
import os
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional
from uuid import UUID

from app.storage import get_storage
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

CHROMA_COLLECTION_AEM_GUIDES = "aem_guides"
CHROMA_COLLECTION_ENTERPRISE_QA = CHROMA_COLLECTION_AEM_GUIDES
CHROMA_COLLECTION_DITA_SPEC = "dita_spec"
CHROMA_COLLECTION_JIRA_QA = "jira_qa"
CHROMA_COLLECTION_DITA_OT_GITHUB = "dita_ot_github"
CHROMA_COLLECTION_LEARNED_QA = "learned_qa"
CHROMA_COLLECTION_DOCKER_DOCS = "docker_docs"
CHROMA_DB_DIR = "chroma_db"

_chroma_client = None
_identity_client = None
_identity_snapshot = None


def _remember_client_identity(client, mode: str, target: dict) -> None:
    """Freeze non-secret target information for this successfully opened client.

    This is observational only: it neither configures a client nor reads mutable
    environment variables. The target comes from the exact constructor arguments.
    No raw path, host, auth settings, or exception text is retained in the receipt.
    """
    global _identity_client, _identity_snapshot
    snapshot = {
        "mode": mode if mode in {"EMBEDDED", "REMOTE"} else "UNKNOWN",
        "target_fingerprint": None,
        "tenant": None, "database": None, "client_version": None,
    }
    try:
        for field in ("tenant", "database"):
            value = getattr(client, field, None)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value):
                snapshot[field] = value
        try:
            installed = version("chromadb")
            if re.fullmatch(r"[0-9][A-Za-z0-9.+_-]{0,63}", installed):
                snapshot["client_version"] = installed
        except (PackageNotFoundError, ValueError, TypeError):
            pass
        valid_target = False
        if mode == "EMBEDDED":
            path = target.get("path")
            valid_target = isinstance(path, str) and bool(path) and len(path) <= 4096
        elif mode == "REMOTE":
            # Full URLs with userinfo/query credentials are not diagnostic targets.
            # Unsupported forms leave the fingerprint unavailable; never guess it.
            host, port, ssl = target.get("host"), target.get("port"), target.get("ssl")
            valid_target = (
                isinstance(host, str)
                and re.fullmatch(r"[A-Za-z0-9.:[\]-]{1,253}", host) is not None
                and type(port) is int and 1 <= port <= 65535 and type(ssl) is bool
            )
        if valid_target and snapshot["tenant"] and snapshot["database"]:
            payload = {"mode": mode, "target": target,
                       "tenant": snapshot["tenant"], "database": snapshot["database"]}
            snapshot["target_fingerprint"] = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
    except Exception:
        # A diagnostic failure must never change retrieval availability.
        pass
    _identity_client = client
    _identity_snapshot = snapshot


def get_index_identity() -> dict:
    """Read the initialized client's identity and existing collection UUIDs/counts.

    Does not initialize Chroma, create collections, fetch documents, or infer
    embedding compatibility. Equal counts are not proof of equal collection IDs.
    Collection read failures are null/UNAVAILABLE, never a fabricated zero.
    """
    client = _chroma_client
    result = {
        "schema_version": "chroma-index-identity-v1", "status": "UNAVAILABLE",
        "mode": "UNKNOWN", "target_fingerprint": None,
        "tenant": None, "database": None, "client_version": None,
        "collections": {},
    }
    if client is not None and client is _identity_client and isinstance(_identity_snapshot, dict):
        # Chroma clients can change tenant/database after construction. Do not
        # attribute those collections to an earlier scope's cached fingerprint.
        try:
            same_scope = all(getattr(client, field, None) == _identity_snapshot[field]
                             for field in ("tenant", "database"))
        except Exception:
            same_scope = False
        if same_scope:
            result.update(_identity_snapshot)
    for name in (CHROMA_COLLECTION_AEM_GUIDES, CHROMA_COLLECTION_DITA_SPEC, CHROMA_COLLECTION_JIRA_QA):
        row = {"id": None, "count": None, "status": "UNAVAILABLE"}
        result["collections"][name] = row
        if client is None:
            continue
        try:
            collection = client.get_collection(name=name)
            identifier = str(collection.id)
            if re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", identifier):
                row["id"] = str(UUID(identifier))
            observed = collection.count()
            if type(observed) is int and observed >= 0:
                row["count"] = observed
            row["status"] = "OK" if row["id"] is not None and row["count"] is not None else "PARTIAL"
        except Exception:
            # Preserve any UUID already observed; never return raw errors/auth data.
            row["status"] = "UNAVAILABLE"
    if client is not None:
        complete = result["target_fingerprint"] is not None and all(
            row["status"] == "OK" for row in result["collections"].values()
        )
        result["status"] = "OK" if complete else "PARTIAL"
    return result


def _get_chroma_path() -> Path:
    """Path for ChromaDB persistent storage."""
    storage = get_storage()
    path = storage.base_path / CHROMA_DB_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_client():
    """Get or create ChromaDB persistent client. Returns None if ChromaDB unavailable."""
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client
    try:
        import os

        import chromadb
        from chromadb.config import DEFAULT_DATABASE, DEFAULT_TENANT

        # Shared-server mode: when CHROMA_HOST is set, connect to a Chroma running in
        # client-server mode (e.g. on the VM) so multiple people/processes can write
        # to ONE database safely (embedded PersistentClient is single-writer and
        # corrupts under concurrent multi-process writes). Backward-compatible: with
        # no CHROMA_HOST, we fall back to the local embedded PersistentClient.
        chroma_host = os.getenv("CHROMA_HOST", "").strip()
        if chroma_host:
            from chromadb.config import Settings
            setting_kwargs = {}
            auth_token = os.getenv("CHROMA_AUTH_TOKEN", "").strip()
            if auth_token:
                setting_kwargs["chroma_client_auth_provider"] = "chromadb.auth.token_authn.TokenAuthClientProvider"
                setting_kwargs["chroma_client_auth_credentials"] = auth_token
            # NOTE: the Chroma client validates chroma_server_api_default_path as an
            # enum (/api/v1 or /api/v2 only) - a custom sub-path prefix is rejected.
            # To reverse-proxy through an already-exposed port, route the real
            # /api/v2 path in nginx (location /api/v2/ -> chroma) instead of a
            # custom prefix; the client then needs no path override here.
            settings = Settings(**setting_kwargs) if setting_kwargs else None
            chroma_port = int(os.getenv("CHROMA_PORT", "8000"))
            chroma_ssl = os.getenv("CHROMA_SSL", "false").strip().lower() in ("1", "true", "yes", "on")
            client = chromadb.HttpClient(
                host=chroma_host,
                port=chroma_port,
                ssl=chroma_ssl,
                settings=settings,
            )
            client.heartbeat()  # fail fast if the server is unreachable
            _remember_client_identity(client, "REMOTE", {"host": chroma_host, "port": chroma_port, "ssl": chroma_ssl})
            _chroma_client = client
            logger.info_structured("ChromaDB connected in server mode",
                                   extra_fields={"host": chroma_host, "port": os.getenv("CHROMA_PORT", "8000")})
            return _chroma_client

        path = _get_chroma_path()
        # Pin Chroma's canonical tenant/database names (default_tenant / default_database) so we never
        # rely on ambiguous defaults after upgrades or partial migrations.
        client = chromadb.PersistentClient(
            path=str(path),
            tenant=DEFAULT_TENANT,
            database=DEFAULT_DATABASE,
        )
        try:
            client.list_collections()
        except Exception as warmup_exc:
            msg = str(warmup_exc).lower()
            if "tenant" in msg and "not found" in msg:
                try:
                    client.create_tenant(DEFAULT_TENANT)
                except Exception:
                    pass
                try:
                    client.create_database(DEFAULT_DATABASE, tenant=DEFAULT_TENANT)
                except Exception:
                    pass
                client.list_collections()
        _remember_client_identity(client, "EMBEDDED", {"path": str(path)})
        _chroma_client = client
        return _chroma_client
    except ImportError as e:
        logger.warning_structured(
            "ChromaDB not installed",
            extra_fields={"error": str(e), "hint": "pip install chromadb"},
        )
        return None
    except Exception as e:
        logger.warning_structured(
            "ChromaDB init failed",
            extra_fields={"error": str(e)},
        )
        return None


def is_chroma_available() -> bool:
    """Return True if ChromaDB is available and usable."""
    return _get_client() is not None


def add_documents(
    collection_name: str,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
    embeddings: list[list[float]],
) -> bool:
    """
    Add or upsert documents to a ChromaDB collection.
    All lists must have the same length.
    Returns True on success, False on failure.
    """
    client = _get_client()
    if not client or not ids or len({len(ids), len(documents), len(metadatas), len(embeddings)}) != 1:
        return False
    try:
        coll = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        coll.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        events_persisted = _queue_evidence_graph_events(
            collection_name,
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            event_type="upsert",
        )
        return bool(events_persisted)
    except Exception as e:
        logger.warning_structured(
            "ChromaDB add_documents failed",
            extra_fields={"collection": collection_name, "error": str(e), "count": len(ids)},
        )
        return False


def _collection_exists(client, collection_name: str) -> bool:
    """Check if collection exists without raising. Returns False if not found."""
    try:
        names = [c.name for c in client.list_collections()]
        return collection_name in names
    except Exception:
        return False


def query_collection(
    collection_name: str,
    query_embedding: list[float],
    k: int = 5,
    where: Optional[dict] = None,
) -> list[dict]:
    """
    Query ChromaDB collection by embedding.
    Returns list of dicts with keys: id, document, metadata, distance.
    Returns [] when collection does not exist (expected before first index).
    """
    client = _get_client()
    if not client or not query_embedding:
        return []
    if not _collection_exists(client, collection_name):
        return []
    # Ensure embedding is list of floats (ChromaDB expects list)
    emb = query_embedding
    if hasattr(emb, "tolist"):
        emb = emb.tolist()
    emb = list(emb) if emb else []
    if not emb:
        return []
    try:
        coll = client.get_collection(name=collection_name)
        count = coll.count()
        if count == 0:
            return []
        result = coll.query(
            query_embeddings=[emb],
            n_results=min(k, count),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        if not result or not result["ids"] or not result["ids"][0]:
            return []
        rows = []
        for i, doc_id in enumerate(result["ids"][0]):
            doc = (result["documents"][0][i] or "") if result["documents"] else ""
            meta = (result["metadatas"][0][i] or {}) if result["metadatas"] else {}
            dist = (result["distances"][0][i] or 0.0) if result.get("distances") else 0.0
            rows.append({
                "id": doc_id,
                "document": doc,
                "metadata": meta,
                "distance": dist,
            })
        return rows
    except Exception as e:
        logger.warning_structured(
            "ChromaDB query failed",
            extra_fields={"collection": collection_name, "error": str(e)},
        )
        return []


def delete_documents(collection_name: str, ids: list[str]) -> bool:
    """Delete documents by id from a collection. No-op if collection missing or ids empty."""
    if not ids:
        return True
    client = _get_client()
    if not client:
        return False
    if not _collection_exists(client, collection_name):
        return True
    try:
        coll = client.get_collection(name=collection_name)
        existing = get_collection_records_by_ids(collection_name, ids, include_documents=True)
        coll.delete(ids=ids)
        metadata_by_id = {str(row.get("id") or ""): row for row in existing}
        events_persisted = _queue_evidence_graph_events(
            collection_name,
            ids=ids,
            documents=[str(metadata_by_id.get(doc_id, {}).get("document") or "") for doc_id in ids],
            metadatas=[dict(metadata_by_id.get(doc_id, {}).get("metadata") or {}) for doc_id in ids],
            event_type="delete",
        )
        return bool(events_persisted)
    except Exception as e:
        logger.warning_structured(
            "ChromaDB delete_documents failed",
            extra_fields={"collection": collection_name, "error": str(e), "count": len(ids)},
        )
        return False


def update_documents_metadata(collection_name: str, where: dict, updates: dict, *, limit: int = 500) -> int:
    """Merge scalar metadata into matching Chroma documents without changing text or embeddings."""
    client = _get_client()
    if not client or not _collection_exists(client, collection_name):
        return 0
    try:
        coll = client.get_collection(name=collection_name)
        result = coll.get(
            where=where,
            limit=max(1, limit),
            include=["documents", "metadatas"],
        )
        ids = result.get("ids") or []
        metadatas = result.get("metadatas") or []
        documents = result.get("documents") or []
        if not ids:
            return 0
        merged = []
        for index, _doc_id in enumerate(ids):
            metadata = dict(metadatas[index] or {})
            metadata.update({key: value for key, value in updates.items() if isinstance(value, (str, int, float, bool))})
            merged.append(metadata)
        coll.update(ids=ids, metadatas=merged)
        events_persisted = _queue_evidence_graph_events(
            collection_name,
            ids=ids,
            documents=[
                str(documents[index] or "") if index < len(documents) else ""
                for index in range(len(ids))
            ],
            metadatas=merged,
            event_type="upsert",
        )
        return len(ids) if events_persisted else 0
    except Exception as exc:
        logger.warning_structured(
            "ChromaDB metadata update failed",
            extra_fields={"collection": collection_name, "error": str(exc), "where": str(where)[:500]},
        )
        return 0


def update_document_metadatas(collection_name: str, ids: list[str], metadatas: list[dict]) -> bool:
    """Replace metadata for specific documents while preserving documents and embeddings."""
    if not ids or len(ids) != len(metadatas):
        return False
    client = _get_client()
    if not client or not _collection_exists(client, collection_name):
        return False
    cleaned: list[dict] = []
    for metadata in metadatas:
        cleaned.append({
            key: value
            for key, value in dict(metadata or {}).items()
            if isinstance(value, (str, int, float, bool))
        })
    try:
        existing = get_collection_records_by_ids(collection_name, ids, include_documents=True)
        existing_by_id = {str(row.get("id") or ""): row for row in existing}
        client.get_collection(name=collection_name).update(ids=ids, metadatas=cleaned)
        events_persisted = _queue_evidence_graph_events(
            collection_name,
            ids=ids,
            documents=[
                str(existing_by_id.get(doc_id, {}).get("document") or "")
                for doc_id in ids
            ],
            metadatas=cleaned,
            event_type="upsert",
        )
        return bool(events_persisted)
    except Exception as exc:
        logger.warning_structured(
            "ChromaDB per-document metadata update failed",
            extra_fields={"collection": collection_name, "error": str(exc), "count": len(ids)},
        )
        return False


def delete_collection(collection_name: str) -> bool:
    """Delete a ChromaDB collection. Returns True on success. No-op if collection does not exist."""
    client = _get_client()
    if not client:
        return False
    if not _collection_exists(client, collection_name):
        return True
    try:
        client.delete_collection(name=collection_name)
        return True
    except Exception as e:
        logger.warning_structured(
            "ChromaDB delete_collection failed",
            extra_fields={"collection": collection_name, "error": str(e)},
        )
        return False


def get_collection_count(collection_name: str) -> int:
    """Return number of documents in collection. Returns 0 if unavailable or collection does not exist."""
    client = _get_client()
    if not client:
        return 0
    if not _collection_exists(client, collection_name):
        return 0
    try:
        coll = client.get_collection(name=collection_name)
        return coll.count()
    except Exception:
        return 0


def get_collection_records(collection_name: str, *, include_documents: bool = False) -> list[dict]:
    """Return all document IDs and metadata, optionally including document text."""
    client = _get_client()
    if not client or not _collection_exists(client, collection_name):
        return []
    try:
        includes = ["metadatas", "documents"] if include_documents else ["metadatas"]
        result = client.get_collection(name=collection_name).get(include=includes)
        ids = result.get("ids") or []
        metadatas = result.get("metadatas") or []
        documents = result.get("documents") or []
        return [
            {
                "id": doc_id,
                "metadata": (metadatas[index] if index < len(metadatas) else None) or {},
                **(
                    {"document": (documents[index] if index < len(documents) else None) or ""}
                    if include_documents
                    else {}
                ),
            }
            for index, doc_id in enumerate(ids)
        ]
    except Exception as exc:
        logger.warning_structured(
            "ChromaDB collection record scan failed",
            extra_fields={"collection": collection_name, "error": str(exc)},
        )
        return []


def get_collection_records_by_ids(
    collection_name: str,
    ids: list[str],
    *,
    include_documents: bool = False,
) -> list[dict]:
    """Return selected Chroma records without scanning the collection."""
    requested = [str(value) for value in ids if str(value)]
    if not requested:
        return []
    client = _get_client()
    if not client or not _collection_exists(client, collection_name):
        return []
    try:
        includes = ["metadatas", "documents"] if include_documents else ["metadatas"]
        result = client.get_collection(name=collection_name).get(ids=requested, include=includes)
        result_ids = result.get("ids") or []
        metadatas = result.get("metadatas") or []
        documents = result.get("documents") or []
        return [
            {
                "id": doc_id,
                "metadata": (metadatas[index] if index < len(metadatas) else None) or {},
                **(
                    {"document": (documents[index] if index < len(documents) else None) or ""}
                    if include_documents
                    else {}
                ),
            }
            for index, doc_id in enumerate(result_ids)
        ]
    except Exception as exc:
        logger.warning_structured(
            "ChromaDB selected-record read failed",
            extra_fields={"collection": collection_name, "error": str(exc), "count": len(requested)},
        )
        return []


def _graph_event_capture_enabled() -> bool:
    explicit = os.getenv("EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("EVIDENCE_GRAPH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _queue_evidence_graph_events(
    collection_name: str,
    *,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
    event_type: str,
) -> bool:
    """Persist graph events after a vector mutation and surface partial failure."""
    source_kind_by_collection = {
        CHROMA_COLLECTION_JIRA_QA: "jira",
        CHROMA_COLLECTION_AEM_GUIDES: "docs",
        CHROMA_COLLECTION_DITA_SPEC: "dita",
    }
    source_kind = source_kind_by_collection.get(collection_name)
    if not source_kind or not _graph_event_capture_enabled():
        return True
    grouped: dict[str, list[str]] = {}
    for index, doc_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
        if source_kind == "jira":
            record_id = str(metadata.get("jira_key") or str(doc_id).split("::", 1)[0]).strip().upper()
        else:
            record_id = str(doc_id).strip()
        if not record_id:
            continue
        document = documents[index] if index < len(documents) else ""
        fingerprint = str(
            metadata.get("chunk_content_hash")
            or metadata.get("source_content_hash")
            or metadata.get("source_file_hash")
            or ""
        )
        grouped.setdefault(record_id, []).append(
            fingerprint or hashlib.sha256(str(document).encode("utf-8", errors="ignore")).hexdigest()
        )
    if not grouped:
        return True
    try:
        from app.db.session import SessionLocal
        from app.services.evidence_graph_store import enqueue_source_event

        session = SessionLocal()
        try:
            for record_id, hashes in grouped.items():
                source_hash = hashlib.sha256(
                    json.dumps(sorted(hashes), separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                enqueue_source_event(
                    session,
                    source_kind=source_kind,
                    source_record_id=record_id,
                    source_hash=f"sha256:{source_hash}",
                    event_type=event_type,
                )
            session.commit()
            return True
        finally:
            session.close()
    except Exception as exc:
        logger.warning_structured(
            "Evidence graph source event capture failed",
            extra_fields={"collection": collection_name, "error": str(exc), "event_type": event_type},
        )
        return False


def iter_collection_records(
    collection_name: str,
    *,
    include_documents: bool = False,
    batch_size: int = 500,
    max_retries: int = 3,
):
    """Yield a complete Chroma collection scan without loading the corpus at once.

    Unlike ``get_collection_records``, this strict iterator raises when a page is
    missing or the final scanned count differs from the collection count. Graph
    rebuilds use that contract to avoid promoting partial generations.
    """
    import time

    client = _get_client()
    if not client or not _collection_exists(client, collection_name):
        raise RuntimeError(f"Chroma collection is unavailable: {collection_name}")
    collection = client.get_collection(name=collection_name)
    expected_count = int(collection.count())
    page_size = max(1, min(int(batch_size or 500), 5000))
    retries = max(1, min(int(max_retries or 3), 10))
    scanned = 0
    includes = ["metadatas", "documents"] if include_documents else ["metadatas"]

    while scanned < expected_count:
        result = None
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                result = collection.get(
                    limit=min(page_size, expected_count - scanned),
                    offset=scanned,
                    include=includes,
                )
                break
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(min(0.25 * (2 ** (attempt - 1)), 2.0))
        if result is None:
            raise RuntimeError(
                f"Chroma page scan failed for {collection_name} at offset {scanned}: {last_error}"
            )

        ids = result.get("ids") or []
        metadatas = result.get("metadatas") or []
        documents = result.get("documents") or []
        if not ids:
            raise RuntimeError(
                f"Chroma returned an empty page for {collection_name} at offset {scanned}; "
                f"expected {expected_count} records"
            )
        for index, doc_id in enumerate(ids):
            yield {
                "id": doc_id,
                "metadata": (metadatas[index] if index < len(metadatas) else None) or {},
                **(
                    {"document": (documents[index] if index < len(documents) else None) or ""}
                    if include_documents
                    else {}
                ),
            }
        scanned += len(ids)

    final_count = int(collection.count())
    if scanned != expected_count or final_count != expected_count:
        raise RuntimeError(
            f"Chroma scan count mismatch for {collection_name}: "
            f"scanned={scanned}, initial_count={expected_count}, final_count={final_count}"
        )


def get_documents_where(
    collection_name: str,
    where: dict,
    limit: int = 10,
) -> list[dict]:
    """Fetch documents matching a metadata filter from a ChromaDB collection.
    Returns list of dicts with keys: id, document, metadata.
    Returns [] when collection does not exist or filter matches nothing.
    """
    client = _get_client()
    if not client:
        return []
    if not _collection_exists(client, collection_name):
        return []
    try:
        coll = client.get_collection(name=collection_name)
        if coll.count() == 0:
            return []
        result = coll.get(
            where=where,
            limit=limit,
            include=["documents", "metadatas"],
        )
        if not result or not result.get("ids"):
            return []
        rows = []
        for i, doc_id in enumerate(result["ids"]):
            doc = (result["documents"][i] or "") if result.get("documents") else ""
            meta = (result["metadatas"][i] or {}) if result.get("metadatas") else {}
            rows.append({"id": doc_id, "document": doc, "metadata": meta})
        return rows
    except Exception as e:
        logger.warning_structured(
            "ChromaDB get_documents_where failed",
            extra_fields={"collection": collection_name, "error": str(e)},
        )
        return []
