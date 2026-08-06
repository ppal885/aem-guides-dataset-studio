---
description: Generate and report DITA-OT publishing evidence without replacing requested fixtures
argument-hint: Describe constructs, output formats, fixtures, and required evidence
---

Use only `mcp__aem-guides-dataset-studio__generate_dita_ot_output` for this command.

Pass the complete user request unchanged in `prompt`. Normalize only `output_format` and an optional filesystem-safe `package_name`.

After the tool returns:

1. Start with the positive-control status, run ID, output format, and ZIP download path.
2. Add a `Request Coverage` bullet for every requested construct or fixture. Mark it `Generated and executed`, `Generated but not executed`, or `Missing` strictly from returned file and fixture evidence.
3. When `negative_fixture_results` exists, report every fixture ID with its source map, expected signal, exit code, warning/error signal, and generated-output location. A negative fixture may legitimately exit zero; never equate exit zero with the absence of a reproduced behavior.
4. Distinguish expected behavior from observed behavior. Do not turn risk notes into generated evidence.
5. Report packaged logs and `observation_summary` explicitly.
6. Never claim the generator cannot author invalid fixtures when the result contains isolated negative fixtures.
7. Never re-run automatically. If a requested fixture is missing, identify the exact missing item and stop.
8. Do not call `ask_dita_expert`, Jira, GitHub, web, filesystem, or upload tools from this command.
9. Do not suggest local hand-authoring as a substitute for a missing MCP fixture.
10. Emit valid UTF-8. Replace corrupted sequences such as `â€”`, `âœ…`, or `âš ` with plain ASCII punctuation if necessary.

If the generation tool is unavailable, state that the Dataset Studio MCP session must be refreshed. Do not synthesize output evidence.
