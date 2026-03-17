# Agentic Pipeline Setup

Quick setup for Index One, Plan from Jira, and Generate from Jira.

## 1. Jira Configuration (.env)

```env
JIRA_URL=https://jira.corp.adobe.com
JIRA_USERNAME=your_username
JIRA_PASSWORD=your_password
JIRA_PROJECT_KEY=GUIDES
JIRA_API_VERSION=2
```

**Important:** Corporate/on-prem Jira (e.g. `jira.corp.adobe.com`) requires `JIRA_API_VERSION=2`. Jira Cloud uses v3.

## 2. LLM (Optional – Mock Mode Available)

- **With Anthropic key:** Set `ANTHROPIC_API_KEY` for real LLM planning.
- **Without key:** Plan and Generate use mock mode (default domain, single scenario, top recipe candidates). Index One and Jira Search still require Jira.

## 3. Flow

**When Index One 404s but Search works** (common with corporate Jira):

1. **Search** – `POST /api/v1/ai/jira/search` with `{"jql": "project = GUIDES AND status != Closed"}`
2. **Index from Search** – Click "Index" on a result row, or `POST /api/v1/ai/jira/index-from-search` with `{"issues": [{...}]}`
3. **Plan** – Uses DB fallback when Jira get_issue 404s
4. **Generate** – Same as Plan

**Standard flow** (when Index One works):

1. **Index One** – `POST /api/v1/ai/jira/index-one` with `{"issue_key": "GUIDES-41226"}`
2. **Plan** – `POST /api/v1/ai/plan-from-jira` with `{"jira_id": "GUIDES-41226"}`
3. **Generate** – `POST /api/v1/ai/generate-from-jira` with `{"jira_id": "GUIDES-41226"}`

## 4. Troubleshooting

| Error | Fix |
|-------|-----|
| Jira 404 | Set `JIRA_API_VERSION=2` in .env |
| Issue not found | Run Index One first; verify issue exists in Jira |
| Plan/Generate slow | Jira and LLM calls can take 30s–2min; use async mode `?async=true` for Generate |
