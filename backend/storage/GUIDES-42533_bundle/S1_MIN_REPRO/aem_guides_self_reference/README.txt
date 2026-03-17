Self-Reference Dataset
====================

This dataset demonstrates a topic that references itself via keyref.

Structure:
- Map defines key "self" -> self_ref_topic.dita
- Topic self_ref_topic.dita contains <xref keyref="self"/> (points to itself)

Use case: Testing AEM Guides right panel (outgoing links / forward reference)
when displaying self-reference. Bug GUIDES-42286: self reference may show
empty in right panel.
