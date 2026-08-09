from __future__ import annotations

import hashlib
from datetime import datetime

from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.services.jira_uac_analysis_service import (
    HISTORICAL_UAC_CHUNK_TYPES,
    UAC_REFERENCE_CHUNK_TYPE,
    UAC_SCHEMA_VERSION,
    analyze_historical_uac,
    build_historical_uac_chunks,
    extract_explicit_root_cause_evidence,
    extract_explicit_test_evidence,
)
from app.services.jira_uac_backfill_service import build_sql_uac_rows


BASELINE_PREVIEW_UAC = """
Preview will show a baseline on/off switch in the filter panel.
Applicable for both new and old Baseline.
Applicable for Static baseline. Dynamic baseline not in scope of this ticket.
Only for map preview, not topics.
Show diff should be hidden, when baseline switch is on and baseline is selected.
Validate conditions
Verify direct and indirect references.
Applicable for both old and new editor.
In dynamic/static baseline, we should add loader, same as we click on author mode and get that.
Check performance impact. TBD
Switching between author/source/preview views, baseline selection and preview should be retained.
Check/Test for keys also
Handle/Test version purge as well - Version purge is not allowed for a version if it is present inside a baseline.
"""

MATHML_OUTPUTCLASS_UAC = """
*Feature Flag - No feature flag*
*Acceptance Criterion* :-
Mentioned with https://jira.corp.adobe.com/browse/GUIDES-22950
Verify complex MathML equation's
All crud operation's should work fine for mathML.
Output class and css[mentioned in class] should be applied on MathML.
"""

MATHML_EVIDENCE_COMMENT = """
QA verification:
Verified on build 2026.06.2315.
Output class is applied on the MathML row.
Preview foreign class and user-applied class propagate to Native PDF and merged HTML.

Analysis:
The outputclass of the MathML tag was dropped when the img node was replaced with the math node.
The source node had child elements, so the replacement logic changed to retain outputclass on the created span node.
"""

TOPICHEAD_OUTPUTCLASS_UAC = """
*Feature flag -* *No feature flag*
*Problem Statement:*
The outputclass attribute is not being propagated into mergedHTML.htm for topicgroup, topichead, and MathML elements.
*Acceptance Criteria:*
The outputclass attribute should be present in mergedHTML.htm for the following DITA elements:
topichead
MathML elements
topicgroup can be ignored, as it does not appear in the output (validated against DITA-OT HTML5 output).
No data or attributes should be lost in mergedHTML.htm. This must be validated through a diff comparison.
Validation should cover the following elements: MathML, video, audio, SVG, and foreign. Ensure that images are not broken.
For MathML-to-SVG conversion, the outputclass should be applied to the wrapping element.
*Out of Scope :-*
outputclass is dropped in Iframe tag too but we are not taking the fix for that in current sprint.
"""

TOPICHEAD_EVIDENCE_COMMENT = """
QA Verification:
Verified on build 2026.06.2314.
User-applied outputclass on topichead propagates to mergedHTML and is applied to the generated h1 element.
Video, audio, SVG, foreign, and image validation passed without broken images.

Analysis:
The outputclass of the tocObj was not considered when generating the corresponding HTML tags.
The generation logic was updated to carry the class to the emitted tag.
"""

MAP_TITLE_INLINE_CONTENT_UAC = """
Ph tag in map title or project title should resolve with ditaval conditioning in the pdf output.
Scope for Map title
Map Title- >Ph > conref, conkeyref, keyref (only ph->keyref and keyword->keyref/conref allowed)
Map title-> conref , conkeyref - N/A
TM symbol and inline styling in the title (italics, bold, etc.)
Applicable for Native PDF with dita-ot switch on/off. (content filtering will not work as we rely on dita-ot for ditaval)
Verify for ditavalref
Verify for Conditional presets.
Text decorations and <image> in map title
Metadata title should use text only map title
Out of scope:
topic title would not be picked up
Other elements in map title example video, object, etc.
"""

