# Authoritative source-to-UAC coverage

Use this contract before discovery, hypotheses, or UI/action validation when a
behavioral v3 manifest contains a Jira description, Jira comments, or analysed
attachment text. It extends the existing `contract_facts` and source-fidelity
path; it is not a second planning or acceptance-authority model.

## Purpose

The intake sources define what must be dispositioned. Atomize every meaningful
source clause before testing hypotheses:

- Map a material fact to an Acceptance Criterion.
- Map it to a real Open Question when a product decision is genuinely unknown.
- Map it to an explicit out-of-scope disposition with a concrete source-backed
  reason.

Do not let an investigation hypothesis, current implementation observation,
ownership check, or unsupported UI-action claim select, narrow, or remove a
source-backed requested outcome. Those inputs can widen investigation or expose
an implementation gap only.

## Manifest contract

Declare `authoritative_source_coverage` with schema
`aem-guides-authoritative-source-coverage-v1`.

```json
{
  "authoritative_source_coverage": {
    "schema_version": "aem-guides-authoritative-source-coverage-v1",
    "sources": [
      {
        "source_id": "TSRC-01",
        "source_ref": "issue.description",
        "source_kind": "JIRA_DESCRIPTION",
        "raw_text": "Exact source text",
        "sha256": "lowercase SHA-256 of raw_text",
        "inspected": true,
        "atomization_complete": true
      }
    ],
    "facts": [
      {
        "fact_id": "TSF-01",
        "source_id": "TSRC-01",
        "verbatim_text": "Exact material source clause",
        "material": true,
        "destination": "ACCEPTANCE_CRITERION",
        "contract_fact_refs": ["CF-01"],
        "ac_refs": ["AC-01"],
        "required_terms_all": ["material source term"]
      }
    ]
  }
}
```

The gate derives the required source list from current manifest intake:

- `issue.description` is `JIRA_DESCRIPTION`.
- Every retained `issue.comments` entry is `JIRA_COMMENT`.
- Every analysed attachment with retained inspected text is
  `ANALYSED_ATTACHMENT`.

Keep the exact current source text in each source record. The source hash and
complete atomization prevent a summary from silently replacing the source. An
analysed attachment must retain inspected facts in one of `raw_text`,
`extracted_text`, `ocr_text`, `text`, `analysis_text`, or `analysis`; a filename
or a bare "analysed" flag is not an atomizable fact.

Each material atom must reference one or more existing `contract_facts` whose
source, literal wording, destination, and destination reference agree. The
atom's required terms and protected identifiers must survive in its mapped AC,
Open Question, or explicit out-of-scope reason.

Use `NOT_MATERIAL` only for source context that is not a ticket contract. It
requires a concrete `materiality_reason` and cannot reference `contract_facts`.
It does not permit an unclassified source clause to disappear.

## Required order

1. Inspect and retain the description, comments, and attachment facts.
2. Atomize each source and disposition material facts through `contract_facts`.
3. Run the authoritative source coverage gate.
4. Run discovery and hypotheses to investigate additional dimensions.
5. Validate implementation, ownership, routes, and UI actions without changing
   the source-fact destination.

## UI-action boundary

An outcome requested by a source is still covered when the current product
surface does not prove a claimed existing action. Preserve the outcome in its
AC, out-of-scope record, or decision question. Then record the unsupported
existing-action assertion separately:

- A proven existing action needs `claim_status: "PROVEN"` and current,
  surface-specific selectable-action proof.
- An unproven existing-action assertion uses `claim_status: "UNVERIFIED"`,
  a concrete `unverified_reason`, source references for the claim, and a
  matching Open Question.

Do not turn a configured result, backend effect, or documentation outcome into
proof that a selectable control already exists. Conversely, do not delete the
requested outcome to make an action-proof failure disappear.

## Gate behavior

`run_gates.py` runs authoritative source coverage before discovery and
dimension-inventory gates. It fails when a source is omitted, an atom omits a
material source clause, a material atom lacks a direct AC/Open Question/out-of-
scope destination, a mapped term disappears, or a hypothesis is used as a
scope destination.
