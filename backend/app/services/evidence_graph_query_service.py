"""Bounded, provenance-preserving queries over the active evidence graph."""

from __future__ import annotations

from collections import OrderedDict, defaultdict
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
from threading import Lock
import time
from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.evidence_graph_models import (
    EvidenceGraphAssertion,
    EvidenceGraphEdge,
    EvidenceGraphGeneration,
    EvidenceGraphNode,
)
from app.db.session import SessionLocal
from app.services.evidence_graph_contract import (
    MECHANISM_NODE_TYPES,
    NODE_PROPERTY_ALLOWLIST,
    RELATIONS,
    TRUST_WEIGHTS,
    canonical_url,
    deterministic_id,
    extract_api_routes,
    extract_config_keys,
    extract_error_signatures,
    normalize_text,
    normalized_token,
    stable_digest,
    stable_key,
)
from app.services.evidence_graph_store import active_generation, graph_status
from app.services.jira_component_metadata_service import canonical_component_name


APPROVED_TRAVERSAL_RELATIONS = frozenset(RELATIONS)
DITA_CONSTRAINT_RELATIONS = frozenset({"ALLOWS_CHILD", "HAS_ATTRIBUTE", "SPECIALIZES", "CONSTRAINS"})
RELEASE_RELATIONS = frozenset({"AFFECTS_VERSION", "FIXED_IN_RELEASE", "APPLIES_TO_RELEASE"})
AREA_ONLY_NODE_TYPES = frozenset({"customer", "component", "domain", "subdomain", "feature", "workflow"})
STRONG_MECHANISM_TYPES = frozenset(
    {"root_cause", "behavior_claim", "error_signature", "api_route", "config_key"}
)
COMBINATION_SIGNAL_RELATIONS = frozenset(
    {"HAS_ACTUAL_BEHAVIOR", "MENTIONS_DITA_ENTITY", "AFFECTS_OUTPUT"}
)
SAFE_NODE_PROPERTIES = NODE_PROPERTY_ALLOWLIST
RELATION_WEIGHTS = {
    "HAS_ROOT_CAUSE": 1.0,
    "HAS_EXPECTED_BEHAVIOR": 0.98,
    "HAS_ERROR_SIGNATURE": 0.96,
    "USES_API_ROUTE": 0.94,
    "USES_CONFIG_KEY": 0.92,
    "HAS_ACTUAL_BEHAVIOR": 0.86,
    "HAS_QA_ORACLE": 0.84,
    "CONSTRAINS": 0.9,
    "SPECIALIZES": 0.9,
    "HAS_ATTRIBUTE": 0.86,
    "ALLOWS_CHILD": 0.84,
    "FIXED_IN_RELEASE": 0.82,
    "AFFECTS_VERSION": 0.78,
    "APPLIES_TO_RELEASE": 0.76,
    "AFFECTS_OUTPUT": 0.65,
    "MENTIONS_DITA_ENTITY": 0.64,
    "IN_COMPONENT": 0.28,
    "IN_DOMAIN": 0.18,
    "REPORTED_BY": 0.18,
}

_QUERY_CACHE: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_STATUS_CACHE: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_QUERY_CACHE_LOCK = Lock()
_INFLUENCE_MODES = {"interactive", "off", "shadow", "augment"}


def clear_evidence_graph_query_cache() -> None:
    with _QUERY_CACHE_LOCK:
        _QUERY_CACHE.clear()
        _STATUS_CACHE.clear()


def _graph_status_cached(session: Session) -> dict[str, Any]:
    ttl = _clamp(
        os.getenv("EVIDENCE_GRAPH_STATUS_CACHE_TTL_SECONDS"),
        default=5,
        minimum=0,
        maximum=60,
    )
    if ttl <= 0:
        return graph_status(session)
    bind = session.get_bind()
    key = f"{id(bind)}:{getattr(bind, 'url', '')}:{os.getenv('EVIDENCE_GRAPH_ENABLED', 'false')}"
    now = time.monotonic()
    with _QUERY_CACHE_LOCK:
        cached = _STATUS_CACHE.get(key)
        if cached is not None and now - cached[0] <= ttl:
            _STATUS_CACHE.move_to_end(key)
            return copy.deepcopy(cached[1])
        _STATUS_CACHE.pop(key, None)
    value = graph_status(session)
    with _QUERY_CACHE_LOCK:
        _STATUS_CACHE[key] = (now, copy.deepcopy(value))
        _STATUS_CACHE.move_to_end(key)
        while len(_STATUS_CACHE) > 16:
            _STATUS_CACHE.popitem(last=False)
    return value


def _cache_settings() -> tuple[int, int]:
    ttl = _clamp(
        os.getenv("EVIDENCE_GRAPH_QUERY_CACHE_TTL_SECONDS"),
        default=60,
        minimum=0,
        maximum=3600,
    )
    maximum = _clamp(
        os.getenv("EVIDENCE_GRAPH_QUERY_CACHE_MAX_ENTRIES"),
        default=256,
        minimum=0,
        maximum=5000,
    )
    return ttl, maximum


def _cache_key(
    generation_id: str,
    *,
    query: str,
    selectors: dict[str, Any],
    tenant_id: str,
    allow_cross_customer_details: bool,
    max_depth: int,
    top_k: int,
    max_paths: int,
) -> str:
    return stable_digest(
        "evidence-graph-query-v2",
        generation_id,
        tenant_id,
        allow_cross_customer_details,
        max_depth,
        top_k,
        max_paths,
        query,
        repr(sorted(selectors.items())),
        length=64,
    )


