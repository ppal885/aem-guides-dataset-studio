# Quality Gate Checklist

Use this before calling a test plan review-ready.

## Evidence Gate

- Jira facts are present from Jira MCP, Jira REST fallback, or user-pasted Jira details.
- Acceptance criteria are explicit, or missing AC is marked as a Draft blocker.
- `ask_dita_expert` was used for behaviour facts unless the task is strictly code-only.
- RAG evidence was accepted only when direct and rejected when generic/noisy.
- Past similar tickets were searched through Jira MCP/JQL, user-provided tickets, or available team memory.
- PR/branch/commit/pasted diff was inspected when fix-impact claims are included.
- Changed files/functions and line counts come from real PR/Git evidence.
- Local repo evidence states fetch/sync status and is not used as final proof when dirty, stale, diverged, or unsynced.

## Draft When

- Jira facts are missing or too vague.
- RAG is down, noisy, unrelated, or unavailable for a behaviour claim.
- Historical Jira search was not possible and similar tickets matter for coverage.
- PR/diff was not inspected but the plan claims code impact.
- Line counts or key hunks are unavailable.
- Repo evidence is dirty, stale, behind, diverged, or not fetched.
- Expected behaviour depends on an unverified product assumption.

## Review-Ready When

- Each expected-behaviour bullet is backed by Jira, accepted RAG, PR diff, or explicitly marked unknown.
- Each P0/P1 scenario maps to AC, expected behaviour, PR diff, past Jira learning, or a high-risk regression.
- Scope, code touched, and lines changed cite real PR/Git evidence.
- Past similar tickets either list useful matches or clearly state no matches/evidence unavailable.
- Regression areas are specific to touched code and learned product behaviour, not generic module names.

## Anti-Patterns To Block

- Tables.
- Extra headings outside the required eight sections.
- Raw RAG chunks, scores, JSON, backend traces, or evidence matrices in the final plan.
- “Proper RAG-backed” claims when evidence is only keyword-matched.
- Test scenarios that say only “verify functionality” without action + expected result.
- Confident product behaviour based only on memory, code names, or broad docs.
