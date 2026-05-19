## UUID UAC Focus
- Use evidenced UUID mechanics: UUID references, duplicate/missing UUID, stale reference maps, BTree lookup, ReferenceListener behavior, and downstream publish/index effects.
- Treat queue delay, async reference update, or post-processing lag as acceptance risks only when Jira mentions timing, queue, listener, or delayed propagation.
- Validate BSON size risk only when Jira mentions BSON, large payload, large map, too many references, or bulk post-processing.
- Ask which UUID reference, map/topic, queue stage, and output/index consumer define acceptance when missing.
