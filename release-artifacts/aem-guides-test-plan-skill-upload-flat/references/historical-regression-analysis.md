# Historical Regression Analysis

Use Jira MCP/search as a risk-signal source, not as a specification source.

## Retrieval Rules

Search related historical JIRAs using:

- exact feature names, UI labels, error messages, exception classes, service/method names, and configuration keys;
- customer-visible symptom wording;
- DITA construct names such as Schematron, map, topic, keyref, conref, baseline, output preset, validation;
- changed file/component names when available.

Record source, query, matched issues, and why each issue is relevant or not relevant.

## Signals To Extract

Identify:

- reopened bugs;
- customer escapes or support escalations;
- similar exceptions or logs;
- previous fixes and whether they were narrow/broad;
- related components and shared paths;
- missing automation patterns;
- duplicate/empty/multiple input variants repeatedly missed;
- recurrence around configuration inheritance, persistence, cache, retry, or async jobs.

## Use In Plans

Historical JIRAs increase risk priority or suggest hypotheses. They do not override current requirements, code, docs, or reproduction evidence. If historical evidence conflicts with current evidence, label the conflict and keep confidence lower.
