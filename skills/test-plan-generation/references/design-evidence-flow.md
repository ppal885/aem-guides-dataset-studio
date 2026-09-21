# Design Evidence Flow

Use this before relying on Figma links, prototype links, frame names, screenshots, or design notes for a test plan.

## When To Use Figma MCP

- Use Figma MCP read-only when Jira, PR, comments, attachments, or the user provides a Figma/design/prototype link.
- Use Figma MCP when the ticket changes UI layout, dialogs, menus, upload/status flows, navigation, review workflows, editor panels, assets UI, dashboards, or error/empty/loading states.
- If the ticket is UI-heavy but no design link is available, ask for the design link only if it materially affects expected behaviour; otherwise add a Draft blocker.
- Do not use Figma MCP for writing or changing designs during test-plan generation.

## Deep Analysis Checklist

- Identify the exact file, page, frame, component, or prototype inspected.
- Map the user journey: entry point, primary action, decision point, success path, cancel/back path, and recovery path.
- Capture visible states: default, hover/focus if relevant, loading/progress, empty, error, disabled, selected, completed, cancelled, aborted, resumed, and overwritten.
- Capture dialog/toast/copy details only when they are central to QA expectations.
- Capture component variants and responsive states when the same component appears in multiple layouts.
- Check role, permission, tenant, cloud/on-premise, browser, locale, and theme assumptions if visible or documented in the design.
- Compare Figma flow against Jira UAC, RAG product rules, PR diff, and existing UI behaviour from local repos.
- Record contradictions as Draft blockers instead of silently choosing one source.

## Evidence Rules

- Figma proves intended UI flow and visual/state expectations, not backend persistence, API contracts, permissions, versioning, or database behaviour.
- Jira remains the source for acceptance criteria and business intent.
- RAG remains the source for documented product behaviour and configuration rules.
- PR/repo evidence remains the source for changed code, touched components, and line counts.
- Screenshots are weaker than Figma MCP inspection; mark them as screenshot-based evidence.
- An inspected screenshot or user-provided visual that names a surface, visible
  artifact/control, and state variants activates
  `attachment-visual-reference-coverage.md`. Record its visible facts as observation
  evidence only; it cannot establish the desired state or broad parity on its own.
- When current evidence names a control that edits a value and a distinct surface that
  displays or tag-renders it, record the writer/reader pair in the same reference
  contract. The evidence can establish the named relationship, but Jira, the user, or
  an accepted product source must establish the expected read-after-write result.
- A configured or documented outcome does not prove a selectable UI option/action.
  When an AC asserts an existing action, require current evidence that names that
  action on the applicable surface through the UI-action/surface contract; do not
  infer a control from its effect. Preserve a source-backed desired outcome even
  when the existing-action claim is unsupported, and expose that implementation gap
  as an Open Question rather than silently dropping ticket scope.
- If Figma access fails, write `Draft blocker: Figma design evidence not inspected`.

## How To Use In Final Plan

- Put design-backed behaviour under `Expected Behaviour`, for example upload progress, cancel/resume affordance, rename dialog, or disabled state.
- Put the design source/access state under `Scope From Git` because no extra section is allowed.
- Convert design states into `Test Scenarios`, especially progress, cancel, resume, overwrite, rename, error, and boundary UI states.
- Put nearby components, reused dialogs, variants, responsive states, and stale design/code mismatches under `Regression Areas`.
- Do not paste raw Figma JSON, node dumps, layer trees, or screenshots unless the user asks.
