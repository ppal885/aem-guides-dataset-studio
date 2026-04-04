import asyncio

from app.services.smart_suggestions_service import analyse_content, apply_fix


def test_smart_suggestions_are_issue_and_research_aware():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "technicalContent/dtd/concept.dtd">
<concept id="circleci_job">
  <title>Add 2nd-gen a11y test job to CircleCI</title>
  <shortdesc>This topic describes the bug.</shortdesc>
  <conbody>
    <p>Expected result: the job works.</p>
  </conbody>
</concept>"""
    issue = {
        "issue_key": "AUTH-44",
        "summary": "Add 2nd-gen a11y test job to CircleCI",
        "description": "Document the second-generation accessibility job in CircleCI for AEM Guides.",
        "issue_type": "Story",
        "components": ["CircleCI"],
        "labels": ["concept", "accessibility"],
    }
    research_context = {
        "results": [
            {
                "summary": "CircleCI guidance for AEM Guides 4.2 mentions the second-generation accessibility job.",
                "chunks": ["Applies to AEM Guides 4.2 and CircleCI pipeline configuration."],
                "urls": ["https://example.com/circleci"],
            }
        ]
    }
    validation = [{"label": "xml:lang present", "passing": False}]

    report = asyncio.run(
        analyse_content(
            xml=xml,
            issue=issue,
            tenant_id="kone",
            research_context=research_context,
            validation=validation,
        )
    )

    rule_ids = {item.rule_id for item in report.suggestions}
    assert "title_work_item_jargon" in rule_ids
    assert "bug_report_language" in rule_ids
    assert "research_version_note" in rule_ids
    assert "validation_xml_lang" in rule_ids


def test_apply_fix_handles_title_and_xml_lang_rules_without_llm():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "technicalContent/dtd/concept.dtd">
<concept id="circleci_job">
  <title>Add 2nd-gen a11y test job to CircleCI</title>
  <shortdesc>Accessibility job overview.</shortdesc>
  <conbody>
    <p>Details.</p>
  </conbody>
</concept>"""

    updated_title = asyncio.run(
        apply_fix(
            xml=xml,
            suggestion={
                "rule_id": "title_work_item_jargon",
                "after": "2nd-Gen A11y Test Job To CircleCI",
                "title": "Title reads like a Jira work item",
            },
            issue={},
            tenant_id="kone",
        )
    )
    assert "<title>2nd-Gen A11y Test Job To CircleCI</title>" in updated_title

    updated_lang = asyncio.run(
        apply_fix(
            xml=updated_title,
            suggestion={
                "rule_id": "validation_xml_lang",
                "after": 'Add xml:lang="en-US" to the root element.',
                "title": "Missing xml:lang",
            },
            issue={},
            tenant_id="kone",
        )
    )
    assert '<concept id="circleci_job" xml:lang="en-US">' in updated_lang


def test_low_quality_breakdown_produces_gap_suggestions():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">
<task id="guides_34724" xml:lang="en-US">
  <title>Resolve context highlighting on hover</title>
  <shortdesc>Resolve the context highlighting issue on hover in AEM Guides.</shortdesc>
  <prolog>
    <metadata>
      <othermeta name="jira-key" content="GUIDES-34724"/>
    </metadata>
  </prolog>
  <taskbody>
    <context>
      <p>Use this task when context content does not highlight on hover.</p>
    </context>
    <steps>
      <step><cmd>Update the hover styling.</cmd></step>
      <step><cmd>Verify the hover behavior.</cmd></step>
    </steps>
    <result>
      <p>The context highlights correctly on hover.</p>
    </result>
  </taskbody>
</task>"""
    issue = {
        "issue_key": "GUIDES-34724",
        "summary": "Context not getting highlighted on hovering the context",
        "description": "Please find the video attached.",
        "issue_type": "Bug",
        "components": ["Authoring"],
        "labels": [],
        "attachments": [{"is_video": True, "filename": "hover.mov"}],
    }
    research_context = {
        "results": [
            {
                "summary": "Experience League explains hover-state authoring behavior.",
                "chunks": ["Use an external reference when linking the supporting guidance."],
                "urls": ["https://experienceleague.adobe.com/example"],
            }
        ]
    }

    report = asyncio.run(
        analyse_content(
            xml=xml,
            issue=issue,
            tenant_id="kone",
            research_context=research_context,
            validation=[],
            quality_breakdown={
                "structure": 30,
                "content_richness": 5,
                "dita_features": 0,
                "aem_readiness": 20,
            },
        )
    )

    rule_ids = {item.rule_id for item in report.suggestions}
    assert "quality_add_example" in rule_ids
    assert "quality_add_xref" in rule_ids
    assert "quality_add_media_object" in rule_ids


def test_apply_fix_handles_quality_gap_rules_without_llm():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">
<task id="guides_34724" xml:lang="en-US">
  <title>Resolve context highlighting on hover</title>
  <shortdesc>Resolve the context highlighting issue on hover in AEM Guides.</shortdesc>
  <taskbody>
    <context><p>Use this task to resolve the hover issue.</p></context>
    <steps><step><cmd>Update the hover styling.</cmd></step></steps>
    <result><p>The context highlights correctly on hover.</p></result>
  </taskbody>
</task>"""

    updated_example = asyncio.run(
        apply_fix(
            xml=xml,
            suggestion={
                "rule_id": "quality_add_example",
                "after": "Add an example.",
                "title": "Add a concrete example",
            },
            issue={},
            tenant_id="kone",
        )
    )
    assert "<example>" in updated_example

    updated_xref = asyncio.run(
        apply_fix(
            xml=updated_example,
            suggestion={
                "rule_id": "quality_add_xref",
                "after": 'Add an xref to the supporting guidance: <xref href="https://example.com/help" scope="external" format="html">Related guidance</xref>.',
                "title": "Add an xref",
            },
            issue={},
            tenant_id="kone",
        )
    )
    assert '<xref href="https://example.com/help" scope="external" format="html">Related guidance</xref>' in updated_xref