def _cache_get(key: str) -> dict[str, Any] | None:
    ttl, maximum = _cache_settings()
    if not key or ttl <= 0 or maximum <= 0:
        return None
    now = time.monotonic()
    with _QUERY_CACHE_LOCK:
        item = _QUERY_CACHE.get(key)
        if item is None:
            return None
        created_at, value = item
        if now - created_at > ttl:
            _QUERY_CACHE.pop(key, None)
            return None
        _QUERY_CACHE.move_to_end(key)
        return copy.deepcopy(value)


def _cache_put(key: str, value: dict[str, Any]) -> None:
    ttl, maximum = _cache_settings()
    if not key or ttl <= 0 or maximum <= 0:
        return
    with _QUERY_CACHE_LOCK:
        _QUERY_CACHE[key] = (time.monotonic(), copy.deepcopy(value))
        _QUERY_CACHE.move_to_end(key)
        while len(_QUERY_CACHE) > maximum:
            _QUERY_CACHE.popitem(last=False)


@dataclass(frozen=True)
class Seed:
    node_id: str
    stable_key: str
    score: float
    source: str


@dataclass(frozen=True)
class TraversedPath:
    seed: Seed
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]


def _clamp(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _authorized_edge_ids(session: Session, generation_id: str, tenant_id: str):
    return session.query(EvidenceGraphAssertion.edge_id).filter(
        EvidenceGraphAssertion.generation_id == generation_id,
        EvidenceGraphAssertion.edge_id.isnot(None),
        EvidenceGraphAssertion.active.is_(True),
        or_(
            EvidenceGraphAssertion.tenant_id.is_(None),
            EvidenceGraphAssertion.tenant_id == tenant_id,
        ),
    )


def _canonical_output(value: str) -> str:
    token = normalized_token(value)
    aliases = {
        "pdf": "PDF",
        "pdf2": "DITA-OT PDF2",
        "native-pdf": "Native PDF",
        "html": "HTML",
        "html5": "HTML5",
        "aem-sites": "AEM Sites",
        "experience-manager-sites": "AEM Sites",
        "dita-ot": "DITA-OT",
    }
    return aliases.get(token, normalize_text(value))


def _semantic_seed_keys(
    query: str,
    *,
    jira_key: str,
    customer: str,
    component: str,
    outputs: list[str],
    dita_entities: list[str],
    top_k: int,
) -> tuple[dict[str, tuple[float, str]], list[str]]:
    seed_keys: dict[str, tuple[float, str]] = {}
    warnings: list[str] = []

    def add(key: str, score: float, source: str) -> None:
        if not key:
            return
        current = seed_keys.get(key)
        bounded = max(0.0, min(float(score), 1.0))
        if current is None or bounded > current[0]:
            seed_keys[key] = (bounded, source)

    if jira_key:
        add(stable_key("jira_issue", jira_key), 1.0, "selector:jira")
    if customer:
        add(stable_key("customer", customer), 0.92, "selector:customer")
    if component:
        add(stable_key("component", component), 0.92, "selector:component")
    for output in outputs:
        add(stable_key("output", _canonical_output(output)), 0.9, "selector:output")
    for entity in dita_entities:
        value = normalize_text(entity)
        if not value:
            continue
        node_type = "dita_attribute" if value.startswith("@") else "dita_element"
        add(stable_key(node_type, value.lstrip("@").strip("<>")), 0.92, "selector:dita")
    for route in extract_api_routes(query):
        add(stable_key("api_route", route), 0.98, "query:api_route")
    for signature in extract_error_signatures(query):
        add(stable_key("error_signature", signature), 0.98, "query:error_signature")
    for config_key in extract_config_keys(query):
        add(stable_key("config_key", config_key), 0.95, "query:config_key")

    try:
        from app.services.jira_qa_retrieval_service import semantic_search_jira_qa

        hits = semantic_search_jira_qa(
            query,
            top_k=min(25, max(top_k * 2, 10)),
            exclude_jira_key=jira_key or None,
            customer=customer or None,
            base_components=[component] if component else None,
            dita_entities=[item.lstrip("@").strip("<>") for item in dita_entities],
            affected_outputs=outputs,
            customer_names=[customer] if customer else None,
        )
        for rank, hit in enumerate(hits):
            key = normalize_text(hit.get("jira_key")).upper()
            if not key:
                continue
            raw_score = hit.get("score") or hit.get("final_score") or 1.0 / (rank + 2)
            add(stable_key("jira_issue", key), float(raw_score), "semantic:jira")
    except Exception as exc:
        warnings.append(f"Jira semantic seed retrieval degraded: {type(exc).__name__}: {exc}")

    try:
        from app.services.doc_retriever_service import retrieve_relevant_docs

        for rank, hit in enumerate(retrieve_relevant_docs(query, k=min(25, max(top_k * 2, 10)))):
            score = max(0.35, 1.0 - (rank * 0.04))
            chunk_id = normalize_text(hit.get("chunk_id"))
            if chunk_id:
                add(
                    stable_key("source_chunk", f"aem_guides:{chunk_id}"),
                    score,
                    "semantic:documentation_chunk",
                )
            url = canonical_url(hit.get("canonical_url") or hit.get("source_url") or hit.get("url"))
            if url:
                add(stable_key("documentation_page", url), score, "semantic:documentation_page")
    except Exception as exc:
        warnings.append(f"Documentation semantic seed retrieval degraded: {type(exc).__name__}: {exc}")

    try:
        from app.services.dita_knowledge_retriever import retrieve_dita_knowledge

        for rank, hit in enumerate(retrieve_dita_knowledge(query, k=min(25, max(top_k, 8)))):
            element = normalize_text(hit.get("element_name")).strip("<>")
            if element and element != "dita_spec":
                add(stable_key("dita_element", element), max(0.4, 0.9 - rank * 0.05), "semantic:dita")
    except Exception as exc:
        warnings.append(f"DITA semantic seed retrieval degraded: {type(exc).__name__}: {exc}")
    return seed_keys, warnings


def _resolve_seeds(
    session: Session,
    generation_id: str,
    keyed_scores: dict[str, tuple[float, str]],
    tenant_id: str,
) -> tuple[list[Seed], list[str]]:
    if not keyed_scores:
        return [], []
    rows = (
        session.query(EvidenceGraphNode)
        .filter(
            EvidenceGraphNode.generation_id == generation_id,
            EvidenceGraphNode.active.is_(True),
            EvidenceGraphNode.stable_key.in_(list(keyed_scores)),
            or_(EvidenceGraphNode.tenant_id.is_(None), EvidenceGraphNode.tenant_id == tenant_id),
        )
        .all()
    )
    found = {row.stable_key for row in rows}
    seeds = [
        Seed(
            node_id=row.id,
            stable_key=row.stable_key,
            score=keyed_scores[row.stable_key][0],
            source=keyed_scores[row.stable_key][1],
        )
        for row in rows
    ]
    seeds.sort(key=lambda item: (-item.score, item.stable_key))
    missing = sorted(key for key in keyed_scores if key not in found and keyed_scores[key][1].startswith("selector:"))
    return seeds, missing


def _traverse(
    session: Session,
    generation_id: str,
    seeds: list[Seed],
    *,
    max_depth: int,
    max_paths: int,
    tenant_id: str,
) -> tuple[list[TraversedPath], dict[str, EvidenceGraphEdge], dict[str, EvidenceGraphNode]]:
    nodes: dict[str, EvidenceGraphNode] = {
        row.id: row
        for row in session.query(EvidenceGraphNode).filter(
            EvidenceGraphNode.id.in_([seed.node_id for seed in seeds]),
            or_(EvidenceGraphNode.tenant_id.is_(None), EvidenceGraphNode.tenant_id == tenant_id),
        )
    }
    edge_map: dict[str, EvidenceGraphEdge] = {}
    completed: list[TraversedPath] = []
    frontier = [TraversedPath(seed=seed, node_ids=(seed.node_id,), edge_ids=()) for seed in seeds]
    expansion_cap = max(100, max_paths * 40)
    for _depth in range(max_depth):
        if not frontier:
            break
        current_ids = list(dict.fromkeys(path.node_ids[-1] for path in frontier))
        edges = (
            session.query(EvidenceGraphEdge)
            .filter(
                EvidenceGraphEdge.generation_id == generation_id,
                EvidenceGraphEdge.active.is_(True),
                EvidenceGraphEdge.id.in_(
                    _authorized_edge_ids(session, generation_id, tenant_id)
                ),
                EvidenceGraphEdge.relation.in_(APPROVED_TRAVERSAL_RELATIONS),
                or_(
                    EvidenceGraphEdge.source_node_id.in_(current_ids),
                    EvidenceGraphEdge.target_node_id.in_(current_ids),
                ),
            )
            .order_by(EvidenceGraphEdge.confidence.desc(), EvidenceGraphEdge.id.asc())
            .limit(expansion_cap)
            .all()
        )
        by_node: dict[str, list[EvidenceGraphEdge]] = defaultdict(list)
        neighbor_ids: set[str] = set()
        for edge in edges:
            edge_map[edge.id] = edge
            by_node[edge.source_node_id].append(edge)
            by_node[edge.target_node_id].append(edge)
            neighbor_ids.add(edge.source_node_id)
            neighbor_ids.add(edge.target_node_id)
        if neighbor_ids:
            for row in session.query(EvidenceGraphNode).filter(
                EvidenceGraphNode.id.in_(list(neighbor_ids)),
                EvidenceGraphNode.active.is_(True),
                or_(EvidenceGraphNode.tenant_id.is_(None), EvidenceGraphNode.tenant_id == tenant_id),
            ):
                nodes[row.id] = row
        next_frontier: list[TraversedPath] = []
        for path in frontier:
            current_id = path.node_ids[-1]
            for edge in by_node.get(current_id, []):
                neighbor_id = edge.target_node_id if edge.source_node_id == current_id else edge.source_node_id
                if neighbor_id in path.node_ids or neighbor_id not in nodes:
                    continue
                candidate = TraversedPath(
                    seed=path.seed,
                    node_ids=(*path.node_ids, neighbor_id),
                    edge_ids=(*path.edge_ids, edge.id),
                )
                completed.append(candidate)
                next_frontier.append(candidate)
                if len(completed) >= expansion_cap:
                    break
            if len(completed) >= expansion_cap:
                break
        frontier = next_frontier
        if len(completed) >= expansion_cap:
            break
    return completed, edge_map, nodes


def _load_assertions(
    session: Session,
    generation_id: str,
    paths: Iterable[TraversedPath],
    tenant_id: str,
) -> tuple[dict[str, list[EvidenceGraphAssertion]], dict[str, list[EvidenceGraphAssertion]]]:
    edge_ids = sorted({edge_id for path in paths for edge_id in path.edge_ids})
    node_ids = sorted({node_id for path in paths for node_id in path.node_ids})
    edge_assertions: dict[str, list[EvidenceGraphAssertion]] = defaultdict(list)
    node_assertions: dict[str, list[EvidenceGraphAssertion]] = defaultdict(list)
    if not edge_ids and not node_ids:
        return edge_assertions, node_assertions
    for row in session.query(EvidenceGraphAssertion).filter(
        EvidenceGraphAssertion.generation_id == generation_id,
        EvidenceGraphAssertion.active.is_(True),
        or_(EvidenceGraphAssertion.tenant_id.is_(None), EvidenceGraphAssertion.tenant_id == tenant_id),
        or_(
            EvidenceGraphAssertion.edge_id.in_(edge_ids) if edge_ids else False,
            EvidenceGraphAssertion.node_id.in_(node_ids) if node_ids else False,
        ),
    ):
        if row.edge_id:
            edge_assertions[row.edge_id].append(row)
        elif row.node_id:
            node_assertions[row.node_id].append(row)
    return edge_assertions, node_assertions


def _safe_properties(node: EvidenceGraphNode) -> dict[str, Any]:
    allowed = SAFE_NODE_PROPERTIES.get(node.node_type, set())
    raw = node.properties if isinstance(node.properties, dict) else {}
    return {key: raw[key] for key in sorted(allowed) if key in raw and raw[key] not in (None, "", [], {})}


def _citation(assertion: EvidenceGraphAssertion) -> dict[str, Any]:
    leaf_id = ":".join(
        [
            assertion.source_kind,
            assertion.source_record_id,
            assertion.source_chunk_id or "",
            assertion.source_hash,
        ]
    )
    return {
        "leaf_id": leaf_id,
        "source_type": assertion.source_kind,
        "source_ref": assertion.source_ref,
        "source_record_id": assertion.source_record_id,
        "source_chunk_id": assertion.source_chunk_id,
        "source_hash": assertion.source_hash,
        "authority": assertion.authority,
        "trust_tier": assertion.trust_tier,
        "extraction_method": assertion.extraction_method,
        "excerpt": assertion.excerpt or "",
        "source_updated_at": assertion.source_updated_at.isoformat() if assertion.source_updated_at else None,
    }


def _path_citations(
    path: TraversedPath,
    edge_assertions: dict[str, list[EvidenceGraphAssertion]],
    node_assertions: dict[str, list[EvidenceGraphAssertion]],
) -> list[dict[str, Any]]:
    rows: list[EvidenceGraphAssertion] = []
    for edge_id in path.edge_ids:
        rows.extend(edge_assertions.get(edge_id, []))
    for node_id in path.node_ids:
        rows.extend(node_assertions.get(node_id, []))
    rows.sort(
        key=lambda item: (
            -TRUST_WEIGHTS.get(item.trust_tier, 0.0),
            -(item.source_updated_at.timestamp() if item.source_updated_at else 0.0),
            item.source_kind,
            item.source_record_id,
        )
    )
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for assertion in rows:
        item = _citation(assertion)
        if item["leaf_id"] in seen:
            continue
        seen.add(item["leaf_id"])
        citations.append(item)
        if len(citations) >= 8:
            break
    return citations


def _freshness_score(citations: list[dict[str, Any]]) -> float:
    timestamps = []
    for item in citations:
        raw = item.get("source_updated_at")
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            timestamps.append(parsed)
        except ValueError:
            continue
    if not timestamps:
        return 0.55
    age_days = max(0.0, (datetime.now(timezone.utc) - max(timestamps)).total_seconds() / 86400.0)
    return max(0.25, math.exp(-age_days / 730.0))


def _path_score(
    path: TraversedPath,
    edge_map: dict[str, EvidenceGraphEdge],
    nodes: dict[str, EvidenceGraphNode],
    citations: list[dict[str, Any]],
) -> float:
    edges = [edge_map[edge_id] for edge_id in path.edge_ids]
    trust = max((TRUST_WEIGHTS.get(edge.trust_tier, 0.0) for edge in edges), default=0.0)
    relation = max((RELATION_WEIGHTS.get(edge.relation, 0.5) for edge in edges), default=0.0)
    mechanism = max(
        (
            1.0
            if nodes[node_id].node_type in STRONG_MECHANISM_TYPES
            else 0.72
            if nodes[node_id].node_type == "symptom"
            else 0.35
            for node_id in path.node_ids
        ),
        default=0.0,
    )
    confidence = sum(edge.confidence for edge in edges) / len(edges) if edges else 0.0
    freshness = _freshness_score(citations)
    depth_penalty = 0.04 * max(0, len(edges) - 1)
    return round(
        max(
            0.0,
            0.30 * path.seed.score
            + 0.24 * mechanism
            + 0.18 * trust
            + 0.13 * relation
            + 0.09 * confidence
            + 0.06 * freshness
            - depth_penalty,
        ),
        6,
    )


def _jira_customers(
    session: Session,
    generation_id: str,
    jira_node_ids: list[str],
    nodes: dict[str, EvidenceGraphNode],
    tenant_id: str,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    if not jira_node_ids:
        return result
    edges = session.query(EvidenceGraphEdge).filter(
        EvidenceGraphEdge.generation_id == generation_id,
        EvidenceGraphEdge.active.is_(True),
        EvidenceGraphEdge.id.in_(_authorized_edge_ids(session, generation_id, tenant_id)),
        EvidenceGraphEdge.relation == "REPORTED_BY",
        EvidenceGraphEdge.source_node_id.in_(jira_node_ids),
    ).all()
    customer_ids = [edge.target_node_id for edge in edges]
    if customer_ids:
        for row in session.query(EvidenceGraphNode).filter(
            EvidenceGraphNode.id.in_(customer_ids),
            or_(EvidenceGraphNode.tenant_id.is_(None), EvidenceGraphNode.tenant_id == tenant_id),
        ):
            nodes[row.id] = row
    for edge in edges:
        customer = nodes.get(edge.target_node_id)
        if customer:
            result[edge.source_node_id].add(customer.label)
    return result


def _jira_signal_index(
    session: Session,
    generation_id: str,
    jira_node_ids: list[str],
    nodes: dict[str, EvidenceGraphNode],
    tenant_id: str,
) -> dict[str, dict[str, set[str]]]:
    """Load trusted direct symptom, DITA, and output signals for Jira comparison."""
    result: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    if not jira_node_ids:
        return result
    edges = session.query(EvidenceGraphEdge).filter(
        EvidenceGraphEdge.generation_id == generation_id,
        EvidenceGraphEdge.active.is_(True),
        EvidenceGraphEdge.id.in_(_authorized_edge_ids(session, generation_id, tenant_id)),
        EvidenceGraphEdge.source_node_id.in_(jira_node_ids),
        EvidenceGraphEdge.relation.in_(COMBINATION_SIGNAL_RELATIONS),
        EvidenceGraphEdge.trust_tier != "candidate",
    ).all()
    target_ids = sorted({edge.target_node_id for edge in edges})
    if target_ids:
        for row in session.query(EvidenceGraphNode).filter(
            EvidenceGraphNode.id.in_(target_ids),
            EvidenceGraphNode.active.is_(True),
            or_(EvidenceGraphNode.tenant_id.is_(None), EvidenceGraphNode.tenant_id == tenant_id),
        ):
            nodes[row.id] = row
    for edge in edges:
        target = nodes.get(edge.target_node_id)
        if target and target.node_type in {"symptom", "dita_element", "dita_attribute", "output"}:
            result[edge.source_node_id][target.node_type].add(target.id)
    return result


def _shared_signal_combination(
    current_jira_node_id: str,
    candidate_jira_node_id: str,
    signal_index: dict[str, dict[str, set[str]]],
    nodes: dict[str, EvidenceGraphNode],
) -> tuple[bool, list[str]]:
    if not current_jira_node_id or not candidate_jira_node_id:
        return False, []
    current = signal_index.get(current_jira_node_id, {})
    candidate = signal_index.get(candidate_jira_node_id, {})
    shared_symptoms = set(current.get("symptom", set())) & set(candidate.get("symptom", set()))
    shared_dita = (
        set(current.get("dita_element", set()))
        | set(current.get("dita_attribute", set()))
    ) & (
        set(candidate.get("dita_element", set()))
        | set(candidate.get("dita_attribute", set()))
    )
    shared_outputs = set(current.get("output", set())) & set(candidate.get("output", set()))
    if not shared_symptoms or not (shared_dita or shared_outputs):
        return False, []
    labels = sorted({
        nodes[node_id].label
        for node_id in sorted(shared_symptoms | shared_dita | shared_outputs)
        if node_id in nodes
    }, key=str.casefold)
    return True, labels


def _has_same_mechanism(
    path: TraversedPath,
    nodes: dict[str, EvidenceGraphNode],
    edge_map: dict[str, EvidenceGraphEdge],
) -> tuple[bool, list[str]]:
    intermediate = [nodes[node_id] for node_id in path.node_ids[1:-1] if node_id in nodes]
    strong = []
    for index, node_id in enumerate(path.node_ids[1:-1], 1):
        node = nodes.get(node_id)
        if node is None or node.node_type not in STRONG_MECHANISM_TYPES:
            continue
        adjacent_edge_ids = [
            edge_id
            for edge_id in (
                path.edge_ids[index - 1] if index - 1 < len(path.edge_ids) else None,
                path.edge_ids[index] if index < len(path.edge_ids) else None,
            )
            if edge_id
        ]
        if adjacent_edge_ids and all(
            edge_map[edge_id].trust_tier != "candidate" for edge_id in adjacent_edge_ids
        ):
            strong.append(node.label)
    if strong:
        return True, sorted(set(strong), key=str.casefold)
    signal_types = {node.node_type for node in intermediate if node.node_type in {"symptom", "dita_element", "dita_attribute", "output"}}
    if (
        len(signal_types) >= 2
        and "symptom" in signal_types
        and all(edge_map[edge_id].trust_tier != "candidate" for edge_id in path.edge_ids)
    ):
        return True, sorted(
            {node.label for node in intermediate if node.node_type in signal_types},
            key=str.casefold,
        )
    return False, []


def _path_node_trust(
    path: TraversedPath,
    node_id: str,
    edge_map: dict[str, EvidenceGraphEdge],
) -> str:
    try:
        index = path.node_ids.index(node_id)
    except ValueError:
        return "candidate"
    adjacent = [
        edge_map[edge_id].trust_tier
        for edge_id in (
            path.edge_ids[index - 1] if index > 0 else None,
            path.edge_ids[index] if index < len(path.edge_ids) else None,
        )
        if edge_id
    ]
    if not adjacent:
        return "candidate"
    return min(adjacent, key=lambda value: TRUST_WEIGHTS.get(value, 0.0))


def _render_path(
    generation_id: str,
    path: TraversedPath,
    nodes: dict[str, EvidenceGraphNode],
    edge_map: dict[str, EvidenceGraphEdge],
    citations: list[dict[str, Any]],
    score: float,
) -> dict[str, Any]:
    path_id = deterministic_id(generation_id, "path", path.seed.stable_key, *path.edge_ids)
    rendered_nodes = []
    for node_id in path.node_ids:
        node = nodes[node_id]
        rendered_nodes.append(
            {
                "stable_key": node.stable_key,
                "type": node.node_type,
                "label": node.label,
                "properties": _safe_properties(node),
            }
        )
    rendered_edges = []
    for edge_id in path.edge_ids:
        edge = edge_map[edge_id]
        rendered_edges.append(
            {
                "relation": edge.relation,
                "trust_tier": edge.trust_tier,
                "confidence": edge.confidence,
            }
        )
    return {
        "path_id": path_id,
        "score": score,
        "seed_source": path.seed.source,
        "nodes": rendered_nodes,
        "edges": rendered_edges,
        "leaf_citations": citations,
    }


def _dedupe_section(items: list[dict[str, Any]], key_fields: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for item in sorted(items, key=lambda value: (-float(value.get("score") or 0.0), str(value))):
        key = tuple(str(item.get(field) or "") for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _record_query_audit_best_effort(
    *,
    result: dict[str, Any],
    query: str,
    selectors: dict[str, Any],
    tenant_id: str,
    actor_id: str,
    influence_mode: str,
    duration_ms: int,
    cache_hit: bool,
) -> None:
    if not actor_id:
        return
    audit_session = SessionLocal()
    try:
        from app.services.evidence_graph_store import record_query_audit

        leaf_ids = {
            str(citation.get("leaf_id") or "")
            for path in result.get("evidence_paths") or []
            for citation in path.get("leaf_citations") or []
            if str(citation.get("leaf_id") or "")
        }
        record_query_audit(
            audit_session,
            generation_id=(result.get("generation") or {}).get("id"),
            tenant_id=tenant_id,
            actor_id=actor_id,
            query=query,
            selectors=selectors,
            influence_mode=influence_mode,
            status=str(result.get("status") or "unknown"),
            duration_ms=duration_ms,
            cache_hit=cache_hit,
            path_count=len(result.get("evidence_paths") or []),
            leaf_count=len(leaf_ids),
            cross_customer_detail_count=sum(
                1
                for item in result.get("same_mechanism_jira_history") or []
                if item.get("cross_customer")
            ),
            cross_customer_aggregate_count=int(
                (result.get("cross_customer_aggregate") or {}).get("same_mechanism_ticket_count", 0)
            ),
            warning_count=len(result.get("warnings") or []),
        )
        audit_session.commit()
    except Exception:
        audit_session.rollback()
    finally:
        audit_session.close()


def query_test_evidence_graph(
    query: str,
    *,
    jira_key: str = "",
    customer: str = "",
    component: str = "",
    outputs: list[str] | None = None,
    dita_entities: list[str] | None = None,
    include_cross_customer: bool = True,
    max_depth: int = 2,
    top_k: int = 10,
    max_paths: int = 20,
    tenant_id: str = "kone",
    allow_cross_customer_details: bool = False,
    actor_id: str = "",
    influence_mode: str = "interactive",
    use_cache: bool = True,
    session: Session | None = None,
) -> dict[str, Any]:
    """Query the active graph without treating graph paths as standalone evidence."""
    started_at = time.perf_counter()
    query_text = normalize_text(query)
    if not query_text:
        raise ValueError("query is required")
    depth = _clamp(max_depth, default=2, minimum=1, maximum=2)
    result_limit = _clamp(top_k, default=10, minimum=1, maximum=25)
    path_limit = _clamp(max_paths, default=20, minimum=1, maximum=50)
    jira = normalize_text(jira_key).upper()
    customer_name = normalize_text(customer)
    canonical_component = canonical_component_name(component) if normalize_text(component) else ""
    if component and not canonical_component:
        raise ValueError(f"Unsupported Jira component: {component}")
    output_values = list(dict.fromkeys(_canonical_output(value) for value in (outputs or []) if normalize_text(value)))
    dita_values = list(dict.fromkeys(normalize_text(value) for value in (dita_entities or []) if normalize_text(value)))
    normalized_tenant = normalize_text(tenant_id).casefold() or "kone"
    normalized_influence_mode = str(influence_mode or "interactive").strip().lower()
    if normalized_influence_mode not in _INFLUENCE_MODES:
        normalized_influence_mode = "interactive"
    selectors = {
        "jira_key": jira or None,
        "customer": customer_name or None,
        "component": canonical_component or None,
        "outputs": output_values,
        "dita_entities": dita_values,
        "tenant_id": normalized_tenant,
        "include_cross_customer": bool(include_cross_customer),
    }
    budget_ms = _clamp(
        os.getenv("EVIDENCE_GRAPH_QUERY_BUDGET_MS"),
        default=1500,
        minimum=100,
        maximum=30000,
    )

    def finish(result: dict[str, Any], *, cache_hit: bool = False) -> dict[str, Any]:
        duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
        runtime = {
            "duration_ms": duration_ms,
            "budget_ms": budget_ms,
            "within_budget": duration_ms <= budget_ms,
            "cache_hit": cache_hit,
        }
        result["query_runtime"] = runtime
        if duration_ms > budget_ms:
            warnings = list(result.get("warnings") or [])
            warnings.append(
                f"Evidence graph query exceeded its {budget_ms} ms soft budget; direct evidence remains authoritative."
            )
            result["warnings"] = list(dict.fromkeys(warnings))
        _record_query_audit_best_effort(
            result=result,
            query=query_text,
            selectors=selectors,
            tenant_id=normalized_tenant,
            actor_id=actor_id,
            influence_mode=normalized_influence_mode,
            duration_ms=duration_ms,
            cache_hit=cache_hit,
        )
        return result

    db = session or SessionLocal()
    owns_session = session is None
    try:
        status = _graph_status_cached(db)
        generation: EvidenceGraphGeneration | None = active_generation(db)
        if not status.get("enabled"):
            return finish({
                "available": False,
                "status": "disabled",
                "query": query_text,
                "documented_behaviors": [],
                "same_mechanism_jira_history": [],
                "release_version_boundaries": [],
                "dita_constraints": [],
                "regression_signals": [],
                "cross_customer_aggregate": {},
                "coverage_gaps": ["Evidence graph querying is disabled."],
                "evidence_paths": [],
                "graph_freshness": status,
                "redactions": {"citations_with_redactions": 0},
                "warnings": list(status.get("warnings") or []),
            })
        if generation is None:
            return finish({
                "available": False,
                "status": "unavailable",
                "query": query_text,
                "documented_behaviors": [],
                "same_mechanism_jira_history": [],
                "release_version_boundaries": [],
                "dita_constraints": [],
                "regression_signals": [],
                "cross_customer_aggregate": {},
                "coverage_gaps": ["No audited evidence graph generation is active."],
                "evidence_paths": [],
                "graph_freshness": status,
                "redactions": {"citations_with_redactions": 0},
                "warnings": list(status.get("warnings") or []),
            })

        cache_key = _cache_key(
            generation.id,
            query=query_text,
            selectors=selectors,
            tenant_id=normalized_tenant,
            allow_cross_customer_details=allow_cross_customer_details,
            max_depth=depth,
            top_k=result_limit,
            max_paths=path_limit,
        )
        if use_cache:
            cached = _cache_get(cache_key)
            if cached is not None:
                return finish(cached, cache_hit=True)

        keyed_scores, warnings = _semantic_seed_keys(
            query_text,
            jira_key=jira,
            customer=customer_name,
            component=canonical_component,
            outputs=output_values,
            dita_entities=dita_values,
            top_k=result_limit,
        )
        seeds, missing_selectors = _resolve_seeds(
            db,
            generation.id,
            keyed_scores,
            normalized_tenant,
        )
        paths, edge_map, nodes = _traverse(
            db,
            generation.id,
            seeds,
            max_depth=depth,
            max_paths=path_limit,
            tenant_id=normalized_tenant,
        )
        edge_assertions, node_assertions = _load_assertions(
            db,
            generation.id,
            paths,
            normalized_tenant,
        )

        rendered_paths: list[dict[str, Any]] = []
        documented: list[dict[str, Any]] = []
        similar: list[dict[str, Any]] = []
        releases: list[dict[str, Any]] = []
        dita_constraints: list[dict[str, Any]] = []
        regressions: list[dict[str, Any]] = []
        excluded_area_only = 0
        cross_customer_jira_keys: set[str] = set()
        cross_customer_mechanisms: dict[str, set[str]] = defaultdict(set)

        jira_node_ids = sorted(
            {
                node_id
                for path in paths
                for node_id in path.node_ids
                if nodes.get(node_id) and nodes[node_id].node_type == "jira_issue"
            }
        )
        customers_by_jira = _jira_customers(
            db,
            generation.id,
            jira_node_ids,
            nodes,
            normalized_tenant,
        )
        signals_by_jira = _jira_signal_index(
            db,
            generation.id,
            jira_node_ids,
            nodes,
            normalized_tenant,
        )
        current_jira_stable_key = stable_key("jira_issue", jira) if jira else ""
        current_jira_node_id = next(
            (
                node_id
                for node_id in jira_node_ids
                if nodes[node_id].stable_key == current_jira_stable_key
            ),
            "",
        )
        selected_customer_tokens = {
            normalized_token(value)
            for value in ([customer_name] if customer_name else customers_by_jira.get(current_jira_node_id, set()))
            if normalized_token(value)
        }

        scored_paths = []
        for path in paths:
            citations = _path_citations(path, edge_assertions, node_assertions)
            if not citations:
                continue
            score = _path_score(path, edge_map, nodes, citations)
            scored_paths.append((score, path, citations))
        scored_paths.sort(key=lambda item: (-item[0], item[1].seed.stable_key, item[1].edge_ids))

        for score, path, citations in scored_paths:
            if len(rendered_paths) >= path_limit:
                break
            path_nodes = [nodes[node_id] for node_id in path.node_ids]
            path_edges = [edge_map[edge_id] for edge_id in path.edge_ids]
            trust_tiers = {edge.trust_tier for edge in path_edges}
            terminal = path_nodes[-1]
            terminal_is_historical_jira = bool(
                terminal.node_type == "jira_issue"
                and terminal.stable_key != current_jira_stable_key
            )
            same_mechanism = False
            mechanisms: list[str] = []
            candidate_customers: list[str] = []
            candidate_customer_tokens: set[str] = set()
            same_customer = False
            is_cross_customer = False
            customer_scope_verified = False

            if terminal_is_historical_jira:
                same_mechanism, mechanisms = _has_same_mechanism(path, nodes, edge_map)
                if not same_mechanism:
                    same_mechanism, mechanisms = _shared_signal_combination(
                        current_jira_node_id,
                        terminal.id,
                        signals_by_jira,
                        nodes,
                    )
                if not same_mechanism:
                    if any(node.node_type in AREA_ONLY_NODE_TYPES for node in path_nodes[1:-1]):
                        excluded_area_only += 1
                    continue
                candidate_customers = sorted(customers_by_jira.get(terminal.id, set()))
                candidate_customer_tokens = {
                    normalized_token(value) for value in candidate_customers if normalized_token(value)
                }
                customer_scope_verified = bool(selected_customer_tokens and candidate_customer_tokens)
                same_customer = bool(selected_customer_tokens & candidate_customer_tokens)
                is_cross_customer = customer_scope_verified and not same_customer
                if not same_customer and not include_cross_customer:
                    continue
                if not allow_cross_customer_details and not same_customer:
                    candidate_key = (
                        _safe_properties(terminal).get("jira_key")
                        or terminal.stable_key.removeprefix("jira:")
                    )
                    cross_customer_jira_keys.add(str(candidate_key))
                    for mechanism in mechanisms[:3]:
                        cross_customer_mechanisms[normalized_token(mechanism)].add(str(candidate_key))
                    continue

            historical_path_jiras = [
                node
                for node in path_nodes
                if node.node_type == "jira_issue" and node.stable_key != current_jira_stable_key
            ]
            if not allow_cross_customer_details and historical_path_jiras:
                path_is_same_customer = all(
                    bool(
                        selected_customer_tokens
                        & {
                            normalized_token(value)
                            for value in customers_by_jira.get(node.id, set())
                            if normalized_token(value)
                        }
                    )
                    for node in historical_path_jiras
                )
                if not path_is_same_customer:
                    continue

            rendered = _render_path(generation.id, path, nodes, edge_map, citations, score)
            rendered_paths.append(rendered)

            behavior_nodes = [node for node in path_nodes if node.node_type == "behavior_claim"]
            behavior_node = behavior_nodes[-1] if behavior_nodes else None
            behavior_trust = (
                _path_node_trust(path, behavior_node.id, edge_map) if behavior_node is not None else "candidate"
            )
            behavior_blocked = bool(
                behavior_node
                and isinstance(behavior_node.properties, dict)
                and behavior_node.properties.get("cannot_define_expected_behavior")
            )
            if behavior_node is not None and behavior_trust != "candidate" and not behavior_blocked:
                documented.append(
                    {
                        "behavior": behavior_node.label,
                        "trust_tier": behavior_trust,
                        "score": score,
                        "path_id": rendered["path_id"],
                        "leaf_citations": citations,
                    }
                )

            relations = {edge.relation for edge in path_edges}
            if relations & RELEASE_RELATIONS:
                for release_node in (node for node in path_nodes if node.node_type == "release"):
                    releases.append(
                        {
                            "release": release_node.label,
                            "release_key": release_node.stable_key,
                            "relations": sorted(relations & RELEASE_RELATIONS),
                            "requires_live_jira_validation": any(
                                isinstance(edge.properties, dict)
                                and edge.properties.get("requires_live_jira_validation")
                                for edge in path_edges
                            ),
                            "score": score,
                            "path_id": rendered["path_id"],
                            "leaf_citations": citations,
                        }
                    )
            if relations & DITA_CONSTRAINT_RELATIONS:
                dita_constraints.append(
                    {
                        "constraint": " -> ".join(node.label for node in path_nodes),
                        "relations": sorted(relations & DITA_CONSTRAINT_RELATIONS),
                        "trust_tier": max(trust_tiers, key=lambda value: TRUST_WEIGHTS.get(value, 0.0)),
                        "score": score,
                        "path_id": rendered["path_id"],
                        "leaf_citations": citations,
                    }
                )

            if terminal_is_historical_jira:
                properties = _safe_properties(terminal)
                similar.append(
                    {
                        "jira_key": properties.get("jira_key") or terminal.stable_key.removeprefix("jira:"),
                        "summary": terminal.label,
                        "status": properties.get("status"),
                        "resolution": properties.get("resolution"),
                        "priority": properties.get("priority"),
                        "customers": candidate_customers,
                        "cross_customer": is_cross_customer,
                        "customer_scope_verified": customer_scope_verified,
                        "shared_mechanisms": mechanisms,
                        "mutable_facts_require_live_validation": True,
                        "score": score,
                        "path_id": rendered["path_id"],
                        "leaf_citations": citations,
                    }
                )

            for signal_node in path_nodes:
                if signal_node.node_type not in {"risk", "qa_oracle", "symptom", "root_cause", "error_signature"}:
                    continue
                signal_trust = _path_node_trust(path, signal_node.id, edge_map)
                blocked_as_expected = bool(
                    isinstance(signal_node.properties, dict)
                    and signal_node.properties.get("cannot_define_expected_behavior")
                )
                regressions.append(
                    {
                        "type": signal_node.node_type,
                        "signal": signal_node.label,
                        "trust_tier": signal_trust,
                        "usable_as_expected_behavior": (
                            signal_trust != "candidate"
                            and signal_node.node_type != "risk"
                            and not blocked_as_expected
                        ),
                        "score": score,
                        "path_id": rendered["path_id"],
                        "leaf_citations": citations,
                    }
                )

        coverage_gaps = [f"Selector was not represented in the active graph: {key}" for key in missing_selectors]
        if not seeds:
            coverage_gaps.append("No semantic or structured query seed resolved to an active graph node.")
        if excluded_area_only:
            coverage_gaps.append(
                f"Rejected {excluded_area_only} Jira path(s) supported only by customer/component/domain/feature overlap."
            )
        if not documented:
            coverage_gaps.append("No trusted documented behaviour claim was connected within two hops.")
        if not similar:
            coverage_gaps.append("No ticket met the deterministic same-mechanism qualification rule.")
        if status.get("status") == "degraded":
            warnings.extend(status.get("warnings") or [])
        warnings.append(
            "Graph paths are traceability metadata only; use their leaf citations as evidence and validate mutable Jira facts live."
        )
        redacted_citations = sum(
            1
            for path in rendered_paths
            for citation in path.get("leaf_citations", [])
            if "[redacted-" in str(citation.get("excerpt") or "")
        )
        result = {
            "available": True,
            "status": status.get("status") or "ready",
            "query": query_text,
            "selectors": selectors,
            "generation": {
                "id": generation.id,
                "schema_version": generation.schema_version,
                "promoted_at": generation.promoted_at.isoformat() if generation.promoted_at else None,
            },
            "documented_behaviors": _dedupe_section(documented, ("behavior",), result_limit),
            "same_mechanism_jira_history": _dedupe_section(similar, ("jira_key",), result_limit),
            "release_version_boundaries": _dedupe_section(releases, ("release_key",), result_limit),
            "dita_constraints": _dedupe_section(dita_constraints, ("constraint",), result_limit),
            "regression_signals": _dedupe_section(regressions, ("type", "signal"), result_limit),
            "cross_customer_aggregate": {
                "same_mechanism_ticket_count": len(cross_customer_jira_keys),
                **{
                    f"mechanism:{mechanism}": len(jira_keys)
                    for mechanism, jira_keys in sorted(cross_customer_mechanisms.items())
                    if mechanism
                },
            }
            if cross_customer_jira_keys
            else {},
            "coverage_gaps": list(dict.fromkeys(coverage_gaps)),
            "evidence_paths": rendered_paths,
            "graph_freshness": status,
            "redactions": {"citations_with_redactions": redacted_citations},
            "warnings": list(dict.fromkeys(warnings)),
        }
        if use_cache:
            _cache_put(cache_key, result)
        return finish(result)
    finally:
        if owns_session:
            db.close()
