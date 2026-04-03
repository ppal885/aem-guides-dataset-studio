"""
Author Safety Service — complete human control layer over AI generation.

Handles:
1. Relevance check — is generated DITA actually relevant to the Jira issue?
2. Scratch mode — author writes from scratch, AI is just assistant
3. Audit log — every AI vs human change tracked
4. Version history — compare AI draft vs final
5. Approval gate — human must approve before publish
6. Section locks — mark sections as author-only, AI cannot touch

Place at: backend/app/services/author_safety_service.py
"""
from __future__ import annotations

import difflib
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

SAFETY_STORE = Path(__file__).resolve().parent.parent / "storage" / "author_safety"
SAFETY_STORE.mkdir(parents=True, exist_ok=True)


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class RelevanceCheck:
    """Result of checking if generated DITA matches the Jira issue."""
    issue_key:        str
    is_relevant:      bool
    score:            float          # 0.0 - 1.0
    matched_terms:    list[str]      = field(default_factory=list)
    missing_terms:    list[str]      = field(default_factory=list)
    wrong_topic_type: bool           = False
    warnings:         list[str]      = field(default_factory=list)
    recommendation:   str            = ""

    def to_dict(self) -> dict:
        return {
            "issue_key":        self.issue_key,
            "is_relevant":      self.is_relevant,
            "score":            round(self.score, 2),
            "matched_terms":    self.matched_terms,
            "missing_terms":    self.missing_terms,
            "wrong_topic_type": self.wrong_topic_type,
            "warnings":         self.warnings,
            "recommendation":   self.recommendation,
        }


@dataclass
class VersionEntry:
    """A single version of a DITA file."""
    version:      int
    content:      str
    author:       str            # "ai" | "human" | "mixed"
    action:       str            # "generated" | "edited" | "approved" | "rejected" | "scratch"
    timestamp:    str
    ai_percent:   float          # how much is AI-written (0-100)
    comment:      str            = ""
    diff_from_prev: str          = ""   # unified diff from previous version

    def to_dict(self) -> dict:
        return {
            "version":      self.version,
            "author":       self.author,
            "action":       self.action,
            "timestamp":    self.timestamp,
            "ai_percent":   round(self.ai_percent, 1),
            "comment":      self.comment,
            "diff_lines":   len(self.diff_from_prev.splitlines()) if self.diff_from_prev else 0,
        }


@dataclass
class AuditEntry:
    """Single audit log entry tracking AI vs human contribution."""
    issue_key:   str
    filename:    str
    action:      str             # generated | section_edited | section_locked | approved | rejected | scratch_started
    actor:       str             # "ai" | author name
    timestamp:   str
    section:     str             = ""
    old_content: str             = ""
    new_content: str             = ""
    metadata:    dict            = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "issue_key":  self.issue_key,
            "filename":   self.filename,
            "action":     self.action,
            "actor":      self.actor,
            "timestamp":  self.timestamp,
            "section":    self.section,
            "change_size": abs(len(self.new_content) - len(self.old_content)) if self.new_content else 0,
            "metadata":   self.metadata,
        }


@dataclass
class ApprovalRecord:
    """Approval status for a DITA file before publishing."""
    issue_key:     str
    filename:      str
    status:        str           # "pending" | "approved" | "rejected" | "needs_revision"
    approved_by:   str           = ""
    approved_at:   str           = ""
    rejected_by:   str           = ""
    rejected_at:   str           = ""
    rejection_reason: str        = ""
    ai_percent:    float         = 0.0
    version:       int           = 0
    notes:         str           = ""

    def to_dict(self) -> dict:
        return {
            "issue_key":        self.issue_key,
            "filename":         self.filename,
            "status":           self.status,
            "approved_by":      self.approved_by,
            "approved_at":      self.approved_at,
            "rejected_by":      self.rejected_by,
            "rejection_reason": self.rejection_reason,
            "ai_percent":       round(self.ai_percent, 1),
            "version":          self.version,
            "notes":            self.notes,
        }


# ── 1. Relevance Check ────────────────────────────────────────────────────────

