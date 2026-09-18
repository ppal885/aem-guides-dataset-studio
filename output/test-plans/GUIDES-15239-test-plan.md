# GUIDES-15239 — QE plan

## Issue understanding

- [Experience Enhancement] Outputs in XML editor

## Publishing / product scope

- In scope: Applies to folders under Experience Manager DAM and affects DAM Update Asset workflow postprocessing/UUID generation.
- Execution interface: API
- Execution interface: UI

## Proposed acceptance contract

- Customer-stated desired behavior: The outputs are very handy on this side, but as you are not getting the traffic lights for processing, authors would need to be knowledgeable enough to check the log to see if there are warnings. In this example, an image is missing but I need to go to the log to see this.

## Product decisions required

- (TBD) Established by evidence: Customer-stated text on the slide: 'The outputs are very handy on this side, but as you are not getting the traffic lights for processing, authors would need to be knowledgeable enough to check the log to see if there are warnings. In this example, an image is missing but I need to go to the log to see this. The old UI gives you the traffic light as an indic Undecided: The Jira fix comment (ev:JIRA_COMMENT:aaf49479f0b19407df08a4194986adef) states the backend scans the publish log for WARN lines and sets an errorsExist flag, but in C:\starling at fdfa72777a2d73b2cdba6d2bdd60ea5535bad75f LogToHtml.java sets errorsExist only on Error/Fatal matches (lines 84-85) and its unit test shouldGenerateHtmlFromLogWithNoErrors asserts a Decision needed: which interpretation defines the acceptance expectation for this question.

## Semantic coverage

- Positive state: internal evidence recorded for 12 closure records (see trace)
- Controlling attributes: internal evidence recorded for 12 closure records (see trace)
- Fallback: internal evidence recorded for 12 closure records (see trace)
- Specializations: internal evidence recorded for 12 closure records (see trace)
- Deployment applicability: internal evidence recorded for 12 closure records (see trace)
- Absent value: internal evidence recorded for 12 closure records (see trace)
- Version applicability: internal evidence recorded for 12 closure records (see trace)
- Governing configuration: internal evidence recorded for 12 closure records (see trace)
- Governing semantics: internal evidence recorded for 12 closure records (see trace)

## Structural / hierarchy coverage

- Child context: internal evidence recorded for 12 closure records (see trace)
- Hierarchy: internal evidence recorded for 12 closure records (see trace)
- Parent context: internal evidence recorded for 12 closure records (see trace)

## Referenced content coverage

- Referenced content: internal evidence recorded for 12 closure records (see trace)
- Nested referenced content: internal evidence recorded for 12 closure records (see trace)

## Configuration / state coverage

