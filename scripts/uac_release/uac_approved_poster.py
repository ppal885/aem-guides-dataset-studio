#!/usr/bin/env python3
"""Copy QE-approved draft UACs into the Jira Acceptance Criteria field.

Runs on a schedule after uac_release_runner.py. For each ticket that has the
approval label and not the posted label:
  1. uses the exact text drafted by the runner (UAC.md hash must match the draft);
  2. refuses to overwrite a field that already holds different text, unless
     --overwrite is passed for that run;
  3. writes the field in Jira wiki format (bold labels, Source/TBD bullets);
  4. reads the rendered field back and checks the labels rendered as bold;
  5. swaps labels (draft -> posted) and leaves a short comment;
  6. when decision_comment is enabled and the approved draft carried a decision
     request (DECISIONS.md, unchanged since the draft), posts it once as its own
     comment, tagging the configured people.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def approved_jql(config: dict) -> str:
    labels = config["labels"]
    scope = config.get("approved_scope_jql") or config["jql"]
    return f'({scope}) AND labels = "{labels["approved"]}" AND labels != "{labels["posted"]}"'


def post_ticket(key: str, config: dict, jira, logger, overwrite: bool) -> str:
    ticket_dir = Path(config["output_dir"]) / key
    status = common.read_status(ticket_dir)
    uac = ticket_dir / common.UAC_FILE
    body_file = ticket_dir / "field-body.txt"
    if status.get("state") != "DRAFT_POSTED" or not uac.is_file() or not body_file.is_file():
        logger.error("%s: approved in Jira but no posted draft on this machine (state %s)", key, status.get("state"))
        return "NO_DRAFT"
    if common.sha256_file(uac) != status.get("uac_sha256"):
        logger.error("%s: UAC.md changed after the draft was posted; re-run the runner so QE reviews the new text", key)
        return "DRAFT_CHANGED"
    field = config["acceptance_criteria_field"]
    body = body_file.read_text(encoding="utf-8")
    current = (jira.get_field(key, field) or "").strip()
    if current and current != body.strip() and not overwrite:
        logger.error("%s: Acceptance Criteria field already has other text; not overwriting (use --overwrite)", key)
        return "FIELD_NOT_EMPTY"
    jira.set_field(key, field, body)
    rendered = jira.get_field(key, field, rendered=True) or ""
    if "<b>Acceptance Criteria 01:</b>" not in rendered:
        logger.error("%s: field written but did not render as expected; check it in Jira", key)
        return "RENDER_CHECK_FAILED"
    labels = config["labels"]
    jira.update_labels(key, add=[labels["posted"]], remove=[labels["draft"]])
    jira.add_comment(key, "*UAC posted:* the QE-approved draft is now in the Acceptance Criteria field.")
    status.update(state="POSTED")
    common.write_status(ticket_dir, status)
    logger.info("%s: posted to the Acceptance Criteria field", key)
    post_decision_request(key, config, jira, logger, ticket_dir, status)
    return "POSTED"


def post_decision_request(key: str, config: dict, jira, logger, ticket_dir: Path, status: dict) -> str:
    """Post the QE-approved decision request once; never blocks the AC post."""
    settings = config.get("decision_comment") or {}
    body_file = ticket_dir / common.DECISION_BODY_FILE
    decisions = ticket_dir / common.DECISIONS_FILE
    if not settings.get("enabled") or not body_file.is_file() or not decisions.is_file():
        return "NONE"
    if status.get("decision_comment_id"):
        return "ALREADY_POSTED"
    if common.sha256_file(decisions) != status.get("decisions_sha256"):
        logger.error("%s: DECISIONS.md changed after the draft; decision request not sent", key)
        return "DECISIONS_CHANGED"
    people = jira.get_people(key) if settings.get("mention") else {}
    names = [people.get(role, "") for role in settings.get("mention", [])] + list(settings.get("cc", []))
    names = list(dict.fromkeys(n for n in names if n))
    lead = " ".join(f"[~{name}]" for name in names)
    intro = "The UAC is in the Acceptance Criteria field. These product decisions are still open:"
    body = (f"{lead} {intro}" if lead else intro) + "\n\n" + body_file.read_text(encoding="utf-8")
    status["decision_comment_id"] = jira.add_comment(key, body)
    common.write_status(ticket_dir, status)
    logger.info("%s: decision request posted (comment %s)", key, status["decision_comment_id"])
    return "POSTED"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=common.REPO_ROOT / "backend" / ".env")
    parser.add_argument("--overwrite", action="store_true",
                        help="allow replacing a non-empty Acceptance Criteria field in this run")
    args = parser.parse_args(argv)

    common.load_env_file(args.env_file)
    config = common.load_config(args.config)
    logger = common.setup_logging(Path(config["output_dir"]) / "logs", "uac-poster")
    jira = common.JiraClient.from_env()
    with common.RunLock(Path(config["output_dir"]) / "poster.lock", int(config.get("lock_max_age_minutes", 720)) * 60):
        keys = jira.search_keys(approved_jql(config))
        logger.info("approved tickets: %s", ", ".join(keys) or "none")
        results = {key: post_ticket(key, config, jira, logger, args.overwrite) for key in keys}
    logger.info("summary: %s", results)
    return 0 if all(v == "POSTED" for v in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
