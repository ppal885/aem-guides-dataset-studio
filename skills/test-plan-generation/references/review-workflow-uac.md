# Review Workflow Contract

Use this generic reference when current evidence names review tasks, review comments, author incorporation, a review panel, task selection/state, comment import, version comparison, or review-task details. It is not a gold-ticket prompt. Current accepted scope and verified current implementation/design decide every surface, actor, state, label, default, permission, and action.

## Scope and Identity

- Record the named actor/role, editor/surface, topic/file identity, review-task identity, task states, selected/default task rule, topic version, comment thread identity, and feature-flag/configuration boundary.
- Keep task membership, selected task, current/open/closed state, topic version, comment visibility, import eligibility, editability, search/filter scope, and diff comparison as separate dimensions.
- Do not assume a right panel, dropdown, `Current` tag, details icon, feature flag, both editors, attachment support, or revert behavior unless current evidence places it in scope.
- When a topic belongs to multiple tasks, derive the list and default selection from the approved task-membership/state contract. Never use a historical UI default as authority.

## Generic Behavior Relationships

- Changing the selected task updates only consumers verified to read selected-task state. Comments or metadata from another task/topic must not leak into the result.
- Read-only, editable, and importable states require independent permission and task-state rules.
- Search/filter operates on the approved loaded scope; hidden/unloaded task data must not influence results unless current evidence explicitly requires cross-task search.
- Version comparison must name both sides, the topic/file identity, and which comments/tags/replies/attachments belong to the selected version.
- Switching topics resets or preserves task selection only according to the approved state contract.
- User/reviewer display names and fallback behavior require current UI/implementation evidence; historical screenshots cannot set the label/fallback.
- Feature/configuration OFF, ON, activation boundary, first-render state, and rollback behavior are separate facts.

## Test Oracles

- Use fixtures with distinct task IDs, topic IDs, states, project metadata, comment authors, tags, replies, and version content so cross-task/topic leakage is visible.
- Verify visible task list and selected state against repository/API membership, not UI text alone.
- Verify task switching changes each in-scope consumer once and leaves unrelated topic/task data unchanged.
- Verify denied or read-only actions remain unavailable and do not mutate comments or topic content.
- Verify import or incorporation changes only the approved target version/content and is idempotent or duplicate-safe according to current evidence.
- Verify comparison output identifies the correct versions and associated annotations; a diff window opening is not enough.

## Required Open Questions

- Which actor roles and permissions can view tasks/comments, import/incorporate comments, open details, compare versions, or download attachments?
- Which task states are supported, what exact labels are shown, and which state/task is selected first?
- Which editor/surfaces are in scope and do they share state/implementation?
- What feature/configuration key, default, activation boundary, and OFF/ON presentation apply?
- Are previous-task comments read-only, searchable/filterable, importable, or editable?
- Which versions are compared, and are tags, replies, attachments, and revert actions included?
- What happens when task membership changes, the selected task closes/deletes, permissions change, or the open topic changes?
- What fixture represents multiple tasks and versions without relying on historical customer data?
