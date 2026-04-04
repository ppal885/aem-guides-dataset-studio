from __future__ import annotations

import hashlib
import io
import json
import os
import re
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.structured_logging import get_structured_logger
from app.storage import get_storage

logger = get_structured_logger(__name__)

DEFAULT_GITHUB_DITA_SOURCE_URL = os.getenv(
    "GITHUB_DITA_SOURCE_URL",
    "https://github.com/oxygenxml/userguide/tree/master/DITA",
)
# Extra subtrees indexed when running "index all" (Oxygen userguide developer guide)
DEFAULT_GITHUB_DITA_EXTRA_SOURCES: list[str] = [
    "https://github.com/oxygenxml/userguide/tree/master/DITA/dev_guide",
]
MAX_FILE_BYTES = int(os.getenv("GITHUB_DITA_MAX_FILE_BYTES", str(512 * 1024)))
CHUNK_SIZE = int(os.getenv("GITHUB_DITA_CHUNK_SIZE", "1600"))
CHUNK_OVERLAP = int(os.getenv("GITHUB_DITA_CHUNK_OVERLAP", "250"))
SUPPORTED_EXTENSIONS = {".dita", ".ditamap", ".bookmap"}


def _tenant_config_for_github_index(tenant_id: str):
    """Chroma collection config for indexing. Resolves UI tenant_id 'default' without calling get_tenant('default').

    Older deployments raised ValueError for get_tenant('default'); this path uses the built-in kone seed directly.
    """
    from app.services.tenant_service import (
        DEFAULT_TENANT,
        _build_default_tenant,
        _load_tenant,
        get_tenant,
    )

    raw = str(tenant_id or "").strip().lower()
    if raw in ("", "default"):
        loaded = _load_tenant(DEFAULT_TENANT)
        return loaded if loaded is not None else _build_default_tenant()
    return get_tenant(raw)


@dataclass
class GitHubTreeSource:
    owner: str
    repo: str
    branch: str
    subtree: str
    source_url: str

    @property
    def archive_url(self) -> str:
        return f"https://codeload.github.com/{self.owner}/{self.repo}/zip/refs/heads/{self.branch}"

    @property
    def source_key(self) -> str:
        digest_input = f"{self.owner}/{self.repo}:{self.branch}:{self.subtree}".encode("utf-8")
        return hashlib.sha1(digest_input).hexdigest()[:12]

    @property
    def source_label(self) -> str:
        subtree = self.subtree.strip("/") or "repo root"
        return f"{self.owner}/{self.repo}:{self.branch}/{subtree}"


@dataclass
class GitHubDitaFile:
    path: str
    content: str
    topic_type: str
    title: str = ""


@dataclass
class GitHubDitaIndexResult:
    tenant_id: str
    source_url: str
    source_label: str
    files_indexed: int = 0
    example_chunks_stored: int = 0
    rag_chunks_stored: int = 0
    """Chunks also upserted into global `aem_guides` Chroma collection for chat RAG."""
    aem_guides_merged_chunks: int = 0
    skipped: bool = False
    errors: list[str] = field(default_factory=list)
    indexed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "source_url": self.source_url,
            "source_label": self.source_label,
            "files_indexed": self.files_indexed,
            "example_chunks_stored": self.example_chunks_stored,
            "rag_chunks_stored": self.rag_chunks_stored,
            "aem_guides_merged_chunks": self.aem_guides_merged_chunks,
            "skipped": self.skipped,
            "errors": self.errors,
            "indexed_at": self.indexed_at,
        }


def _registry_path() -> Path:
    path = get_storage().base_path / "github_dita_index_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_registry() -> dict:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_registry(payload: dict) -> None:
    _registry_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_github_dita_rag_summary(tenant_id: str = "default") -> dict:
    """
    Aggregate GitHub DITA index registry for Settings / GET rag-status.
    Chunks merged into chat RAG live in the global `aem_guides` collection; this reports registry totals.
    """
    registry = _load_registry()
    subtrees = 0
    merged_total = 0
    last_indexed = ""
    labels: list[str] = []
    prefix = f"{tenant_id}:"
    for key, rec in registry.items():
        if not isinstance(rec, dict):
            continue
        if not str(key).startswith(prefix):
            continue
        ex = int(rec.get("example_chunks_stored", 0) or 0)
        if ex <= 0:
            continue
        subtrees += 1
        merged_total += int(rec.get("aem_guides_merged_chunks", 0) or 0)
        lbl = rec.get("source_label") or rec.get("source_url") or str(key)
        labels.append(str(lbl))
        idx = (rec.get("indexed_at") or "").strip()
        if idx and (not last_indexed or idx > last_indexed):
            last_indexed = idx
    merge_enabled = _also_merge_github_to_aem_rag()
    return {
        "source": "Oxygen userguide & other GitHub DITA trees (zip download)",
        "indexed_subtrees": subtrees,
        "merged_into_aem_guides_chunks": merged_total,
        "merge_into_aem_guides_enabled": merge_enabled,
        "source_labels": labels[:24],
        "last_indexed_at": last_indexed,
        "populate_via": "POST /api/v1/ai/index-github-dita-examples",
    }


