#!/usr/bin/env python3
"""Generate the skill's UAC for every ticket of a blind evaluation set, on the UAC VM.

Each ticket folder holds input.json (the ticket text from before a human wrote the UAC) and
human_uac.md (the human UAC). For every folder that has no skill_uac.md yet, this script runs
Copilot CLI with the test-plan-generation skill on input.json only and writes skill_uac.md next to it.

Blindness:
  - only input.json is copied into a per-ticket work folder under --work-dir; the blind set folder,
    with the human UACs, is never passed to Copilot (keep it outside the repo and outside add_dirs);
  - every Jira tool is denied (`--deny-tool=<server>` for each name in --jira-mcp), so the skill cannot
    read the ticket and its Acceptance Criteria from Jira;
  - after each run the transcript and draft are checked; a run that reads a path into the blind set, makes a
    Jira call that was not denied, or copies human wording is recorded as a leak in run.json and results.csv.
Product documentation (Dataset Studio MCP), code clones and the researcher agents stay available, as in the
nightly runner. Nothing is written to Jira.

Usage on the VM:
  python3 scripts/uac_eval/run_blind50.py --config /opt/uac-release/config.json \\
      --env-file /opt/uac-release/uac.env --set-dir /opt/uac-release/blind50
  # a rule change, kept beside the baseline as skill_uac_<tag>.md:
  python3 scripts/uac_eval/run_blind50.py ... --tag vm1 --only GUIDES-1 GUIDES-2
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "uac_release"))
import common  # noqa: E402
import uac_release_runner as runner  # noqa: E402

PROMPT = """Generate the UAC for the AEM Guides ticket {key} using the test-plan-generation skill.
This is a blind evaluation. The ticket text is ONLY in {input_path} (summary, type, components, fix versions,
description, comments and attachment names from before the UAC was written). Do not read the ticket, its
comments or its Acceptance Criteria from Jira or from any other file, and do not open any other folder named
blind50. Everything else the skill uses is allowed: product and automation clones, the researcher agents,
the Dataset Studio MCP (ask_dita_expert) and Experience League documentation.
Do not write anything to Jira. When finished, write this file:
{uac_rules}
"""


def uac_rules(uac_path: Path) -> str:
    """The nightly runner's rules for the delivered UAC block, so blind and nightly UACs share one format."""
    text = runner.PROMPT
    start = text.index("1. {uac_path}:")
    end = text.index("\n2. ", start)
    return text[start:end].replace("{uac_path}", str(uac_path)).replace("{{", "{").replace("}}", "}")


def build_command(config: dict, prompt: str, transcript: Path, work: Path, jira_servers: list[str]) -> list[str]:
    cmd = runner.copilot_command(config, prompt, transcript)
    cmd.append(f"--add-dir={work}")
    cmd += [f"--deny-tool={server}" for server in jira_servers]
    return cmd


def _phrases(text: str, size: int = 6) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(words[i:i + size]) for i in range(len(words) - size + 1)}


def leaks(transcript_text: str, prompt: str, key: str, jira_servers: list[str], ticket: Path | None = None,
          draft: str = "") -> list[str]:
    """Signs that a run saw the human UAC.

    Repository code names human_uac.md and the Jira server in plain text, so a mention alone is not a leak.
    A leak is: a path into the blind set (<set>/<KEY>/... or .../human_uac.md), a Jira tool call that was not
    denied, or a draft that copies human wording (four or more 6-word phrases, i.e. a 9-word run, from human_uac.md not in
    input.json).
    """
    text = transcript_text.replace(prompt, "")
    found = []
    if ticket is not None and (f"{ticket.parent}/{key}" in text or f"{ticket.parent}\\{key}" in text):
        found.append("transcript reads the blind set folder")
    if re.search(r"[/\\]human_uac\.md\b", text):
        found.append("transcript reads a human_uac.md path")
    for server in jira_servers:
        calls = re.findall(rf"^### `{re.escape(server)}[-_(.:][^`]*`(.*)$", text, re.M)
        if any("Failed" not in rest for rest in calls):
            found.append(f"transcript calls Jira tool {server}")
    if ticket is not None and draft and (ticket / "human_uac.md").is_file():
        human = _phrases((ticket / "human_uac.md").read_text(encoding="utf-8", errors="replace"))
        given = _phrases((ticket / "input.json").read_text(encoding="utf-8", errors="replace"))
        copied = (human & _phrases(draft)) - given
        if len(copied) >= 4:
            found.append(f"draft copies {len(copied)} phrases of the human UAC")
    return found


