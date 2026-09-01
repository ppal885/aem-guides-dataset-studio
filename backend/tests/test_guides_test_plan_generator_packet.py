import pytest

from app.services import guides_test_plan_generator_service as service


def test_generator_entrypoint_delegates_to_canonical_runtime(monkeypatch):
    monkeypatch.setattr(
        service,
        "_collect_guides_test_plan_evidence_packet",
        lambda *args, **kwargs: {
            "jira_key": "GUIDES-42",
            "generation_mode": "full_rag",
            "issue": {
                "issue_key": "GUIDES-42",
                "summary": "The API should preserve the complete asset path.",
                "expected_behavior": "The API should preserve the complete asset path.",
            },
        },
    )

    projected = service.build_guides_test_plan_packet("GUIDES-42")

    assert projected["projection_version"] == "canonical-result-compatibility-v2"
    assert projected["runtime_id"] == "aem-guides-test-plan-runtime"
    assert projected["plan_markdown"]
    assert projected["issue"]["issue_key"] == "GUIDES-42"
    assert (
        service.render_guides_test_plan_packet_markdown(projected)
        == projected["plan_markdown"]
    )


@pytest.fixture(autouse=True)
def _stub_optional_graph_and_history(monkeypatch):
    monkeypatch.setattr(
        "app.services.jira_history_search_service.search_jira_history_evidence",
        lambda query, **kwargs: {
            "searched_jira_qa": True,
            "indexed_chunks": 0,
            "component_filter": kwargs.get("component") or None,
            "customer_filter": kwargs.get("customer") or None,
            "match_count": 0,
            "results": [],
            "note": "test fixture",
        },
    )
    monkeypatch.setattr(
        service,
        "_retrieve_evidence_graph",
        lambda *args, **kwargs: {
            "available": False,
            "status": "disabled",
            "evidence_paths": [],
        },
    )


