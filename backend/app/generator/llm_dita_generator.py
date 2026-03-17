"""
LLM DITA generator - produces DITA from Jira evidence when no recipe exists.

Used when Jira mentions topicset, navref, foreign, topicgroup, or other constructs
not covered by the recipe catalog. Generates DITA directly via LLM token generation.
Uses RAG (DITA spec, DITA graph, AEM Guides docs) to reduce hallucination.
"""
import asyncio
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.generator.dita_utils import make_dita_id
from app.jobs.schemas import DatasetConfig
from app.core.structured_logging import get_structured_logger
from app.core.observability import get_observability_logger
from app.utils.fs_guard import safe_join, SecurityError

logger = get_structured_logger(__name__)
obs_log = get_observability_logger("llm_dita")

LLM_DITA_MAX_FILES = 10
LLM_DITA_MAX_BYTES_PER_FILE = 50 * 1024  # 50KB
LLM_DITA_MAX_TOKENS = int(os.environ.get("LLM_DITA_MAX_TOKENS", "4000"))
LLM_DITA_MAX_RETRIES = max(1, int(os.environ.get("LLM_DITA_MAX_RETRIES", "1")))

# RAG tuning (env vars)
LLM_DITA_RAG_DITA_K = int(os.environ.get("LLM_DITA_RAG_DITA_K", "4"))
LLM_DITA_RAG_DITA_GRAPH_ENABLED = os.environ.get("LLM_DITA_RAG_DITA_GRAPH_ENABLED", "true").lower() in ("true", "1", "yes")
LLM_DITA_RAG_AEM_DOCS_ENABLED = os.environ.get("LLM_DITA_RAG_AEM_DOCS_ENABLED", "true").lower() in ("true", "1", "yes")

# Optional content fidelity: check that evidence terms appear in generated DITA (warn only)
LLM_DITA_CONTENT_FIDELITY_ENABLED = os.environ.get("LLM_DITA_CONTENT_FIDELITY_ENABLED", "false").lower() in ("true", "1", "yes")
LLM_DITA_CONTENT_FIDELITY_MIN_RATIO = max(0.0, min(1.0, float(os.environ.get("LLM_DITA_CONTENT_FIDELITY_MIN_RATIO", "0.2"))))

