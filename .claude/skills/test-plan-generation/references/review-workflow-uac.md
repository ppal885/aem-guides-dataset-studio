# Review Workflow UAC

Use this file when Jira scope mentions review tasks, review comments, author incorporation of final review comments, editor review right panel, selected/current/closed review task state, review-task dropdowns, read-only review comments, comment import, side-by-side diff, or review-task details.

## Gold Reference: Review Task History Panel For Current Topic

Use this as the quality bar for tickets where authors need to view current and previous review tasks for the currently open topic inside a new review panel/workflow. The important quality signal is that task selection changes the visible read-only comments and task metadata without mixing comments from other tasks or topics.

**Scope**

- Persona is Author, because final review comments are incorporated by authors.
- Show open and closed review tasks that contain the currently open topic.
- Provide a dropdown listing review tasks that contain the topic.
- Show task state such as active/current/open or closed.
- Show project name and task details through the details icon.
- Show previous versions of the topic for the selected review task as read-only.
- Show diff between the current task working copy and the previous topic version with comments incorporated.
- Keep changes behind the required feature flag.
- Validate compatibility with both editors only after dev/PM confirms both editors are in scope.

**UAC**

- If a topic belongs to multiple review tasks, open or closed, all matching tasks must be listed in the right-panel dropdown.
- The initially selected review task should be the current review task and should show a `Current` tag.
- Changing the selected review task updates the right panel with that task's review information, state, project name, and task details.
- Comments from the selected review task appear in read-only mode and are specific to the current file/topic.
- Only comments from the current review task can be imported; import is disabled for previous or closed review tasks.
- Filtering and search operate only on the selected review task's loaded comments and are not affected by comments from other unloaded tasks.
- The side-by-side view shows selected task comments for that topic version, including comments, tags, and replies.
- Attachment download behavior in side-by-side view is a confirmation point and should not be assumed until owner/dev confirms it.
- Changing the topic in the editor resets the right panel to the current review task for the newly opened topic.
- Reviewer and user names in comments and replies must render correctly and follow existing fallback behavior.
- Revert-version behavior is an open question and must be confirmed before QA treats it as in scope.

**Test Cases To Verify**

- Verify an author opening a topic that is part of one active review task sees that task selected with the `Current` tag.
- Verify an author opening a topic that belongs to multiple open and closed review tasks sees all matching tasks in the right-panel dropdown.
- Verify selecting a closed review task updates task state, project name, task details, and comments for that selected task only.
- Verify comments from a previous or closed task are read-only and cannot be edited or imported.
- Verify the import option remains enabled only for the current review task and is disabled for all previous or closed review tasks.
- Verify search filters only the loaded comments for the selected review task and does not match hidden or unloaded comments from other tasks.
- Verify comment filters apply only to the selected task and preserve the selected task state after clearing filters.
- Verify side-by-side diff opens from the diff icon and compares the current task working copy against the selected previous topic version.
- Verify side-by-side diff displays comments, tags, and replies for the selected topic version.
- Verify attachment visibility or download in side-by-side view only if confirmed in Jira/dev comments; otherwise keep it as an open question.
- Verify switching the open topic in the editor resets the right panel to the current review task for the new topic.
- Verify user/reviewer names in comments and replies display correctly, including fallback cases for missing profile fields.
- Verify feature flag off hides or disables the new panel/workflow and preserves existing review behavior.
- Verify feature flag on enables the new panel/workflow without regressing existing current-review comments.
- Verify both editors only if confirmed in scope; otherwise mark editor compatibility as an open question.

**Regression Areas To Carry Forward**

- Editor review right panel task selection and reset behavior.
- Review task dropdown population for current topic membership.
- Current/open/closed task state labels and `Current` tag rendering.
- Project name and review task details icon.
- Read-only rendering for previous or closed task comments.
- Import-comment eligibility and disabled-state logic.
- Search and filter scoping to selected task comments.
- Side-by-side diff launch and topic version comparison.
- Comments, tags, replies, and attachment handling in side-by-side view.
- User/reviewer display names and existing fallback behavior.
- Feature flag on/off behavior and rollback safety.
- Old editor and new editor compatibility if both are confirmed in scope.
- Automation coverage for review panels, dropdown selection, search/filter, import disabled state, and topic-switch reset.

**Open Questions To Carry Forward**

- Feature flag: What is the exact flag name, default state, and environment where QA should validate on/off behavior?
- Editor compatibility: Are both old editor and new editor in scope, and are there any known UI differences?
- Revert version: Is revert-version behavior in scope, and what should happen for previous or closed review tasks?
- Attachments: Should side-by-side view show, preview, and download comment attachments for the selected review task?
- Search/filter: Should search and filter remain available for non-current tasks, or should they be removed if unsupported?
- Task states: What exact labels should be shown for active/current/open and closed tasks?
- Permissions: Which author roles can view previous task comments, import current comments, open task details, and open side-by-side diff?
- Data setup: What fixture should QA use for a topic present in multiple open and closed review tasks with comments, tags, replies, and attachments?
