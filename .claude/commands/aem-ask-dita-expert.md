---
description: Ask the VM-backed AEM Guides DITA expert using grounded RAG evidence.
argument-hint: What is searchtitle in DITA and how does AEM Guides use it?
---

You are running the AEM Guides DITA Expert slash command.

Question:

```text
$ARGUMENTS
```

Rules:

1. If `$ARGUMENTS` is empty, ask the user for the exact DITA, DITA-OT, AEM Guides, publishing, editor, workflow, or configuration question and stop.
2. Use the registered `mcp__aem-guides-dataset-studio__ask_dita_expert` tool for VM-backed RAG evidence.
3. This command answers behaviour questions only. If the user asks to generate publishing output, direct them to `/generate-dita-ot-output`; if they ask to upload generated output, direct them to `/aem-upload-generated-to-aem`.
4. Answer directly first, then add short evidence/source bullets when the MCP result provides source titles or URLs.
5. If the MCP evidence is missing, generic, or unrelated, clearly say the answer is not VM-RAG verified instead of guessing.
6. For exact DITA element or attribute behavior, do not treat broad AEM Guides docs or attribute-only evidence as proof for a different element.
7. Do not add, expand, or "complete" product behavior beyond the MCP result. In particular, never invent HTML/JCR mappings, map-versus-topic precedence, fallback chains, indexing/ranking behavior, translation behavior, or version parity.
8. Preserve evidence boundaries exactly. If the MCP result verifies only legacy component mapping, do not generalize it to composite/new mapping or all AEM Guides versions.
9. When the MCP result distinguishes verified implementation behavior from unverified adjacent claims, keep both lists separate and do not replace verified code evidence with a generic "not VM-RAG verified" statement.
10. Treat the MCP result as evidence to answer the user's question, not as text to copy unchanged. Cover every explicitly requested facet in the user's order.
11. For a requested facet that the evidence does not answer, write `Not verified from current evidence` under that facet and identify the exact runtime observation, product-code path, or official documentation needed to verify it.
12. Never return only a list of links or a generic source summary. Connect each retained source to the exact claim it supports and omit adjacent sources that do not prove the requested behavior.
13. For compound publishing questions, keep DITA specification behavior, DITA-OT generated behavior, AEM Guides product mapping, and environment/version boundaries separate.
