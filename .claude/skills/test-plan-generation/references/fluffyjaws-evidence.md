# FluffyJaws Supporting-Discovery Evidence (flag-gated)

FluffyJaws can query the **whole Experience League + AEM Guides product-doc
surface** on demand. Use it to *discover* relevant behaviour that the local RAG
corpus may not yet cover — not to author acceptance criteria.

## Hard invariant (never violate)

- FluffyJaws synthesis is **`SUPPORTING_DISCOVERY` only**. It is generated prose,
  not a citable normative source, and it can hallucinate.
- **There is no FluffyJaws → AC path.** Anything FluffyJaws surfaces must be
  **re-grounded** in a first-class source (DITA spec, DITA-OT, AEM Guides product
  doc via `ask_dita_expert` / `lookup_aem_guides`, current code, or historical
  Jira) that keeps its own authority, before it can raise an AC's coverage.
- A FluffyJaws discovery may **never** be the sole basis for a `Covered` or
  `Partially covered` claim.

This mirrors the backend provider (`SUPPORTING_DISCOVERY`, no direct promotion)
and is enforced by `scripts/fluffyjaws_evidence.py` inside `run_gates.py`.

## When to consult it

Only for **material** product-behaviour discovery gaps, after local retrieval:
documented product surface, terminology, supported configuration, workflow, or
limitation that `ask_dita_expert` + `lookup_aem_guides` + the local corpus did not
resolve. Do **not** route normative DITA/DITA-OT questions here (those go to the
DITA spec / DITA-OT oracle per `references/dita-spec-evidence.md`).

## Access model: the Claude FluffyJaws connector (not a backend HTTP call)

FluffyJaws is reached as a **native Claude enterprise connector tool**, the same
way the skill already calls `ask_dita_expert`. There is **no** MCP URL, client ID,
secret, terminal command, or JSON to configure. A human connects it once:

1. Open Claude's connector picker / connector settings.
2. Choose **FluffyJaws** from the Adobe enterprise connectors, select **Connect**,
   and complete Adobe sign-in if prompted.
3. When you want it used, select **FluffyJaws** from Claude's available tools.

The skill does **not** call a backend FluffyJaws provider; it invokes the
connector tool directly and treats the answer as supporting discovery.

## Availability (default OFF)

FluffyJaws is used only when **all** of these hold: the connector is connected, the
FluffyJaws tool is selected/available in this session, and the skill flag is on.

```bash
python scripts/fluffyjaws_evidence.py --probe
```

- Flag off / tool not present (today's default): **do not attempt a FluffyJaws
  call.** Fall back to the existing RAG path and proceed exactly as before. Leave
  the manifest `fluffyjaws` block absent.
- When the connector tool is available and you intend to use it, set
  `SKILL_FLUFFYJAWS_MODE=FLUFFYJAWS_SHADOW` (or `FLUFFYJAWS_SECOND_PASS`) and
  record discoveries as below. If the tool is not actually present in the session,
  do not fabricate a call — leave the block absent.

## Manifest block (only when a call actually happened)

```json
"fluffyjaws": {
  "mode": "FLUFFYJAWS_SHADOW",
  "available": true,
  "discoveries": [
    {
      "query": "Native PDF File properties documented behaviour",
      "authority": "SUPPORTING_DISCOVERY",
      "regrounded_evidence_id": "E7"
    }
  ]
}
```

- `regrounded_evidence_id` must reference an `evidence_authority.items[]` entry
  whose `authority` is a first-class dimension (spec/impl/product-doc/history/test).
- Omit the whole block when disabled/unavailable, or when no FluffyJaws call was
  made — absence is a clean gate pass and keeps existing plans unchanged.
- Never place tokens, cookies, `X-User-Token`, or any secret-shaped key in the
  block; the gate rejects them.

## Fallback chain (today's working path)

`ask_dita_expert` → `lookup_aem_guides` → local Chroma corpus (the ongoing
ingestions). FluffyJaws is an *additive* discovery layer on top of this; it never
replaces the required `rag_tool = ask_dita_expert` product-doc evidence.

## Skill workflow (moved from SKILL.md)

Moved verbatim from SKILL.md on 2026-09-30 when SKILL.md was consolidated. The rules are unchanged.

- Use the FluffyJaws connector ONLY as a `SUPPORTING_DISCOVERY` source, and only when it is registered in the session AND `SKILL_FLUFFYJAWS_MODE` is `FLUFFYJAWS_SHADOW` or `FLUFFYJAWS_SECOND_PASS` (default `FLUFFYJAWS_DISABLED` => never call it). When enabled, call the connector's own tool for discovery, then RE-GROUND every finding into a first-class source (spec / DITA-OT / product doc / current code / historical Jira) that keeps its own authority before it can raise any AC coverage. FluffyJaws synthesis can hallucinate: it is never an authority, never the sole basis for a Covered/Partially-covered claim, and there is no FluffyJaws -> AC path. Record it in the manifest `fluffyjaws` block (see "### FluffyJaws Supporting-Discovery"); enforced by `fluffyjaws_evidence`. See `docs/fluffyjaws_setup.md` and `references/fluffyjaws-evidence.md`.
FluffyJaws broadens *discovery* of relevant behaviour, but it is a synthesis engine, not an authority. Use it only to widen the net for candidate dimensions and behaviours; never as evidence on its own.

- **Gate on the mode.** Read `SKILL_FLUFFYJAWS_MODE`. `FLUFFYJAWS_DISABLED` (default) => do not call FluffyJaws and claim no discoveries. Only `FLUFFYJAWS_SHADOW` or `FLUFFYJAWS_SECOND_PASS` may call it, and only when the connector is actually registered in this session. If the mode is enabled but the connector is not reachable, set `available: false` and record no discoveries (fall back to the normal RAG path).
- **Query for discovery, then re-ground.** Ask FluffyJaws focused discovery questions derived from the normalized behaviour model. For every finding it surfaces, RE-GROUND it into a first-class source that keeps its own authority (spec / DITA-OT / product doc / current code / historical Jira) before it can raise any AC's coverage. A finding that cannot be re-grounded stays an Open Question or is dropped - it never becomes an AC.
- **Record it in the manifest `fluffyjaws` block** so `fluffyjaws_evidence` can enforce the invariants: `{"mode": "FLUFFYJAWS_SHADOW|FLUFFYJAWS_SECOND_PASS", "available": true|false, "discoveries": [{"finding": "...", "authority": "SUPPORTING_DISCOVERY", "regrounded_evidence_id": "E#"}]}`. Every discovery's `authority` must be `SUPPORTING_DISCOVERY` and must name a `regrounded_evidence_id`; a discovery present while `DISABLED`/`available:false` is a hard failure.
- **Mode effect.** `FLUFFYJAWS_SHADOW` records discoveries for trace/evaluation only - the final plan stays baseline-equivalent, unchanged versus `DISABLED`. `FLUFFYJAWS_SECOND_PASS` may let a re-grounded discovery become an `INVESTIGATION_CANDIDATE` in the coverage pipeline, still `SUPPORTING_DISCOVERY` and still with no FluffyJaws -> AC path.
- **Transport note.** The connector-driven path above (this skill calling the registered FluffyJaws tool) is the supported path here. The separate backend HTTPS provider (`build_fluffyjaws_provider` with an injected authenticated transport) requires human-only setup - service-app registration, the operator-guide MCP/API schemas, and the confirmed API base per `docs/fluffyjaws_setup.md`; do not guess that transport.