GUID_MOVE_BEFORE_SAVE_UAC = r"""
{}UAC{}-
1. Drag-drop from repository panel → GUID in source :
Drop a topic from the repository panel into an open ditamap. Inspect the source XML. The topicref href must be the file's GUID (e.g., GUID-...xxxxxx.dita), not a relative path like ../topics/foo.dita. [\\\{_}and scope should be local by default|file://\{_}and%20scope%20should%20be%20local%20by%20default/]{_}
2. Toolbar insert → GUID in source :
Insert a topicref via the toolbar → browse dialog → select a topic. Inspect the source XML. The href must be the file's GUID.
[ and scope should be local by default. ]
3. Toolbar insert or Drag-drop from repository panel: also insert GUID of the topic in the source but if the user updates scope to External, it will be updated to an absolute /content/dam/<path>. (NOT NEEDED AS DISCUSSED)
4. Move-before-save does not break the ref:
Drop/insert a topicref without saving the map. Move the referenced topic to a different folder. Save the map. Refresh the browser. The topic-ref must resolve correctly — not broken.
5. No spurious new GUID assigned to the topic:
After the above move-before-save sequence, the topic file itself must retain its original GUID. No new GUID should be minted.
6. If uuid property is true: only UUID will be inserted always in any case.
7. Both CKEditor and MarkupEditor
UAC points 1–5 must pass in both editors independently.
"""


TRANSLATION_V2_FIRST_RUN_UAC = """
We will be providing fix in v2 workflow for this ticket.
When config <name to be confirmed by dev> is turned on with v2, we will copy source language assets with source content to the translation language folders when translation is initiated for the first time.
When translation completes and assets are approved, these source content copies will get replaced with the translated content. (same like v1) All references point to translated assets only, should not have any unnecessary broken links.
No change in workflow when translation is initiated for 2nd time onwards- buffer copy made in translation_output folder
Following validations to work as is:
All map assets in lang folder
Map assets in lang folder and some referenced multimedia or topic refs in global folder: After 1st translation completes, all references are fixed and translated map should refer to the global asset
All reference types-> topics, multimedia, ditavalrefs (with flagging images), markdown, keyrefs etc should work as is
Asset created outside lang folder (will not have lang code in guid)-> move to en and referred in source map: Language copy created for this asset also in target folder and when translation completes, all guids will have lang code appended
Asset from lang folder moved to global folder (version bumped scenario also)
Multiple languages selected for translation: some already have insync files, some have missing copy -> english copy created only in missing copy languages, other language existing assets not affected, buffer copies created in translation output. -> translation completes, post approval> all assets updated accordingly i.e. insync assets will have new version, missing copy assets will have translated v1.0
When config is disabled, empty xml is created like before for 1st translation project-> 2nd or furthermore translation works as is
Following workflows to be covered:
machine translation
human translation
xliff translation
multi-lingual translation
with baseline
baseline export
label propagation
Should also work for projects created via v1/translation project create api: should also work when language folder is getting created in create call itself.
For related assets: Translated topic to not have any linking to the asset its source asset was related to. i.e.
topic1-en has <source> related to topic2-en
map1-en refers topic1-en
Translation completes
map1-fr refers to topic1-fr
topic1-fr has no link to topic2-en
no copy of topic2 created in fr
topic1 will not have any link information to any asset.

This above mentioned behavior of related assets to be validated in v1 and v2 translation both.
The config should not have any effect when v1 translation is enabled i.e. enable/disable of this config will not effect v1 workflow
More information awaited on status of tickets mentioned in comment: GUIDES-27772 and GUIDES-24152. These tickets are to be validated as well. Scope will be discussed and updated here.
"""

BASELINE_EXPORT_ASSET_MOVE_UAC = """
Move image/topicref from lang to global and baseline export should work
Move image/topicref back to lang from global and baseline export should work
Move an image having no lang code appended (i.e. asset created in global and then moved to lang) from lang to global and baseline export should work
Exported baseline should have correct version info as per version created after move.
Check for content moved/baseline created before upgrading the server
No changes in normal workflows for translation asset retrieval, acceptance, rejection, xliff, human and machine
"""


