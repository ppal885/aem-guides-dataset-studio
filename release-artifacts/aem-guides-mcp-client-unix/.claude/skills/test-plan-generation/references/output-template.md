# Output Template

Use this file before writing the final user-facing plan.

## Required Shape

Use exactly these sections. Keep every line as a bullet.

```markdown
**Acceptance Criteria**
- ...

**Expected Behaviour**
- ...

**Scope From Git**
- ...

**Code Touched**
- ...

**Lines Changed**
- ...

**Test Scenarios**
- P0: ...
- P1: ...
- P2: ...

**Past Similar Tickets**
- ...

**Regression Areas**
- ...
```

## Writing Style

- Write like a manual QA engineer: direct action, observable result, no implementation jargon unless needed.
- Prefer “Verify that…” and “Confirm that…” over vague words like “check properly”.
- Keep bullets short enough to scan.
- Put missing evidence in the section it affects: `Draft blocker: ...`
- Do not create extra sections.
- Do not use tables.

## Scenario Formula

Use:

`- P0: <action/test data/config/user role> -> <expected observable result>.`

Examples:

- `P0: Create a translation project from a map with postprocessing enabled -> project creation completes and generated assets remain under the expected DAM path.`
- `P1: Repeat the workflow for a child folder ignored for postprocessing -> child and successor folders are skipped consistently.`
- `P2: Refresh the UI after the operation -> status, toast, and persisted state remain consistent without duplicate actions.`

## Sample Draft

```markdown
**Acceptance Criteria**
- Verify that the configured workflow completes for the affected user role.
- Verify that invalid or unsupported input is blocked with a clear error.
- Draft blocker: Jira acceptance criteria are incomplete; confirm final sign-off conditions.

**Expected Behaviour**
- AEM Guides should follow the documented configuration rule returned by accepted RAG evidence.
- The UI should show the final status without requiring a manual refresh.
- Unknown from current evidence: exact behaviour for upgraded instances was not confirmed by Jira or RAG.

**Scope From Git**
- PR inspected: <PR URL>; changed area is <component/workflow>.
- Repo sync state: fetched and clean/up to date before diff inspection.

**Code Touched**
- `<file>`: affects <workflow/API/UI state>, so QA should verify <impact>.

**Lines Changed**
- `<file>`: +12/-4; key hunk changes validation before save.

**Test Scenarios**
- P0: Run the primary Jira workflow with valid data -> operation succeeds and expected UI/API state is persisted.
- P0: Run the workflow with the Jira failure condition -> previous failure does not reproduce.
- P1: Use invalid or boundary input -> user sees a clear error and no partial state is saved.
- P1: Repeat after browser refresh/session reload -> state remains consistent.
- P2: Verify nearby workflow that shares the touched component -> no regression in existing behaviour.

**Past Similar Tickets**
- `GUIDES-xxxxx`: similar because <reason>; adds coverage for <area>.
- Draft blocker: historical Jira MCP/JQL was unavailable, so similar-ticket coverage is incomplete.

**Regression Areas**
- Shared validation/API path used by <nearby workflow>.
- Role/permission combinations around <feature>.
- Config/version boundary around <setting/release>.
```