def test_guides_packet_exposes_scraped_behavior_evidence(monkeypatch):
    monkeypatch.setattr(
        service,
        "_lookup_issue",
        lambda jira_key, tenant_id: {
            "issue_key": jira_key,
            "summary": "PDF output fails for map publishing",
            "description": "Publishing ticket involving HTML5 and DITA-OT output.",
            "labels": ["publishing", "html5"],
        },
    )
    monkeypatch.setattr(
        service,
        "_retrieve_aem_docs",
        lambda query, k: [
            {
                "chunk_id": "doc-1",
                "title": "Generate output",
                "source_url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/example",
                "canonical_url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/example",
                "snippet": "Official documentation.",
                "corpus": "aem_guides",
                "evidence_type": "enriched_evidence_excerpt",
            }
        ],
    )
    monkeypatch.setattr(
        service,
        "_retrieve_learned_behavior_evidence",
        lambda query, k: {
            "available": True,
            "source": "scraped_experienceleague_dita_behavior_chunks",
            "result_count": 1,
            "results": [
                {
                    "chunk_id": "behavior-1",
                    "title": "HTML5",
                    "source_url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/html5",
                    "canonical_url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/html5",
                    "evidence_type": "enriched_learned_behavior",
                    "snippet": (
                        "Learned feature behavior: dita-ot-publishing, map-management. "
                        "Detected DITA constructs and attributes: schematron, map, topicref. "
                        "Publishing/output contexts: PDF, HTML5. "
                        "Generation requirement: produce QA checklist and HTML5 review areas."
                    ),
                }
            ],
            "expected_planner_use": [
                "Use these chunks to summarize expected AEM Guides behavior."
            ],
        },
    )
    monkeypatch.setattr(service, "_retrieve_dita_chunks", lambda query, k: [])
    monkeypatch.setattr(
        service,
        "_build_publishing_transform_context",
        lambda issue, query, k: {"enabled": True, "dita_ot_evidence": []},
    )
    monkeypatch.setattr(service, "_qa_preview", lambda jira_key, issue: {})

    packet = service.build_guides_test_plan_evidence_packet("DXML-12345", evidence_k=3)

    assert packet["learned_behavior_evidence"]["available"] is True
    assert (
        packet["learned_behavior_evidence"]["results"][0]["evidence_type"]
        == "enriched_learned_behavior"
    )
    assert packet["canonical_runtime_contract"]["packet_role"] == "evidence_only"
    assert packet["canonical_runtime_contract"]["caller_reasoning_allowed"] is False
    assert "prompt" not in packet
    assert "instructions" not in packet
    assert packet["planning_seeds"]["features"] == [
        "dita-ot-publishing",
        "map-management",
    ]
    assert "schematron" in packet["planning_seeds"]["constructs"]
    assert "HTML5" in packet["planning_seeds"]["outputs"]
    assert packet["planning_seeds"]["blast_radius_seed"]
    assert packet["planning_seeds"]["bug_hypothesis_seed"]
    assert packet["planning_seeds"]["test_area_seed"]
    assert packet["planning_seeds"]["regression_risk_seed"]
    assert any(
        seed["id"] == "BH-SCHEMATRON-XSLT-EXCEPTION"
        for seed in packet["planning_seeds"]["bug_hypothesis_seed"]
    )
    repo_ids = {
        repo["id"]
        for repo in packet["repository_evidence_contract"]["required_repositories"]
    }
    assert {"xmleditor", "starling", "guides-ui-tests", "dxml-it-tests"} <= repo_ids
    repo_roles = {
        repo["id"]: repo["owner_role"]
        for repo in packet["repository_evidence_contract"]["required_repositories"]
    }
    assert repo_roles["xmleditor"] == "frontend"
    assert repo_roles["starling"] == "backend"
    gates = {
        gate["owner_role"]: gate
        for gate in packet["repository_evidence_contract"]["role_based_evidence_gates"]
    }
    assert gates["frontend"]["primary_repo"] == "xmleditor"
    assert gates["frontend"]["automation_repo"] == "guides-ui-tests"
    assert gates["backend"]["primary_repo"] == "starling"
    assert gates["backend"]["automation_repo"] == "dxml-it-tests"
    assert packet["repository_evidence"]["source"] == "local_repository_scan"
    assert packet["repo_evidence_status"] in {"complete", "partial", "missing"}
    assert "repository_evidence_seed" in packet["planning_seeds"]


def test_lookup_issue_uses_direct_jira_fetch(monkeypatch):
    captured = {}

    class FakeClient:
        base_url = "https://jira.corp.adobe.com"

        def is_configured(self):
            return True

        def get_issue(self, issue_key):
            captured["issue_key"] = issue_key
            return {
                "key": issue_key,
                "fields": {
                    "summary": "Broken Links Report hangs",
                    "description": "Map with 600 topics hangs in browser.",
                    "status": {"name": "Open"},
                    "issuetype": {"name": "Bug"},
                    "priority": {"name": "Critical"},
                    "labels": ["sla3"],
                    "components": [{"name": "Reports"}],
                },
            }

    monkeypatch.setattr(
        "app.services.tenant_service.build_jira_client",
        lambda tenant_id: FakeClient(),
    )
    monkeypatch.setattr(
        "app.services.jira_client.extract_description_from_issue",
        lambda issue: issue.get("fields", {}).get("description", ""),
    )

    issue = service._fetch_issue_direct("GUIDES-37845", tenant_id="kone")

    assert captured["issue_key"] == "GUIDES-37845"
    assert issue["source"] == "jira_api"
    assert issue["lookup_source"] == "jira_api_direct"
    assert issue["summary"] == "Broken Links Report hangs"
    assert issue["components"] == ["Reports"]


