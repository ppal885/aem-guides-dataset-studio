import time

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.evidence_graph_models import (
    EvidenceGraphAssertion,
    EvidenceGraphEdge,
    EvidenceGraphGeneration,
    EvidenceGraphNode,
    EvidenceGraphQueryAudit,
    EvidenceGraphSourceEvent,
    EvidenceGraphSourceState,
    EvidenceGraphSyncRun,
)
from app.services import evidence_graph_query_service as query_service
from app.services.evidence_graph_contract import EdgeSpec, EvidenceSpec, NodeSpec, stable_key
from app.services.evidence_graph_store import GraphWriter, create_generation, promote_generation


GRAPH_TABLES = [
    EvidenceGraphGeneration.__table__,
    EvidenceGraphNode.__table__,
    EvidenceGraphEdge.__table__,
    EvidenceGraphAssertion.__table__,
    EvidenceGraphSourceEvent.__table__,
    EvidenceGraphSourceState.__table__,
    EvidenceGraphSyncRun.__table__,
    EvidenceGraphQueryAudit.__table__,
]


def _evidence(record_id, *, trust="authoritative", source_kind="jira_enriched", tenant_id=None):
    return EvidenceSpec(
        source_kind=source_kind,
        source_ref=record_id,
        source_record_id=record_id,
        source_hash=f"sha256:{record_id.lower()}",
        extraction_method="test_fixture_exact_source",
        authority="official_fixture" if source_kind != "jira_enriched" else "indexed_jira_snapshot",
        trust_tier=trust,
        excerpt=f"Evidence for {record_id}",
        tenant_id=tenant_id,
    )


