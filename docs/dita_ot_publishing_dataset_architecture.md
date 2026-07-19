# DITA-OT Publishing Dataset Architecture

This workflow keeps publishing-behavior data generation separate from
single-topic DITA authoring.

## Routing Contract

- Single-topic authoring requests route to `generate_dita`.
- PDF, PDF2, HTML, XHTML, HTML5, publishing, output, or DITA-OT evidence
  requests route to the DITA-OT publishing path.
- Follow-up prompts such as `above`, `same`, `previous`, or `this combination`
  must merge recent user context before construct detection.
- Upload-only requests route to AEM upload tools and must not generate new data.

## Shared Service

All chat, slash-command, and MCP callers should use:

`backend/app/services/publishing_dataset_intent_service.py`

That service owns:

- publishing dataset intent detection;
- output-format detection normalization;
- prior-context expansion;
- tool argument normalization;
- safe package-name generation.

Do not add new one-off routing branches in `chat_service.py` or MCP tools for
individual prompts. If a new DITA construct is missing, add it to the registry.

## Construct Registry

Publishing corpus behavior is registry-driven:

`backend/app/services/dita_publishing_construct_registry.py`

Each construct entry should define:

- map usage pattern;
- topic usage pattern;
- safe positive case;
- negative or risk case;
- PDF review areas;
- HTML/HTML5 review areas;
- QA checklist;
- validation oracles.

Examples: `copy-to`, `chunk`, `xml:lang`, `keyref`, `conref`, `conkeyref`,
`conrefpush`, `conrefend`, `xref`, `map-attributes`,
`conditional-processing`, `mapref`, and `reltable`.

## Regression Rule

When a prompt fails, add a test for the behavior class:

- routing to DITA-OT vs `generate_dita`;
- context expansion;
- construct detection;
- corpus source files and oracles.

Do not add a branch that only matches the exact failed prompt.
