#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build high-signal behavior chunks from scraped Experience League DITA.

The raw Experience League scrape is intentionally broad. This script converts
that corpus into retrieval-friendly learned behavior chunks for AEM Guides QA,
publishing, integration, and DITA-OT data-generation flows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
for candidate in (PROJECT_ROOT, BACKEND_DIR, Path(__file__).resolve().parent):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from index_dita_behavior_corpus import (  # noqa: E402
    CandidateBlock,
    clean_text,
    derive_source_url,
    extract_blocks,
    extract_metadata,
    first_text,
    infer_dita_construct_signals,
    infer_output_terms,
    parse_dita,
    upsert_to_chroma,
    write_json,
)


DEFAULT_CORPUS_ROOT = PROJECT_ROOT / "experienceleague-dita-corpus" / "topics"
DEFAULT_OUTPUT = PROJECT_ROOT / "backend" / "storage" / "aem_guides_enriched_behavior_chunks.json"
CHUNK_VERSION = "experienceleague-enriched-behavior/1.0"
MAX_CONTENT_CHARS = 2200

DITA_ATTRIBUTE_TERMS = (
    "audience",
    "chunk",
    "conaction",
    "conkeyref",
    "conref",
    "conrefend",
    "copy-to",
    "deliverytarget",
    "ditaval",
    "format",
    "href",
    "keyref",
    "keys",
    "keyscope",
    "linking",
    "otherprops",
    "platform",
    "print",
    "processing-role",
    "product",
    "props",
    "rev",
    "scope",
    "translate",
    "type",
    "xml:lang",
)

ELEMENT_TERMS = (
    "chapter",
    "conbody",
    "conrefpush",
    "ditamap",
    "image",
    "keydef",
    "map",
    "mapref",
    "reltable",
    "topic",
    "topicref",
    "xref",
)

FEATURE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dita-ot-publishing", ("dita-ot", "dita ot", "pdf", "pdf2", "html5", "xhtml", "publish", "output preset")),
    ("native-pdf", ("native pdf", "template", "page layout", "css paged", "pdf template")),
    ("branch-filtering", ("ditaval", "conditional processing", "profile", "profiling", "audience", "platform", "props", "print")),
    ("map-management", ("map console", "ditamap", "map collection", "topicref", "baseline", "open files")),
    ("translation-localization", ("translation", "translate", "language copy", "xml:lang", "locale")),
    ("metadata-taxonomy", ("metadata", "properties", "smart tag", "tags", "taxonomy")),
    ("reports-analysis", ("report", "reports", "content reuse", "topic list", "reverted file")),
    ("integration-workflow", ("workfront", "integration", "connector", "aem assets", "asset link", "translation project")),
    ("authoring-editor", ("web editor", "editor", "author", "review", "schematron", "validation")),
)

UNRELATED_PRODUCT_FAMILIES = {
    "acrobat-services-learn",
    "analytics",
    "analytics-platform",
    "campaign",
    "commerce-admin",
    "customer-journey-analytics",
    "dynamic-media-classic",
    "journey-optimizer",
    "marketo",
    "target",
}

GUIDES_PRODUCT_FAMILIES = {
    "experience-manager-guides",
    "experience-manager-guides-learn",
}

RELATED_AEM_PRODUCT_FAMILIES = {
    "experience-manager-65",
    "experience-manager-65-lts",
    "experience-manager-cloud-service",
    "experience-manager-learn",
    "workfront",
}

LOW_VALUE_TITLES = {
    "disclaimer",
}


