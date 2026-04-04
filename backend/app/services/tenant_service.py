from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from app.core.auth import UserIdentity
from app.core.structured_logging import get_structured_logger
from app.storage import get_storage

logger = get_structured_logger(__name__)

DEFAULT_TENANT = "kone"


def _slug_for_tenant_lookup(tenant_id: object) -> str:
    """Normalize UI / query / header tenant tokens so aliases like 'default' always match reliably."""
    if tenant_id is None:
        base = ""
    elif isinstance(tenant_id, (bytes, bytearray)):
        base = bytes(tenant_id).decode("utf-8", errors="replace")
    else:
        base = str(tenant_id)
    s = unicodedata.normalize("NFKC", base).strip().lower()
    for ch in ("\ufeff", "\u200b", "\u200c", "\u200d"):
        s = s.replace(ch, "")
    return s


def _tenants_dir() -> Path:
    path = get_storage().base_path / "tenants"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _environment() -> str:
    return (os.getenv("ENVIRONMENT") or "development").strip().lower()


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _plaintext_tenant_secrets_allowed() -> bool:
    return _bool_env("ALLOW_PLAINTEXT_TENANT_SECRETS", _environment() in {"development", "test"})


def _secret_key_material() -> str:
    return (os.getenv("TENANT_SECRET_KEY") or os.getenv("SECRET_KEY") or "").strip()


def _build_fernet() -> Fernet | None:
    secret = _secret_key_material()
    if not secret:
        return None
    try:
        return Fernet(secret.encode("utf-8"))
    except Exception:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        return Fernet(key)


def _encrypt_secret(value: str) -> str:
    if not value:
        return ""
    fernet = _build_fernet()
    if fernet is None:
        if _plaintext_tenant_secrets_allowed():
            logger.warning_structured(
                "Persisting tenant secret in plaintext because TENANT_SECRET_KEY is not configured",
                extra_fields={"environment": _environment()},
            )
            return value
        raise ValueError("TENANT_SECRET_KEY must be configured to persist tenant Jira credentials")
    return f"enc:v1:{fernet.encrypt(value.encode('utf-8')).decode('utf-8')}"


def _decrypt_secret(value: str) -> str:
    if not value:
        return ""
    if not value.startswith("enc:v1:"):
        return value
    fernet = _build_fernet()
    if fernet is None:
        raise ValueError("TENANT_SECRET_KEY must be configured to decrypt tenant Jira credentials")
    token = value.split("enc:v1:", 1)[1]
    try:
        return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Stored tenant Jira credential could not be decrypted with the current TENANT_SECRET_KEY") from exc


def _extract_requested_tenant_id(request) -> str:
    tenant_id = request.headers.get("X-Tenant-ID", "").strip().lower()
    if tenant_id:
        return _normalize_tenant_id(tenant_id) or DEFAULT_TENANT

    host = request.headers.get("host", "")
    if "." in host:
        subdomain = host.split(".")[0].strip().lower()
        if subdomain and subdomain not in {"www", "api", "app", "localhost", "127"}:
            return _normalize_tenant_id(subdomain) or DEFAULT_TENANT
    return DEFAULT_TENANT


def _normalized_allowed_tenants(user: UserIdentity) -> list[str]:
    tenants = _normalize_tenant_id_list(getattr(user, "allowed_tenants", []))
    if user.is_admin and "*" not in tenants:
        return ["*", *tenants]
    return tenants


def _normalize_tenant_id_list(values) -> list[str]:
    if values in (None, "", []):
        return []
    if values == "*":
        return ["*"]
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    normalized = []
    for item in values:
        value = str(item).strip().lower()
        if not value:
            continue
        if value == "*":
            return ["*"]
        normalized.append(_normalize_tenant_id(value))
    return normalized


def _canonical_tenant_id_for_access(normalized: str) -> str:
    """UI and query params often use 'default'; treat as the built-in default tenant."""
    if normalized == "default":
        return DEFAULT_TENANT
    return normalized


def ensure_user_can_access_tenant(user: UserIdentity, tenant_id: str) -> str:
    normalized = _canonical_tenant_id_for_access(_normalize_tenant_id(tenant_id) or DEFAULT_TENANT)
    allowed = _normalized_allowed_tenants(user)
    if "*" in allowed:
        return normalized
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tenant access configured for this user")
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User '{user.id}' does not have access to tenant '{normalized}'",
        )
    return normalized


