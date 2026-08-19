"""Configuration loading + credential policy.

Credentials come ONLY from env vars named by the config (default AEM_USERNAME /
AEM_PASSWORD). They are never read from, or written to, config/code/logs.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    base_url: str = ""
    deployment_model: str = "cloud"
    username_env: str = "AEM_USERNAME"
    password_env: str = "AEM_PASSWORD"
    storage_state: str = "ui_evidence/auth/storage_state.json"
    browser_type: str = "chromium"
    headed: bool = True
    viewport_width: int = 1536
    viewport_height: int = 960
    mode: str = "smoke"
    max_states: int = 30
    max_depth: int = 4
    max_actions_per_state: int = 12
    max_dialog_states: int = 40
    navigation_timeout_ms: int = 20000
    overall_timeout_s: int = 1800
    mutation_mode: bool = False
    fixtures: dict = field(default_factory=dict)
    safe_action_patterns: list = field(default_factory=list)
    blocked_action_patterns: list = field(default_factory=list)
    safe_selectors: list = field(default_factory=list)
    blocked_selectors: list = field(default_factory=list)
    output_dir: str = "ui_evidence"
    seed_surfaces: list = field(default_factory=list)

    # --- credential access (values never persisted) ---
    def username(self):
        return os.environ.get(self.username_env, "")

    def password(self):
        return os.environ.get(self.password_env, "")

    def has_credentials(self):
        return bool(self.username() and self.password())


def load_config(path):
    """Load config/ui_crawler.yaml into a Config. Requires PyYAML."""
    import yaml  # local import so unit tests that build Config directly need no yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    env = data.get("environment", {}) or {}
    auth = data.get("authentication", {}) or {}
    browser = data.get("browser", {}) or {}
    viewport = browser.get("viewport", {}) or {}
    crawler = data.get("crawler", {}) or {}
    policy = data.get("action_policy", {}) or {}
    out = data.get("output", {}) or {}
    return Config(
        base_url=env.get("base_url", ""),
        deployment_model=env.get("deployment_model", "cloud"),
        username_env=auth.get("username_env", "AEM_USERNAME"),
        password_env=auth.get("password_env", "AEM_PASSWORD"),
        storage_state=auth.get("storage_state", "ui_evidence/auth/storage_state.json"),
        browser_type=browser.get("type", "chromium"),
        headed=bool(browser.get("headed", True)),
        viewport_width=int(viewport.get("width", 1536)),
        viewport_height=int(viewport.get("height", 960)),
        mode=crawler.get("mode", "smoke"),
        max_states=int(crawler.get("max_states", 30)),
        max_depth=int(crawler.get("max_depth", 4)),
        max_actions_per_state=int(crawler.get("max_actions_per_state", 12)),
        max_dialog_states=int(crawler.get("max_dialog_states", 40)),
        navigation_timeout_ms=int(crawler.get("navigation_timeout_ms", 20000)),
        overall_timeout_s=int(crawler.get("overall_timeout_s", 1800)),
        mutation_mode=bool(crawler.get("mutation_mode", False)),
        fixtures=data.get("fixtures", {}) or {},
        safe_action_patterns=policy.get("safe_action_patterns", []) or [],
        blocked_action_patterns=policy.get("blocked_action_patterns", []) or [],
        safe_selectors=policy.get("safe_selectors", []) or [],
        blocked_selectors=policy.get("blocked_selectors", []) or [],
        output_dir=out.get("directory", "ui_evidence"),
        seed_surfaces=data.get("seed_surfaces", []) or [],
    )
