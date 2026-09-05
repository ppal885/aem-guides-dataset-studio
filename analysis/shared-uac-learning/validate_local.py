"""Reproducible local validation; temporary SQL/global installs, no VM traffic.

Run with the project's backend Python environment. Does not change real globals.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(__file__).resolve().parent
SOURCE = ROOT / ".codex/skills/test-plan-generation"
COPIES = [SOURCE, ROOT / ".claude/skills/test-plan-generation", ROOT / "skills/test-plan-generation",
    ROOT / "release-artifacts/aem-guides-mcp-client-unix/.claude/skills/test-plan-generation",
    ROOT / "release-artifacts/aem-guides-mcp-client-windows/.claude/skills/test-plan-generation"]
TESTS = [
    "test_test_plan_feedback_service.py", "test_test_plan_feedback_api.py", "test_test_plan_feedback_migration.py",
    "test_qe_pattern_mcp_service.py", "test_qe_pattern_mcp_interfaces.py", "test_pfix02_pattern_runtime_integration.py",
    "test_canonical_test_plan_runtime_contracts.py", "test_remote_mcp_gateway.py", "test_shared_uac_learning.py",
    "test_shared_uac_learning_identity.py", "test_shared_uac_learning_cross_client.py",
    "test_shared_uac_qe_authorization.py",
    "test_shared_learning_pattern_provider.py", "test_shared_learning_sql_runtime_integration.py",
    "test_shared_learning_shadow_replay.py",
    "test_shared_uac_learning_review_regressions.py",
    "test_shared_uac_learning_lineage_bounds.py",
    "test_auth_and_tenant_security.py", "test_test_plan_pipeline_service.py", "test_mcp_jira_dita_pipeline_service.py",
    "test_mcp_stdio_config.py", "test_remote_mcp_ask_tool_isolation.py",
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(label, args, cwd, env):
    started = time.monotonic()
    result = subprocess.run([sys.executable, *args], cwd=cwd, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    output = result.stdout + result.stderr
    (ARTIFACTS / f"{label}.txt").write_text(output, encoding="utf-8")
    print(f"{label}: exit {result.returncode}", flush=True)
    return {"label": label, "exit_code": result.returncode,
        "duration_seconds": round(time.monotonic() - started, 3), "log": f"{label}.txt",
        "log_sha256": hashlib.sha256(output.encode()).hexdigest(),
        "summary": [line for line in output.splitlines()
                    if re.search(r"\b\d+ (?:passed|failed)\b", line)
                    or line.startswith(("FAILED ", "FAIL:", "AssertionError:"))
                    or "ALL SELF-TESTS PASSED" in line][-12:]}


def main():
    actual_home = Path.home()
    report = {"scope": "ISOLATED_LOCAL_ONLY", "vm_deployed": False,
        "real_global_installations_changed": False, "python": sys.version,
        "runtime_base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "checks": [], "real_global_conflicts": {}, "copy_parity": {}}
    paths = [p for p in SOURCE.rglob("*") if p.is_file() and p.suffix in {".py", ".md", ".json", ".yaml", ".yml"}
             and "__pycache__" not in p.parts]
    for copy in COPIES[1:]:
        mismatches = [str(p.relative_to(SOURCE)).replace("\\", "/") for p in paths
            if not (copy / p.relative_to(SOURCE)).is_file() or sha(p) != sha(copy / p.relative_to(SOURCE))]
        report["copy_parity"][str(copy.relative_to(ROOT)).replace("\\", "/")] = mismatches
    for kind in (".codex", ".claude"):
        installed = actual_home / kind / "skills/test-plan-generation"
        report["real_global_conflicts"][str(installed)] = [str(p.relative_to(SOURCE)).replace("\\", "/")
            for p in paths if not (installed / p.relative_to(SOURCE)).is_file()
            or sha(p) != sha(installed / p.relative_to(SOURCE))]
    with tempfile.TemporaryDirectory(prefix="uac-learning-validation-") as temporary:
        sandbox = Path(temporary)
        for kind in (".codex", ".claude"):
            shutil.copytree(SOURCE, sandbox / kind / "skills/test-plan-generation",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        env = {**os.environ, "DATABASE_URL": "sqlite:///" + (sandbox / "tests.db").as_posix(),
            "PYTHONPATH": str(ROOT / "backend"), "USERPROFILE": str(sandbox),
            "AEM_GUIDES_TEST_PLAN_CANONICAL_ROOT": str(SOURCE), "AEM_STUDIO_REPO": str(ROOT),
            "LEARNED_QA_AUTO_SYNC_ON_STARTUP": "false", "CLEANUP_ENABLED": "false",
            "SHARED_UAC_LEARNING_MODE": "DISABLED", "SHARED_UAC_LEARNING_WORKER_ENABLED": "false",
            "SHARED_UAC_LEARNING_PROOF_PATH": str(ARTIFACTS / "local-learning-proof.json"),
            "PYTHONIOENCODING": "utf-8", "AEM_STUDIO_URL": "", "AEM_STUDIO_TOKEN": ""}
        report["checks"].append(run("backend-regression", ["-m", "pytest", *["tests/" + t for t in TESTS], "-q"], ROOT / "backend", env))
        for index, copy in enumerate(COPIES):
            report["checks"].append(run(f"skill-self-tests-{index + 1}", [str(copy / "scripts/test_skill_scripts.py")], ROOT, env))
        report["checks"].append(run("anti-hardcoding", [str(SOURCE / "scripts/audit_production_hardcoding.py")], ROOT, env))
        report["checks"].append(run("feedback-client-self-test", [str(SOURCE / "scripts/feedback_capture.py"), "--self-test"], ROOT, env))
    report["release_ready"] = False
    report["release_blockers"] = ["VM deployment/auth/migration/live proof not performed", "Real global copies have existing local changes; no overwrite",
        "Known baseline classification test failure must not be waived",
        "Eight pre-existing production-hardcoding findings in unchanged coverage_forcing.py"]
    (ARTIFACTS / "validation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if all(c["exit_code"] == 0 for c in report["checks"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
