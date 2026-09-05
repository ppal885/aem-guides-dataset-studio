"""Authentication and authorization modules."""
import json
import os
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)


class JiraReviewIdentity(BaseModel):
    """Operator-provisioned Jira identity, never accepted from review requests."""

    model_config = ConfigDict(extra="forbid", strict=True)
    server_url: str = Field(min_length=1, max_length=500)
    user_key: str = Field(default="", max_length=255)
    account_id: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def one_stable_identity(self):
        if bool(self.user_key) == bool(self.account_id):
            raise ValueError("Configure exactly one Jira user key or account ID.")
        for value in (self.server_url, self.user_key, self.account_id):
            if value != value.strip() or any(ord(char) < 32 for char in value):
                raise ValueError("Jira identity values must be clean bounded strings.")
        return self


class UserIdentity(BaseModel):
    """User identity model."""
    id: str
    email: Optional[str] = None
    name: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    allowed_tenants: list[str] = Field(default_factory=list)
    auth_method: str = "unknown"
    # Explicit operator configuration, never a client-supplied approval claim.
    principal_type: Literal["human", "service", "shared", "unknown"] = "unknown"
    jira_identity: JiraReviewIdentity | None = None

    @property
    def is_admin(self) -> bool:
        return "admin" in {role.lower() for role in self.roles}


def _environment() -> str:
    return (os.getenv("ENVIRONMENT") or "development").strip().lower()


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_development_auth_mode() -> bool:
    return _environment() in {"development", "test"} and _bool_env("ALLOW_DEV_AUTH_BYPASS", True)


def _normalize_roles(value) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalize_allowed_tenants(value) -> list[str]:
    if value in (None, "", []):
        return []
    if value == "*":
        return ["*"]
    if isinstance(value, str):
        return [item.strip().lower() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        tenants = [str(item).strip().lower() for item in value if str(item).strip()]
        return ["*"] if "*" in tenants else tenants
    return []


def _build_identity(payload: dict, *, auth_method: str) -> UserIdentity:
    roles = _normalize_roles(payload.get("roles"))
    allowed_tenants = _normalize_allowed_tenants(payload.get("allowed_tenants"))
    if "admin" in {role.lower() for role in roles} and "*" not in allowed_tenants:
        allowed_tenants = ["*", *allowed_tenants]
    principal_type = payload.get("principal_type", "unknown")
    if principal_type not in {"human", "service", "shared", "unknown"}:
        principal_type = "unknown"
    try:
        jira_identity = JiraReviewIdentity.model_validate(payload["jira_identity"]) if payload.get("jira_identity") else None
    except (ValidationError, TypeError, ValueError):
        # A bad optional mapping denies ticket review, without breaking legacy
        # capture/generation authentication or exposing configured credentials.
        jira_identity = None
    return UserIdentity(
        id=str(payload.get("id") or payload.get("user_id") or "unknown-user"),
        email=str(payload.get("email") or "") or None,
        name=str(payload.get("name") or payload.get("display_name") or "") or None,
        roles=roles,
        allowed_tenants=allowed_tenants,
        auth_method=auth_method,
        principal_type=principal_type,
        jira_identity=jira_identity,
    )


def _default_dev_user() -> UserIdentity:
    return UserIdentity(
        id=os.getenv("DEV_AUTH_USER_ID", "dev-user"),
        email=os.getenv("DEV_AUTH_USER_EMAIL", "dev@example.com"),
        name=os.getenv("DEV_AUTH_USER_NAME", "Development User"),
        roles=["admin"],
        allowed_tenants=["*"],
        auth_method="dev_bypass",
        principal_type="shared",
    )


def _load_token_config_map() -> dict[str, UserIdentity]:
    token_map: dict[str, UserIdentity] = {}

    raw_json = (os.getenv("AUTH_TOKENS_JSON") or "").strip()
    if raw_json:
        try:
            payload = json.loads(raw_json)
            if isinstance(payload, dict):
                for token, value in payload.items():
                    if isinstance(value, dict) and str(token).strip():
                        token_map[str(token).strip()] = _build_identity(value, auth_method="token")
            elif isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    token = str(item.get("token") or "").strip()
                    if token:
                        token_map[token] = _build_identity(item, auth_method="token")
        except json.JSONDecodeError:
            payload = None

    admin_token = (os.getenv("ADMIN_BEARER_TOKEN") or "").strip()
    if admin_token:
        token_map[admin_token] = _build_identity(
            {
                "id": os.getenv("ADMIN_BEARER_USER_ID", "admin"),
                "email": os.getenv("ADMIN_BEARER_USER_EMAIL", ""),
                "name": os.getenv("ADMIN_BEARER_USER_NAME", "Admin"),
                "principal_type": "shared",
                "roles": ["admin"],
                "allowed_tenants": ["*"],
            },
            auth_method="token",
        )

    api_token = (os.getenv("API_BEARER_TOKEN") or "").strip()
    if api_token:
        token_map[api_token] = _build_identity(
            {
                "id": os.getenv("API_BEARER_USER_ID", "service-user"),
                "email": os.getenv("API_BEARER_USER_EMAIL", ""),
                "name": os.getenv("API_BEARER_USER_NAME", "Service User"),
                "principal_type": "service",
                "roles": _normalize_roles(os.getenv("API_BEARER_ROLES", "writer")),
                "allowed_tenants": _normalize_allowed_tenants(os.getenv("API_ALLOWED_TENANTS", "*")),
            },
            auth_method="token",
        )

    if _environment() in {"development", "test"}:
        token_map.setdefault(
            "test-token",
            UserIdentity(
                id="test-user-1",
                email="test@example.com",
                name="Test User",
                roles=["admin"],
                allowed_tenants=["*"],
                auth_method="test_token",
            ),
        )
    return token_map


def has_configured_auth_tokens(*, include_test_token: bool = False) -> bool:
    """Return True when at least one non-dev bearer token is configured."""
    token_map = _load_token_config_map()
    if include_test_token:
        return bool(token_map)
    return any(
        token
        for token, identity in token_map.items()
        if identity.auth_method not in {"test_token"}
    )


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserIdentity:
    """
    Get current user from token.
    """
    token_map = _load_token_config_map()
    if credentials and credentials.credentials:
        token = credentials.credentials
        if token in token_map:
            user = token_map[token]
            request.state.user = user
            return user

    if is_development_auth_mode():
        user = _default_dev_user()
        request.state.user = user
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin_user(user: UserIdentity = Depends(get_current_user)) -> UserIdentity:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# Dependency alias for easier use
CurrentUser = Depends(get_current_user)
AdminUser = Depends(require_admin_user)
