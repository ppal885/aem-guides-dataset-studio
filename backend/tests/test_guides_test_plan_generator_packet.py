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
