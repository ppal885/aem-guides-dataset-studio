from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
PID_FILE = ROOT / "ui-live-pids.json"


def _open_log(name: str):
    return open(ROOT / name, "ab", buffering=0)


def _status(url: str) -> int | str:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return int(response.status)
    except Exception as exc:  # noqa: BLE001 - keeper diagnostics only
        return str(exc)


def _start_services() -> tuple[subprocess.Popen, subprocess.Popen]:
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    backend = subprocess.Popen(
        [str(PYTHON), "run_local.py"],
        cwd=ROOT / "backend",
        stdout=_open_log("backend-ui-left-running.out.log"),
        stderr=_open_log("backend-ui-left-running.err.log"),
        creationflags=flags,
        close_fds=False,
    )
    frontend = subprocess.Popen(
        [str(PYTHON), "tmp/frontend_proxy.py"],
        cwd=ROOT,
        stdout=_open_log("frontend-ui-left-running.out.log"),
        stderr=_open_log("frontend-ui-left-running.err.log"),
        creationflags=flags,
        close_fds=False,
    )
    return backend, frontend


def _terminate(process: subprocess.Popen) -> None:
    try:
        process.terminate()
    except Exception:
        pass


def _ready() -> bool:
    return _status("http://127.0.0.1:8001/health") == 200 and _status("http://127.0.0.1:5173/chat") == 200


def _write_state(backend: subprocess.Popen, frontend: subprocess.Popen, *, ready: bool, restarts: int) -> None:
    PID_FILE.write_text(
        json.dumps(
            {
                "keeper_pid": subprocess.os.getpid(),
                "backend_launcher_pid": backend.pid,
                "frontend_launcher_pid": frontend.pid,
                "ready": ready,
                "restarts": restarts,
                "backend_returncode": backend.poll(),
                "frontend_returncode": frontend.poll(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    restarts = 0
    backend, frontend = _start_services()
    ready = False
    for _ in range(60):
        time.sleep(1)
        ready = _ready()
        if ready:
            break
    _write_state(backend, frontend, ready=ready, restarts=restarts)
    while True:
        ready = _ready()
        if not ready:
            _terminate(backend)
            _terminate(frontend)
            time.sleep(2)
            restarts += 1
            backend, frontend = _start_services()
            for _ in range(30):
                time.sleep(1)
                ready = _ready()
                if ready:
                    break
            _write_state(backend, frontend, ready=ready, restarts=restarts)
        else:
            _write_state(backend, frontend, ready=True, restarts=restarts)
        time.sleep(10)


if __name__ == "__main__":
    main()
