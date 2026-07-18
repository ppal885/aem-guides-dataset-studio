# AEM Guides Evidence Gateway Runbook

## Purpose

The Evidence Gateway exposes read-only MCP tools over HTTP for authorized team members. It reuses the existing VM-hosted RAG indexes and optional canonical repository checkouts. It does not proxy Jira; users should continue using the approved Adobe Jira MCP separately.

## Existing Architecture Discovered

- Vector database: ChromaDB persistent client.
- Storage path: `backend/storage/chroma_db`.
- Knowledge collections observed locally: `aem_guides`, `dita_spec`, `dita_ot_github`, `learned_qa`, `jira_qa`.
- AEM Guides RAG entry point: `app.services.doc_retriever_service`.
- DITA spec RAG entry point: `app.services.dita_knowledge_retriever`.
- Existing MCP: stdio-only helper under `mcp_server/`.
- Existing backend auth: static bearer-token/dev-bypass FastAPI dependency. OIDC/OAuth resource-server integration is not present in this repo yet.

## HTTP MCP Endpoint

The gateway is mounted at:

- `POST /mcp`
- `POST /api/v1/mcp`
- `GET /mcp/live`
- `GET /mcp/health`

Production should expose only the private HTTPS URL through approved reverse proxy or ingress:

```json
{
  "mcpServers": {
    "aem-guides-evidence": {
      "type": "http",
      "url": "https://<adobe-private-host>/mcp"
    }
  }
}
```

## Tools

- `health`
- `list_corpora`
- `search_knowledge`
- `fetch_evidence`
- `list_repositories`
- `search_code`
- `fetch_code_context`
- `get_code_diff`

Tool schemas are advertised through JSON-RPC:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8001/mcp `
  -Headers @{ Authorization = "Bearer <token>" } `
  -ContentType application/json `
  -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Safe Configuration

Use placeholders only; inject real values through the deployment secret mechanism.

```env
ENVIRONMENT=production
ALLOW_DEV_AUTH_BYPASS=false
CORS_ALLOWED_ORIGINS=https://<approved-host>

# Existing static-token auth until approved Adobe OIDC integration is wired.
AUTH_TOKENS_JSON=[{"token":"<secret-from-secret-store>","id":"svc-evidence","email":"svc@example.invalid","roles":["evidence"],"allowed_tenants":["*"]}]

EVIDENCE_REQUIRED_ROLE=evidence
EVIDENCE_CORPORA_ALLOWLIST=aem_guides,dita_spec,dita_ot,learned_qa
EVIDENCE_DEFAULT_CORPORA=aem_guides,dita_spec,dita_ot,learned_qa
EVIDENCE_REPOSITORIES_JSON=[
  {"alias":"guides-ui-tests","root":"/srv/aem-guides/repos/guides-ui-tests","diff_access_supported":true},
  {"alias":"dxml-it-test","root":"/srv/aem-guides/repos/dxml-it-test","diff_access_supported":true},
  {"alias":"xml-editor","root":"/srv/aem-guides/repos/xml-editor","diff_access_supported":true},
  {"alias":"starling-backend","root":"/srv/aem-guides/repos/starling-backend","diff_access_supported":true}
]
EVIDENCE_USER_GRANTS_JSON={
  "user@example.invalid":{"corpora":["aem_guides","dita_spec"],"repositories":["guides-ui-tests"]}
}
```

## Authentication Status

Current implementation uses the existing FastAPI bearer-token boundary and per-user corpus/repository authorization. Production OIDC/OAuth 2.1 remains an Adobe-specific integration task because issuer, audience, JWKS, scopes, and group claims are not present in the repository.

Required OIDC behavior for production hardening:

- Validate token signature from approved JWKS.
- Validate issuer and audience for this MCP resource.
- Validate expiration and not-before.
- Map scopes/groups to `EVIDENCE_REQUIRED_ROLE`, corpus grants, and repository grants.
- Keep dev bypass disabled in production.

## Security Controls

- Read-only Chroma queries; no index mutation calls.
- Repository operations use `git` argument arrays with `shell=False`.
- Revision strings reject option-like values.
- Repository paths reject absolute paths, traversal, and root escapes.
- Source windows, diffs, search results, query lengths, and chunk windows are bounded.
- Tool errors return safe categories and correlation IDs, not stack traces.
- Health omits credentials, DSNs, filesystem roots, and secrets.

## Smoke Test

```powershell
$headers = @{ Authorization = "Bearer <token>"; "Content-Type" = "application/json" }
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/mcp -Headers $headers -Body '{
  "jsonrpc":"2.0",
  "id":"smoke-1",
  "method":"tools/call",
  "params":{
    "name":"search_knowledge",
    "arguments":{
      "query":"AEM Guides new baseline migration rollback invalid references",
      "corpus_ids":["aem_guides"],
      "top_k":3
    }
  }
}'
```

## Startup and Shutdown

Use the existing backend deployment mechanism. Do not expose ChromaDB or repository filesystems directly.

Local:

```powershell
cd backend
.\.venv312\Scripts\python.exe run_local.py
```

Production options should reuse the current VM service/container pattern. If using systemd, point it at the existing backend start command and inject environment from a protected env file.

## Health

- Liveness: `GET /mcp/live`
- Authenticated operational health: `GET /mcp/health`
- Existing backend health remains: `GET /health`

## Rollback

Disable the reverse-proxy route for `/mcp` or revert the backend deployment. No indexes, repositories, Jira issues, or production data are modified by this gateway.

