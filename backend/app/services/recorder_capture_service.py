"""Recorder / UI capture sessions: storage, redaction, validation, planning bridge."""

from __future__ import annotations

import copy
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.local_storage import LocalStorage
from app.services.qa_studio_automation_validator import _fragile_xpath_fragment

# Patterns to flag (avoid trusting for generated Behave)
_UNSTABLE_ID_RES = (
    re.compile(r"react-spectrum-[0-9]+", re.I),
    re.compile(r"tabView-jui-react-", re.I),
    re.compile(r"topic_id__", re.I),
    re.compile(r"\[@[a-z-]+=['\"][^'\"]{32,}['\"]", re.I),
)
_TOKEN_REDACT_RE = re.compile(
    r"\b(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_.-]+|"
    r"sk-[A-Za-z0-9]{16,}|"
    r"xox[baprs]-[A-Za-z0-9-]+|"
    r"api[_-]?key\s*[=:]\s*[\w-]{8,})\b",
    re.I,
)


def get_recorder_sessions_root() -> Path:
    raw = (os.getenv("RECORDER_SESSIONS_PATH") or "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    root = LocalStorage().base_path / "recorder_sessions"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _sanitize_session_id(session_id: str) -> str:
    s = "".join(c for c in (session_id or "").strip() if c.isalnum() or c in "-_")
    if not s or len(s) > 128:
        raise ValueError("invalid session id")
    root = get_recorder_sessions_root().resolve()
    candidate = (root / s).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ValueError("invalid session path") from None
    return s


def _session_paths(session_id: str) -> tuple[Path, Path]:
    sid = _sanitize_session_id(session_id)
    d = get_recorder_sessions_root() / sid
    return d, d / "session.json"


def new_session_id() -> str:
    return str(uuid.uuid4())


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_session_doc(session_id: str) -> dict[str, Any]:
    _, path = _session_paths(session_id)
    if not path.is_file():
        raise FileNotFoundError(session_id)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_session_doc(session_id: str, doc: dict[str, Any]) -> None:
    d, path = _session_paths(session_id)
    d.mkdir(parents=True, exist_ok=True)
    doc.setdefault("meta", {})
    doc["meta"]["updated_at_utc"] = _iso_now()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def create_session_from_capture(capture: dict[str, Any], *, session_id: str | None = None) -> str:
    sid = session_id or new_session_id()
    _sanitize_session_id(sid)
    d, _ = _session_paths(sid)
    d.mkdir(parents=True, exist_ok=True)
    doc = {
        "capture": capture,
        "meta": {
            "id": sid,
            "created_at_utc": _iso_now(),
            "updated_at_utc": _iso_now(),
            "attached_jira_key": None,
            "authoring_job_id": None,
            "user_notes_overlay": "",
        },
    }
    save_session_doc(sid, doc)
    return sid


def delete_session(session_id: str) -> bool:
    try:
        d, path = _session_paths(session_id)
    except ValueError:
        return False
    if not path.is_file():
        return False
    import shutil

    shutil.rmtree(d, ignore_errors=True)
    return True


def list_sessions(limit: int = 100) -> list[dict[str, Any]]:
    root = get_recorder_sessions_root()
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return []
    for child in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime if p.is_dir() else 0, reverse=True):
        if not child.is_dir():
            continue
        sp = child / "session.json"
        if not sp.is_file():
            continue
        try:
            with open(sp, encoding="utf-8") as f:
                doc = json.load(f)
            cap = doc.get("capture") or {}
            meta = doc.get("meta") or {}
            out.append(
                {
                    "id": meta.get("id") or child.name,
                    "workflow_name": cap.get("workflow_name"),
                    "jira_key": cap.get("jira_key") or meta.get("attached_jira_key"),
                    "started_at": cap.get("started_at"),
                    "step_count": len(cap.get("steps") or []) if isinstance(cap.get("steps"), list) else 0,
                    "updated_at_utc": meta.get("updated_at_utc"),
                }
            )
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out


def _deep_redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in ("password", "secret", "token", "authorization"):
                out[k] = "[REDACTED]"
            elif lk == "action_type" and str(v).lower() in ("input", "type", "fill"):
                out[k] = v
                # sibling fields handled when walking
            else:
                out[k] = _deep_redact(v)
        if str(out.get("action_type", "")).lower() in ("input", "clear", "type", "fill"):
            if isinstance(out.get("visible_text"), str) and "password" in json.dumps(out).lower():
                out["visible_text"] = "[REDACTED]"
            if isinstance(out.get("target_summary"), str) and "password" in (out.get("role") or "").lower():
                out["target_summary"] = "[REDACTED]"
        # mask token-like strings in known string fields
        for key in ("visible_text", "target_summary", "dom_snippet", "accessible_name", "user_notes"):
            if isinstance(out.get(key), str):
                out[key] = _TOKEN_REDACT_RE.sub("[REDACTED_TOKEN]", out[key])
        return out
    if isinstance(obj, list):
        return [_deep_redact(x) for x in obj]
    if isinstance(obj, str):
        return _TOKEN_REDACT_RE.sub("[REDACTED_TOKEN]", obj)
    return obj


