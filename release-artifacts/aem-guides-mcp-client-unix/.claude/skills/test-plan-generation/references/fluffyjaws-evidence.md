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
