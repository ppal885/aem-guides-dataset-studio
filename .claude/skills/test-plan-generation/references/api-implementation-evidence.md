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