def redact_capture_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied document with sensitive fields/token patterns scrubbed."""
    out = copy.deepcopy(doc)
    cap = out.get("capture")
    if isinstance(cap, dict):
        steps = cap.get("steps")
        if isinstance(steps, list):
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                st = _deep_redact(step)
                role = str(st.get("role") or "").lower()
                aria = str(st.get("aria") or "").lower()
                if "password" in role or "password" in aria or st.get("redaction_applied"):
                    for fk in ("visible_text", "target_summary", "dom_snippet"):
                        if fk in st and isinstance(st[fk], str) and len(st[fk]) > 0:
                            st[fk] = "[REDACTED_PASSWORD_FIELD]"
                    st["redaction_applied"] = True
                cap["steps"][i] = st
        out["capture"] = _deep_redact(cap)
    return out


def _step_unstable_locators(step: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    candidates = step.get("locator_candidates")
    if not isinstance(candidates, list):
        candidates = []
    for c in candidates:
        s = str(c if isinstance(c, str) else (c or {}).get("xpath") or (c or {}).get("value") or "")
        if not s:
            continue
        if _fragile_xpath_fragment(s):
            issues.append(f"fragile positional xpath: {s[:120]}")
        for rx in _UNSTABLE_ID_RES:
            if rx.search(s):
                issues.append(f"unstable generated-id pattern in locator: {s[:120]}")
    dom = str(step.get("dom_snippet") or "")
    for rx in _UNSTABLE_ID_RES:
        if rx.search(dom):
            issues.append("dom_snippet contains unstable generated id pattern")
            break
    return issues


def validate_capture(capture: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(capture, dict):
        return {"ok": False, "errors": ["capture must be an object"], "warnings": [], "steps": []}
    steps = capture.get("steps")
    if not isinstance(steps, list):
        errors.append("steps must be an array")
        steps = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"steps[{i}] must be an object")
            continue
        if not str(step.get("step_id") or "").strip():
            warnings.append(f"steps[{i}] missing step_id")
        if not str(step.get("action_type") or "").strip():
            warnings.append(f"steps[{i}] missing action_type")
        dom = str(step.get("dom_snippet") or "").strip()
        cand = step.get("locator_candidates")
        has_cand = isinstance(cand, list) and any(str(x).strip() for x in cand)
        if not dom and str(step.get("action_type") or "").lower() in ("click", "double_click", "right_click", "hover"):
            warnings.append(f"steps[{i}] click-like action without dom_snippet — locator review may be harder")
        if not has_cand and dom:
            warnings.append(f"steps[{i}] has DOM but no locator_candidates — PO match / governance incomplete")
        for u in _step_unstable_locators(step):
            warnings.append(f"steps[{i}] {u}")
        if step.get("screenshot_before") or step.get("screenshot_after"):
            pass
        elif str(step.get("action_type") or "").lower() in ("click", "select", "menu"):
            warnings.append(f"steps[{i}] ({step.get('action_type')}) has no screenshots — ambiguous UI state risk")
    if not (capture.get("expected_state_hint") or "").strip() and not (capture.get("user_notes") or "").strip():
        if capture.get("jira_key"):
            pass
        else:
            warnings.append("No Jira key and no expected_state_hint / user_notes — assertions may be under-specified")
    sensitive_hits = []
    blob = json.dumps(capture, ensure_ascii=False)
    for m in _TOKEN_REDACT_RE.finditer(blob[:50000]):
        sensitive_hits.append("possible token/API material in capture — run redaction before sharing")
        break
    warnings.extend(sensitive_hits[:2])
    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings, "step_count": len(steps)}


def format_repro_from_capture(capture: dict[str, Any], *, max_steps: int = 80) -> str:
    lines: list[str] = []
    steps = capture.get("steps") if isinstance(capture.get("steps"), list) else []
    for step in steps[:max_steps]:
        if not isinstance(step, dict):
            continue
        at = str(step.get("action_type") or "action").strip()
        ts = str(step.get("target_summary") or step.get("accessible_name") or step.get("visible_text") or "").strip()
        ctx = str(step.get("ancestor_context") or "").strip()[:200]
        line = f"- {at}"
        if ts:
            line += f": {ts[:300]}"
        if ctx:
            line += f" [{ctx}]"
        lines.append(line)
    return "\n".join(lines) if lines else "(no steps)"


def build_recorder_digest(capture: dict[str, Any], validation: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append("### Recorder capture (evidence — do not paste raw locators into Behave steps)")
    parts.append(
        f"session context: app_url={capture.get('app_url', '')!s} workflow={capture.get('workflow_name', '')!s} "
        f"jira_key={capture.get('jira_key', '')!s}"
    )
    aem = capture.get("aem_guides_context")
    if isinstance(aem, dict) and aem:
        parts.append(f"AEM Guides annotations: {json.dumps(aem, ensure_ascii=False)[:2000]}")
    parts.append("### Ordered user actions (normalize into framework When steps; use Page Object APIs only)")
    parts.append(format_repro_from_capture(capture))
    if validation.get("warnings"):
        parts.append("### Recorder validation warnings")
        for w in validation["warnings"][:25]:
            parts.append(f"- {w}")
    parts.append(
        "### Planning rules: derive Given/When/Then from Jira expected behavior; "
        "map actions to framework helpers and PO calls; ignore fragile recorder XPaths for generated code."
    )
    return "\n".join(parts)


def merge_recorder_into_authoring_fields(
    session_id: str | None,
    *,
    repro_steps: str,
    manual_notes: str,
    target_area: str,
    jira_key: str | None,
) -> tuple[str, str, str, dict[str, Any]]:
    """
    Merge stored recorder session into authoring fields. Returns (repro, notes, target_area, sidecar).
    """
    if not (session_id or "").strip():
        return repro_steps, manual_notes, target_area, {}
    doc = load_session_doc(_sanitize_session_id(session_id))
    capture = doc.get("capture")
    if not isinstance(capture, dict):
        raise ValueError("session has no capture")
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    validation = validate_capture(capture)
    digest = build_recorder_digest(capture, validation)
    recorder_repro = format_repro_from_capture(capture)
    merged_repro = (repro_steps or "").strip()
    if merged_repro:
        merged_repro = merged_repro + "\n\n### Recorder-derived steps\n" + recorder_repro
    else:
        merged_repro = "### Recorder-derived steps\n" + recorder_repro
    overlay = str(meta.get("user_notes_overlay") or "").strip()
    extra_notes_parts = [
        manual_notes.strip(),
        overlay,
        digest[:12000],
    ]
    merged_notes = "\n\n".join(p for p in extra_notes_parts if p)
    ta = (target_area or "").strip()
    if not ta and isinstance(capture.get("aem_guides_context"), dict):
        pan = capture["aem_guides_context"].get("primary_panel")
        if pan:
            ta = str(pan)[:200]
    jk = jira_key or capture.get("jira_key") or meta.get("attached_jira_key")
    sidecar = {
        "recorder_session_id": session_id,
        "validation": validation,
        "digest_excerpt": digest[:2000],
        "resolved_jira_from_session": jk if isinstance(jk, str) else None,
    }
    return merged_repro, merged_notes, ta, sidecar


def plan_input_from_session(session_id: str) -> dict[str, Any]:
    doc = load_session_doc(session_id)
    capture = doc.get("capture") if isinstance(doc.get("capture"), dict) else {}
    validation = validate_capture(capture)
    digest = build_recorder_digest(capture, validation)
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    return {
        "session_id": meta.get("id") or session_id,
        "repro_steps": format_repro_from_capture(capture),
        "manual_notes_digest": digest,
        "target_area_suggestion": (
            str((capture.get("aem_guides_context") or {}).get("primary_panel") or "")[:200] or None
        ),
        "jira_key": capture.get("jira_key") or meta.get("attached_jira_key"),
        "validation": validation,
    }


def attach_session_metadata(session_id: str, *, jira_key: str | None, authoring_job_id: str | None, user_notes: str) -> dict[str, Any]:
    doc = load_session_doc(session_id)
    meta = doc.setdefault("meta", {})
    if jira_key is not None:
        meta["attached_jira_key"] = jira_key.strip()[:50] or None
    if authoring_job_id is not None:
        meta["authoring_job_id"] = authoring_job_id.strip()[:128] or None
    if user_notes is not None:
        meta["user_notes_overlay"] = user_notes.strip()[:8000]
    cap = doc.setdefault("capture", {})
    if isinstance(cap, dict) and jira_key and not (cap.get("jira_key") or "").strip():
        cap["jira_key"] = jira_key.strip()[:50]
    save_session_doc(session_id, doc)
    return {"ok": True, "meta": meta}


def screenshots_dir(session_id: str) -> Path:
    d, _ = _session_paths(session_id)
    sd = d / "screenshots"
    sd.mkdir(parents=True, exist_ok=True)
    return sd
