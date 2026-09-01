# FJ-02 v2 - FluffyJaws Capability Contract (Programmatic Access Update)

> Versioned update for `FJ-PROGRAMMATIC-ACCESS-UPGRADE`. **Non-destructive**: the
> original `02_capability_contract.md` (audit of 2026-08-28) remains authoritative
> historical evidence and is NOT overwritten. This file reconciles the newly
> supplied "official contract" facts against that captured evidence.

## Result (unchanged from FJ-02)

- `STATUS = BLOCKED`
- `INTEGRATION_MODE_AVAILABLE = BOTH`
- `API_SUPPORTED = YES` (contract established)
- `REMOTE_MCP_SUPPORTED = YES` (transport identified; tool I/O schema NOT available here)
- `LOCAL_MODE_CONFIGURED = NONE`
- `SERVICE_APP_REQUIREMENT = YES (human-only registration; not performed)`
- `PROVIDER_INTEGRATION_READY = false`

The upgrade requested by `FJ-PROGRAMMATIC-ACCESS-UPGRADE` **cannot be implemented
in this environment**, for the *same two contract reasons* recorded in FJ-02.
Nothing in the new prompt changes them.

## Why still BLOCKED (verified 2026-09-01)

1. **No configured programmatic identity.** `LOCAL_MODE_CONFIGURED = NONE`: no
   `fj` CLI, no `fj login` session, no MCP server entry, no registered service
   identity, no FluffyJaws credential variable. Remote MCP (`POST /api/v1/mcp`)
   is **restricted to approved services / hosted integrations with authorization
   coordinated with the FluffyJaws team** (FJ-02 captured evidence). That approval
   and the service-app registration are **human-only** prerequisites (see §9, §26
   of the upgrade prompt) and have not been done.
2. **MCP tool I/O contract is not available here.** The captured docs identify the
   transport and a `fluffyjaws_chat` tool but **delegate the full JSON-RPC /
   tools-list / tools-call input+output schema to an operator guide not present**
   in this environment. The public HTTPS API still exposes **no stable structured
   citation/source schema** for a generated answer. Implementing an MCP or `/api/v1`
   transport now would require *inventing* tool names, payloads, headers, scopes,
   or token-exchange formats - **explicitly forbidden** by upgrade-prompt §2, §6,
   §7, and the no-hardcoding gate §28.
3. **Docs are not independently re-readable.** On 2026-09-01, `https://fluffyjaws.adobe.com/docs/mcp`
   returned `307 -> adobe.okta.com/oauth2/v1/authorize` (Adobe Okta OAuth). The
   OAuth flow was **not** followed (prohibited). The only FluffyJaws doc authority
   available is the FJ-02 read-only capture of 2026-08-28.

## Captured authority (from FJ-02, 2026-08-28 - do not re-derive)

- `API_BASE = https://api.fluffyjaws.adobe.com`, public contract `/api/v1/*`.
- Discovery/startup: `GET /api/v1`. Contract headers `X-FluffyJaws-Api-Version: v1`,
  `X-FluffyJaws-Api-Stability: public`. Undocumented routes are private.
- `MCP_ENDPOINT = POST /api/v1/mcp` (remote, approval-gated). Local MCP =
  `fj-mcp --api https://api.fluffyjaws.adobe.com`, reusing an `fj login` session.
  Native Claude connector = Adobe enterprise remote MCP via Adobe sign-in/OAuth
  (users must NOT configure its endpoint manually).
- `SERVICE_APP_REQUIREMENT = YES`; registration is human-only and governed.

## Reconciliation with the new prompt's "confirmed" facts

| Field | Upgrade prompt states | FJ-02 captured docs (authority) | Action |
|---|---|---|---|
| API base | `https://fluffyjaws.adobe.com/api/v1` | `https://api.fluffyjaws.adobe.com` + path `/api/v1/*` | **Discrepancy.** Keep captured `api.` origin; the provider (`_DEFAULT_BASE_URL`) already uses it. A human must confirm which origin the FJ team means before any change. |
| Remote MCP | supported over HTTP | `POST /api/v1/mcp`, approval-gated | Consistent. |
| Auth modes | session / bearer / service / OBO (X-User-Token) / A2A | session + service identity + governed registration documented; OBO/A2A exact token-exchange **not in captured evidence** | Do not implement OBO/A2A token exchange from prompt text alone - schema unknown here. |
| App registration | human-only at `/integrations/apps` | human-only, governed | Consistent. Preserved. |

## What an upgrade WOULD require (hand-off, not implemented)

A human must, outside this environment:

1. Register the QE service app at `https://fluffyjaws.adobe.com/integrations/apps`
   (or obtain remote-MCP approval from the FluffyJaws team).
2. Obtain the **operator guide** that specifies the MCP `tools/list` / `tools/call`
   JSON-RPC input+output schemas and the API citation/source schema.
3. Supply resulting credentials **only** via approved secret/config injection
   (never committed, logged, or cached with evidence).

Only after (1)-(3) can transport selection (Remote MCP vs `/api/v1`), the auth
adapter, OBO, and the FJ-11 shadow / FJ-19 ablation re-runs proceed **without
inventing** any wire contract.

## Non-goals honored

- No provider code changed. `FluffyJawsKnowledgeProvider` transport seam
  (`FluffyJawsTransport` Protocol + injected auth-owning client) is already the
  correct extension point; no `FluffyJawsProviderV2` / duplicate retriever created.
- Authority model (SUPPORTING_DISCOVERY only; no direct FJ->AC) untouched.
- Default mode remains `FLUFFYJAWS_DISABLED`.