def test_guides_packet_derives_api_encoding_seeds_from_jira_text(monkeypatch):
    monkeypatch.setattr(
        service,
        "_lookup_issue",
        lambda jira_key, tenant_id: {
            "issue_key": jira_key,
            "summary": "Unable to Create Snippet When colwidth Contains Percentage Value (%)",
            "description": (
                "POST /bin/fmdita/config/snippets with Content-Type application/x-www-form-urlencoded "
                'fails when embedded table XML contains colspec colwidth="369.50%". '
                "Error: URLDecoder Illegal hex characters in escape (%) pattern."
            ),
            "labels": ["api"],
        },
    )
    monkeypatch.setattr(service, "_retrieve_aem_docs", lambda query, k: [])
    monkeypatch.setattr(
        service,
        "_retrieve_learned_behavior_evidence",
        lambda query, k: {
            "available": False,
            "source": "scraped_experienceleague_dita_behavior_chunks",
            "results": [],
            "expected_planner_use": [],
        },
    )
    monkeypatch.setattr(service, "_retrieve_dita_chunks", lambda query, k: [])
    monkeypatch.setattr(
        service,
        "_build_publishing_transform_context",
        lambda issue, query, k: {"enabled": False},
    )
    monkeypatch.setattr(service, "_qa_preview", lambda jira_key, issue: {})

    packet = service.build_guides_test_plan_evidence_packet("DXML-45678", evidence_k=3)
    seeds = packet["planning_seeds"]

    assert "snippet-management" in seeds["features"]
    assert "form-urlencoded-api" in seeds["features"]
    assert "request-decoding" in seeds["features"]
    assert "colwidth" in seeds["constructs"]
    assert "percent-character" in seeds["constructs"]
    assert "Snippet API" in seeds["outputs"]
    assert any(seed["id"] == "BR-FORM-DECODING" for seed in seeds["blast_radius_seed"])
    assert any(
        seed["id"] == "BH-PERCENT-DECODE-ESCAPE"
        for seed in seeds["bug_hypothesis_seed"]
    )
    assert any(seed["id"] == "TA-ENCODING-MATRIX" for seed in seeds["test_area_seed"])
    assert any(
        seed["id"] == "RR-ENCODING-BACKWARD-COMPAT"
        for seed in seeds["regression_risk_seed"]
    )
    assert (
        "/bin/fmdita/config/snippets"
        in packet["repository_evidence_contract"]["focus_queries"]
    )
    assert "guides-ui-tests" in {
        repo["id"]
        for repo in packet["repository_evidence_contract"]["required_repositories"]
    }