def test_human_uac_is_split_into_traceable_gaps_without_inference():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-10878",
        acceptance_criteria=BASELINE_PREVIEW_UAC,
        status="Open",
        labels=["UAC_Done"],
    )

    assert analysis is not None
    assert analysis.source_authority == "jira_accepted_uac"
    assert analysis.reuse_tier == "candidate"
    assert analysis.contract_complete is False
    assert analysis.performance_matters is True
    assert analysis.performance_contract_complete is False
    assert analysis.source_truncated is False
    assert len(analysis.out_of_scope_clauses) == 1
    assert "Dynamic baseline" in analysis.out_of_scope_clauses[0].text
    assert any("dynamic" in contradiction for contradiction in analysis.contradictions)

    reasons = {reason for clause in analysis.unresolved_clauses for reason in clause.unresolved_reasons}
    assert {
        "baseline_fixture_definition_missing",
        "missing_observable_outcome",
        "loader_lifecycle_missing",
        "performance_metric_missing",
        "performance_workload_missing",
    }.issubset(reasons)


def test_mathml_uac_separates_reference_and_finds_automation_blocking_gaps():
    root_cause, root_source = extract_explicit_root_cause_evidence(
        comment_documents=[MATHML_EVIDENCE_COMMENT]
    )
    test_evidence, test_source = extract_explicit_test_evidence(
        comment_documents=[MATHML_EVIDENCE_COMMENT]
    )
    analysis = analyze_historical_uac(
        jira_key="GUIDES-44393",
        acceptance_criteria=MATHML_OUTPUTCLASS_UAC,
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done", "Emerson"],
        root_cause=root_cause,
        test_evidence=test_evidence,
        root_cause_source=root_source,
        test_evidence_source=test_source,
    )

    assert analysis is not None
    assert all(clause.text != "Acceptance Criterion:" for clause in analysis.clauses)
    assert analysis.reference_clauses[0].source_id == "REF-01"
    assert "GUIDES-22950" in analysis.reference_clauses[0].text
    assert analysis.explicit_root_cause is True
    assert analysis.explicit_test_evidence is True
    assert analysis.root_cause_source == "jira_comment_explicit_analysis"
    assert analysis.test_evidence_source == "jira_comment_qa_verification"
    assert analysis.contract_complete is False
    assert analysis.reuse_tier == "supporting"

    feature_flag = next(clause for clause in analysis.in_scope_clauses if "Feature Flag" in clause.text)
    complex_mathml = next(clause for clause in analysis.in_scope_clauses if "complex MathML" in clause.text)
    crud = next(clause for clause in analysis.in_scope_clauses if "crud" in clause.text.casefold())
    styling = next(clause for clause in analysis.in_scope_clauses if "Output class" in clause.text)
    assert feature_flag.unresolved_reasons == ()
    assert "complex_fixture_definition_missing" in complex_mathml.unresolved_reasons
    assert "generic_success_outcome" in crud.unresolved_reasons
    assert "crud_operation_matrix_missing" in crud.unresolved_reasons
    assert "output_target_matrix_missing" in styling.unresolved_reasons
    assert {"mathml", "styling", "authoring_crud", "feature_flag", "jira_reference"}.issubset(
        set(analysis.dimensions)
    )
    chunks = build_historical_uac_chunks(analysis)
    reference_chunk = next(chunk for chunk in chunks if chunk["chunk_type"] == UAC_REFERENCE_CHUNK_TYPE)
    assert reference_chunk["uac_clause_kind"] == "reference"
    assert reference_chunk["uac_root_cause_source"] == "jira_comment_explicit_analysis"
    assert reference_chunk["uac_test_evidence_source"] == "jira_comment_qa_verification"


