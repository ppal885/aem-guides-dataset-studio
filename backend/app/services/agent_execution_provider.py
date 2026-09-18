"""A5: agent execution providers - the boundary between the canonical
runtime's research orchestration and the execution substrate.

The canonical runtime remains the only authority for state, validation,
sufficiency, coverage, promotion, and rendering.  Providers perform bounded
research interpretation and return the shared R2 ResearchWorkerResult
envelope; the runtime validates and admits it.  Agent output is proposed
research evidence, never acceptance authority.

Execution modes (AGENT_RESEARCH_MODE):

- ``deterministic`` (default): the existing R2 deterministic workers.
- ``agent``: real model execution per worker via the backend's configured
  LLM substrate (``llm_service``).  When no model is available the worker
  records WORKER_UNAVAILABLE - never a silent deterministic stand-in that
  claims agent execution.
- ``shadow``: deterministic result remains authoritative; the model worker
  also executes read-only and the comparison is recorded.  Never two
  production authorities.

Truthful receipts: every ResearchWorkerExecution records ``provider`` and
``model_execution`` - a deterministic service is never called an agent.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from pathlib import Path

from app.core.schemas_canonical_test_plan_runtime import (
    AgentResearchRequest,
    CanonicalEvidenceBundle,
    EvidenceSourceType,
    HostAgentResultEnvelope,
    ResearchFinding,
    ResearchFindingEvidenceRole,
    ResearchWorkerResult,
    ResearchWorkerRole,
    ResearchWorkerStatus,
    stable_sha256,
)

_PROVIDER_DETERMINISTIC = "DETERMINISTIC"
_PROVIDER_MODEL_AGENT = "MODEL_AGENT"

# Read-only repository roots authorized for bounded code research.  Canonical
# definition; research_workers imports it from here.
RESEARCH_REPOSITORY_ENV_VARS = (
    "STARLING_REPO_PATH",
    "XML_EDITOR_REPO_PATH",
    "GUIDES_UI_TESTS_REPO_PATH",
    "AEM_STUDIO_REPO",
)

_ROLE_CONTRACT_FILES = {
    ResearchWorkerRole.DOC_RESEARCHER: "uac-doc-researcher.md",
    ResearchWorkerRole.CODE_RESEARCHER: "uac-code-researcher.md",
    ResearchWorkerRole.ATTACHMENT_RESEARCHER: "uac-attachment-researcher.md",
}

_MAX_EVIDENCE_EXCERPT = 400
_MAX_EVIDENCE_ITEMS = 25


def agent_research_mode() -> str:
    """The configured execution mode: deterministic (default) |
    backend_model (in-process LLM substrate, needs credentials) |
    copilot_host (the Copilot host delegates registered custom agents and
    returns results through the resume boundary) | shadow."""

    mode = os.environ.get("AGENT_RESEARCH_MODE", "").strip().casefold()
    # "agent" is the pre-rename spelling of backend_model.
    if mode == "agent":
        mode = "backend_model"
    return (
        mode
        if mode in {"deterministic", "backend_model", "copilot_host", "shadow"}
        else "deterministic"
    )


def agent_research_store() -> Path:
    """Pending/fulfilled handoff store for COPILOT_HOST orchestration."""

    root = os.environ.get("AGENT_RESEARCH_STORE", "").strip()
    if root:
        return Path(root)
    return Path(__file__).resolve().parents[2] / "storage" / "agent_research"


def load_role_contract(role: ResearchWorkerRole) -> tuple[str, str, str]:
    """Load the canonical Skill role contract for a worker role.

    Returns (contract_name, version_sha256, text).  The canonical source is
    the Skill agents directory; Copilot registrations are generated wrappers
    kept in parity by scripts/sync_agent_registrations.py --check.
    """

    filename = _ROLE_CONTRACT_FILES[role]
    current = Path(__file__).resolve()
    for ancestor in current.parents:
        candidate = (
            ancestor / "skills" / "test-plan-generation" / "agents" / filename
        )
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8")
            version = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
            return filename.removesuffix(".md"), version, text
    raise FileNotFoundError(f"canonical role contract not found: {filename}")


def _excerpt(value: object) -> str:
    text = str(value or "").strip()
    return text[:_MAX_EVIDENCE_EXCERPT]


def _authorized_evidence_rows(
    request: "AgentResearchRequest", bundle: "CanonicalEvidenceBundle"
) -> list[dict]:
    """Bounded excerpt rows for the request's authorized evidence.  Shared by
    the in-process model prompt and the COPILOT_HOST pending payload so a
    delegated leaf agent receives the actual content, not opaque IDs."""

    authorized = set(request.authorized_source_refs) | set(request.context_refs)
    rows = []
    for record in bundle.records:
        if record.evidence_id not in authorized:
            continue
        rows.append(
            {
                "source_ref": record.evidence_id,
                "source_type": record.source_type.value,
                "excerpt": _excerpt(record.content),
            }
        )
        if len(rows) >= _MAX_EVIDENCE_ITEMS:
            break
    return rows


def _documentation_roots() -> list[str]:
    """Approved local documentation scopes for delegated DOC research: the
    Skill's curated reference packs and product vocabulary plus the
    repository docs directory."""

    current = Path(__file__).resolve()
    for ancestor in current.parents:
        refs = ancestor / "skills" / "test-plan-generation" / "references"
        if refs.is_dir():
            roots = [str(refs)]
            data = ancestor / "skills" / "test-plan-generation" / "data"
            if data.is_dir():
                roots.append(str(data))
            docs = ancestor / "docs"
            if docs.is_dir():
                roots.append(str(docs))
            return roots
    return []


_QUERY_STOPWORDS = frozenset(
    {
        "this", "that", "with", "from", "which", "what", "does", "do", "is",
        "are", "the", "a", "an", "and", "or", "of", "to", "in", "on", "for",
        "under", "given", "here", "there", "when", "will", "would", "should",
        "could", "must", "than", "then", "them", "they", "their", "have",
        "has", "had", "been", "being", "into", "about", "after", "before",
        "between", "existing", "evidence", "mentions", "without", "change",
        "behavior", "behaviour", "question", "claim", "acceptance", "current",
        "ticket", "jira",
    }
)


def _load_guides_vocabulary() -> dict:
    import json as _json

    current = Path(__file__).resolve()
    for ancestor in current.parents:
        candidate = (
            ancestor
            / "skills"
            / "test-plan-generation"
            / "data"
            / "guides_vocabulary.json"
        )
        if candidate.exists():
            try:
                return _json.loads(candidate.read_text(encoding="utf-8-sig"))
            except Exception:
                return {}
    return {}


def _load_doc_query_expansions() -> list[dict]:
    import json as _json

    current = Path(__file__).resolve()
    for ancestor in current.parents:
        candidate = (
            ancestor
            / "skills"
            / "test-plan-generation"
            / "data"
            / "doc_query_expansions.json"
        )
        if candidate.exists():
            try:
                data = _json.loads(candidate.read_text(encoding="utf-8-sig"))
            except Exception:
                return []
            return [
                row
                for row in data.get("expansions", [])
                if isinstance(row, dict) and row.get("concept") and row.get("doc_terms")
            ]
    return []


def _term_present(term: str, text: str) -> bool:
    return bool(
        len(term) > 3
        and re.search(r"(?<![\w-])" + re.escape(term.casefold()) + r"(?![\w-])", text)
    )


def _documentation_query_plan(claim: str) -> tuple[list[str], list[str]]:
    """Bounded documentation query plan: the ORIGINAL claim is always the
    first query; a small set of high-value alternates follows, derived from
    the shipped product vocabulary (canonical terms + synonym groups) and
    the provenance-tagged bootstrap expansion map (Jira-side concept ->
    documentation-side terminology).  Expansion terms are retrieval hints,
    never evidence.  Returns (queries, expansion_terms_used)."""

    text = (claim or "").casefold()
    if not text.strip():
        return [], []
    queries = [claim]
    used: list[str] = []

    vocab = _load_guides_vocabulary()
    vocab_terms = [
        term for term in vocab.get("canonical_terms", []) if isinstance(term, str)
    ]
    for group in vocab.get("synonyms", []) or []:
        if isinstance(group, dict):
            group_terms = [t for t in group.get("terms", []) if isinstance(t, str)]
            if any(_term_present(t, text) for t in group_terms):
                # The claim uses one name; documentation may use its sibling.
                for t in group_terms:
                    if not _term_present(t, text) and t not in used:
                        used.append(t)
            vocab_terms.extend(group_terms)

    matched_vocab = sorted(
        {t for t in vocab_terms if _term_present(t, text)}, key=str.casefold
    )
    for row in _load_doc_query_expansions():
        if any(_term_present(str(concept), text) for concept in row["concept"]):
            for term in row["doc_terms"]:
                term = str(term)
                if not _term_present(term, text) and term not in used:
                    used.append(term)

    tokens = [
        token
        for token in re.findall(r"[a-z][a-z0-9-]{3,}", text)
        if token not in _QUERY_STOPWORDS
    ]
    # Alternate 1: documentation-side terminology for the matched concepts.
    if used:
        queries.append("AEM Guides " + " ".join(used[:6]))
    # Alternate 2: the product's canonical names plus the claim's own
    # significant tokens (helps when documentation uses the canonical name).
    if matched_vocab:
        queries.append("AEM Guides " + " ".join((matched_vocab[:3] + tokens[:3])))
    elif tokens:
        queries.append("AEM Guides " + " ".join(tokens[:6]))
    # Bound the plan: original + at most 3 alternates.
    seen: set[str] = set()
    plan: list[str] = []
    for query in queries:
        if query not in seen:
            seen.add(query)
            plan.append(query)
    return plan[:4], used


def _claim_domains(text: str) -> set[str]:
    """Light claim-side domain signal from the existing AEM Guides taxonomy.
    Used only to BOOST candidates whose own metadata declares a matching
    area - never to filter any candidate out."""

    try:
        from app.core.aem_guides_taxonomy import get_domain_specs
    except Exception:
        return set()
    out: set[str] = set()
    for dom_id, keywords, _weight in get_domain_specs():
        if any(str(keyword).casefold() in text for keyword in keywords):
            out.add(dom_id)
    return out


def _corpus_phrasing_terms(
    claim: str, candidates: list[dict], *, max_terms: int = 5
) -> list[str]:
    """Pseudo-relevance feedback: harvest the terminology the INDEXED
    DOCUMENTATION itself uses from the first-pass candidates' titles and
    snippets.  This is the primary expansion mechanism - it grows with the
    corpus and needs no hand-maintained dictionary."""

    claim_tokens = set(re.findall(r"[a-z][a-z0-9-]{3,}", (claim or "").casefold()))
    scores: dict[str, float] = {}
    for index, candidate in enumerate(candidates[:5]):
        weight = 1.0 / (index + 1)
        title_tokens = dict.fromkeys(
            re.findall(r"[a-z][a-z0-9-]{3,}", (candidate.get("title") or "").casefold())
        )
        snippet_tokens = dict.fromkeys(
            re.findall(
                r"[a-z][a-z0-9-]{3,}", (candidate.get("snippet") or "").casefold()
            )
        )
        for token in title_tokens:
            scores[token] = scores.get(token, 0.0) + 2.0 * weight
        for token in snippet_tokens:
            scores[token] = scores.get(token, 0.0) + 0.5 * weight
    ordered = sorted(scores, key=lambda token: (-scores[token], token))
    return [
        token
        for token in ordered
        if token not in claim_tokens and token not in _QUERY_STOPWORDS
    ][:max_terms]


def _rag_documentation_candidates(
    claim: str, *, top_k: int = 5
) -> tuple[list[dict], str, list[str], list[str]]:
    """RAG discovery for the DOC researcher over the existing indexed
    product-documentation retrieval layer, run across the bounded query
    plan (original claim first, vocabulary/terminology expansions after).
    Results merge by source (url/chunk), keeping every surfacing query as
    provenance, and rerank for the ORIGINAL research question (reciprocal
    rank fusion + a bonus for surfacing under the original query + claim
    token overlap).  Returns (candidates, status, queries, expansion_terms).
    Candidates are discovery leads - never evidence or acceptance claims,
    and a retrieval score is never authority."""

    queries, expansion_terms = _documentation_query_plan(claim)
    if not queries:
        return [], "rag retrieval unavailable: empty claim", [], []
    try:
        from app.services.doc_retriever_service import (
            retrieve_relevant_docs_with_diagnostics,
        )
    except Exception as exc:  # pragma: no cover - import guard
        return [], f"rag retrieval unavailable: {exc.__class__.__name__}", queries, expansion_terms

    merged: dict[str, dict] = {}
    modes: list[str] = []
    claim_tokens = set(re.findall(r"[a-z][a-z0-9-]{3,}", (claim or "").casefold()))
    errors: list[str] = []

    def _merge(query: str) -> None:
        try:
            payload = retrieve_relevant_docs_with_diagnostics(query[:4000], k=top_k)
        except Exception as exc:
            errors.append(f"{exc.__class__.__name__}")
            return
        mode = str(payload.get("retrieval_mode") or "none")
        if mode not in modes:
            modes.append(mode)
        for rank, row in enumerate(payload.get("results") or []):
            key = (
                str(row.get("url") or "")
                or str(row.get("chunk_id") or row.get("id") or "")
                or str(row.get("title") or "")
            )
            if not key:
                continue
            candidate = merged.get(key)
            if candidate is None:
                candidate = {
                    "chunk_id": str(row.get("chunk_id") or row.get("id") or ""),
                    "source_type": str(row.get("corpus") or "aem_guides"),
                    "title": str(row.get("title") or ""),
                    "url": str(row.get("url") or ""),
                    "snippet": _excerpt(row.get("snippet") or ""),
                    "area": str(row.get("area") or row.get("aem_guides_area") or ""),
                    "matched_queries": [],
                    "retrieval_modes": [],
                    "discovery_lead": True,
                    "_ranks": [],
                }
                merged[key] = candidate
            candidate["matched_queries"].append(query)
            if mode not in candidate["retrieval_modes"]:
                candidate["retrieval_modes"].append(mode)
            candidate["_ranks"].append(rank)

    for query in queries:
        _merge(query)
    # Pseudo-relevance feedback: one extra pass using the phrasing the
    # indexed documentation itself used in the first-pass candidates.
    prf_terms = _corpus_phrasing_terms(claim, list(merged.values()))
    if prf_terms:
        prf_query = "AEM Guides " + " ".join(prf_terms)
        if prf_query not in queries:
            queries.append(prf_query)
            _merge(prf_query)

    claim_query = claim
    claim_domains = _claim_domains((claim or "").casefold())
    candidates: list[dict] = []
    for candidate in merged.values():
        ranks = candidate.pop("_ranks")
        rrf = sum(1.0 / (rank + 1) for rank in ranks)
        original_bonus = 0.5 if claim_query in candidate["matched_queries"] else 0.0
        text = (candidate["title"] + " " + candidate["snippet"]).casefold()
        overlap = len(claim_tokens & set(re.findall(r"[a-z][a-z0-9-]{3,}", text)))
        # Domain classification BOOSTS matching candidates only; nothing is
        # ever filtered out by domain.
        domain_bonus = (
            0.1
            if claim_domains
            and candidate.get("area")
            and candidate["area"].casefold() in {d.casefold() for d in claim_domains}
            else 0.0
        )
        candidate["score"] = round(
            rrf + original_bonus + 0.02 * overlap + domain_bonus, 4
        )
        candidates.append(candidate)
    candidates.sort(key=lambda row: row["score"], reverse=True)
    candidates = candidates[:top_k]
    if candidates:
        status = "ok:" + "+".join(modes or ["none"])
    elif errors:
        status = "rag retrieval unavailable: " + ",".join(sorted(set(errors)))
    else:
        status = "no candidates:" + "+".join(modes or ["none"])
    return candidates, status, queries, expansion_terms


def _attachment_files(
    request: "AgentResearchRequest",
    bundle: "CanonicalEvidenceBundle",
    store: Path,
) -> list[dict]:
    """Materialize the actual content of authorized Jira attachments so the
    delegated attachment researcher reads real content, never metadata alone.
    Failures are recorded with their exact reason - never hidden - so the
    researcher can honestly report SOURCE_UNAVAILABLE for that source."""

    authorized = set(request.authorized_source_refs) | set(request.context_refs)
    out: list[dict] = []
    for record in bundle.records:
        if record.evidence_id not in authorized:
            continue
        if record.source_type != EvidenceSourceType.JIRA_ATTACHMENT:
            continue
        content = record.content if isinstance(record.content, dict) else {}
        url = str(content.get("url") or "").strip()
        filename = str(content.get("filename") or "attachment.bin")
        entry = {
            "source_ref": record.evidence_id,
            "filename": filename,
            "mime_type": str(content.get("mime_type") or ""),
            "path": "",
            "size_bytes": 0,
            "error": "",
        }
        if not url:
            entry["error"] = "attachment record carries no content URL"
        else:
            try:
                from app.services.jira_client import JiraClient

                client = JiraClient()
                if not client.is_configured():
                    entry["error"] = (
                        "Jira credentials not configured "
                        "(JIRA_BASE_URL/JIRA_PAT)"
                    )
                else:
                    data = client.download_attachment(url)
                    target_dir = (
                        store / "attachments" / request.execution_id.replace(":", "_")
                    )
                    target_dir.mkdir(parents=True, exist_ok=True)
                    safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
                    target = target_dir / safe
                    target.write_bytes(data)
                    entry["path"] = str(target)
                    entry["size_bytes"] = len(data)
                    _extract_pdf_text(entry, target)
            except Exception as exc:
                entry["error"] = (
                    f"download failed: {exc.__class__.__name__}: {exc}"
                )[:500]
        out.append(entry)
    return out


# G3: bounded PDF text materialization for the attachment researcher.
# Text extraction only - never OCR.  Failures record the exact reason.
_PDF_MAX_BYTES = 25 * 1024 * 1024
_PDF_MAX_PAGES = 20
_PDF_MAX_CHARS = 20000


def _extract_pdf_text(entry: dict, target: Path) -> None:
    """For PDF attachments, write bounded extracted text beside the binary
    (``text_path``) so the researcher reads actual content.  Encrypted,
    corrupt, oversized, or image-only files set ``text_error`` with the
    exact reason instead."""

    filename = str(entry.get("filename") or "")
    mime = str(entry.get("mime_type") or "")
    if not (
        mime.strip().lower() == "application/pdf"
        or filename.lower().endswith(".pdf")
    ):
        return
    entry["text_path"] = ""
    entry["text_error"] = ""
    if int(entry.get("size_bytes") or 0) > _PDF_MAX_BYTES:
        entry["text_error"] = (
            f"oversized PDF ({entry['size_bytes']} bytes exceeds the "
            f"{_PDF_MAX_BYTES}-byte extraction bound)"
        )
        return
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(target))
        if reader.is_encrypted:
            entry["text_error"] = (
                "encrypted PDF: text extraction not attempted"
            )
            return
        parts: list[str] = []
        total = 0
        for page in reader.pages[:_PDF_MAX_PAGES]:
            text = page.extract_text() or ""
            parts.append(text)
            total += len(text)
            if total >= _PDF_MAX_CHARS:
                break
        text = "\n".join(parts)[:_PDF_MAX_CHARS]
        if not text.strip():
            entry["text_error"] = (
                "no extractable text layer (image-only PDF; OCR is not "
                "performed)"
            )
            return
        text_path = target.with_name(target.name + ".txt")
        text_path.write_text(text, encoding="utf-8")
        entry["text_path"] = str(text_path)
    except Exception as exc:
        entry["text_error"] = (
            f"text extraction failed: {exc.__class__.__name__}: {exc}"
        )[:300]


def _conflict_text(conflict: object) -> str:
    """Human-facing text for one worker-reported conflict.

    A researcher role contract reports a conflict as ``topic`` plus the
    disagreeing ``claims`` and an optional ``resolution``.  Reading only
    ``description``/``text`` collapsed every such conflict to an empty
    string, so a real disagreement that research found was discarded before
    convergence ever saw it.  The structured shape is flattened here instead.
    """

    if not isinstance(conflict, dict):
        return str(conflict).strip()
    direct = str(conflict.get("description") or conflict.get("text") or "").strip()
    if direct:
        return direct
    topic = str(conflict.get("topic") or "").strip()
    sides: list[str] = []
    for side in conflict.get("claims") or []:
        if isinstance(side, dict):
            claim = str(side.get("claim") or "").strip()
            authority = str(side.get("authority") or "").strip()
        else:
            claim, authority = str(side).strip(), ""
        if not claim:
            continue
        sides.append(f"{claim} ({authority})" if authority else claim)
    resolution = str(conflict.get("resolution") or "").strip()
    parts = [part for part in (topic, " vs ".join(sides), resolution) if part]
    return " - ".join(parts)


def _terminal_result(
    request: AgentResearchRequest, status: ResearchWorkerStatus, notes
) -> ResearchWorkerResult:
    return ResearchWorkerResult(
        worker_role=request.worker_role,
        question_id=request.question_id,
        status=status,
        limitations=[str(note)[:500] for note in notes],
    )


_RESEARCHER_LIFECYCLE_RE = re.compile(
    r"\b(delivered|shipped|released|generally available|in production|"
    r"current product behavior|current product behaviour)\b",
    re.IGNORECASE,
)
_RESEARCHER_NEGATION_RE = re.compile(
    r"\b(not|never|no|isn't|cannot|can't|doesn't|don't|didn't|without)\b"
    r"[^.]{0,60}$",
    re.IGNORECASE,
)


def _lifecycle_claimed(text: str) -> bool:
    """True only when lifecycle language is used AFFIRMATIVELY.  A disciplined
    negation anywhere earlier in the same sentence ("No consulted
    documentation establishes this as delivered or current product
    behavior") is exactly the language the rule exists to encourage, so it
    never trips the gate."""

    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        for match in _RESEARCHER_LIFECYCLE_RE.finditer(sentence):
            prefix = sentence[: match.start()]
            if not _RESEARCHER_NEGATION_RE.search(
                prefix.replace("\n", " ")
            ) and not re.search(
                r"\b(no|not|never|cannot|can't|doesn't|don't|didn't|isn't|without)\b",
                prefix,
                re.IGNORECASE,
            ):
                return True
    return False


def validate_agent_result_shape(raw: object, worker_role) -> str | None:
    """Canonical result-shape rules shared by the bridge (fulfill time) and
    the provider (resume time): one schema, one vocabulary, one path grammar.
    Returns a rejection reason, or None when the shape is admissible.
    Never weakens admission: existence/revision/source-membership checks
    still run at resume where the filesystem and bundle are available."""

    if not isinstance(raw, dict):
        return "result is not a JSON object"
    try:
        status = ResearchWorkerStatus(str(raw.get("status") or ""))
    except ValueError:
        allowed = ", ".join(sorted(s.value for s in ResearchWorkerStatus))
        return f"result status is outside the R2 vocabulary (allowed: {allowed})"
    if status == ResearchWorkerStatus.AWAITING_HOST:
        return "a returned result cannot claim to still be waiting"
    is_code = str(getattr(worker_role, "value", worker_role)) == "CODE_RESEARCHER"
    findings = raw.get("findings") or []
    if not isinstance(findings, list):
        return "findings is not a list"
    for index, item in enumerate(findings):
        if not isinstance(item, dict) or not str(item.get("claim") or "").strip():
            return f"findings[{index}] lacks a claim"
        # Lifecycle language discipline: "delivered/shipped/released/current
        # product behavior" claims are documentation-established-behavior
        # statements only (EXISTING_BEHAVIOR).  A fix comment, a PR, code at
        # HEAD, or a screenshot never by itself establishes release state.
        claim_text = str(item.get("claim") or "")
        role_value = str(item.get("evidence_role") or "")
        if _lifecycle_claimed(claim_text) and (
            role_value != ResearchFindingEvidenceRole.EXISTING_BEHAVIOR.value
        ):
            return (
                f"findings[{index}] uses release/current-behavior language "
                "without documentation-established EXISTING_BEHAVIOR evidence"
            )
        if is_code:
            path = str(item.get("path") or "")
            if not path:
                return f"findings[{index}] lacks a repository-relative path"
            if ";" in path:
                return (
                    f"findings[{index}] packs multiple paths into one field; "
                    "split them into one finding per file"
                )
            if ":" in path:
                return (
                    f"findings[{index}] path carries a line-range suffix; "
                    "path must be the bare repo-relative file path - put line "
                    "ranges in the claim text"
                )
            if not str(item.get("repository") or "").strip():
                return f"findings[{index}] lacks the repository root"
            if not str(item.get("revision") or "").strip():
                return f"findings[{index}] lacks the exact revision"
    return None


def validate_agent_result(
    request: AgentResearchRequest, raw: object, bundle: CanonicalEvidenceBundle
) -> ResearchWorkerResult:
    return _validate_agent_result(request, raw, bundle, repository_roots=None)


def _validate_agent_result(
    request: AgentResearchRequest,
    raw: object,
    bundle: CanonicalEvidenceBundle,
    repository_roots: list[str] | None = None,
) -> ResearchWorkerResult:
    """Canonical admission validation (A5 section 14), shared by every agent
    substrate: never trust agent JSON merely because it parses."""

    shape_rejection = validate_agent_result_shape(raw, request.worker_role)
    if shape_rejection is not None:
        return _terminal_result(
            request, ResearchWorkerStatus.FAILED, [shape_rejection]
        )
    status = ResearchWorkerStatus(str(raw.get("status") or ""))
    bundle_ids = {record.evidence_id for record in bundle.records}
    allowed_refs = (
        set(request.authorized_source_refs) | set(request.context_refs) | bundle_ids
    )
    # A discovered source's provenance is its identity, but the role contract
    # lets a result declare that identity once in the result-level
    # ``source_refs`` registry instead of repeating it on every finding that
    # cites the same page.  Both shapes carry the same locator/title/query, so
    # admission resolves a finding's provenance from the finding first and
    # falls back to the registry entry naming the same ``doc:`` slug.  A slug
    # with provenance in neither place is still rejected wholesale.
    registry_provenance: dict[str, dict] = {}
    for entry in raw.get("source_refs") or []:
        if not isinstance(entry, dict):
            continue
        entry_ref = str(entry.get("source_ref") or "").strip()
        entry_prov = entry.get("provenance")
        if (
            re.fullmatch(r"doc:[A-Za-z0-9._~-]{3,80}", entry_ref)
            and isinstance(entry_prov, dict)
            and entry_prov
        ):
            registry_provenance[entry_ref] = entry_prov

    def _resolved_provenance(finding: dict, finding_refs: list[str]) -> dict:
        own = finding.get("provenance")
        if isinstance(own, dict) and own:
            return own
        for finding_ref in finding_refs:
            inherited = registry_provenance.get(finding_ref)
            if inherited:
                return inherited
        return {}

    findings = []
    for index, item in enumerate(raw.get("findings") or []):
        if not isinstance(item, dict) or not str(item.get("claim") or "").strip():
            return _terminal_result(
                request,
                ResearchWorkerStatus.FAILED,
                [f"findings[{index}] lacks a claim"],
            )
        refs = [str(ref) for ref in (item.get("source_refs") or [])]
        if request.worker_role == ResearchWorkerRole.CODE_RESEARCHER:
            # Code findings prove provenance with repository + revision +
            # path, not bundle ids: the path must exist inside an authorized
            # repository root and the claimed revision must match the repo's
            # current HEAD (read-only verification; never a mutation).
            repo = str(item.get("repository") or "")
            path = str(item.get("path") or "")
            revision = str(item.get("revision") or "")
            roots = [
                os.path.abspath(root)
                for root in (
                    repository_roots
                    if repository_roots is not None
                    else [
                        os.environ.get(name, "").strip()
                        for name in RESEARCH_REPOSITORY_ENV_VARS
                    ]
                )
                if root
            ]
            repo_ok = any(
                os.path.abspath(repo).casefold() == root.casefold()
                for root in roots
            )
            if not repo_ok:
                return _terminal_result(
                    request,
                    ResearchWorkerStatus.FAILED,
                    [f"findings[{index}] cites an unauthorized repository"],
                )
            full_path = os.path.join(repo, path.replace("/", os.sep))
            if not path or not os.path.exists(full_path):
                return _terminal_result(
                    request,
                    ResearchWorkerStatus.FAILED,
                    [f"findings[{index}] cites a path that does not exist"],
                )
            revision_sha = revision.split(" ")[0].strip()
            if re.fullmatch(r"[0-9a-f]{40}", revision_sha):
                import subprocess

                head = subprocess.run(
                    ["git", "-C", repo, "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                ).stdout.strip()
                if head and head != revision_sha:
                    return _terminal_result(
                        request,
                        ResearchWorkerStatus.FAILED,
                        [
                            f"findings[{index}] claims revision "
                            f"{revision_sha[:12]} but the repository is at "
                            f"{head[:12]}"
                        ],
                    )
        else:
            unknown = [ref for ref in refs if ref not in allowed_refs]
            if unknown:
                # Fabricated/unknown source reference: reject the result -
                # except documentation sources the DOC researcher discovered
                # itself inside the authorized documentation scopes, which
                # must carry full provenance instead of a bundle id.
                if request.worker_role == ResearchWorkerRole.DOC_RESEARCHER:
                    prov = _resolved_provenance(item, refs)
                    discovered_ok = (
                        isinstance(prov, dict)
                        and all(
                            re.fullmatch(r"doc:[A-Za-z0-9._~-]{3,80}", ref)
                            for ref in unknown
                        )
                        and str(prov.get("locator") or "").strip()
                        and str(prov.get("title") or "").strip()
                        and str(prov.get("query") or "").strip()
                    )
                    if discovered_ok:
                        unknown = []
                if unknown:
                    detail = (
                        f"findings[{index}] cites sources outside the "
                        f"authorized set: {', '.join(sorted(unknown))}"
                    )
                    if request.worker_role == ResearchWorkerRole.DOC_RESEARCHER and all(
                        re.fullmatch(r"doc:[A-Za-z0-9._~-]{3,80}", ref)
                        for ref in unknown
                    ):
                        prov = _resolved_provenance(item, refs)
                        missing = [
                            field
                            for field in ("locator", "title", "query")
                            if not (
                                isinstance(prov, dict)
                                and str(prov.get(field) or "").strip()
                            )
                        ]
                        detail = (
                            f"findings[{index}] cites discovered documentation "
                            f"{', '.join(sorted(unknown))} without complete "
                            f"provenance (missing: {', '.join(missing)})"
                        )
                    return _terminal_result(
                        request,
                        ResearchWorkerStatus.FAILED,
                        [detail],
                    )
            # A discovered-source provenance block must be tied to a doc: ref;
            # provenance without the ref (or vice versa) is malformed.
            if request.worker_role == ResearchWorkerRole.DOC_RESEARCHER:
                has_doc_ref = any(
                    re.fullmatch(r"doc:[A-Za-z0-9._~-]{3,80}", ref)
                    for ref in refs
                )
                has_prov = bool(_resolved_provenance(item, refs))
                if has_doc_ref != has_prov:
                    return _terminal_result(
                        request,
                        ResearchWorkerStatus.FAILED,
                        [
                            f"findings[{index}] discovered-source provenance "
                            "and doc: reference must appear together"
                        ],
                    )
        try:
            role = ResearchFindingEvidenceRole(
                str(item.get("evidence_role") or "SUPPORTING_CONTEXT")
            )
        except ValueError:
            role = ResearchFindingEvidenceRole.SUPPORTING_CONTEXT
        # Lifecycle language ("delivered", "current product behavior", ...)
        # additionally requires a documentation basis, not only the role
        # label: the finding must cite documentation (bundle doc record or a
        # provenance-carrying discovered doc source).
        if _lifecycle_claimed(str(item.get("claim") or "")):
            doc_ids = {
                record.evidence_id
                for record in bundle.records
                if record.source_type
                in {
                    EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
                    EvidenceSourceType.DITA_SPECIFICATION,
                    EvidenceSourceType.DITA_OT_DOCUMENTATION,
                    EvidenceSourceType.AEM_ASSETS_PLATFORM_DOCUMENTATION,
                }
            }
            if not (set(refs) & doc_ids) and not any(
                ref.startswith("doc:") for ref in refs
            ):
                return _terminal_result(
                    request,
                    ResearchWorkerStatus.FAILED,
                    [
                        f"findings[{index}] claims release/current product "
                        "behavior without a documentation source"
                    ],
                )
        findings.append(
            ResearchFinding(
                claim=str(item["claim"]).strip()[:2000],
                source_refs=refs,
                evidence_role=role,
                applicability=str(item.get("applicability") or "")[:500],
                provenance=_resolved_provenance(item, refs),
                repository=(
                    str(item.get("repository") or "")[:500]
                    if request.worker_role == ResearchWorkerRole.CODE_RESEARCHER
                    else ""
                ),
                revision=(
                    str(item.get("revision") or "")[:200]
                    if request.worker_role == ResearchWorkerRole.CODE_RESEARCHER
                    else ""
                ),
                path=(
                    str(item.get("path") or "")[:1000]
                    if request.worker_role == ResearchWorkerRole.CODE_RESEARCHER
                    else ""
                ),
            )
        )
    if status == ResearchWorkerStatus.ANSWER_FOUND and not findings:
        return _terminal_result(
            request,
            ResearchWorkerStatus.FAILED,
            ["ANSWER_FOUND without findings is not a valid agent result"],
        )
    if status in {
        ResearchWorkerStatus.SOURCE_UNAVAILABLE,
        ResearchWorkerStatus.WORKER_UNAVAILABLE,
        ResearchWorkerStatus.FAILED,
    } and findings:
        return _terminal_result(
            request,
            ResearchWorkerStatus.FAILED,
            ["unavailable/failed status cannot carry findings"],
        )
    try:
        return ResearchWorkerResult(
            worker_role=request.worker_role,
            question_id=request.question_id,
            status=status,
            findings=findings,
            source_refs=sorted(
                {ref for finding in findings for ref in finding.source_refs}
            ),
            applicability=str(raw.get("applicability") or "")[:500],
            currentness=str(raw.get("currentness") or "")[:200],
            limitations=[str(item)[:500] for item in (raw.get("limitations") or [])],
            conflicts=[
                _conflict_text(item)[:500]
                for item in (raw.get("conflicts") or [])
                if _conflict_text(item)
            ],
        )
    except Exception as exc:
        return _terminal_result(
            request,
            ResearchWorkerStatus.FAILED,
            [f"result failed envelope validation: {exc.__class__.__name__}"],
        )


class DeterministicResearchProvider:
    """The existing R2 deterministic workers behind the provider boundary."""

    provider_id = _PROVIDER_DETERMINISTIC
    model_execution = False

    def __init__(self, workers: dict[ResearchWorkerRole, object]) -> None:
        self._workers = workers

    def execute(
        self,
        request: AgentResearchRequest,
        *,
        bundle: CanonicalEvidenceBundle,
        question,
        requirement,
        repository_roots: list[str] | None = None,
    ) -> ResearchWorkerResult:
        worker = self._workers[request.worker_role]
        if request.worker_role == ResearchWorkerRole.CODE_RESEARCHER:
            return worker.research(
                question, requirement, bundle, repository_roots=repository_roots
            )
        return worker.research(question, requirement, bundle)


class ModelAgentExecutionProvider:
    """Real model-backed research workers via the backend's configured LLM
    substrate.  The model receives only the bounded authorized context and
    the canonical role contract; it has NO tools - it can only interpret the
    supplied evidence, so it cannot write, mutate, or fetch anything.  The
    runtime validates the structured result before admission."""

    provider_id = _PROVIDER_MODEL_AGENT

    def __init__(self) -> None:
        # Truthful receipts: True only when an actual model invocation ran
        # during the last execute() call - never for WORKER_UNAVAILABLE.
        self.last_model_execution = False
        self.last_role_contract = ""

    def execute(
        self,
        request: AgentResearchRequest,
        *,
        bundle: CanonicalEvidenceBundle,
        question,
        requirement,
        repository_roots: list[str] | None = None,
    ) -> ResearchWorkerResult:
        self.last_model_execution = False
        try:
            name, version, contract = load_role_contract(request.worker_role)
        except FileNotFoundError:
            return self._terminal(
                request,
                ResearchWorkerStatus.WORKER_UNAVAILABLE,
                ["canonical role contract unavailable for this role"],
            )
        self.last_role_contract = f"{name}@{version}"
        try:
            from app.services import llm_service

            if not llm_service.is_llm_available():
                return self._terminal(
                    request,
                    ResearchWorkerStatus.WORKER_UNAVAILABLE,
                    ["no model provider is configured (LLM credentials absent)"],
                )
            system_prompt = (
                contract
                + "\n\nYou MUST answer with a single JSON object matching the "
                "requested schema. Never write acceptance criteria. Cite only "
                "supplied source_refs.\n"
            )
            user_prompt = self._user_prompt(request, bundle, question)
            # The model invocation actually happens here.
            self.last_model_execution = True
            raw = asyncio.run(
                llm_service.generate_json(
                    system_prompt,
                    user_prompt,
                    max_tokens=1500,
                    step_name=f"agent_research_{request.worker_role.value}",
                )
            )
        except Exception as exc:
            return self._terminal(
                request,
                ResearchWorkerStatus.FAILED,
                [f"model execution failed: {exc.__class__.__name__}"],
            )
        return self._validate_and_build(
            request, raw, bundle, role_contract=f"{name}@{version}"
        )

    # ------------------------------------------------------------------

    def _user_prompt(
        self,
        request: AgentResearchRequest,
        bundle: CanonicalEvidenceBundle,
        question,
    ) -> str:
        evidence_lines = []
        for row in _authorized_evidence_rows(request, bundle):
            evidence_lines.append(
                f"- source_ref: {row['source_ref']}\n"
                f"  source_type: {row['source_type']}\n"
                f"  excerpt: {row['excerpt']}"
            )
        return (
            f"question_id: {request.question_id}\n"
            f"question_revision: {request.question_revision}\n"
            f"question: {question.question}\n"
            f"requested_claim: {request.requested_claim}\n"
            f"applicability: {request.applicability or 'current ticket'}\n"
            f"currentness: {request.currentness or 'current'}\n\n"
            "Authorized evidence (cite only these source_refs):\n"
            + ("\n".join(evidence_lines) or "(none supplied)")
            + "\n\nReturn JSON: {\"status\": one of ANSWER_FOUND, PARTIAL, "
            "NOT_FOUND, SOURCE_UNAVAILABLE, CONFLICTED; "
            '"applicability": string; "currentness": string; '
            '"limitations": [string]; "conflicts": [string]; '
            '"findings": [{"claim": string, "source_refs": [string], '
            '"evidence_role": EXISTING_BEHAVIOR | REQUIREMENT_CLARIFICATION '
            "| SUPPORTING_CONTEXT | IMPLEMENTATION_EVIDENCE | "
            'OBSERVED_BEHAVIOR | DESIRED_BEHAVIOR}]}.  NOT_FOUND means the '
            "authorized evidence did not answer the question; never claim "
            "the opposite behavior."
        )

    def _validate_and_build(
        self,
        request: AgentResearchRequest,
        raw: object,
        bundle: CanonicalEvidenceBundle,
        *,
        role_contract: str,
    ) -> ResearchWorkerResult:
        return validate_agent_result(request, raw, bundle)
    def _terminal(
        self, request: AgentResearchRequest, status: ResearchWorkerStatus, notes
    ) -> ResearchWorkerResult:
        return ResearchWorkerResult(
            worker_role=request.worker_role,
            question_id=request.question_id,
            status=status,
            limitations=[str(note)[:500] for note in notes],
        )


class HostMediatedResearchProvider:
    """COPILOT_HOST: the canonical runtime emits a pending
    AgentResearchRequest for the Copilot host to delegate to the registered
    custom agent, and consumes the result only through the resume contract.
    Python never launches Copilot; with no fulfilled result the run waits
    (AWAITING_HOST) - it never silently substitutes another substrate."""

    provider_id = "COPILOT_HOST"

    def __init__(self, store: Path | None = None) -> None:
        self._store = store or agent_research_store()
        # Receipt metadata from the last fulfilled result consumed.
        self.last_model_execution = False
        self.last_model = ""
        self.last_role_contract = ""

    @staticmethod
    def _pending_path(store: Path, execution_id: str) -> Path:
        # Windows-legal filename: colon is not allowed in file names.
        return store / "pending" / f"{execution_id.replace(':', '_')}.json"

    @staticmethod
    def _fulfilled_path(store: Path, execution_id: str) -> Path:
        return store / "fulfilled" / f"{execution_id.replace(':', '_')}.json"

    # The evidence binding is retrieval output, not question identity.
    # Semantic (embedding/ANN) retrieval is approximate, so two runs over the
    # same ticket legitimately admit slightly different evidence rows; hashing
    # those rows into the logical key made every re-run mint a fresh episode
    # and stranded the host's fulfilled results forever.
    _EVIDENCE_BINDING_FIELDS = frozenset({"authorized_source_refs", "context_refs"})

    @classmethod
    def _logical_execution_key(cls, request: AgentResearchRequest) -> str:
        """Run-independent identity of the logical research execution: the
        question, role, claim and requirement WITHOUT the run scope or the
        retrieval-dependent evidence binding.  The logical question stays
        traceable across runs through this key (and question_id); the run
        scope makes each run's executions distinct."""

        identity = request.model_dump(
            mode="json",
            exclude={"execution_id", *cls._EVIDENCE_BINDING_FIELDS},
        )
        identity["run_scope"] = ""
        return stable_sha256(identity)[:32]

    @staticmethod
    def _request_from_payload(payload: dict) -> AgentResearchRequest | None:
        """Rebuild the exact request an episode emitted.  The stored payload
        also carries host-delegation context (``logical_execution_key``,
        ``authorized_evidence``, roots, RAG candidates); those are not model
        fields, so they are dropped before validation."""

        try:
            return AgentResearchRequest.model_validate(
                {
                    field: value
                    for field, value in payload.items()
                    if field in AgentResearchRequest.model_fields
                }
            )
        except Exception:
            return None

    def _resolve_run_scope(self, request: AgentResearchRequest) -> AgentResearchRequest:
        """G1: bind this invocation's request to its research episode.

        - No pending episode for the logical key -> the current invocation's
          own run scope (a fresh episode).
        - An episode exists and is still in flight (pending unfulfilled, or
          fulfilled but not yet consumed) -> resume under the episode's
          recorded scope; the emit-side pass and the resume pass are
          different top-level invocations of one logical run.
        - The episode's fulfilled result was already consumed -> that logical
          run completed; this invocation is a NEW run and gets a fresh scope,
          so a second Generate-UAC run delegates fresh research instead of
          dying on the consumed marker.

        Consume-once is untouched: within one episode, an already-consumed
        fulfilled file can never be consumed again (the bridge rejects the
        duplicate write; a new episode has a different execution id)."""

        import json as _json

        logical_key = self._logical_execution_key(request)
        pending_dir = self._store / "pending"
        # Every pending episode for this logical key.  A completed (consumed)
        # episode must never shadow an in-flight episode for the same
        # logical question - with several runs in the store, the oldest
        # matching pending is usually the consumed one.
        #
        # The key is recomputed from each stored request rather than read from
        # the payload's recorded ``logical_execution_key``, so an episode
        # emitted under an older key formula still resolves instead of being
        # silently stranded.
        episodes: dict[str, AgentResearchRequest] = {}
        emitted_at: dict[str, float] = {}
        if pending_dir.is_dir():
            for candidate in sorted(pending_dir.glob("agent-request_*.json")):
                try:
                    payload = _json.loads(
                        candidate.read_text(encoding="utf-8-sig")
                    )
                except Exception:
                    continue
                stored = self._request_from_payload(payload)
                if stored is None:
                    continue
                if self._logical_execution_key(stored) != logical_key:
                    continue
                scope = str(payload.get("run_scope") or "")
                episodes[scope] = stored
                try:
                    emitted_at[scope] = candidate.stat().st_mtime
                except OSError:
                    emitted_at[scope] = 0.0
        if not episodes:
            return request

        # Resuming an episode adopts the request that episode actually
        # emitted.  Rebuilding it from the CURRENT request instead would
        # recompute a different execution_id whenever retrieval admitted a
        # different evidence set, so the fulfilled result would never be
        # found - and the result was produced against the stored evidence
        # binding, which is what admission must validate it against.
        # Prefer a resumable episode (fulfilled, not yet consumed), then an
        # in-flight one (pending, unfulfilled); only when every matching
        # episode completed does this invocation become a fresh run.  Several
        # episodes qualify whenever an earlier run's research was delegated
        # but never consumed, so the tiebreak is the most recently emitted
        # episode - that is the delegation the host just answered.  Run-scope
        # ids are random, so ordering by scope string would pick arbitrarily.
        resumable: list[str] = []
        in_flight: list[str] = []
        completed = False
        for scope, episode_request in episodes.items():
            fulfilled = self._fulfilled_path(
                self._store, episode_request.execution_id
            )
            if fulfilled.exists():
                if fulfilled.with_suffix(".consumed").exists():
                    completed = True
                else:
                    resumable.append(scope)
            else:
                in_flight.append(scope)

        def _newest(scopes: list[str]) -> str:
            return max(scopes, key=lambda scope: (emitted_at.get(scope, 0.0), scope))

        if resumable:
            return episodes[_newest(resumable)]
        if completed:
            # A sibling episode already completed this logical question's
            # research: this invocation is a new run and mints fresh
            # executions.  A pending-only episode alongside a completed one
            # is a superseded duplicate (never delegated, or its pass's
            # research terminated elsewhere) - waiting on it would block
            # every later run forever.
            return request
        if in_flight:
            return episodes[_newest(in_flight)]
        # Every matching episode completed; this top-level invocation is a
        # new run with fresh executions.
        return request

    def execute(
        self,
        request: AgentResearchRequest,
        *,
        bundle: CanonicalEvidenceBundle,
        question,
        requirement,
        repository_roots: list[str] | None = None,
    ) -> ResearchWorkerResult:
        import json

        self.last_model_execution = False
        # G1: bind the request to its run-scoped research episode before any
        # store access.  A completed episode (fulfilled+consumed) yields the
        # current invocation's fresh scope, so a repeated Generate-UAC run
        # delegates fresh research; an in-flight episode resumes under its
        # recorded scope even though the resume pass is a new top-level
        # invocation with a different canonical run id.
        request = self._resolve_run_scope(request)
        fulfilled = self._fulfilled_path(self._store, request.execution_id)
        if fulfilled.exists():
            consumed = fulfilled.with_suffix(".consumed")
            if consumed.exists():
                return _terminal_result(
                    request,
                    ResearchWorkerStatus.FAILED,
                    ["duplicate result: this execution was already consumed"],
                )
            try:
                envelope = json.loads(fulfilled.read_text(encoding="utf-8"))
            except Exception:
                return _terminal_result(
                    request,
                    ResearchWorkerStatus.FAILED,
                    ["fulfilled result is not readable JSON"],
                )
            rejection = self._validate_resume_envelope(request, envelope, bundle)
            if rejection is not None:
                return _terminal_result(
                    request, ResearchWorkerStatus.FAILED, [rejection]
                )
            result = _validate_agent_result(
                request,
                envelope.get("result"),
                bundle,
                repository_roots=repository_roots,
            )
            if result.status != ResearchWorkerStatus.FAILED:
                # Consume once; the receipt rides on the execution row.
                consumed.write_text("consumed", encoding="utf-8")
                self.last_model_execution = True
                self.last_model = str(envelope.get("model") or "")
                self.last_role_contract = str(
                    envelope.get("role_contract_version") or ""
                )
            return result
        # No fulfilled result: emit the pending request for the host.
        pending = self._pending_path(self._store, request.execution_id)
        if not pending.exists():
            payload = request.model_dump(mode="json")
            # G1: the run-independent logical identity lets a later
            # invocation resolve this episode's run scope; run_scope itself
            # rides in the payload as a model field.
            payload["logical_execution_key"] = self._logical_execution_key(
                request
            )
            # The delegated leaf agent has a read-only, bounded toolset and
            # cannot resolve evidence IDs: carry the authorized content
            # (bounded excerpts) and, for code research, the authorized
            # repository roots so the leaf can inspect real evidence.
            payload["authorized_evidence"] = _authorized_evidence_rows(
                request, bundle
            )
            # Clone-backed research runs where the clones actually live.  When
            # the caller supplies roots it owns them: pass them through
            # verbatim, because normalizing a remote caller's path against this
            # host's filesystem yields a path the caller's worker cannot read.
            # Only this host's env-configured roots are resolved locally, which
            # keeps the same-machine CLI behaviour unchanged.
            if repository_roots is not None:
                payload["authorized_repository_roots"] = [
                    root.strip()
                    for root in repository_roots
                    if root and root.strip()
                ]
            else:
                payload["authorized_repository_roots"] = [
                    os.path.abspath(root)
                    for root in (
                        os.environ.get(name, "").strip()
                        for name in RESEARCH_REPOSITORY_ENV_VARS
                    )
                    if root
                ]
            # Attachment researchers read real content: materialize authorized
            # attachments into the store (exact failure reasons recorded).
            payload["attachment_files"] = _attachment_files(
                request, bundle, self._store
            )
            # Doc researchers get the approved local documentation scopes to
            # search/read directly, generic vocabulary-routed search seeds
            # derived from the requested claim, and RAG discovery leads from
            # the existing indexed product-documentation corpus (the primary
            # discovery input; the leaf verifies before citing).
            if request.worker_role == ResearchWorkerRole.DOC_RESEARCHER:
                payload["documentation_roots"] = _documentation_roots()
                (
                    candidates,
                    rag_status,
                    doc_queries,
                    expansion_terms,
                ) = _rag_documentation_candidates(request.requested_claim)
                payload["documentation_queries"] = doc_queries
                payload["rag_candidates"] = candidates
                payload["rag_status"] = rag_status
                # Retrieval hints only - provenance for the coordinator and
                # audit, never evidence.
                payload["rag_expansion_terms"] = expansion_terms
            # Bind the role-contract version AT EMISSION: the result must
            # answer this request under the contract this request was
            # emitted with, regardless of later contract edits.
            contract_name, contract_version, _text = load_role_contract(
                request.worker_role
            )
            payload["role_contract_version"] = (
                f"{contract_name}@{contract_version}"
            )
            pending.parent.mkdir(parents=True, exist_ok=True)
            pending.write_text(
                json.dumps(payload, indent=1, ensure_ascii=False),
                encoding="utf-8",
            )
        return _terminal_result(
            request,
            ResearchWorkerStatus.AWAITING_HOST,
            ["pending host delegation: the Copilot host has not returned a "
             "result for this execution"],
        )

    def _validate_resume_envelope(
        self,
        request: AgentResearchRequest,
        envelope: object,
        bundle: CanonicalEvidenceBundle,
    ) -> str | None:
        """The resume contract (spec section 6): the returned result must
        prove it answers THIS emitted request."""

        # Canonical envelope schema first: the host receipt (provider, model,
        # role-contract version) and the leaf payload are structurally
        # separated; extra top-level fields are forbidden so a leaf cannot
        # smuggle receipt claims into the envelope.
        try:
            parsed = HostAgentResultEnvelope.model_validate(envelope)
        except Exception as exc:
            return f"resume envelope failed the canonical schema: {exc.__class__.__name__}"
        if parsed.execution_id != request.execution_id:
            return "execution_id does not match the emitted request"
        if parsed.question_id != request.question_id:
            return "result answers a different question"
        if (
            request.question_revision
            and parsed.question_revision != request.question_revision
        ):
            return "stale result: question revision changed"
        if parsed.worker_role != request.worker_role:
            return "result comes from a different worker role"
        pending = self._pending_path(self._store, request.execution_id)
        if not pending.exists():
            return "unknown execution: no pending request was emitted"
        # Identity rule shared with the bridge: the envelope's role-contract
        # version must equal the version bound into the emitted request.
        # Legacy pendings without the binding fall back to the current
        # canonical contract hash.
        name, version, _text = load_role_contract(request.worker_role)
        expected = f"{name}@{version}"
        try:
            import json as _json

            bound = (
                _json.loads(pending.read_text(encoding="utf-8-sig")).get(
                    "role_contract_version"
                )
                or ""
            )
        except Exception:
            bound = ""
        if bound:
            expected = str(bound)
        if parsed.role_contract_version != expected:
            return "role contract version drifted from the emitted request"
        return None


class RoutedResearchProvider:
    """Mode-aware provider: deterministic | backend_model | copilot_host |
    shadow.  Shadow runs both read-only and keeps the deterministic result
    authoritative; the model comparison is returned for tracing, never for
    promotion."""

    def __init__(
        self,
        deterministic: DeterministicResearchProvider,
        agent: ModelAgentExecutionProvider | None = None,
        host: HostMediatedResearchProvider | None = None,
        mode: str | None = None,
    ) -> None:
        self._deterministic = deterministic
        self._agent = agent or ModelAgentExecutionProvider()
        self._host = host or HostMediatedResearchProvider()
        self._mode = mode or agent_research_mode()

    @property
    def mode(self) -> str:
        return self._mode

    def execute(self, request, **kwargs):
        """Return (authoritative_result, executions) where executions carries
        (provider_id, model_execution, result) per actual execution."""

        if self._mode == "backend_model":
            result = self._agent.execute(request, **kwargs)
            return result, [
                (
                    self._agent.provider_id,
                    bool(getattr(self._agent, "last_model_execution", True)),
                    result,
                    {
                        "role_contract": getattr(
                            self._agent, "last_role_contract", ""
                        ),
                    },
                )
            ]
        if self._mode == "copilot_host":
            result = self._host.execute(request, **kwargs)
            return result, [
                (
                    self._host.provider_id,
                    bool(getattr(self._host, "last_model_execution", False)),
                    result,
                    {
                        "model": getattr(self._host, "last_model", ""),
                        "role_contract": getattr(
                            self._host, "last_role_contract", ""
                        ),
                    },
                )
            ]
        primary = self._deterministic.execute(request, **kwargs)
        executions = [(self._deterministic.provider_id, False, primary, {})]
        if self._mode == "shadow":
            shadow = self._agent.execute(request, **kwargs)
            executions.append(
                (
                    self._agent.provider_id,
                    bool(getattr(self._agent, "last_model_execution", True)),
                    shadow,
                    {},
                )
            )
        return primary, executions