@dataclass
class TenantConfig:
    tenant_id: str
    name: str
    jira_url: str = ""
    jira_token: str = ""
    jira_email: str = ""
    rag_collection: str = ""
    examples_collection: str = ""
    research_collection: str = ""
    terminology: dict[str, str] = field(default_factory=dict)
    forbidden_terms: list[str] = field(default_factory=list)
    style_rules: str = ""
    component_map: dict[str, dict] = field(default_factory=dict)
    custom_audiences: dict[str, dict] = field(default_factory=dict)
    created_at: str = ""
    is_active: bool = True
    plan: str = "standard"

    def collection(self, kind: str = "rag") -> str:
        mapping = {
            "rag": self.rag_collection,
            "examples": self.examples_collection,
            "research": self.research_collection,
        }
        return mapping.get(kind, self.rag_collection)

    def to_dict(self, include_kb: bool = False) -> dict:
        payload = {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "jira_url": self.jira_url,
            "jira_email": self.jira_email,
            "token_configured": bool(self.jira_token),
            "rag_collection": self.rag_collection,
            "examples_collection": self.examples_collection,
            "research_collection": self.research_collection,
            "is_active": self.is_active,
            "plan": self.plan,
            "created_at": self.created_at,
        }
        if include_kb:
            payload.update(
                {
                    "terminology": self.terminology,
                    "forbidden_terms": self.forbidden_terms,
                    "style_rules": self.style_rules,
                    "component_map": self.component_map,
                    "custom_audiences": self.custom_audiences,
                }
            )
        return payload


def create_tenant(
    tenant_id: str,
    name: str,
    jira_url: str = "",
    jira_token: str = "",
    jira_email: str = "",
    plan: str = "standard",
) -> TenantConfig:
    normalized = _normalize_tenant_id(tenant_id)
    if not normalized:
        raise ValueError("tenant_id is required")
    if _load_tenant(normalized) is not None:
        raise ValueError(f"Tenant '{normalized}' already exists")

    config = TenantConfig(
        tenant_id=normalized,
        name=name.strip() or normalized.upper(),
        jira_url=jira_url.strip(),
        jira_token=jira_token.strip(),
        jira_email=jira_email.strip(),
        rag_collection=f"{normalized}_rag",
        examples_collection=f"{normalized}_examples",
        research_collection=f"{normalized}_research",
        created_at=datetime.utcnow().isoformat(),
        plan=plan.strip() or "standard",
    )
    _save_tenant(config)
    logger.info_structured("Tenant created", extra_fields={"tenant_id": normalized, "name": config.name})
    return config


