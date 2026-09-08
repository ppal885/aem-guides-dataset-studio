# Adjacent-feature discovery candidate — 2026-09-09

Status: source candidate, **not a qualified production release**.
Base: `957a8d84523e4d6ddf7719cfd65c8856aa986b15`.

## Scope

- Every exact discovery needs retained evidence, terminal verification and a linked
  disposition. A copied feature key or broad axis no longer clears DISCOVERY REVIEW.
- Recorded sibling configuration and consumer findings become separate candidates.
- Native PDF activates separate, advisory Variables and Variable Sets investigations.
  Language Variables do not establish their behavior or acceptance scope.
- Existing query limits stay unchanged; surface rotation reduces starvation and
  deferred/unexecuted query groups remain visible.
- Coverage/scope revisions rerun discovery; wording-only edits cannot claim a fresh
  completeness check. No automatic acceptance promotion was added.
- Source matching preserves line ranges. Nonoverlapping citations, or direct evidence
  IDs pointing at another source, cannot silently clear the discovery note.

The source change is restricted to 14 skill files in each of the five repository
copies. Backend, evaluation calculations, corpus, MCP transport and dashboard code
are unchanged by this commit. Unrelated changes in the original dirty checkout,
including separate language-policy work, were not included.

## Validation and artifacts

- Focused checks: 55 disposition, 13 recorded-neighbor, 41 Native PDF/query-budget,
  and 11 forward-pipeline checks.
- Full self-tests pass in all five repository copies and two isolated installed
  copies. Real user installations are not overwritten to satisfy release parity.
  The initial installed-copy test profile was nested under the dirty checkout and
  correctly failed parity against that different source. Moving only the test
  profile under the release worktree produced the final seven passing results;
  no production validation or gate was weakened.
- Existing-workspace canonical self-tests also passed after the line-binding repair;
  the two repaired files were mirrored only after existing mirror hashes matched.
- Production hardcoding audit and whitespace validation pass. Bounded manual code
  review found and fixed the line-binding issue. Bandit was unavailable; this is not
  a comprehensive dependency/security certification. No dependencies were added.
- All three candidate ZIPs preserve every unrelated previously published member.
  Each updates seven skill members and adds seven; no member is deleted. Two command
  documents existed only in the previous published client ZIPs, so their exact bytes
  were retained instead of silently removing them during the standard rebuild.
- The 193 enforced files match the source and all three ZIPs. Candidate fingerprint:
  `ea17b611c4d848c9ddc943b8d054ccdb9e789e6b848986a7c2d7b01d3d0ed6b7`.

Archive SHA-256:

- Windows: `27024bbed1b765ecf383135894be908bc042b79b17101dd640a1fef9c8b2cb45`
- Unix: `1d2ab87814288a3791f3e5bf0259b417bf43c08908680ec2e775265ad84963e8`
- Claude skill: `02fa8c7819a0be860bbdbfea03e79565b8b4f06a09b08378171d1b6060c05370`

## Deployment and benchmark hold

The actual golden-suite validator accepts the 18-case manifest, but reports
`golden_status=seeded`. No approved baseline was found in the inspected benchmark
and artifact locations. This is schema validation, not a passing live benchmark.
No goldens were approved, expected answers inspected for generation, or waivers added.

The VM gateway health check returned alive. The noninteractive SSH attempt was
denied, so no VM pull, installation, restart, index write or writer-resume happened.
Prior routing diagnostics separately found that this workstation's registered RAG
connector targets local storage; that is not proof of using the team VM index.
This skill-only commit does not repair or certify transport/corpus parity.

Before production deployment:

1. Obtain accountable QE review of each golden case and the reviewed suite approval.
2. Run fresh, blinded Claude and Codex candidates with verified VM-backed evidence
   access, complete artifacts, normal gates, and the correct per-variant skill root.
3. Score against the approved baseline, or establish an initial approved baseline
   through the existing reviewed process. Do not substitute an offline monitor.
4. With authenticated VM access, preserve local changes, deploy the qualified commit,
   sync reviewed skill files, verify copy hashes and run the existing VM read-only
   routing/retrieval checks. Do not overwrite local overrides or resume corpus writers
   as a side effect of this skill update.

See `.codex/skills/test-plan-generation/references/golden-benchmark.md` for the
existing release policy. Until these checks pass, distributing these artifacts is
candidate evaluation only, not a claim of a production-qualified release.
