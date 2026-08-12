from __future__ import annotations

import hashlib
from datetime import datetime

from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.services.jira_uac_analysis_service import (
    HISTORICAL_UAC_CHUNK_TYPES,
    UAC_CLAUSE_CHUNK_TYPE,
    UAC_CONTEXT_CHUNK_TYPE,
    UAC_REFERENCE_CHUNK_TYPE,
    UAC_SCHEMA_VERSION,
    analyze_historical_uac,
    build_historical_uac_chunks,
    extract_comment_accepted_uac,
    extract_explicit_root_cause_evidence,
    extract_explicit_test_evidence,
    extract_release_scope_evidence,
    historical_uac_contract_dict,
    is_no_uac_sentinel,
    resolve_historical_uac_text,
)
from app.services.jira_uac_backfill_service import build_sql_uac_rows


def test_historical_uac_contract_is_fingerprinted_and_never_current_ticket_authority():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-90001",
        acceptance_criteria="Outputclass must remain on MathML in merged HTML.",
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done"],
        root_cause="The replacement path dropped outputclass.",
        test_evidence="Verified merged HTML and Native PDF output.",
        root_cause_source="jira_comment_root_cause",
        test_evidence_source="jira_comment_qa_verification",
    )

    assert analysis is not None
    contract = historical_uac_contract_dict(
        analysis,
        acceptance_criteria="Outputclass must remain on MathML in merged HTML.",
        root_cause="The replacement path dropped outputclass.",
        test_evidence="Verified merged HTML and Native PDF output.",
    )

    assert contract["source_snapshot_id"].startswith("jira:GUIDES-90001:uac:")
    assert contract["confirmed_ac_eligible"] is False
    assert contract["current_ticket_authority"] is False
    assert contract["clauses"][0]["citation"].startswith("JIRA:GUIDES-90001:UAC:UAC-01:")


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

FOLDER_PROFILE_SCOPE_COMMENTS = """
[2024-11-21T10:00:00.000+0000] developer: Scope:
Folder Profile will not show groups, but saving must preserve the existing group values.
[2024-11-26T09:00:00.000+0000] qa: As discussed, the scope of this bug is limited to adding new conditions without altering existing ones.
Editing an existing condition in Folder Profile can remove its group and reset its color to yellow; this is beyond the scope of this bug and should be handled as an enhancement.
Scope:
- Add new conditions via Folder Profile, ensuring existing conditions remain unchanged.
- Editing existing conditions must be done using XML Editor.
"""


DITAVAL_TOUCHPOINT_CONTEXT = """
Problem Statement:
Enterprise complaint that ditaval is treated differently at different touch points in AEM Guides.
TouchPoint 1 - Repository Search:
Ditaval is treated as non-DITA file.
TouchPoint 2 - Ditaval Creation:
Ditaval is treated as DITA topic file.
TouchPoint 3 - Reports:
Ditaval is treated as documents/others Type.
As per DITA standard Ditaval is Other DITA type document.
"""


NAVTITLE_BUTTON_DECISION_CONTEXT = """
Problem Statement:
The enterprise reported that the Refresh Navigation Title Attribute button was absent in 5.0 and asked whether it had been deprecated.
The final investigation found no product change was required and the feature was working as expected.
The button is controlled by the existing ui_config ditaAttributes setting.
The control is rendered in the DITA map toolbar.
The button is shown when required navtitle is true and the default required object is empty.
Removing the modified ui_config hides the button again.
Documentation is required for this configuration behavior.
"""


METADATA_FILTER_TENTATIVE_RCA_COMMENT = """
[2025-05-06] Support: RCA:
The root cause could be linked to a custom assetPrefixNodename index, which seems to be impacting the result.
To confirm, I suggest disabling this index and verifying the result.
"""


METADATA_FILTER_CONFIRMED_RCA_COMMENT = """
[2025-05-08] Engineering: The query with type=dam:Asset returned one result while the nodename-only query returned the correct result.
This indicated a problem with indexing of the damAssetLucene index.
Reindexing this index fixed the filtering results, so the issue is environment-specific where damAssetLucene was not created properly.
The initial assumption that the customer index or custom namespaced metadata caused the problem is invalid.
"""


METADATA_FILTER_CUSTOMER_VALIDATION_COMMENT = """
[2025-05-16] Support: KONE IT team has tested and validated that it is fixed after re-indexing.
"""


