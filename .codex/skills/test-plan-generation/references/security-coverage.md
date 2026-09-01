# Security Coverage Contract

Use this contract whenever the current plan or evidence manifest contains a
security activation signal. It is a deterministic coverage forcing gate, not a
security implementation review and not authority to invent product behavior.

## Purpose

AEM Guides accepts and transforms XML/DITA content, resolves references, exposes
content-processing endpoints, publishes to repositories and shared destinations,
and applies role-based access. A plan that touches one of those paths must either
cover its applicable security outcome or consciously defer the decision. Silence is
not a safe default.

The gate checks only whether the security dimension is represented by mapped
Acceptance Criteria or an explicit Open Question. Existing publishing, API,
configuration, and implementation-grounding gates continue to own their normal
content checks.

## Activation

`scripts/security_coverage.py` examines both the plan body and manifest evidence.
Any of these strong signals activates the corresponding dimension:

- `INPUT_SAFETY`: XML/DITA parsing or ingestion, DITA upload/import, or entity/DTD
  handling such as XXE, DOCTYPE, external entities, or entity expansion.
- `REFERENCE_TRAVERSAL`: conref, conkeyref, keyref, href, xref, or explicit DITA
  reference resolution.
- `AUTHZ`: a REST/API/servlet/endpoint accepting user content, publishing/output to
  a shared location, or an ACL, authorization, permission, or role-bearing operation.

Ordinary non-security plans with none of these signals remain backward-compatible
and pass without a `security_coverage` block. Generic output generation or a
generated XML file alone does not activate input-parser security.

## Manifest Block

Once any signal is active, record all three dimensions. Applicable dimensions map
to coverage or a decision-shaped Open Question. Genuinely inapplicable dimensions
must say why; omission never means not applicable.

```json
{
  "security_coverage": {
    "schema_version": "aem-guides-security-coverage-v1",
    "dimensions": [
      {
        "dimension": "INPUT_SAFETY",
        "disposition": "COVERED_BY_AC",
        "reason": "The changed upload path parses user-supplied DITA.",
        "ac_refs": ["AC-01", "AC-02", "AC-03"]
      },
      {
        "dimension": "REFERENCE_TRAVERSAL",
        "disposition": "NOT_APPLICABLE",
        "reason": "The change does not resolve DITA references.",
        "ac_refs": []
      },
      {
        "dimension": "AUTHZ",
        "disposition": "OPEN_QUESTION",
        "reason": "The accepted role boundary is not defined yet.",
        "open_question_ref": "OQ-01"
      }
    ]
  }
}
```

Allowed dispositions are:

- `COVERED_BY_AC`: provide non-empty `ac_refs` that exist in the plan. The mapped
  AC text must cover the complete applicable dimension.
- `OPEN_QUESTION`: provide one `open_question_ref` that exists in the plan. The
  question must contain `QA impact:` and name the complete missing security decision.
- `NOT_APPLICABLE`: provide a concrete reason explaining why the signalled change
  does not exercise that security boundary. A bare `N/A`, `none`, `unknown`, or
  similar placeholder fails. The signal activates the ledger; it does not authorize
  the gate to invent applicability.

## Required Coverage

### INPUT_SAFETY

The mapped ACs, or the mapped Open Question when the contract is undecided, must
cover all of these independently observable outcomes:

- external-entity resolution/XXE is disabled or rejected;
- entity expansion, including Billion Laughs behavior, has a defined limit or is
  rejected;
- malformed XML/DITA input has a defined safe failure outcome;
- oversized XML/DITA input has a defined safe failure outcome.

One broad sentence such as "invalid XML is handled safely" is insufficient because
it does not cover XXE, resource exhaustion, and size boundaries separately.

### REFERENCE_TRAVERSAL

The mapped AC or Open Question must state that conref/keyref/href/xref resolution
cannot traverse outside the permitted content scope. Include the observable denied
or rejected outcome; do not prescribe a particular path-normalization implementation.

### AUTHZ

The mapped ACs or Open Question must cover both outcomes:

- an unauthorized role or user is denied; and
- the changed endpoint, publish path, or permission-bearing operation cannot bypass
  access control or cause privilege escalation.

Authentication success alone is not authorization coverage.

## Interactions and Boundaries

- Current Jira/UAC remains product-contract authority. If the exact security outcome
  is not approved, use `OPEN_QUESTION`; do not fabricate a Confirmed AC.
- Git/code evidence may prove the current parser, resolver, or permission path, but it
  does not automatically promote a product AC.
- The gate does not require every security dimension on every ticket. It requires an
  explicit, concrete `NOT_APPLICABLE` reason for every genuinely irrelevant
  dimension once the security ledger is active, including a false-positive signal
  that does not exercise the changed path.
- Do not copy hostile payloads, credentials, private paths, or customer content into
  the manifest. Name the attack class and observable outcome instead.
- Keep technical parser settings and implementation choices in evidence or code
  review. Acceptance Criteria state observable rejection, containment, and access
  results.

## Command

```text
python scripts/security_coverage.py --plan <plan.md> --manifest <manifest.json>
```

Exit `0` means the gate is inactive or every disposition is complete. Exit `1`
prints one or more stable `SECURITY GATE:` failures.
