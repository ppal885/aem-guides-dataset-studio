r"""Jira-safe formatting for anything the skill POSTS into a Jira comment.

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


_AC_BLOCK = re.compile(
    r"^-\s*(Acceptance Criteria \d+):\s*(.+?)\s*$"
    r"((?:\n[ \t]+(?:\*\*)?(?:Source|TBD):(?:\*\*)?\s*.+)*)",
    re.MULTILINE,
)
_SUB_LINE = re.compile(r"^[ \t]+(?:\*\*)?(Source|TBD):(?:\*\*)?\s*(.+)$", re.MULTILINE)
_FILE_TOKEN = re.compile(
    r"(?<![{\w])([\w./-]+\.(?:java|js|ts|tsx|py|xml|xsl|json|csv|md|dita|ditamap"
    r"|feature|yaml|yml|properties|txt|sh|html|css))(?![}\w])"
)
_MONOSPACE_SPAN = re.compile(r"(\{\{.*?\}\})")
_BACKSLASH = chr(92)


def _escape_wiki_brackets(text: str) -> str:
    """Escape [ and ] outside {{monospace}} spans. In Jira wiki a bracket pair is a
    link, so a UI name such as [Home page] would otherwise render as a broken link."""
    parts = _MONOSPACE_SPAN.split(text or "")
    return "".join(
        part if _MONOSPACE_SPAN.fullmatch(part)
        else part.replace("[", _BACKSLASH + "[").replace("]", _BACKSLASH + "]")
        for part in parts
    )


def _wiki_text(text: str) -> str:
    return _escape_wiki_brackets(_FILE_TOKEN.sub(r"{{\1}}", strip_markup(text)))


def jira_field_body(text: str) -> str:
    """Render the delivered UAC block for a wiki-rendered Jira field.

    Each criterion becomes a bold 'Acceptance Criteria NN:' label with its
    Source/TBD lines as bullets. File names go in {{monospace}} so underscores
    and dashes inside them cannot turn into italics or strikethrough, and
    square-bracket UI names are escaped so they do not become links. The
    'Acceptance Criteria NN' label is not issue-key shaped, so it is not
    auto-linked. Use jira_comment_body for free-form comments.
    """
    blocks = []
    for match in _AC_BLOCK.finditer(text or ""):
        label, statement, subs = match.groups()
        lines = [f"*{label}:* {_wiki_text(statement)}"]
        for kind, value in _SUB_LINE.findall(subs or ""):
            lines.append(f"* {kind}: {_wiki_text(value)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


_MD_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_MD_BULLET = re.compile(r"^\s*[-*+]\s+(.+)$")
_MD_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.+)$")


def jira_wiki_from_markdown(text: str) -> str:
    """Render a short Markdown note (headings, bullets, numbered lists, paragraphs)
    as Jira wiki for a comment that should keep its structure, such as a
    decision request. Headings become bold lines, bullets '*', numbered items '#';
    brackets are escaped and file names go in {{monospace}}."""
    out = []
    for line in (text or "").splitlines():
        if not line.strip():
            out.append("")
            continue
        heading = _MD_HEADING.match(line)
        numbered = _MD_NUMBERED.match(line)
        bullet = _MD_BULLET.match(line)
        if heading:
            out.append(f"*{_wiki_text(heading.group(1))}*")
        elif numbered:
            out.append(f"# {_wiki_text(numbered.group(1))}")
        elif bullet:
            out.append(f"* {_wiki_text(bullet.group(1))}")
        else:
            out.append(_wiki_text(line))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


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
