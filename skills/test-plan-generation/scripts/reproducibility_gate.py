"""Signal-activated reproducibility gate (hard).

Before a plan may assert fix-validation acceptance criteria, the issue must
actually reproduce. When the evidence carries a not-reproducible signal (a
"cannot/unable to reproduce" comment, a needs-clarification / crosshair label, a
working-hypothesis-only root cause, intermittent/flaky wording), a plan that
still ships fix-shaped ACs without a reproduction strategy - or without gating
those ACs on "once reproduced" - is the miss this gate stops (caught on the batch
UUID-conflict overwrite ticket that QE could not reproduce).

Plans with no not-reproducible signal are unaffected (backward-compatible).

Generic only.  Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PREFIX = "REPRODUCIBILITY GATE:"
BLOCK_NAME = "reproducibility"
VALID_STATUS = {"CONFIRMED", "UNCONFIRMED", "NOT_REPRODUCED"}
UNRESOLVED_STATUS = {"UNCONFIRMED", "NOT_REPRODUCED"}

# Strong not-reproducible signals. Kept specific to avoid false activation on a
# plan that merely mentions the word "reproduce" in a normal repro step.
NOT_REPRO_RE = re.compile(
    r"\b(?:un(?:able|-able)\s+to\s+repro|could\s*n[o']t\s+repro|can\s*not\s+repro|"
    r"cannot\s+repro|not\s+reproducible|not\s+able\s+to\s+reproduce|"
    r"couldn'?t\s+reproduce|unable\s+to\s+reproduce|no\s+consistent\s+repro|"
    r"working\s+hypothesis|root\s+cause\s+could\s+not\s+be\s+pinned|"
    r"needs[-\s]clarification|crosshair[-\s]needs[-\s]clarification)\b",
    re.IGNORECASE,
)
# A plan that actually contains reproduction-strategy content.
REPRO_STRATEGY_RE = re.compile(
    r"reproduc(?:tion|e)\s+strateg|to\s+reproduce|trigger\s+condition|repro\s+step|"
    r"reliably\s+(?:trigger|reproduce)|force\s+(?:the\s+)?(?:race|concurrent|collision)",
    re.IGNORECASE,
)
# "gated on once reproduced" acknowledgement in the plan body.
GATED_RE = re.compile(
    r"once\s+reproduc|after\s+(?:it\s+)?reproduc|gated\s+on\s+reproduc|pending\s+reproduc|"
    r"blocked\s+on\s+reproduc",
    re.IGNORECASE,
)


def _problem(message: str) -> str:
    return f"{PREFIX} {message}"


def _manifest_text(manifest: dict[str, Any]) -> str:
    parts: list[str] = []
    issue = manifest.get("issue")
    if isinstance(issue, dict):
        parts.append(str(issue.get("summary", "")))
        parts.append(str(issue.get("description", "")))
        labels = issue.get("labels")
        if isinstance(labels, list):
            parts.append(" ".join(str(x) for x in labels))
    for key in ("repro_signals", "reproducibility_signals"):
        val = manifest.get(key)
        if isinstance(val, list):
            parts.append(" ".join(str(x) for x in val))
        elif isinstance(val, str):
            parts.append(val)
    return "\n".join(parts)


def detect_signals(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    detected: list[str] = []
    if isinstance(manifest_data.get(BLOCK_NAME), dict):
        detected.append(f"{BLOCK_NAME} block")
    hay = _manifest_text(manifest_data) + "\n" + (plan_body or "")
    if NOT_REPRO_RE.search(hay):
        detected.append("not-reproducible signal")
    return list(dict.fromkeys(detected))


def is_present(plan_body: str = "", manifest: dict[str, Any] | None = None) -> bool:
    return bool(detect_signals(plan_body, manifest))


def _has_fix_acs(plan_body: str) -> bool:
    # Any acceptance criterion at all counts as fix-shaped scope unless the plan
    # is explicitly a reproduction/triage plan; the presence of AC-## lines is the
    # trigger. A reproduction-only plan carries a strategy (checked separately).
    return bool(re.search(r"^-\s*AC-\d", plan_body or "", re.MULTILINE))


def validate(plan_body: str = "", manifest: dict[str, Any] | None = None) -> list[str]:
    manifest_data = manifest if isinstance(manifest, dict) else {}
    signals = detect_signals(plan_body, manifest_data)
    if not signals:
        return []

    block = manifest_data.get(BLOCK_NAME)
    if not isinstance(block, dict):
        return [_problem(
            "a not-reproducible signal is present but no reproducibility block is declared; "
            "record {status, evidence, reproduction_strategy_present, fix_acs_gated_on_reproduction}"
        )]

    problems: list[str] = []
    status = str(block.get("status", "")).strip().upper()
    if status not in VALID_STATUS:
        problems.append(_problem(f"reproducibility.status must be one of {sorted(VALID_STATUS)}; got {block.get('status')!r}"))
        return problems
    if not str(block.get("evidence", "")).strip():
        problems.append(_problem("reproducibility.evidence must quote the not-reproducible evidence (comment/label/hypothesis)"))

    if status in UNRESOLVED_STATUS:
        if block.get("reproduction_strategy_present") is not True:
            problems.append(_problem(
                "reproduction is unconfirmed - the primary deliverable is a REPRODUCTION STRATEGY "
                "(exact trigger conditions: concurrency, timing, collision setup, batch size, "
                "environment, data). Set reproduction_strategy_present=true and include it in the plan"
            ))
        elif not REPRO_STRATEGY_RE.search(plan_body or ""):
            problems.append(_problem(
                "reproducibility declares a reproduction strategy but the plan body contains no "
                "reproduction-strategy content (trigger conditions / how to reliably reproduce)"
            ))
        if _has_fix_acs(plan_body):
            if block.get("fix_acs_gated_on_reproduction") is not True:
                problems.append(_problem(
                    "fix-validation ACs are present while reproduction is unconfirmed - keep them "
                    "Proposed and gated on 'once reproduced' (set fix_acs_gated_on_reproduction=true "
                    "and state the gating in the plan)"
                ))
            elif not GATED_RE.search(plan_body or ""):
                problems.append(_problem(
                    "fix_acs_gated_on_reproduction=true but the plan does not state the ACs are gated "
                    "on reproduction ('once reproduced' / 'pending reproduction')"
                ))
    return problems


def summarize(plan_body: str = "", manifest: dict[str, Any] | None = None) -> str:
    if not detect_signals(plan_body, manifest):
        return "reproducibility gate: not activated"
    block = (manifest or {}).get(BLOCK_NAME) if isinstance(manifest, dict) else None
    status = str(block.get("status", "?")).upper() if isinstance(block, dict) else "undeclared"
    return f"reproducibility gate: activated (status={status})"


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproducibility gate (hard)")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    plan_body = args.plan.read_text(encoding="utf-8") if args.plan.exists() else ""
    manifest_data = (
        json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.exists() else {}
    )
    problems = validate(plan_body, manifest_data)
    if problems:
        for p in problems:
            print(p)
        return 1
    print(summarize(plan_body, manifest_data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
