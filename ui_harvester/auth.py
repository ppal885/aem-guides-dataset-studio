"""Authentication: interactive-headed login + storage_state reuse.

Credential policy (hard rules):
- Username/password come ONLY from the env vars named in config (AEM_USERNAME /
  AEM_PASSWORD). They are used to pre-fill a login form ONLY if the SSO provider
  exposes plain username/password fields; SSO/MFA/OTP are NEVER bypassed.
- The authenticated session is persisted to config.storage_state as a Playwright
  storage_state.json. That file is git-ignored and must never be committed.
- If auth is missing/expired, callers get AUTHENTICATION_REQUIRED and STOP.

Preferred order: existing storage_state -> interactive headed login -> env-var
credential prefill (only if the provider supports it).
"""

from pathlib import Path
from urllib.parse import urlsplit

AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"

# Hosts/paths that indicate we are still on the Adobe IMS sign-in flow (NOT the
# authenticated app). Deliberately specific - we must not match the AEM "author"
# host, whose name contains the substring "auth".
_LOGIN_MARKERS = ("adobelogin.com", "ims-na", "auth.services.adobe", "/ims/", "signin", "/login")


def storage_state_exists(config):
    p = Path(config.storage_state)
    return p.is_file() and p.stat().st_size > 0


def ensure_auth_dir(config):
    Path(config.storage_state).parent.mkdir(parents=True, exist_ok=True)


def interactive_login(config, *, timeout_ms=300000):
    """Open a HEADED browser at the AEM author URL and wait for the human to
    complete SSO/MFA, then save storage_state. Intended to be run LOCALLY by the
    user - it blocks on human interaction and never scripts MFA.

    Returns the storage_state path on success. Raises RuntimeError if Playwright
    is unavailable. This function is deliberately not invoked automatically by the
    crawler; the CLI `auth` subcommand runs it.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("playwright is required for interactive_login") from exc

    ensure_auth_dir(config)
    with sync_playwright() as p:
        browser = getattr(p, config.browser_type).launch(headless=False)
        context = browser.new_context(
            viewport={"width": config.viewport_width, "height": config.viewport_height}
        )
        page = context.new_page()
        page.goto(config.base_url, wait_until="domcontentloaded", timeout=config.navigation_timeout_ms)

        # Best-effort, provider-permitting prefill of a plain username field. We do
        # NOT submit, click MFA, or handle OTP - the human drives SSO to completion.
        _maybe_prefill_username(page, config)

        print("\n[ui_harvester] Complete the Adobe SSO / MFA sign-in in the opened "
              "browser window. The session will be saved automatically once you "
              "reach the authenticated AEM author UI.\n")
        # Wait until we are clearly inside the authenticated app: the URL is on the
        # configured AEM author host and carries no IMS/login markers. We match the
        # host explicitly (never the bare substring "auth", which the author host
        # itself contains).
        target_host = urlsplit(config.base_url).netloc.lower()

        def _is_authenticated(url):
            u = (url or "").lower()
            return target_host in u and not any(m in u for m in _LOGIN_MARKERS)

        page.wait_for_url(_is_authenticated, timeout=timeout_ms)
        context.storage_state(path=config.storage_state)
        browser.close()
    return config.storage_state


def _maybe_prefill_username(page, config):
    user = config.username()
    if not user:
        return
    for sel in ("input[type=email]", "input[name=username]", "#EmailPage-EmailField"):
        try:
            if page.locator(sel).count() > 0:
                page.fill(sel, user, timeout=3000)
                break
        except Exception:  # noqa: BLE001 - prefill is best-effort only
            continue
