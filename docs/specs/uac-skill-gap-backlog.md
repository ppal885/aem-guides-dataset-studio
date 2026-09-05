# UAC / Test-Plan Skill — Prioritized Gap Backlog

Status: Living doc
Author: generated from a working session (multiple live Jira UACs + eval mining)
Basis: GUIDES-52444, GUIDES-50368, GUIDES-53351, GUIDES-47137, GUIDES-14665, and the
uac_eval harness runs. Ranked by impact (ceiling-raisers first).

## G1 — Coverage intelligence lives in the skill, not the generator (CEILING)
The coverage gates (partition, performance, ui-surface, no-code-identifiers, investigation)
run in the skill layer (`scripts/run_gates.py`) and only VALIDATE a plan. The shipped
plans are produced by the VM canonical runtime, a separate codebase, so a dimension the
gate would catch can still be omitted by the runtime unless someone authors through the
skill. Evidence: the partition backend change was the only thing that could move the eval,
and the runtime is deliberately locked against bolt-on gates (see
`canonical-runtime-coverage-stages.md`).
Fix (the real lever): fold the coverage dimensions into the runtime's acceptance-candidate
generation so the pipeline PRODUCES the ACs (not just flags gaps). SCOPED in
`g1-runtime-coverage-generation.md` (within-stage change to the closure explorer +
ACCEPTANCE_CONTRACT_RESOLVER; locked-runtime-safe, no new stage). Everything else is incremental.

## G2 — Authors first, enumerates later (BEHAVIORAL)
On every ticket this session a reviewer had to add a missed dimension after the draft
(52444: performance, UI surfaces, then scope/entry-points/siblings, then method-names;
50368: under-specified first pass). The "enumerate the full dimension space and ask
blocking questions BEFORE writing ACs" rule exists in memory but is not reliably executed.
Fix: a mandatory pre-authoring enumeration step that emits a dimension inventory (all
entry points, consumers, sibling paths, states/config partitions, output presets,
DITA-OT on/off, error paths, performance, security, localization) and forces each to be
dispositioned before any AC is written. Make it a gate, not a guideline.

