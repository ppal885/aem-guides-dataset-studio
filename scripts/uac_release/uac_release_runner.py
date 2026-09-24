#!/usr/bin/env python3
"""Generate draft UACs for every release ticket with GitHub Copilot CLI.

One scheduled run:
  1. health checks: Jira auth, Dataset Studio MCP health URL, Copilot CLI present;
  2. finds tickets with the configured JQL;
  3. runs `copilot -p` once per ticket with the test-plan-generation skill, writing
     UAC.md and test-plan.md into <output_dir>/<KEY>/;
  4. checks the files (plan validator, AC count 1-10, blocked vocabulary);
  5. posts a draft comment with the plan attached and adds the draft label. When the
     UAC has TBDs, the draft also shows the decision request that the poster will send
     to the ticket after QE approval (DECISIONS.md).

Copilot never writes to Jira: its Jira write tools are denied in the config and
all Jira writes happen here, after the checks. The Acceptance Criteria field is
only filled later by uac_approved_poster.py, after QE adds the approval label.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

PROMPT = """Generate the UAC for Jira {key} using the test-plan-generation skill.
Follow the skill fully: live Jira, attachments, product and automation clones, the researcher
agents, and Experience League documentation. Do not write anything to Jira.
When finished, write these files:
1. {uac_path}: only the delivered UAC block - a flat list of "- Acceptance Criteria NN: ..." lines,
   each followed by an indented "**Source:** ..." line and, when a decision is open, a "**TBD:** ...?" line.
2. {plan_path}: the full eleven-section test plan record that passes scripts/validate_test_plan.py.
3. {decisions_path}: ONLY when the UAC has at least one TBD - a short decision request for the
   developer or product owner, in Markdown with exactly these three sections:
   "### What we found" (3-5 bullets of verified facts, each naming its source such as a doc page
   or code file), "### Decision needed" (a numbered list, one question per open TBD), and
   "### Impact on the Acceptance Criteria" (bullets saying which Acceptance Criteria each answer
   changes). No greeting, no names, no mentions. Do not write this file when there is no TBD.
