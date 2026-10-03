# Blind50 labeling instructions (B4)

The draft file is `skill_uac.md` for the baseline run, `skill_uac_<tag>.md` for a rule change or a repeat run;
the labels go to `labels.json` or `labels_<tag>.json` next to it. The labeler never opens another labels file or
draft for the same ticket, so it cannot anchor on an earlier result.

For each ticket folder you are given, compare `human_uac.md` (the human QE's Acceptance Criteria, the reference)
with `skill_uac.md` (our draft). You may also read `input.json` to understand the ticket. Do not change any file
except the one you write.

1. Split each UAC into single criteria.
   - Human: every numbered/bulleted point (# , *, -, 1.) or line that states a checkable expectation is one
     criterion. A heading such as "UAC:" or "Out of scope" is not a criterion. Nested sub-bullets that are
     separate checkable cases count as their own criterion.
   - Ours: every "Acceptance Criteria NN" is one criterion; its indented sub-points belong to it (they are the
     cases of that criterion, not separate criteria). Scope / Out of scope / Note lines are not criteria.
2. For every HUMAN criterion, label how our draft covers it:
   - FOUND: one of our criteria (or its sub-points) checks the same expected behaviour.
   - PARTIAL: we check the area but miss a condition, value, surface or the expected result differs in detail,
     or we left it as a TBD/question while the human states the answer.
   - MISSED: nothing in our draft checks it.
   Record the matching draft criterion number(s).
3. For every DRAFT criterion, label:
   - MATCH: a human criterion covers it.
   - EXTRA_OK: correct and useful for QE, the human did not write it.
   - EXTRA_NOISE: correct but not needed (too detailed, generic regression nobody asked for, duplicate).
   - WRONG: a false or unsupported claim, or it contradicts the human UAC or the ticket.
4. Give a one-line reason for every PARTIAL, MISSED, EXTRA_NOISE and WRONG.
5. Be strict and consistent. Do not change a label to make the draft look better.

Write `labels.json` in the ticket folder:
{"key": "...", "human_count": N, "draft_count": M,
 "human": [{"n": 1, "text": "<short paraphrase>", "label": "FOUND|PARTIAL|MISSED", "draft": [<numbers>], "reason": "..."}],
 "draft": [{"n": 1, "text": "<short paraphrase>", "label": "MATCH|EXTRA_OK|EXTRA_NOISE|WRONG", "human": [<numbers>], "reason": "..."}],
 "miss_kind": ["<for each MISSED/PARTIAL human point, one short category, e.g. 'decision made after ticket', 'specific UI detail', 'other output type', 'permission/role', 'performance', 'upgrade/existing content', 'negative case', 'API'>"]}
