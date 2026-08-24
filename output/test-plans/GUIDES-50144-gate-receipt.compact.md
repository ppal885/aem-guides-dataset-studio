**Acceptance Criteria**
- AC-01
  - Starting point: a delegated folder-profile admin without local administrator membership.
  - Action: the admin adds another Admin User to the same non-global profile.
  - Expected result: the added user remains in Admin Users after a page refresh.

- AC-02
  - Starting point: a delegated folder-profile admin without local administrator membership.
  - Action: the admin removes an Admin User from the same non-global profile.
  - Expected result: the removed user stays absent after a page refresh.

- AC-03
  - Starting point: a member of the exact local administrators group uses a non-global folder profile.
  - Action: the administrator adds or removes one Admin User.
  - Expected result: the requested membership change remains saved after refresh.

- AC-04
  - Starting point: a delegated folder-profile admin opens the global folder profile.
  - Action: the admin submits an Admin Users change.
  - Expected result: the global Admin Users list stays unchanged.

- AC-05
  - Starting point: an unauthorized user has neither target-profile admin membership nor local administrator membership.
  - Action: the user submits an Admin Users change.
  - Expected result: the client reports an authorization error without changing stored membership.

**Test Scenarios**
- Test data to prepare: on an AEM Guides Cloud Service Stage build containing commit eac2c72512306061d2110b02e03d28197eadeecf, create non-global profile fp-50144-a for `/content/dam/guides-50144`; verify its exact group is `folderprofile-fp-50144-a`; prepare delegated user d-admin, local administrator l-admin, unauthorized user u-author, and candidate user new-admin. Give u-author the Jira-listed non-authorizing groups authors, Contributors, AEM Administrators author Program 167205 Environment 1910614, everyone, AEM Assets Collaborator Users - Service, AEM Sites Content Managers - Service, AEM Administrators - Service, and Analytics Administrators. Withhold exact `administrators` and `folderprofile-fp-50144-a`. Use a full browser refresh plus fresh profile and group reads as persistence oracles.
- Actor matrix - delegated folder-profile admin: grant authors and `folderprofile-fp-50144-a`; withhold exact `administrators`; the Folder Profile assignment auto-adds `folderprofile-fp-50144-a`; use this actor for AC-01, AC-02, and AC-04.
- Actor matrix - local administrator: grant exact `administrators`; do not require `folderprofile-fp-50144-a`; no Folder Profile group is auto-added for setup; use this actor for AC-03.
- Actor matrix - unauthorized user: grant all eight Jira-listed non-authorizing customer groups, including the similarly named Program and Service administrator groups; withhold exact `administrators` and `folderprofile-fp-50144-a`; no Folder Profile group is auto-added; use this actor for AC-05.
- Actor matrix - candidate user: grant authors; start outside exact `administrators` and `folderprofile-fp-50144-a`; AC-01 should auto-add the profile group, and AC-02 should remove it when the candidate is removed from Admin Users.
- P0 [TS-01] [AC-01]: Action: Sign in as d-admin, add new-admin to Admin Users for fp-50144-a, save, and refresh the page. Expected: new-admin remains listed and belongs to `folderprofile-fp-50144-a` after the fresh read.
- P0 [TS-02] [AC-02]: Action: Sign in as d-admin, remove new-admin from Admin Users for fp-50144-a, save, and refresh the page. Expected: new-admin stays absent and no longer belongs to `folderprofile-fp-50144-a` after the fresh read.
- P1 [TS-03] [AC-03]: Action: Sign in as l-admin, add new-admin, verify it, then remove new-admin from fp-50144-a. Expected: both requested changes remain saved after refresh.
- P1 [TS-04] [AC-04]: Action: Sign in as d-admin and try the same Admin Users request against the global profile. Expected: global-profile membership stays unchanged after a fresh read.
- P0 [TS-05] [AC-05]: Action: Sign in as u-author with all eight non-authorizing customer groups and submit an Admin Users change for fp-50144-a. Expected: the request shows an authorization error and a fresh read shows the original membership.
- P1 [TS-06] [AC-01, AC-02]: Action: Repeat add and remove through the direct UPDATEFOLDERPROFILE request, then read the profile and target group from the repository. Expected: the API, profile response, and declared group membership report the same saved user set.
- Implementation gap: TS-05 is expected to fail on the currently inspected PR #8091 result because the unauthorized path still returns HTTP 200 with true and drives the UI success message.
- P3 [Regression]: Action: Validate Re-test the global-profile boundary through the visible UI and a direct request because the widened role condition relies on the existing non-global guard to prevent delegated access from becoming global access. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Confirm that global-profile authorization is unchanged for both add and remove requests; the non-global permission must not broaden that boundary. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test local administrators on non-global profiles because widening the condition must preserve the existing broad administrator path while adding the delegated path. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test profile configuration updates for conditional attributes, templates, and output presets because that sibling update path reuses the moved isFolderAdmin value even though PR #8091 does not intentionally change it. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test new-profile group creation and Admin User synchronization because authorization depends on the stored group ID and exact declared membership, including add and remove operations. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test the UI success and error messages against actual HTTP outcomes because the current done callback reports success for the unauthorized no-op response and can hide a failed persistence result. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.

**Jira Tickets Worth Checking**
- No same-mechanism Jira ticket is worth checking from the validated evidence.

**Automation Coverage**
- Main feature coverage: Not covered - based on direct automation evidence for 3 AC mapping(s).
- AC-01, AC-02: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-03, AC-04: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-05: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
