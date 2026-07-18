#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Index converted Experience League DITA topics as behavior knowledge chunks.

This is an offline-first ingestion utility. By default it reads converted DITA
topics, produces a JSON audit file, and does not mutate ChromaDB. Pass
``--upsert-chroma`` only after reviewing the JSON output.

Examples:
    python scripts/index_dita_behavior_corpus.py
    python scripts/index_dita_behavior_corpus.py --limit 25 --sample-output tmp/behavior_sample.json
    python scripts/index_dita_behavior_corpus.py --upsert-chroma
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from lxml import etree


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
for candidate in (PROJECT_ROOT, BACKEND_DIR):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)


DEFAULT_CORPUS_ROOT = PROJECT_ROOT / "experienceleague-dita-corpus" / "topics"
DEFAULT_OUTPUT = PROJECT_ROOT / "backend" / "storage" / "aem_guides_behavior_chunks.json"
DEFAULT_ALLOWED_PREFIXES = (
    "https://experienceleague.adobe.com/",
    "https://github.com/dita-ot/dita-ot/issues/",
)
CHUNK_VERSION = "dita-behavior-chunker/1.0"
MAX_CHARS = 1400
MIN_CHARS = 80

BOILERPLATE_PATTERNS = (
    re.compile(r"^Documentation$", re.I),
    re.compile(r"^Last update:", re.I),
    re.compile(r"^Topics:$", re.I),
    re.compile(r"^CREATED FOR:$", re.I),
    re.compile(r"^Recommended tutorials on this topic$", re.I),
    re.compile(r"^recommendation-more-help$", re.I),
)


def read_topic_text(path: Path) -> str:
    """Read generated DITA topics, including legacy files written with Windows encodings."""
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")

BEHAVIOR_HINTS = re.compile(
    r"\b("
    r"can|cannot|will|won't|does not|do not|must|should|supports?|allows?|enables?|"
    r"select|click|open|create|save|generate|publish|validate|configure|import|copy|"
    r"default|fallback|override|inherit|retry|error|warning|fails?|blocked|"
    r"output|baseline|schematron|metadata|translation|preset|map|topic"
    r")\b",
    re.I,
)


@dataclass
class CandidateBlock:
    section_path: list[str]
    kind: str
    text: str


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-output", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0, help="limit DITA files read; 0 means all")
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS)
    parser.add_argument("--min-chars", type=int, default=MIN_CHARS)
    parser.add_argument(
        "--include-out-of-scope",
        action="store_true",
        help="include non-Experience League URLs too; Experience League is included by default",
    )
    parser.add_argument(
        "--allowed-source-prefix",
        action="append",
        default=list(DEFAULT_ALLOWED_PREFIXES),
        help="allowed canonical/source URL prefix; can be repeated",
    )
    parser.add_argument("--upsert-chroma", action="store_true")
    parser.add_argument("--batch-size", type=int, default=64)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    dita_files = sorted(args.corpus_root.rglob("*.dita"))
    if args.limit > 0:
        dita_files = dita_files[: args.limit]

    records: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for path in dita_files:
        try:
            topic_records = topic_to_behavior_records(
                path,
                corpus_root=args.corpus_root,
                allowed_prefixes=tuple(args.allowed_source_prefix or ()),
                include_out_of_scope=args.include_out_of_scope,
                max_chars=args.max_chars,
                min_chars=args.min_chars,
            )
        except Exception as exc:
            skipped.append({"path": str(path), "reason": f"parse_error: {exc}"})
            continue
        if topic_records:
            records.extend(topic_records)
        else:
            skipped.append({"path": str(path), "reason": "no behavior chunks"})

    records = dedupe_records(records)
    link_neighbors(records)
    write_json(args.output, records)
    if args.sample_output:
        write_json(args.sample_output, records[: min(25, len(records))])

    chroma_upserted = 0
    if args.upsert_chroma and records:
        chroma_upserted = upsert_to_chroma(records, batch_size=max(1, args.batch_size))

    print(
        json.dumps(
            {
                "files_seen": len(dita_files),
                "chunks_written": len(records),
                "output": str(args.output),
                "sample_output": str(args.sample_output) if args.sample_output else "",
                "skipped": len(skipped),
                "chroma_upserted": chroma_upserted,
                "mode": "upsert" if args.upsert_chroma else "json-only",
            },
            indent=2,
        )
    )
    return 0


