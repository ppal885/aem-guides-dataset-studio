"""List the AEM Guides configuration settings that can change the behaviour a ticket describes.

WHAT IT DOES
------------
Reads the current ticket's own text (summary, description, comments) and matches it against the
product areas in data/guides_config_settings.json (the Publish Configuration Manager settings, PID
com.adobe.fmdita.config.ConfigManager). For every matched area it lists the settings with their
Cloud Service and on-premise defaults, the Experience League page when one exists, and any known
difference between the documentation and the product source.

WHAT IT MUST NEVER DO
---------------------
A listed setting is a configuration candidate for discovery, never an Acceptance Criterion by
itself. For each one the author decides: the behaviour differs with this setting (cover the values
that matter in an AC), the answer is unknown (a TBD), or it does not apply (an out-of-scope reason).
A missing or malformed data file reports UNAVAILABLE and never blocks or relaxes any other gate.

Usage:
    python config_settings_lookup.py TICKET_TEXT_FILE [--limit N] [--json]

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "guides_config_settings.json"
SCHEMA_VERSION = "aem-guides-config-settings-v1"
DEFAULT_LIMIT = 5
NOTICE = ("Configuration candidate, not an acceptance criterion: decide whether the ticket's behaviour "
          "changes with this setting (AC for the values that matter), is unknown (TBD), or does not apply "
          "(out-of-scope reason).")


def load(path: Path = DATA_PATH) -> dict:
    """Return the validated data, or raise ValueError for a missing or malformed file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"config settings unreadable: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("config settings have an unsupported schema")
    if not isinstance(data.get("areas"), dict) or not isinstance(data.get("settings"), list):
        raise ValueError("config settings need 'areas' and 'settings'")
    keys = {s.get("key") for s in data["settings"] if isinstance(s, dict)}
    for name, area in data["areas"].items():
        missing = [k for k in area.get("keys") or [] if k not in keys]
        if not area.get("triggers") or missing:
            raise ValueError(f"area {name} has no triggers or unknown keys {missing}")
    return data


def _hits(trigger: str, text: str) -> int:
    """Whole-word match; a trailing * also matches longer words (replicat* matches replication)."""
    prefix = trigger.endswith("*")
    word = re.escape(trigger.rstrip("*").lower())
    return len(re.findall(r"(?<![A-Za-z0-9])" + word + ("" if prefix else r"(?![A-Za-z0-9])"), text))


def suggest(text: str, data: dict, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Return matched settings, most relevant first."""
    lowered = text.lower()
    by_key = {s["key"]: s for s in data["settings"]}
    scores: dict[str, int] = {}
    reasons: dict[str, list[str]] = {}
    for name, area in data["areas"].items():
        matched = [t for t in area["triggers"] if _hits(t, lowered)]
        if not matched:
            continue
        weight = sum(_hits(t, lowered) for t in matched)
        for key in area["keys"]:
            scores[key] = scores.get(key, 0) + weight
            reasons.setdefault(key, []).append(f"{name} ({', '.join(matched)})")
    ranked = sorted(scores, key=lambda k: (-scores[k], not by_key[k].get("documented"), k))
    return [dict(by_key[k], matched_because=reasons[k]) for k in ranked[:limit]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ticket_text_file", type=Path)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    text = args.ticket_text_file.read_text(encoding="utf-8", errors="replace")
    try:
        data = load()
    except ValueError as exc:
        result = {"status": "UNAVAILABLE", "reason": str(exc), "settings": []}
    else:
        found = suggest(text, data, args.limit)
        result = {"status": "OK" if found else "NO_MATCH", "notice": NOTICE, "pid": data.get("pid"), "settings": found}
    if args.json:
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0
    print(f"{result['status']}: {result.get('notice') or result.get('reason', '')}")
    for s in result["settings"]:
        defaults = ", ".join(f"{k}={v}" for k, v in s["defaults"].items())
        print(f"- {s['key']} ({s['label']}); default {defaults}; matched {'; '.join(s['matched_because'])}")
        print(f"  doc: {s['doc_urls'][0] if s['doc_urls'] else 'not documented on Experience League'}")
        if s.get("doc_code_conflict"):
            print(f"  note: {s['doc_code_conflict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
