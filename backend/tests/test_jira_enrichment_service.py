"""Unit tests for Jira enrichment pipeline (pure functions + enrich_jira)."""

from __future__ import annotations

from app.services.jira_enrichment_service import (
    CUSTOMER_LABEL_EXCLUDE_PATTERNS,
    classify_domain,
    detect_customers,
    detect_customers_dynamic,
    detect_customers_dynamic_with_debug,
    enrich_jira,
    extract_dita_entities,
    extract_expected_actual,
)


def test_classify_domain_native_pdf():
    r = classify_domain("Native PDF output fails for bookmap with keyrefs", [])
    assert r["domain"] == "native_pdf"


def test_classify_domain_keyref_over_publishing():
    r = classify_domain("keyref does not resolve in web editor preview", [])
    assert r["domain"] == "keyref"


def test_classify_domain_unknown():
    r = classify_domain("nothing specific here", [])
    assert r["domain"] == "unknown"


def test_extract_dita_entities_order_unique():
    t = "Use conref and keyref in topicref; also mapref to bookmap with glossentry."
    got = extract_dita_entities(t)
    assert "conref" in got
    assert "keyref" in got
    assert "topicref" in got
    assert got == list(dict.fromkeys(got))


def test_detect_customers_labels_and_text():
    assert detect_customers("Escalation for Cisco router team", ["Topcon", "noise"]) == ["Cisco", "Topcon"]
    assert detect_customers("", ["ABS", "swift"]) == ["ABS", "Swift"]


def test_extract_expected_actual():
    body = """Steps:
1. Open map

Expected: PDF generates
Actual: Error 500 from publish servlet
"""
    d = extract_expected_actual(body)
    assert "PDF" in d["expected_behavior"] or "generates" in d["expected_behavior"].lower()
    assert "500" in d["actual_behavior"] or "error" in d["actual_behavior"].lower()


def test_enrich_jira_round_trip_jsonable():
    issue = {
        "key": "GUIDES-42",
        "fields": {
            "summary": "Baseline compare fails for Native PDF",
            "description": "Expected: same output\nActual: UUID mismatch in metadata\nconref to glossary broken",
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
            "priority": {"name": "Major"},
            "labels": ["cisco", "native-pdf"],
            "components": [{"name": "Publishing"}],
            "updated": "2024-01-01T00:00:00.000+0000",
        },
    }
    doc = enrich_jira(issue)
    assert doc.jira_key == "GUIDES-42"
    assert doc.domain in (
        "native_pdf",
        "baseline",
        "uuid",
        "metadata",
        "conref",
        "glossary",
        "publishing",
    )
    assert "Cisco" in doc.customer_names
    assert any(e.lower() == "conref" for e in doc.dita_entities)
    dumped = doc.model_dump()
    assert isinstance(dumped["labels"], list)
    assert dumped["automation_fit"]


def test_enrich_jira_performance_bson():
    issue = {
        "key": "GUIDES-99",
        "fields": {
            "summary": "BSONObj too large during asset update",
            "description": "Performance degrades; validatexml logs ReferenceListener errors",
            "issuetype": {"name": "Bug"},
            "status": {"name": "In Progress"},
            "priority": {"name": "Critical"},
            "labels": [],
            "components": [],
        },
    }
    doc = enrich_jira(issue)
    assert doc.domain == "performance"
    lowered = [e.lower() for e in doc.dita_entities]
    assert any("bson" in e for e in lowered)
    assert any("validatexml" in e for e in lowered)


def test_detect_customers_dynamic_prefixed_labels():
    issue = {
        "key": "X-1",
        "fields": {
            "summary": "PDF issue",
            "description": "",
            "labels": [
                "customer:Hyundai",
                "org:Lexmark",
                "cust:PwC",
                "customer-topcon",
                "account_ABS",
                "client=Swift",
            ],
        },
    }
    names = detect_customers_dynamic(issue)
    assert "Hyundai" in names
    assert "Lexmark" in names
    assert "PwC" in names
    assert "Topcon" in names
    assert "ABS" in names
    assert "Swift" in names
    assert "Customer-topcon" not in names


def test_detect_customers_technical_labels_excluded():
    issue = {
        "key": "X-2",
        "fields": {
            "summary": "test",
            "description": "",
            "labels": ["regression", "customer:ACME", "smoke"],
        },
    }
    names, dbg = detect_customers_dynamic_with_debug(issue)
    assert "ACME" in names
    assert "regression" in dbg["excluded_labels"] or "smoke" in dbg["excluded_labels"]


def test_detect_customers_does_not_promote_unhinted_summary_terms():
    issue = {
        "key": "X-TECH",
        "fields": {
            "summary": "Native PDF GlossStatus issue in Web Editor",
            "description": "Expected: output works. Actual: publishing warning.",
            "labels": ["native-publishing", "release", "hotfix", "keyref"],
        },
    }
    names = detect_customers_dynamic(issue)
    assert names == []


def test_detect_customers_normalize_pwc_mixed_case():
    issue = {
        "key": "X-3",
        "fields": {"summary": "Escalation from pWC on SSO", "description": "", "labels": []},
    }
    assert "PwC" in detect_customers_dynamic(issue)


def test_detect_customers_custom_account_field():
    issue = {
        "key": "X-4",
        "fields": {
            "summary": "Login",
            "description": "",
            "labels": [],
            "account": {"name": "topcon"},
        },
    }
    names = detect_customers_dynamic(issue)
    assert "Topcon" in names


def test_customer_exclude_patterns_fixture():
    assert "native_pdf" in CUSTOMER_LABEL_EXCLUDE_PATTERNS


def test_enrich_jira_customer_detection_debug_keys():
    issue = {
        "key": "GUIDES-1",
        "fields": {
            "summary": "Notes",
            "description": "",
            "labels": ["client:Swift"],
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
            "priority": {"name": "Major"},
            "components": [],
        },
    }
    doc = enrich_jira(issue)
    d = doc.customer_detection_debug
    assert set(d.keys()) == {"from_custom_fields", "from_labels", "excluded_labels", "final_customers"}
    assert "Swift" in doc.customer_names
    assert doc.enrichment_debug["customer_detection"]["final_customers"] == ["Swift"]
    assert "domain_classification" in doc.enrichment_debug