def test_topichead_outputclass_uac_preserves_context_matrix_and_iframe_exclusion():
    root_cause, root_source = extract_explicit_root_cause_evidence(
        comment_documents=[TOPICHEAD_EVIDENCE_COMMENT]
    )
    test_evidence, test_source = extract_explicit_test_evidence(
        comment_documents=[TOPICHEAD_EVIDENCE_COMMENT]
    )
    analysis = analyze_historical_uac(
        jira_key="GUIDES-22950",
        acceptance_criteria=TOPICHEAD_OUTPUTCLASS_UAC,
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done"],
        root_cause=root_cause,
        test_evidence=test_evidence,
        root_cause_source=root_source,
        test_evidence_source=test_source,
    )

    assert analysis is not None
    assert analysis.contract_complete is True
    assert analysis.reuse_tier == "historical_verified"
    assert analysis.contradictions == ()
    assert analysis.unresolved_clauses == ()
    assert analysis.context_clauses[0].source_id == "CTX-01"
    assert "not being propagated" in analysis.context_clauses[0].text
    assert len(analysis.in_scope_clauses) == 8
    assert "topichead, MathML elements" in analysis.in_scope_clauses[1].text
    assert analysis.out_of_scope_clauses[0].source_id == "OOS-01"
    assert "Iframe" in analysis.out_of_scope_clauses[0].text
    assert {"merged_html", "dita_structure", "multimedia", "svg", "foreign", "image_integrity"}.issubset(
        set(analysis.dimensions)
    )
    chunks = build_historical_uac_chunks(analysis)
    assert any(chunk["chunk_type"] == "historical_uac_context_chunk" for chunk in chunks)
    assert all(chunk["uac_reuse_tier"] == "historical_verified" for chunk in chunks)


def test_map_title_inline_content_uac_preserves_dita_matrix_and_ambiguities():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-28832",
        acceptance_criteria=MAP_TITLE_INLINE_CONTENT_UAC,
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done", "IBM", "Emerson"],
    )

    assert analysis is not None
    assert analysis.source_authority == "jira_accepted_uac"
    assert analysis.contract_complete is False
    assert analysis.reuse_tier == "supporting"
    assert analysis.contradictions == ()
    assert len(analysis.out_of_scope_clauses) == 2
    assert "topic title" in analysis.out_of_scope_clauses[0].text
    assert "video, object" in analysis.out_of_scope_clauses[1].text

    first_clause = analysis.in_scope_clauses[0]
    not_applicable = next(clause for clause in analysis.in_scope_clauses if "N/A" in clause.text)
    styling = next(clause for clause in analysis.in_scope_clauses if "TM symbol" in clause.text)
    dita_ot = next(clause for clause in analysis.in_scope_clauses if "switch on/off" in clause.text)
    ditavalref = next(clause for clause in analysis.in_scope_clauses if "ditavalref" in clause.text)
    image = next(clause for clause in analysis.in_scope_clauses if "<image>" in clause.text)
    assert "scope_target_mismatch" in first_clause.unresolved_reasons
    assert not_applicable.unresolved_reasons == ()
    assert {"not_applicable", "negative", "map_title", "references", "keys"}.issubset(
        set(not_applicable.dimensions)
    )
    assert "missing_observable_outcome" in styling.unresolved_reasons
    assert "configuration_state_outcome_mapping_missing" in dita_ot.unresolved_reasons
    assert "missing_observable_outcome" in ditavalref.unresolved_reasons
    assert "missing_observable_outcome" in image.unresolved_reasons
    assert {
        "conditional_preset",
        "dita_image",
        "dita_object",
        "dita_ot",
        "dita_ph",
        "ditavalref",
        "inline_styling",
        "map_title",
        "metadata_title",
        "native_pdf",
        "project_title",
        "topic_title",
        "trademark",
    }.issubset(set(analysis.dimensions))


def test_dita_ot_state_matrix_accepts_explicit_state_specific_limitations():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-31101",
        acceptance_criteria="""
Scope: Native PDF
Title text must render with DITA-OT enabled and disabled.
Ditaval filtering is only supported with DITA-OT enabled.
""",
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done"],
    )

    assert analysis is not None
    assert analysis.contract_complete is True
    assert all(
        "configuration_state_outcome_mapping_missing" not in clause.unresolved_reasons
        for clause in analysis.in_scope_clauses
    )


