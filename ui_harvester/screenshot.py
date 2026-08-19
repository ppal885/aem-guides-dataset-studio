"""Screenshot capture + content-hash dedup.

Uses page.screenshot() (application viewport only), so OS chrome/taskbar/clock
are never captured. A screenshot is stored under <output>/screenshots/ named by
content hash, and deduplicated by (checksum, state_id): identical bytes for the
same semantic state are stored once; a visually similar image with a DIFFERENT
semantic state is retained.
"""

import hashlib
from pathlib import Path


def image_checksum(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def screenshot_id(checksum, state_id):
    key = f"{checksum}|{state_id}".encode("utf-8")
    return "shot:" + hashlib.sha256(key).hexdigest()[:24]


class ScreenshotStore:
    """Dedup-aware screenshot writer. Pure filesystem; no browser dependency so
    the dedup logic is unit testable by feeding bytes directly."""

    def __init__(self, output_dir):
        self.dir = Path(output_dir) / "screenshots"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._by_checksum_state = {}  # (checksum, state_id) -> screenshot_id

    def store(self, data, state_id):
        """Persist bytes for a state; returns a stable screenshot_id, writing the
        file only the first time a (checksum, state) pair is seen."""
        checksum = image_checksum(data)
        key = (checksum, state_id)
        if key in self._by_checksum_state:
            return self._by_checksum_state[key], False  # deduped
        sid = screenshot_id(checksum, state_id)
        path = self.dir / f"{sid}.png"
        if not path.exists():
            path.write_bytes(data)
        self._by_checksum_state[key] = sid
        return sid, True

    def manifest_entry(self, state):
        return {
            "screenshot_id": state.screenshot_id,
            "state_id": state.state_id,
            "product": state.product,
            "product_area": state.product_area,
            "surface": state.surface,
            "region": state.region,
            "container": state.container,
            "active_panel": state.active_left_panel or state.active_right_panel,
            "editor_mode": state.active_editor_mode,
            "dialog": state.open_dialog,
            "menu": state.open_menu,
            "entity_context": state.active_entity_type,
            "visible_capabilities": state.visible_capabilities,
            "disabled_capabilities": state.disabled_capabilities,
            "empty_state": state.empty_state,
            "captured_at": state.captured_at,
            "product_version": state.product_version,
            "currentness": state.currentness,
            "screenshot_path": f"screenshots/{state.screenshot_id}.png" if state.screenshot_id else "",
            "authority": "UI_OBSERVATION",
        }
