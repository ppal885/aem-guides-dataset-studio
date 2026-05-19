"""Enterprise Jira-aware UAC generation for AEM Guides QA workflows.

The service is intentionally deterministic by default.  LLM providers can be
plugged in later, but every returned point still goes through the same evidence
critic so generic or unsupported UAC advice cannot leak into the response.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_MESSAGE = "Insufficient evidence from indexed Jira data."

_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9_]{1,10}-\d+\b", re.I)
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_:-]{2,}", re.I)
_WS_RE = re.compile(r"\s+")

_GENERIC_REJECT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\btest\s+regression\b",
        r"\bverify\s+ui\b",
        r"\bvalidate\s+functionality\b",
        r"\btest\s+positive\s+and\s+negative\s+scenarios\b",
    )
)


@dataclass(frozen=True)
class ScenarioPattern:
    """Reusable domain scenario template."""

    scenario: str
    why: str
    layer: str
    automation_fit: str


@dataclass(frozen=True)
class DomainPlaybook:
    """Domain-specific UAC reasoning hooks."""

    key: str
    aliases: tuple[str, ...]
    default_entities: tuple[str, ...]
    default_outputs: tuple[str, ...]
    risk_theme: str
    scenarios: tuple[ScenarioPattern, ...]
    clarifications: tuple[str, ...]


DOMAIN_PLAYBOOKS: dict[str, DomainPlaybook] = {
    "keyref": DomainPlaybook(
        key="keyref",
        aliases=("keyref", "keyscope", "keydef", "keys", "key space"),
        default_entities=("keyref", "keydef", "keyscope"),
        default_outputs=("editor_preview", "native_pdf", "sites"),
        risk_theme="key-space resolution",
        scenarios=(
            ScenarioPattern(
                scenario="{jira_key}: Resolve {entity} through scoped keydef before publishing {output}",
                why="{entity} failures often surface only after map-level keyscope changes; {output} must match author-time resolution.",
                layer="Publishing",
                automation_fit="Partial",
            ),
            ScenarioPattern(
                scenario="{jira_key}: Rename or move the keydef target and re-open {entity} in Web Editor",
                why="{entity} can pass initial authoring but fail after target movement or stale key cache.",
                layer="UI",
                automation_fit="Partial",
            ),
        ),
        clarifications=(
            "For {jira_key}, which map/keyscope is the acceptance source of truth for {entity} in {output}?",
            "Should unresolved {entity} block {output} generation or surface as a warning for {jira_key}?",
        ),
    ),
    "conref": DomainPlaybook(
        key="conref",
        aliases=("conref", "conkeyref", "reusable content", "content reference"),
        default_entities=("conref", "conkeyref"),
        default_outputs=("editor_preview", "native_pdf", "sites"),
        risk_theme="content reference resolution",
        scenarios=(
            ScenarioPattern(
                scenario="{jira_key}: Validate {entity} resolution after source topic move in {output}",
                why="{entity} regressions commonly appear after reusable content is renamed, moved, or re-keyed.",
                layer="Publishing",
                automation_fit="Partial",
            ),
            ScenarioPattern(
                scenario="{jira_key}: Compare Web Editor preview and generated {output} for {entity}",
                why="{entity} preview/output divergence is a customer-visible release risk.",
                layer="Hybrid",
                automation_fit="Partial",
            ),
        ),
        clarifications=(
            "For {jira_key}, should broken {entity} in {output} fail publishing or remain a non-blocking warning?",
            "Which reusable-content source should define expected {entity} behavior for {jira_key}?",
        ),
    ),
    "ditaval": DomainPlaybook(
        key="ditaval",
        aliases=("ditaval", "conditional processing", "conditional profiling", "props filter", "profiling"),
        default_entities=("ditaval", "props", "audience", "platform", "product"),
        default_outputs=("native_pdf", "sites", "html5"),
        risk_theme="conditional filtering",
        scenarios=(
            ScenarioPattern(
                scenario="{jira_key}: Apply DITAVAL include/exclude filters for {entity} and compare {output}",
                why="{entity} filter drift can hide required content or leak excluded content in {output}.",
                layer="Publishing",
                automation_fit="Yes",
            ),
            ScenarioPattern(
                scenario="{jira_key}: Switch between two DITAVAL profiles and confirm {entity} deltas in {output}",
                why="{entity} must remain deterministic across profile changes and output regeneration.",
                layer="Publishing",
                automation_fit="Yes",
            ),
        ),
        clarifications=(
            "Which DITAVAL profile values must include or exclude {entity} in {output} for {jira_key}?",
            "Does {jira_key} require parity for {entity} between preview and generated {output}?",
        ),
    ),
    "native_pdf": DomainPlaybook(
        key="native_pdf",
        aliases=("native_pdf", "native pdf", "pdf publishing", "fop", "pdf template"),
        default_entities=("bookmap", "topicref", "glossentry"),
        default_outputs=("native_pdf",),
        risk_theme="PDF rendition correctness",
        scenarios=(
            ScenarioPattern(
                scenario="{jira_key}: Publish {output} with {entity} and inspect generated PDF structure",
                why="{entity} defects in {output} usually affect customer-visible TOC, numbering, links, or rendered text.",
                layer="Publishing",
                automation_fit="Partial",
            ),
            ScenarioPattern(
                scenario="{jira_key}: Re-run {output} after template/preset change for {entity}",
                why="{entity} can regress when Native PDF templates, variables, or processing order change.",
                layer="Publishing",
                automation_fit="Partial",
            ),
        ),
        clarifications=(
            "Which Native PDF preset/template must be used for {entity} acceptance in {jira_key}?",
            "Which {output} artifact fields prove {entity} is rendered correctly for {jira_key}?",
        ),
    ),
    "baseline": DomainPlaybook(
        key="baseline",
        aliases=("baseline", "versioned content", "version snapshot", "baseline publish"),
        default_entities=("baseline", "versioned topic", "versioned map"),
        default_outputs=("native_pdf", "sites", "editor_preview"),
        risk_theme="versioned content integrity",
        scenarios=(
            ScenarioPattern(
                scenario="{jira_key}: Publish {output} from baseline and latest versions for {entity}",
                why="{entity} must preserve version selection and avoid mixing latest content into baseline output.",
                layer="Publishing",
                automation_fit="Partial",
            ),
            ScenarioPattern(
                scenario="{jira_key}: Restore or update baseline and confirm {entity} remains stable",
                why="Baseline acceptance requires versioned {entity} behavior to survive restore/update workflows.",
                layer="UI",
                automation_fit="Partial",
            ),
        ),
        clarifications=(
            "Which baseline version of {entity} is authoritative for {output} in {jira_key}?",
            "Should {jira_key} compare {entity} against latest, baseline, or both in UAC?",
        ),
    ),
    "assets": DomainPlaybook(
        key="assets",
        aliases=("asset", "assets", "dam", "binary", "file reference"),
        default_entities=("image", "xref", "asset reference"),
        default_outputs=("native_pdf", "sites", "editor_preview"),
        risk_theme="asset reference integrity",
        scenarios=(
            ScenarioPattern(
                scenario="{jira_key}: Move referenced asset and validate {entity} in {output}",
                why="{entity} can break when DAM paths, permissions, or binary renditions change.",
                layer="Hybrid",
                automation_fit="Partial",
            ),
            ScenarioPattern(
                scenario="{jira_key}: Publish {output} with missing and restored asset reference for {entity}",
                why="{entity} must produce a diagnosable warning and recover after asset restoration.",
                layer="Publishing",
                automation_fit="Partial",
            ),
        ),
        clarifications=(
            "Which asset repository path is in scope for {entity} and {output} in {jira_key}?",
            "Should missing {entity} block {output} generation or only warn for {jira_key}?",
        ),
    ),
    "image_rendition": DomainPlaybook(
        key="image_rendition",
        aliases=("image rendition", "rendition", "thumbnail", "image handling", "image"),
        default_entities=("image", "fig", "alt"),
        default_outputs=("native_pdf", "sites", "editor_preview"),
        risk_theme="image rendition parity",
        scenarios=(
            ScenarioPattern(
                scenario="{jira_key}: Generate {output} with {entity} and compare image rendition dimensions",
                why="{entity} rendition bugs affect visible sizing, cropping, or missing images in {output}.",
                layer="Publishing",
                automation_fit="Partial",
            ),
            ScenarioPattern(
                scenario="{jira_key}: Replace source image and confirm {entity} refreshes in {output}",
                why="{entity} can use stale renditions after source asset replacement or cache reuse.",
                layer="Hybrid",
                automation_fit="Partial",
            ),
        ),
        clarifications=(
            "Which image rendition size or format proves {entity} is correct in {output} for {jira_key}?",
            "Does {jira_key} require cache invalidation checks for {entity} in {output}?",
        ),
    ),
    "glossary": DomainPlaybook(
        key="glossary",
        aliases=("glossary", "glossentry", "glossref", "glossstatus", "glossterm"),
        default_entities=("glossentry", "glossStatus", "glossterm"),
        default_outputs=("native_pdf", "sites"),
        risk_theme="glossary term rendering",
        scenarios=(
            ScenarioPattern(
                scenario="{jira_key}: Publish glossary map with {entity} and inspect {output}",
                why="{entity} defects change glossary visibility, term status, or cross-reference behavior in {output}.",
                layer="Publishing",
                automation_fit="Partial",
            ),
            ScenarioPattern(
                scenario="{jira_key}: Cross-reference {entity} from topic content and validate {output}",
                why="{entity} must resolve consistently from authored topic references to final glossary output.",
                layer="Publishing",
                automation_fit="Partial",
            ),
        ),
        clarifications=(
            "Which glossary rendering contract applies to {entity} in {output} for {jira_key}?",
            "Should {entity} appear in TOC, inline term rendering, glossary section, or all of them for {jira_key}?",
        ),
    ),
    "metadata": DomainPlaybook(
        key="metadata",
        aliases=("metadata", "prolog", "search metadata", "labels", "attributes"),
        default_entities=("prolog", "metadata", "attribute"),
        default_outputs=("native_pdf", "sites", "search_index"),
        risk_theme="metadata propagation",
        scenarios=(
            ScenarioPattern(
                scenario="{jira_key}: Propagate {entity} from DITA source into {output}",
                why="{entity} must survive ingestion, authoring, publishing, and downstream search or output consumption.",
                layer="Hybrid",
                automation_fit="Yes",
            ),
            ScenarioPattern(
                scenario="{jira_key}: Update {entity} and confirm stale metadata is removed from {output}",
                why="{entity} regressions often leave stale values after re-save or re-publish.",
                layer="API",
                automation_fit="Yes",
            ),
        ),
        clarifications=(
            "Which {entity} fields must be visible in {output} acceptance for {jira_key}?",
            "Should {jira_key} validate {entity} in authoring metadata, published output, search index, or all three?",
        ),
    ),
    "editor": DomainPlaybook(
        key="editor",
        aliases=("editor", "web editor", "authoring", "xml editor", "save reload"),
        default_entities=("topic", "map", "reference"),
        default_outputs=("editor_preview", "native_pdf", "sites"),
        risk_theme="authoring workflow stability",
        scenarios=(
            ScenarioPattern(
                scenario="{jira_key}: Save, reload, and reopen Web Editor content containing {entity}",
                why="{entity} authoring defects often appear after persistence, reload, or synchronization.",
                layer="UI",
                automation_fit="Partial",
            ),
            ScenarioPattern(
                scenario="{jira_key}: Compare editor preview against {output} for {entity}",
                why="{entity} must not pass authoring preview while failing generated customer output.",
                layer="Hybrid",
                automation_fit="Partial",
            ),
        ),
        clarifications=(
            "Which Web Editor workflow is in scope for {entity} and {output} in {jira_key}?",
            "Should {jira_key} require parity between editor preview and {output} for {entity}?",
        ),
    ),
}


class UACLLMProvider(Protocol):
    """Future provider hook for OpenAI, Azure OpenAI, Bedrock, local models, etc."""

    provider_name: str

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, Any] | None:
        """Return provider-generated JSON-like output, or None on abstain/failure."""


class NullUACLLMProvider:
    """No-op provider used by the deterministic production-safe path."""

    provider_name = "none"

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, Any] | None:
        return None


class UACPromptBuilder:
    """Reusable prompts for optional provider-driven generation and critique."""

    def build_system_prompt(self) -> str:
        return (
            "You generate compact Jira-aware UAC recommendations for AEM Guides QA. "
            "Use only supplied evidence. Do not invent Jira keys, customers, environments, fixes, or historical patterns. "
            "Every scenario must cite a Jira entity, affected output, or similar Jira key. "
            "Reject generic QA phrases unless tied to concrete evidence."
        )

    def build_generation_prompt(
        self,
        *,
        enriched_jira: Mapping[str, Any],
        similar_jiras: Sequence[Mapping[str, Any]],
        retrieval_debug: Mapping[str, Any],
    ) -> str:
        payload = {
            "enriched_jira": enriched_jira,
            "similar_jiras": list(similar_jiras),
            "retrieval_debug": retrieval_debug,
            "required_output_keys": [
                "classification",
                "risk_summary",
                "similar_jiras",
                "must_test_scenarios",
                "missing_clarifications",
                "automation_fit",
                "evidence_summary",
                "confidence",
            ],
        }
        return json.dumps(payload, ensure_ascii=True, default=str)

    def build_critic_prompt(
        self,
        *,
        candidate_output: Mapping[str, Any],
        enriched_jira: Mapping[str, Any],
        similar_jiras: Sequence[Mapping[str, Any]],
    ) -> str:
        payload = {
            "task": "Critique and remove unsupported UAC points. Keep compact JSON.",
            "candidate_output": candidate_output,
            "evidence": {
                "enriched_jira": enriched_jira,
                "similar_jiras": list(similar_jiras),
            },
            "hard_reject_phrases": [p.pattern for p in _GENERIC_REJECT_PATTERNS],
        }
        return json.dumps(payload, ensure_ascii=True, default=str)


@dataclass
class EvidenceContext:
    """Normalized grounding signals used across generation and critic passes."""

    enriched: dict[str, Any]
    similar: list[dict[str, Any]]
    retrieval_debug: dict[str, Any]
    jira_key: str
    domain: str
    sub_domain: str
    issue_type: str
    priority: str
    summary: str
    description: str
    entities: list[str]
    outputs: list[str]
    features: list[str]
    components: list[str]
    customers: list[str]
    labels: list[str]
    symptoms: list[str]
    missing_info: list[str]
    similar_keys: list[str]
    anchors: list[str]


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    model_dump = getattr(obj, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dict(dumped) if isinstance(dumped, dict) else {}
    dict_fn = getattr(obj, "dict", None)
    if callable(dict_fn):
        dumped = dict_fn()
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _json_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if x is not None and str(x).strip()]
    if isinstance(raw, tuple | set):
        return [str(x).strip() for x in raw if x is not None and str(x).strip()]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                loaded = json.loads(s)
                if isinstance(loaded, list):
                    return [str(x).strip() for x in loaded if x is not None and str(x).strip()]
            except (json.JSONDecodeError, TypeError):
                pass
        if "," in s:
            return [x.strip() for x in s.split(",") if x.strip()]
        return [s]
    return [str(raw).strip()] if str(raw).strip() else []


def _norm(text: Any) -> str:
    return _WS_RE.sub(" ", str(text or "").strip())


def _norm_key(text: Any) -> str:
    return _norm(text).lower().replace("-", "_").replace(" ", "_")


def _dedupe(values: Sequence[str], *, max_items: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = _norm(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if max_items is not None and len(out) >= max_items:
            break
    return out


def _tokens(text: str) -> set[str]:
    stop = {
        "aem",
        "the",
        "and",
        "for",
        "with",
        "jira",
        "guides",
        "issue",
        "test",
        "uac",
        "qa",
        "bug",
        "fix",
    }
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) >= 3 and t.lower() not in stop}


def _stringify_evidence(evidence: Any) -> str:
    if isinstance(evidence, str):
        return evidence
    try:
        return json.dumps(evidence, ensure_ascii=True, default=str)
    except TypeError:
        return str(evidence)


def _truncate(text: Any, limit: int) -> str:
    s = _norm(text)
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "..."


def _first(values: Sequence[str], fallback: str) -> str:
    for value in values:
        text = _norm(value)
        if text:
            return text
    return fallback


def _field_list(data: Mapping[str, Any], *names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        values.extend(_json_list(data.get(name)))
    return _dedupe(values)


def _similar_key(row: Mapping[str, Any]) -> str:
    return _norm(row.get("jira_key") or row.get("key") or row.get("issue_key")).upper()


def _score(row: Mapping[str, Any]) -> float:
    for field in ("final_score", "confidence_score", "score", "similarity_score", "vector_score"):
        raw = row.get(field)
        try:
            if raw is not None and raw != "":
                return round(float(raw), 4)
        except (TypeError, ValueError):
            pass
    scores = row.get("scores")
    if isinstance(scores, Mapping):
        for field in ("final", "confidence", "similarity", "vector"):
            try:
                raw = scores.get(field)
                if raw is not None and raw != "":
                    return round(float(raw), 4)
            except (TypeError, ValueError):
                pass
    retrieval = row.get("retrieval")
    if isinstance(retrieval, Mapping):
        for field in ("final_score", "confidence_score", "similarity_score", "vector_score"):
            try:
                raw = retrieval.get(field)
                if raw is not None and raw != "":
                    return round(float(raw), 4)
            except (TypeError, ValueError):
                pass
    return 0.0


def _row_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def _row_blob(row: Mapping[str, Any]) -> str:
    meta = _row_metadata(row)
    parts = [
        _similar_key(row),
        row.get("summary"),
        row.get("title"),
        row.get("document"),
        row.get("description"),
        row.get("matched_snippet"),
        row.get("root_cause_summary"),
        row.get("why_similar"),
        row.get("resolution"),
        meta.get("title"),
        meta.get("enrich_domain"),
        meta.get("enrich_sub_domain"),
        meta.get("enrich_entities"),
        meta.get("enrich_outputs"),
        meta.get("labels"),
        meta.get("components"),
    ]
    return "\n".join(str(x) for x in parts if x)


def _infer_domain(enriched: Mapping[str, Any]) -> str:
    explicit = _norm_key(enriched.get("domain"))
    sub = _norm_key(enriched.get("sub_domain"))
    blob = " ".join(
        [
            explicit,
            sub,
            str(enriched.get("summary") or ""),
            str(enriched.get("description") or ""),
            str(enriched.get("raw_text") or ""),
            " ".join(_field_list(enriched, "affected_outputs", "affected_features", "dita_entities", "labels", "components")),
        ]
    ).lower()
    for key, playbook in DOMAIN_PLAYBOOKS.items():
        if explicit == key or sub == key:
            return key
        for alias in playbook.aliases:
            if re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", blob):
                return key
    if "pdf" in blob:
        return "native_pdf"
    if "publish" in blob:
        return "native_pdf" if "native" in blob else "metadata"
    return explicit if explicit and explicit != "unknown" else "unknown"


def _build_context(
    enriched_jira: Any,
    similar_jiras: Sequence[Any] | None,
    retrieval_debug: Mapping[str, Any] | None,
) -> EvidenceContext:
    enriched = _as_dict(enriched_jira)
    similar = [_as_dict(row) for row in (similar_jiras or [])]
    debug = dict(retrieval_debug or {})

    entities = _field_list(enriched, "dita_entities", "entities", "enrich_entities")
    outputs = _field_list(enriched, "affected_outputs", "outputs", "enrich_outputs")
    features = _field_list(enriched, "affected_features", "features")
    components = _field_list(enriched, "components", "component")
    customers = _field_list(enriched, "customer_names", "customers", "customer_labels", "customer")
    labels = _field_list(enriched, "labels", "customer_labels")
    symptoms = _field_list(enriched, "symptoms", "qa_risk_tags")
    missing_info = _field_list(enriched, "missing_info")
    similar_keys = _dedupe([_similar_key(row) for row in similar if _similar_key(row)])
    jira_key = _norm(enriched.get("jira_key") or enriched.get("key") or enriched.get("issue_key")).upper()
    domain = _infer_domain(enriched)
    playbook = DOMAIN_PLAYBOOKS.get(domain)
    evidence_blob = " ".join(
        [
            str(enriched.get("summary") or ""),
            str(enriched.get("description") or ""),
            str(enriched.get("raw_text") or ""),
            " ".join(labels),
            " ".join(features),
            " ".join(components),
        ]
    ).lower()
    if not entities and playbook:
        for candidate in playbook.default_entities:
            if candidate.lower() in evidence_blob or any(alias.lower() in evidence_blob for alias in playbook.aliases):
                entities = [candidate]
                break

    anchors = _dedupe(
        [
            jira_key,
            *entities,
            *outputs,
            *features,
            *components,
            *customers,
            *labels,
            *similar_keys,
            domain if domain != "unknown" else "",
        ]
    )
    return EvidenceContext(
        enriched=enriched,
        similar=similar,
        retrieval_debug=debug,
        jira_key=jira_key,
        domain=domain,
        sub_domain=_norm(enriched.get("sub_domain")),
        issue_type=_norm(enriched.get("issue_type")),
        priority=_norm(enriched.get("priority")),
        summary=_norm(enriched.get("summary")),
        description=_norm(enriched.get("description")),
        entities=entities,
        outputs=outputs,
        features=features,
        components=components,
        customers=customers,
        labels=labels,
        symptoms=symptoms,
        missing_info=missing_info,
        similar_keys=similar_keys,
        anchors=anchors,
    )


def _text_mentions_anchor(
    text: str,
    ctx: EvidenceContext,
    *,
    allow_similar: bool = True,
    allow_current_jira: bool = False,
) -> bool:
    blob = (text or "").lower()
    for anchor in ctx.entities + ctx.outputs:
        if anchor and anchor.lower() in blob:
            return True
    if allow_similar:
        for key in ctx.similar_keys:
            if key and key.lower() in blob:
                return True
    if allow_current_jira and ctx.jira_key and ctx.jira_key.lower() in blob:
        return True
    return False


def _evidence_mentions_anchor(evidence: Any, ctx: EvidenceContext) -> bool:
    return _text_mentions_anchor(_stringify_evidence(evidence), ctx)


def _generic_reject_reason(text: str, ctx: EvidenceContext, evidence: Any | None = None) -> str:
    blob = _norm(text)
    for pattern in _GENERIC_REJECT_PATTERNS:
        if not pattern.search(blob):
            continue
        if _text_mentions_anchor(blob, ctx) or _evidence_mentions_anchor(evidence, ctx):
            return ""
        return f"generic_phrase_without_specific_evidence:{pattern.pattern}"
    return ""


def _grounded_point(text: str, ctx: EvidenceContext, evidence: Any | None = None) -> bool:
    return _text_mentions_anchor(text, ctx) or _evidence_mentions_anchor(evidence, ctx)


def _playbook(ctx: EvidenceContext) -> DomainPlaybook | None:
    return DOMAIN_PLAYBOOKS.get(ctx.domain)


def _primary_entity(ctx: EvidenceContext) -> str:
    playbook = _playbook(ctx)
    defaults = list(playbook.default_entities) if playbook else []
    return _first(ctx.entities + defaults + ctx.features + ctx.components, ctx.jira_key or "ticket_scope")


def _primary_output(ctx: EvidenceContext) -> str:
    playbook = _playbook(ctx)
    defaults = list(playbook.default_outputs) if playbook else []
    return _first(ctx.outputs + defaults, "output_not_specified")


def _layer_for(ctx: EvidenceContext, preferred: str, output: str, entity: str) -> str:
    pref = _norm(preferred)
    if pref in {"UI", "API", "Publishing", "Manual", "Hybrid"}:
        return pref
    blob = " ".join([ctx.domain, output, entity, ctx.summary, ctx.description]).lower()
    if any(x in blob for x in ("native_pdf", "pdf", "publish", "dita-ot", "sites", "html5")):
        return "Publishing"
    if any(x in blob for x in ("api", "rest", "json", "endpoint")):
        return "API"
    if any(x in blob for x in ("web editor", "editor", "ui", "authoring")):
        return "UI"
    return "Manual"


def _priority_for_test_layer(test_layer: str) -> str:
    tl = (test_layer or "").lower()
    if "publish" in tl:
        return "P1"
    if "ui" in tl or "manual" in tl:
        return "P3"
    return "P2"


def _automation_fit_label(text: str, layer: str) -> tuple[str, dict[str, Any]]:
    try:
        from app.services.jira_qa_automation_rubric import rubric_to_dict, score_automation_fit

        rubric = score_automation_fit(text)
        payload = rubric_to_dict(rubric)
        return str(payload.get("automation_fit") or rubric.fit_label), payload
    except Exception:  # pragma: no cover - fallback for standalone scripts
        t = (text or "").lower()
        score = 4.5
        if any(x in t for x in ("expected", "should", "must", "publish", "api", "json", "ditaval")):
            score += 1.5
        if layer in {"API", "Publishing", "Hybrid"}:
            score += 1.0
        if any(x in t for x in ("intermittent", "random", "manual only", "sso")):
            score -= 1.5
        score = max(0.0, min(10.0, score))
        label = "Yes" if score >= 6.5 else "Partial" if score >= 3.5 else "No"
        return label, {"automation_fit": label, "score_0_10": round(score, 2)}


def _evidence_item(source: str, *, field: str, value: Any, jira_key: str = "") -> dict[str, str]:
    return {
        "source": source,
        "jira_key": jira_key,
        "field": field,
        "value": _truncate(value, 220),
    }


def _normalize_similar_jiras(ctx: EvidenceContext) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    current_tokens = _tokens(
        " ".join(
            [
                ctx.domain,
                ctx.summary,
                ctx.description,
                " ".join(ctx.entities),
                " ".join(ctx.outputs),
                " ".join(ctx.components),
                " ".join(ctx.labels),
            ]
        )
    )
    seen: set[str] = set()
    accepted: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []

    for row in ctx.similar:
        key = _similar_key(row)
        if not key:
            dropped.append({"candidate": "<missing-key>", "reason": "missing_jira_key"})
            logger.debug("uac.similar.rejected", extra={"candidate": "<missing-key>", "reason": "missing_jira_key"})
            continue
        if key in seen:
            dropped.append({"candidate": key, "reason": "duplicate_jira_key"})
            logger.debug("uac.similar.rejected", extra={"candidate": key, "reason": "duplicate_jira_key"})
            continue
        if ctx.jira_key and key == ctx.jira_key:
            dropped.append({"candidate": key, "reason": "same_as_current_jira"})
            logger.debug("uac.similar.rejected", extra={"candidate": key, "reason": "same_as_current_jira"})
            continue

        meta = _row_metadata(row)
        row_entities = _dedupe(
            _json_list(row.get("matching_entities"))
            + _json_list(row.get("dita_entities"))
            + _json_list(meta.get("enrich_entities"))
        )
        row_outputs = _dedupe(
            _json_list(row.get("matching_outputs"))
            + _json_list(row.get("affected_outputs"))
            + _json_list(meta.get("enrich_outputs"))
        )
        overlap_entities = [x for x in ctx.entities if x.lower() in {e.lower() for e in row_entities}]
        overlap_outputs = [x for x in ctx.outputs if x.lower() in {o.lower() for o in row_outputs}]
        blob = _row_blob(row)
        lexical_overlap = current_tokens & _tokens(blob)
        score = _score(row)

        weak = not (overlap_entities or overlap_outputs or lexical_overlap or score >= 0.58)
        if weak:
            dropped.append({"candidate": key, "reason": "weak_evidence_no_entity_output_or_score_overlap"})
            logger.debug(
                "uac.similar.rejected",
                extra={
                    "candidate": key,
                    "reason": "weak_evidence_no_entity_output_or_score_overlap",
                    "score": score,
                },
            )
            continue

        why_bits: list[str] = []
        if overlap_entities:
            why_bits.append("shared entity " + ", ".join(overlap_entities[:3]))
        if overlap_outputs:
            why_bits.append("shared output " + ", ".join(overlap_outputs[:3]))
        if not why_bits and lexical_overlap:
            why_bits.append("shared evidence terms " + ", ".join(sorted(lexical_overlap)[:3]))
        if not why_bits:
            why_bits.append("retrieval score above weak-evidence threshold")

        accepted_row = {
            "jira_key": key,
            "summary": _truncate(row.get("summary") or row.get("title") or meta.get("title") or "", 180),
            "score": score,
            "why_relevant": _truncate(f"{key}: " + "; ".join(why_bits), 260),
            "matching_entities": overlap_entities or row_entities[:3],
            "matching_outputs": overlap_outputs or row_outputs[:3],
            "evidence": [
                _evidence_item(
                    "similar_jira",
                    jira_key=key,
                    field="matched_snippet",
                    value=row.get("matched_snippet") or row.get("why_similar") or row.get("document") or "",
                )
            ],
        }
        accepted.append(accepted_row)
        seen.add(key)
        logger.debug(
            "uac.similar.selected",
            extra={
                "candidate": key,
                "score": score,
                "overlap_entities": overlap_entities,
                "overlap_outputs": overlap_outputs,
                "lexical_overlap": sorted(lexical_overlap)[:8],
            },
        )
        if len(accepted) >= 5:
            break

    return accepted, dropped


def _classification(ctx: EvidenceContext) -> dict[str, Any]:
    return {
        "jira_key": ctx.jira_key,
        "issue_type": ctx.issue_type,
        "domain": ctx.domain,
        "sub_domain": ctx.sub_domain,
        "priority": ctx.priority,
        "customer_names": ctx.customers[:5],
        "affected_outputs": ctx.outputs[:6],
        "dita_entities": ctx.entities[:8],
        "components": ctx.components[:6],
    }


def _risk_summary(ctx: EvidenceContext, similar_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not (ctx.entities or ctx.outputs or similar_rows):
        return {"level": "insufficient", "message": INSUFFICIENT_EVIDENCE_MESSAGE, "drivers": []}

    entity = _primary_entity(ctx)
    output = _primary_output(ctx)
    playbook = _playbook(ctx)
    drivers: list[str] = []

    if ctx.jira_key and (ctx.entities or ctx.outputs):
        drivers.append(
            _truncate(
                f"{ctx.jira_key}: {entity} in {output} needs UAC coverage because Jira evidence classifies it as {ctx.domain}.",
                260,
            )
        )
    if playbook:
        drivers.append(
            _truncate(
                f"{ctx.jira_key or entity}: {playbook.risk_theme} is the domain risk for {entity} and {output}.",
                260,
            )
        )
    if similar_rows:
        keys = ", ".join(str(row.get("jira_key")) for row in similar_rows[:3])
        drivers.append(_truncate(f"{keys}: historical Jira evidence increases regression risk for {entity} in {output}.", 260))
    if ctx.customers and output != "output_not_specified":
        drivers.append(
            _truncate(
                f"{ctx.customers[0]} customer metadata on {ctx.jira_key or 'current Jira'} makes {output} acceptance customer-sensitive.",
                260,
            )
        )
    for missing in ctx.missing_info[:2]:
        drivers.append(
            _truncate(
                f"{ctx.jira_key or entity}: missing clarification '{missing}' affects acceptance for {entity} in {output}.",
                260,
            )
        )

    risk_points = _dedupe(drivers, max_items=5)
    score = len(ctx.entities) + len(ctx.outputs) + len(similar_rows) + (2 if ctx.customers else 0)
    level = "high" if score >= 6 else "medium" if score >= 3 else "low"
    return {"level": level, "drivers": risk_points}


def _scenario_from_pattern(
    ctx: EvidenceContext,
    pattern: ScenarioPattern,
    *,
    entity: str,
    output: str,
    similar_key: str = "",
) -> dict[str, Any]:
    jira_key = ctx.jira_key or similar_key or "current_jira"
    scenario = pattern.scenario.format(jira_key=jira_key, entity=entity, output=output, similar_key=similar_key)
    why = pattern.why.format(jira_key=jira_key, entity=entity, output=output, similar_key=similar_key)
    layer = _layer_for(ctx, pattern.layer, output, entity)
    evidence = [
        _evidence_item("current_jira", jira_key=ctx.jira_key, field="domain", value=ctx.domain),
        _evidence_item("current_jira", jira_key=ctx.jira_key, field="entity", value=entity),
        _evidence_item("current_jira", jira_key=ctx.jira_key, field="affected_output", value=output),
    ]
    if similar_key:
        evidence.append(_evidence_item("similar_jira", jira_key=similar_key, field="jira_key", value=similar_key))
    return {
        "scenario": _truncate(scenario, 220),
        "why": _truncate(why, 260),
        "evidence": evidence,
        "impacted_output": output,
        "related_entity": entity,
        "test_layer": layer,
        "priority": _priority_for_test_layer(layer),
        "automation_fit": pattern.automation_fit,
    }


def _must_test_scenarios(ctx: EvidenceContext, similar_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not (ctx.entities or ctx.outputs or similar_rows):
        return []

    entity = _primary_entity(ctx)
    output = _primary_output(ctx)
    playbook = _playbook(ctx)
    candidates: list[dict[str, Any]] = []

    if similar_rows:
        sim_key = str(similar_rows[0].get("jira_key") or "")
        pattern = ScenarioPattern(
            scenario="{jira_key}: Regression parity for {entity} in {output} against {similar_key}",
            why="{similar_key} is grounded similar Jira evidence; compare {entity}/{output} behavior before UAC sign-off.",
            layer="Hybrid",
            automation_fit="Partial",
        )
        candidates.append(_scenario_from_pattern(ctx, pattern, entity=entity, output=output, similar_key=sim_key))

    if playbook:
        for pattern in playbook.scenarios:
            candidates.append(_scenario_from_pattern(ctx, pattern, entity=entity, output=output))
    else:
        candidates.append(
            _scenario_from_pattern(
                ctx,
                ScenarioPattern(
                    scenario="{jira_key}: Exercise {entity} through {output} using ticket reproduction data",
                    why="{entity} and {output} are the grounded Jira acceptance anchors for this UAC pass.",
                    layer="Manual",
                    automation_fit="Partial",
                ),
                entity=entity,
                output=output,
            )
        )

    if ctx.entities and ctx.outputs and len(ctx.entities) > 1:
        second_entity = ctx.entities[1]
        candidates.append(
            _scenario_from_pattern(
                ctx,
                ScenarioPattern(
                    scenario="{jira_key}: Cross-check {entity} with primary output {output}",
                    why="{entity} appears in Jira evidence and can interact with the primary affected output {output}.",
                    layer="Hybrid",
                    automation_fit="Partial",
                ),
                entity=second_entity,
                output=output,
            )
        )

    if ctx.customers and ctx.outputs:
        customer = ctx.customers[0]
        tl = _layer_for(ctx, "Manual", output, entity)
        candidates.append(
            {
                "scenario": _truncate(f"{ctx.jira_key}: Customer profile {customer} preserves {entity} in {output}", 220),
                "why": _truncate(
                    f"{customer} is present in Jira customer metadata; UAC should cover customer-sensitive {output} behavior for {entity}.",
                    260,
                ),
                "evidence": [
                    _evidence_item("current_jira", jira_key=ctx.jira_key, field="customer_names", value=customer),
                    _evidence_item("current_jira", jira_key=ctx.jira_key, field="affected_output", value=output),
                    _evidence_item("current_jira", jira_key=ctx.jira_key, field="entity", value=entity),
                ],
                "impacted_output": output,
                "related_entity": entity,
                "test_layer": tl,
                "priority": _priority_for_test_layer(tl),
                "automation_fit": "Partial",
            }
        )

    return candidates


def _missing_clarifications(ctx: EvidenceContext, similar_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not (ctx.entities or ctx.outputs or ctx.jira_key or similar_rows):
        return []
    entity = _primary_entity(ctx)
    output = _primary_output(ctx)
    playbook = _playbook(ctx)
    rows: list[dict[str, Any]] = []

    for missing in ctx.missing_info[:3]:
        question = f"For {ctx.jira_key or entity}, clarify '{missing}' because it changes {entity} acceptance in {output}."
        rows.append(
            {
                "question": _truncate(question, 240),
                "why": _truncate(f"{entity} and {output} cannot be signed off without this Jira-specific acceptance detail.", 240),
                "evidence": [_evidence_item("current_jira", jira_key=ctx.jira_key, field="missing_info", value=missing)],
                "related_entity": entity,
            }
        )

    if playbook:
        for template in playbook.clarifications:
            q = template.format(jira_key=ctx.jira_key or "current_jira", entity=entity, output=output)
            rows.append(
                {
                    "question": _truncate(q, 240),
                    "why": _truncate(f"{ctx.domain} UAC depends on explicit behavior for {entity} in {output}.", 240),
                    "evidence": [
                        _evidence_item("current_jira", jira_key=ctx.jira_key, field="domain", value=ctx.domain),
                        _evidence_item("current_jira", jira_key=ctx.jira_key, field="entity", value=entity),
                        _evidence_item("current_jira", jira_key=ctx.jira_key, field="affected_output", value=output),
                    ],
                    "related_entity": entity,
                }
            )

    if similar_rows:
        sim_key = str(similar_rows[0].get("jira_key") or "")
        rows.append(
            {
                "question": _truncate(
                    f"Should {ctx.jira_key or 'current Jira'} match the {entity}/{output} behavior proven by {sim_key}?",
                    240,
                ),
                "why": _truncate(f"{sim_key} is similar historical Jira evidence for the same UAC area.", 240),
                "evidence": [_evidence_item("similar_jira", jira_key=sim_key, field="jira_key", value=sim_key)],
                "related_entity": entity,
            }
        )

    return rows


def _automation_fit(ctx: EvidenceContext, scenarios: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entity = _primary_entity(ctx)
    output = _primary_output(ctx)
    blob = "\n".join(
        [
            ctx.summary,
            ctx.description,
            " ".join(ctx.symptoms),
            " ".join(ctx.entities),
            " ".join(ctx.outputs),
            " ".join(str(sc.get("scenario") or "") for sc in scenarios),
        ]
    )
    layer = _layer_for(ctx, "", output, entity)
    label, rubric = _automation_fit_label(blob, layer)
    return {
        "recommended": label in {"Yes", "Partial"},
        "fit": label,
        "score": rubric.get("score_0_10", rubric.get("score", 0.0)),
        "framework": "Python Behave + Playwright/Selenium + AEM Guides fixtures",
        "primary_test_layer": layer,
        "dependencies": _dedupe(
            [
                f"Fixture content with {entity} for {output}",
                f"Stable AEM Guides environment for {ctx.jira_key or entity}",
                f"Golden output artifact for {output}" if output != "output_not_specified" else "",
            ],
            max_items=4,
        ),
        "rubric": rubric,
    }


def _evidence_summary(
    ctx: EvidenceContext,
    similar_rows: Sequence[Mapping[str, Any]],
    dropped: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    retrieval = {
        "fallback_used": bool(
            ctx.retrieval_debug.get("fallback_used")
            or ctx.retrieval_debug.get("semantic_fallback_used")
            or ctx.retrieval_debug.get("metadata_incomplete")
        ),
        "candidate_count": ctx.retrieval_debug.get("candidate_count", len(ctx.similar)),
        "accepted_count": len(similar_rows),
        "rejected_count": len(dropped),
    }
    trace = []
    for entity in ctx.entities[:4]:
        trace.append(_evidence_item("current_jira", jira_key=ctx.jira_key, field="dita_entities", value=entity))
    for output in ctx.outputs[:4]:
        trace.append(_evidence_item("current_jira", jira_key=ctx.jira_key, field="affected_outputs", value=output))
    for row in similar_rows[:4]:
        trace.append(
            _evidence_item(
                "similar_jira",
                jira_key=str(row.get("jira_key") or ""),
                field="why_relevant",
                value=row.get("why_relevant") or "",
            )
        )
    return {
        "current_jira": ctx.jira_key,
        "domain": ctx.domain,
        "anchors": {
            "entities": ctx.entities[:8],
            "outputs": ctx.outputs[:8],
            "customers": ctx.customers[:5],
            "similar_jiras": [str(row.get("jira_key") or "") for row in similar_rows],
        },
        "retrieval": retrieval,
        "trace": trace,
        "critic": {"dropped": list(dropped)[:20]},
    }


def _confidence(ctx: EvidenceContext, similar_rows: Sequence[Mapping[str, Any]], dropped: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    score = 0.15 if ctx.jira_key else 0.0
    signals: list[str] = []
    if ctx.jira_key:
        signals.append("current_jira_key")
    if ctx.entities:
        score += 0.18
        signals.append("entity_evidence")
    if ctx.outputs:
        score += 0.18
        signals.append("output_evidence")
    if ctx.domain != "unknown":
        score += 0.14
        signals.append("domain_classification")
    if ctx.customers:
        score += 0.08
        signals.append("customer_metadata")
    if similar_rows:
        score += min(0.2, 0.08 + (0.04 * min(len(similar_rows), 3)))
        signals.append("similar_historical_jira")
    if ctx.retrieval_debug.get("fallback_used") or ctx.retrieval_debug.get("semantic_fallback_used"):
        score -= 0.08
        signals.append("semantic_fallback_used")
    if dropped and len(dropped) > len(similar_rows) + 3:
        score -= 0.08
        signals.append("critic_rejected_weak_evidence")
    if not (ctx.entities or ctx.outputs or similar_rows):
        score = 0.0
        signals.append("insufficient_evidence")
    score = round(max(0.0, min(1.0, score)), 3)
    level = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    return {"score": score, "level": level, "signals": signals}


def _dedupe_records(rows: Sequence[Mapping[str, Any]], *, key_fields: Sequence[str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = " ".join(_norm(row.get(field)).lower() for field in key_fields)
        key = re.sub(r"\s+", " ", key).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(dict(row))
    return out


def _critic_pass(output: dict[str, Any], ctx: EvidenceContext, prior_dropped: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    dropped: list[dict[str, str]] = [dict(x) for x in prior_dropped]

    # Similar Jira rows are already normalized, but dedupe again after optional LLM merge.
    similar_rows = _dedupe_records(output.get("similar_jiras") or [], key_fields=("jira_key",))
    output["similar_jiras"] = similar_rows[:5]

    risk = output.get("risk_summary") if isinstance(output.get("risk_summary"), dict) else {}
    drivers: list[str] = []
    for driver in _json_list(risk.get("drivers")):
        reason = _generic_reject_reason(driver, ctx)
        if reason or not _grounded_point(driver, ctx):
            dropped.append({"candidate": _truncate(driver, 140), "reason": reason or "ungrounded_risk_point"})
            logger.debug("uac.risk.rejected", extra={"candidate": driver, "reason": reason or "ungrounded_risk_point"})
            continue
        drivers.append(driver)
    risk["drivers"] = _dedupe(drivers, max_items=5)
    if not risk.get("drivers") and not ctx.anchors:
        risk = {"level": "insufficient", "message": INSUFFICIENT_EVIDENCE_MESSAGE, "drivers": []}
    output["risk_summary"] = risk

    scenarios: list[dict[str, Any]] = []
    for row in output.get("must_test_scenarios") or []:
        if not isinstance(row, Mapping):
            continue
        sc = dict(row)
        if "priority" not in sc or not str(sc.get("priority") or "").strip():
            sc["priority"] = _priority_for_test_layer(str(sc.get("test_layer") or ""))
        text = " ".join(
            [
                str(sc.get("scenario") or ""),
                str(sc.get("why") or ""),
                str(sc.get("impacted_output") or ""),
                str(sc.get("related_entity") or ""),
                _stringify_evidence(sc.get("evidence")),
            ]
        )
        missing_fields = [
            field
            for field in ("scenario", "why", "evidence", "impacted_output", "related_entity", "test_layer", "automation_fit")
            if field not in sc
        ]
        reason = _generic_reject_reason(str(sc.get("scenario") or ""), ctx) or _generic_reject_reason(
            text, ctx, sc.get("evidence")
        )
        if missing_fields:
            dropped.append({"candidate": _truncate(text, 140), "reason": "missing_scenario_fields:" + ",".join(missing_fields)})
            logger.debug("uac.scenario.rejected", extra={"candidate": text, "reason": "missing_fields", "fields": missing_fields})
            continue
        if reason or not _grounded_point(text, ctx, sc.get("evidence")):
            dropped.append({"candidate": _truncate(text, 140), "reason": reason or "ungrounded_scenario"})
            logger.debug("uac.scenario.rejected", extra={"candidate": text, "reason": reason or "ungrounded_scenario"})
            continue
        sc["scenario"] = _truncate(sc["scenario"], 220)
        sc["why"] = _truncate(sc["why"], 260)
        sc["impacted_output"] = _truncate(sc["impacted_output"], 80)
        sc["related_entity"] = _truncate(sc["related_entity"], 80)
        sc["test_layer"] = _truncate(sc["test_layer"], 40)
        sc["automation_fit"] = _truncate(sc["automation_fit"], 40)
        scenarios.append(sc)
        logger.debug(
            "uac.scenario.selected",
            extra={
                "scenario": sc["scenario"],
                "entity": sc["related_entity"],
                "output": sc["impacted_output"],
                "layer": sc["test_layer"],
            },
        )
    output["must_test_scenarios"] = _dedupe_records(scenarios, key_fields=("scenario", "related_entity", "impacted_output"))[:7]

    clarifications: list[dict[str, Any]] = []
    for row in output.get("missing_clarifications") or []:
        if not isinstance(row, Mapping):
            continue
        q = dict(row)
        text = " ".join([str(q.get("question") or ""), str(q.get("why") or ""), _stringify_evidence(q.get("evidence"))])
        reason = _generic_reject_reason(text, ctx, q.get("evidence"))
        if reason or not _grounded_point(text, ctx, q.get("evidence")):
            dropped.append({"candidate": _truncate(text, 140), "reason": reason or "ungrounded_clarification"})
            logger.debug("uac.clarification.rejected", extra={"candidate": text, "reason": reason or "ungrounded_clarification"})
            continue
        q["question"] = _truncate(q.get("question"), 240)
        q["why"] = _truncate(q.get("why"), 240)
        q["related_entity"] = _truncate(q.get("related_entity") or _primary_entity(ctx), 80)
        clarifications.append(q)
    output["missing_clarifications"] = _dedupe_records(clarifications, key_fields=("question", "related_entity"))[:5]

    output["evidence_summary"] = _evidence_summary(ctx, output["similar_jiras"], dropped)
    output["confidence"] = _confidence(ctx, output["similar_jiras"], dropped)
    return output


class UACGenerationEngine:
    """Production-safe UAC generator with optional LLM provider extension point."""

    def __init__(
        self,
        *,
        llm_provider: UACLLMProvider | None = None,
        prompt_builder: UACPromptBuilder | None = None,
    ) -> None:
        self.llm_provider = llm_provider or NullUACLLMProvider()
        self.prompt_builder = prompt_builder or UACPromptBuilder()

    def generate(
        self,
        *,
        enriched_jira: Any,
        similar_jiras: Sequence[Any] | None = None,
        retrieval_debug: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = _build_context(enriched_jira, similar_jiras, retrieval_debug)
        similar_rows, dropped = _normalize_similar_jiras(ctx)
        insufficient_current_anchors = not (ctx.entities or ctx.outputs) and ctx.domain == "unknown"
        if insufficient_current_anchors:
            if similar_rows:
                dropped.append(
                    {
                        "candidate": ",".join(str(row.get("jira_key") or "") for row in similar_rows[:5]),
                        "reason": "ignored_similar_jiras_because_current_jira_has_unknown_domain_and_no_entity_or_output",
                    }
                )
            similar_rows = []
        scenarios = _must_test_scenarios(ctx, similar_rows)
        output = {
            "classification": _classification(ctx),
            "risk_summary": _risk_summary(ctx, similar_rows),
            "similar_jiras": similar_rows,
            "must_test_scenarios": scenarios,
            "missing_clarifications": _missing_clarifications(ctx, similar_rows),
            "automation_fit": _automation_fit(ctx, scenarios),
            "evidence_summary": {},
            "confidence": {},
        }

        provider_output = self._provider_candidate(ctx, output)
        if provider_output:
            output = self._merge_provider_output(output, provider_output)

        if insufficient_current_anchors or not (ctx.entities or ctx.outputs or similar_rows):
            output["risk_summary"] = {"level": "insufficient", "message": INSUFFICIENT_EVIDENCE_MESSAGE, "drivers": []}
            output["similar_jiras"] = []
            output["must_test_scenarios"] = []
            output["missing_clarifications"] = []

        insufficient_out = insufficient_current_anchors or not (ctx.entities or ctx.outputs or similar_rows)
        result = _critic_pass(output, ctx, dropped)
        if insufficient_out:
            result["output_parity"] = {"parity_required": False, "parity_pairs": [], "validation_points": []}
        else:
            from services.uac.uac_output_parity import build_output_parity

            result["output_parity"] = build_output_parity(ctx, similar_rows=result.get("similar_jiras") or [])
        return result

    def _provider_candidate(self, ctx: EvidenceContext, draft: Mapping[str, Any]) -> Mapping[str, Any] | None:
        if isinstance(self.llm_provider, NullUACLLMProvider):
            return None
        try:
            system_prompt = self.prompt_builder.build_system_prompt()
            user_prompt = self.prompt_builder.build_generation_prompt(
                enriched_jira=ctx.enriched,
                similar_jiras=ctx.similar,
                retrieval_debug=ctx.retrieval_debug,
            )
            candidate = self.llm_provider.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_name="aem_guides_uac_recommendations_v1",
            )
            if not isinstance(candidate, Mapping):
                return None
            self.prompt_builder.build_critic_prompt(
                candidate_output=candidate,
                enriched_jira=ctx.enriched,
                similar_jiras=ctx.similar,
            )
            return candidate
        except Exception as exc:  # pragma: no cover - provider hook only
            logger.warning(
                "uac.provider.failed",
                extra={"provider": getattr(self.llm_provider, "provider_name", "unknown"), "error": str(exc)},
            )
            return None

    def _merge_provider_output(
        self,
        deterministic_output: Mapping[str, Any],
        provider_output: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Merge only known compact fields; the critic pass remains authoritative."""

        merged = dict(deterministic_output)
        for field in (
            "risk_summary",
            "similar_jiras",
            "must_test_scenarios",
            "missing_clarifications",
            "automation_fit",
        ):
            value = provider_output.get(field)
            if value:
                merged[field] = value
        return merged


def generate_uac_recommendations(
    enriched_jira: Any,
    similar_jiras: Sequence[Any] | None = None,
    retrieval_debug: Mapping[str, Any] | None = None,
    *,
    llm_provider: UACLLMProvider | None = None,
) -> dict[str, Any]:
    """Return compact structured UAC recommendations grounded in Jira evidence."""

    return UACGenerationEngine(llm_provider=llm_provider).generate(
        enriched_jira=enriched_jira,
        similar_jiras=similar_jiras,
        retrieval_debug=retrieval_debug,
    )


__all__ = [
    "DOMAIN_PLAYBOOKS",
    "INSUFFICIENT_EVIDENCE_MESSAGE",
    "NullUACLLMProvider",
    "UACGenerationEngine",
    "UACLLMProvider",
    "UACPromptBuilder",
    "generate_uac_recommendations",
]
