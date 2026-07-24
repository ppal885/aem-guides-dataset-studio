# Plain-English test plan writing

**Audience:** Manual QA engineers — not developers decoding internal jargon.

Use this reference whenever you write or rewrite an AEM Guides test plan. Applies on **Claude**, **Cursor**, and **Codex** — same markdown, same validator.

## Jargon → plain English (mandatory)

| Do not write (in plan body) | Write instead |
| --- | --- |
| oracle / multi-layer oracle | **how to verify**, **how to check**, **pass if** |
| blast radius | **what can break**, **what else is affected** |
| UAC | **sign-off checks**, **acceptance checks** (AC-* bullets — Jira outcomes, not test scripts) |
| residual risk | **what's left**, **not tested yet** |
| failure mode | **what goes wrong** |
| bug hypothesis | **likely bug to watch** |
| trace (EB / risk) | **links to** |
| Draft gates | **why still Draft** |
| prerequisites | **before you start** |
| Evidence map (E1–E12 table) | Inline bullets under **Where we got the facts** |

**Keep IDs** (`EB-*`, `AC-*`, `S-*`, `R-*`, `BH-*`) for traceability — but explain pass/fail in the same line in plain words.

## Pass criteria rules

Every P0/P1 scenario must say **how to check** with at least one concrete signal:

- HTTP status (e.g. **401**, **200**)
- JSON field and value (e.g. `assets[].path` contains `test,comma`)
- CRX property (e.g. `guides:assetStatus=SUCCESS`)
- Log line (e.g. no `Not an absolute path: comma/...`)
- File/output path or visible UI state

**Never use alone:** "works correctly", "no error", "verify behavior", "should work".

## Section titles (validator accepts these)

1. `## 1. Summary & expected behaviour`
2. `## 2. What can break & risks`
3. `## 3. Test scenarios & release`

Subsections: **Sign-off checks**, **Where we got the facts**, **Code path (where the fix lives)**, **Must not break (regression checks)**, **Likely bugs to watch (top 3)**, **Related past Jiras**, **Test list (priority order)**, **Steps for P0 / P1 tests**, **Automation coverage**, **What's left & sign-off**.

## Gold-standard example

**File:** `C:/starling/docs/qa/test-plans/GUIDES-49065-test-plan.md`

## Sign-off checks vs test scenarios

| Section | Purpose | Format |
| --- | --- | --- |
| **Sign-off checks (AC / UAC)** | What Jira says must be true before release | Descriptive **bullet points** in plain English; link each AC to S-* |
| **Section 3 — Test scenarios** | How QA executes and verifies | Scenario table + **Steps for P0/P1** with **How to check** |

Never use a table for AC/UAC bullets. Never put numbered test steps only in sign-off — put execution detail in section 3.

Patterns to copy:

- Sign-off: **AC-* descriptive bullets** (Jira acceptance — what to prove)
- Section 3: scenario table + step list with **How to check**
- Risk table column **What goes wrong** (not "Failure mode")
- Short bullets; ≤195 lines total

## Before/after examples

**Bad (jargon):**

> S-01 oracle: multi-layer — API SUCCESS and no Splunk failure mode for comma path decode.

**Good (plain English):**

> **S-01** POST comma path → poll until done. **How to check:** poll status is `SUCCESS`; Splunk has no `Not an absolute path: comma/...`.

---

**Bad:**

> Residual risk: Author UAC for comma paths pending; blast radius includes shared-path codec.

**Good:**

> **Not tested yet:** comma-path manual tests on Author. **Why still Draft:** sign-off checks AC-1–AC-5 not run on staging Author.

## Optional dev appendix (long plans only)

If a ticket needs dev traceability (e.g. GUIDES-49507 style), you may add a short **Appendix — dev codes** at the end **after** the 3 main sections, telling QA to ignore `BH-*`, `PR Gate`, etc. Do **not** replace plain-English steps with appendix-only content.

## Validate before delivery

```bash
python scripts/validate_test_plan.py path/to/GUIDES-XXXXX-test-plan.md
```

Fix all errors. Trim to ≤195 lines if the validator complains about length.
