"""
Tenant Service — multi-client isolation layer.

Every API call carries a tenant_id. This service:
1. Resolves tenant config (Jira URL, KB, style rules)
2. Routes ChromaDB queries to the right collection
3. Loads tenant-specific knowledge base
4. Keeps all client data completely isolated

The kone_knowledge_base.py becomes ONE tenant's config.
Every other client gets the same structure with their own data.

Place at: backend/app/services/tenant_service.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

TENANTS_DIR = Path(__file__).resolve().parent.parent / "storage" / "tenants"
TENANTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TENANT = "kone"   # for backwards compatibility with existing project


# ── Tenant config structure ───────────────────────────────────────────────────

@dataclass
class TenantConfig:
    tenant_id:      str
    name:           str
    jira_url:       str          = ""
    jira_token:     str          = ""   # encrypted at rest
    jira_email:     str          = ""

    # ChromaDB collection names — all prefixed with tenant_id
    rag_collection:     str      = ""   # e.g. "kone_rag"
    examples_collection: str    = ""   # e.g. "kone_examples"
    research_collection: str    = ""   # e.g. "kone_research"

    # Knowledge base
    terminology:    dict         = field(default_factory=dict)  # generic → specific
    forbidden_terms: list[str]   = field(default_factory=list)
    style_rules:    str          = ""   # full style guide text
    component_map:  dict         = field(default_factory=dict)  # jira component → audience

    # Audience profiles (simplified — full profiles in shared module)
    custom_audiences: dict       = field(default_factory=dict)

    # Settings
    created_at:     str          = ""
    is_active:      bool         = True
    plan:           str          = "standard"   # standard | enterprise

    def to_dict(self) -> dict:
        return {
            "tenant_id":          self.tenant_id,
            "name":               self.name,
            "jira_url":           self.jira_url,
            "rag_collection":     self.rag_collection,
            "examples_collection": self.examples_collection,
            "research_collection": self.research_collection,
            "component_map":      self.component_map,
            "is_active":          self.is_active,
            "plan":               self.plan,
        }

    # ── Collection name helpers ───────────────────────────────────────────
    def collection(self, type: str = "rag") -> str:
        """Get the ChromaDB collection name for this tenant."""
        map = {
            "rag":      self.rag_collection,
            "examples": self.examples_collection,
            "research": self.research_collection,
        }
        return map.get(type, self.rag_collection)


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_tenant(
    tenant_id:    str,
    name:         str,
    jira_url:     str = "",
    jira_token:   str = "",
    jira_email:   str = "",
    plan:         str = "standard",
) -> TenantConfig:
    """Create a new tenant workspace. Provisions all storage automatically."""
    from datetime import datetime

    # Validate tenant_id — alphanumeric + underscore only
    import re
    if not re.match(r'^[a-z0-9_]+$', tenant_id):
        raise ValueError("tenant_id must be lowercase alphanumeric with underscores")

    if _load_tenant(tenant_id) is not None:
        raise ValueError(f"Tenant '{tenant_id}' already exists")

    cfg = TenantConfig(
        tenant_id            = tenant_id,
        name                 = name,
        jira_url             = jira_url,
        jira_token           = jira_token,
        jira_email           = jira_email,
        rag_collection       = f"{tenant_id}_rag",
        examples_collection  = f"{tenant_id}_examples",
        research_collection  = f"{tenant_id}_research",
        created_at           = datetime.utcnow().isoformat(),
        plan                 = plan,
    )

    # Create tenant storage directory
    tenant_dir = TENANTS_DIR / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    (tenant_dir / "approved_topics").mkdir(exist_ok=True)
    (tenant_dir / "style_guide").mkdir(exist_ok=True)
    (tenant_dir / "audit_logs").mkdir(exist_ok=True)

    _save_tenant(cfg)

    logger.info_structured(
        "Tenant created",
        extra_fields={"tenant_id": tenant_id, "name": name},
    )
    return cfg


def get_tenant(tenant_id: str) -> TenantConfig:
    """Get tenant config. Raises if not found."""
    cfg = _load_tenant(tenant_id)
    if cfg is None:
        # Fall back to KONE config for backwards compatibility
        if tenant_id == DEFAULT_TENANT:
            return _build_kone_default()
        raise ValueError(f"Tenant '{tenant_id}' not found")
    return cfg


def update_tenant_kb(
    tenant_id:     str,
    terminology:   Optional[dict]      = None,
    style_rules:   Optional[str]       = None,
    component_map: Optional[dict]      = None,
    forbidden_terms: Optional[list]    = None,
) -> TenantConfig:
    """Update tenant knowledge base — called from admin panel."""
    cfg = get_tenant(tenant_id)
    if terminology:
        cfg.terminology.update(terminology)
    if style_rules:
        cfg.style_rules = style_rules
    if component_map:
        cfg.component_map.update(component_map)
    if forbidden_terms is not None:
        cfg.forbidden_terms = forbidden_terms
    _save_tenant(cfg)
    return cfg


def list_tenants() -> list[dict]:
    """List all tenants (admin only)."""
    tenants = []
    for path in TENANTS_DIR.glob("*/config.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            tenants.append({
                "tenant_id": data.get("tenant_id"),
                "name":      data.get("name"),
                "is_active": data.get("is_active", True),
                "plan":      data.get("plan", "standard"),
            })
        except Exception:
            pass
    return tenants


# ── Tenant-aware KB builder ───────────────────────────────────────────────────

def build_tenant_context(tenant_id: str, issue: dict, intent_type: str) -> dict:
    """
    Build context object for generation — tenant-aware version of
    kone_knowledge_base.build_kone_context().

    For KONE: loads KONE-specific terminology, audiences, style rules.
    For IBM:  loads IBM-specific terminology, audiences, style rules.
    For any client: loads their uploaded KB automatically.
    """
    cfg = get_tenant(tenant_id)

    # Import shared audience detection
    from app.services.kone_knowledge_base import (
        AUDIENCE_PROFILES,
        WRITING_PATTERN_EXAMPLES,
        KONE_STYLE_RULES,
    )

    # Detect audience using tenant's component map
    audience_id = _detect_audience_for_tenant(issue, cfg)

    # Build terminology rules from tenant KB
    terminology_rules = _build_terminology_for_tenant(issue, cfg)

    # Style rules: tenant-specific if uploaded, else shared DITA rules
    style_rules = cfg.style_rules or KONE_STYLE_RULES

    # Get audience profile (shared profiles, tenant labels override)
    audience = AUDIENCE_PROFILES.get(audience_id, AUDIENCE_PROFILES.get("aem_author", {}))

    # Writing examples (shared structural patterns)
    examples = _select_examples_for_tenant(audience_id, intent_type)

    # Product context from component map
    product_context = _detect_product_for_tenant(issue, cfg)

    return {
        "tenant_id":        tenant_id,
        "product_context":  product_context,
        "audience_id":      audience_id,
        "audience":         audience,
        "terminology_rules": terminology_rules,
        "style_rules":      style_rules,
        "writing_examples": examples,
        "forbidden_terms":  cfg.forbidden_terms,
        "conref_hints":     [],  # tenant-specific conrefs added by admin
        "rag_collection":   cfg.rag_collection,
        "examples_collection": cfg.examples_collection,
    }


def _detect_audience_for_tenant(issue: dict, cfg: TenantConfig) -> str:
    """Detect audience using tenant's own component→audience map."""
    components = issue.get("components") or []
    labels     = [l.lower() for l in (issue.get("labels") or [])]

    # Check tenant's component map first
    for comp in components:
        if comp in cfg.component_map:
            return cfg.component_map[comp].get("audience", "aem_author")

    # Fall back to shared detection
    from app.services.kone_knowledge_base import _detect_audience as shared_detect
    return shared_detect(issue)


