# Component UAC Contracts

Moved verbatim from SKILL.md on 2026-09-30 when SKILL.md was consolidated. The rules are unchanged.

## Translation Project API UAC Reference

- Use this UAC when scope covers an automation API that creates a translation project for a supplied DITA map and selected filters.
- Require support for project types `newTranslationProject`, `xliffTranslationProject`, `newMultiLingualTranslationProject`, `addToExistingProject`, and `newScopingTranslationProject`.
- For `latestVersion`, resolve forward references from the latest saved version of the DITA map and exclude working-copy changes.
- For `baseline`, resolve forward references exactly as they existed when the specified baseline was created.
- For `versionAsOfDate`, resolve forward references exactly as they existed at the supplied date and time.
- Cover `referenceType` values `Direct` and `Indirect`.
- Cover `fileType` values `Map`, `Topic`, and `Others`.
- Cover `documentState` values `Draft`, `In-Review`, and `Reviewed`.
- Cover `translationStatus` values `Out of Date`, `In Progress`, `In Sync`, `Out of Sync`, and `Missing copy`.
- Require the API request to accept the DITA map, project title, project type, language list, version selection and required version value, and selected filters.
- Verify the API creates missing target-language folders before creating or updating the translation project.
- Derive positive, negative, boundary, filter-combination, version-resolution, missing-language-folder, permissions, idempotency, validation, error-contract, and automation-consumability scenarios from this UAC.
- Keep unspecified API details as open questions, including endpoint and method, request/response schema, baseline identifier format, date/time zone and inclusivity, filter combination semantics, existing-project identifier, duplicate project-title behavior, partial-failure rollback, folder naming/location, and permissions.

## EDS GitHub And GitLab Publishing Profile UAC Reference

- Use this UAC when scope covers creating or using EDS Publishing Profiles with GitHub or GitLab repositories.
- Support GitHub Cloud public/private, GitLab Cloud public/private, self-hosted GitHub Enterprise, and self-hosted GitLab repositories.
- Provide a `Git Provider` selector with GitHub and GitLab options, dynamically update provider-specific UI fields, and default the server URL to the self-hosted GitLab URL when GitLab is selected.
- Enforce mandatory-field validation and enable `Save` only after all required fields are present and authentication succeeds; never persist an unauthenticated profile.
- Support OAuth authentication for both providers using Client ID, Client Secret, and token exchange.
- Show clear errors for invalid repository details or credentials, expired/revoked tokens, insufficient or read-only permissions, authentication failures, network interruption, API timeout, and server failure.
- Prevent publishing when authentication fails or repository permissions are insufficient.
- Verify `Push to Live` commits and pushes content to the configured repository and branch for both providers, while preserving the existing EDS workflow and downstream EDS pipeline trigger.
- Verify Publishing Profile APIs behave consistently for GitHub and GitLab.
- Preserve backward compatibility for existing GitHub publishing profiles, Push to Live, APIs, logging, upgrades, and all supported AEM Guides Cloud versions.
- Preserve existing publishing profiles during upgrades and confirm no impact to Salesforce publishing.
- Verify the required AEM Admin suffix configuration change from `HTML` to `HTM`; keep the exact setting, scope, default, and upgrade behavior as open questions when Jira does not define them.
- Verify supported content publishes through both providers without content loss or formatting issues, including DITA topics, DITAMAPs, Bookmaps, Markdown, images, multimedia, MathML, tables, code blocks, cross-references, keyrefs, conrefs, conditional content, multilingual content, and other supported assets.
- Require logging for authentication, token exchange, publishing, commit creation, push operations, API failures, and retries when applicable.
- Verify Client Secret, Access Token, and OAuth Token values are never logged, exposed in UI errors, or returned through unsafe API responses.
- Derive positive, negative, provider/platform matrix, public/private repository, permission, authentication lifecycle, UI-state, API-contract, upgrade, logging/redaction, retry, pipeline-trigger, content-fidelity, and regression scenarios from this UAC.
- Keep unspecified details as open questions, including exact OAuth grant/token-exchange flow, redirect URI, scopes, token storage/refresh, provider-specific required fields, self-hosted TLS/proxy requirements, GitLab default URL behavior, branch protections, retry policy, rollback after partial commit/push failure, supported file-size limits, and the supported AEM Guides Cloud version matrix.