def update_tenant(
    tenant_id: str,
    *,
    name: Optional[str] = None,
    jira_url: Optional[str] = None,
    jira_email: Optional[str] = None,
    jira_token: Optional[str] = None,
    plan: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> TenantConfig:
    config = get_tenant(tenant_id)
    if name is not None:
        config.name = name.strip() or config.name
    if jira_url is not None:
        config.jira_url = jira_url.strip()
    if jira_email is not None:
        config.jira_email = jira_email.strip()
    if jira_token is not None:
        config.jira_token = jira_token.strip()
    if plan is not None:
        config.plan = plan.strip() or config.plan
    if is_active is not None:
        config.is_active = bool(is_active)
    _save_tenant(config)
    return config


def get_tenant(tenant_id: str) -> TenantConfig:
    # Settings UI and several AI routes pass tenant_id "default" or omit it; always map to the built-in seed tenant.
    # Use a single slug for both the alias check and _normalize_tenant_id (must not pass raw tenant_id twice with
    # different coercion rules — that could skip the alias and still yield normalized "default", raising not found).
    slug = _slug_for_tenant_lookup(tenant_id)
    if slug in ("", "default"):
        config = _load_tenant(DEFAULT_TENANT)
        if config is not None:
            return config
        return _build_default_tenant()

    normalized = _normalize_tenant_id(slug) or DEFAULT_TENANT
    config = _load_tenant(normalized)
    if config is not None:
        return config
    if normalized == DEFAULT_TENANT:
        return _build_default_tenant()
    # On-disk tenant id "default" is not supported; treat like the UI alias.
    if normalized == "default":
        config = _load_tenant(DEFAULT_TENANT)
        if config is not None:
            return config
        return _build_default_tenant()
    raise ValueError(f"Tenant '{normalized}' not found")


def list_tenants() -> list[dict]:
    tenants: list[dict] = []
    for path in _tenants_dir().glob("*/config.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            tenants.append(
                {
                    "tenant_id": payload.get("tenant_id"),
                    "name": payload.get("name"),
                    "is_active": payload.get("is_active", True),
                    "plan": payload.get("plan", "standard"),
                }
            )
        except Exception:
            continue
    if not any(item.get("tenant_id") == DEFAULT_TENANT for item in tenants):
        tenants.insert(0, _build_default_tenant().to_dict())
    tenants.sort(key=lambda item: (item.get("tenant_id") != DEFAULT_TENANT, item.get("name") or ""))
    return tenants


def update_tenant_kb(
    tenant_id: str,
    *,
    terminology: Optional[dict] = None,
    style_rules: Optional[str] = None,
    component_map: Optional[dict] = None,
    forbidden_terms: Optional[list[str]] = None,
    custom_audiences: Optional[dict] = None,
) -> TenantConfig:
    config = get_tenant(tenant_id)
    if terminology is not None:
        config.terminology = {str(key): str(value) for key, value in terminology.items()}
    if style_rules is not None:
        config.style_rules = style_rules.strip()
    if component_map is not None:
        config.component_map = {
            str(key): value if isinstance(value, dict) else {"audience": str(value), "product": config.name}
            for key, value in component_map.items()
        }
    if forbidden_terms is not None:
        config.forbidden_terms = [str(item).strip() for item in forbidden_terms if str(item).strip()]
    if custom_audiences is not None:
        config.custom_audiences = custom_audiences
    _save_tenant(config)
    return config


def get_tenant_id_from_request(request) -> str:
    return _extract_requested_tenant_id(request)


def get_authorized_tenant_id(request, user: UserIdentity) -> str:
    requested = _extract_requested_tenant_id(request)
    allowed = _normalized_allowed_tenants(user)
    if requested == DEFAULT_TENANT and allowed and "*" not in allowed and DEFAULT_TENANT not in allowed and len(allowed) == 1:
        requested = allowed[0]
    return ensure_user_can_access_tenant(user, requested)


def build_jira_client(tenant_id: str):
    from app.services.jira_client import JiraClient

    try:
        config = get_tenant(tenant_id)
    except Exception:
        return JiraClient()
    return JiraClient(
        base_url=config.jira_url or None,
        email=config.jira_email or None,
        api_token=config.jira_token or None,
    )


def build_tenant_context(tenant_id: str, issue: dict, intent_type: str) -> dict:
    from app.services.kone_knowledge_base import (
        AUDIENCE_PROFILES,
        COMPONENT_MAPPING,
        FORBIDDEN_GENERIC_TERMS,
        KONE_STYLE_RULES,
        WRITING_PATTERN_EXAMPLES,
        _detect_audience,
    )

    config = get_tenant(tenant_id)
    audience_id = _detect_audience_for_tenant(issue, config) or _detect_audience(issue)
    audience = AUDIENCE_PROFILES.get(audience_id, AUDIENCE_PROFILES["aem_author"])
    component_map = config.component_map or {
        key: {"product": value["product"], "audience": value["audience"]}
        for key, value in COMPONENT_MAPPING.items()
    }

    return {
        "tenant_id": config.tenant_id,
        "tenant_name": config.name,
        "product_context": _detect_product_for_tenant(issue, config),
        "audience_id": audience_id,
        "audience": audience,
        "terminology_rules": _build_terminology_rules_for_tenant(issue, config),
        "style_rules": config.style_rules or KONE_STYLE_RULES,
        "writing_examples": _select_examples_for_tenant(audience_id, intent_type, WRITING_PATTERN_EXAMPLES),
        "forbidden_terms": config.forbidden_terms or FORBIDDEN_GENERIC_TERMS,
        "component_map": component_map,
        "rag_collection": config.rag_collection,
        "examples_collection": config.examples_collection,
    }


def retrieve_tenant_context(query: str, tenant_id: str, k: int = 4) -> list[dict]:
    from app.services.embedding_service import embed_query, is_embedding_available
    from app.services.vector_store_service import is_chroma_available, query_collection

    config = get_tenant(tenant_id)
    if not is_chroma_available() or not is_embedding_available():
        return []
    embedding = embed_query(query)
    if embedding is None:
        return []
    rows = query_collection(
        config.rag_collection,
        query_embedding=embedding.tolist() if hasattr(embedding, "tolist") else list(embedding),
        k=k,
    )
    return [
        {
            "content": row.get("document") or "",
            "metadata": row.get("metadata") or {},
            "distance": row.get("distance", 0.0),
        }
        for row in rows
        if row.get("document")
    ]


def retrieve_tenant_examples(query: str, tenant_id: str, k: int = 2) -> list[dict]:
    from app.services.embedding_service import embed_query, is_embedding_available
    from app.services.vector_store_service import is_chroma_available, query_collection

    config = get_tenant(tenant_id)
    if not is_chroma_available() or not is_embedding_available():
        return []
    embedding = embed_query(query)
    if embedding is None:
        return []
    rows = query_collection(
        config.examples_collection,
        query_embedding=embedding.tolist() if hasattr(embedding, "tolist") else list(embedding),
        k=k,
    )
    examples: list[dict] = []
    for row in rows:
        metadata = row.get("metadata") or {}
        document = row.get("document") or ""
        if not document:
            continue
        examples.append(
            {
                "filename": metadata.get("filename") or row.get("id") or "example.dita",
                "content": document,
                "quality_score": metadata.get("quality_score", ""),
                "source": metadata.get("source", "tenant_examples"),
            }
        )
    return examples


def _normalize_tenant_id(value: str) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""
    if not re.match(r"^[a-z0-9_]+$", value):
        raise ValueError("tenant_id must be lowercase alphanumeric with underscores")
    return value


def _load_tenant(tenant_id: str) -> Optional[TenantConfig]:
    path = _tenants_dir() / tenant_id / "config.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        allowed = {field_name for field_name in TenantConfig.__dataclass_fields__}
        normalized_payload = {key: value for key, value in payload.items() if key in allowed}
        encrypted_token = payload.get("jira_token_encrypted")
        if encrypted_token:
            try:
                normalized_payload["jira_token"] = _decrypt_secret(str(encrypted_token))
            except Exception as exc:
                logger.error_structured(
                    "Failed to decrypt tenant Jira token",
                    extra_fields={"tenant_id": tenant_id, "error": str(exc)},
                )
                normalized_payload["jira_token"] = ""
        return TenantConfig(**normalized_payload)
    except Exception as exc:
        logger.warning_structured("Failed to load tenant", extra_fields={"tenant_id": tenant_id, "error": str(exc)})
        return None


def _save_tenant(config: TenantConfig) -> None:
    path = _tenants_dir() / config.tenant_id / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted_token = _encrypt_secret(config.jira_token) if config.jira_token else ""
    payload = {
        "tenant_id": config.tenant_id,
        "name": config.name,
        "jira_url": config.jira_url,
        "jira_email": config.jira_email,
        "rag_collection": config.rag_collection,
        "examples_collection": config.examples_collection,
        "research_collection": config.research_collection,
        "terminology": config.terminology,
        "forbidden_terms": config.forbidden_terms,
        "style_rules": config.style_rules,
        "component_map": config.component_map,
        "custom_audiences": config.custom_audiences,
        "created_at": config.created_at,
        "is_active": config.is_active,
        "plan": config.plan,
    }
    if encrypted_token:
        if encrypted_token.startswith("enc:v1:"):
            payload["jira_token_encrypted"] = encrypted_token
        else:
            payload["jira_token"] = encrypted_token
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_default_tenant() -> TenantConfig:
    from app.services.kone_knowledge_base import (
        COMPONENT_MAPPING,
        FORBIDDEN_GENERIC_TERMS,
        KONE_STYLE_RULES,
        KONE_TERMINOLOGY,
    )

    return TenantConfig(
        tenant_id=DEFAULT_TENANT,
        name="KONE",
        rag_collection=f"{DEFAULT_TENANT}_rag",
        examples_collection=f"{DEFAULT_TENANT}_examples",
        research_collection=f"{DEFAULT_TENANT}_research",
        terminology=KONE_TERMINOLOGY,
        forbidden_terms=FORBIDDEN_GENERIC_TERMS,
        style_rules=KONE_STYLE_RULES,
        component_map={
            key: {"product": value["product"], "audience": value["audience"]}
            for key, value in COMPONENT_MAPPING.items()
        },
    )


def _detect_audience_for_tenant(issue: dict, config: TenantConfig) -> str:
    components = issue.get("components") or []
    for component in components:
        mapping = config.component_map.get(component)
        if isinstance(mapping, dict) and mapping.get("audience"):
            return str(mapping["audience"])
    return ""


def _detect_product_for_tenant(issue: dict, config: TenantConfig) -> str:
    components = issue.get("components") or []
    for component in components:
        mapping = config.component_map.get(component)
        if isinstance(mapping, dict) and mapping.get("product"):
            return str(mapping["product"])
    return config.name


def _build_terminology_rules_for_tenant(issue: dict, config: TenantConfig) -> list[str]:
    rules: list[str] = []
    summary = (issue.get("summary") or "").lower()
    for generic, specific in config.terminology.items():
        generic_lower = generic.lower()
        if generic_lower in summary:
            rules.append(f"Use '{specific}' instead of '{generic}'.")
        elif len(rules) < 6:
            rules.append(f"Prefer '{specific}' when referring to '{generic}'.")
    return rules[:10]


def _select_examples_for_tenant(audience_id: str, intent_type: str, examples: dict) -> list[dict]:
    selected: list[dict] = []
    suffix = audience_id.replace("_technician", "_field_tech")
    shortdesc_key = f"shortdesc_{suffix}"
    step_key = f"step_{suffix}"
    if shortdesc_key in examples:
        selected.append({"type": "shortdesc", **examples[shortdesc_key]})
    if step_key in examples:
        selected.append({"type": "step", **examples[step_key]})
    if intent_type in {"troubleshooting_task", "configuration_task"} and "context_section" in examples:
        selected.append({"type": "context", **examples["context_section"]})
    return selected
