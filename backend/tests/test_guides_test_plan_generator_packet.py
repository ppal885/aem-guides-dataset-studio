from app.services import guides_test_plan_generator_service as service


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
            "expected_planner_use": ["Use these chunks to summarize expected AEM Guides behavior."],
        },
    )
    monkeypatch.setattr(service, "_retrieve_dita_chunks", lambda query, k: [])
    monkeypatch.setattr(
        service,
        "_build_publishing_transform_context",
        lambda issue, query, k: {"enabled": True, "dita_ot_evidence": []},
    )
    monkeypatch.setattr(service, "_qa_preview", lambda jira_key, issue: {})

    packet = service.build_guides_test_plan_packet("DXML-12345", evidence_k=3)

    assert packet["learned_behavior_evidence"]["available"] is True
    assert packet["learned_behavior_evidence"]["results"][0]["evidence_type"] == "enriched_learned_behavior"
    assert "learned_behavior_evidence" in packet["prompt"]
    assert any("learned_behavior_evidence" in item for item in packet["instructions"])
    assert packet["planning_seeds"]["features"] == ["dita-ot-publishing", "map-management"]
    assert "schematron" in packet["planning_seeds"]["constructs"]
    assert "HTML5" in packet["planning_seeds"]["outputs"]
    assert packet["planning_seeds"]["blast_radius_seed"]
    assert packet["planning_seeds"]["bug_hypothesis_seed"]
    assert packet["planning_seeds"]["test_area_seed"]
    assert packet["planning_seeds"]["regression_risk_seed"]
    assert any(seed["id"] == "BH-SCHEMATRON-XSLT-EXCEPTION" for seed in packet["planning_seeds"]["bug_hypothesis_seed"])
    assert "planning_seeds" in packet["prompt"]
    assert any("planning_seeds" in item for item in packet["instructions"])
    repo_ids = {repo["id"] for repo in packet["repository_evidence_contract"]["required_repositories"]}
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
    assert "repository_evidence_contract" in packet["prompt"]
    assert any("repository_evidence_contract" in item for item in packet["instructions"])
    assert packet["repository_evidence"]["source"] == "local_repository_scan"
    assert packet["repo_evidence_status"] in {"complete", "partial", "missing"}
    assert "repository_evidence_seed" in packet["planning_seeds"]
    assert "repository_evidence" in packet["prompt"]
    assert any("repository_evidence" in item for item in packet["instructions"])


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
                "fails when embedded table XML contains colspec colwidth=\"369.50%\". "
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
    monkeypatch.setattr(service, "_build_publishing_transform_context", lambda issue, query, k: {"enabled": False})
    monkeypatch.setattr(service, "_qa_preview", lambda jira_key, issue: {})

    packet = service.build_guides_test_plan_packet("DXML-45678", evidence_k=3)
    seeds = packet["planning_seeds"]

    assert "snippet-management" in seeds["features"]
    assert "form-urlencoded-api" in seeds["features"]
    assert "request-decoding" in seeds["features"]
    assert "colwidth" in seeds["constructs"]
    assert "percent-character" in seeds["constructs"]
    assert "Snippet API" in seeds["outputs"]
    assert any(seed["id"] == "BR-FORM-DECODING" for seed in seeds["blast_radius_seed"])
    assert any(seed["id"] == "BH-PERCENT-DECODE-ESCAPE" for seed in seeds["bug_hypothesis_seed"])
    assert any(seed["id"] == "TA-ENCODING-MATRIX" for seed in seeds["test_area_seed"])
    assert any(seed["id"] == "RR-ENCODING-BACKWARD-COMPAT" for seed in seeds["regression_risk_seed"])
    assert "/bin/fmdita/config/snippets" in packet["repository_evidence_contract"]["focus_queries"]
    assert "guides-ui-tests" in {
        repo["id"] for repo in packet["repository_evidence_contract"]["required_repositories"]
    }
