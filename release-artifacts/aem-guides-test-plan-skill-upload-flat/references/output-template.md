# Output Template

Use **plain English** a tester can read without jargon. Avoid: *oracle*, *blast radius*, *UAC*, *residual risk*, *failure mode*. Use **how to verify**, **what can break**, **sign-off checks**, **what's left**, and **what goes wrong**.

Keep the final plan **<=3 pages** (~195 lines). Short bullets and small tables beat long prose.

Do not include a large standalone `## 3. Evidence map`; include the compact evidence table in section 1.

# Test Plan: <JIRA key or title>

**Jira:** <KEY> · **Type:** Bug / Feature request · **Scope:** <UI/API/Publishing/etc.>  
**Routing:** QE_REVIEW_READY / QE_REVIEW_WITH_FLAGS / Draft-human-clarification  
**Score:** <0-100> · **Review status:** Draft / Review-ready  
**QE review:** Required; not auto-approved

---

## 1. Action items (QA — start here)

### Setup (one time)

1. Test data / DAM path
2. Environment prerequisites
3. Auth / config

### Must run before release

**Gate:** list required AC / scenario IDs.

| Run first | Scenario | Pass if |
| --- | --- | --- |

### Test list (priority order)

| Scenario ID | Priority | Title | Links to | How to verify |
| --- | --- | --- | --- | --- |

Include at least one **R0** regression row. Max **10** rows.

### Steps for P0 / P1 tests

For each P0/P1: **Do** + **How to check** (API + log + CRX when useful).

### Sign-off checks (acceptance from Jira)

Bullet each **AC-*** — what to prove · maps to S-* · pass criteria · classification label.

**Blocking sign-off today:** …

---

## 2. Supplementary — context, risks & traceability

### Summary & expected behaviour

- **Bug / feature:**
- **API or UI entry point:**
- **How to reproduce today:**
- **Fix area (if known):** `repo/file:line`

**Expected behaviour (reference):** EB-* bullets (5-7 pass/fail statements).

### Where we got the facts (evidence)

| Evidence ID | Source | Classification | What it proves | Link / path |
| --- | --- | --- | --- | --- |

Classification: ticket-confirmed | documentation-confirmed | specification-confirmed | implementation-derived | previous-JIRA-derived | assumption | human-clarification-required

### What can break & risks

### Code path (where the fix lives)

Short flow: user action -> code -> service/API/background job -> what customer sees.

| Area | Impact | Why | Test / skip |
| --- | --- | --- | --- |

Impact values: Direct, Shared-path, Downstream, Compatibility, Not impacted, Unknown.

| Risk ID | Priority | What goes wrong | Test / skip |
| --- | --- | --- | --- |

### Must not break (regression checks)

- List R0 scenario IDs — things that worked before and must still work.

### Likely bugs to watch (top 3)

| ID | What we suspect | How you'd notice | Test |
| --- | --- | --- | --- |

### Related past Jiras

Max **5 rows**. Past bugs are hints only — not requirements.

| Jira | What happened | Why it matters here | Test |
| --- | --- | --- | --- |

If none found: `Historical search: no related Jiras found (query: …)`.

### Automation coverage

| Check | Where | Coverage | Gap |
| --- | --- | --- | --- |

Coverage: Exact and strong | Exact but weak check | Partial | Obsolete | Mocked-path only | Missing | Best match for this bug

### Confidence breakdown

| Dimension | Score | Evidence / deduction |
| --- | --- | --- |
| Ticket completeness |  |  |
| Retrieval quality |  |  |
| Evidence coverage |  |  |
| Source consistency |  |  |
| Sign-off testability |  |  |
| Requirement traceability |  |  |

**Routing reason:** explain why QE_REVIEW_READY / QE_REVIEW_WITH_FLAGS / Draft-human-clarification.

### QE review package

- QE owner:
- Must review before release:
- Unresolved questions:
- Required approval evidence:

### Evidence & release status

- Jira / code / Swagger / test-data paths:
- Full RAG packet path if available:
- Retained memory / prior plan path if available:
- Not tested yet:
- Known gaps:
- **Release confidence:** Low / Medium / High
- **Review status:** Draft / Review-ready