def _also_merge_github_to_aem_rag() -> bool:
    """When True, GitHub DITA chunks are also stored in the global `aem_guides` collection (used by chat)."""
    return os.getenv("GITHUB_DITA_ALSO_MERGE_TO_AEM_RAG", "true").lower() in ("true", "1", "yes")


def configured_github_dita_index_urls() -> list[str]:
    """
    Unique ordered URLs to index when running "index all": primary from env, defaults (incl. DITA/dev_guide),
    then GITHUB_DITA_ADDITIONAL_SOURCE_URLS (comma-separated).
    """
    seen: set[str] = set()
    out: list[str] = []
    primary = os.getenv("GITHUB_DITA_SOURCE_URL", DEFAULT_GITHUB_DITA_SOURCE_URL).strip()
    for u in [primary] + list(DEFAULT_GITHUB_DITA_EXTRA_SOURCES):
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    extra = os.getenv("GITHUB_DITA_ADDITIONAL_SOURCE_URLS", "").strip()
    if extra:
        for part in extra.split(","):
            u = part.strip()
            if u and u not in seen:
                seen.add(u)
                out.append(u)
    return out


def parse_github_tree_url(source_url: str) -> GitHubTreeSource:
    """
    Parse a GitHub URL pointing at a folder in a repo (branch + path).
    Accepts both /tree/ and /blob/ (browser often uses tree for folders; blob is accepted for compatibility).
    """
    raw = (source_url or DEFAULT_GITHUB_DITA_SOURCE_URL).strip()
    parsed = urllib.parse.urlparse(raw)
    host = (parsed.netloc or "").lower().split(":")[0]
    if parsed.scheme not in {"http", "https"} or host not in ("github.com", "www.github.com"):
        raise ValueError("source_url must be a github.com URL")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4 or parts[2] not in ("tree", "blob"):
        raise ValueError(
            "source_url must look like https://github.com/<owner>/<repo>/(tree|blob)/<branch>/<path>"
        )

    owner, repo = parts[0], parts[1]
    branch = parts[3]
    subtree = "/".join(parts[4:]).strip("/") or "DITA"
    canonical = (
        f"https://github.com/{owner}/{repo}/tree/{branch}/{subtree}"
        if subtree
        else f"https://github.com/{owner}/{repo}/tree/{branch}"
    )
    return GitHubTreeSource(
        owner=owner,
        repo=repo,
        branch=branch,
        subtree=subtree,
        source_url=canonical,
    )


