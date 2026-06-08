Nested Keydef Chain (Map A -> Map B -> Topic C)
==============================================

Reproduces AEM Guides Web Editor: nested keys not resolved when Map A is context.

Structure:
- Map A (map_a.ditamap): keydef staticKeyMap -> map_b.ditamap; topicref -> topic_d_consumer.dita
- Map B (map_b.ditamap): keydef productName (inline); keydef keywordFile -> topic_c_keywords.dita
- Topic C (topic_c_keywords.dita): keywords with id=versionString
- Topic D (topic_d_consumer.dita): uses keyref ['productName', 'versionString']

Expected: When Map A is opened as context, keys should resolve.
Bug: Keys only resolve when Map B is opened as root. DITA-OT publishes correctly.

Workaround: Open Map B as root context map to verify keys resolve.