Write in simple English with AEM Guides names a QE sees on screen."""
DECISION_SECTIONS = ("### What we found", "### Decision needed", "### Impact on the Acceptance Criteria")


def decision_problems(ticket_dir: Path) -> list[str]:
    """Warnings (never failures) about the optional decision request."""
    uac_text = (ticket_dir / common.UAC_FILE).read_text(encoding="utf-8")
    decisions = ticket_dir / common.DECISIONS_FILE
    has_tbd = bool(re.search(r"\*\*TBD:\*\*|^\s+TBD:", uac_text, re.MULTILINE))
    if not has_tbd:
        return []
    if not decisions.is_file():
        return ["the UAC has TBDs but DECISIONS.md was not written; no decision request will be sent"]
    text = decisions.read_text(encoding="utf-8")
    missing = [s for s in DECISION_SECTIONS if s not in text]
    return [f"DECISIONS.md is missing section(s): {', '.join(missing)}; no decision request will be sent"] if missing else []


def copilot_command(config: dict, prompt: str, transcript: Path) -> list[str]:
    cop = config.get("copilot", {})
    cmd = [cop.get("command", "copilot"), "-p", prompt, "-s", "--no-ask-user", f"--share={transcript}"]
    if cop.get("model"):
        cmd.append(f"--model={cop['model']}")
    if cop.get("agent"):
        cmd.append(f"--agent={cop['agent']}")
    for directory in cop.get("add_dirs", []):
        cmd.append(f"--add-dir={directory}")
    if cop.get("allow_all_tools"):
        cmd.append("--allow-all-tools")
    for tool in cop.get("allow_tools", []):
        cmd.append(f"--allow-tool={tool}")
    for tool in cop.get("deny_tools", []):
        cmd.append(f"--deny-tool={tool}")
    return cmd


def check_outputs(ticket_dir: Path) -> list[str]:
    """Return problems with the generated files; an empty list means ready to draft."""
    problems = []
    uac, plan = ticket_dir / common.UAC_FILE, ticket_dir / common.PLAN_FILE
    for path in (uac, plan):
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            problems.append(f"{path.name} was not written")
    if problems:
        return problems
    result = subprocess.run(
        [sys.executable, str(common.SKILL_SCRIPTS / "validate_test_plan.py"), str(plan)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        problems.append("test plan failed validate_test_plan.py: " + (result.stdout + result.stderr).strip()[-600:])
    text = uac.read_text(encoding="utf-8")
    count = len(re.findall(r"^- Acceptance Criteria \d+:", text, re.MULTILINE))
    if not 1 <= count <= 10:
        problems.append(f"UAC.md has {count} Acceptance Criteria (expected 1-10)")
    vocabulary = common.import_skill_module("guides_vocabulary")
    lines = "\n".join(f"- AC-{i:02d}: {m}" for i, m in enumerate(
        re.findall(r"^- Acceptance Criteria \d+:\s*(.+)$", text, re.MULTILINE), 1))
    blocked, _ = vocabulary.check(lines)
    problems.extend(f"vocabulary: {b}" for b in blocked)
    return problems


def draft_comment(field_body: str, plan_name: str, decision_body: str = "", mention_note: str = "") -> str:
    text = (
        "*Draft UAC ready for QE review* (generated automatically, not yet in the Acceptance Criteria field)\n"
        "* To approve, add the label *UAC_Approved*. The criteria below are then copied into the "
        "Acceptance Criteria field unchanged.\n"
        "* To request changes, add the label *UAC_Rework* and leave a comment.\n"
        f"* Full test plan: [^{plan_name}]\n\n" + field_body
    )
    if decision_body:
        text += (
            "\n\n----\n*Decision request* (posted as its own comment after approval"
            + (f", tagging {mention_note}" if mention_note else "")
            + "; edit it by asking for rework)\n\n" + decision_body
        )
    return text


def decision_mention_note(config: dict) -> str:
    settings = config.get("decision_comment") or {}
    if not settings.get("enabled"):
        return ""
    who = [f"the {role}" for role in settings.get("mention", [])] + [f"[~{u}]" for u in settings.get("cc", [])]
    return ", ".join(who)


def process_ticket(key: str, config: dict, jira, logger, dry_run: bool) -> str:
    out_root = Path(config["output_dir"])
    ticket_dir = out_root / key
    status = common.read_status(ticket_dir)
    if status.get("state") in {"DRAFT_POSTED", "POSTED"} and not config.get("regenerate_existing"):
        logger.info("%s: already %s, skipping", key, status["state"])
        return "SKIPPED"
    ticket_dir.mkdir(parents=True, exist_ok=True)
    for name in (common.UAC_FILE, common.PLAN_FILE, common.DECISIONS_FILE, common.DECISION_BODY_FILE):
        (ticket_dir / name).unlink(missing_ok=True)
    prompt = PROMPT.format(key=key, uac_path=ticket_dir / common.UAC_FILE, plan_path=ticket_dir / common.PLAN_FILE,
                           decisions_path=ticket_dir / common.DECISIONS_FILE)
    cmd = copilot_command(config, prompt, ticket_dir / "copilot-transcript.md")
    timeout = int(config.get("copilot", {}).get("timeout_minutes", 45)) * 60
    started = time.time()
    logger.info("%s: running Copilot CLI", key)
    try:
        run = subprocess.run(cmd, cwd=common.REPO_ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout)
        (ticket_dir / "copilot-output.txt").write_text(run.stdout + "\n" + run.stderr, encoding="utf-8")
        exit_code = run.returncode
    except subprocess.TimeoutExpired:
        exit_code = "timeout"
    status.update({"key": key, "copilot_exit": exit_code, "copilot_seconds": round(time.time() - started)})
    problems = check_outputs(ticket_dir) if exit_code == 0 else [f"Copilot CLI exit {exit_code}"]
    if problems:
        status.update(state="FAILED", problems=problems)
        common.write_status(ticket_dir, status)
        logger.error("%s: not drafted - %s", key, "; ".join(problems))
        return "FAILED"
    jira_text = common.import_skill_module("jira_safe_text")
    field_body = jira_text.jira_field_body((ticket_dir / common.UAC_FILE).read_text(encoding="utf-8"))
    (ticket_dir / "field-body.txt").write_text(field_body, encoding="utf-8")
    status.update(state="READY", problems=[], uac_sha256=common.sha256_file(ticket_dir / common.UAC_FILE))
    warnings = decision_problems(ticket_dir)
    decision_body = ""
    if not warnings and (ticket_dir / common.DECISIONS_FILE).is_file():
        decision_body = jira_text.jira_wiki_from_markdown(
            (ticket_dir / common.DECISIONS_FILE).read_text(encoding="utf-8"))
        (ticket_dir / common.DECISION_BODY_FILE).write_text(decision_body, encoding="utf-8")
        status["decisions_sha256"] = common.sha256_file(ticket_dir / common.DECISIONS_FILE)
    status["warnings"] = warnings
    for warning in warnings:
        logger.warning("%s: %s", key, warning)
    if dry_run:
        common.write_status(ticket_dir, status)
        logger.info("%s: ready (dry run, nothing posted)", key)
        return "READY"
    labels = config["labels"]
    plan_copy = ticket_dir / f"{key}-test-plan.md"
    shutil.copyfile(ticket_dir / common.PLAN_FILE, plan_copy)
    attachment_id = jira.attach_file(key, plan_copy)
    comment_id = jira.add_comment(key, draft_comment(field_body, plan_copy.name, decision_body,
                                                     decision_mention_note(config)))
    jira.update_labels(key, add=[labels["draft"]], remove=[labels.get("rework", "")] if labels.get("rework") else [])
    status.update(state="DRAFT_POSTED", comment_id=comment_id, attachment_id=attachment_id)
    common.write_status(ticket_dir, status)
    logger.info("%s: draft posted (comment %s)", key, comment_id)
    return "DRAFT_POSTED"


def health(config: dict, jira, logger) -> list[str]:
    problems = []
    try:
        me = jira.myself()
        logger.info("Jira auth OK as %s", me.get("name") or me.get("displayName"))
    except Exception as exc:  # noqa: BLE001 - report any auth/network failure the same way
        problems.append(f"Jira: {exc}")
    url = config.get("mcp_health_url")
    if url:
        ok, detail = common.check_url(url)
        (logger.info if ok else logger.error)("Dataset Studio MCP %s: %s", url, detail)
        if not ok:
            problems.append(f"Dataset Studio MCP unreachable ({detail}); documentation research would be skipped")
    if not shutil.which(config.get("copilot", {}).get("command", "copilot")):
        problems.append("Copilot CLI not found on PATH")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=common.REPO_ROOT / "backend" / ".env")
    parser.add_argument("--ticket", action="append", help="process only these keys (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="generate and check, but write nothing to Jira")
    args = parser.parse_args(argv)

    common.load_env_file(args.env_file)
    config = common.load_config(args.config)
    logger = common.setup_logging(Path(config["output_dir"]) / "logs", "uac-runner")
    jira = common.JiraClient.from_env()
    with common.RunLock(Path(config["output_dir"]) / "runner.lock", int(config.get("lock_max_age_minutes", 720)) * 60):
        problems = health(config, jira, logger)
        if problems:
            for p in problems:
                logger.error("health: %s", p)
            return 2
        keys = args.ticket or config.get("tickets") or jira.search_keys(config["jql"])
        logger.info("tickets: %s", ", ".join(keys) or "none")
        results = {key: process_ticket(key, config, jira, logger, args.dry_run) for key in keys}
    logger.info("summary: %s", results)
    return 1 if any(v == "FAILED" for v in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
