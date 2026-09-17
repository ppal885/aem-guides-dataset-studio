"""A5: generate/verify Copilot custom-agent registrations from the canonical
Skill role contracts.

Single canonical source: skills/test-plan-generation/agents/<role>.md.
Registrations in .github/agents/<role>.agent.md are generated wrappers:
frontmatter (name/description/read-only tools) + the canonical contract body
verbatim.  Regenerate after editing a role contract:

    python scripts/sync_agent_registrations.py

CI/review verification (fails on any drift):

    python scripts/sync_agent_registrations.py --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

def _repo_root() -> Path:
    """The repository root is the first ancestor that actually holds the
    canonical Skill agents directory - preferring the real git checkout over
    a synced skill copy's own parent."""

    candidates = [
        ancestor
        for ancestor in Path(__file__).resolve().parents
        if (ancestor / "skills" / "test-plan-generation" / "agents").is_dir()
    ]
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate
    if candidates:
        return candidates[0]
    # Fallback for packaged layouts: two levels above the skill directory.
    return Path(__file__).resolve().parents[3]


SKILL_AGENTS = _repo_root() / "skills" / "test-plan-generation" / "agents"
REGISTRATIONS = _repo_root() / ".github" / "agents"

# Read-only minimum tool surface per role (A5 section 13): no write, no
# shell mutation, no Jira/Git mutation - research only.
ROLES = {
    "uac-doc-researcher": {
        "description": (
            "Bounded documentation research for one UAC question: answer from "
            "authorized product documentation only, with applicability, "
            "limitations, and structured findings; never writes ACs."
        ),
        "tools": ["view"],
    },
    "uac-code-researcher": {
        "description": (
            "Bounded read-only implementation research for one UAC question "
            "over authorized repositories, with exact revision/path "
            "provenance; never converts implementation into acceptance "
            "behavior."
        ),
        "tools": ["view", "grep"],
    },
    "uac-attachment-researcher": {
        "description": (
            "Bounded attachment-evidence interpretation for one UAC "
            "question: separates observed behavior from customer-stated "
            "desired behavior; never fabricates unreadable content."
        ),
        "tools": ["view"],
    },
}

_HEADER = (
    "<!-- Generated from skills/test-plan-generation/agents/{name}.md by "
    "sync_agent_registrations.py; never edit by hand. -->\n"
)


def _registration_text(name: str, contract: str) -> str:
    meta = ROLES[name]
    tools = "\n".join(f"  - {tool}" for tool in meta["tools"])
    return (
        "---\n"
        f"name: {name}\n"
        f"description: >\n  {meta['description']}\n"
        "deferred-tool-loading: true\n"
        "tools:\n"
        f"{tools}\n"
        "---\n\n"
        + _HEADER.format(name=name)
        + "\n"
        + contract.rstrip() + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify registrations match the canonical role contracts",
    )
    args = parser.parse_args()
    drift = []
    for name in sorted(ROLES):
        canonical_path = SKILL_AGENTS / f"{name}.md"
        registration_path = REGISTRATIONS / f"{name}.agent.md"
        if not canonical_path.exists():
            print(f"MISSING canonical role contract: {canonical_path}")
            drift.append(name)
            continue
        canonical = canonical_path.read_text(encoding="utf-8")
        expected = _registration_text(name, canonical)
        if args.check:
            if not registration_path.exists():
                print(f"MISSING registration: {registration_path}")
                drift.append(name)
            elif registration_path.read_text(encoding="utf-8") != expected:
                print(f"DRIFT: {registration_path} != {canonical_path}")
                drift.append(name)
        else:
            REGISTRATIONS.mkdir(parents=True, exist_ok=True)
            registration_path.write_text(expected, encoding="utf-8")
            print(f"synced: {registration_path}")
    if drift:
        print(f"\nFAIL: {len(drift)} role registration(s) drifted or missing")
        return 1
    print("OK" if args.check else "DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
