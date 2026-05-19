#!/usr/bin/env python3
"""
Live smoke test: fetch one Jira issue via REST using backend/.env credentials.

Usage (from repo root or backend/):
  python backend/scripts/smoke_jira_issue.py
  python backend/scripts/smoke_jira_issue.py GUIDES-32719

Requires: JIRA_URL (or JIRA_BASE_URL), JIRA_USERNAME + JIRA_PASSWORD
          OR JIRA_EMAIL + JIRA_API_TOKEN. Optional: JIRA_API_VERSION (2|3).

Does not print secrets. On success prints summary + status only.
"""
from __future__ import annotations

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_backend))

_env = _backend / ".env"
if _env.exists():
    from dotenv import load_dotenv

    load_dotenv(_env, override=True, encoding="utf-8-sig")


def main() -> int:
    key = (sys.argv[1] if len(sys.argv) > 1 else "GUIDES-32719").strip().upper()
    print(f"Smoke test: GET issue {key}\n")

    from app.services.jira_client import JiraClient

    client = JiraClient()
    if not client.base_url:
        print("ERROR: Set JIRA_URL or JIRA_BASE_URL in backend/.env")
        return 1
    if not ((client.username and client.password) or (client.email and client.api_token)):
        print("ERROR: Set JIRA_USERNAME+JIRA_PASSWORD or JIRA_EMAIL+JIRA_API_TOKEN in backend/.env")
        return 1

    try:
        issue = client.get_issue(key, fields="summary,status,issuetype,description")
    except Exception as exc:
        print(f"ERROR: Jira request failed: {exc}")
        return 2

    fields = issue.get("fields") or {}
    summary = str(fields.get("summary") or "").strip()
    st = fields.get("status") or {}
    status = str(st.get("name") or "") if isinstance(st, dict) else ""
    it = fields.get("issuetype") or {}
    itype = str(it.get("name") or "") if isinstance(it, dict) else ""

    print("OK - issue readable from your Jira:")
    print(f"  key:     {issue.get('key', key)}")
    print(f"  type:    {itype}")
    print(f"  status:  {status}")
    print(f"  summary: {summary[:240]}{'…' if len(summary) > 240 else ''}")

    desc = fields.get("description")
    has_desc = bool(desc)
    print(f"  description field present: {has_desc}")

    # Optional: one line for UAC copilot — confirms same client the app uses
    print("\nNext: in the UI open UAC planner, set Jira key to this key or paste it in the message, then Send.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