def test_reuse_suggestions_cover_conref_keyref_keywords_and_topic_reuse():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">
<task id="guides_34724" xml:lang="en-US">
  <title>Resolve context highlighting on hover in AEM Guides</title>
  <shortdesc>Resolve the context highlighting issue on hover in AEM Guides.</shortdesc>
  <taskbody>
    <context><p>Use this task when AEM Guides highlights the wrong context on hover.</p></context>
    <steps><step><cmd>Update the hover styling.</cmd></step></steps>
    <result><p>The context highlights correctly on hover.</p></result>
  </taskbody>
</task>"""
    issue = {
        "issue_key": "GUIDES-34724",
        "summary": "Resolve context highlighting on hover in AEM Guides",
        "description": "Make the topic reusable across related authoring fixes.",
        "issue_type": "Bug",
        "components": ["AEM Guides", "Authoring"],
        "labels": ["hover", "highlighting"],
    }

    report = asyncio.run(
        analyse_content(
            xml=xml,
            issue=issue,
            tenant_id="kone",
            validation=[],
            quality_breakdown={
                "structure": 28,
                "content_richness": 8,
                "dita_features": 4,
                "aem_readiness": 18,
            },
        )
    )

    rule_ids = {item.rule_id for item in report.suggestions}
    assert "reuse_title_conref" in rule_ids
    assert "reuse_add_keywords" in rule_ids
    assert "reuse_add_keyref" in rule_ids
    assert "reuse_add_conkeyref" in rule_ids


def test_apply_fix_handles_reuse_rules_without_llm():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">
<task id="guides_34724" xml:lang="en-US">
  <title>Resolve context highlighting on hover in AEM Guides</title>
  <shortdesc>Resolve the context highlighting issue on hover in AEM Guides.</shortdesc>
  <taskbody>
    <context><p>Use this task when AEM Guides highlights the wrong context on hover.</p></context>
    <steps><step><cmd>Update the hover styling.</cmd></step></steps>
    <result><p>The context highlights correctly on hover.</p></result>
  </taskbody>
</task>"""
    issue = {
        "summary": "Resolve context highlighting on hover in AEM Guides",
        "components": ["AEM Guides", "Authoring"],
        "labels": ["hover", "highlighting"],
    }

    updated_title = asyncio.run(
        apply_fix(
            xml=xml,
            suggestion={"rule_id": "reuse_title_conref", "after": "Add reusable title conref."},
            issue=issue,
            tenant_id="kone",
        )
    )
    assert 'conref="reuse/reusable-titles.dita#reusable_titles/resolve-context-highlighting-on-hover-in-aem-guides"' in updated_title

    updated_keywords = asyncio.run(
        apply_fix(
            xml=updated_title,
            suggestion={"rule_id": "reuse_add_keywords", "after": "Add reusable keywords metadata."},
            issue=issue,
            tenant_id="kone",
        )
    )
    assert "<keywords>" in updated_keywords
    assert "<keyword>AEM Guides</keyword>" in updated_keywords

    updated_keyref = asyncio.run(
        apply_fix(
            xml=updated_keywords,
            suggestion={"rule_id": "reuse_add_keyref", "after": "Add keyref-backed product naming."},
            issue=issue,
            tenant_id="kone",
        )
    )
    assert 'keyref="aem-guides"' in updated_keyref

    updated_conkeyref = asyncio.run(
        apply_fix(
            xml=updated_keyref,
            suggestion={"rule_id": "reuse_add_conkeyref", "after": "Add reusable conkeyref block."},
            issue=issue,
            tenant_id="kone",
        )
    )
    assert 'conkeyref="reuse/reusable-blocks/resolve-context-highlighting-on-hover-in-aem-guides-verification"' in updated_conkeyref
