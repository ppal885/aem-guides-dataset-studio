from app.services.evidence_graph_contract import (
    EDGE_PROPERTY_ALLOWLIST,
    NODE_TYPES,
    RELATIONS,
    RELATION_ENDPOINT_TYPES,
    canonical_url,
    contains_sensitive_text,
    deterministic_id,
    exact_source_claim,
    extract_api_routes,
    extract_config_keys,
    extract_error_signatures,
    normalize_text,
    normalized_token,
    relation_endpoint_allowed,
    sanitize_excerpt,
    sanitize_structured_properties,
    stable_key,
)


def test_stable_keys_and_ids_are_deterministic_and_canonical():
    assert stable_key("jira_issue", " guides-123 ") == "jira:GUIDES-123"
    assert stable_key("component", "New Editor") == "component:new-editor"
    assert stable_key("customer", "  KONE  ") == "customer:kone"
    assert stable_key("output", "Native PDF") == "output:native-pdf"
    assert stable_key("dita_element", "xref") == "dita-element:xref"
    assert stable_key("dita_attribute", "scope") == "dita-attribute:scope"
    assert stable_key("release", "cloud:2025.02.0") == "release:cloud:2025.02.0"
    assert stable_key("documentation_page", "HTTPS://EXAMPLE.COM/a//b/?x=1#f") == stable_key(
        "documentation_page", "https://example.com/a/b"
    )
    assert deterministic_id("generation", "node", "jira:GUIDES-123") == deterministic_id(
        "generation", "node", "jira:GUIDES-123"
    )


def test_normalization_contract_and_allowlists_are_closed():
    assert normalize_text("  one\n\ttwo  ") == "one two"
    assert normalized_token(" Native PDF / PDF2 ") == "native-pdf-pdf2"
    assert canonical_url("HTTPS://Example.COM//docs/item/?q=secret#fragment") == "https://example.com/docs/item"
    assert "jira_issue" in NODE_TYPES
    assert "HAS_ROOT_CAUSE" in RELATIONS
    assert "random_relation" not in RELATIONS
    assert "requires_live_jira_validation" in EDGE_PROPERTY_ALLOWLIST
    assert frozenset(RELATION_ENDPOINT_TYPES) == RELATIONS
    assert relation_endpoint_allowed("HAS_ROOT_CAUSE", "jira_issue", "root_cause")
    assert not relation_endpoint_allowed("HAS_ROOT_CAUSE", "jira_issue", "component")
    assert not relation_endpoint_allowed("HAS_ROOT_CAUSE", "root_cause", "jira_issue")


def test_redaction_removes_identity_and_secret_material():
    excerpt, count = sanitize_excerpt(
        "Contact User.Name@example.com [~accountid:abc] password=hunter2 "
        "Bearer abcdefghijklmnop 0123456789ABCDEF01234567@AdobeOrg"
    )
    assert count == 5
    assert "example.com" not in excerpt
    assert "hunter2" not in excerpt
    assert "abcdefghijklmnop" not in excerpt
    assert "accountid" not in excerpt
    assert not contains_sensitive_text(excerpt)


def test_property_sanitizer_drops_unapproved_fields_and_redacts_strings():
    clean, redactions = sanitize_structured_properties(
        "jira_issue",
        {
            "jira_key": "GUIDES-1",
            "status": "Assigned to qa@example.com",
            "description": "must never be stored",
            "priority": "P1",
            "mutable_facts_require_live_validation": True,
        },
    )
    assert clean == {
        "jira_key": "GUIDES-1",
        "status": "Assigned to [redacted-email]",
        "priority": "P1",
        "mutable_facts_require_live_validation": True,
    }
    assert redactions == 1


def test_exact_source_containment_and_structural_extractors():
    source = (
        "The editor preserves the external xref when scope is external. "
        "POST /bin/fmdita/config/snippets can return HTTP 403 or IllegalStateException. "
        "Set AEM_GUIDES_TIMEOUT and guides.output.enabled."
    )
    assert exact_source_claim("preserves the external xref when scope is external", source)
    assert not exact_source_claim("the editor silently repairs invalid links", source)
    assert extract_api_routes(source) == ["/bin/fmdita/config/snippets"]
    assert extract_error_signatures(source) == ["HTTP 403", "IllegalStateException"]
    assert extract_config_keys(source) == ["AEM_GUIDES_TIMEOUT", "guides.output.enabled"]
