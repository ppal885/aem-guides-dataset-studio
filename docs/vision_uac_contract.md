# Contract: the posted UAC as input for the Vision agent

Audience: the Vision team, and anyone else who reads the UAC our nightly automation writes to Jira.
Producer: `scripts/uac_release/uac_release_runner.py` (see `scripts/uac_release/README.md`).
Grammar in code: `scripts/uac_release/uac_field_parser.py`; tests in `scripts/uac_release/test_uac_field_parser.py`.

Vision reads the Jira **Acceptance Criteria** field directly. It does not call this backend.

## 1. Which tickets to read

```
project = GUIDES AND labels = QEVision_UAC_DONE AND "Acceptance Criteria" is not EMPTY
```

`QEVision_UAC_DONE` (config `labels.posted`) is added only after the runner wrote the UAC into an empty
Acceptance Criteria field, read it back and confirmed Jira rendered it, and attached the full test plan.
No label means the field content is not a UAC this automation vouches for (see section 4).

Field: the Acceptance Criteria custom field named in config `acceptance_criteria_field`
(`customfield_13400` on the current Jira). Read it through the Jira REST API; use the raw (wiki) value,
not the HTML-rendered one, for parsing.

## 2. Field grammar (as posted)

Jira wiki markup, one top-level bullet per criterion, 1 to 10 criteria, numbered from 01:

```
_Note: A fix is proposed in a linked pull request but is not merged; ..._      ← optional, not a criterion
* *Acceptance Criteria 01:* <plain-English criterion>
** <case sub-point>                                                             ← zero or more
** *Source:* <ticket line, comment, attachment, documentation page or PR>
** *TBD:* <open question>?                                                      ← only when a decision is open
* *Acceptance Criteria 02:* ...
```

Rules a consumer can rely on:

- A criterion starts at a line whose label matches, case-insensitively,
  `(Acceptance Criteria|Acceptance Criterion|AC)[ -]*NN:` optionally preceded by a bullet (`*`, `-`, `#`)
  and wrapped in `*...*` (bold). Numbers may be `1` or `01`.
- Everything until the next criterion label belongs to that criterion: nested `**` bullets are case
  sub-points, `*Source:*` and `*TBD:*` lines are metadata.
- The `_Note: ..._` line above the first criterion is a status note (fix only proposed, root cause not
  confirmed). It is **not** a criterion.
- A `*TBD:*` line means **the decision is open**: the criterion is not a confirmed requirement yet, and the
  runner has posted a decision-request comment on the ticket. Treat that criterion as provisional.
- An `Open Questions` heading or `OQ-NN` lines, if present, are not criteria.
- The AC text is plain English. Settings are named by on-screen label; file names are in `{{monospace}}`.

### Extracting AC text only

Python consumers can import the parser directly:

```python
from uac_field_parser import ac_texts_only, has_open_decision   # scripts/uac_release on sys.path
texts = ac_texts_only(field_value)          # one string per criterion: statement + its case sub-points;
                                            # Source/TBD lines excluded, struck criteria left out
pending = has_open_decision(field_value)    # True while any criterion still has a TBD
```

Any other language: split on criterion labels with

```
^(?:[-*#]\s+)?\*?\s*(?:Acceptance Criteri(?:a|on)|AC)[\s-]*(\d+)\s*:?\s*\*?\s*:?\s*(.*)$      (multiline, case-insensitive)
```

take group 2 as the statement, and drop lines matching `^(?:[*#-]+\s*)?\*?(Source|TBD)\*?\s*:` and nested
`**` bullets. Both patterns are the ones the harvester uses on real posted fields.

## 3. The UAC changes after posting

QE owns the field once it is posted. Expect, and re-read on every `updated` change:

- **Edits**: wording changed, criteria added (often as `AC-NN:` without bold), criteria reordered.
- **Rejections by strikethrough**: `-text-` or `{-}text{-}`. A fully struck criterion is rejected; text QE
  left unstruck beside it is the reason. `ac_texts_only` already leaves struck criteria out.
- **Re-runs**: QE may clear the field and have the UAC regenerated. The label stays; the text changes.

Never cache a UAC past the ticket's `updated` timestamp. The automation itself diffs the field every
30 minutes (`uac_learning_harvester.py`) to learn from these edits.

## 4. States to handle

| What you see | Meaning | What to do |
|---|---|---|
| `QEVision_UAC_DONE` + non-empty field | UAC posted and rendered | Consume |
| Label `UAC_Not_Required` | A person decided no UAC is needed | Do not wait for one |
| Field has text, no `QEVision_UAC_DONE` | Hand-written by a person, or written but Jira did not render the bold label (`WRITTEN_UNRENDERED`) | Treat as human text; parsing may still work but it is not this automation's output |
| Empty field, label `UAC_Check`, unresolved | Queued for a future nightly run | Wait |
| Criterion with `*TBD:*` | Product decision pending | Provisional, not a confirmed requirement |
| `_Note: A fix is proposed ... not merged_` | Fix is a proposal | Criteria describe expected behaviour, not a verified fix |

## 5. No feedback loop

Vision posts its results as Jira comments from a person's account ("via Copilot"). The runner must not
mistake them for human requirements or closure requests, and Vision must not treat our UAC as its own
confirmation. Rules:

- **Vision keeps the `[Vision]` prefix** as the first text of every comment (currently
  `[Vision] <state> — <repo> · via Copilot`, with a `— Vision · GUIDES-NNNNN · <state>` sign-off). The runner
  classifies a comment that starts with `vision` after markup is stripped as a bot notice
  (`_BOT_COMMENT` in `uac_release_runner.py`) and excludes it from requirement mapping and closure detection.
  Tests cover the three observed shapes (PR created, Checked PR for feedback, Needs review).
- Vision output is never acceptance authority for the UAC. If Vision's **Root cause** / **Fix** fields are
  ever used by the UAC pipeline, they enter as observation evidence only, like historical ticket findings,
  never as the source of an Acceptance Criterion without a human decision.
- A Vision PR arriving after the UAC does **not** regenerate the UAC. The staleness watch
  (`uac_staleness_watch.py`) alerts QE once; QE decides whether to re-run.

## 6. What Vision must not do

- Write to the Acceptance Criteria field (the runner never overwrites text it did not write; Vision text
  there would freeze the ticket as `FIELD_KEPT`).
- Add or remove `QEVision_UAC_DONE`, `UAC_Check` or `UAC_Not_Required`.
- Rely on the HTML-rendered field for parsing, or on comment author to detect this automation.

## 7. Open questions for the Vision team

1. Is the `[Vision]` prefix guaranteed on every comment, including failures and retries?
2. Does Vision want a machine-readable `UAC.json` attachment (criteria with numbers, sources and TBD flags)
   in addition to the field? The runner can attach one behind a config flag if so.
3. Which Vision state should trigger a QE alert that the UAC may be stale: `PR created` only, or also
   `Needs review`?
