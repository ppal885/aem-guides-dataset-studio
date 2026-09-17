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


def _suggested_documentation_queries(claim: str) -> list[str]:
    """Generic, vocabulary-routed documentation search seeds for the DOC
    researcher: match the requested claim against the curated AEM Guides
    product vocabulary (canonical terms + synonym groups) and build bounded
    queries from matched canonical terms plus the claim's own significant
    tokens.  Nothing here is ticket-specific; routing comes from the claim
    text and the shipped vocabulary file only."""

    text = (claim or "").casefold()
    if not text.strip():
        return []
    vocab = _load_guides_vocabulary()
    terms = [
        term for term in vocab.get("canonical_terms", []) if isinstance(term, str)
    ]
    for group in vocab.get("synonyms", []) or []:
        if isinstance(group, dict):
            terms.extend(
                t for t in group.get("terms", []) if isinstance(t, str)
            )
    matched = sorted(
        {
            term
            for term in terms
            if len(term) > 3
            and re.search(
                r"(?<![\w-])" + re.escape(term.casefold()) + r"(?![\w-])", text
            )
        },
        key=str.casefold,
    )
    tokens = [
        token
        for token in re.findall(r"[a-z][a-z0-9-]{3,}", text)
        if token not in _QUERY_STOPWORDS
    ]
    queries: list[str] = []
    if matched:
        queries.append("AEM Guides " + " ".join(matched[:4]))
    if tokens:
        queries.append("AEM Guides " + " ".join(tokens[:6]))
    seen: set[str] = set()
    out: list[str] = []
    for query in queries:
        if query not in seen:
            seen.add(query)
            out.append(query)
    return out[:3]


def _rag_documentation_candidates(
    claim: str, *, top_k: int = 5
) -> tuple[list[dict], str]:
    """Discovery leads from the existing indexed AEM Guides / product
    documentation retrieval layer (``doc_retriever_service`` - the same
    retrieval the pipeline's full_rag path uses: Chroma, then
    JSON+embedding, then lexical).  Returns (candidates, status_note).
    Candidates are discovery input for the delegated DOC researcher - never
    acceptance authority, and a retrieval score is never authority."""

    try:
        from app.services.doc_retriever_service import (
            retrieve_relevant_docs_with_diagnostics,
        )

        payload = retrieve_relevant_docs_with_diagnostics(
            (claim or "")[:4000], k=top_k
        )
    except Exception as exc:
        return [], f"rag retrieval unavailable: {exc.__class__.__name__}"
    rows = payload.get("results") or []
    mode = str(payload.get("retrieval_mode") or "none")
    candidates: list[dict] = []
    for row in rows:
        candidates.append(
            {
                "chunk_id": str(row.get("chunk_id") or row.get("id") or ""),
                "source_type": str(row.get("corpus") or "aem_guides"),
                "title": str(row.get("title") or ""),
                "url": str(row.get("url") or ""),
                "score": row.get("score"),
                "snippet": _excerpt(row.get("snippet") or ""),
            }
        )
    status = f"ok:{mode}" if candidates else f"no candidates:{mode}"
    return candidates, status


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
            except Exception as exc:
                entry["error"] = (
                    f"download failed: {exc.__class__.__name__}: {exc}"
                )[:500]
        out.append(entry)
    return out


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
        if _RESEARCHER_LIFECYCLE_RE.search(claim_text) and (
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
                    prov = item.get("provenance") or {}
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
                    return _terminal_result(
                        request,
                        ResearchWorkerStatus.FAILED,
                        ["finding cites sources outside the authorized set"],
                    )
            # A discovered-source provenance block must be tied to a doc: ref;
            # provenance without the ref (or vice versa) is malformed.
            if request.worker_role == ResearchWorkerRole.DOC_RESEARCHER:
                has_doc_ref = any(
                    re.fullmatch(r"doc:[A-Za-z0-9._~-]{3,80}", ref)
                    for ref in refs
                )
                has_prov = bool(item.get("provenance"))
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
        if _RESEARCHER_LIFECYCLE_RE.search(str(item.get("claim") or "")):
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
                provenance=(
                    item.get("provenance")
                    if isinstance(item.get("provenance"), dict)
                    else {}
                ),
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
            conflicts=[str(item)[:500] for item in (raw.get("conflicts") or [])],
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
            # The delegated leaf agent has a read-only, bounded toolset and
            # cannot resolve evidence IDs: carry the authorized content
            # (bounded excerpts) and, for code research, the authorized
            # repository roots so the leaf can inspect real evidence.
            payload["authorized_evidence"] = _authorized_evidence_rows(
                request, bundle
            )
            # Same root resolution as the deterministic code worker: when the
            # caller did not pass roots, fall back to the configured env vars.
            effective_roots = (
                repository_roots
                if repository_roots is not None
                else [
                    os.environ.get(name, "").strip()
                    for name in RESEARCH_REPOSITORY_ENV_VARS
                ]
            )
            payload["authorized_repository_roots"] = [
                os.path.abspath(root) for root in effective_roots if root
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
                payload["documentation_queries"] = (
                    _suggested_documentation_queries(request.requested_claim)
                )
                candidates, rag_status = _rag_documentation_candidates(
                    request.requested_claim
                )
                payload["rag_candidates"] = candidates
                payload["rag_status"] = rag_status
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
