# Publishing DITA-OT + Preset Scope Coverage (mandatory for publishing tickets)

For any PUBLISHING ticket (Jira component Publishing, or an output preset / output
generation is in scope), the acceptance criteria MUST explicitly cover both:

1. **DITA-OT processing ON and OFF** - the behaviour when the preset uses the DITA-OT
   engine versus the native engine (for example Native PDF native engine vs DITA-OT
   PDF), which mode is in scope, and what stays unchanged in the other mode.
2. **Preset IN-scope / OUT-of-scope** - which output preset the change applies to, and
   which presets (AEM Site, HTML5, JSON, DITA-OT PDF, etc.) are out of scope unless
   shared-code analysis proves the metadata/output path is shared.

Enforced by `scripts/publishing_scope_coverage.py` inside `run_gates.py`. The check
activates when the issue component is Publishing or the plan carries a strong
output-preset / output-generation signal, and it fails a publishing plan whose
Acceptance Criteria section does not mention a DITA-OT engine-mode boundary and an
explicit preset in/out-of-scope statement. Non-publishing plans are unaffected.

Author these as real observable ACs, e.g.:
- a DITA-OT-mode boundary AC ("a preset using the DITA-OT engine keeps its existing
  metadata behaviour; this fix changes only the native engine path"), and
- a preset-scope AC ("the fix is scoped to the Native PDF preset; AEM Site, HTML5,
  JSON, and DITA-OT PDF are out of scope unless shared-code analysis proves the path
  is shared").

This is a product policy, not a style rule: publishing behaviour diverges sharply by
engine and by preset, so omitting either silently under- or over-scopes the fix.
