"""Compatibility entry point for the retired local UI proxy.

The implementation is intentionally a thin wrapper around the canonical Windows
dashboard/backend launcher. It does not serve files or proxy requests itself.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = REPO_ROOT / "RUN_LOCAL_DEV.ps1"


def main() -> int:
    if not LAUNCHER.is_file() or LAUNCHER.parent != REPO_ROOT:
        print(f"Canonical launcher not found: {LAUNCHER}", file=sys.stderr)
        return 1

    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        print("PowerShell was not found; run RUN_LOCAL_DEV.ps1 directly.", file=sys.stderr)
        return 1

    print(
        "This legacy command now starts the dashboard-only UAC runtime. "
        "Use RUN_LOCAL_DEV.ps1 for new workflows.",
        file=sys.stderr,
    )
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LAUNCHER),
            *sys.argv[1:],
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