def test_guid_move_before_save_uac_groups_numbered_flows_and_scope_boundaries():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-47467",
        acceptance_criteria=GUID_MOVE_BEFORE_SAVE_UAC,
        status="Review",
        resolution="",
        labels=["UAC_Done", "Kone"],
    )

    assert analysis is not None
    assert analysis.reuse_tier == "candidate"
    assert analysis.contract_complete is False
    assert analysis.contradictions == ()
    assert len(analysis.in_scope_clauses) == 6
    assert len(analysis.out_of_scope_clauses) == 1
    assert "External" in analysis.out_of_scope_clauses[0].text
    assert "/content/dam/<path>" in analysis.out_of_scope_clauses[0].text

    drag_drop = analysis.in_scope_clauses[0]
    toolbar = analysis.in_scope_clauses[1]
    move_before_save = analysis.in_scope_clauses[2]
    guid_identity = analysis.in_scope_clauses[3]
    uuid_property = analysis.in_scope_clauses[4]
    editor_parity = analysis.in_scope_clauses[5]
    assert drag_drop.unresolved_reasons == ()
    assert "topicref href must be the file's GUID" in drag_drop.text
    assert "scope should be local by default" in drag_drop.text
    assert "file://" not in drag_drop.text
    assert "{_}" not in drag_drop.text
    assert toolbar.unresolved_reasons == ()
    assert move_before_save.unresolved_reasons == ()
    assert "must resolve correctly" in move_before_save.text
    assert guid_identity.unresolved_reasons == ()
    assert "original GUID" in guid_identity.text
    assert uuid_property.unresolved_reasons == ("uuid_false_state_behavior_missing",)
    assert editor_parity.unresolved_reasons == ("range_includes_out_of_scope_point",)
    assert {
        "absolute_dam_path",
        "ckeditor",
        "ditamap",
        "editor_parity",
        "external_scope",
        "guid_identity",
        "guid_reference",
        "local_scope",
        "markup_editor",
        "move_before_save",
        "reference_integrity",
        "repository_drag_drop",
        "scope_attribute",
        "source_xml",
        "toolbar_insert",
        "topicref",
        "uuid_property",
    }.issubset(set(analysis.dimensions))


def test_translation_v2_uac_preserves_first_run_state_and_reference_matrices():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-42745",
        acceptance_criteria=TRANSLATION_V2_FIRST_RUN_UAC,
        status="Open",
        resolution="",
        labels=["UAC_Done", "ExampleCustomer"],
    )

    assert analysis is not None
    assert analysis.source_authority == "jira_accepted_uac"
    assert analysis.reuse_tier == "candidate"
    assert analysis.contract_complete is False
    assert analysis.contradictions == ()
    assert len(analysis.context_clauses) == 1
    assert len(analysis.in_scope_clauses) == 15
    assert len(analysis.reference_clauses) == 1
    assert "v2 workflow" in analysis.context_clauses[0].text

    config_enabled = next(
        clause for clause in analysis.in_scope_clauses if "name to be confirmed" in clause.text
    )
    references = next(
        clause for clause in analysis.in_scope_clauses if "All reference types" in clause.text
    )
    global_move = next(
        clause for clause in analysis.in_scope_clauses if "version bumped scenario" in clause.text
    )
    config_disabled = next(
        clause for clause in analysis.in_scope_clauses if "config is disabled" in clause.text
    )
    workflow_matrix = next(
        clause for clause in analysis.in_scope_clauses if "Following workflows" in clause.text
    )
    project_api = next(
        clause for clause in analysis.in_scope_clauses if "project create api" in clause.text
    )
    related_assets = next(
        clause for clause in analysis.in_scope_clauses if "topic1-fr has no link" in clause.text
    )
    parity = next(
        clause for clause in analysis.in_scope_clauses if "validated in v1 and v2" in clause.text
    )
    v1_unchanged = next(
        clause for clause in analysis.in_scope_clauses if "effect when v1" in clause.text
    )

    assert config_enabled.unresolved_reasons == ("tbd_marker",)
    assert {
        "config_placeholder",
        "source_language_copy",
        "target_language_folder",
        "translation_first_run",
        "translation_v2",
    }.issubset(set(config_enabled.dimensions))
    assert references.unresolved_reasons == ("generic_success_outcome",)
    assert {"ditavalref", "keys", "markdown", "multimedia"}.issubset(
        set(references.dimensions)
    )
    assert global_move.unresolved_reasons == ("missing_observable_outcome",)
    assert config_disabled.unresolved_reasons == ("generic_success_outcome",)
    assert workflow_matrix.unresolved_reasons == ()
    assert {
        "baseline_translation",
        "label_propagation",
        "multilingual_translation",
        "translation_workflow_matrix",
    }.issubset(set(workflow_matrix.dimensions))
    assert project_api.unresolved_reasons == ("generic_success_outcome",)
    assert related_assets.unresolved_reasons == ()
    assert "no copy of topic2 created in fr" in related_assets.text
    assert "topic1 will not have any link information" in related_assets.text
    assert parity.unresolved_reasons == ()
    assert "translation_parity_matrix" in parity.dimensions
    assert v1_unchanged.unresolved_reasons == ()
    assert "GUIDES-27772" in analysis.reference_clauses[0].text
    assert "GUIDES-24152" in analysis.reference_clauses[0].text


