---
name: jira-rag-indexing
description: >
  Index Jira issues into the RAG (ChromaDB) for semantic search and retrieval.
  Use this skill whenever the user wants to: index a Jira issue, search for similar
  Jira issues, find related bugs, check if a Jira key is already indexed, add Jira
  issues to the knowledge base, or improve dataset generation by pulling similar past
  issues. Triggers on: "index GUIDES-XXXXX", "add jira to RAG", "find similar jira",
  "search jira issues about X", "jira RAG", "index jira for retrieval", or any
  request to persist Jira knowledge for future similarity lookups.
---

# Jira RAG Indexing Skill

Every Jira issue processed for dataset generation is automatically indexed into
ChromaDB. This skill lets you manually trigger indexing, check index status, and
use indexed issues for similarity-based dataset improvement.

---

## 1. Auto-Indexing (Happens Automatically)

When you type a Jira key like `GUIDES-48304` to generate a dataset, the system:
1. Fetches the full issue (description, comments, attachments)
2. Generates a DITA scenario analysis
3. **Automatically indexes the issue into ChromaDB** in the background
4. Next time a similar issue arrives, the indexed analysis is used as prior context

You don't need to do anything — it happens transparently.

---

## 2. Manual Index: Index a Specific Issue

```
POST /api/v1/admin/index-jira/{issue_key}
Authorization: Bearer dev-bypass
```

This indexes the issue immediately (synchronous). Use it when:
- You want to pre-populate the RAG before generating datasets
- The auto-index failed (e.g. no network at generation time)
- You're bulk-loading a set of issues

**Via chat:** say `Index GUIDES-48304 into RAG` and the system will call the endpoint.

---

## 3. Search Similar Jiras

```
POST /api/v1/admin/search-jira-rag
Body: {"query": "keyword popup not appearing in AEM Guides", "limit": 5}
```

Returns the top matching indexed issues with similarity scores.

**Via chat:** say `Find Jira issues similar to GUIDES-48304` or
`Search RAG for issues about prolog metadata AEM Sites`.

---

## 4. How Indexed Issues Improve Dataset Generation

When generating a dataset from a Jira issue:

1. **Direct lookup**: if the exact key is indexed, its prior DITA analysis (element names,
   scenario, topic recommendations) is loaded as context
2. **Similarity search**: top 3 related indexed issues are found by semantic similarity
3. **Enriched analysis**: the LLM sees prior analyses of similar issues when reasoning
   about what DITA elements/topics to generate

Example — GUIDES-44087 (prolog not propagating to AEM Sites headnode):
- Without RAG: LLM reasons from scratch about prolog/headnode
- With RAG: finds GUIDES-43210 (similar AEM Sites output mapping issue) and reuses
  its validated dataset structure as a starting point

---

## 5. Index Status

```
GET /api/v1/admin/jira-rag-status
```

Returns count of indexed issues, last index timestamp, and collection health.

---

## 6. Bulk Index a Project

To index all open issues from the GUIDES project:

```
POST /api/v1/admin/index-jira-bulk
Body: {"jql": "project = GUIDES AND updated > -30d", "limit": 100}
```

This runs async (returns a job ID). Check progress with `GET /api/v1/admin/jira-rag-status`.

---

## 7. LLM Reasoning with Indexed Jiras

When a user asks about a Jira issue in chat, the system:
1. Checks if the issue is already indexed (instant retrieval)
2. Finds semantically similar indexed issues
3. Presents them as additional context in the DITA analysis

Topic recommendations become **more specific** as more issues are indexed because
the system can say: "Issue GUIDES-44087 is similar to GUIDES-43210 which generated
these 5 concept topics about AEM Sites output mapping — reuse that structure."
