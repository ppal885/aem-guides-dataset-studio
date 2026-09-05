"""Prereq-checking entry point for the UAC eval harness.

`judge_pipeline.py` produces meaningful numbers only when four things are true, and
three of them are not in a fresh clone. Running the raw script on a broken setup does
not fail loudly - it silently emits nulls or scores a plan against nothing, which is
worse than no number. This wrapper checks every prerequisite FIRST, prints exactly
what is missing and how to fix it, and refuses to run until the setup is sound.

Checks:
  1. corpus       - scripts/uac_eval/corpus.jsonl exists with scorable rows
                    (gitignored; must be copied in - it is not in a fresh clone).
  2. judge model  - Azure OpenAI creds in backend/.env (endpoint/key/version/model).
  3. runtime      - the VM canonical runtime answers at --vm (corp network / VPN).
  4. deps         - openai, requests, python-dotenv importable.

Usage:
  python scripts/uac_eval/run.py --check-only          # just report readiness
  python scripts/uac_eval/run.py --n 30 --seed 5       # check, then run the eval
  (any judge_pipeline.py flag is accepted and passed through)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DEFAULT_VM = "http://10.42.46.78:4502"

GREEN, RED, YEL, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def _ok(msg: str) -> None:
    print(f"  {GREEN}OK{OFF}   {msg}")


def _fail(msg: str, fix: str) -> None:
    print(f"  {RED}MISS{OFF} {msg}\n         fix: {fix}")


def check_deps() -> bool:
    missing = []
    for mod in ("openai", "requests", "dotenv"):
        try:
            __import__(mod)
        except ImportError:
            missing.append("python-dotenv" if mod == "dotenv" else mod)
    if missing:
        _fail(f"python deps missing: {', '.join(missing)}",
              f"pip install {' '.join(missing)}  (or use the backend venv)")
        return False
    _ok("python deps (openai, requests, python-dotenv)")
    return True


def check_corpus() -> bool:
    import json
    path = HERE / "corpus.jsonl"
    if not path.exists():
        _fail("corpus.jsonl not found (it is gitignored - not in a fresh clone)",
              "copy scripts/uac_eval/corpus.jsonl from the VM or a teammate into this path")
        return False
    try:
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception as exc:  # noqa: BLE001
        _fail(f"corpus.jsonl unreadable: {exc}", "re-copy a clean corpus.jsonl")
        return False
    scorable = [r for r in rows
                if len((r.get("description") or "").strip()) > 120
                and len((r.get("human_ac") or "").strip()) > 60]
    if not scorable:
        _fail(f"corpus.jsonl has {len(rows)} rows but 0 are scorable (need description + human_ac)",
              "verify the corpus was built with build_corpus.py / harvest.py")
        return False
    _ok(f"corpus.jsonl ({len(rows)} rows, {len(scorable)} scorable)")
    return True


def check_judge() -> bool:
    import os
    from dotenv import load_dotenv
    load_dotenv(str(REPO / "backend" / ".env"))
    need = {
        "AZURE_OPENAI_API_KEY": "the Azure OpenAI key",
        "AZURE_OPENAI_ENDPOINT": "the Azure endpoint URL",
        "AZURE_OPENAI_API_VERSION": "the API version",
        "AZURE_OPENAI_MODEL": "the deployment/model name (e.g. gpt-5.2)",
    }
    missing = [k for k in need if not os.getenv(k)]
    if missing:
        _fail(f"judge creds missing in backend/.env: {', '.join(missing)}",
              "set " + ", ".join(f"{k}=<{need[k]}>" for k in missing) + " in backend/.env")
        return False
    _ok(f"judge model creds ({os.getenv('AZURE_OPENAI_MODEL')} @ Azure OpenAI)")
    return True


def check_runtime(vm: str) -> bool:
    import requests
    try:
        r = requests.get(vm.rstrip("/") + "/", timeout=8, verify=False)
        if r.status_code < 500:
            _ok(f"VM canonical runtime reachable at {vm} (HTTP {r.status_code})")
            return True
        _fail(f"VM at {vm} answered HTTP {r.status_code}",
              "check the backend service is up (systemctl status) and the port is right")
        return False
    except Exception as exc:  # noqa: BLE001
        _fail(f"VM at {vm} not reachable: {type(exc).__name__}",
              "connect to the corp network / VPN, or pass --vm <reachable-url>")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, add_help=True)
    ap.add_argument("--vm", default=DEFAULT_VM)
    ap.add_argument("--check-only", action="store_true",
                    help="report readiness and exit without running the eval")
    # everything else is passed straight through to judge_pipeline.py
    args, passthrough = ap.parse_known_args()

    print("UAC eval prerequisite check")
    print("-" * 40)
    results = [
        check_deps(),
        check_corpus(),
        check_judge(),
        check_runtime(args.vm),
    ]
    print("-" * 40)
    if not all(results):
        n = sum(1 for r in results if not r)
        print(f"{RED}NOT READY{OFF}: {n} prerequisite(s) missing. Fix the item(s) above, then re-run.")
        print("Nothing was scored (a broken setup produces meaningless numbers, so the eval was not run).")
        return 2
    print(f"{GREEN}READY{OFF}: all prerequisites satisfied.")
    if args.check_only:
        print("(--check-only) not running the eval.")
        return 0

    # Hand off to judge_pipeline.py with the same --vm and any passthrough flags.
    print("\nStarting judge_pipeline.py ...\n")
    sys.argv = [str(HERE / "judge_pipeline.py"), "--vm", args.vm, *passthrough]
    import judge_pipeline  # noqa: E402  (import here so a dep failure is caught above first)
    return judge_pipeline.main()


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    try:
        import urllib3
        urllib3.disable_warnings()  # silence the verify=False InsecureRequestWarning noise
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
