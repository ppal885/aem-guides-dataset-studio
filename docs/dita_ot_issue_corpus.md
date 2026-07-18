# DITA-OT Issue Corpus

Convert DITA-OT GitHub issues into DITA topics, then index them as retrieval evidence.

## Direct GitHub URL

```powershell
backend\.venv312\Scripts\python.exe scripts\convert_dita_ot_issues_to_dita.py `
  --input https://github.com/dita-ot/dita-ot/issues `
  --state all `
  --output-dir dita-ot-issue-corpus `
  --reset
```

If GitHub returns `403`, set a token and rerun:

```powershell
$env:GITHUB_TOKEN = "YOUR_TOKEN_HERE"
backend\.venv312\Scripts\python.exe scripts\convert_dita_ot_issues_to_dita.py `
  --input https://github.com/dita-ot/dita-ot/issues `
  --state all `
  --output-dir dita-ot-issue-corpus `
  --reset
```

For large repositories, the converter uses GitHub GraphQL cursor pagination when
`GITHUB_TOKEN` is available. Without a token it falls back to the REST API and
only fetches the first 10 pages to avoid GitHub's large-dataset `page`
pagination failure.

## GitHub CLI Export Fallback

If direct API access is blocked, export issues with GitHub CLI and pass the JSON file:

```powershell
gh issue list `
  --repo dita-ot/dita-ot `
  --state all `
  --limit 5000 `
  --json number,title,state,url,body,labels,author,createdAt,updatedAt,closedAt `
  > tmp\dita-ot-issues.json

backend\.venv312\Scripts\python.exe scripts\convert_dita_ot_issues_to_dita.py `
  --input tmp\dita-ot-issues.json `
  --output-dir dita-ot-issue-corpus `
  --reset
```

## Index for Retrieval

```powershell
backend\.venv312\Scripts\python.exe scripts\index_dita_behavior_corpus.py `
  --corpus-root dita-ot-issue-corpus\topics `
  --output backend\storage\dita_ot_issue_behavior_chunks.json
```