RECIPE_SPECS = [
    {
        "id": "llm_generated_dita",
        "title": "LLM Generated DITA",
        "description": "Generate DITA from Jira evidence using LLM when no recipe exists (topicset, navref, foreign, topicgroup, etc.).",
        "tags": ["LLM", "fallback", "topicset", "navref", "foreign", "topicgroup", "novel construct"],
        "module": "app.generator.llm_dita_generator",
        "function": "generate_llm_dita",
        "params_schema": {"evidence_pack": "dict", "representative_xml": "list", "additional_instructions": "str"},
        "default_params": {},
        "stability": "stable",
        "constructs": ["map", "topic", "topicref", "topicgroup", "topicset", "navref", "foreign", "topicmeta", "bookmap", "bookmeta"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["no matching recipe", "topicset", "navref", "foreign", "topicgroup", "bookmap", "bookmeta", "novel DITA construct"],
        "avoid_when": ["specific recipe matches"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
]

DOCTYPE_TOPIC = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">'
DOCTYPE_MAP = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">'
DOCTYPE_BOOKMAP = '<!DOCTYPE bookmap PUBLIC "-//OASIS//DTD DITA BookMap//EN" "technicalContent/dtd/bookmap.dtd">'


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON object from response."""
    text = (text or "").strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _normalize_llm_xml_content(content: str) -> str:
    """Preprocess LLM output before validation: strip markdown fences, XML declaration, DOCTYPE."""
    if not content or not isinstance(content, str):
        return content or ""
    s = content.strip()
    # Strip markdown code fences (```xml, ```json, ``` at start/end)
    s = re.sub(r"^```(?:xml|json)?\s*\n?", "", s)
    s = re.sub(r"\n?```\s*$", "", s)
    s = s.strip()
    # Strip XML declaration
    s = re.sub(r"<\?xml[^?>]*\?>\s*", "", s, flags=re.IGNORECASE)
    # Strip DOCTYPE
    s = re.sub(r"<!DOCTYPE[^>]*>\s*", "", s, flags=re.IGNORECASE)
    return s.strip()


def _check_content_fidelity(
    evidence_text: str,
    output: Dict[str, bytes],
    jira_id: Optional[str] = None,
) -> None:
    """
    Optional check: warn if too few evidence terms appear in generated DITA.
    Extracts words > 4 chars from evidence; requires min ratio to appear in output.
    """
    if not LLM_DITA_CONTENT_FIDELITY_ENABLED or not evidence_text or not output:
        return
    terms = set()
    for word in re.findall(r"[a-zA-Z0-9]{5,}", evidence_text):
        terms.add(word.lower())
    if not terms:
        return
    combined = ""
    for content_bytes in output.values():
        try:
            combined += content_bytes.decode("utf-8", errors="ignore")
        except Exception:
            pass
    combined_lower = combined.lower()
    found = sum(1 for t in terms if t in combined_lower)
    ratio = found / len(terms) if terms else 1.0
    if ratio < LLM_DITA_CONTENT_FIDELITY_MIN_RATIO:
        logger.warning_structured(
            "LLM content fidelity check: low evidence overlap",
            extra_fields={
                "jira_id": jira_id,
                "evidence_terms": len(terms),
                "found_in_output": found,
                "ratio": round(ratio, 2),
                "min_ratio": LLM_DITA_CONTENT_FIDELITY_MIN_RATIO,
            },
        )


def _is_valid_dita_xml(content: str) -> bool:
    """Check if content parses as valid XML with DITA-like root.
    Accepts namespaced tags (dita:topic, {uri}topic) by normalizing to local name.
    """
    if not content or not isinstance(content, str):
        return False
    content = content.strip()
    if not content:
        return False
    try:
        root = ET.fromstring(content)
        tag = root.tag.split("}")[-1].lower() if "}" in root.tag else root.tag.lower()
        # Accept dita:topic, topic, etc.
        local_name = tag.split(":")[-1] if ":" in tag else tag
        return local_name in ("map", "topic", "bookmap")
    except ET.ParseError:
        return False


def _wrap_with_doctype(content: str, is_map: bool, is_bookmap: bool = False) -> bytes:
    """Add XML declaration and DOCTYPE to content."""
    if is_bookmap:
        doctype = DOCTYPE_BOOKMAP
    elif is_map:
        doctype = DOCTYPE_MAP
    else:
        doctype = DOCTYPE_TOPIC
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{doctype}\n{content.strip()}'
    return doc.encode("utf-8")


def _run_async(coro):
    """Run async coroutine from sync context (e.g. when executor calls recipe in thread)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already in async context - create new loop in thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(asyncio.run, coro)
        return future.result()


async def _generate_llm_dita_async(
    config: DatasetConfig,
    base_path: str,
    evidence_pack: Optional[dict] = None,
    representative_xml: Optional[List[str]] = None,
    additional_instructions: Optional[str] = None,
    id_prefix: str = "llm",
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
) -> Dict[str, bytes]:
    """Async implementation of LLM DITA generation."""
    from app.services.llm_service import generate_json, is_llm_available
    from app.services.dita_knowledge_retriever import retrieve_dita_knowledge, retrieve_dita_graph_knowledge
    from app.utils.evidence_extractor import AEM_GUIDES_TRIGGER_TERMS

    prompt_path = Path(__file__).resolve().parent.parent / "templates" / "prompts" / "llm_dita_generator.txt"
    system_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

    if not system_prompt or not is_llm_available():
        logger.warning_structured(
            "LLM DITA generator: prompt missing or LLM unavailable",
            extra_fields={"jira_id": jira_id},
        )
        raise RuntimeError(
            "LLM unavailable: set ANTHROPIC_API_KEY or GROQ_API_KEY in backend/.env. "
            "See backend/.env.example. Use LLM_PROVIDER=groq for Groq."
        )

    primary = (evidence_pack or {}).get("primary") or {}
    summary = (primary.get("summary") or "Issue")[:500]
    description = (primary.get("description") or "")[:3000]
    evidence_text = f"{summary}\n\n{description}"

    # RAG: DITA spec chunks
    dita_context = ""
    try:
        chunks = retrieve_dita_knowledge(evidence_text, k=LLM_DITA_RAG_DITA_K)
        if chunks:
            texts = [
                f"{c.get('element_name', '')}: {c.get('text_content', '')[:500]}"
                for c in chunks
            ]
            dita_context = "DITA KNOWLEDGE:\n" + "\n".join(texts) + "\n\n"
    except Exception as e:
        logger.debug_structured("DITA knowledge retrieval skipped", extra_fields={"error": str(e)})

    # RAG: DITA graph (nesting and attributes)
    if LLM_DITA_RAG_DITA_GRAPH_ENABLED:
        try:
            graph_block = retrieve_dita_graph_knowledge(element_hint=evidence_text)
            if graph_block:
                dita_context += "DITA STRUCTURE (nesting and attributes):\n" + graph_block + "\n\n"
        except Exception as e:
            logger.debug_structured("DITA graph retrieval skipped", extra_fields={"error": str(e)})

    # RAG: AEM Guides docs (when evidence mentions product-specific terms)
    if LLM_DITA_RAG_AEM_DOCS_ENABLED and evidence_text:
        text_lower = evidence_text.lower()
        if any(term in text_lower for term in AEM_GUIDES_TRIGGER_TERMS):
            try:
                from app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt
                docs = retrieve_relevant_docs(evidence_text[:3000], k=3, max_snippet_chars=500)
                if docs:
                    formatted = format_docs_for_prompt(docs)
                    if formatted:
                        dita_context += "AEM GUIDES DOCUMENTATION:\n" + formatted + "\n\n"
            except Exception as e:
                logger.debug_structured("AEM Guides doc retrieval skipped", extra_fields={"error": str(e)})

    rep_xml_hint = ""
    if representative_xml and isinstance(representative_xml, list) and representative_xml:
        rep_xml_hint = "\n\nREPRESENTATIVE SAMPLE (use as reference):\n"
        for i, s in enumerate(representative_xml[:3]):
            if s and isinstance(s, str):
                rep_xml_hint += f"\n--- Snippet {i + 1} ---\n{s[:1500]}\n"

    instructions_hint = ""
    if additional_instructions and additional_instructions.strip():
        instructions_hint = f"\n\nADDITIONAL INSTRUCTIONS (follow these):\n{additional_instructions.strip()[:1500]}\n\n"

    # Use neutral label: user input may be Jira evidence or natural language (e.g. "create a task topic about X")
    user = f"{dita_context}USER INPUT (Jira evidence or natural language request):\nSummary: {summary}\n\nDescription: {description}{rep_xml_hint}{instructions_hint}Output STRICT JSON with 'files' array only:"

    obs_log.info(
        "llm_dita_generation_started",
        run_id=trace_id,
        session_id=trace_id,
        jira_id=jira_id,
        evidence_length=len(evidence_text),
    )
    last_error: Optional[Exception] = None
    for attempt in range(1, LLM_DITA_MAX_RETRIES + 1):
        try:
            result = await generate_json(
                system_prompt,
                user,
                max_tokens=min(LLM_DITA_MAX_TOKENS, 4000),
                step_name="llm_dita_generator",
                trace_id=trace_id,
                jira_id=jira_id,
            )
            last_error = None
            break
        except Exception as e:
            last_error = e
            logger.warning_structured(
                "LLM DITA generator attempt failed",
                extra_fields={"jira_id": jira_id, "attempt": attempt, "max_retries": LLM_DITA_MAX_RETRIES, "error": str(e)},
            )
            if attempt >= LLM_DITA_MAX_RETRIES:
                raise RuntimeError(f"LLM DITA generator failed after {LLM_DITA_MAX_RETRIES} attempt(s): {e}") from e
            await asyncio.sleep(1.0 * attempt)  # Backoff: 1s, 2s, ...

    raw = result if isinstance(result, dict) else (_extract_json(str(result)) if result else {})
    if not isinstance(raw, dict):
        raw = {}

    files_list = raw.get("files") or []
    if not isinstance(files_list, list):
        logger.warning_structured(
            "LLM returned invalid structure: files not a list",
            extra_fields={"jira_id": jira_id, "files_type": type(files_list).__name__},
        )
        raise ValueError(
            f"LLM returned invalid structure: 'files' must be a list, got {type(files_list).__name__}"
        )

    root_folder = f"{base_path}/llm_generated_dita"
    output: Dict[str, bytes] = {}
    used_ids: set = set()
    file_count = 0
    rejected_count = 0
    first_rejected_sample: Optional[str] = None

    for item in files_list[:LLM_DITA_MAX_FILES]:
        if file_count >= LLM_DITA_MAX_FILES:
            break
        if not isinstance(item, dict):
            rejected_count += 1
            continue
        path_val = item.get("path") or ""
        content_val = item.get("content") or ""
        if not path_val or not content_val:
            rejected_count += 1
            continue

        path_val = str(path_val).strip().replace("\\", "/")
        if path_val.startswith("llm_generated_dita/"):
            path_val = path_val[len("llm_generated_dita/"):].lstrip("/")
        if not path_val or ".." in path_val or path_val.startswith("/"):
            rejected_count += 1
            continue

        content_val = str(content_val).strip()[:LLM_DITA_MAX_BYTES_PER_FILE]
        content_val = _normalize_llm_xml_content(content_val)
        if not _is_valid_dita_xml(content_val):
            rejected_count += 1
            if first_rejected_sample is None:
                first_rejected_sample = (content_val or "")[:300]
            continue

        content_lower = content_val.lower().strip()
        is_bookmap = content_lower.startswith("<bookmap")
        is_map = content_lower.startswith("<map") or is_bookmap
        full_path = f"{root_folder}/{path_val}"

        try:
            base_resolved = Path(base_path).resolve()
            safe_join(base_resolved, f"llm_generated_dita/{path_val}")
        except SecurityError:
            rejected_count += 1
            continue

        xml_bytes = _wrap_with_doctype(content_val, is_map, is_bookmap=is_bookmap)
        output[full_path] = xml_bytes
        file_count += 1

    if not output:
        total = len(files_list[:LLM_DITA_MAX_FILES])
        logger.warning_structured(
            "All LLM file(s) failed DITA validation",
            extra_fields={
                "jira_id": jira_id,
                "total_items": total,
                "rejected_count": rejected_count,
                "first_rejected_sample": first_rejected_sample[:200] if first_rejected_sample else None,
            },
        )
        sample_hint = f" First rejected sample: {first_rejected_sample!r}" if first_rejected_sample else ""
        raise ValueError(
            f"All {total} file(s) from LLM failed DITA validation (invalid XML or wrong root tag)."
            f"{sample_hint}"
        )

    _check_content_fidelity(evidence_text, output, jira_id=jira_id)
    obs_log.info(
        "llm_dita_generation_completed",
        run_id=trace_id,
        jira_id=jira_id,
        topic_count=len(output),
        file_count=len(output),
    )
    return output


def _minimal_fallback(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str,
    evidence_pack: Optional[dict] = None,
) -> Dict[str, bytes]:
    """Return minimal valid DITA when LLM fails. Include Jira summary/description when available."""
    from app.generator.evidence_to_dita import _minimal_topic_xml

    primary = (evidence_pack or {}).get("primary") or {}
    summary = (primary.get("summary") or "LLM Fallback Placeholder").strip()[:200]
    description = (primary.get("description") or "").strip()[:500]

    title = summary if summary else "LLM Fallback Placeholder"
    body_text = description if description else None

    used: set = set()
    topic_id = make_dita_id("placeholder", id_prefix, used)
    root = f"{base_path}/llm_generated_dita"
    map_elem = f"""<map id="llm_fallback_map"><title>LLM Fallback</title><topicref href="../topics/placeholder.dita" navtitle="Placeholder"/></map>"""
    return {
        f"{root}/maps/main.ditamap": _wrap_with_doctype(map_elem, True),
        f"{root}/topics/placeholder.dita": _minimal_topic_xml(config, topic_id, title, body_text),
    }


def generate_llm_dita(
    config: DatasetConfig,
    base_path: str,
    evidence_pack: Optional[dict] = None,
    representative_xml: Optional[List[str]] = None,
    additional_instructions: Optional[str] = None,
    id_prefix: str = "llm",
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, bytes]:
    """
    Generate DITA from Jira evidence using LLM when no recipe exists.
    Used for topicset, navref, foreign, topicgroup, and other novel constructs.
    """
    return _run_async(
        _generate_llm_dita_async(
            config=config,
            base_path=base_path,
            evidence_pack=evidence_pack,
            representative_xml=representative_xml,
            additional_instructions=additional_instructions,
            id_prefix=id_prefix,
            trace_id=trace_id,
            jira_id=jira_id,
        )
    )