## G3 — Code tracing stops too early (DISCOVERY)
Scope was under-traced until pushed (52444: one entry point until "check consumers /
siblings / direct siblings"). The pipeline should trace a construct to ALL consumers,
entry points, and sibling code paths before writing scope. `relationship_traversal`
exists but does not force full consumer enumeration at author time.
Fix: at author time, require the touched construct's consumer/sibling set to be
enumerated (with file:line in the manifest, translated to plain behaviour in the ACs)
before scope ACs are accepted.

## G4 — Root cause often lives outside the inspected clones (EVIDENCE)
Native PDF resolution (50368) and gen-list input scoping (52444) live in the Node/JS
publishing engines, not the Starling Java clone. The skill grounds well in Starling but
goes vague exactly where the bug is.
Fix: add the Node/JS publishing-engine repos to the clone/evidence set (or a GitHub-MCP
path to them) and teach the evidence step to reach them for Native-PDF / gen-list /
executor questions.

## G5 — The measurement instrument has gaps (EVAL)
- Rare dimensions are unmeasurable (partition = 5/315) — the eval cannot validate a fix
  for a low-prevalence dimension; do not ship unmeasured generation changes for these.
- Non-AC gold silently trusted — FIXED (gold_quality classifier, ~2% excluded).
- Judge miscounted extra ACs as hallucinations — FIXED (contradiction/invention only +
  extra_criteria).
- Judge produced transient nulls (21/30 in one run) — FIXED (retry + higher token cap +
  accept-only-numeric).
- Eval rewarded recall only, incentivising over-production of ACs (the exact drift
  reviewers penalise: over-decomposition, redundant/instance-of ACs, verbose ACs) -
  FIXED. Added `scripts/uac_eval/precision.py` (deterministic AC-block metrics: AC count,
  over-decomposition beyond the skill's 12-AC cap, lexical near-duplicate pairs at
  Jaccard >= 0.6, verbose-AC count -> `precision_pct`) plus `combined_pct` = harmonic
  mean (F1) of coverage and precision. Judge prompt (`judge.py`) now also returns
  `redundant_criteria`, `over_decomposed`, and a `precision` 1-5. `judge_pipeline.py`
  reports coverage / precision / combined per ticket and in the summary table, so a plan
  can no longer win by dumping ACs. Self-tests pass; thresholds mirror the skill gate.
Remaining: build a dimension-enriched eval slice so rare-dimension fixes can be measured;
periodically re-run the gold-quality classifier as the corpus grows.

## G6 — History / RAG unreliable in-session (EVIDENCE)
`search_jira_history` (live) and offline `jira_qa` were unavailable on nearly every
ticket, so "Known Jira Bugs" sections were thin — one of the skill's supposed strengths
(cross-customer defect mining) frequently did not run.
Fix: make the RAG/history endpoint dependably reachable in the session (ops), and add a
hard "history attempted (source, query, result)" record so a thin section is visible, not
silent.

## G7 — Multimodal evidence is ad-hoc (EVIDENCE) — DONE
Video analysis worked on 52444 only via improvised cv2 frame extraction; the external
63MB video on 50368 could not be fetched; the "sample PDF" was the wrong content.
Fixed: `scripts/jira_attachment_ingest.py` ingests a ticket's attachments in one call -
video to evenly spaced frames (OpenCV), PDF to per-page text + keyword-hit pages (pypdf),
images downloaded as-is, plus a manifest.json - so the author reads real content, never a
filename. Degrades gracefully without OpenCV/pypdf; can also fetch an external --url.
Verified end-to-end on GUIDES-52444 (1 video -> frames, 8 screenshots). Remaining
optional polish: screenshot OCR, and auth for gated external video hosts.

## What is already solid (do not regress)
- Grounded single-ticket UAC authoring once pointed correctly.
- The measure -> fix -> re-measure loop for high-prevalence FAILURE CLASSES
  (crash fix: hard failures 2/30 -> 0/30, cleanly measured and shipped).
- Fail-closed skill gates: performance, ui-surface, state/config/language partition,
  investigation-as-AC, no-code-identifiers, paste-safe/plain-language.

## Ops follow-ups (surfaced during the 2026-09-04 VM redeploy)
- G8 — VM deploy is nginx/systemd, not Docker, but `deploy.sh` is Docker-only
  (`docker compose -p ...` failed on the VM). The real deploy is: `git pull` then
  `systemctl restart <backend-service>` (bare checkout, so `_build_commit()` reads git
  directly - no stamping needed). Add a short "VM restart (non-Docker)" path to the
  vm-deployment skill so the next redeploy skips the Docker detour. Verify with
  `python scripts/verify_deploy.py --expect <sha>` (checks build_commit + evidence-fragment count).
- G9 — Tracked runtime data drift on the VM. DONE (commit 83cee1af6). The 11 top-level
  `backend/storage/*.json` runtime artifacts (RAG/behavior/doc chunks, enrichment, index
  registries, allure export, feedback prompt_overrides) were untracked (`git rm --cached`,
  working copies kept) and `backend/storage/*.json` added to .gitignore (depth-1 only, so
  deeper bundle manifests stay tracked). Safe because RAG is VM-hosted and consumed via MCP,
  not these local files. One-time VM migration (backup -> checkout -> pull -> restore)
  documented so the VM keeps its runtime data; deploys are now clean fast-forwards.

## Recommended order of work
1. G1 (runtime generation) — the ceiling-raiser; scoped in the companion spec.
2. G2 (enumerate-first gate) — highest behavioral leverage, stops the review-patch cycle.
3. G4 + G6 + G7 (evidence reach: Node engines, history, attachments) — feeds G1/G2.
4. G3 (consumer-tracing gate) — narrower, reinforces G2.
5. G5 remaining (dimension-enriched eval slice) — so the above can be measured.
