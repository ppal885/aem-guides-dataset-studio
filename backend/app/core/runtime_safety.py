"""Runtime safety helpers for enterprise-friendly startup validation."""
from __future__ import annotations

import os

from app.core.auth import has_configured_auth_tokens, is_development_auth_mode


def _raw_dev_bypass_requested() -> bool:
    return (os.getenv("ALLOW_DEV_AUTH_BYPASS") or "").strip().lower() in {"1", "true", "yes", "on"}


def environment_name() -> str:
    return (os.getenv("ENVIRONMENT") or "development").strip().lower()


def is_production_environment() -> bool:
    return environment_name() == "production"


def cors_allowed_origins() -> list[str]:
    raw = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    if environment_name() in {"development", "test"}:
        return ["*"]
    return []


def validate_runtime_safety() -> dict[str, object]:
    """Return warnings and fatal errors for startup/runtime policy."""
    env = environment_name()
    origins = cors_allowed_origins()
    warnings: list[str] = []
    errors: list[str] = []

    if is_development_auth_mode():
        warnings.append("Development auth bypass is enabled.")

    if env == "production":
        if _raw_dev_bypass_requested():
            errors.append("ALLOW_DEV_AUTH_BYPASS must be disabled in production.")
        if not origins:
            errors.append("CORS_ALLOWED_ORIGINS must be configured in production.")
        if "*" in origins:
            errors.append("Wildcard CORS is not allowed in production.")
        if not has_configured_auth_tokens(include_test_token=False):
            errors.append("At least one bearer token must be configured in production.")

    return {
        "environment": env,
        "cors_allowed_origins": origins,
        "dev_auth_bypass_enabled": is_development_auth_mode(),
        "dev_auth_bypass_requested": _raw_dev_bypass_requested(),
        "warnings": warnings,
        "errors": errors,
    }
