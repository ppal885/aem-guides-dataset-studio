"""Read-only repository checks; writes only the local implementation safety report."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(__file__).resolve().parent
ORIGINAL = Path("C:/Users/prashantp/Videos/aem-guides-dataset-studio")


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True, encoding="utf-8").strip()


def main():
    before = json.loads((ARTIFACTS / "original-checkout-safety.json").read_text(encoding="utf-8"))
    dirty_checks = [{"path": row["path"], "unchanged": hashlib.sha256(
        (ORIGINAL / row["path"]).read_bytes()).hexdigest() == row["sha256"]}
        for row in before["tracked_dirty_files"]]
    protected = ["scripts/uac_eval", "scripts/run_test_plan_pipeline.py", "backend/storage",
        "backend/data", "ui_harvester", "incoming_archives", "frontend"]
    protected_diff = git("diff", "--name-only", "--", *protected).splitlines()
    report = {"original_head": git("rev-parse", "HEAD", cwd=ORIGINAL),
        "original_head_unchanged": git("rev-parse", "HEAD", cwd=ORIGINAL) == before["head"],
        "original_dirty_file_checks": dirty_checks, "protected_tracked_changes": protected_diff,
        "staged_files": git("diff", "--cached", "--name-only").splitlines(),
        "implementation_branch": git("branch", "--show-current"),
        "implementation_base": git("rev-parse", "HEAD"),
        "vm_changed": False, "global_installs_changed": False}
    report["passed"] = (report["original_head_unchanged"] and all(row["unchanged"] for row in dirty_checks)
        and not protected_diff and not report["staged_files"])
    (ARTIFACTS / "safety-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Safety checks: " + ("PASS" if report["passed"] else "FAIL"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
