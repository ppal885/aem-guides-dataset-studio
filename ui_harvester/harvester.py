"""The Playwright state-crawler orchestration.

Read-only / non-destructive. It reuses the deterministic, unit-tested modules
(state, dom_extract, actions, transitions, rag_records) for all identity and
classification logic, so the browser code stays thin.

Modes:
- DRY_RUN : snapshot the seed state, discover + classify candidate actions
            (SAFE/BLOCKED/UNKNOWN), NO clicks, NO state changes.
- SMOKE   : bounded crawl (~max_states, depth) clicking only SAFE actions.
- CORE / EXPANDED : deeper safe crawl (same engine, larger bounds) - NOT run
            automatically; a human enables them after review.

The crawler NEVER runs mutation flows (create/save/upload/publish/delete...).
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import actions as action_mod
from . import dom_extract, rag_records, screenshot as shot_mod, transitions as trans_mod
from .auth import AUTHENTICATION_REQUIRED, storage_state_exists
from .state import UIState, finalize_state, normalize_url


def _now():
    return datetime.now(timezone.utc).isoformat()


class HarvestResult:
    def __init__(self):
        self.states = {}          # state_id -> UIState
        self.transitions = []     # list[UITransition]
        self.capabilities = {}    # capability -> {surface, states:set}
        self.blocked_actions = [] # dicts
        self.unknown_actions = [] # dicts
        self.safe_executed = 0
        self.duplicates_skipped = 0
        self.vision_candidates = []
        self.failures = []
        self.auth_status = "OK"
        self.product_version = "UNKNOWN"

    def summary(self):
        return {
            "unique_states": len(self.states),
            "transitions": len(self.transitions),
            "capabilities": len(self.capabilities),
            "safe_executed": self.safe_executed,
            "blocked": len(self.blocked_actions),
            "unknown": len(self.unknown_actions),
            "duplicates_skipped": self.duplicates_skipped,
            "vision_required": len(self.vision_candidates),
            "failures": len(self.failures),
            "auth_status": self.auth_status,
            "product_version": self.product_version,
        }


class Harvester:
    def __init__(self, config):
        self.config = config
        self.result = HarvestResult()

    # ---- public API --------------------------------------------------------
    def run(self, mode=None):
        mode = (mode or self.config.mode or "smoke").lower()
        if not storage_state_exists(self.config):
            self.result.auth_status = AUTHENTICATION_REQUIRED
            return self.result
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.result.auth_status = "PLAYWRIGHT_UNAVAILABLE"
            self.result.failures.append({"stage": "startup", "error": "playwright not installed"})
            return self.result

        deadline = time.time() + self.config.overall_timeout_s
        with sync_playwright() as p:
            browser = getattr(p, self.config.browser_type).launch(headless=not self.config.headed)
            context = browser.new_context(
                storage_state=self.config.storage_state,
                viewport={"width": self.config.viewport_width, "height": self.config.viewport_height},
            )
            page = context.new_page()
            page.set_default_timeout(self.config.navigation_timeout_ms)
            try:
                page.goto(self.config.base_url, wait_until="domcontentloaded")
                self.result.product_version = self._detect_version(page)
                shots = shot_mod.ScreenshotStore(self.config.output_dir)
                if mode == "dry_run":
                    self._dry_run(page, shots)
                else:
                    self._crawl(page, shots, mode, deadline)
            except Exception as exc:  # noqa: BLE001 - record, never crash the run
                self.result.failures.append({"stage": "run", "error": str(exc)})
            finally:
                browser.close()
        return self.result

    # ---- DRY_RUN -----------------------------------------------------------
    def _dry_run(self, page, shots):
        state = self._snapshot_state(page, shots, capture=True)
        self.result.states[state.state_id] = state
        for cand in self._candidate_actions(page):
            verdict = self._classify(cand)
            self._record_candidate(cand, verdict)

    # ---- crawl -------------------------------------------------------------
    def _seed_urls(self):
        """Entry points that take the crawler INTO Guides. The AEM author root
        alone lands on the Start page, so we seed the configured Guides surfaces
        (e.g. the Assets UI) and any fixture-provided editor deep link."""
        base = self.config.base_url.rstrip("/")
        urls = []
        for s in (self.config.seed_surfaces or []):
            s = str(s).strip()
            if s:
                urls.append(s if s.startswith("http") else base + "/" + s.lstrip("/"))
        fx = self.config.fixtures or {}
        # A full editor URL is the most reliable way into the New Editor surfaces.
        editor_url = str(fx.get("editor_url", "") or "").strip()
        if editor_url:
            urls.append(editor_url)
        template = str(fx.get("editor_url_template", "") or "").strip()
        for key in ("root_map_with_keys", "dita_map", "topic_with_keys", "dita_topic"):
            path = str(fx.get(key, "") or "").strip()
            if path and template:
                urls.append(template.format(path=path))
        if not urls:
            urls = [self.config.base_url]  # fallback only when nothing is configured
        seen, out = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    def _crawl(self, page, shots, mode, deadline):
        queue = []
        for seed_url in self._seed_urls():
            try:
                page.goto(seed_url, wait_until="domcontentloaded")
            except Exception as exc:  # noqa: BLE001 - a bad seed must not abort the crawl
                self.result.failures.append({"stage": "seed", "url": seed_url, "error": str(exc)})
                continue
            # The Guides editor is a heavy SPA that may never reach networkidle;
            # a timeout here must NOT skip the seed - proceed with what has loaded.
            try:
                page.wait_for_load_state("networkidle", timeout=self.config.navigation_timeout_ms)
            except Exception:  # noqa: BLE001
                pass
            st = self._snapshot_state(page, shots, capture=True)
            if st.state_id not in self.result.states:
                self.result.states[st.state_id] = st
                queue.append((st, 0))
        if not queue:
            self.result.failures.append({"stage": "seed", "error": "no seed state captured - check seed_surfaces/base_url"})
        explored_edges = set()  # (state_id, capability) to avoid endless retries
        while queue and len(self.result.states) < self.config.max_states:
            if time.time() > deadline:
                self.result.failures.append({"stage": "crawl", "error": "overall_timeout"})
                break
            state, depth = queue.pop(0)
            if depth >= self.config.max_depth:
                continue
            self._restore_state(page, state)
            candidates = self._candidate_actions(page)[: self.config.max_actions_per_state]
            for cand in candidates:
                verdict = self._classify(cand)
                self._record_candidate(cand, verdict)
                edge = (state.state_id, cand.get("capability", ""))
                if verdict != action_mod.SAFE or edge in explored_edges:
                    continue
                explored_edges.add(edge)
                new_state = self._try_action(page, state, cand, shots)
                if new_state is None:
                    continue
                if new_state.state_id in self.result.states:
                    self.result.duplicates_skipped += 1
                else:
                    self.result.states[new_state.state_id] = new_state
                    queue.append((new_state, depth + 1))
                self._restore_state(page, state)  # backtrack for the next candidate

    # ---- one safe action ---------------------------------------------------
    def _try_action(self, page, from_state, cand, shots):
        try:
            before = shots  # screenshots captured inside snapshot
            locator = page.locator(cand["selector"]).first
            locator.click(timeout=self.config.navigation_timeout_ms)
            page.wait_for_load_state("domcontentloaded")
            to_state = self._snapshot_state(page, shots, capture=True)
            if to_state.state_id == from_state.state_id:
                return None  # no observable transition
            action = {
                "type": "click", "capability": cand.get("capability", ""),
                "control_pattern": cand.get("control_pattern", ""), "target": cand.get("name", ""),
            }
            t = trans_mod.make_transition(
                from_state, to_state, action,
                relation=self._infer_relation(cand, to_state),
                observed_effects=self._diff_effects(from_state, to_state),
                surface=to_state.surface, product_version=self.result.product_version,
                before_screenshot=from_state.screenshot_id, after_screenshot=to_state.screenshot_id,
                captured_at=_now(),
            )
            self.result.transitions.append(t)
            self.result.safe_executed += 1
            return to_state
        except Exception as exc:  # noqa: BLE001
            self.result.failures.append({"stage": "action", "capability": cand.get("capability"), "error": str(exc)})
            return None

    # ---- state snapshot ----------------------------------------------------
    def _snapshot_state(self, page, shots, capture=False):
        nodes = self._accessibility_nodes(page)
        visible, disabled = dom_extract.extract_capabilities(nodes)
        state = UIState(
            product="AEM_GUIDES",
            surface=self._infer_surface(page),
            region="UNKNOWN",
            open_dialog=self._first_role_name(nodes, "dialog"),
            open_menu=self._first_role_name(nodes, "menu"),
            active_tab=self._first_selected_tab(nodes),
            visible_capabilities=visible,
            disabled_capabilities=disabled,
            url=page.url,
            url_normalized=normalize_url(page.url),
            captured_at=_now(),
            product_version=self.result.product_version,
            currentness="CURRENT_UI_REFERENCE",
        )
        finalize_state(state)
        for cap in visible:
            self.result.capabilities.setdefault(cap, {"surface": state.surface, "states": set()})["states"].add(state.state_id)
        if capture:
            try:
                png = page.screenshot(full_page=False)
                sid, _new = shots.store(png, state.state_id)
                state.screenshot_id = sid
            except Exception as exc:  # noqa: BLE001
                self.result.failures.append({"stage": "screenshot", "error": str(exc)})
        return state

    # ---- browser helpers (thin) -------------------------------------------
    def _accessibility_nodes(self, page):
        try:
            snap = page.accessibility.snapshot(interesting_only=True) or {}
        except Exception:  # noqa: BLE001
            return []
        flat = []

        def walk(n):
            if not isinstance(n, dict):
                return
            flat.append({
                "role": n.get("role", ""), "name": n.get("name", ""),
                "disabled": n.get("disabled", False), "expanded": n.get("expanded"),
                "selected": n.get("selected"), "checked": n.get("checked"),
                "attributes": {},
            })
            for c in n.get("children", []) or []:
                walk(c)

        walk(snap)
        return flat

    def _candidate_actions(self, page):
        """Interactive candidates with a stable selector. Kept small and generic:
        prefer role+name locators; skip nameless controls."""
        candidates = []
        for node in self._accessibility_nodes(page):
            role = (node.get("role") or "").lower()
            name = (node.get("name") or "").strip()
            if role not in ("button", "tab", "menuitem", "treeitem", "link") or not name:
                continue
            c = dom_extract.classify_node(node)
            c["selector"] = f'role={role}[name="{_escape(name)}"]'
            candidates.append(c)
        return candidates

    def _classify(self, cand):
        return action_mod.classify_action(
            capability=cand.get("capability", ""), name=cand.get("name", ""),
            control_pattern=cand.get("control_pattern", ""), selector=cand.get("selector", ""),
            safe_patterns=self.config.safe_action_patterns,
            blocked_patterns=self.config.blocked_action_patterns,
            safe_selectors=self.config.safe_selectors, blocked_selectors=self.config.blocked_selectors,
        )

    def _record_candidate(self, cand, verdict):
        row = {"capability": cand.get("capability"), "name": cand.get("name"),
               "control_pattern": cand.get("control_pattern"), "verdict": verdict}
        if verdict == action_mod.BLOCKED:
            self.result.blocked_actions.append(row)
        elif verdict == action_mod.UNKNOWN:
            self.result.unknown_actions.append(row)

    def _restore_state(self, page, state):
        """SPA-safe backtrack: reload the seed URL rather than trusting Back."""
        try:
            if normalize_url(page.url) != state.url_normalized:
                page.goto(state.url, wait_until="domcontentloaded")
            page.keyboard.press("Escape")  # close any transient menu/dialog
        except Exception as exc:  # noqa: BLE001
            self.result.failures.append({"stage": "restore", "error": str(exc)})

    def _detect_version(self, page):
        """Best-effort exact version; UNKNOWN if not reliably available (never
        inferred from date)."""
        try:
            body = page.evaluate("() => (window.Granite && Granite.HTTP) ? 'granite' : ''")
            _ = body
        except Exception:  # noqa: BLE001
            pass
        return "UNKNOWN"

    # ---- pure-ish helpers --------------------------------------------------
    def _infer_surface(self, page):
        url = (page.url or "").lower()
        if "/editor" in url or "guides" in url and "assets" not in url:
            return "NEW_EDITOR"
        if "/assets" in url or "assetdetails" in url:
            return "ASSETS_UI"
        if "baseline" in url:
            return "BASELINE"
        return "UNKNOWN"

    def _first_role_name(self, nodes, role):
        for n in nodes:
            if (n.get("role") or "").lower() == role:
                return (n.get("name") or "").strip() or role.upper()
        return ""

    def _first_selected_tab(self, nodes):
        for n in nodes:
            if (n.get("role") or "").lower() == "tab" and n.get("selected"):
                return (n.get("name") or "").strip()
        return ""

    def _infer_relation(self, cand, to_state):
        if to_state.open_dialog:
            return "OPENS"
        if to_state.open_menu:
            return "OPENS"
        if "EXPAND" in (cand.get("capability") or ""):
            return "EXPANDS"
        return "UPDATES_UI_STATE"

    def _diff_effects(self, a, b):
        effects = []
        if b.open_dialog and b.open_dialog != a.open_dialog:
            effects.append(f"DIALOG_OPENED:{b.open_dialog}")
        if b.open_menu and b.open_menu != a.open_menu:
            effects.append(f"MENU_OPENED:{b.open_menu}")
        added = set(b.visible_capabilities) - set(a.visible_capabilities)
        if added:
            effects.append(f"CAPABILITIES_APPEARED:{len(added)}")
        return effects or ["STATE_UPDATED"]


def _escape(text):
    return text.replace('"', '\\"')
