"""One-call deploy verification for the canonical test-plan runtime on the VM.

Reports the running build_commit (compare to `git rev-parse --short HEAD`) and counts
evidence-fragment bullets in the rendered coverage sections (should be 0 with the
evidence filter live). Usage:
  python scripts/verify_deploy.py [--vm http://10.42.46.78:4502] [--expect <sha>] [KEY ...]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

_FRAG = re.compile(
    r"\.png|\|thumbnail|^\s*-\s*(?:documented purpose|learn about|configure |source page|"
    r"how to use this in rag)|\.java\b|https?://|PropertiesUtil|"
    r"\b\w+(?:\.\w+)+\s*=\s*(?:true|false)\b|\b\w+\.\w+\.\w+\.\w+\b|"
    r"release of adobe experience manager|^\s*-\s*[\d.]+\s*$",
    re.I,
)


def _coverage_bullets(plan: str) -> list[str]:
    out, in_cov = [], False
    for line in plan.splitlines():
        if line.startswith("## "):
            in_cov = "coverage" in line.lower()
        elif in_cov and line.strip().startswith("- "):
            out.append(line)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vm", default="http://10.42.46.78:4502")
    ap.add_argument("--token", default=os.getenv("AEM_STUDIO_TOKEN", "dev-bypass"))
    ap.add_argument("--expect", default="")
    ap.add_argument("keys", nargs="*", default=["GUIDES-14665", "GUIDES-52444"])
    args = ap.parse_args()
    keys = args.keys or ["GUIDES-14665", "GUIDES-52444"]

    commits, total_frag = set(), 0
    for key in keys:
        try:
            r = requests.post(
                args.vm.rstrip("/") + "/api/v1/mcp/guides-test-plan-generator",
                headers={"Authorization": f"Bearer {args.token}", "Content-Type": "application/json"},
                json={"jira_key": key, "skip_uac_label_gate": True, "full_rag": True},
                timeout=300, verify=False,
            )
        except Exception as exc:
            print(f"{key}: request failed: {exc!r}")
            continue
        if r.status_code != 200:
            print(f"{key}: HTTP {r.status_code}")
            continue
        data = r.json()
        commits.add(data.get("build_commit", "MISSING"))
        frags = [b for b in _coverage_bullets(data.get("plan_markdown", "")) if _FRAG.search(b)]
        total_frag += len(frags)
        print(f"{key}: build_commit={data.get('build_commit', 'MISSING')} evidence-fragment bullets={len(frags)}")
        for f in frags[:3]:
            print("     FRAG:", f.strip()[:90])

    print(f"\nrunning build_commit(s): {sorted(commits)}")
    print(f"total evidence-fragment bullets: {total_frag} (expected 0)")
    if args.expect:
        live = commits == {args.expect}
        print(f"expected {args.expect}: {'MATCH - deploy live' if live else 'MISMATCH - not deployed / cached'}")
        return 0 if (live and total_frag == 0) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
