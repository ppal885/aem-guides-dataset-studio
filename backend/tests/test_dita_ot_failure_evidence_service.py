from app.services.dita_ot_failure_evidence_service import build_dita_ot_failure_query


def test_build_dita_ot_failure_query_includes_transform_constructs_and_stderr():
    query = build_dita_ot_failure_query(
        prompt="Generate copy-to and chunk publishing corpus",
        formats=["pdf", "html5"],
        detected_constructs=["copy-to", "chunk"],
        publish={
            "pdf": {
                "ok": False,
                "stderr": "BUILD FAILED: unresolved conref target in temp map",
                "stdout": "",
            },
            "html5": {
                "ok": True,
                "stderr": "",
                "stdout": "BUILD SUCCESSFUL",
            },
        },
    )

    assert "DITA-OT publishing failure" in query
    assert "pdf, html5" in query
    assert "copy-to, chunk" in query
    assert "BUILD FAILED" in query
    assert "unresolved conref target" in query