def test_baseline_export_asset_move_uac_requires_exact_export_and_upgrade_oracles():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-39394",
        acceptance_criteria=BASELINE_EXPORT_ASSET_MOVE_UAC,
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done", "ExampleCustomer"],
    )

    assert analysis is not None
    assert analysis.source_authority == "jira_accepted_uac"
    assert analysis.reuse_tier == "supporting"
    assert analysis.contract_complete is False
    assert analysis.contradictions == ()
    assert len(analysis.in_scope_clauses) == 6

    lang_to_global = analysis.in_scope_clauses[0]
    global_to_lang = analysis.in_scope_clauses[1]
    no_language_code = analysis.in_scope_clauses[2]
    version_info = analysis.in_scope_clauses[3]
    upgrade = analysis.in_scope_clauses[4]
    workflow_parity = analysis.in_scope_clauses[5]

    assert lang_to_global.unresolved_reasons == ("generic_success_outcome",)
    assert {"baseline_export", "move_lang_to_global", "topicref"}.issubset(
        set(lang_to_global.dimensions)
    )
    assert global_to_lang.unresolved_reasons == ("generic_success_outcome",)
    assert {"baseline_export", "move_global_to_lang", "topicref"}.issubset(
        set(global_to_lang.dimensions)
    )
    assert no_language_code.unresolved_reasons == ("generic_success_outcome",)
    assert {
        "asset_language_code",
        "move_global_to_lang",
        "move_lang_to_global",
    }.issubset(set(no_language_code.dimensions))
    assert version_info.unresolved_reasons == ()
    assert {"baseline_export", "versioning"}.issubset(set(version_info.dimensions))
    assert upgrade.unresolved_reasons == ("missing_observable_outcome",)
    assert "upgrade_compatibility" in upgrade.dimensions
    assert workflow_parity.unresolved_reasons == ("generic_success_outcome",)
    assert {
        "translation_acceptance",
        "translation_asset_retrieval",
        "translation_rejection",
        "translation_workflow",
    }.issubset(set(workflow_parity.dimensions))


def test_reuse_tier_requires_fixed_complete_uac_root_cause_and_test_evidence():
    complete_uac = """
Scope: Native PDF
Map-level related links must render before topic-level related links.
Broken related links must remain visible as entries matching AEM Sites behavior.
Default output must omit related links unless -Dargs.rellinks=nofamily is configured.
Out of scope:
HTML5 output is excluded.
"""
    verified = analyze_historical_uac(
        jira_key="GUIDES-38333",
        acceptance_criteria=complete_uac,
        status="Closed",
        resolution="Fixed",
        root_cause="The Native PDF transform omitted reltable links.",
        test_evidence="Generate Native PDF with the flag and verify link ordering.",
    )
    supporting = analyze_historical_uac(
        jira_key="GUIDES-38334",
        acceptance_criteria=complete_uac,
        status="Closed",
        resolution="Fixed",
    )
    caution = analyze_historical_uac(
        jira_key="GUIDES-38335",
        acceptance_criteria=complete_uac,
        status="Closed",
        resolution="Question Answered",
        root_cause="Not applicable.",
        test_evidence="Reviewed manually.",
    )

    assert verified is not None and verified.contract_complete is True
    assert verified.reuse_tier == "historical_verified"
    assert supporting is not None and supporting.reuse_tier == "supporting"
    assert caution is not None and caution.reuse_tier == "candidate"


