"""Jira-safe formatting for anything the skill POSTS into a Jira comment.

TWO distinct Jira hazards:

1. Wiki markup: a comment body is Jira WIKI markup, not Markdown. `*text*` = bold,
   `-x-` = strikethrough, `_x_` italic, backticks/`{{ }}` monospace, `[t|url]` link.

2. ISSUE-KEY AUTO-LINKING (the real strikethrough cause): Jira auto-links any token
   shaped like an issue key (`[A-Z][A-Z0-9]+-\d+`). The plan's own labels - AC-01,
   OQ-03, TS-05 - match that shape, and because no project "AC"/"OQ"/"TS" exists,
   Jira renders them as a link to a NON-EXISTENT issue, which shows with a
   strikethrough. Removing bold/dashes does NOT fix this.

The robust fix is to wrap the posted body in a `{noformat}` block: Jira does not
process wiki markup OR auto-link issue keys inside it, so AC-01..AC-NN render
literally. `jira_comment_body` strips Markdown then wraps in `{noformat}`.
`validate_jira_safe` reports residual risk (used by the self-test).

Generic, stdlib only.
"""
from __future__ import annotations

import re

_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_BOLD2 = re.compile(r"\*\*([^*\n]+)\*\*")
_ITAL2 = re.compile(r"__([^_\n]+)__")
_STRIKE = re.compile(r"~~?([^~\n]+)~~?")
_CODE = re.compile(r"`([^`\n]+)`")
_BOLD1 = re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])")
_LEAD_BULLET = re.compile(r"^(\s*)[*+\-]\s+")
# A plan-internal label that Jira would try to auto-link as an issue key.
_KEY_SHAPED = re.compile(r"\b(?:AC|OQ|TS|CQ|MQ|H|SC|CF|D|AP|BGN|BGE|EV|EC)-\d{1,3}\b")
_NOFORMAT_OPEN = "{noformat}"
_NOFORMAT_CLOSE = "{noformat}"


def strip_markup(text: str) -> str:
    """Remove Markdown/wiki format markers so the text renders literally."""
    if not text:
        return text or ""
    out = []
    for line in text.split("\n"):
        s = line
        s = _MD_LINK.sub(r"\1 (\2)", s)
        s = s.replace("—", " - ").replace("–", " - ")
        s = _CODE.sub(r"\1", s)
        s = _BOLD2.sub(r"\1", s)
        s = _ITAL2.sub(r"\1", s)
        s = _STRIKE.sub(r"\1", s)
        s = _LEAD_BULLET.sub(r"\1", s)
        s = _BOLD1.sub(r"\1", s)
        s = s.replace("*", "")
        s = re.sub(r" {2,}", " ", s).rstrip()
        out.append(s)
    return "\n".join(out)


def jira_comment_body(text: str) -> str:
    """Return a Jira-comment-safe body: Markdown stripped and wrapped in a
    {noformat} block so plan labels (AC-01, OQ-03, ...) are NOT auto-linked/struck
    through and no wiki markup is interpreted."""
    inner = strip_markup(text).replace("{noformat}", "").strip()
    return f"{_NOFORMAT_OPEN}\n{inner}\n{_NOFORMAT_CLOSE}"


def validate_jira_safe(text: str) -> list[str]:
    """Report residual hazards in a comment body that is NOT wrapped in {noformat}."""
    if isinstance(text, str) and text.lstrip().startswith(_NOFORMAT_OPEN):
        return []  # a noformat block neutralizes both wiki markup and key auto-linking
    problems = []
    for name, rx in (
        ("asterisk", re.compile(r"\*")),
        ("underscore-bold", re.compile(r"__")),
        ("backtick", re.compile(r"`")),
        ("tilde", re.compile(r"~")),
        ("em/en dash", re.compile(r"[–—]")),
        ("markdown link", _MD_LINK),
    ):
        if rx.search(text or ""):
            problems.append(f"jira comment still contains {name}; use jira_comment_body()")
    if _KEY_SHAPED.search(text or ""):
        problems.append(
            "jira comment contains an issue-key-shaped plan label (e.g. AC-01) that Jira "
            "will auto-link and strike through; wrap the body with jira_comment_body()"
        )
    return problems


def main() -> int:
    import sys
    sys.stdout.write(jira_comment_body(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