METADATA_FILTER_DECISION_CONTEXT = """
Problem Statement:
The DITA Topic metadata report filter returned 2 files from a corpus of 442 topic files, while combining DITA Topic and Others returned more files.
The early custom namespace and TypeFilter theory was not confirmed.
The type=dam:Asset query returned one result while the nodename-only query returned the correct result.
The final investigation identified an environment-specific damAssetLucene indexing problem.
Reindexing damAssetLucene fixed the filtering results and KONE validated the remediation.
"""


METADATA_MANAGE_UAC = """
Overall functionality of manage in reports>metadata should work:
Tags, document state should be applied on all or selective list of assets.
Common tags list should be visible in manage dialog and tags should be updated as per the user action.
It should work for all type of assets (DITA, non-DITA).
While updating tags or document state, the Manage button should be disabled.
It should work for both on-prem and cloud versions of Guides.
Custom tags and OOTB tags should both be updated through Manage.
For a bulk operation, the report should show files updated and files skipped, including the skipped count.
Negative scenario dialogs need to be checked.
If the API does not respond within the timeout, a proper error message should be visible.
In Fix Links, if a link cannot be fixed, no error dialog is shown and the link remains broken.
After clicking Manage, a loader should be shown and the button should stay disabled until the API response is received, preventing duplicate API calls.
The Filters panel should show a loading shimmer until the API response is received.
The same disabled-state behavior applies to the Fix Link button.
Other pointers:
Filters should work as is and Manage should affect only files visible in the Metadata tab.
Since the API response is being corrected, performance side there will be no change.
Automation:
API automation has been added by development.
UI automation must cover select all, common tags, and Manage disable/enable behavior.
"""


METADATA_MANAGE_RCA_COMMENT = """
[2025-05-08] Engineering: RCA:
The feature is broken when allAssets=true. Code is missing the UUID-to-path conversion required while creating the query. This causes null to be passed to the query and scans all data. Common tags are not returned even when present.
"""


METADATA_MANAGE_VALIDATION_COMMENTS = """
[2025-05-10] Engineering: Acceptance Criteria Looks good to me!
[2025-05-15] Engineering: The ticket passes all the mentioned points of Acceptance Criteria. EM Review done.
[2025-06-23] Customer QA: Looks good, Tested for smaller and Bigger file-set. Button gets disabled as the user clicks for the first time and progress bar is shown too.
"""