@pytest.fixture
def graph_session(tmp_path, monkeypatch):
    query_service.clear_evidence_graph_query_cache()
    engine = create_engine(
        f"sqlite:///{tmp_path / 'query-graph.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine, tables=GRAPH_TABLES)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    generation = create_generation(session)
    writer = GraphWriter(session, generation.id)

    current_key = stable_key("jira_issue", "GUIDES-100")
    same_key = stable_key("jira_issue", "GUIDES-101")
    cross_key = stable_key("jira_issue", "GUIDES-102")
    area_key = stable_key("jira_issue", "GUIDES-103")
    hidden_key = stable_key("jira_issue", "GUIDES-104")
    candidate_history_key = stable_key("jira_issue", "GUIDES-105")
    combination_history_key = stable_key("jira_issue", "GUIDES-106")
    root_key = stable_key("root_cause", "scope dropped by the shared link serializer")
    symptom_key = stable_key("symptom", "external xref is not clickable")
    output_key = stable_key("output", "AEM Sites")
    component_key = stable_key("component", "Editor")
    kone_key = stable_key("customer", "KONE")
    ey_key = stable_key("customer", "EY")
    behavior_key = stable_key("behavior_claim", "External xrefs retain scope and remain clickable.")
    candidate_behavior_key = stable_key("behavior_claim", "Generated behavior guess")
    candidate_oracle_key = stable_key("qa_oracle", "Verify the behavior contract")
    release_key = stable_key("release", "cloud:2025.02.0")
    xref_key = stable_key("dita_element", "xref")
    dir_key = stable_key("dita_attribute", "dir")

    nodes = [
        NodeSpec(
            stable_key=current_key,
            node_type="jira_issue",
            label="Current xref failure",
            properties={"jira_key": "GUIDES-100", "status": "Open"},
            evidence=[_evidence("GUIDES-100")],
        ),
        NodeSpec(
            stable_key=same_key,
            node_type="jira_issue",
            label="Earlier KONE xref failure",
            properties={"jira_key": "GUIDES-101", "status": "Closed", "resolution": "Fixed"},
            evidence=[_evidence("GUIDES-101", trust="historical_verified")],
        ),
        NodeSpec(
            stable_key=cross_key,
            node_type="jira_issue",
            label="Earlier EY xref failure",
            properties={"jira_key": "GUIDES-102", "status": "Closed", "resolution": "Fixed"},
            evidence=[_evidence("GUIDES-102", trust="historical_verified")],
        ),
        NodeSpec(
            stable_key=area_key,
            node_type="jira_issue",
            label="Unrelated editor issue",
            properties={"jira_key": "GUIDES-103"},
            evidence=[_evidence("GUIDES-103")],
        ),
        NodeSpec(
            stable_key=hidden_key,
            node_type="jira_issue",
            label="Other tenant issue",
            properties={"jira_key": "GUIDES-104"},
            tenant_id="other",
            evidence=[_evidence("GUIDES-104", tenant_id="other")],
        ),
        NodeSpec(
            stable_key=candidate_history_key,
            node_type="jira_issue",
            label="Generated behavior-only match",
            properties={"jira_key": "GUIDES-105"},
            evidence=[_evidence("GUIDES-105", trust="candidate")],
        ),
        NodeSpec(
            stable_key=combination_history_key,
            node_type="jira_issue",
            label="Earlier shared symptom and output failure",
            properties={"jira_key": "GUIDES-106", "status": "Closed", "resolution": "Fixed"},
            evidence=[_evidence("GUIDES-106", trust="historical_verified")],
        ),
        NodeSpec(stable_key=root_key, node_type="root_cause", label="Shared link serializer defect"),
        NodeSpec(stable_key=symptom_key, node_type="symptom", label="External xref is not clickable"),
        NodeSpec(stable_key=output_key, node_type="output", label="AEM Sites"),
        NodeSpec(stable_key=component_key, node_type="component", label="Editor"),
        NodeSpec(stable_key=kone_key, node_type="customer", label="KONE"),
        NodeSpec(stable_key=ey_key, node_type="customer", label="EY"),
        NodeSpec(stable_key=behavior_key, node_type="behavior_claim", label="External xrefs retain scope and remain clickable."),
        NodeSpec(stable_key=candidate_behavior_key, node_type="behavior_claim", label="Generated behavior guess"),
        NodeSpec(
            stable_key=candidate_oracle_key,
            node_type="qa_oracle",
            label="Verify the behavior contract",
            properties={"qa_oracle_source": "derived_contract_fallback", "cannot_define_expected_behavior": True},
        ),
        NodeSpec(
            stable_key=release_key,
            node_type="release",
            label="2025.02.0",
            properties={"channel": "cloud", "version": "2025.02.0"},
        ),
        NodeSpec(stable_key=xref_key, node_type="dita_element", label="<xref>"),
        NodeSpec(stable_key=dir_key, node_type="dita_attribute", label="@dir"),
    ]

    edges = []

    def add(source, relation, target, evidence, trust="supporting", confidence=0.9, properties=None):
        edges.append(
            EdgeSpec(
                source_key=source,
                relation=relation,
                target_key=target,
                trust_tier=trust,
                confidence=confidence,
                properties=properties or {},
                evidence=[evidence],
            )
        )

    add(current_key, "HAS_ROOT_CAUSE", root_key, _evidence("GUIDES-100"), "authoritative", 1.0)
    add(same_key, "HAS_ROOT_CAUSE", root_key, _evidence("GUIDES-101", trust="historical_verified"), "historical_verified", 0.95)
    add(cross_key, "HAS_ROOT_CAUSE", root_key, _evidence("GUIDES-102", trust="historical_verified"), "historical_verified", 0.95)
    add(hidden_key, "HAS_ROOT_CAUSE", root_key, _evidence("GUIDES-104", tenant_id="other"), "historical_verified", 0.95)
    add(current_key, "IN_COMPONENT", component_key, _evidence("GUIDES-100"), properties={"ranking_only": True})
    add(area_key, "IN_COMPONENT", component_key, _evidence("GUIDES-103"), properties={"ranking_only": True})
    add(current_key, "REPORTED_BY", kone_key, _evidence("GUIDES-100"), "authoritative", 1.0)
    add(same_key, "REPORTED_BY", kone_key, _evidence("GUIDES-101"), "authoritative", 1.0)
    add(cross_key, "REPORTED_BY", ey_key, _evidence("GUIDES-102"), "authoritative", 1.0)
    add(area_key, "REPORTED_BY", kone_key, _evidence("GUIDES-103"), "authoritative", 1.0)
    add(candidate_history_key, "REPORTED_BY", kone_key, _evidence("GUIDES-105"), "authoritative", 1.0)
    add(combination_history_key, "REPORTED_BY", kone_key, _evidence("GUIDES-106"), "authoritative", 1.0)
    add(current_key, "HAS_ACTUAL_BEHAVIOR", symptom_key, _evidence("GUIDES-100"), "authoritative", 0.95)
    add(combination_history_key, "HAS_ACTUAL_BEHAVIOR", symptom_key, _evidence("GUIDES-106", trust="historical_verified"), "historical_verified", 0.9)
    add(current_key, "AFFECTS_OUTPUT", output_key, _evidence("GUIDES-100"), "supporting", 0.8)
    add(combination_history_key, "AFFECTS_OUTPUT", output_key, _evidence("GUIDES-106", trust="historical_verified"), "historical_verified", 0.8)
    add(current_key, "HAS_EXPECTED_BEHAVIOR", behavior_key, _evidence("doc-behavior", source_kind="aem_guides_chroma"), "authoritative", 0.98)
    add(current_key, "HAS_EXPECTED_BEHAVIOR", candidate_behavior_key, _evidence("derived-behavior", trust="candidate"), "candidate", 0.2, {"cannot_define_expected_behavior": True})
    add(candidate_history_key, "HAS_EXPECTED_BEHAVIOR", behavior_key, _evidence("GUIDES-105", trust="candidate"), "candidate", 0.2, {"cannot_define_expected_behavior": True})
    add(current_key, "HAS_QA_ORACLE", candidate_oracle_key, _evidence("derived-oracle", trust="candidate"), "candidate", 0.2, {"qa_oracle_source": "derived_contract_fallback", "cannot_define_expected_behavior": True})
    add(current_key, "AFFECTS_VERSION", release_key, _evidence("GUIDES-100"), "authoritative", 1.0, {"requires_live_jira_validation": True})
    add(xref_key, "HAS_ATTRIBUTE", dir_key, _evidence("dita-dir", source_kind="dita_spec_sql"), "authoritative", 1.0)

    writer.write(nodes, edges)
    promote_generation(session, generation.id)
    session.commit()
    monkeypatch.setenv("EVIDENCE_GRAPH_ENABLED", "true")

    def fake_seeds(_query, *, jira_key, customer, component, outputs, dita_entities, top_k):
        del customer, component, outputs, top_k
        values = {}
        if jira_key:
            values[stable_key("jira_issue", jira_key)] = (1.0, "selector:jira")
        for entity in dita_entities:
            node_type = "dita_attribute" if entity.startswith("@") else "dita_element"
            values[stable_key(node_type, entity.lstrip("@").strip("<>"))] = (0.95, "selector:dita")
        return values, []

    monkeypatch.setattr(query_service, "_semantic_seed_keys", fake_seeds)
    try:
        yield session
    finally:
        query_service.clear_evidence_graph_query_cache()
        session.close()


def _query(session, **overrides):
    params = {
        "jira_key": "GUIDES-100",
        "customer": "KONE",
        "component": "Editor",
        "include_cross_customer": True,
        "max_depth": 2,
        "top_k": 25,
        "max_paths": 50,
        "tenant_id": "kone",
        "session": session,
    }
    params.update(overrides)
    return query_service.query_test_evidence_graph("xref scope publish failure", **params)


def test_query_returns_only_same_mechanism_history_and_leaf_provenance(graph_session):
    result = _query(graph_session, allow_cross_customer_details=True)

    history = {item["jira_key"]: item for item in result["same_mechanism_jira_history"]}
    assert {"GUIDES-101", "GUIDES-102", "GUIDES-106"} <= set(history)
    assert "GUIDES-103" not in history
    assert "GUIDES-104" not in history
    assert "GUIDES-105" not in history
    assert history["GUIDES-101"]["shared_mechanisms"] == ["Shared link serializer defect"]
    assert history["GUIDES-102"]["cross_customer"] is True
    assert history["GUIDES-106"]["shared_mechanisms"] == [
        "AEM Sites",
        "External xref is not clickable",
    ]
    assert all(item["leaf_citations"] for item in history.values())
    assert all(citation["source_ref"] for item in history.values() for citation in item["leaf_citations"])
    assert any("supported only" in gap for gap in result["coverage_gaps"])
    assert all(path["path_id"] and path["leaf_citations"] for path in result["evidence_paths"])


def test_cross_customer_ticket_details_are_aggregated_without_reader_role(graph_session):
    result = _query(graph_session, allow_cross_customer_details=False)

    assert {item["jira_key"] for item in result["same_mechanism_jira_history"]} == {
        "GUIDES-101",
        "GUIDES-106",
    }
    assert result["cross_customer_aggregate"]["same_mechanism_ticket_count"] == 1
    assert all("GUIDES-102" not in str(item) for item in result["same_mechanism_jira_history"])
    assert all("GUIDES-102" not in str(path) for path in result["evidence_paths"])
    assert all("Earlier EY xref failure" not in str(path) for path in result["evidence_paths"])


def test_regular_user_derives_same_customer_from_current_jira_without_customer_selector(graph_session):
    result = _query(
        graph_session,
        customer="",
        allow_cross_customer_details=False,
    )

    assert {item["jira_key"] for item in result["same_mechanism_jira_history"]} == {
        "GUIDES-101",
        "GUIDES-106",
    }
    assert result["cross_customer_aggregate"]["same_mechanism_ticket_count"] == 1
    assert all("GUIDES-102" not in str(path) for path in result["evidence_paths"])


def test_candidate_claims_and_fallback_oracles_cannot_define_expected_behavior(graph_session):
    result = _query(graph_session, allow_cross_customer_details=True)

    behaviors = {item["behavior"] for item in result["documented_behaviors"]}
    assert "External xrefs retain scope and remain clickable." in behaviors
    assert "Generated behavior guess" not in behaviors
    fallback = next(
        signal for signal in result["regression_signals"] if signal["signal"] == "Verify the behavior contract"
    )
    assert fallback["trust_tier"] == "candidate"
    assert fallback["usable_as_expected_behavior"] is False


def test_dita_constraints_are_returned_with_oasis_leaf_citation(graph_session):
    result = _query(
        graph_session,
        jira_key="",
        customer="",
        component="",
        dita_entities=["@dir"],
        allow_cross_customer_details=False,
    )

    assert any("HAS_ATTRIBUTE" in item["relations"] for item in result["dita_constraints"])
    assert any(
        citation["source_type"] == "dita_spec_sql"
        for item in result["dita_constraints"]
        for citation in item["leaf_citations"]
    )


def test_release_boundaries_require_live_jira_validation(graph_session):
    result = _query(graph_session, allow_cross_customer_details=True)

    release = next(
        item for item in result["release_version_boundaries"] if item["release"] == "2025.02.0"
    )
    assert release["requires_live_jira_validation"] is True
    assert release["leaf_citations"]


def test_tenant_specific_seed_from_other_tenant_is_not_visible(graph_session, monkeypatch):
    monkeypatch.setattr(
        query_service,
        "_semantic_seed_keys",
        lambda *args, **kwargs: ({stable_key("jira_issue", "GUIDES-104"): (1.0, "selector:jira")}, []),
    )

    result = _query(graph_session, jira_key="GUIDES-104", allow_cross_customer_details=True)

    assert result["evidence_paths"] == []
    assert any("No semantic or structured query seed" in gap for gap in result["coverage_gaps"])


def test_tenant_inaccessible_edge_assertions_cannot_drive_paths_or_similarity(graph_session):
    current = graph_session.query(EvidenceGraphNode).filter_by(
        stable_key=stable_key("jira_issue", "GUIDES-100")
    ).one()
    protected_edge_ids = [
        edge_id
        for (edge_id,) in graph_session.query(EvidenceGraphEdge.id).filter(
            EvidenceGraphEdge.source_node_id == current.id,
            EvidenceGraphEdge.relation.in_(
                ("HAS_ROOT_CAUSE", "HAS_ACTUAL_BEHAVIOR", "AFFECTS_OUTPUT")
            ),
        )
    ]
    graph_session.query(EvidenceGraphAssertion).filter(
        EvidenceGraphAssertion.edge_id.in_(protected_edge_ids)
    ).update({EvidenceGraphAssertion.tenant_id: "other"}, synchronize_session=False)
    graph_session.commit()
    query_service.clear_evidence_graph_query_cache()

    result = _query(graph_session, allow_cross_customer_details=True)

    assert result["same_mechanism_jira_history"] == []
    assert all(
        path["edges"][0]["relation"]
        not in {"HAS_ROOT_CAUSE", "HAS_ACTUAL_BEHAVIOR", "AFFECTS_OUTPUT"}
        for path in result["evidence_paths"]
    )


def test_disabled_graph_returns_stable_structured_shape(graph_session, monkeypatch):
    monkeypatch.setenv("EVIDENCE_GRAPH_ENABLED", "false")

    result = _query(graph_session)

    assert result["status"] == "disabled"
    assert result["available"] is False
    assert result["evidence_paths"] == []
    assert result["cross_customer_aggregate"] == {}


def test_warm_graph_query_p95_is_below_acceptance_threshold(graph_session):
    _query(graph_session, allow_cross_customer_details=True)
    durations = []
    for _ in range(25):
        started = time.perf_counter()
        _query(graph_session, allow_cross_customer_details=True)
        durations.append(time.perf_counter() - started)
    p95 = sorted(durations)[int(len(durations) * 0.95) - 1]
    assert p95 <= 1.5


def test_query_cache_is_generation_and_permission_aware(graph_session, monkeypatch):
    monkeypatch.setenv("EVIDENCE_GRAPH_QUERY_CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("EVIDENCE_GRAPH_QUERY_CACHE_MAX_ENTRIES", "8")
    query_service.clear_evidence_graph_query_cache()
    status_calls = []
    original_graph_status = query_service.graph_status
    monkeypatch.setattr(
        query_service,
        "graph_status",
        lambda session: status_calls.append(True) or original_graph_status(session),
    )

    first = _query(graph_session, allow_cross_customer_details=False)
    second = _query(graph_session, allow_cross_customer_details=False)

    assert first["query_runtime"]["cache_hit"] is False
    assert second["query_runtime"]["cache_hit"] is True
    assert len(status_calls) == 1
    selectors = {
        "jira_key": "GUIDES-100",
        "customer": "KONE",
        "component": "Editor",
        "outputs": [],
        "dita_entities": [],
        "tenant_id": "kone",
        "include_cross_customer": True,
    }
    base = query_service._cache_key(
        "generation-a",
        query="xref failure",
        selectors=selectors,
        tenant_id="kone",
        allow_cross_customer_details=False,
        max_depth=2,
        top_k=10,
        max_paths=20,
    )
    assert base != query_service._cache_key(
        "generation-b",
        query="xref failure",
        selectors=selectors,
        tenant_id="kone",
        allow_cross_customer_details=False,
        max_depth=2,
        top_k=10,
        max_paths=20,
    )
    assert base != query_service._cache_key(
        "generation-a",
        query="xref failure",
        selectors=selectors,
        tenant_id="kone",
        allow_cross_customer_details=True,
        max_depth=2,
        top_k=10,
        max_paths=20,
    )


def test_invalid_query_runtime_environment_values_fail_safe(graph_session, monkeypatch):
    monkeypatch.setenv("EVIDENCE_GRAPH_STATUS_CACHE_TTL_SECONDS", "invalid")
    monkeypatch.setenv("EVIDENCE_GRAPH_QUERY_CACHE_TTL_SECONDS", "invalid")
    monkeypatch.setenv("EVIDENCE_GRAPH_QUERY_CACHE_MAX_ENTRIES", "invalid")
    monkeypatch.setenv("EVIDENCE_GRAPH_QUERY_BUDGET_MS", "invalid")
    query_service.clear_evidence_graph_query_cache()

    result = _query(graph_session, allow_cross_customer_details=True)

    assert result["available"] is True
    assert result["query_runtime"]["budget_ms"] == 1500