def check_relevance(
    issue: dict,
    generated_content: str,
    dita_type: str,
) -> RelevanceCheck:
    """
    Check if the generated DITA is actually relevant to the Jira issue.

    Catches:
    - Wrong topic (AI generated about a different issue)
    - Wrong DITA type (task when issue needs concept)
    - Missing key terms from the issue
    - Content that ignores the actual problem
    """
    issue_key = issue.get("issue_key", "")
    summary   = (issue.get("summary") or "").lower()
    desc      = (issue.get("description") or "").lower()
    labels    = [l.lower() for l in (issue.get("labels") or [])]
    content_l = generated_content.lower()

    warnings:      list[str] = []
    matched_terms: list[str] = []
    missing_terms: list[str] = []

    # Extract key terms from the issue
    key_terms = _extract_key_terms_for_check(summary, desc, labels)

    # Check how many key terms appear in the generated content
    for term in key_terms:
        if term.lower() in content_l:
            matched_terms.append(term)
        else:
            missing_terms.append(term)

    match_ratio = len(matched_terms) / len(key_terms) if key_terms else 0.0

    # Check wrong DITA type
    wrong_type = False
    expected_type = _infer_expected_type(issue)
    if expected_type and expected_type != dita_type:
        wrong_type = True
        warnings.append(
            f"Expected {expected_type} topic based on issue labels, "
            f"but generated {dita_type}"
        )

    # Check if issue key is referenced
    if issue_key.lower() not in content_l and issue_key not in generated_content:
        warnings.append(f"Issue key {issue_key} not referenced in generated content")

    # Check for generic/placeholder content
    generic_signals = [
        "lorem ipsum", "placeholder", "todo", "tbd",
        "insert content here", "sample text",
    ]
    for sig in generic_signals:
        if sig in content_l:
            warnings.append(f"Generic placeholder content detected: '{sig}'")

    # Check if summary keywords appear
    summary_words = [w for w in summary.split() if len(w) > 4][:5]
    summary_hits  = sum(1 for w in summary_words if w in content_l)
    if summary_words and summary_hits / len(summary_words) < 0.3:
        warnings.append(
            "Generated content seems unrelated to issue summary — "
            "fewer than 30% of summary keywords found"
        )

    # Compute overall relevance score
    score = (
        0.5 * match_ratio +
        0.3 * (summary_hits / len(summary_words) if summary_words else 0) +
        0.2 * (0.0 if wrong_type else 1.0)
    )

    # Determine recommendation
    if score >= 0.7 and not wrong_type:
        recommendation = "Content looks relevant. Review and approve."
    elif score >= 0.4:
        recommendation = (
            "Content is partially relevant. Use Review Mode to approve "
            "good sections and rewrite or reject weak ones."
        )
    else:
        recommendation = (
            "Content may not match the issue. Consider rejecting and "
            "regenerating, or use Scratch Mode to write from scratch."
        )

    return RelevanceCheck(
        issue_key        = issue_key,
        is_relevant      = score >= 0.4 and not (score < 0.2),
        score            = score,
        matched_terms    = matched_terms,
        missing_terms    = missing_terms[:5],
        wrong_topic_type = wrong_type,
        warnings         = warnings,
        recommendation   = recommendation,
    )


def _extract_key_terms_for_check(summary: str, desc: str, labels: list[str]) -> list[str]:
    """Extract the most important terms to check for in generated content."""
    terms = []

    # From labels (highest priority — explicit)
    terms.extend([l for l in labels if len(l) > 3][:4])

    # From summary — words > 4 chars
    summary_words = [w.strip(".,;:") for w in summary.split() if len(w) > 4]
    terms.extend(summary_words[:5])

    # Technical DITA/AEM terms from description
    tech_terms = [
        "keyref", "keyscope", "conref", "ditaval", "xref", "mapref",
        "outputclass", "profiling", "baseline", "publishing",
        "aem guides", "oxygen", "shortdesc", "taskbody",
    ]
    desc_lower = desc.lower()
    terms.extend([t for t in tech_terms if t in desc_lower][:3])

    # Deduplicate
    seen = set()
    unique = []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)

    return unique[:10]