def test_unspecified_resolution_does_not_make_an_open_issue_closed():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-40001",
        acceptance_criteria="Generated output must retain the selected baseline version.",
        status="Open",
        resolution="Unspecified",
    )

    assert analysis is not None
    assert analysis.issue_closed is False


def test_more_than_two_hundred_unique_clauses_is_explicitly_incomplete():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-40002",
        acceptance_criteria="\n".join(
            f"Requirement {index:03d} must retain its configured value." for index in range(205)
        ),
        status="Closed",
        resolution="Fixed",
        root_cause="A stale cache was used.",
        test_evidence="Validate every configured value.",
    )

    assert analysis is not None
    assert len(analysis.clauses) == 200
    assert analysis.source_truncated is True
    assert analysis.contract_complete is False
    assert analysis.reuse_tier == "supporting"
    contract = build_historical_uac_chunks(analysis)[0]
    assert contract["uac_source_truncated"] is True
    assert "cannot be reused" in contract["chunk_text"]


def test_analysis_and_chunks_are_deterministic_and_never_llm_generated():
    first = analyze_historical_uac(
        jira_key="GUIDES-40000",
        acceptance_criteria="Generated output must retain the selected baseline version.",
        status="Closed",
        resolution="Fixed",
    )
    second = analyze_historical_uac(
        jira_key="GUIDES-40000",
        acceptance_criteria="Generated output must retain the selected baseline version.",
        status="Closed",
        resolution="Fixed",
    )

    assert first is not None and second is not None
    assert first.source_hash == second.source_hash
    assert [clause.stable_key for clause in first.clauses] == [clause.stable_key for clause in second.clauses]
    chunks = build_historical_uac_chunks(first)
    assert {chunk["chunk_type"] for chunk in chunks}.issubset(HISTORICAL_UAC_CHUNK_TYPES)
    assert all(chunk["uac_schema_version"] == UAC_SCHEMA_VERSION for chunk in chunks)
    assert all(chunk["uac_llm_used"] is False for chunk in chunks)


def test_sql_backfill_recovers_full_uac_from_description_not_truncated_chunk():
    full_uac = "\n".join(
        [f"Requirement {index:03d} must retain the selected baseline metadata value." for index in range(90)]
        + ["The final metadata version must remain pinned to the baseline."]
    )
    issue = JiraEnrichedIssue(
        id=1,
        jira_key="GUIDES-42952",
        summary="AEM Sites baseline metadata",
        description=f"Issue details.\n\n## UAC Criteria (custom field)\n{full_uac}",
        issue_type="Customer Request",
        status="Closed",
        priority="Critical",
        resolution="Fixed",
        jira_updated_at=datetime(2026, 8, 1, 10, 0, 0),
        source_type="jira_csv",
        labels=["UAC_Done"],
        components=["Publishing"],
        customer_names=["Example Customer"],
        domain="publishing",
        affected_outputs=["AEM Sites"],
        dita_entities=["ditamap"],
        qa_risk_tags=["regression"],
        raw_text="",
        customer_detection_debug={},
    )
    truncated = JiraIssueChunk(
        jira_key=issue.jira_key,
        chunk_type="acceptance_criteria_chunk",
        chunk_text="Acceptance criteria:\n" + full_uac[:4000],
    )

    built = build_sql_uac_rows(issue, [truncated])

    assert built is not None
    analysis, rows = built
    assert analysis.source_hash == hashlib.sha256(full_uac.encode("utf-8")).hexdigest()
    assert any("final metadata version" in row["document"] for row in rows)
    assert {row["metadata"]["chunk_type"] for row in rows}.issubset(HISTORICAL_UAC_CHUNK_TYPES)
    assert all(row["metadata"]["uac_llm_used"] is False for row in rows)


def test_historical_uac_audit_endpoint_is_admin_only_and_returns_stats(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.jira_uac_backfill_service.backfill_historical_uac_chunks",
        lambda **kwargs: {
            "available": True,
            "valid": True,
            "dry_run": kwargs["dry_run"],
            "scan_complete": True,
            "issues_with_uac": 249,
            "planned_chunks": 1400,
        },
    )

    response = client.get(
        "/api/v1/admin/jira-rag/uac-chunks/audit?source_type=jira_csv&page_size=100",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert response.json()["issues_with_uac"] == 249
