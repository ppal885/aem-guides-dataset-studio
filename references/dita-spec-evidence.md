# DITA Spec Evidence — Consultation Protocol

Read and apply this file whenever a ticket mentions named DITA elements or attributes,
DITA-OT processing behavior, or a discrepancy between output presets where one conforms
to the DITA spec and another does not.

## When to trigger this protocol

Trigger when ANY of the following appear in the Jira description, comments, or attachments:

- A named DITA element (`<glossarylist>`, `<topicref>`, `<conref>`, `<keydef>`,
  `<glossentry>`, `<chunk>`, `<reltable>`, `<subjectScheme>`, etc.)
- A named DITA attribute (`keyref`, `conref`, `chunk`, `format`, `scope`, etc.)
- A DITA processing expectation ("should appear in output", "should resolve", "should include")
- A cross-output-type comparison ("DITA-OT PDF includes it but Native PDF does not")
- A claim about spec compliance, spec deviation, or inconsistent behavior across presets
- A reference to DITA 1.2 or DITA 1.3 spec behavior
- A content category (glossary, booklist, subject scheme, reltable, key space, etc.)

## Three evidence sources — always run all three separately

`ask_dita_expert` covers all three corpora.
Use targeted query intent to target each one; mixing intents produces noisy, unusable results.

### 1. DITA spec (normative)

What the DITA 1.2 or DITA 1.3 spec REQUIRES a conforming processor to do.

**Corpus**: DITA spec collection in `ask_dita_expert` (covers both 1.2 and 1.3).

**Probe intent**: `DITA 1.3 spec <element-name> normative processing required included`
- For version-sensitive constructs (element or attribute changed between versions): probe
  BOTH DITA 1.2 AND DITA 1.3 and record where they differ.
- Target the element's Content Model, Usage constraints, and Attributes sections.

**How to use**:
- Spec uses "shall" or "must": any AC covering that behavior is **[Confirmed]**.
  (Non-compliance is a bug by definition; cite provenance "per DITA 1.3 spec normative".)
- Spec uses "should" or "may": the AC is **[Proposed]** (processor has discretion).
- Spec is silent: keep AC [Proposed] and add an Open Question about interpretation.

### 2. DITA-OT behavior — benchmark assertion oracle

DITA-OT is the reference open-source processor. For AEM Guides output defects,
**DITA-OT PDF output is the benchmark**: if DITA-OT PDF renders the element correctly
and an AEM Guides output type does not, the AEM Guides output type is wrong.

This is not merely "evidence" — it is the primary assertion oracle for output verification.
Every output-correctness AC must include a "matches DITA-OT PDF" or "matches DITA-OT HTML5"
clause where a DITA-OT output for that format exists.

**Corpus**: DITA-OT documentation collection in `ask_dita_expert`.

**Probe intent**: `DITA-OT processing <element-name> <output-type> included unconditionally`
- Ask how DITA-OT handles the specific element in the relevant output format.
- Ask whether DITA-OT's inclusion is conditional (based on usage in content) or unconditional
  (based on structural declaration in the map).

**How to use**:
- If DITA-OT and the DITA spec agree AND AEM Guides output differs: the AEM Guides
  behavior is a bug. State: "Per DITA 1.3 spec and DITA-OT reference implementation,
  [element-name] [expected behavior]. AEM Guides currently [actual behavior] — this is
  the defect."
- If DITA-OT deviates from the spec: the spec is still authoritative. Note the deviation.
- Always generate AC-pairs: one AC for the primary fix, one AC comparing output to DITA-OT.

### 3. AEM Guides behavior — product under test

What AEM Guides currently does — which may be the defect — and any documented workarounds.

**Corpus**: AEM Guides / Experience League collection in `ask_dita_expert`.

**Probe intent**: `AEM Guides <element-name> <output-preset> behavior expected`
- Ask what AEM Guides documents for the element's handling in the relevant output preset.
- Ask whether there is a documented workaround or configuration option.

**How to use**:
- Confirms the reported actual behavior and surfaces documented workarounds.
- A confirmed workaround is a mandatory regression AC after the fix (the workaround path
  must still work after the bug is fixed).
- When silent: record "AEM Guides behavior on this element undocumented in Experience
  League — inferred from Jira and product clone inspection only."

## Output preset coverage matrix