def _detect_product_for_tenant(issue: dict, cfg: TenantConfig) -> str:
    """Detect product using tenant's component map."""
    components = issue.get("components") or []
    for comp in components:
        if comp in cfg.component_map:
            return cfg.component_map[comp].get("product", cfg.name)
    return cfg.name


def _build_terminology_for_tenant(issue: dict, cfg: TenantConfig) -> list[str]:
    """Build terminology rules from tenant's own KB."""
    rules   = []
    summary = (issue.get("summary") or "").lower()

    for generic, specific in cfg.terminology.items():
        if generic.lower() in summary:
            rules.append(f"Use '{specific}' instead of '{generic}'")
        elif len(rules) < 6:
            # Include top terms regardless
            rules.append(f"Use '{specific}' for '{generic}'")

    return rules[:10]


def _select_examples_for_tenant(audience_id: str, intent_type: str) -> list[dict]:
    """Select writing examples — same patterns, any client."""
    from app.services.kone_knowledge_base import WRITING_PATTERN_EXAMPLES

    examples = []
    sd_key   = f"shortdesc_{audience_id.replace('_technician','_field_tech')}"
    if sd_key in WRITING_PATTERN_EXAMPLES:
        examples.append({"type": "shortdesc", **WRITING_PATTERN_EXAMPLES[sd_key]})

    step_key = f"step_{audience_id.replace('_technician','_field_tech')}"
    if step_key in WRITING_PATTERN_EXAMPLES:
        examples.append({"type": "step", **WRITING_PATTERN_EXAMPLES[step_key]})

    if intent_type in ("troubleshooting_task", "configuration_task"):
        examples.append({"type": "context", **WRITING_PATTERN_EXAMPLES["context_section"]})

    return examples


