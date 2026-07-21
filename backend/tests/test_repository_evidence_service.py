from app.services.repository_evidence_service import collect_repository_evidence


def test_collect_repository_evidence_scans_owner_repos(tmp_path, monkeypatch):
    xmleditor = tmp_path / "xmleditor"
    starling = tmp_path / "starling"
    ui_tests = tmp_path / "guides-ui-tests"
    it_tests = tmp_path / "dxml-it-tests"
    for path in (xmleditor, starling, ui_tests, it_tests):
        path.mkdir()

    (xmleditor / "BrokenLinksReport.tsx").write_text(
        "function BrokenLinksReport(){ fetch('/bin/fmdita/reports/broken-links?pageSize=50') }",
        encoding="utf-8",
    )
    (starling / "BrokenLinksServlet.java").write_text(
        "class BrokenLinksServlet { void doGet(){ /* Broken Links Report pagination */ } }",
        encoding="utf-8",
    )
    (ui_tests / "broken_links_report.spec.ts").write_text(
        "test('Broken Links Report paginates large map results', async () => {})",
        encoding="utf-8",
    )
    (it_tests / "BrokenLinksReportIT.java").write_text(
        "class BrokenLinksReportIT { void largeMapPagination(){ /* broken links */ } }",
        encoding="utf-8",
    )

    monkeypatch.setenv("XML_EDITOR_REPO_PATH", str(xmleditor))
    monkeypatch.setenv("STARLING_REPO_PATH", str(starling))
    monkeypatch.setenv("GUIDES_UI_TESTS_REPO_PATH", str(ui_tests))
    monkeypatch.setenv("DXML_IT_TESTS_REPO_PATH", str(it_tests))

    repo_contract = {
        "required_repositories": [
            {"id": "xmleditor", "owner_role": "frontend", "path_env": "XML_EDITOR_REPO_PATH"},
            {"id": "starling", "owner_role": "backend", "path_env": "STARLING_REPO_PATH"},
            {"id": "guides-ui-tests", "owner_role": "frontend_qa_automation", "path_env": "GUIDES_UI_TESTS_REPO_PATH"},
            {"id": "dxml-it-tests", "owner_role": "backend_qa_automation", "path_env": "DXML_IT_TESTS_REPO_PATH"},
        ],
        "focus_queries": ["Broken Links Report", "pagination"],
        "role_based_evidence_gates": [
            {"owner_role": "frontend", "primary_repo": "xmleditor", "automation_repo": "guides-ui-tests"},
            {"owner_role": "backend", "primary_repo": "starling", "automation_repo": "dxml-it-tests"},
        ],
    }
    result = collect_repository_evidence(
        issue={"summary": "Broken Links Report hangs for large map"},
        planning_seeds={"features": ["reports"]},
        repo_contract=repo_contract,
        max_matches=10,
    )

    assert result["repo_evidence_status"] == "complete"
    by_id = {repo["id"]: repo for repo in result["repositories"]}
    assert by_id["xmleditor"]["matches"][0]["evidence_type"] == "product_code"
    assert by_id["guides-ui-tests"]["matches"][0]["evidence_type"] in {"ui_test", "page_object"}
    assert all(gate["status"] == "complete" for gate in result["owner_gates"])


def test_collect_repository_evidence_reports_missing_clone(monkeypatch):
    monkeypatch.delenv("XML_EDITOR_REPO_PATH", raising=False)
    repo_contract = {
        "required_repositories": [
            {
                "id": "xmleditor",
                "owner_role": "frontend",
                "path_env": "XML_EDITOR_REPO_PATH",
                "fallback_path_hints": ["../xmleditor"],
            }
        ],
        "focus_queries": ["Broken Links Report"],
        "role_based_evidence_gates": [
            {"owner_role": "frontend", "primary_repo": "xmleditor", "automation_repo": ""},
        ],
    }
    result = collect_repository_evidence(
        issue={"summary": "Broken Links Report hangs"},
        planning_seeds={},
        repo_contract=repo_contract,
    )

    assert result["repo_evidence_status"] == "missing"
    assert result["repositories"][0]["available"] is False
    assert result["missing_evidence"]