def test_direct_jira_history_runs_same_and_cross_customer(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append(kwargs)
        customer = kwargs.get("customer") or ""
        return {
            "searched_jira_qa": True,
            "indexed_chunks": 100,
            "component_filter": kwargs.get("component") or None,
            "customer_filter": customer or None,
            "results": [
                {
                    "jira_key": "GUIDES-200",
                    "customer": customer or "EY",
                    "customers": [customer or "EY"],
                    "why_similar": "Shared xref serializer",
                },
                {
                    "jira_key": "GUIDES-201",
                    "customer": "KONE",
                    "customers": ["KONE"],
                    "why_similar": "Shared scope behavior",
                },
            ],
            "match_count": 2,
            "note": "searched",
        }

    monkeypatch.setattr(
        "app.services.jira_history_search_service.search_jira_history_evidence",
        fake_search,
    )
    issue = {
        "issue_key": "GUIDES-100",
        "customer": "KONE",
        "components": ["Editor"],
    }

    result = service._retrieve_direct_jira_history(
        "GUIDES-100",
        issue,
        "xref scope is dropped",
        {"outputs": ["AEM Sites"], "constructs": ["xref", "scope"]},
        top_k=5,
    )

    assert [call.get("customer") for call in calls] == ["KONE", ""]
    assert all(call["component"] == "Editor" for call in calls)
    assert all(call["exclude_jira_key"] == "GUIDES-100" for call in calls)
    assert {row["jira_key"] for row in result["same_customer"]["results"]} == {
        "GUIDES-200",
        "GUIDES-201",
    }
    assert [row["jira_key"] for row in result["cross_customer"]["results"]] == [
        "GUIDES-200"
    ]
    assert all(
        row["evidence_origin"] == "search_jira_history"
        for scope in ("same_customer", "cross_customer")
        for row in result[scope]["results"]
    )


def test_same_customer_history_is_explicitly_unavailable_without_customer(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.jira_history_search_service.search_jira_history_evidence",
        lambda query, **kwargs: (
            calls.append(kwargs)
            or {
                "searched_jira_qa": False,
                "indexed_chunks": 0,
                "results": [],
                "match_count": 0,
                "note": "unavailable",
            }
        ),
    )

    result = service._retrieve_direct_jira_history(
        "GUIDES-100",
        {"issue_key": "GUIDES-100", "components": ["Editor"]},
        "xref scope is dropped",
        {},
        top_k=5,
    )

    assert len(calls) == 1
    assert result["same_customer"]["status"] == "not_applicable"
    assert result["cross_customer"]["status"] == "degraded"
    assert result["warnings"]


def test_packet_retrieves_direct_history_before_graph(monkeypatch):
    order = []
    monkeypatch.setattr(
        service,
        "_lookup_issue",
        lambda jira_key, tenant_id: {"issue_key": jira_key, "summary": "xref failure"},
    )
    monkeypatch.setattr(service, "_retrieve_aem_docs", lambda query, k: [])
    monkeypatch.setattr(
        service,
        "_retrieve_learned_behavior_evidence",
        lambda query, k: {"available": False, "results": []},
    )
    monkeypatch.setattr(service, "_retrieve_dita_chunks", lambda query, k: [])
    monkeypatch.setattr(
        service,
        "_build_publishing_transform_context",
        lambda issue, query, k: {"enabled": False},
    )
    monkeypatch.setattr(
        service,
        "_retrieve_direct_jira_history",
        lambda *args, **kwargs: (
            order.append("history")
            or {
                "same_customer": {"results": []},
                "cross_customer": {"results": []},
                "warnings": [],
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "_retrieve_evidence_graph",
        lambda *args, **kwargs: (
            order.append("graph")
            or {"available": True, "status": "ready", "evidence_paths": []}
        ),
    )
    monkeypatch.setattr(
        service,
        "_collect_repository_evidence",
        lambda *args, **kwargs: {"status": "missing"},
    )
    monkeypatch.setattr(service, "_qa_preview", lambda jira_key, issue: {})

    packet = service.build_guides_test_plan_evidence_packet("GUIDES-100")

    assert order == ["history", "graph"]
    assert "jira_history_searches" in packet
    assert packet["evidence_graph_influence_mode"] == "shadow"
    assert packet["evidence_graph_evaluation"]["used_for_plan"] is False
    assert (
        "Direct Jira history searches"
        in service.render_guides_test_plan_packet_markdown(packet)
    )


def test_disabled_graph_keeps_existing_planning_seeds(monkeypatch):
    monkeypatch.delenv("EVIDENCE_GRAPH_ENABLED", raising=False)
    direct_seed = {
        "direct_jira_history_seed": [
            {"jira_key": "GUIDES-100", "evidence": ["JIRA:GUIDES-100"]}
        ],
        "regression_risk_seed": [
            {"id": "DIRECT-RR-01", "rationale": "Existing direct-evidence risk"}
        ],
    }

    graph = service._retrieve_evidence_graph(
        "GUIDES-200",
        {"issue_key": "GUIDES-200", "summary": "xref failure"},
        "xref failure",
        direct_seed,
        tenant_id="kone",
        enabled=True,
        max_paths=20,
        allow_cross_customer_details=False,
    )
    merged = service._add_evidence_graph_seeds(direct_seed, graph)

    assert graph["status"] == "disabled"
    assert merged["direct_jira_history_seed"] == direct_seed["direct_jira_history_seed"]
    assert merged["regression_risk_seed"] == direct_seed["regression_risk_seed"]


@pytest.mark.parametrize(
    ("mode", "should_augment"),
    (("shadow", False), ("augment", True)),
)
def test_graph_mode_controls_plan_seed_influence(monkeypatch, mode, should_augment):
    monkeypatch.setenv("EVIDENCE_GRAPH_TEST_PLAN_MODE", mode)
    baseline = {
        "features": [],
        "constructs": [],
        "outputs": [],
        "blast_radius_seed": [],
        "bug_hypothesis_seed": [],
        "test_area_seed": [],
        "regression_risk_seed": [{"id": "DIRECT-RISK", "rationale": "Direct risk"}],
    }
    monkeypatch.setattr(
        service,
        "_lookup_issue",
        lambda jira_key, tenant_id: {"issue_key": jira_key, "summary": "xref failure"},
    )
    monkeypatch.setattr(service, "_retrieve_aem_docs", lambda query, k: [])
    monkeypatch.setattr(
        service,
        "_retrieve_learned_behavior_evidence",
        lambda query, k: {"available": False, "results": []},
    )
    monkeypatch.setattr(
        service, "_derive_planning_seeds", lambda *_args: dict(baseline)
    )
    monkeypatch.setattr(service, "_retrieve_dita_chunks", lambda query, k: [])
    monkeypatch.setattr(
        service,
        "_build_publishing_transform_context",
        lambda issue, query, k: {"enabled": False},
    )
    monkeypatch.setattr(
        service,
        "_retrieve_direct_jira_history",
        lambda *args, **kwargs: {
            "same_customer": {"results": []},
            "cross_customer": {"results": []},
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        service,
        "_retrieve_evidence_graph",
        lambda *args, **kwargs: {
            "available": True,
            "status": "ready",
            "generation": {"id": "generation-1"},
            "documented_behaviors": [
                {
                    "behavior": "Graph-only behavior",
                    "trust_tier": "authoritative",
                    "leaf_citations": [{"leaf_id": "doc:1"}],
                }
            ],
            "same_mechanism_jira_history": [],
            "regression_signals": [
                {
                    "signal": "Graph-only risk",
                    "trust_tier": "supporting",
                    "leaf_citations": [{"leaf_id": "doc:1"}],
                }
            ],
            "evidence_paths": [
                {"path_id": "path-1", "leaf_citations": [{"leaf_id": "doc:1"}]}
            ],
        },
    )
    monkeypatch.setattr(
        service,
        "_collect_repository_evidence",
        lambda *args, **kwargs: {
            "status": "missing",
            "repositories": [],
            "owner_gates": [],
        },
    )
    monkeypatch.setattr(
        service, "_add_repository_evidence_seeds", lambda seeds, _repo: seeds
    )
    monkeypatch.setattr(service, "_qa_preview", lambda jira_key, issue: {})

    packet = service.build_guides_test_plan_evidence_packet("GUIDES-900")

    assert packet["evidence_graph_influence_mode"] == mode
    assert packet["evidence_graph_evaluation"]["used_for_plan"] is should_augment
    if should_augment:
        assert (
            packet["planning_seeds"]["documented_behavior_seed"][0]["behavior"]
            == "Graph-only behavior"
        )
        assert any(
            row.get("rationale") == "Graph-only risk"
            for row in packet["planning_seeds"]["regression_risk_seed"]
        )
    else:
        assert "documented_behavior_seed" not in packet["planning_seeds"]
        assert (
            packet["planning_seeds"]["regression_risk_seed"]
            == baseline["regression_risk_seed"]
        )


def test_invalid_graph_mode_fails_safe_to_shadow(monkeypatch):
    monkeypatch.setenv("EVIDENCE_GRAPH_TEST_PLAN_MODE", "force-everything")

    assert service._evidence_graph_test_plan_mode(requested=True) == "shadow"
    assert service._evidence_graph_test_plan_mode(requested=False) == "off"