METADATA_MANAGE_HOTFIX_SCOPE_COMMENT = """
[2025-05-27] QA: This ticket is created for 5.0.1 hotfix only.
UAC mentioned in this ticket is done for 2507.
For hotfix, we have just done the point fix. Manage and broken link buttons are disabled while their process runs and enabled when it completes. Common tags are fixed.
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


def test_problem_statement_only_ditaval_taxonomy_decision_never_becomes_trusted_uac():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-31711",
        acceptance_criteria=DITAVAL_TOUCHPOINT_CONTEXT,
        status="Closed",
        resolution="Working as Designed",
        labels=["KONE"],
    )

    assert analysis is not None
    assert analysis.historical_outcome == "expected_product_behavior"
    assert analysis.issue_closed is True
    assert analysis.source_authority == "jira_acceptance_field"
    assert analysis.contract_complete is False
    assert analysis.reuse_tier == "candidate"
    assert analysis.in_scope_clauses == ()
    assert len(analysis.context_clauses) == 8
    assert {
        "conditions",
        "creation_dialog",
        "cross_touchpoint_taxonomy",
        "ditaval_asset",
        "file_type_taxonomy",
        "reports",
        "repository_search",
    }.issubset(set(analysis.dimensions))

    chunks = build_historical_uac_chunks(analysis)
    assert any(chunk["chunk_type"] == UAC_CONTEXT_CHUNK_TYPE for chunk in chunks)
    assert not any(chunk["chunk_type"] == UAC_CLAUSE_CHUNK_TYPE for chunk in chunks)
    assert all(chunk["uac_reuse_tier"] == "candidate" for chunk in chunks)
    assert "Context statements (not acceptance criteria)" in chunks[0]["chunk_text"]
    assert "candidate clauses may only add open questions or risk coverage" in chunks[0]["chunk_text"]


def test_uac_not_required_sentinel_never_creates_historical_acceptance_clauses():
    assert is_no_uac_sentinel("UAC Not Required") is True
    assert is_no_uac_sentinel("Acceptance Criteria: N/A") is True
    assert is_no_uac_sentinel("Navigation title is not required") is False

    analysis = analyze_historical_uac(
        jira_key="GUIDES-30001",
        acceptance_criteria="UAC Not Required",
        status="Closed",
        resolution="Working as Designed",
        labels=["KONE", "Doc_Required"],
    )

    assert analysis is None


def test_configuration_gated_navtitle_decision_is_candidate_context_not_confirmed_uac():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-30001",
        acceptance_criteria=NAVTITLE_BUTTON_DECISION_CONTEXT,
        status="Closed",
        resolution="Working as Designed",
        labels=["KONE", "Doc_Required"],
    )

    assert analysis is not None
    assert analysis.historical_outcome == "expected_product_behavior"
    assert analysis.issue_closed is True
    assert analysis.contract_complete is False
    assert analysis.reuse_tier == "candidate"
    assert analysis.in_scope_clauses == ()
    assert {
        "configuration",
        "configuration_visibility",
        "documentation_gap",
        "navtitle",
        "state",
        "toolbar_customization",
        "ui",
        "ui_configuration",
    }.issubset(set(analysis.dimensions))

    chunks = build_historical_uac_chunks(analysis)
    assert any(chunk["chunk_type"] == UAC_CONTEXT_CHUNK_TYPE for chunk in chunks)
    assert not any(chunk["chunk_type"] == UAC_CLAUSE_CHUNK_TYPE for chunk in chunks)
    assert all(chunk["uac_reuse_tier"] == "candidate" for chunk in chunks)


def test_later_confirmed_root_cause_overrides_tentative_metadata_filter_hypothesis():
    root_cause, source = extract_explicit_root_cause_evidence(
        comment_documents=[
            METADATA_FILTER_TENTATIVE_RCA_COMMENT,
            METADATA_FILTER_CONFIRMED_RCA_COMMENT,
            METADATA_FILTER_CUSTOMER_VALIDATION_COMMENT,
        ]
    )

    assert source == "jira_comment_confirmed_root_cause"
    assert "damAssetLucene" in root_cause
    assert "environment-specific" in root_cause
    assert "initial assumption" in root_cause
    assert "root cause could be linked" not in root_cause

    tentative_only, tentative_source = extract_explicit_root_cause_evidence(
        comment_documents=[METADATA_FILTER_TENTATIVE_RCA_COMMENT]
    )
    assert tentative_only == ""
    assert tentative_source == "missing"


def test_customer_reindex_validation_is_reusable_verification_evidence():
    evidence, source = extract_explicit_test_evidence(
        comment_documents=[METADATA_FILTER_CUSTOMER_VALIDATION_COMMENT]
    )

    assert source == "jira_comment_customer_validation"
    assert "tested and validated" in evidence
    assert "re-indexing" in evidence


def test_exact_version_and_hotfix_comments_are_combined_as_validation_evidence():
    evidence, source = extract_explicit_test_evidence(
        comment_documents=[
            '[2025-01-24] QA: Verified on 5.0.207 this has been fixed.',
            '[2025-03-11] QA: Verified on "4.6.0.164".',
            '[2025-04-05] QA: This is working fine on hotfix 4.6.4, hence closing this as fixed.',
        ]
    )

    assert source == "jira_comment_version_validation"
    assert "5.0.207" in evidence
    assert "4.6.0.164" in evidence
    assert "hotfix 4.6.4" in evidence


def test_metadata_filter_index_incident_is_candidate_context_not_product_uac():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-28847",
        acceptance_criteria=METADATA_FILTER_DECISION_CONTEXT,
        status="Closed",
        resolution="",
        labels=["KONE", "UAC_Not_Required", "Won't_Automate"],
    )

    assert analysis is not None
    assert analysis.historical_outcome == "other_resolution"
    assert analysis.issue_closed is True
    assert analysis.contract_complete is False
    assert analysis.reuse_tier == "candidate"
    assert analysis.in_scope_clauses == ()
    assert {
        "dam_asset_lucene",
        "custom_namespace",
        "environment_specific",
        "file_type_filter",
        "filter_union",
        "metadata_report",
        "oak_index",
        "reindexing",
        "result_count",
        "type_filter",
    }.issubset(set(analysis.dimensions))


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


def test_bulk_metadata_manage_uac_dedupes_and_preserves_performance_boundary():
    root_cause, root_cause_source = extract_explicit_root_cause_evidence(
        comment_documents=[METADATA_MANAGE_RCA_COMMENT]
    )
    test_evidence, test_evidence_source = extract_explicit_test_evidence(
        comment_documents=[METADATA_MANAGE_VALIDATION_COMMENTS]
    )
    analysis = analyze_historical_uac(
        jira_key="GUIDES-28443",
        acceptance_criteria=f"{METADATA_MANAGE_UAC}\n{METADATA_MANAGE_UAC}",
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done"],
        root_cause=root_cause,
        root_cause_source=root_cause_source,
        test_evidence=test_evidence,
        test_evidence_source=test_evidence_source,
    )

    assert analysis is not None
    normalized_clauses = [clause.text.casefold() for clause in analysis.clauses]
    assert len(normalized_clauses) == len(set(normalized_clauses))
    assert sum("common tags list" in text for text in normalized_clauses) == 1
    assert any("api automation" in clause.text.casefold() for clause in analysis.context_clauses)
    assert analysis.root_cause_source == "jira_comment_root_cause"
    assert analysis.test_evidence_source == "jira_comment_acceptance_validation"
    assert "Bigger file-set" in test_evidence
    assert analysis.performance_matters is True
    assert analysis.performance_contract_complete is False
    assert analysis.contract_complete is False
    assert analysis.reuse_tier == "supporting"
    assert {
        "api_response",
        "bulk_operation",
        "common_tags",
        "custom_tags",
        "disabled_state",
        "document_state",
        "fix_links",
        "loading_shimmer",
        "metadata_manage",
        "non_dita_asset",
        "on_prem",
        "ootb_tags",
        "select_all",
        "skipped_count",
        "timeout",
        "visible_assets",
    }.issubset(set(analysis.dimensions))


def test_acceptance_validation_requires_execution_not_signoff_only():
    evidence, source = extract_explicit_test_evidence(
        comment_documents=["Acceptance Criteria Looks good to me!"]
    )
    assert evidence == ""
    assert source == "missing"

    evidence, source = extract_explicit_test_evidence(
        comment_documents=[METADATA_MANAGE_VALIDATION_COMMENTS]
    )
    assert source == "jira_comment_acceptance_validation"
    assert "progress bar is shown" in evidence


def test_hotfix_scope_split_blocks_mainline_uac_reuse():
    release_scope, release_scope_source = extract_release_scope_evidence(
        comment_documents=[METADATA_MANAGE_HOTFIX_SCOPE_COMMENT]
    )
    analysis = analyze_historical_uac(
        jira_key="GUIDES-29778",
        acceptance_criteria=METADATA_MANAGE_UAC,
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done"],
        root_cause="The allAssets query omitted UUID-to-path conversion.",
        test_evidence="Tested select all, common tags, filters, and broken-link fixing on hotfix 5.0.1.2.",
        release_scope_evidence=release_scope,
        release_scope_source=release_scope_source,
    )

    assert analysis is not None
    assert analysis.release_scope_split is True
    assert analysis.release_scope_source == "jira_comment_release_scope"
    assert "5.0.1 hotfix only" in analysis.release_scope_evidence
    assert analysis.contract_complete is False
    assert analysis.reuse_tier == "candidate"
    assert any("separate mainline release" in warning for warning in analysis.contradictions)
    contract = build_historical_uac_chunks(analysis)[0]
    assert contract["uac_release_scope_split"] is True
    assert contract["uac_release_scope_source"] == "jira_comment_release_scope"
    assert "only the explicitly listed hotfix point fix may be reused" in contract["chunk_text"]


def test_custom_preview_button_contract_has_lock_and_configuration_migration_dimensions():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-28667",
        acceptance_criteria=(
            "The custom Export PDF button must be visible in preview mode for both locked and unlocked "
            "files after porting the configuration to editor_toolbar.json."
        ),
        status="Closed",
        resolution="Fixed",
    )

    assert analysis is not None
    assert {
        "configuration_migration",
        "custom_button",
        "editor_toolbar_configuration",
        "locked_state",
        "preview_mode",
        "unlocked_state",
    }.issubset(set(analysis.dimensions))


def test_unspecified_resolution_does_not_make_an_open_issue_closed():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-40001",
        acceptance_criteria="Generated output must retain the selected baseline version.",
        status="Open",
        resolution="Unspecified",
    )

    assert analysis is not None
    assert analysis.issue_closed is False


def test_latest_explicit_scope_comment_becomes_accepted_uac_only_with_accepted_label():
    text, source = extract_comment_accepted_uac(
        labels=["KONE", "UAC_Done"],
        comment_documents=[FOLDER_PROFILE_SCOPE_COMMENTS],
    )

    assert source == "jira_comment_accepted_scope"
    assert "Add new conditions via Folder Profile" in text
    assert "Editing existing conditions must be done using XML Editor" in text
    assert "beyond the scope of this bug" in text
    assert "Folder Profile will not show groups" not in text

    unaccepted_text, unaccepted_source = extract_comment_accepted_uac(
        labels=["KONE"],
        comment_documents=[FOLDER_PROFILE_SCOPE_COMMENTS],
    )
    assert unaccepted_text == ""
    assert unaccepted_source == "missing"


def test_native_no_uac_sentinel_blocks_comment_scope_promotion():
    text, source = resolve_historical_uac_text(
        acceptance_criteria="UAC Not Required",
        labels=["UAC_Done"],
        comment_documents=[FOLDER_PROFILE_SCOPE_COMMENTS],
    )

    assert text == ""
    assert source == "jira_no_uac_sentinel"


def test_native_acceptance_field_precedes_comment_scope_and_pending_scope_is_rejected():
    text, source = resolve_historical_uac_text(
        acceptance_criteria="Existing condition groups must remain unchanged after save.",
        labels=["UAC_Done"],
        comment_documents=[FOLDER_PROFILE_SCOPE_COMMENTS],
    )
    assert text == "Existing condition groups must remain unchanged after save."
    assert source == "jira_acceptance_field"

    pending_text, pending_source = extract_comment_accepted_uac(
        labels=["UAC_Done"],
        comment_documents=["[2024-11-27T09:00:00.000+0000] qa: Scope: will be discussed and updated here."],
    )
    assert pending_text == ""
    assert pending_source == "missing"


def test_guides_34915_thumbnail_uac_overrides_stale_multi_selection_description():
    accepted_uac = """Acceptance Criterion:
1. Thumbnail should be shown for valid image files at Home Repository content view, Search panel, and Bottom search panel.
2. Selection of image files should work fine.
3. Thumbnail should be visible for PNG, JPG, and SVG.
4. Thumbnail should be the same as the latest version of the image.
5. Unsupported or invalid images show a default placeholder broken image with no broken UI.
6. Thumbnails load smoothly using lazy-loading when necessary, without layout jank.
"""
    stale_description = """Enterprise Problem Statement:
Multi-selection is not possible when applying an image to a topic.
Multi-selection should only be possible within a specific folder.
"""

    text, source = resolve_historical_uac_text(
        acceptance_criteria=accepted_uac,
        description=stale_description,
        labels=["UAC_Done", "Hyundai"],
    )
    analysis = analyze_historical_uac(
        jira_key="GUIDES-34915",
        acceptance_criteria=text,
        acceptance_source=source,
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done", "Hyundai"],
    )

    assert source == "jira_acceptance_field"
    assert "Multi-selection" not in text
    assert analysis is not None
    assert {
        "asset_browser_thumbnail",
        "thumbnail_surfaces",
        "thumbnail_format_matrix",
        "thumbnail_freshness",
        "thumbnail_fallback",
        "thumbnail_lazy_loading",
    }.issubset(set(analysis.dimensions))
    assert "asset_picker_multi_selection" not in analysis.dimensions


def test_guides_34580_duplicate_without_uac_remains_candidate_only():
    description = """Problem Statement:
For Topics, an Xref displays the Title. For MAP files, the Xref displays the file name.
Display the Title of the MAP reference instead of the file name.
"""
    text, source = resolve_historical_uac_text(
        acceptance_criteria="",
        description=description,
        labels=["Authoring"],
    )

    assert text == ""
    assert source == "missing"

    candidate = analyze_historical_uac(
        jira_key="GUIDES-34580",
        acceptance_criteria=(
            "A MAP file referenced using Xref should display its Title instead of its file name."
        ),
        status="Closed",
        resolution="Duplicate",
        labels=["Authoring"],
    )

    assert candidate is not None
    assert candidate.historical_outcome == "duplicate_reference"
    assert candidate.reuse_tier == "candidate"
    assert {
        "xref_map_display_label",
        "map_reference",
        "reference_display_label",
    }.issubset(set(candidate.dimensions))


def test_map_view_initial_hierarchy_selection_count_preserves_file_type_matrix():
    accepted_uac = """Acceptance Criterion:
In a fresh Guides 4.6 Map View, selecting map2 for the first time currently shows 1 selected although
the expanded hierarchy contains exactly 7 selected nodes. This happens only for the first time and
any subsequent selection shows the correct count. The first selection must immediately display
7 selected, including the selected map and all selected child nodes, without relying on a second selection.
The hierarchy can contain DITA files, Markdown files, and DITAVAL files.
"""

    text, source = resolve_historical_uac_text(
        acceptance_criteria=accepted_uac,
        labels=["Authoring", "UAC_Done"],
    )
    analysis = analyze_historical_uac(
        jira_key="GUIDES-MAP-VIEW-SELECTION",
        acceptance_criteria=text,
        acceptance_source=source,
        status="Closed",
        resolution="Fixed",
        labels=["Authoring", "UAC_Done"],
    )

    assert source == "jira_acceptance_field"
    assert analysis is not None
    assert {
        "map_view_selection_count",
        "hierarchy_selection",
        "initial_selection",
        "selected_descendants",
        "first_selection_self_recovery",
        "markdown",
        "ditaval_asset",
        "dita_asset",
    }.issubset(set(analysis.dimensions))
    assert "performance" not in analysis.dimensions
    assert "translation_first_run" not in analysis.dimensions


def test_asset_crud_api_contract_is_not_misclassified_as_editor_crud():
    proposed_contract = """Scope: External-system asset import through the CRUD APIs.