def _infer_expected_type(issue: dict) -> Optional[str]:
    """Infer expected DITA type from issue to detect wrong type."""
    labels    = [l.lower() for l in (issue.get("labels") or [])]
    issue_type = (issue.get("issue_type") or "").lower()

    if any(l in labels for l in ["concept", "overview", "explanation"]):
        return "concept"
    if any(l in labels for l in ["reference", "api", "syntax"]):
        return "reference"
    if any(l in labels for l in ["glossary", "term"]):
        return "glossentry"
    if any(l in labels for l in ["task", "howto", "procedure"]):
        return "task"
    return None  # can't determine — no mismatch warning


# ── 2. Version History ────────────────────────────────────────────────────────

def save_version(
    issue_key: str,
    filename:  str,
    content:   str,
    author:    str,       # "ai" or author name
    action:    str,
    comment:   str = "",
) -> VersionEntry:
    """Save a new version of a DITA file."""
    history = _load_history(issue_key, filename)
    prev_content = history[-1].content if history else ""
    version_num  = len(history) + 1

    # Compute diff from previous version
    diff = _compute_diff(prev_content, content)

    # Compute AI % — how much of final content is from original AI draft
    ai_percent = _compute_ai_percent(
        original_ai = history[0].content if history else content,
        current     = content,
        author      = author,
    )

    entry = VersionEntry(
        version      = version_num,
        content      = content,
        author       = author,
        action       = action,
        timestamp    = datetime.utcnow().isoformat(),
        ai_percent   = ai_percent,
        comment      = comment,
        diff_from_prev = diff,
    )

    history.append(entry)
    _save_history(issue_key, filename, history)

    logger.info_structured(
        "Version saved",
        extra_fields={
            "issue_key":  issue_key,
            "filename":   filename,
            "version":    version_num,
            "author":     author,
            "action":     action,
            "ai_percent": ai_percent,
        },
    )
    return entry


def get_version_history(issue_key: str, filename: str) -> list[dict]:
    """Get version history for a file."""
    history = _load_history(issue_key, filename)
    return [v.to_dict() for v in history]


def get_version_diff(issue_key: str, filename: str, v1: int, v2: int) -> dict:
    """Get unified diff between two versions."""
    history = _load_history(issue_key, filename)
    versions = {v.version: v for v in history}

    if v1 not in versions or v2 not in versions:
        return {"error": f"Version {v1} or {v2} not found"}

    diff = _compute_diff(versions[v1].content, versions[v2].content)
    return {
        "v1": v1, "v2": v2,
        "diff":       diff,
        "diff_lines": len(diff.splitlines()),
        "v1_ai_pct":  versions[v1].ai_percent,
        "v2_ai_pct":  versions[v2].ai_percent,
    }


def _compute_diff(old: str, new: str) -> str:
    if not old:
        return "+ (new file)"
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile="previous", tofile="current",
        lineterm="",
    )
    return "".join(list(diff)[:100])  # limit diff size


def _compute_ai_percent(original_ai: str, current: str, author: str) -> float:
    """Estimate how much of the current content is still from the AI original."""
    if author == "ai":
        return 100.0
    if author == "scratch":
        return 0.0
    if not original_ai or not current:
        return 50.0

    # Use SequenceMatcher to estimate similarity to original AI draft
    ratio = difflib.SequenceMatcher(None, original_ai, current).ratio()
    return round(ratio * 100, 1)


def _load_history(issue_key: str, filename: str) -> list[VersionEntry]:
    path = SAFETY_STORE / f"{issue_key}_{filename}_history.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            VersionEntry(**{
                k: v for k, v in entry.items()
                if k in VersionEntry.__dataclass_fields__
            })
            for entry in data
        ]
    except Exception:
        return []