def run_ticket(ticket: Path, config: dict, work_root: Path, jira_servers: list[str], timeout: int,
               tag: str = "") -> dict:
    """Generate one blind draft. With a tag, files are named skill_uac_<tag>.md, run_<tag>.json, ... so
    the baseline run is kept for blind50_score.py --compare."""
    key = ticket.name
    sfx = f"_{tag}" if tag else ""
    work = work_root / key
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copyfile(ticket / "input.json", work / "input.json")
    uac = work / "skill_uac.md"
    transcript = work / "copilot-transcript.md"
    prompt = PROMPT.format(key=key, input_path=work / "input.json", uac_rules=uac_rules(uac))
    started = time.time()
    try:
        done = subprocess.run(build_command(config, prompt, transcript, work, jira_servers), cwd=common.REPO_ROOT,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        exit_code = done.returncode
        (work / "copilot-output.txt").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired:
        exit_code = "timeout"
    text = transcript.read_text(encoding="utf-8", errors="replace") if transcript.is_file() else ""
    draft = uac.read_text(encoding="utf-8") if uac.is_file() else ""
    record = {"key": key, "tag": tag, "exit": exit_code, "seconds": round(time.time() - started),
              "uac_written": bool(draft.strip()), "criteria": 0,
              "leaks": leaks(text, prompt, key, jira_servers, ticket, draft)}
    for name in ("skill_uac.md", "copilot-transcript.md", "copilot-output.txt"):
        if (work / name).is_file():
            stem, dot, ext = name.rpartition(".")
            shutil.copyfile(work / name, ticket / f"{stem}{sfx}{dot}{ext}")
    if record["uac_written"]:
        record["criteria"] = len(re.findall(r"^- Acceptance Criteria \d+:", draft, re.M))
    (ticket / f"run{sfx}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True, help="the nightly runner's config.json (Copilot settings)")
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--set-dir", type=Path, required=True, help="folder with <KEY>/input.json; keep it outside the repo")
    parser.add_argument("--work-dir", type=Path, default=Path("/tmp/blind50-work"))
    parser.add_argument("--jira-mcp", action="append", default=None,
                        help="name of a Jira MCP server in Copilot to deny (repeatable; default corp-jira)")
    parser.add_argument("--only", nargs="*", default=None, help="run only these keys")
    parser.add_argument("--redo", action="store_true", help="run again even when the draft exists")
    parser.add_argument("--tag", default="", help="write skill_uac_<tag>.md etc. (a rule change); keeps the baseline")
    parser.add_argument("--timeout-minutes", type=int, default=45)
    args = parser.parse_args(argv)
    if args.env_file:
        common.load_env_file(args.env_file)
    config = common.load_config(args.config)
    jira_servers = args.jira_mcp or ["corp-jira"]
    set_dir = args.set_dir.resolve()
    if common.REPO_ROOT in set_dir.parents or set_dir == common.REPO_ROOT:
        parser.error("keep --set-dir outside the repo, so Copilot cannot read the human UACs")
    if any(Path(d).resolve() in (set_dir, *set_dir.parents) for d in config.get("copilot", {}).get("add_dirs", [])):
        parser.error("--set-dir is inside a Copilot add_dir; move it so Copilot cannot read the human UACs")
    if not shutil.which(config.get("copilot", {}).get("command", "copilot")):
        parser.error("Copilot CLI not found on PATH")
    tickets = sorted(p for p in set_dir.iterdir() if (p / "input.json").is_file())
    if args.only:
        tickets = [p for p in tickets if p.name in set(args.only)]
    if args.tag and not re.fullmatch(r"[A-Za-z0-9]+", args.tag):
        parser.error("--tag must be letters and digits only")
    sfx = f"_{args.tag}" if args.tag else ""
    results = []
    for number, ticket in enumerate(tickets, 1):
        if (ticket / f"skill_uac{sfx}.md").is_file() and not args.redo:
            print(f"[{number}/{len(tickets)}] {ticket.name}: skill_uac{sfx}.md exists, skipped")
            continue
        print(f"[{number}/{len(tickets)}] {ticket.name}: running Copilot ...", flush=True)
        record = run_ticket(ticket, config, args.work_dir, jira_servers, args.timeout_minutes * 60, args.tag)
        print(f"    exit {record['exit']}, {record['seconds']} s, criteria {record['criteria']}"
              + (f", LEAK: {'; '.join(record['leaks'])}" if record["leaks"] else ""), flush=True)
        results.append(record)
    rows = [json.loads((p / f"run{sfx}.json").read_text()) for p in tickets if (p / f"run{sfx}.json").is_file()]
    with open(set_dir / f"results{sfx}.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "exit", "seconds", "uac_written", "criteria", "leaks"])
        for r in rows:
            writer.writerow([r["key"], r["exit"], r["seconds"], r["uac_written"], r["criteria"], "; ".join(r["leaks"])])
    written = sum(r["uac_written"] for r in rows)
    leaked = [r["key"] for r in rows if r["leaks"]]
    print(f"\n{written}/{len(tickets)} tickets have skill_uac{sfx}.md; results in {set_dir / f'results{sfx}.csv'}")
    if leaked:
        print("Possible leaks (exclude or re-run these): " + ", ".join(leaked))
    return 0 if written == len(tickets) and not leaked else 1


if __name__ == "__main__":
    raise SystemExit(main())
