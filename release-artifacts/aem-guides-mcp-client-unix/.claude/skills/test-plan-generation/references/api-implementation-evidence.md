# API / Operation / Backend Implementation-Evidence Protocol

Read this whenever a ticket concerns a **named code artifact** — a REST path, a
servlet operation, a handler method, a service class, or a config key (signals:
`/bin/...`, `/api/...`, "servlet", "endpoint", "REST/HTTP/public API", "operation",
"handler method", "response DTO", "API contract/signature"). It is the API analogue
of the DITA semantic-relationship protocol and the state-compatibility protocol: it
stops acceptance criteria from being written out of the ticket's prose without ever
reading the code.

## Why this exists

A ticket's account of *current* behaviour is frequently stale or incomplete. A
premise such as "the generate call returns no job id" can already be false in the
current build. Writing ACs from that premise produces criteria that (a) restate the
ask, (b) accept an outdated premise as fact, and (c) invent generic ACs (auth,
performance) that no code was checked for. The fix is mandatory grounding: read the
handler, then write the AC.

## Procedure

1. **Identify the named artifacts.** From the summary/description/behaviour model,
   list every REST path, servlet operation, handler method, service class, and config
   key the ticket concerns.
2. **Locate and read each handler** in the product clone (`C:\starling`,
   `core/publish-listener/`, `core/publish-workflow/`, etc.) or via GitHub MCP — the
   servlet dispatch, the operation branch, and the response DTO it writes. Do not stop
   at the ticket text or a file name.
3. **Verify the ticket's current-behaviour premise against the code.** Record whether
   the code confirms it (`premise_holds`). If the code contradicts the premise (e.g. a
   job id is already returned), the AC must reflect the code, not the ticket.
4. **Ground every current-behaviour AC / Expected Behaviour bullet in a `file:line`.**
   An assertion about what the API does today with no cited handler is a gate failure.
5. **Only then** derive the enhancement/gap ACs, the regression ACs (which callers /
   dashboards consume the same operation?), the auth/permission ACs (what session /
   tenant gate does the handler actually run under?), and the open questions.

## Manifest block (enforced by `run_gates.py`)

Declare `implementation_grounding` when API/operation/backend artifacts are in scope:

```json
"implementation_grounding": {
  "active": true,
  "named_artifacts": [
    {
      "artifact": "/bin/publishlistener GENERATEOUTPUT",
      "kind": "operation",
      "inspected": true,
      "evidence": ["PublishOutputService.java:182"],
      "material": true,
      "premise": "the generate call returns no job id",
      "premise_verified": true,
      "premise_holds": false,
      "note": "code shows generationId IS returned; ticket premise is outdated"
    }
  ]
}
```

- `kind` ∈ `api | operation | handler | method | service_class | config_key`.
- Every `material` artifact must be `inspected: true` with at least one `file:line`
  `evidence` entry.
- If a ticket `premise` about current behaviour is stated, `premise_verified` must be
  `true` (with cited evidence) and `premise_holds` must record whether the code agrees.

If the block is absent but the plan names an API artifact **and** asserts current
behaviour about it, the gate fails: read the handler and cite it first. This is
generic — it hardcodes no endpoint, operation, or class.

### `premise_holds` is a tri-state, not just true/false

`premise_holds` accepts `true`, `false`, or the string `"unresolved"`. Use `unresolved`
only when the code was genuinely inspected but cannot confirm **or** refute the ticket's
premise — most commonly because the real logic is delegated to a dependency this session
cannot reach (see `dependency_resolution` below), or the claimed behaviour depends on
runtime state no static read can settle. `unresolved` requires a `premise_note` explaining
what was searched and why it fell short; it is not an escape hatch from actually looking,
and the resulting gap should normally also be carried as an Open Question.

### Dependency-delegated implementation (`dependency_resolution`)

When the artifact's real logic lives in an external or vendored package (not the
ticket's own repo) — for example an XML-editor feature implemented in `@rh/jui-app` —
record how that dependency was resolved on the artifact:

```json
{
  "artifact": "updateTagViewAttributeFriendlyNames",
  "kind": "method",
  "inspected": true,
  "evidence": ["FullTagsView.js:88"],
  "material": true,
  "premise": "friendly names update live when the workspace config changes",
  "premise_verified": true,
  "premise_holds": "unresolved",
  "premise_note": "the friendly-name lookup itself is delegated to @rh/jui-app; the call site is guarded here but the dependency's own behaviour could not be inspected",
  "dependency_resolution": {
    "status": "UNRESOLVED_NO_ACCESS",
    "external_package": "@rh/jui-app",
    "note": "no local clone of @rh/jui-app and GitHub MCP is unavailable this session"
  }
}
```

`dependency_resolution.status` ∈ `RESOLVED_LOCAL_CLONE | RESOLVED_GITHUB_MCP |
UNRESOLVED_NO_ACCESS | NOT_APPLICABLE`. Only `UNRESOLVED_NO_ACCESS` requires a `note`.
This field is optional and only validated when declared — it does not retroactively
block plans that never used it.

## Comment-claim verification (`comment_claims`)

A Jira comment that asserts something about **current** code/behaviour — an author's
RCA ("there is no DB-mode gate here"), a reviewer's finding ("this reads the wrong
property"), or a "Fix Ready" note — is exactly as capable of being stale as the ticket's
own description, and for the same reason: it records what someone believed at the time
they wrote it, not what the current diff does. Treat such a comment as a claim to verify,
never as ground truth to restate in an AC.

When the plan relies on (or explicitly rules out) such a comment, record it:

```json
"comment_claims": [
  {
    "claim": "there is no DB-mode gate before the cleanup job runs",
    "comment_source": "author_rca",
    "verification_status": "VERIFIED_FALSE",
    "evidence_ids": ["E9"],
    "note": "MapDeleteParentMapsCleanupHandler.java:41 checks isDbMode() before enqueueing; the comment predates that guard"
  }
]
```

- `comment_source` ∈ `author_rca | reviewer_finding | reporter_note | fix_ready_note | other_comment`.
- `verification_status` ∈ `VERIFIED_TRUE | VERIFIED_FALSE | STALE_SUPERSEDED | UNVERIFIABLE`.
- `VERIFIED_TRUE` / `VERIFIED_FALSE` / `STALE_SUPERSEDED` must cite `evidence_ids` from
  the diff/code actually checked — not just restate the comment.
- `UNVERIFIABLE` must carry an `open_question_ref` rather than being silently dropped.

This block is optional — omitting it is not a failure. But if comment text in the
manifest's `issue.comments` looks like a current-behaviour claim (phrases like "there is
no", "currently does not", "wrong property", "already fixed") and nothing is recorded,
`run_gates.py` prints a non-blocking `REVIEW comment-claims` note naming the candidate
text, so the omission is visible rather than silent.