For any DITA element rendering or content inclusion defect, the following output presets
are all in scope as regression dimensions unless the Jira explicitly limits scope:

| Preset | Benchmark | Notes |
|---|---|---|
| DITA-OT PDF | Primary benchmark | The canonical correct output; AEM Guides Native PDF must match it for this element |
| Native PDF | Subject under test | AEM Guides-specific pipeline; most often where DITA spec deviations appear |
| AEM Sites (new) | Secondary benchmark | Uses AEM Sites rendering pipeline; must be consistent with DITA-OT behavior |
| AEM Sites (legacy) | Secondary benchmark | Legacy Sites pipeline; verify separately as it has a different code path |
| HTML5 | Secondary benchmark | Verify separately; shares some processing with AEM Sites but different renderer |
| Native AEM Site | Secondary benchmark | Native AEM publishing path; verify element is included if other Sites formats include it |

**Rule**: If the DITA-OT PDF includes the element and a non-DITA-OT AEM Guides output type
does not, that is a defect in the AEM Guides output type. The fact that one AEM Guides
preset works (e.g., AEM Sites) does not excuse another failing (e.g., Native PDF).

**Rule**: For the fix verification AC, always generate one AC whose Then clause reads:
"Native PDF output matches DITA-OT PDF output for [element-name]: same count, same order,
same content." This gives a concrete, reproducible assertion oracle that any QA can run
without access to implementation code.

## Using spec evidence in the plan

**When spec AND DITA-OT agree on expected behavior:**
- Upgrade matching [Proposed] ACs to [Confirmed]; cite provenance.
- Expected Behaviour: "Per DITA 1.3 spec (normative) and DITA-OT reference implementation,
  `<element-name>` [expected behavior]. AEM Guides [output-preset] currently [buggy behavior]
  — this is the defect. Template and rendering layer are correct per [evidence source];
  the defect is upstream in [pipeline stage]."

**When spec is ambiguous or version-dependent:**
- Keep AC [Proposed] and add Open Question naming the ambiguous clause.

**When spec and DITA-OT disagree:**
- Surface the conflict explicitly. Add Open Question: "Does the AEM Guides fix target DITA
  spec conformance or DITA-OT behavioral parity? QA impact: different targets change the
  assertion oracle and may give different pass/fail verdicts for edge cases."

Never conflate spec behavior with AEM Guides implementation behavior — they are separate
corpora and may contradict.

## Common DITA element probe topics

| Ticket involves | Spec probe topics |
|---|---|
| Glossary (glossentry, glossterm, glossref, glossarylist) | `<glossarylist>` inclusion rules, `<booklists>` processing, DITA 1.2 and 1.3 |
| Keys, keyrefs, keydefs, key spaces | `<keydef>` resolution algorithm, key scope, `<keyref>` fallback |
| Conrefs, conkeyrefs | `<conref>` resolution order, `<conkeyref>` algorithm |
| Relationship tables | `<reltable>` processing, link generation from relrow/relcell |
| Subject scheme maps | `<subjectScheme>`, `<hasInstance>`, `<enumerationDef>` filtering |
| Bookmaps, frontmatter, backmatter | `<bookmap>`, `<frontmatter>`, `<backmatter>`, `<booklists>` |
| Chunk attribute | `chunk` value matrix, `select-topic`, `to-content` DITA-OT handling |
| Metadata inheritance | `<topicmeta>` inheritance, `<data>` propagation, cascade rules |
| Profiling / conditions | `<val>`, profiling attributes, DITAVAL `<prop>` processing |
| MathML / equation elements | `<mathml>`, `<equation-block>`, `<equation-inline>` spec backing |
| Navigation titles | `<navtitle>`, `@locktitle`, title vs navtitle rendering by output type |
| Topic references | `<topicref>`, `@format`, `@scope`, `@type` — processing intent |

## Evidence manifest requirements

When this protocol runs, record in `rag_probes`:
- At least one probe targeting the DITA spec corpus (exact element names, normative terms)
- At least one probe targeting DITA-OT behavior in the affected output format
- At least one probe targeting AEM Guides behavior in the affected output preset
- State which DITA version(s) were probed (1.2, 1.3, or both) and why

When a probe returns nothing, record it and state "DITA spec / DITA-OT / AEM Guides docs
are silent on [specific behavior]" — that absence is itself evidence and must be recorded,
not silently omitted.