def _save_history(issue_key: str, filename: str, history: list[VersionEntry]):
    path = SAFETY_STORE / f"{issue_key}_{filename}_history.json"
    path.write_text(
        json.dumps([
            {
                "version":       v.version,
                "content":       v.content,
                "author":        v.author,
                "action":        v.action,
                "timestamp":     v.timestamp,
                "ai_percent":    v.ai_percent,
                "comment":       v.comment,
                "diff_from_prev": v.diff_from_prev,
            }
            for v in history
        ], indent=2),
        encoding="utf-8",
    )


# ── 3. Audit Log ─────────────────────────────────────────────────────────────

def log_audit(
    issue_key:   str,
    filename:    str,
    action:      str,
    actor:       str,
    section:     str = "",
    old_content: str = "",
    new_content: str = "",
    metadata:    dict = None,
):
    """Append an entry to the audit log."""
    entry = AuditEntry(
        issue_key   = issue_key,
        filename    = filename,
        action      = action,
        actor       = actor,
        timestamp   = datetime.utcnow().isoformat(),
        section     = section,
        old_content = old_content[:500],
        new_content = new_content[:500],
        metadata    = metadata or {},
    )

    path = SAFETY_STORE / f"{issue_key}_audit.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict()) + "\n")


def get_audit_log(issue_key: str) -> list[dict]:
    """Get full audit log for an issue."""
    path = SAFETY_STORE / f"{issue_key}_audit.jsonl"
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries


# ── 4. Approval Gate ─────────────────────────────────────────────────────────

def create_approval_request(
    issue_key:  str,
    filename:   str,
    content:    str,
    ai_percent: float,
    version:    int,
) -> ApprovalRecord:
    """Create an approval request — required before publishing."""
    record = ApprovalRecord(
        issue_key  = issue_key,
        filename   = filename,
        status     = "pending",
        ai_percent = ai_percent,
        version    = version,
    )
    _save_approval(record)

    log_audit(
        issue_key = issue_key,
        filename  = filename,
        action    = "approval_requested",
        actor     = "system",
        metadata  = {"ai_percent": ai_percent, "version": version},
    )
    return record


def approve_file(
    issue_key:   str,
    filename:    str,
    approved_by: str,
    notes:       str = "",
) -> ApprovalRecord:
    """Author approves the file for publishing."""
    record = _load_approval(issue_key, filename)
    if not record:
        record = ApprovalRecord(issue_key=issue_key, filename=filename, status="pending")

    record.status      = "approved"
    record.approved_by = approved_by
    record.approved_at = datetime.utcnow().isoformat()
    record.notes       = notes
    _save_approval(record)

    log_audit(
        issue_key = issue_key,
        filename  = filename,
        action    = "approved",
        actor     = approved_by,
        metadata  = {"notes": notes},
    )
    return record


def reject_file(
    issue_key:        str,
    filename:         str,
    rejected_by:      str,
    rejection_reason: str,
) -> ApprovalRecord:
    """Author rejects the file — must be revised before publishing."""
    record = _load_approval(issue_key, filename)
    if not record:
        record = ApprovalRecord(issue_key=issue_key, filename=filename, status="pending")

    record.status           = "rejected"
    record.rejected_by      = rejected_by
    record.rejected_at      = datetime.utcnow().isoformat()
    record.rejection_reason = rejection_reason
    _save_approval(record)

    log_audit(
        issue_key = issue_key,
        filename  = filename,
        action    = "rejected",
        actor     = rejected_by,
        metadata  = {"reason": rejection_reason},
    )
    return record


def get_approval_status(issue_key: str, filename: str) -> dict:
    record = _load_approval(issue_key, filename)
    if not record:
        return {"status": "not_submitted", "issue_key": issue_key, "filename": filename}
    return record.to_dict()


def _save_approval(record: ApprovalRecord):
    path = SAFETY_STORE / f"{record.issue_key}_{record.filename}_approval.json"
    path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")


