"""Tests for safe xref/conref recommendation helper (no invented hrefs)."""

from app.services.dita_link_recommendations import build_link_recommendations


def test_empty_xml_returns_empty():
    assert build_link_recommendations("") == []
    assert build_link_recommendations("   ") == []


def test_malformed_xml_returns_parse_recommendation():
    recs = build_link_recommendations("<task><unclosed>")
    assert recs
    assert recs[0].kind == "parse"
    assert recs[0].severity == "error"


def test_same_doc_xref_missing_target():
    xml = """<task id="t1"><title>T</title><taskbody><context><p>See <xref href="#missing-id"/>.</p></context></taskbody></task>"""
    recs = build_link_recommendations(xml)
    summaries = " ".join(r.summary for r in recs)
    assert "missing" in summaries.lower()


def test_empty_href_xref_warning():
    xml = """<task id="t1"><title>T</title><taskbody><context><p><xref href=""/></p></context></taskbody></task>"""
    recs = build_link_recommendations(xml)
    assert any(r.kind == "xref" and r.severity == "warning" for r in recs)


def test_cross_file_xref_info_only():
    xml = (
        '<task id="t1"><title>T</title><taskbody><context>'
        '<p><xref href="library/other.dita#topic"/></p></context></taskbody></task>'
    )
    recs = build_link_recommendations(xml)
    assert any(r.severity == "info" and "Cross-file" in r.summary for r in recs)


def test_deduplicates_repeated_same_summary():
    xml = (
        '<task id="t1"><title>T</title><taskbody><context>'
        '<p><xref href=""/><xref href=""/></p></context></taskbody></task>'
    )
    recs = build_link_recommendations(xml)
    assert len([r for r in recs if "Empty xref" in r.summary]) <= 1
