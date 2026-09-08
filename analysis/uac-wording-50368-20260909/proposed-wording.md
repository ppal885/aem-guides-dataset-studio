# GUIDES-50368 — targeted wording revision

Status: proposed wording only; not posted to Jira and not a new gated UAC generation.
The live Acceptance Criteria field has nine ACs and five Open Questions. Keep the existing IDs, AC-01/02/04/05/06/07/08 and all Open Questions. Do not remove a check to meet an AC count cap.

## AC-03 — Language Variables in cross-references

Every Language Variable used in a DITA `<xref>` displays the value defined for the output language. This includes the cross-reference title wording and the "on page" wording when they are configured as Language Variables.

Scope clarification: CSS-generated prefixes for chapter/topic headings, `<section>` titles, and `<fig>` or `<table>` captions are outside this fix. For example, "Figure" in "Figure 1" is a CSS-generated prefix, not the DITA element name. This exclusion applies to those CSS prefixes, not to the DITA elements themselves or to Language Variables used in cross-references to them. The supported cross-reference types still need confirmation under OQ-02.

DITA terminology: the figure element is `<fig>`, not `<figure>`. `<chapter>` is a bookmap reference to a topic or map, not a topic-body heading element. Chapter/topic headings are kept in the scope explanation so it does not become incorrectly limited to bookmaps or literal `<section>` elements.

## AC-09 — Consistent Language Variable resolution

Every Language Variable in the Native PDF output uses the same output-language resolution rules. This includes Language Variables used in cross-references and elsewhere in the PDF. When a `pt_br` value is defined, each use displays that value instead of the `pt` value.

The question of consolidating implementation into a single resolver remains in OQ-05. The visible expected result is retained here; the wording does not claim a code refactor has already been verified.

## Other findings — not silently changed

- Current AC-06 specifies UI-language fallback. The new review attachment and linked test GUIDES-56225 instead expect base-language (`pt`) fallback. The actual linked test description was retrieved and confirms the conflict. Reconcile with QE before executing that expected result. Current Experience League describes UI language, then `en_us`, then `en`. A `pt` result can be legitimate when the UI language itself is `pt`; do not ban that value unconditionally.
- In the Jira's example format, `on page` is literal text outside `${lng:cross-reference-title}`. It is covered as a Language Variable only when explicitly configured that way. `{title}` and `{page}` are template placeholders, not automatically Language Variables.
- Attachment review numbering is stale: it reports eleven ACs, whereas the current field has nine. Retain the live field's IDs rather than adopting the attachment's numbering.
- The sample PDF visibly shows `pt_br-Nota` but a `pt-` cross-reference on page 7; pages 63–65 contain additional `pt-` cross-references. These are pre-fix output observations, not proof of source language settings or fixed behavior.

## Evidence and limits

- Live issue via Jira MCP, then the repository's authenticated Jira client for the actual Acceptance Criteria field and attachment inventory. All nine comments, non-empty issue fields, linked-issue summaries and both direct attachments inspected. The sample PDF's full text was scanned and relevant pages 7, 63–65 and 70 visually inspected.
- The external customer video, Dynamics investigation and Slack discussion were not independently opened. They remain reported references, not independently verified evidence.
- `ask_dita_expert`: three queries sent; one timed out, one answered the wrong part of the question, and the element comparison was only partially grounded. Do not treat those responses as product truth.
- Three focused `query_combined_context` retrievals returned the exact Experience League CSS-prefix distinction, Language Variable fallback and cross-reference Language Variable configuration. Relevant retrieved passages were checked against live official pages; unrelated retrieval matches were rejected.
- RAG readiness identifies an embedded local index, not proof of this run querying the shared VM. No import, index change, skill edit, approval, commit or Jira write was performed.
- Shared-feedback readiness returned `CLIENT_NOT_CONFIGURED`; this correction was not saved to or published by shared VM learning.

Sources:

- https://jira.corp.adobe.com/browse/GUIDES-50368
- https://jira.corp.adobe.com/browse/GUIDES-56225
- https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/output-gen-config/config-native-pdf-publish/native-pdf-language-variables
- https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/output-gen-config/config-native-pdf-publish/components-pdf-template#cross-references
- https://docs.oasis-open.org/dita/dita/v1.3/os/part2-tech-content/langRef/base/fig.html
- https://docs.oasis-open.org/dita/dita/v1.3/os/part2-tech-content/langRef/base/section.html
- https://docs.oasis-open.org/dita/dita/v1.3/os/part2-tech-content/langRef/technicalContent/chapter.html
