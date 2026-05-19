## Post-Processing UAC Focus
- Use evidenced post-processing mechanics: UUID reference updates, BTree/index writes, ReferenceListener events, queue delay, post-publish processors, and generated artifact mutation.
- Separate functional failure from async delay: validate timing/queue behavior only when Jira evidence mentions delayed processing, stuck jobs, listener lag, or retries.
- Treat BSON size risk only when evidence mentions BSONObj too large, oversized payloads, large maps, or high reference volume.
- Ask which processor, queue stage, output artifact, and completion signal prove acceptance when missing.