The CREATE API accepts caller-provided topic content instead of template-only content.
The CREATE and UPDATE APIs accept metadata in the same request and persist it with the asset.
The CREATE API accepts an explicit desired GUID independently of a human-readable filename.
The UPDATE call uses UPSERT semantics: an existing target is updated once; a missing target is
not created when force creation is omitted or false, and exactly one asset is created when force
creation is true and the required creation fields are valid.
Existing template-only CREATE clients remain backward compatible.
"""

    analysis = analyze_historical_uac(
        jira_key="GUIDES-ASSET-CRUD-API",
        acceptance_criteria=proposed_contract,
        status="Open",
        resolution="",
        labels=["Integration"],
    )

    assert analysis is not None
    assert {
        "asset_crud_api",
        "caller_content_payload",
        "metadata_write",
        "explicit_guid_assignment",
        "human_readable_filename",
        "template_content",
        "upsert",
        "force_create",
        "external_system_import",
    }.issubset(set(analysis.dimensions))
    assert "authoring_crud" not in analysis.dimensions
    assert all(
        "crud_operation_matrix_missing" not in clause.unresolved_reasons
        for clause in analysis.clauses
    )


def test_guides_30459_bulk_overwrite_session_history_stays_candidate():
    proposed_contract = """Scope: AEM 6.5 On-Prem Guides 5.0 UUID bulk asset overwrite.
The initial upload control for 200 assets completes, but re-uploading the same-name assets through
/bin/fmdita/import can remain stuck on an indefinite loader or show a generic error, repeated CSRF
token requests, and a redirect to login. The overwrite should reach an observable terminal success
or failure state without forced logout. Success must be verified by read-back of every targeted
asset binary, content identity, and repository state. Compare a smaller batch with the reported
200-asset fixture without treating either count as a supported threshold. Maximum POST Parameter,
File Save, and File Count settings plus Product Assets Upload Process changes are diagnostics only.
"""

    analysis = analyze_historical_uac(
        jira_key="GUIDES-30459",
        acceptance_criteria=proposed_contract,
        status="Closed",
        resolution="Cannot Reproduce",
        labels=["Hyundai", "Platform"],
    )

    assert analysis is not None
    assert {
        "bulk_asset_overwrite",
        "same_name_overwrite",
        "fmdita_import_route",
        "indefinite_loader",
        "generic_failure_message",
        "csrf_refresh_loop",
        "login_redirect",
        "processing_terminal_state",
        "asset_readback_integrity",
        "initial_upload_control",
        "batch_boundary",
        "upload_limit_configuration",
        "product_assets_upload_process",
        "bulk_asset_overwrite_session",
    }.issubset(set(analysis.dimensions))
    assert analysis.historical_outcome == "non_fix_decision"
    assert analysis.reuse_tier == "candidate"
    assert analysis.performance_matters is False
    assert analysis.explicit_root_cause is False
    assert analysis.explicit_test_evidence is False


def test_guides_23526_comment_scope_preserves_narrow_final_contract():
    acceptance_text, acceptance_source = resolve_historical_uac_text(
        labels=["UAC_Done", "KONE"],
        comment_documents=[FOLDER_PROFILE_SCOPE_COMMENTS],
    )
    analysis = analyze_historical_uac(
        jira_key="GUIDES-23526",
        acceptance_criteria=acceptance_text,
        acceptance_source=acceptance_source,
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done", "KONE"],
    )

    assert analysis is not None
    assert analysis.source_authority == "jira_accepted_uac"
    assert analysis.source_origin == "jira_comment_accepted_scope"
    assert {clause.source_id for clause in analysis.in_scope_clauses} == {"UAC-01", "UAC-02"}
    assert len(analysis.out_of_scope_clauses) == 1
    assert "Folder Profile will not show groups" not in " ".join(
        clause.text for clause in analysis.clauses
    )
    assert {
        "add_condition",
        "condition_color",
        "condition_groups",
        "edit_condition",
        "folder_profile",
    }.issubset(set(analysis.dimensions))
    assert analysis.reuse_tier == "supporting"
    chunks = build_historical_uac_chunks(analysis)
    assert all(chunk["uac_source_origin"] == "jira_comment_accepted_scope" for chunk in chunks)


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


def test_authoring_viewport_contract_is_distinct_and_does_not_invent_performance_scope():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-91001",
        acceptance_criteria="""
