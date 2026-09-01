# FluffyJaws Integration — Setup & Programmatic-Access Hand-off

This is the operator hand-off for enabling the **existing** FluffyJaws QE evidence
provider. It documents the human-only prerequisites, the secure configuration a
human must supply, how the runtime is switched on, and how to verify health.

It is **not** an architecture guide — see the FJ-00…FJ-19 artifacts under
[`analysis/fluffyjaws/`](../analysis/fluffyjaws/) and the versioned contract
[`02_capability_contract_v2.md`](../analysis/fluffyjaws/02_capability_contract_v2.md).

> **Current status: BLOCKED / default-off.** The provider ships disabled
> (`FLUFFYJAWS_DISABLED`) and makes **zero** network calls until a human completes
> the steps below. Do not enable it in production merely because programmatic
> access exists.

---

## 1. What a human must register (cannot be automated)

App/service registration is **human-only** and governed. The QE application must
**never** self-register.

1. Sign in to `https://fluffyjaws.adobe.com` (Adobe Okta SSO).
2. Register a service app at `https://fluffyjaws.adobe.com/integrations/apps`,
   **or** request remote-MCP access — remote MCP (`POST /api/v1/mcp`) is
   restricted to approved services / hosted integrations and requires
   authorization coordinated with the FluffyJaws team.
3. Obtain the **operator guide** that specifies the MCP `tools/list` / `tools/call`
   JSON-RPC input+output schemas (and, for the HTTPS API, the citation/source
   schema). Without it, transport wiring cannot proceed — the public docs delegate
   these schemas to that guide, and they must **not** be guessed.
4. Confirm with the FluffyJaws team the **canonical API base**. The captured docs
   and the current code use `https://api.fluffyjaws.adobe.com`; the newer
   integration note cites `https://fluffyjaws.adobe.com/api/v1`. Do not change the
   code base URL until this is confirmed.

Until (1)–(3) are done, the honest provider state is `SERVICE_APP_NOT_CONFIGURED`
and the integration stays disabled — no insecure/anonymous fallback.

---

## 2. Configuration a human must supply (securely)

### 2a. Authentication (code-injected, never in env/plaintext)

By design, `FluffyJawsKnowledgeProvider` **does not read credentials, env vars,
cookies, or CLI sessions**. Authentication is owned by an injected HTTP client
passed through `build_fluffyjaws_provider(transport_factory=...)`
(see [`fluffyjaws_knowledge_provider.py`](../backend/app/services/fluffyjaws_knowledge_provider.py)).

The transport factory must build an `httpx.Client` already configured with the
approved auth for the chosen mode:

| Mode | How the injected client authenticates |
|---|---|
| `SESSION_AUTH` | reuses an `fj login` session (local `fj-mcp`) |
| `USER_BEARER` | `Authorization: Bearer <user token>` on the client |
| `SERVICE_AUTH` | registered service identity credential |
| `OBO` | service auth **plus** `X-User-Token` for a real, user-scoped request only |

Supply secrets **only** through your approved secret-injection mechanism
(vault / CI secret / OS keyring wired into the transport factory).

**Never** commit, log, print, cache-with-evidence, or persist: Bearer tokens,
service credentials, `X-User-Token`, session cookies, or client secrets. The
provider redacts these defensively, but the operator must not introduce them into
config files, `.env`, traces, or test fixtures.

### 2b. Runtime knobs (safe, non-secret — env-configured)

Read by the shadow runtime
([`reasoning_evidence_shadow_service.py`](../backend/app/services/reasoning_evidence_shadow_service.py)):

