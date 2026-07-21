"""Load AEM upload credentials from config/aem-upload.properties."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict

DEFAULT_CONFIG_RELATIVE = Path("config") / "aem-upload.properties"

PROPERTY_KEYS = {
    "aem.base.url": "base_url",
    "aem.base_url": "base_url",
    "aem.url": "base_url",
    "aem.username": "username",
    "aem.password": "password",
    "aem.access.token": "access_token",
    "aem.access_token": "access_token",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_config_path() -> Path:
    override = (os.getenv("AEM_UPLOAD_CONFIG") or "").strip()
    if override:
        return Path(override).expanduser()
    return _project_root() / DEFAULT_CONFIG_RELATIVE


def _parse_properties(text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        mapped = PROPERTY_KEYS.get(key)
        if mapped and value:
            values[mapped] = value
    return values


@lru_cache(maxsize=1)
def load_aem_upload_config() -> Dict[str, str]:
    path = get_config_path()
    if not path.is_file():
        return {}
    try:
        return _parse_properties(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def resolve_aem_upload_credentials(
    *,
    aem_base_url: str = "",
    username: str = "",
    password: str = "",
    access_token: str = "",
) -> Dict[str, str]:
    """Resolve credentials: tool args > properties file > environment variables."""
    cfg = load_aem_upload_config()
    base_url = (
        (aem_base_url or "").strip()
        or cfg.get("base_url", "")
        or (os.getenv("AEM_BASE_URL") or os.getenv("AEM_AUTHOR_URL") or "").strip()
    )
    user = (username or "").strip() or cfg.get("username", "") or (os.getenv("AEM_USERNAME") or "")
    pwd = (password or "").strip() or cfg.get("password", "") or (os.getenv("AEM_PASSWORD") or "")
    token = (
        (access_token or "").strip()
        or cfg.get("access_token", "")
        or (os.getenv("AEM_ACCESS_TOKEN") or "")
    )
    return {
        "base_url": base_url,
        "username": user,
        "password": pwd,
        "access_token": token,
    }