# ── Middleware: extract tenant_id from request ────────────────────────────────

def get_tenant_id_from_request(request) -> str:
    """
    Extract tenant_id from request.
    Priority: X-Tenant-ID header > subdomain > default

    In production: use JWT token which contains tenant_id.
    For now: X-Tenant-ID header or default.
    """
    # Header-based (development + API clients)
    tenant_id = request.headers.get("X-Tenant-ID", "")
    if tenant_id:
        return tenant_id.lower().strip()

    # Subdomain-based: kone.yourdomain.com → kone
    host = request.headers.get("host", "")
    if "." in host:
        subdomain = host.split(".")[0]
        if subdomain and subdomain not in ("www", "api", "app"):
            return subdomain.lower()

    return DEFAULT_TENANT


# ── Private helpers ───────────────────────────────────────────────────────────

def _load_tenant(tenant_id: str) -> Optional[TenantConfig]:
    path = TENANTS_DIR / tenant_id / "config.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return TenantConfig(**{
            k: v for k, v in data.items()
            if k in TenantConfig.__dataclass_fields__
        })
    except Exception as e:
        logger.warning_structured("Failed to load tenant", extra_fields={"error": str(e)})
        return None


def _save_tenant(cfg: TenantConfig):
    path = TENANTS_DIR / cfg.tenant_id / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "tenant_id":           cfg.tenant_id,
        "name":                cfg.name,
        "jira_url":            cfg.jira_url,
        "jira_token":          cfg.jira_token,
        "jira_email":          cfg.jira_email,
        "rag_collection":      cfg.rag_collection,
        "examples_collection": cfg.examples_collection,
        "research_collection": cfg.research_collection,
        "terminology":         cfg.terminology,
        "forbidden_terms":     cfg.forbidden_terms,
        "style_rules":         cfg.style_rules,
        "component_map":       cfg.component_map,
        "created_at":          cfg.created_at,
        "is_active":           cfg.is_active,
        "plan":                cfg.plan,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _build_kone_default() -> TenantConfig:
    """Build KONE config from existing kone_knowledge_base for backwards compat."""
    from app.services.kone_knowledge_base import (
        KONE_TERMINOLOGY, FORBIDDEN_GENERIC_TERMS,
        KONE_STYLE_RULES, COMPONENT_MAPPING,
    )
    return TenantConfig(
        tenant_id            = "kone",
        name                 = "KONE",
        rag_collection       = "aem_guides",  # existing collection name
        examples_collection  = "dita_examples",
        research_collection  = "research_cache",
        terminology          = KONE_TERMINOLOGY,
        forbidden_terms      = FORBIDDEN_GENERIC_TERMS,
        style_rules          = KONE_STYLE_RULES,
        component_map        = {
            k: {"product": v["product"], "audience": v["audience"]}
            for k, v in COMPONENT_MAPPING.items()
        },
    )
