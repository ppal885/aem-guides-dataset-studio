# GUIDES-38274 - QE plan

## Issue understanding

- [~mbhalla] [~gautamh] : this is another critical ask due to which customer is stuck with defining content lifecycle process for their team
- Problem statement
- When user is updating topics, user have the option to apply the label which gives you in-context understanding of what label should be applied according to the content changes done by user but there is no logical way to define label on images :
- cc: [~suyashs] [~abhaysi]
- Managing Image Versions for release management
- or neither the user has visibility to where this image will be used in topics and for what content version will this updated image be used

## Publishing / product scope

- Execution interface: API
- Execution interface: UI

## Finalization

- NEEDS_REVIEW: a material contract exists but no acceptance criteria were promoted — resolve the items below, then re-run.
- Blocked: A blocking product decision remains unresolved.
- Unresolved product decision: Which established product behavior or product decision addresses this gap: neither while uploading/updating the image - as at that point the dialog does not have option to add label,?
- Unresolved product decision: What exact product behavior does the human term "When using baselines the versions of topics and dependents (images/media) is chosen based on label largely" mean?

## Product decisions required

- Which established product behavior or product decision addresses this gap: neither while uploading/updating the image - as at that point the dialog does not have option to add label,?
- What exact product behavior does the human term "When using baselines the versions of topics and dependents (images/media) is chosen based on label largely" mean?

## Semantic coverage

- Controlling attributes: internal evidence recorded for 12 closure records (see trace)
- Absent value: internal evidence recorded for 12 closure records (see trace)
- Fallback: internal evidence recorded for 12 closure records (see trace)
- Governing semantics: internal evidence recorded for 12 closure records (see trace)
- Version applicability: internal evidence recorded for 12 closure records (see trace)
- Governing configuration: internal evidence recorded for 12 closure records (see trace)
- Specializations: internal evidence recorded for 12 closure records (see trace)
- Positive state: internal evidence recorded for 12 closure records (see trace)
- Deployment applicability: internal evidence recorded for 12 closure records (see trace)

## Structural / hierarchy coverage

- Parent context: internal evidence recorded for 12 closure records (see trace)
- Hierarchy: internal evidence recorded for 12 closure records (see trace)
- Child context: internal evidence recorded for 12 closure records (see trace)

## Referenced content coverage

- Nested referenced content: internal evidence recorded for 12 closure records (see trace)
- Referenced content: internal evidence recorded for 12 closure records (see trace)

## Configuration / state coverage

- Also the only way to apply label on image is Version History panel in assets UI where the label is a text box and not driven by labels.json of Folder profiles
- When user is updating topics, user have the option to apply the label which gives you in-context understanding of what label should be applied according to the content changes done by user but there is no logical way to define label on images :
- neither while uploading/updating the image - as at that point the dialog does not have option to add label,
- Attached video recording of discussion with customer :  [^Swift + AEM Guides - Baselines - GUIDES-38274-Request.mp4]
- However for media files there is no way to easily manage labels
- When using baselines the versions of topics and dependents (images/media) is chosen based on label largely
- Defining the label of the topic is easily managed via webeditor through Save Revision dialog.
- Asset Management
- Fetched `GUIDES-38274` directly from Jira API.
- In UAC
- Considering above problems or experience gaps the users are unable to manage content releases with baseline as images play a critical role and manually assigning image version labels through Assets UI is not acceptable

## Transformation / processing coverage

- Persisted state: internal evidence recorded for 12 closure records (see trace)
- Sibling consumers: internal evidence recorded for 12 closure records (see trace)
- Downstream processor: internal evidence recorded for 12 closure records (see trace)
- Direct consumers: internal evidence recorded for 12 closure records (see trace)

## Generated output validation

- Generated output: internal evidence recorded for 12 closure records (see trace)

## Negative / boundary coverage

- Negative state: internal evidence recorded for 12 closure records (see trace)
- When user is updating topics, user have the option to apply the label which gives you in-context understanding of what label should be applied according to the content changes done by user but there is no logical way to define label on images :
- Invalid value: internal evidence recorded for 12 closure records (see trace)

## Lifecycle coverage

- Lifecycle: internal evidence recorded for 12 closure records (see trace)

## NFR coverage

- Validate MIGRATION under: bulk
- Validate CONTENT_MANAGEMENT under: bulk
- Validate TRANSLATION under: bulk
- Validate EXTENSION_FRAMEWORK under: bulk
- Validate WORKFLOW_JOB under: bulk
- Validate AUTHORING under: bulk
- Validate PERFORMANCE under: bulk
- Validate PUBLISHING under: bulk
- Validate API under: bulk
- Validate ASSETS under: bulk
- Validate BASELINE under: bulk
- Validate SEARCH_QUERY under: bulk

## Known limitations

- neither while uploading/updating the image - as at that point the dialog does not have option to add label,
- Also the only way to apply label on image is Version History panel in assets UI where the label is a text box and not driven by labels.json of Folder profiles
- However for media files there is no way to easily manage labels
- Considering above problems or experience gaps the users are unable to manage content releases with baseline as images play a critical role and manually assigning image version labels through Assets UI is not acceptable

## Evidence gaps

- [~mbhalla] [~gautamh] : this is another critical ask due to which customer is stuck with defining content lifecycle process for their team — A blocking product decision remains unresolved.
- cc: [~suyashs] [~abhaysi] — A blocking product decision remains unresolved.
- When user is updating topics, user have the option to apply the label which gives you in-context understanding of what label should be applied according to the content changes done by user but there is no logical way to define label on images : — A blocking product decision remains unresolved.
- Managing Image Versions for release management — A blocking product decision remains unresolved.
- or neither the user has visibility to where this image will be used in topics and for what content version will this updated image be used — A blocking product decision remains unresolved.
- Problem statement — A blocking product decision remains unresolved.
- Which other presets intentionally share this behavior?
- What should explicitly be out of scope?
- neither while uploading/updating the image - as at that point the dialog does not have option to add label,
- When using baselines the versions of topics and dependents (images/media) is chosen based on label largely
- What exact product behavior does the human term "When using baselines the versions of topics and dependents (images/media) is chosen based on label largely" mean?
- Which established product behavior or product decision addresses this gap: neither while uploading/updating the image - as at that point the dialog does not have option to add label,?

## Coverage gate result

- ContractIntegrityGate: PASSED
- BehavioralCompletenessGate: PASSED
- AcceptancePromotionGate: BLOCKED — candidate:178f19c153d91b90d09bf8ac695c8e03: A blocking product decision remains unresolved.; candidate:341aa3895fa48d4bbb1ad3d870aaf55a: A blocking product decision remains unresolved.; candidate:74f61e0e564b4f8c331ab9da802a6cf1: A blocking product decision remains unresolved.; candidate:9175e6316b0a57b2a9aba780a3f30098: A blocking product decision remains unresolved.; candidate:9250a15d73d912ed0c2c9dc54e2f07d0: A blocking product decision remains unresolved.; candidate:a06c2abf037ab94efacb98b35fe5837b: A blocking product decision remains unresolved.; No acceptance-contract candidate passed the promotion gate.