- You can also check an asset publish status by selecting an asset and clicking Details .
- Default enabled path: /content/dam.
- UAC_Not_Required
- By default, all uploaded assets are processed using the DAM Update Asset workflow.
- Issue: As per slide 19, Kone Reported.
- NOTE All the API calls related to uploading or updating assets or binaries in general (like renditions) is deprecated for Experience Manager as a Cloud Service deployment.
- Select Enabled Paths for Post Processing to enable a path for postprocessing
- Won’t_Automate
- High-signal topics and headings: configuration overrides, Cloud Service, AEM Guides configuration updates, OSGi configuration, PID, config folder, Cloud Manager pipeline, deploy updated configuration, folder postprocessing setup, install configuration override.
- default enabled path: /content/dam.
- Added a visual "traffic light" indicator for successful outputs that still have DITA-OT warnings (e.g.
- Learning retrieval profile for AEM Guides Cloud Service folder postprocessing configuration.
- ignored wins over enabled.
- Learning retrieval profile for AEM Guides On-Premise folder postprocessing configuration.
- Starling 4.4
- Priority:Normal
- default ignored path: /content/dam/projects/translation_output.
- For making any configuration updates in Experience Manager Guides as a Cloud Service, the following generic approach should be used:
- The ignored property is disabled by default and the translation tab is available on the map dashboard.
- Default ignored path: /content/dam/projects/translation_output.
- By default, postprocessing is done for every folder path under the Experience Manager DAM folder.
- Applies to folders under Experience Manager DAM and affects DAM Update Asset workflow postprocessing/UUID generation.
- If a parent folder is ignored for postprocessing but a child folder is enabled, the child and all successors are considered enabled.
- The file should contain {} as its content, signifying an empty OSGi configuration for the corresponding OSGi component.
- If an asset or folder is not published, the status for columns AEM Publish and Dynamic Media Publish is displayed as N/A .
- Plan_2610
- As there are several differences to standard assets (such as images or documents), some additional rules apply to handling Content Fragments.
- If a parent folder is enabled for postprocessing but a child folder is ignored, the child and all successors are considered ignored.
- Retrieval terms: rules to enable or disable postprocessing, parent ignored child enabled, parent enabled child ignored, same folder path both ignored and enabled, ignored wins, DAM folder hierarchy, successors.
- Use this for Jira-driven QA/test-plan retrieval when tickets mention Experience Manager Guides Cloud Service configuration overrides, creating configuration files, updating a PID, deploying via Cloud Manager pipeline, or using configuration overrides to disable folder postprocessing.
- Fetched `GUIDES-15239` directly from Jira API.

## Transformation / processing coverage

- Sibling consumers: internal evidence recorded for 12 closure records (see trace)
- Downstream processor: internal evidence recorded for 12 closure records (see trace)
- Direct consumers: internal evidence recorded for 12 closure records (see trace)

## Generated output validation

- Generated output: internal evidence recorded for 12 closure records (see trace)

## Negative / boundary coverage

- Negative state: internal evidence recorded for 12 closure records (see trace)
- missing referenced content), so authors no longer need to open the log to notice them.
- Paths are multivalue NODE_OPTIONS strings without trailing slash.
- Invalid value: internal evidence recorded for 12 closure records (see trace)

## Lifecycle coverage

- Lifecycle: internal evidence recorded for 12 closure records (see trace)

## NFR coverage

- Validate CONTENT_MANAGEMENT under: bulk
- Validate API under: bulk, explicit high cardinality
- Validate MIGRATION under: bulk
- Validate PUBLISHING under: bulk, explicit high cardinality
- Validate WORKFLOW_JOB under: bulk, explicit high cardinality
- Validate SEARCH_QUERY under: bulk
- Validate BASELINE under: bulk
- Validate ASSETS under: bulk
- Validate AUTHORING under: bulk, explicit high cardinality
- Validate PERFORMANCE under: bulk
- Validate TRANSLATION under: bulk

## Known limitations

- Although authors cannot add new metadata fields for assets, developers can.
- To enable the OnOffTimeAssetAccessFilter service, you need to create an OSGi configuration.
- Description: The outputs are very handy on this side, but as you are not getting the traffic lights for processing, authors would need to be knowledgeable enough to check the log to see if there are warnings.
- The old UI gives you the traffic light as an indication that you should check the log.
- If you need to view the time when the assets are published, you can navigate to List view and view those details.
- If you cannot view the AEM Publish and Dynamic Media Publish columns in the List view: Click
- In this example, an image is missing but I need to go to the log to see this.

## Evidence gaps

- Which other presets intentionally share this behavior?
- What should explicitly be out of scope?
- Which persisted state is written or read for skip_feature_if_flag, before_feature, 2688, explicit_wait, it('should call close dialog function when preset type is knowledge Base or Native pdf', () => {, reports, should call close dialog function when preset type is knowledge Base or Native p, webpackUniversalModuleDefinition, normalize_branch, allows for more readability of the test reports.?
- Does the processing mode change the behavior under acceptance here, given that existing evidence mentions it without establishing an interaction?

## Coverage gate result

- ContractIntegrityGate: PASSED
- BehavioralCompletenessGate: PASSED
- AcceptancePromotionGate: PASSED
- AcceptanceContractLint: EXCESSIVE_LENGTH: an acceptance criterion runs 58 words — split or tighten it ("Customer-stated desired behavior: The outputs are ...")
