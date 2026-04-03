Conrefend + Cyclic References - False Duplicate ID Warnings
============================================================

Reproduces: False "Duplicate ID" Warnings in Guides Web Editor when conrefend + Cyclic References.

Structure:
- topic_a.dita: conref+conrefend range pulls from topic_b.dita (range_start_b to range_end_b)
- topic_b.dita: conref+conrefend range pulls from topic_a.dita (range_start_a to range_end_a)

Cycle: A -> B -> A. When the editor resolves conrefend, the same element IDs can appear
multiple times in the resolved DOM, triggering false duplicate ID warnings.

Expected: Open in AEM Guides Web Editor; may see duplicate ID warnings in Source view
even though the content is valid and publishes correctly.
