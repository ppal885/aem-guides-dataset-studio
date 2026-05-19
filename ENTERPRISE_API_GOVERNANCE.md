# Enterprise API Governance

This project now treats the backend as a secure internal application, not an anonymous demo API.

## Canonical Status Endpoints

- `GET /health`
  - Public health probe for load balancers and local smoke checks.
- `GET /api/v1/limits`
  - Public static limits/status surface for the frontend bootstrap.
- `GET /api/v1/ai/rag-status`
  - Authenticated canonical RAG status endpoint.
- `GET /api/v1/rag-status`
  - Deprecated alias.
  - Kept only for compatibility.
  - Clients should migrate to `/api/v1/ai/rag-status`.

## Authentication Policy

- All `/api/v1/chat/*` routes require authenticated users.
- Most `/api/v1/ai/*` routes now require authenticated users.
- Administrative AI and tenant-management routes require admin privileges.
- Root `/` and `/health` remain unauthenticated.
- `/api/v1/limits` remains unauthenticated for lightweight frontend bootstrap.

## Tenant and Ownership Rules

- Tenant resolution is enforced through `X-Tenant-ID` plus authenticated user scope.
- Chat sessions are now owned by `user_id` and `tenant_id`.
- AI dataset runs are now owned by `user_id` and `tenant_id`.
- Async run progress (`/api/v1/ai/generate-status/*`, `/generate-stream/*`) is owner-scoped.
- Cross-tenant and cross-user access should return `404` or `403`, not leaked metadata.

## Compatibility Policy

- Prefer additive changes over breaking response changes.
- If an endpoint must be replaced, keep the old endpoint as a deprecated alias when practical.
- Use consistent `401`, `403`, and `404` semantics:
  - `401` for missing/invalid auth
  - `403` for an authenticated user asking for a tenant they are not allowed to access
  - `404` for tenant-scoped or owner-scoped resources that should not be disclosed

## Production Safety Rules

- `ALLOW_DEV_AUTH_BYPASS` must be disabled in production.
- `CORS_ALLOWED_ORIGINS` must be explicitly configured in production.
- Wildcard CORS is not allowed in production.
- At least one configured auth token source must exist in production.

## Mounted Enterprise Routers

The API router now explicitly mounts and supports these previously drifting route groups:

- `/api/v1/storage/*`
- `/api/v1/ai/flow-intelligence`
- `/api/v1/admin/tenants/*`
- `/api/v1/smart/*`
- `/api/v1/docs/*`

These are part of the supported internal API surface and should be treated as governed routes.