def _download_zip_bytes(source: GitHubTreeSource) -> bytes:
    request = urllib.request.Request(
        source.archive_url,
        headers={"User-Agent": "AEM-Guides-Dataset-Studio/1.0 (github-dita-indexer)"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _decode_member(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode file content")


def _extract_title(content: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(1))).strip()


def _infer_topic_type(path: str, content: str) -> str:
    lowered = content.lower()
    for tag in ("task", "concept", "reference", "topic", "glossentry", "ditamap", "bookmap"):
        if f"<{tag}" in lowered or f"doctype {tag}" in lowered:
            return tag
    suffix = Path(path).suffix.lower()
    if suffix == ".ditamap":
        return "ditamap"
    if suffix == ".bookmap":
        return "bookmap"
    return "topic"


def _iter_dita_files_from_zip(
    zip_bytes: bytes,
    *,
    subtree: str,
    max_files: int = 400,
    include_maps: bool = True,
) -> list[GitHubDitaFile]:
    dita_files: list[GitHubDitaFile] = []
    subtree_parts = [part for part in subtree.split("/") if part]

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for member in archive.infolist():
            if member.is_dir() or member.file_size <= 0 or member.file_size > MAX_FILE_BYTES:
                continue
            parts = [part for part in member.filename.split("/") if part]
            if len(parts) < 2:
                continue
            relative_parts = parts[1:]
            if subtree_parts and relative_parts[: len(subtree_parts)] != subtree_parts:
                continue
            suffix = Path(member.filename).suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                continue
            if not include_maps and suffix in {".ditamap", ".bookmap"}:
                continue
            raw = archive.read(member)
            try:
                content = _decode_member(raw)
            except ValueError:
                continue
            relative_path = "/".join(relative_parts)
            dita_files.append(
                GitHubDitaFile(
                    path=relative_path,
                    content=content,
                    topic_type=_infer_topic_type(relative_path, content),
                    title=_extract_title(content),
                )
            )
            if len(dita_files) >= max_files:
                break
    return dita_files


def _chunk_document(content: str) -> list[str]:
    normalized = (content or "").strip()
    if not normalized:
        return []
    if len(normalized) <= CHUNK_SIZE:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + CHUNK_SIZE)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(0, end - CHUNK_OVERLAP)
    return chunks


def _registry_key(tenant_id: str, source: GitHubTreeSource) -> str:
    return f"{tenant_id}:{source.source_key}"


def get_github_dita_status(tenant_id: str, source_url: str = DEFAULT_GITHUB_DITA_SOURCE_URL) -> dict:
    try:
        source = parse_github_tree_url(source_url)
    except Exception:
        return {
            "source": source_url,
            "chunk_count": 0,
            "files_indexed": 0,
            "example_chunk_count": 0,
            "rag_chunk_count": 0,
            "aem_guides_merged_chunk_count": 0,
            "populate_via": "POST /api/v1/ai/index-github-dita-examples",
        }
    record = _load_registry().get(_registry_key(tenant_id, source), {})
    return {
        "source": f"GitHub DITA examples ({source.source_label})",
        "source_url": source.source_url,
        "chunk_count": int(record.get("example_chunks_stored", 0) or 0),
        "files_indexed": int(record.get("files_indexed", 0) or 0),
        "example_chunk_count": int(record.get("example_chunks_stored", 0) or 0),
        "rag_chunk_count": int(record.get("rag_chunks_stored", 0) or 0),
        "aem_guides_merged_chunk_count": int(record.get("aem_guides_merged_chunks", 0) or 0),
        "indexed_at": record.get("indexed_at", ""),
        "populate_via": "POST /api/v1/ai/index-github-dita-examples",
    }


async def index_github_dita_examples(
    *,
    tenant_id: str,
    source_url: str = DEFAULT_GITHUB_DITA_SOURCE_URL,
    max_files: int = 400,
    include_maps: bool = True,
    index_into_rag: bool = True,
) -> GitHubDitaIndexResult:
    from app.services.embedding_service import embed_texts, is_embedding_available
    from app.services.vector_store_service import (
        CHROMA_COLLECTION_AEM_GUIDES,
        add_documents,
        delete_documents,
        is_chroma_available,
    )

    source = parse_github_tree_url(source_url)
    result = GitHubDitaIndexResult(
        tenant_id=tenant_id,
        source_url=source.source_url,
        source_label=source.source_label,
    )

    if not is_chroma_available():
        result.errors.append("ChromaDB is not available.")
        return result
    if not is_embedding_available():
        result.errors.append("Embedding model is not available.")
        return result

    zip_bytes = _download_zip_bytes(source)
    dita_files = _iter_dita_files_from_zip(
        zip_bytes,
        subtree=source.subtree,
        max_files=max_files,
        include_maps=include_maps,
    )
    if not dita_files:
        result.errors.append("No DITA files were found in the selected GitHub subtree.")
        return result

    registry = _load_registry()
    previous = registry.get(_registry_key(tenant_id, source), {})
    old_example_ids = list(previous.get("example_ids") or [])
    old_rag_ids = list(previous.get("rag_ids") or [])
    old_aem_ids = list(previous.get("aem_guides_merged_ids") or [])

    config = _tenant_config_for_github_index(tenant_id)
    if old_example_ids:
        delete_documents(config.examples_collection, old_example_ids)
    if old_rag_ids:
        delete_documents(config.rag_collection, old_rag_ids)
    if old_aem_ids:
        delete_documents(CHROMA_COLLECTION_AEM_GUIDES, old_aem_ids)

    chunk_payloads: list[dict] = []
    for dita_file in dita_files:
        for chunk_index, chunk in enumerate(_chunk_document(dita_file.content)):
            chunk_payloads.append(
                {
                    "path": dita_file.path,
                    "content": chunk,
                    "topic_type": dita_file.topic_type,
                    "title": dita_file.title,
                    "chunk_index": chunk_index,
                }
            )

    if not chunk_payloads:
        result.errors.append("No usable DITA chunks were produced from the GitHub source.")
        return result

    texts = [item["content"] for item in chunk_payloads]
    embeddings_raw = embed_texts(texts)
    if embeddings_raw is None:
        result.errors.append("Failed to embed GitHub DITA examples.")
        return result
    embeddings = embeddings_raw.tolist() if hasattr(embeddings_raw, "tolist") else list(embeddings_raw)

    base_id = f"github_dita_{tenant_id}_{source.source_key}"
    example_ids = [f"{base_id}_example_{index}" for index in range(len(chunk_payloads))]
    example_meta = [
        {
            "filename": Path(item["path"]).name,
            "path": item["path"],
            "topic_type": item["topic_type"],
            "title": item["title"],
            "chunk_index": item["chunk_index"],
            "source": "oxygen_github_example",
            "source_url": source.source_url,
            "tenant_id": tenant_id,
            "repo": source.source_label,
        }
        for item in chunk_payloads
    ]
    examples_ok = add_documents(
        config.examples_collection,
        ids=example_ids,
        documents=texts,
        metadatas=example_meta,
        embeddings=embeddings,
    )
    if not examples_ok:
        result.errors.append("Failed to store GitHub DITA examples in the examples collection.")
        return result

    aem_merged_ids: list[str] = []
    if _also_merge_github_to_aem_rag():
        aem_merged_ids = [f"ghdita_{source.source_key}_{i}" for i in range(len(chunk_payloads))]
        aem_meta = [
            {
                "url": f"https://github.com/{source.owner}/{source.repo}/blob/{source.branch}/{item['path']}",
                "title": (item["title"] or "").strip() or Path(item["path"]).name,
                "source": "github_dita",
                "source_url": source.source_url,
                "path": str(item["path"]),
                "tenant_id": tenant_id,
                "repo": source.source_label,
            }
            for item in chunk_payloads
        ]
        aem_ok = add_documents(
            CHROMA_COLLECTION_AEM_GUIDES,
            ids=aem_merged_ids,
            documents=texts,
            metadatas=aem_meta,
            embeddings=embeddings,
        )
        if not aem_ok:
            result.errors.append(
                "Failed to merge GitHub DITA chunks into global chat RAG collection (aem_guides)."
            )
            aem_merged_ids = []
        else:
            result.aem_guides_merged_chunks = len(aem_merged_ids)

    rag_ids: list[str] = []
    if index_into_rag:
        rag_ids = [f"{base_id}_rag_{index}" for index in range(len(chunk_payloads))]
        rag_meta = [
            {
                "filename": Path(item["path"]).name,
                "path": item["path"],
                "topic_type": item["topic_type"],
                "label": item["title"] or Path(item["path"]).name,
                "chunk_index": item["chunk_index"],
                "source": "oxygen_github_rag",
                "source_url": source.source_url,
                "tenant_id": tenant_id,
                "doc_type": "approved_topic",
                "repo": source.source_label,
            }
            for item in chunk_payloads
        ]
        rag_ok = add_documents(
            config.rag_collection,
            ids=rag_ids,
            documents=texts,
            metadatas=rag_meta,
            embeddings=embeddings,
        )
        if not rag_ok:
            result.errors.append("Failed to store GitHub DITA examples in the tenant RAG collection.")
            return result

    result.files_indexed = len(dita_files)
    result.example_chunks_stored = len(example_ids)
    result.rag_chunks_stored = len(rag_ids)

    registry[_registry_key(tenant_id, source)] = {
        "tenant_id": tenant_id,
        "source_url": source.source_url,
        "source_label": source.source_label,
        "files_indexed": result.files_indexed,
        "example_chunks_stored": result.example_chunks_stored,
        "rag_chunks_stored": result.rag_chunks_stored,
        "aem_guides_merged_chunks": result.aem_guides_merged_chunks,
        "example_ids": example_ids,
        "rag_ids": rag_ids,
        "aem_guides_merged_ids": aem_merged_ids,
        "indexed_at": result.indexed_at,
    }
    _save_registry(registry)
    logger.info_structured(
        "Indexed GitHub DITA examples",
        extra_fields={
            "tenant_id": tenant_id,
            "source": source.source_label,
            "files": result.files_indexed,
            "example_chunks": result.example_chunks_stored,
            "rag_chunks": result.rag_chunks_stored,
            "aem_guides_merged": result.aem_guides_merged_chunks,
        },
    )
    return result


async def index_all_github_dita_examples(
    *,
    tenant_id: str,
    max_files: int = 400,
    include_maps: bool = True,
    index_into_rag: bool = True,
) -> list[GitHubDitaIndexResult]:
    """Index every URL from `configured_github_dita_index_urls()` (primary + dev_guide + extras)."""
    out: list[GitHubDitaIndexResult] = []
    for url in configured_github_dita_index_urls():
        out.append(
            await index_github_dita_examples(
                tenant_id=tenant_id,
                source_url=url,
                max_files=max_files,
                include_maps=include_maps,
                index_into_rag=index_into_rag,
            )
        )
    return out