| Env var | Default | Bounds | Purpose |
|---|---|---|---|
| `FLUFFYJAWS_MODE` | `FLUFFYJAWS_DISABLED` | `DISABLED` / `SHADOW` / `SECOND_PASS` | Master switch |
| `FLUFFYJAWS_SHADOW_MAX_QUESTIONS` | `20` | 1–50 | Questions considered per run |
| `FLUFFYJAWS_SHADOW_MAX_RESULTS` | `5` | 1–100 | Results per call |
| `FLUFFYJAWS_SHADOW_CALL_TIMEOUT_SECONDS` | `300` | >0, ≤300 | Per-call timeout |
| `FLUFFYJAWS_SHADOW_TOTAL_TIMEOUT_SECONDS` | `300` | >0, ≤900 | Per-run total timeout |
| `FLUFFYJAWS_RETRY_MAX_ATTEMPTS` | `2` | 1–3 | Retry attempts |
| `FLUFFYJAWS_CACHE_ENABLED` | `false` | `true`/`false` | Response cache (never caches credentials) |
| `FLUFFYJAWS_CACHE_TTL_SECONDS` | `60` | >0, ≤3600 | Cache TTL |
| `FLUFFYJAWS_CACHE_MAX_ENTRIES` | `128` | 1–4096 | Cache size |
| `FLUFFYJAWS_CACHE_MAX_BYTES` | (bounded) | — | Cache byte cap |
| `FLUFFYJAWS_CIRCUIT_FAILURE_THRESHOLD` | `3` | 1–20 | Circuit-breaker trip count |
| `FLUFFYJAWS_CIRCUIT_COOLDOWN_SECONDS` | `30` | >0, ≤3600 | Breaker cooldown |
| `FLUFFYJAWS_CIRCUIT_MAX_ENTRIES` | `512` | 1–4096 | Breaker tracking size |

---

## 3. Runtime modes

| Mode | Network calls | Effect on UAC |
|---|---|---|
| `FLUFFYJAWS_DISABLED` (default) | none | Baseline; FJ never runs |
| `FLUFFYJAWS_SHADOW` | may call | Evidence stored for trace/evaluation only; **final UAC stays baseline-equivalent** |
| `FLUFFYJAWS_SECOND_PASS` | may call | Conservative FJ-07 routing controls influence; still `SUPPORTING_DISCOVERY` |

**Authority invariant (unchanged, non-negotiable):** FluffyJaws synthesis is
`SUPPORTING_DISCOVERY` only. An underlying official/spec source discovered *through*
FluffyJaws keeps its own source identity and authority. FluffyJaws evidence
**cannot directly promote an acceptance criterion**; there is no FJ → AC path.

Recommended rollout: `DISABLED` → `SHADOW` (evaluate) → `SECOND_PASS` (only after
shadow shows no material UAC regression).

---

## 4. Health check

1. **Config sanity:** confirm `FLUFFYJAWS_MODE` is set intentionally and, if not
   `DISABLED`, that a transport factory with approved auth is wired.
2. **Provider build:** `build_fluffyjaws_provider(...)` returns `None` when disabled
   (correct) and a provider instance when enabled.
3. **Provider tests:** all FluffyJaws tests must pass:
   ```bash
   cd backend && python -m pytest tests/test_fluffyjaws_knowledge_provider.py tests/test_fluffyjaws_failure_resilience.py tests/test_fluffyjaws_shadow_runtime.py tests/test_fluffyjaws_second_pass_routing.py tests/test_reasoning_evidence_provider_contract.py -q
   ```
4. **Shadow smoke:** with `FLUFFYJAWS_MODE=FLUFFYJAWS_SHADOW` and a valid injected
   transport, run one known case and confirm the trace records a provider status
   (`SUCCESS` / `EMPTY` / `AUTH_ERROR` / `TIMEOUT` / …) and that the final UAC is
   unchanged versus `DISABLED`.

Provider status codes distinguish `FLUFFYJAWS_EMPTY` (call succeeded, no evidence)
from `FLUFFYJAWS_UNAVAILABLE` / `AUTH_ERROR` — do not collapse them. A provider
failure must never crash UAC generation; material unresolved behavior stays an
Open Question / Needs-Review per existing policy.

---

## 5. Fallback behavior

If FluffyJaws is applicable but the call fails/unavailable and public Adobe docs
suffice, the Experience League fallback may supply evidence — **labelled
`EXPERIENCE_LEAGUE`**, never relabelled as FluffyJaws.

---

## 6. Secret-handling checklist (must all be true)

- [ ] No token / secret / `X-User-Token` / session cookie in git, `.env`, logs, traces, fixtures, cache, or CI output
- [ ] Credentials supplied only via approved secret injection into the transport factory
- [ ] Service app registered by a human (not self-registered)
- [ ] Canonical API base confirmed with the FluffyJaws team
- [ ] MCP/API operator-guide schemas obtained before any transport wiring
- [ ] Mode set intentionally; production not enabled without shadow evaluation
