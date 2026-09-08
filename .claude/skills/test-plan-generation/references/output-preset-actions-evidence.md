# Output preset actions: documentation and inspected UI

Source: [Edit, duplicate, or delete an output preset](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output-create-edit-preset), updated July 28, 2026; read back from local RAG and visually inspected September 9, 2026.
This is documentation evidence, not Human approval, product-test execution, or an automatic AC checklist.

## Retrieved behaviour

- `aem_ingest_400b02977d_0`: Map console editing changes the selected preset's fields. Duplicate and Delete are in Options.
- `aem_ingest_400b02977d_1`: Map dashboard exposes edit, duplicate, and delete through its top bar.
- Both chunks: editing, duplicating, and deleting **template presets** is restricted to administrators. Do not generalize this to every preset or infer exact role assignments.

Retrieve by the source URL if IDs differ. These two chunks contain the entire short article, including overlapping permission text and navigation/footer noise.

## Every source image inspected

Both PNGs were downloaded and opened; names resolve relative to the source page directory.

| Image | Visible surface |
| --- | --- |
| `media_1a074a5bd95b7e4a6ec0dc1dd8681d39b183a013a.png` | Map console / Output presets. Open Options menu shows Generate, View output, View log, Rename, Duplicate, Delete; the two View actions are greyed. General settings show Site name, Output path, Existing output pages, Design and Retain temporary files. |
| `media_10b557a1ec32ddcf18dce89570560c6b23fea7bc4.png` | Map dashboard / OUTPUT PRESETS. Top actions: Generate, Edit, Duplicate, Create, Delete Preset. AEM Site row is highlighted. Presets Settings is selected beside Publish Context. |

## Terminology and limits

Add **template preset** from text, and **Presets Settings** / **Publish Context** from the second image, with separate provenance. Reuse existing Map console, Map dashboard, and Output Presets terms; do not add generic button names.

The screenshots do not establish logged-in roles, reasons for disabled actions, Publish Context contents, or cross-engine field parity. The source supplies no duplicate-name fallback, copied-field contract, delete-confirmation text, downstream cleanup, or reload/persistence guarantees. Retrieve separate evidence if those questions become material; do not invent answers from this memory.