Given a long topic with the active cursor deep in the Author canvas, editing content keeps the active element visible and does not scroll to the document top.
When the author inserts or updates an xref through the reference picker, closing the dialog restores the caret to the intended insertion location and keeps that location visible.
Typing, paste, dialog cancel, and repeated reference insertion preserve the selection and surrounding content without duplicate insertion or unintended content mutation.
When inserted content causes layout reflow, the viewport restores relative to the active element rather than an exact pixel offset.
""",
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done"],
    )

    assert analysis is not None
    assert "authoring_viewport_stability" in analysis.dimensions
    assert "active_element" in analysis.dimensions
    assert "caret" in analysis.dimensions
    assert "reference_insertion" in analysis.dimensions
    assert "large_topic" in analysis.dimensions
    assert "scroll_to_top" in analysis.dimensions
    assert "map_preview_state" not in analysis.dimensions
    assert analysis.performance_matters is False


def test_map_preview_state_contract_stays_separate_from_author_canvas_scrolling():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-91002",
        acceptance_criteria="""
Map Preview must retain its scroll position and selected topic when the user returns from Edit.
Refreshing Map Preview must fetch current topic content while preserving the applied condition and right-panel state.
""",
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done"],
    )

    assert analysis is not None
    assert "map_preview_state" in analysis.dimensions
    assert "authoring_viewport_stability" not in analysis.dimensions


def test_cals_multi_column_delete_contract_captures_structural_integrity():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-91003",
        acceptance_criteria=(
            "Deleting two columns from a CALS 6x5 table must remove both selected columns and update "
            "tgroup/@cols, colspec, namest, and nameend without a blank or ghost column."
        ),
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done"],
    )

    assert analysis is not None
    assert "cals_table" in analysis.dimensions
    assert "multi_column_delete" in analysis.dimensions
    assert "table_structure_integrity" in analysis.dimensions


def test_guides_35437_is_configuration_driven_working_as_designed_not_a_cell_defect():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-35437",
        acceptance_criteria=(
            "Working as designed: largeFileTagCount is a system configuration that controls large-file "
            "mode, where undo/redo and the dirty marker can be disabled above the configured threshold."
        ),
        status="Closed",
        resolution="Working as Designed",
        labels=["UAC_Done"],
    )

    assert analysis is not None
    assert "large_file_tag_count" in analysis.dimensions
    assert "large_file_safeguard" in analysis.dimensions
    assert "configuration_driven_behavior" in analysis.dimensions
    assert "working_as_designed" in analysis.dimensions
    assert "multi_column_delete" not in analysis.dimensions
    assert analysis.performance_matters is False


def test_guides_41093_explorer_sorting_keeps_display_and_order_dimensions_separate():
    analysis = analyze_historical_uac(
        jira_key="GUIDES-41093",
        acceptance_criteria=(
            "Working as designed: in Web Editor Explorer, User Preferences Display File name changes "
            "the displayed label, but the sort order remains unchanged and follows the folder-level "
            "Assets sort configuration. The requested enhancement should either honor the display "
            "preference as the default sort key or expose explicit sort controls for Name or Title, "
            "ascending or descending, with a per-user session override. With the feature flag OFF, "
            "legacy Explorer behavior remains unchanged. With the feature flag ON, the dedicated "
            "sort control is available. Validate the default state of the sort button on first render."
        ),
        status="Closed",
        resolution="Working as Designed",
        labels=["Red Hat"],
    )

    assert analysis is not None
    assert {
        "explorer_sorting",
        "display_preference",
        "display_sort_decoupling",
        "folder_sort_configuration",
        "user_sort_override",
        "sort_direction",
        "explorer_sort_control",
        "feature_flag",
        "feature_flag_state_matrix",
        "control_default_state",
        "working_as_designed",
    }.issubset(set(analysis.dimensions))
    assert "reference_display_label" not in analysis.dimensions
    assert analysis.reuse_tier == "candidate"
    assert analysis.historical_outcome == "expected_product_behavior"


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
        source_file_hash="a" * 64,
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


def test_sql_backfill_recovers_accepted_scope_from_comment_when_field_is_missing():
    issue = JiraEnrichedIssue(
        id=2,
        jira_key="GUIDES-23526",
        summary="Conditional Attribute grouping lost through Folder Profile",
        description="Folder Profile updates can flatten existing condition groups.",
        issue_type="Customer Request",
        status="Closed",
        priority="Critical",
        resolution="Fixed",
        jira_updated_at=datetime(2024, 11, 26, 9, 0, 0),
        source_type="jira_csv",
        source_file_hash="b" * 64,
        labels=["UAC_Done", "KONE"],
        components=["Authoring"],
        customer_names=["KONE"],
        domain="authoring",
        affected_outputs=[],
        dita_entities=[],
        qa_risk_tags=["regression"],
        raw_text="",
        customer_detection_debug={},
    )
    comment = JiraIssueChunk(
        jira_key=issue.jira_key,
        chunk_type="comment_chunk",
        chunk_text="Discussion:\n" + FOLDER_PROFILE_SCOPE_COMMENTS,
    )

    built = build_sql_uac_rows(issue, [comment])

    assert built is not None
    analysis, rows = built
    assert analysis.source_origin == "jira_comment_accepted_scope"
    assert analysis.source_authority == "jira_accepted_uac"
    assert any("Add new conditions via Folder Profile" in row["document"] for row in rows)
    assert all(
        row["metadata"]["uac_source_origin"] == "jira_comment_accepted_scope"
        for row in rows
    )


def test_sql_backfill_uses_archived_csv_uac_after_newer_issue_metadata_merge():
    archived_uac = (
        "Native PDF output must retain the configured outputclass on MathML.\n"
        "Out of Scope: iframe outputclass propagation."
    )
    issue = JiraEnrichedIssue(
        id=3,
        jira_key="GUIDES-22950",
        summary="MathML outputclass propagation",
        description="A newer Jira API snapshot without the custom UAC field.",
        issue_type="Customer Request",
        status="Closed",
        priority="Critical",
        resolution="Fixed",
        jira_updated_at=datetime(2026, 8, 8, 10, 0, 0),
        source_type="jira_api",
        labels=["UAC_Done"],
        components=["Publishing"],
        customer_names=["Example Customer"],
        domain="publishing",
        affected_outputs=["Native PDF"],
        dita_entities=["mathml"],
        qa_risk_tags=["regression"],
        raw_text="",
        customer_detection_debug={},
        evidence_archive={
            "acceptance_criteria": [archived_uac],
            "root_causes": [],
            "test_plans": [],
            "comments": [],
        },
    )

    built = build_sql_uac_rows(issue, [])

    assert built is not None
    analysis, rows = built
    assert analysis.source_origin == "jira_acceptance_field"
    assert analysis.source_authority == "jira_accepted_uac"
    assert any("configured outputclass" in row["document"] for row in rows)
    assert any("iframe outputclass" in row["document"] for row in rows)


def test_sql_backfill_rejects_screenshot_only_or_unhashed_manual_uac_records():
    screenshot_issue = JiraEnrichedIssue(
        id=4,
        jira_key="GUIDES-99998",
        summary="Screenshot-only Jira example",
        description="## UAC Criteria (custom field)\nThe active cursor must remain visible.",
        issue_type="Customer Request",
        status="Closed",
        resolution="Fixed",
        source_type="screenshot",
        labels=["UAC_Done"],
    )
    unhashed_csv_issue = JiraEnrichedIssue(
        id=5,
        jira_key="GUIDES-99999",
        summary="Unhashed manual Jira example",
        description="## UAC Criteria (custom field)\nThe active cursor must remain visible.",
        issue_type="Customer Request",
        status="Closed",
        resolution="Fixed",
        source_type="jira_csv",
        labels=["UAC_Done"],
    )

    assert build_sql_uac_rows(screenshot_issue, []) is None
    assert build_sql_uac_rows(unhashed_csv_issue, []) is None


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