def _load_approval(issue_key: str, filename: str) -> Optional[ApprovalRecord]:
    path = SAFETY_STORE / f"{issue_key}_{filename}_approval.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ApprovalRecord(
            issue_key        = data.get("issue_key", issue_key),
            filename         = data.get("filename", filename),
            status           = data.get("status", "pending"),
            approved_by      = data.get("approved_by", ""),
            approved_at      = data.get("approved_at", ""),
            rejected_by      = data.get("rejected_by", ""),
            rejected_at      = data.get("rejected_at", ""),
            rejection_reason = data.get("rejection_reason", ""),
            ai_percent       = data.get("ai_percent", 0.0),
            version          = data.get("version", 0),
            notes            = data.get("notes", ""),
        )
    except Exception:
        return None


# ── 5. Scratch Mode ───────────────────────────────────────────────────────────

SCRATCH_TEMPLATES = {
    "task": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">
<task id="{id}" xml:lang="en-US">
  <title><!-- Write your title here --></title>
  <shortdesc><!-- One sentence describing what this task does --></shortdesc>
  <taskbody>
    <prereq>
      <p><!-- What the user needs before starting (optional) --></p>
    </prereq>
    <context>
      <p><!-- Why this task is needed and when to perform it (optional) --></p>
    </context>
    <steps>
      <step>
        <cmd><!-- First step --></cmd>
      </step>
      <step>
        <cmd><!-- Second step --></cmd>
      </step>
    </steps>
    <result>
      <p><!-- What happens when steps complete successfully (optional) --></p>
    </result>
  </taskbody>
</task>""",

    "concept": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="{id}" xml:lang="en-US">
  <title><!-- Write your title here --></title>
  <shortdesc><!-- One sentence explaining what this concept is --></shortdesc>
  <conbody>
    <p><!-- Introduction paragraph --></p>
    <section>
      <title><!-- Section title --></title>
      <p><!-- Section content --></p>
    </section>
    <example>
      <p><!-- A concrete example (optional) --></p>
    </example>
  </conbody>
</concept>""",

    "reference": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">
<reference id="{id}" xml:lang="en-US">
  <title><!-- Write your title here --></title>
  <shortdesc><!-- One sentence describing what this reference covers --></shortdesc>
  <refbody>
    <section>
      <title><!-- Section title --></title>
      <p><!-- Reference content --></p>
    </section>
    <properties>
      <prophead>
        <proptypehd>Parameter</proptypehd>
        <propvaluehd>Value</propvaluehd>
        <propdeschd>Description</propdeschd>
      </prophead>
      <property>
        <proptype><!-- parameter name --></proptype>
        <propvalue><!-- value --></propvalue>
        <propdesc><!-- description --></propdesc>
      </property>
    </properties>
  </refbody>
</reference>""",

    "glossentry": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE glossentry PUBLIC "-//OASIS//DTD DITA Glossary Entry//EN" "glossentry.dtd">
<glossentry id="{id}" xml:lang="en-US">
  <glossterm><!-- The term --></glossterm>
  <glossdef><!-- Full definition of the term --></glossdef>
  <glossBody>
    <p><!-- Additional context or usage notes (optional) --></p>
  </glossBody>
</glossentry>""",
}


def start_scratch_mode(
    issue_key: str,
    dita_type: str,
    author:    str,
) -> dict:
    """
    Author rejects AI output and writes from scratch.
    Returns a clean DITA template appropriate for the topic type.
    """
    topic_id = issue_key.lower().replace("-", "_")
    template = SCRATCH_TEMPLATES.get(dita_type, SCRATCH_TEMPLATES["task"])
    content  = template.format(id=topic_id)
    filename = f"{issue_key.lower()}-{dita_type}.dita"

    # Save version 1 as scratch start
    save_version(
        issue_key = issue_key,
        filename  = filename,
        content   = content,
        author    = author,
        action    = "scratch_started",
        comment   = f"Author started from scratch ({dita_type} template)",
    )

    log_audit(
        issue_key = issue_key,
        filename  = filename,
        action    = "scratch_started",
        actor     = author,
        metadata  = {"dita_type": dita_type, "reason": "AI output rejected"},
    )

    return {
        "filename": filename,
        "content":  content,
        "dita_type": dita_type,
        "mode":     "scratch",
        "message":  f"Clean {dita_type} template ready. All content written by you.",
    }
