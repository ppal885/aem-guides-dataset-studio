"""AEM Guides Product UI Behavior Harvester.

A deterministic, low-token Playwright state crawler that discovers UI topology,
state, and transitions for AEM Guides and writes structured records into the
existing RAG (ChromaDB). It is a PRODUCT capability - it is NOT specialized for
any single Jira. Known Jira/screenshot examples are regression fixtures only.

Design invariants (enforced across the package):
- Observed UI flow is stored as OBSERVED_UI_FLOW, never as EXPECTED_PRODUCT_BEHAVIOR.
- URL alone never defines crawler identity (AEM Guides is a stateful SPA).
- DOM/accessibility drives taxonomy; Vision is a later, separate, opt-in phase.
- Read-only / non-destructive by default; destructive actions are BLOCKED.
- Credentials come only from AEM_USERNAME / AEM_PASSWORD env vars and are never
  written to code, config, logs, screenshots, manifests, or Git.
"""

__version__ = "0.1.0"