@dataclass(frozen=True)
class TopicEvidence:
    path: Path
    relpath: str
    title: str
    shortdesc: str
    source_url: str
    canonical_url: str
    metadata: dict[str, str]
    blocks: list[CandidateBlock]
    body_text: str


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus-root",
        type=Path,
        action="append",
        default=None,
        help="DITA topic corpus root; can be repeated. Defaults to experienceleague-dita-corpus/topics",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=0, help="Limit DITA files read; 0 means all")
    parser.add_argument("--max-chunks", type=int, default=8000)
    parser.add_argument("--sample-output", type=Path, default=None)
    parser.add_argument("--upsert-chroma", action="store_true")
    parser.add_argument("--batch-size", type=int, default=64)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    corpus_roots = args.corpus_root or [DEFAULT_CORPUS_ROOT]
    dita_entries: list[tuple[Path, Path]] = []
    for corpus_root in corpus_roots:
        dita_entries.extend((path, corpus_root) for path in sorted(corpus_root.rglob("*.dita")))
    if args.limit > 0:
        dita_entries = dita_entries[: args.limit]

    records: list[dict[str, Any]] = []
    skipped = 0
    for path, corpus_root in dita_entries:
        evidence = load_topic_evidence(path, corpus_root)
        if not evidence or not should_include(evidence):
            skipped += 1
            continue
        records.extend(build_enriched_records(evidence))

    records = dedupe_records(records)
    records.sort(key=record_sort_key)
    if args.max_chunks > 0:
        records = records[: args.max_chunks]
    relink_neighbors(records)
    write_json(args.output, records)
    if args.sample_output:
        write_json(args.sample_output, records[: min(50, len(records))])
    chroma_upserted = 0
    if args.upsert_chroma and records:
        chroma_upserted = upsert_to_chroma(records, batch_size=max(1, args.batch_size))

    print(
        json.dumps(
            {
                "files_seen": len(dita_entries),
                "corpus_roots": [str(root) for root in corpus_roots],
                "files_skipped": skipped,
                "chunks_written": len(records),
                "output": str(args.output),
                "sample_output": str(args.sample_output) if args.sample_output else "",
                "chroma_upserted": chroma_upserted,
                "mode": "upsert" if args.upsert_chroma else "json-only",
                "chunker_version": CHUNK_VERSION,
                "feature_areas": summarize_feature_areas(records),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def load_topic_evidence(path: Path, corpus_root: Path) -> TopicEvidence | None:
    try:
        root = parse_dita(path)
    except Exception:
        return None
    metadata = extract_metadata(root)
    derived_url = derive_source_url(path)
    source_url = metadata.get("source-url") or metadata.get("canonical-url") or derived_url
    canonical_url = metadata.get("canonical-url") or source_url or derived_url
    title = clean_text(first_text(root, "title"))
    shortdesc = clean_text(first_text(root, "shortdesc"))
    blocks = extract_blocks(root)
    body_text = clean_text("\n".join(block.text for block in blocks))
    try:
        relpath = path.relative_to(corpus_root).as_posix()
    except ValueError:
        relpath = path.as_posix()
    return TopicEvidence(
        path=path,
        relpath=relpath,
        title=title,
        shortdesc=shortdesc,
        source_url=source_url,
        canonical_url=canonical_url,
        metadata=metadata,
        blocks=blocks,
        body_text=body_text,
    )


def should_include(evidence: TopicEvidence) -> bool:
    url = evidence.canonical_url or evidence.source_url
    text = f"{url}\n{evidence.title}\n{evidence.shortdesc}\n{evidence.body_text}".lower()
    family = infer_source_product_family(url)
    title = evidence.title.strip().lower()
    strong_constructs = {
        term
        for term in detect_constructs(text)
        if term
        not in {
            "image",
            "map",
            "topic",
            "type",
            "format",
            "href",
            "scope",
            "xref",
        }
    }
    feature_hits = detect_feature_areas(text)

    if title in LOW_VALUE_TITLES:
        return False
    if evidence.shortdesc.lower().startswith("search for self-help articles and tutorials"):
        return False

    if family in GUIDES_PRODUCT_FAMILIES or "/experience-manager-guides/" in url:
        return True
    if "aem guides" in text or "experience manager guides" in text:
        return True
    if "xml documentation" in text and ("dita" in text or "aem" in text):
        return True
    if family.startswith("workfront"):
        return any(term in text for term in ("aem ", "aem-", "aem/", "experience manager", "aem assets", "guides", "native-integrations"))
    if "workfront" in text and ("aem" in text or "experience manager" in text or "guides" in text):
        return True
    if family in RELATED_AEM_PRODUCT_FAMILIES:
        has_integration_context = any(term in text for term in ("workfront", "integration", "connector", "aem assets", "asset link"))
        has_guides_or_dita_context = any(term in text for term in ("aem guides", "experience manager guides", "xml documentation", "dita-ot", "ditamap", "dita map"))
        has_publishing_context = bool(strong_constructs) and any(
            area in feature_hits
            for area in {"dita-ot-publishing", "branch-filtering", "translation-localization", "map-management"}
        )
        return has_guides_or_dita_context or has_integration_context or (has_publishing_context and "dita" in text)
    if family in UNRELATED_PRODUCT_FAMILIES and not any(term in text for term in ("aem guides", "dita-ot", "ditamap")):
        return False
    return False


def build_enriched_records(evidence: TopicEvidence) -> list[dict[str, Any]]:
    combined_text = clean_text(f"{evidence.title}\n{evidence.shortdesc}\n{evidence.body_text}")
    constructs = detect_constructs(combined_text)
    feature_areas = detect_feature_areas(combined_text)
    output_contexts = infer_output_terms(combined_text, evidence.canonical_url or evidence.source_url)
    workflow_cues = extract_workflow_cues(evidence.blocks)
    risks = infer_risk_cases(constructs, feature_areas, combined_text)
    qa_oracles = build_qa_oracles(constructs, feature_areas, output_contexts)
    excerpts = extract_evidence_excerpts(evidence.blocks)

    summary = build_summary(evidence, constructs, feature_areas, output_contexts)
    records = [
        make_enriched_record(
            evidence,
            section="Learned behavior summary",
            content=summary,
            evidence_type="enriched_learned_behavior",
            ordinal=0,
            constructs=constructs,
            feature_areas=feature_areas,
            output_contexts=output_contexts,
            workflow_cues=workflow_cues,
            risks=risks,
            qa_oracles=qa_oracles,
        )
    ]

    for index, excerpt in enumerate(excerpts[:4], start=1):
        content = "\n".join(
            [
                f"Evidence-backed behavior chunk for {evidence.title}.",
                f"Feature areas: {', '.join(feature_areas) or 'general AEM Guides behavior'}.",
                f"Constructs: {', '.join(constructs) or 'none explicitly detected'}.",
                "Source evidence:",
                excerpt,
                "QA use:",
                "- Generate datasets that preserve the documented map/topic/output context.",
                "- Verify with source-file markers plus published PDF/HTML5 output when publishing is requested.",
            ]
        )
        records.append(
            make_enriched_record(
                evidence,
                section=f"Evidence excerpt {index}",
                content=content,
                evidence_type="enriched_evidence_excerpt",
                ordinal=index,
                constructs=constructs,
                feature_areas=feature_areas,
                output_contexts=output_contexts,
                workflow_cues=workflow_cues,
                risks=risks,
                qa_oracles=qa_oracles,
            )
        )

    if qa_oracles:
        oracle_content = "\n".join(
            [
                f"Validation oracle pack for {evidence.title}.",
                f"Detected constructs: {', '.join(constructs) or 'none explicitly detected'}.",
                "Expected behavior:",
                *[f"- {item}" for item in qa_oracles],
                "Negative/risk cases:",
                *[f"- {item}" for item in risks[:8]],
                "Confidence contract: High for source-backed workflow/oracle cues; Draft if generated data is not published through the requested transform.",
            ]
        )
        records.append(
            make_enriched_record(
                evidence,
                section="QA oracle pack",
                content=oracle_content,
                evidence_type="enriched_generation_oracle",
                ordinal=9,
                constructs=constructs,
                feature_areas=feature_areas,
                output_contexts=output_contexts,
                workflow_cues=workflow_cues,
                risks=risks,
                qa_oracles=qa_oracles,
            )
        )
    return [record for record in records if len(str(record.get("content") or "")) >= 120]


def build_summary(
    evidence: TopicEvidence,
    constructs: list[str],
    feature_areas: list[str],
    output_contexts: list[str],
) -> str:
    lines = [
        f"Source page: {evidence.title}.",
        f"URL: {evidence.canonical_url or evidence.source_url}.",
    ]
    if evidence.shortdesc:
        lines.append(f"Documented purpose: {evidence.shortdesc}")
    lines.extend(
        [
            f"Learned feature behavior: {', '.join(feature_areas) or 'AEM Guides workflow behavior'}.",
            f"Detected DITA constructs and attributes: {', '.join(constructs) or 'not explicit in this page'}.",
            f"Publishing/output contexts: {', '.join(output_contexts) or 'not output-specific'}.",
            "How to use this in RAG: prefer this chunk when a user asks how functionality behaves, asks for DITA-OT PDF/HTML5 evidence, or asks for generated QA data from scraped Experience League docs.",
            "Generation requirement: produce a map, focused topics, README, manifest, expected behavior, QA checklist, PDF review areas, HTML5 review areas, negative/risk cases, and validation oracles.",
        ]
    )
    return "\n".join(lines)


def make_enriched_record(
    evidence: TopicEvidence,
    *,
    section: str,
    content: str,
    evidence_type: str,
    ordinal: int,
    constructs: list[str],
    feature_areas: list[str],
    output_contexts: list[str],
    workflow_cues: list[str],
    risks: list[str],
    qa_oracles: list[str],
) -> dict[str, Any]:
    content = clean_text(content)[:MAX_CONTENT_CHARS].strip()
    url = evidence.canonical_url or evidence.source_url
    seed = f"{url}|{evidence.relpath}|{section}|{ordinal}|{content}"
    chunk_id = "aem_guides_enriched_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    query_terms = sorted(set([*constructs, *feature_areas, *output_contexts, *keyword_terms(content)]))
    return {
        "id": chunk_id,
        "chunk_id": chunk_id,
        "url": evidence.source_url,
        "source_url": evidence.source_url,
        "canonical_url": evidence.canonical_url,
        "dita_path": evidence.relpath,
        "title": evidence.title,
        "section": section,
        "section_path": [section],
        "content": content,
        "summary": first_sentence(content),
        "learned_behavior": first_sentence(content),
        "detected_constructs": constructs,
        "feature_area": feature_areas[0] if feature_areas else "aem-guides-behavior",
        "feature_areas": feature_areas,
        "output_contexts": output_contexts,
        "workflow_cues": workflow_cues[:8],
        "expected_behavior": qa_oracles[:8],
        "qa_oracles": qa_oracles[:8],
        "risk_signals": risks[:8],
        "retrieval_intents": [
            "dita_behavior_question",
            "publishing_dataset_generation",
            "pdf_html5_oracle",
            "aem_guides_qa",
        ],
        "query_terms": query_terms[:60],
        "chunk_index": ordinal,
        "evidence_type": evidence_type,
        "source_product_family": infer_source_product_family(url),
        "source_type": evidence.metadata.get("source-type", "official-experience-league"),
        "product": "AEM Guides",
        "source_language": evidence.metadata.get("source-language", ""),
        "source_last_updated": evidence.metadata.get("source-last-updated", ""),
        "crawled_at": evidence.metadata.get("crawled-at", ""),
        "source_content_hash": evidence.metadata.get("content-hash", ""),
        "chunk_content_hash": "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "chunker_version": CHUNK_VERSION,
        "confidence": "high" if "/experience-manager-guides/" in url else "medium",
        "confidence_contract": "Source-backed Experience League DITA chunk; publishing claims still require DITA-OT execution evidence for the requested transform.",
        "neighbor_prev_id": "",
        "neighbor_next_id": "",
    }


def detect_constructs(*parts: str) -> list[str]:
    text = " ".join(parts).lower()
    labels: list[str] = []
    for term in (*DITA_ATTRIBUTE_TERMS, *ELEMENT_TERMS):
        pattern = r"(?<![\w:-])" + re.escape(term.lower()) + r"(?![\w:-])"
        if re.search(pattern, text):
            labels.append(term)
    for signal in infer_dita_construct_signals(text):
        if signal not in labels:
            labels.append(signal)
    return labels


def detect_feature_areas(*parts: str) -> list[str]:
    text = " ".join(parts).lower()
    areas = [area for area, needles in FEATURE_RULES if any(needle in text for needle in needles)]
    return areas or ["aem-guides-behavior"]


def extract_workflow_cues(blocks: list[CandidateBlock]) -> list[str]:
    cues: list[str] = []
    signal = re.compile(r"\b(open|select|click|choose|create|save|generate|publish|configure|upload|translate|review|validate|enable|disable)\b", re.I)
    for block in blocks:
        for line in re.split(r"(?<=[.!?])\s+|\n+", block.text):
            cleaned = clean_text(line)
            if 28 <= len(cleaned) <= 220 and signal.search(cleaned):
                cues.append(cleaned)
    return list(dict.fromkeys(cues))


def extract_evidence_excerpts(blocks: list[CandidateBlock]) -> list[str]:
    scored: list[tuple[int, str]] = []
    for block in blocks:
        text = clean_text(block.text)
        if len(text) < 120:
            continue
        lowered = text.lower()
        score = 0
        score += 4 if any(term in lowered for term in DITA_ATTRIBUTE_TERMS) else 0
        score += 3 if any(term in lowered for term in ("pdf", "html5", "output", "publish", "dita-ot")) else 0
        score += 2 if any(term in lowered for term in ("select", "click", "configure", "generate", "baseline", "translation")) else 0
        score += 2 if any(term in lowered for term in ("error", "warning", "fail", "cannot", "must", "should")) else 0
        if score > 0:
            scored.append((score, text[:900]))
    scored.sort(key=lambda item: item[0], reverse=True)
    return list(dict.fromkeys(text for _, text in scored))


def infer_risk_cases(constructs: list[str], feature_areas: list[str], text: str) -> list[str]:
    risks: list[str] = []
    lowered = text.lower()
    if "chunk" in constructs:
        risks.append("Chunking can change output file boundaries, navigation, and link targets; verify PDF and HTML5 separately.")
    if "copy-to" in constructs:
        risks.append("copy-to can create unique effective targets from the same source; verify duplicate references do not collide.")
    if "xml:lang" in constructs:
        risks.append("xml:lang inheritance or override can affect generated language metadata, labels, fonts, and localized strings.")
    if any(term in constructs for term in ("audience", "platform", "product", "props", "otherprops", "print", "ditaval")):
        risks.append("Conditional filtering can remove map branches or topic content before output transformation.")
    if any(term in constructs for term in ("keyref", "keys", "keyscope", "conkeyref")):
        risks.append("Key scope and missing-key resolution can differ between source validation and generated output.")
    if any(term in constructs for term in ("conref", "conrefend", "conrefpush")):
        risks.append("Content reuse boundaries can fail when targets are missing, reordered, filtered, or pushed into an unexpected location.")
    if "integration-workflow" in feature_areas:
        risks.append("Integration behavior depends on AEM-side configuration, permissions, connected service state, and upload/publish permissions.")
    if "error" in lowered or "fail" in lowered:
        risks.append("Source mentions failure/error behavior; generated tests should include negative and recovery oracles.")
    return list(dict.fromkeys(risks))


def build_qa_oracles(constructs: list[str], feature_areas: list[str], output_contexts: list[str]) -> list[str]:
    oracles = [
        "Source oracle: generated DITA map/topics contain the detected constructs in realistic map context.",
        "Manifest oracle: README and manifest explain expected behavior, risk cases, and review areas.",
    ]
    if any(ctx in output_contexts for ctx in ("PDF", "DITA-OT")) or "dita-ot-publishing" in feature_areas:
        oracles.append("PDF oracle: DITA-OT PDF exits successfully and generated PDF contains expected visible content, ordering, and exclusions.")
    if "HTML5" in output_contexts or "dita-ot-publishing" in feature_areas:
        oracles.append("HTML5 oracle: generated HTML files, filenames, links, language markers, and navigation reflect expected map behavior.")
    if "branch-filtering" in feature_areas:
        oracles.append("Filtering oracle: excluded branches/content are absent and included branches/content remain after DITAVAL/profile processing.")
    if "translation-localization" in feature_areas or "xml:lang" in constructs:
        oracles.append("Language oracle: inherited and overridden language values are visible in source and published output metadata.")
    if "integration-workflow" in feature_areas:
        oracles.append("Integration oracle: generated data and upload instructions identify required AEM path, permissions, and configuration assumptions.")
    return list(dict.fromkeys(oracles))


def infer_source_product_family(url: str) -> str:
    segments = [segment for segment in urlparse(str(url or "")).path.split("/") if segment]
    try:
        index = segments.index("docs")
        return segments[index + 1] if index + 1 < len(segments) else ""
    except ValueError:
        return ""


def keyword_terms(text: str) -> list[str]:
    lowered = text.lower()
    terms = []
    for term in (*DITA_ATTRIBUTE_TERMS, *ELEMENT_TERMS, "pdf", "pdf2", "html5", "aem guides", "dita-ot", "publishing"):
        if term in lowered:
            terms.append(term)
    return terms


def first_sentence(text: str) -> str:
    cleaned = clean_text(text)
    match = re.search(r"^(.{40,240}?[.!?])\s", cleaned)
    return match.group(1) if match else cleaned[:240]


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        key = (str(record.get("canonical_url") or record.get("source_url") or ""), str(record.get("chunk_content_hash") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def record_sort_key(record: dict[str, Any]) -> tuple[int, str, int]:
    url = str(record.get("canonical_url") or record.get("source_url") or "")
    confidence_rank = 0 if "/experience-manager-guides/" in url else 1
    return (confidence_rank, str(record.get("dita_path") or ""), int(record.get("chunk_index") or 0))


def relink_neighbors(records: list[dict[str, Any]]) -> None:
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_doc.setdefault(str(record.get("dita_path") or ""), []).append(record)
    for doc_records in by_doc.values():
        doc_records.sort(key=lambda row: int(row.get("chunk_index") or 0))
        for index, record in enumerate(doc_records):
            record["neighbor_prev_id"] = doc_records[index - 1]["id"] if index > 0 else ""
            record["neighbor_next_id"] = doc_records[index + 1]["id"] if index + 1 < len(doc_records) else ""


def summarize_feature_areas(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for area in record.get("feature_areas") or [record.get("feature_area") or "unknown"]:
            counts[str(area)] = counts.get(str(area), 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20])


if __name__ == "__main__":
    raise SystemExit(main())