def topic_to_behavior_records(
    path: Path,
    *,
    corpus_root: Path,
    allowed_prefixes: tuple[str, ...],
    include_out_of_scope: bool,
    max_chars: int,
    min_chars: int,
) -> list[dict[str, Any]]:
    root = parse_dita(path)
    meta = extract_metadata(root)
    derived_url = derive_source_url(path)
    source_url = meta.get("source-url") or meta.get("canonical-url") or derived_url
    canonical_url = meta.get("canonical-url") or source_url or derived_url
    if not include_out_of_scope and not is_allowed_source(source_url, canonical_url, allowed_prefixes):
        return []

    title = clean_text(first_text(root, "title"))
    shortdesc = clean_text(first_text(root, "shortdesc"))
    relpath = path.relative_to(corpus_root).as_posix()
    blocks = extract_blocks(root)
    grouped = group_blocks(blocks, max_chars=max_chars, min_chars=min_chars)

    records: list[dict[str, Any]] = []
    base_text = f"{title}\n{shortdesc}".strip()
    if base_text and len(base_text) >= min_chars:
        records.append(
            make_record(
                relpath=relpath,
                source_url=source_url,
                canonical_url=canonical_url,
                title=title,
                section_path=[],
                content=base_text,
                evidence_type="summary",
                ordinal=0,
                metadata=meta,
            )
        )

    for ordinal, block in enumerate(grouped, start=1):
        evidence_type = classify_evidence(block.text)
        records.append(
            make_record(
                relpath=relpath,
                source_url=source_url,
                canonical_url=canonical_url,
                title=title,
                section_path=block.section_path,
                content=block.text,
                evidence_type=evidence_type,
                ordinal=ordinal,
                metadata=meta,
            )
        )
    return records


def parse_dita(path: Path) -> etree._Element:
    text = read_topic_text(path)
    text = re.sub(r"<!DOCTYPE[^>]+>\s*", "", text)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True, remove_blank_text=True)
    root = etree.fromstring(text.encode("utf-8"), parser)
    if root.tag != "topic":
        raise ValueError(f"expected <topic>, got <{root.tag}>")
    return root


