# Blind50: the blind benchmark for skill rule changes

Blind50 measures the test-plan skill against UACs that human QEs wrote, on tickets the skill has never seen.
Every future change to a skill rule must be measured on it before it is merged.

## The set

- `scripts/uac_eval/blind50/` (gitignored: it holds Jira text and human UACs). One folder per ticket:
  - `input.json`: the ticket as it was before its human UAC was written (summary, type, components, fix versions,
    and the description, comments and attachment names from before the cutoff).
  - `human_uac.md`: the human Acceptance Criteria, with the author and date. Generators never read it.
  - `skill_uac.md`, `skill_evidence.json`, `run.json`: the baseline skill run.
  - `labels.json`: the B4 labels for the baseline run; `labels_r2.json` for a second run of the unchanged skill.
  - `manifest.csv`, `ai_influenced.csv` (tickets that already had an AI-written UAC or Open Questions comment
    before the human UAC; report scores with and without them).
- Built on 2026-10-03 from every unseen GUIDES Customer Request or Bug with a human UAC: 31 tickets. Tickets
  already used to write the skill's rules, examples, earlier evals or the corpora are excluded, and so are
  tickets whose UAC was written by a bot or the automation.
- Never add these tickets, or anything taken from their human UACs, to a skill rule, an example, a prior or a
  miss probe. Once a ticket teaches a rule, it is no longer blind.

## Baseline (frozen skill = main 97d364b24)

- recall 57.5%, precision 90.4%, WRONG 0.13 per ticket, median 7 criteria against the human median of 6.
- Two runs of the unchanged skill on the same 13 tickets differ by about 2 recall and 3 precision points;
  single tickets swing by 10 to 25 points.

## Testing a rule change

1. Freeze the changed skill copy. Re-generate only the tickets the rule affects, plus a few controls the rule
   should not touch, into `skill_uac_<tag>.md`. The generator reads only `input.json`, the frozen skill, the
   product and automation clones and the documentation; never `human_uac.md`, labels, earlier drafts, live
   Jira, Jira-history or similar-UAC search.
2. Label the new drafts with `BLIND50_LABELING.md` into `labels_<tag>.json`.
3. Score: `python scripts/uac_eval/blind50_score.py --compare <tag> --controls <keys>`. It compares with the
   average of the baseline runs (`labels.json`, plus `labels_r2.json` where it exists).
4. Keep the change only when the verdict is KEEP: recall rises by more than 2 points, precision falls by no
   more than 3 points, and WRONG per ticket does not rise. Otherwise revert it.

## The rule for pull requests

Every pull request that changes a skill rule (SKILL.md, a reference the skill loads, or a checker that decides
what becomes an Acceptance Criterion) shows its blind50 `--compare` table in the description. It may not lower
precision beyond the noise or raise WRONG per ticket. A rule that does not pass is not merged.

## Results so far

| Change | Tickets | Recall | Precision | WRONG/ticket | Verdict |
|---|---|---|---|---|---|
| Generation routes are an AC only when the change depends on the route | 13 | 55.4 -> 50.0 | 84.6 -> 87.0 | 0.27 -> 0.23 | REVERT |
| "What must not happen" negative-case rule | 20 (6 controls) | 54.5 -> 55.1 | 89.1 -> 86.9 | 0.17 -> 0.35 | REVERT |
| Variant matrix per product area (vm1, set of 2026-10-05) | 20 (4 controls) | 35.7 -> 34.3 | 81.3 -> 84.3 | 0.15 -> 0.15 | REVERT |

The variant-matrix rule barely changed the drafts: the skill rarely added the named variants, and the labelers
split the same human UACs differently (185 vs 204 human criteria on the same 20 tickets), so label noise on
this set is larger than on the first one.

Most misses are information decided after the ticket (UAC meetings, developer design), which no rule can
recover; the harvester's QE-edit data (`scripts/uac_release/uac_learning_harvester.py`) is the other source
for rule changes.