def extract_metadata(root: etree._Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in root.xpath("./prolog/metadata/othermeta"):
        name = str(node.get("name") or "").strip()
        content = str(node.get("content") or "").strip()
        if name and content:
            out[name] = repair_mojibake(content)
    return out


def extract_blocks(root: etree._Element) -> list[CandidateBlock]:
    body = root.find("body")
    if body is None:
        return []
    blocks: list[CandidateBlock] = []
    walk_children(body, [], blocks)
    return blocks


def walk_children(parent: etree._Element, section_path: list[str], blocks: list[CandidateBlock]) -> None:
    for child in parent:
        tag = local_name(child)
        if tag == "section":
            title = clean_text(first_text(child, "title"))
            next_path = [*section_path, title] if title and not is_boilerplate(title) else list(section_path)
            walk_children(child, next_path, blocks)
        elif tag in {"p", "note", "codeblock"}:
            text = element_text(child, preserve_space=(tag == "codeblock"))
            add_block(blocks, section_path, tag, text)
        elif tag in {"ul", "ol"}:
            list_text = list_to_text(child)
            add_block(blocks, section_path, tag, list_text)
        elif tag in {"simpletable", "table"}:
            table_text = table_to_text(child)
            add_block(blocks, section_path, tag, table_text)
        elif tag in {"title", "prolog"}:
            continue
        else:
            text = element_text(child)
            add_block(blocks, section_path, tag, text)


def add_block(blocks: list[CandidateBlock], section_path: list[str], kind: str, text: str) -> None:
    text = clean_text(text)
    if not text or is_boilerplate(text):
        return
    if not BEHAVIOR_HINTS.search(text) and len(text) < 220:
        return
    blocks.append(CandidateBlock(section_path=list(section_path), kind=kind, text=text))


def group_blocks(blocks: list[CandidateBlock], *, max_chars: int, min_chars: int) -> list[CandidateBlock]:
    grouped: list[CandidateBlock] = []
    current_path: list[str] = []
    current_parts: list[str] = []
    current_kind = "behavior"

    def flush() -> None:
        nonlocal current_parts
        text = "\n".join(part for part in current_parts if part).strip()
        current_parts = []
        if len(text) >= min_chars:
            grouped.append(CandidateBlock(current_path, current_kind, text))

    for block in blocks:
        if current_parts and (block.section_path != current_path or len("\n".join(current_parts)) + len(block.text) > max_chars):
            flush()
        current_path = block.section_path
        current_parts.append(block.text)
    flush()
    return grouped


def make_record(
    *,
    relpath: str,
    source_url: str,
    canonical_url: str,
    title: str,
    section_path: list[str],
    content: str,
    evidence_type: str,
    ordinal: int,
    metadata: dict[str, str],
) -> dict[str, Any]:
    section = " > ".join(part for part in section_path if part)
    chunk_seed = f"{canonical_url or source_url}|{relpath}|{section}|{ordinal}|{content}"
    chunk_id = "aem_guides_behavior_" + hashlib.sha256(chunk_seed.encode("utf-8")).hexdigest()[:24]
    return {
        "id": chunk_id,
        "chunk_id": chunk_id,
        "url": source_url or canonical_url,
        "source_url": source_url,
        "canonical_url": canonical_url,
        "dita_path": relpath,
        "title": title,
        "section": section,
        "section_path": section_path,
        "content": content,
        "chunk_index": ordinal,
        "evidence_type": evidence_type,
        "feature_area": infer_feature_area(canonical_url or source_url, title, section, content),
        "source_product_family": infer_source_product_family(canonical_url or source_url),
        "source_type": metadata.get("source-type", "official-experience-league"),
        "product": metadata.get("product", ""),
        "source_language": metadata.get("source-language", ""),
        "source_last_updated": metadata.get("source-last-updated", ""),
        "crawled_at": metadata.get("crawled-at", ""),
        "source_content_hash": metadata.get("content-hash", ""),
        "chunk_content_hash": "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "chunker_version": CHUNK_VERSION,
        "neighbor_prev_id": "",
        "neighbor_next_id": "",
    }


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        key = (record.get("canonical_url") or record.get("source_url") or "", record.get("chunk_content_hash") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def link_neighbors(records: list[dict[str, Any]]) -> None:
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_doc.setdefault(str(record.get("dita_path") or ""), []).append(record)
    for doc_records in by_doc.values():
        doc_records.sort(key=lambda row: int(row.get("chunk_index") or 0))
        for index, record in enumerate(doc_records):
            if index > 0:
                record["neighbor_prev_id"] = doc_records[index - 1]["id"]
            if index + 1 < len(doc_records):
                record["neighbor_next_id"] = doc_records[index + 1]["id"]


def upsert_to_chroma(records: list[dict[str, Any]], *, batch_size: int) -> int:
    from app.services.embedding_service import embed_texts, embed_texts_batched, is_embedding_available
    from app.services.vector_store_service import CHROMA_COLLECTION_AEM_GUIDES, add_documents, is_chroma_available

    if not is_chroma_available():
        print("WARN: ChromaDB unavailable; wrote JSON only")
        return 0
    if not is_embedding_available():
        print("WARN: embedding model unavailable; wrote JSON only")
        return 0

    stored = 0
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        texts = [str(row["content"]) for row in batch]
        embeddings = embed_texts_batched(texts) if len(texts) > 32 else embed_texts(texts)
        if embeddings is None:
            continue
        metadatas = [chroma_metadata(row) for row in batch]
        ok = add_documents(
            CHROMA_COLLECTION_AEM_GUIDES,
            ids=[str(row["id"]) for row in batch],
            documents=texts,
            metadatas=metadatas,
            embeddings=[embeddings[i].tolist() for i in range(len(batch))],
        )
        if ok:
            stored += len(batch)
    return stored


def chroma_metadata(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "url",
        "source_url",
        "canonical_url",
        "dita_path",
        "title",
        "section",
        "chunk_index",
        "evidence_type",
        "feature_area",
        "source_product_family",
        "source_type",
        "product",
        "source_language",
        "source_last_updated",
        "source_content_hash",
        "chunk_content_hash",
        "chunker_version",
        "neighbor_prev_id",
        "neighbor_next_id",
    )
    return {key: row.get(key, "") for key in keys}


def is_allowed_source(source_url: str, canonical_url: str, prefixes: tuple[str, ...]) -> bool:
    candidate_urls = [source_url or "", canonical_url or ""]
    for value in candidate_urls:
        if any(value.startswith(prefix) for prefix in prefixes):
            return True
    return False


def classify_evidence(text: str) -> str:
    lowered = text.lower()
    if "error" in lowered or "warning" in lowered or "fail" in lowered:
        return "failure_behavior"
    if "configure" in lowered or "setting" in lowered or "profile" in lowered:
        return "configuration_behavior"
    if "generate" in lowered or "publish" in lowered or "output" in lowered:
        return "output_behavior"
    if "select" in lowered or "click" in lowered or "open" in lowered or "save" in lowered:
        return "ui_workflow_behavior"
    if "default" in lowered or "fallback" in lowered or "inherit" in lowered:
        return "default_behavior"
    return "behavior"


def infer_feature_area(*parts: str) -> str:
    text = " ".join(parts).lower()
    candidates = [
        ("baseline", "baseline"),
        ("schematron", "schematron-validation"),
        ("validation", "validation"),
        ("translation", "translation"),
        ("metadata", "metadata"),
        ("map collection", "map-collection"),
        ("output preset", "output-presets"),
        ("preset", "output-presets"),
        ("native pdf", "native-pdf"),
        ("dita-ot", "dita-ot"),
        ("condition", "conditional-content"),
        ("ditaval", "conditional-content"),
        ("review", "review"),
        ("editor", "web-editor"),
        ("map", "map-management"),
    ]
    for needle, area in candidates:
        if needle in text:
            return area
    path = urlparse(parts[0] if parts else "").path.lower()
    segments = [seg for seg in path.split("/") if seg]
    if "user-guide" in segments:
        idx = segments.index("user-guide")
        if idx + 1 < len(segments):
            return segments[idx + 1]
    return "aem-guides"


def infer_source_product_family(url: str) -> str:
    parsed = urlparse(url or "")
    path = parsed.path.lower()
    if parsed.netloc.lower() == "github.com" and path.startswith("/dita-ot/dita-ot/"):
        return "dita-ot"
    markers = (
        ("experience-manager-guides", "aem-guides"),
        ("experience-manager-guides-learn", "aem-guides"),
        ("workfront", "workfront"),
        ("analytics", "analytics"),
        ("commerce", "commerce"),
        ("campaign", "campaign"),
        ("journey-optimizer", "journey-optimizer"),
        ("target", "target"),
        ("experience-manager", "experience-manager"),
        ("creative-cloud", "creative-cloud"),
    )
    for marker, family in markers:
        if marker in path:
            return family
    segments = [segment for segment in path.split("/") if segment]
    if "docs" in segments:
        index = segments.index("docs")
        if index + 1 < len(segments):
            return segments[index + 1]
    return "experience-league"


def list_to_text(element: etree._Element) -> str:
    items = []
    for li in element.xpath("./*[local-name()='li']"):
        text = element_text(li)
        if text:
            items.append(f"- {text}")
    return "\n".join(items)


def table_to_text(element: etree._Element) -> str:
    rows = []
    for row in element.xpath(".//*[local-name()='strow' or local-name()='row']"):
        cells = [element_text(cell) for cell in row]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def first_text(element: etree._Element, tag: str) -> str:
    found = element.find(tag)
    return element_text(found) if found is not None else ""


def element_text(element: etree._Element | None, *, preserve_space: bool = False) -> str:
    if element is None:
        return ""
    if preserve_space:
        return repair_mojibake("".join(element.itertext()))
    return " ".join(repair_mojibake(text) for text in element.itertext())


def clean_text(text: str) -> str:
    text = repair_mojibake(text)
    text = text.replace("\u200b", "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def repair_mojibake(text: str) -> str:
    if not text or "â" not in text:
        return text
    try:
        repaired = text.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
    except UnicodeError:
        replacements = {
            "â€œ": "“",
            "â€\x9d": "”",
            "â€": "”",
            "â€˜": "‘",
            "â€™": "’",
            "â€\x99": "’",
            "â€”": "—",
            "â€“": "–",
            "â€‘": "‑",
            "â€¢": "•",
            "â€¦": "…",
            "â€‹": "",
            "Â ": " ",
            "Â": "",
        }
        repaired = text
        for bad, good in replacements.items():
            repaired = repaired.replace(bad, good)
        return repaired
    return repaired if repaired.count("\ufffd") <= text.count("\ufffd") else text


def derive_source_url(path: Path) -> str:
    """Derive Experience League URL from mirrored topics path when prolog is absent."""
    parts = list(path.with_suffix("").parts)
    try:
        index = parts.index("topics")
        rel_parts = parts[index + 1 :]
    except ValueError:
        rel_parts = parts
    if not rel_parts:
        return ""
    rel = "/".join(rel_parts)
    return f"https://experienceleague.adobe.com/{rel}"


def is_boilerplate(text: str) -> bool:
    cleaned = clean_text(text).strip()
    if not cleaned:
        return True
    if cleaned.startswith("https://video.tv.adobe.com/"):
        return True
    if cleaned.endswith("/eng.json") and "video.tv.adobe.com" in cleaned:
        return True
    return any(pattern.search(cleaned) for pattern in BOILERPLATE_PATTERNS)


def local_name(element: etree._Element) -> str:
    return etree.QName(element).localname if isinstance(element.tag, str) else ""


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
