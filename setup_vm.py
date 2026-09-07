#!/usr/bin/env python3
"""Install the UAC backend and dashboard-only Nginx site on a Linux VM.

Run the complete setup as root with ``python3 setup_vm.py``. Docker-based
deployments can refresh only Nginx and the static dashboard with
``python3 setup_vm.py --dashboard-only``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
DASHBOARD_DIR = ROOT / "scripts" / "uac_eval"
AGGREGATOR = DASHBOARD_DIR / "aggregate_runs.py"
DASHBOARD_HTML = DASHBOARD_DIR / "dashboard.html"
DASHBOARD_SNAPSHOT = DASHBOARD_DIR / "dashboard_data.json"
WEB_ROOT = Path("/var/www/aem-studio")
NGINX_SITE = Path("/etc/nginx/sites-available/aem-studio")
NGINX_ENABLED_DEFAULT = Path("/etc/nginx/sites-enabled/default")
NGINX_ENABLED_DUPLICATE = Path("/etc/nginx/sites-enabled/aem-studio")
MINIMUM_PYTHON_VERSION = (3, 11, 0)
SYSTEM_PYTHON_CANDIDATES = (
    "python3.11",
    "python3.12",
    "python3.13",
    "python3.14",
    "python3",
    "python",
)


NGINX_CONF = r"""server {
    listen 4502;
    server_name _;
    absolute_redirect off;
    root /var/www/aem-studio;
    index index.html;

    location = /eval-dashboard {
        return 308 /;
    }

    location = /eval-dashboard/ {
        return 308 /;
    }

    location = /health {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }

    location = /api {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_connect_timeout 75s;
    }

    location ^~ /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_connect_timeout 75s;
    }

    location = /mcp {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_request_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_connect_timeout 75s;
        gzip off;
        chunked_transfer_encoding on;
    }

    location ^~ /mcp/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_request_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_connect_timeout 75s;
        gzip off;
        chunked_transfer_encoding on;
    }

    location = / {
        limit_except GET HEAD { deny all; }
        try_files /index.html =404;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com 'sha256-CLP9y1ElrCwWiqoltxsf8iKvKo5NZ08yIG9+K5kZNiQ='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" always;
        add_header Referrer-Policy "no-referrer" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
    }

    location = /index.html {
        limit_except GET HEAD { deny all; }
        try_files $uri =404;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com 'sha256-CLP9y1ElrCwWiqoltxsf8iKvKo5NZ08yIG9+K5kZNiQ='; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" always;
        add_header Referrer-Policy "no-referrer" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
    }

    location = /dashboard_data.json {
        limit_except GET HEAD { deny all; }
        try_files $uri =404;
        default_type application/json;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" always;
        add_header Referrer-Policy "no-referrer" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
    }

    location / {
        return 404;
    }
}
"""


def run(
    command: Sequence[os.PathLike[str] | str],
    *,
    check: bool = True,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a fixed argument vector without invoking a shell."""
    argv = [os.fspath(part) for part in command]
    print(f"  $ {shlex.join(argv)}")
    return subprocess.run(
        argv,
        cwd=os.fspath(cwd or ROOT),
        env=env,
        check=check,
        capture_output=capture_output,
        text=True,
    )


def require_root() -> None:
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise SystemExit("Run setup_vm.py as root so it can update Nginx and systemd.")


def probe_python_version(
    executable: os.PathLike[str] | str,
) -> tuple[int, int, int] | None:
    """Return an interpreter version, or ``None`` when it cannot be trusted."""
    try:
        result = run(
            [
                executable,
                "-c",
                "import sys; print('.'.join(str(v) for v in sys.version_info[:3]))",
            ],
            check=False,
            capture_output=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", result.stdout.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def python_version_supported(version: tuple[int, int, int] | None) -> bool:
    return version is not None and version >= MINIMUM_PYTHON_VERSION


def supported_system_pythons(
    candidates: Sequence[str] = SYSTEM_PYTHON_CANDIDATES,
    *,
    locator: Callable[[str], str | None] = shutil.which,
    probe: Callable[[os.PathLike[str] | str], tuple[int, int, int] | None] = probe_python_version,
) -> tuple[Path, ...]:
    """Resolve installed Python 3.11+ interpreters in deterministic preference order."""
    supported: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        located = locator(candidate)
        if not located:
            continue
        normalized = os.path.normcase(os.path.abspath(located))
        if normalized in seen:
            continue
        seen.add(normalized)
        path = Path(located)
        if python_version_supported(probe(path)):
            supported.append(path)
    return tuple(supported)


def select_backend_venv(
    backend_dir: Path = BACKEND_DIR,
    *,
    probe: Callable[[os.PathLike[str] | str], tuple[int, int, int] | None] = probe_python_version,
) -> Path:
    """Choose the fixed managed venv without altering an incompatible environment."""
    managed = backend_dir / "venv"
    alternate = backend_dir / ".venv"

    if managed.exists():
        managed_python = managed / "bin" / "python"
        version = probe(managed_python)
        if not python_version_supported(version):
            description = ".".join(str(part) for part in version) if version else "unreadable"
            raise RuntimeError(
                f"Managed backend virtual environment {managed} uses Python {description}; "
                "Python 3.11+ is required. The directory was left untouched. Move it aside "
                "after review and rerun setup_vm.py to create a compatible environment."
            )
        return managed

    if alternate.exists():
        alternate_python = alternate / "bin" / "python"
        version = probe(alternate_python)
        if python_version_supported(version):
            print(f"  Reusing compatible backend virtual environment: {alternate}")
            return alternate
        description = ".".join(str(part) for part in version) if version else "unreadable"
        print(
            f"  Existing alternate virtual environment {alternate} uses Python {description}; "
            f"leaving it untouched and creating {managed} instead"
        )

    return managed


def write_atomic(path: Path, content: str, mode: int = 0o644) -> None:
    """Atomically replace one fixed configuration file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def dashboard_inline_script_hashes() -> tuple[str, ...]:
    """Return CSP sha256 tokens for each inline script in the shipped dashboard."""
    try:
        document = DASHBOARD_HTML.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Cannot read dashboard HTML for CSP validation: {exc}") from exc
    scripts = re.findall(
        r"<script(?P<attributes>[^>]*)>(?P<body>.*?)</script\s*>",
        document,
        flags=re.IGNORECASE | re.DOTALL,
    )
    inline_bodies = [
        body
        for attributes, body in scripts
        if not re.search(r"\bsrc\s*=", attributes, flags=re.IGNORECASE)
    ]
    if not inline_bodies:
        raise RuntimeError("Dashboard HTML contains no inline script to validate")
    return tuple(
        "sha256-"
        + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii")
        for body in inline_bodies
    )


def validate_nginx_contract() -> None:
    """Fail before installation if the dashboard-only routing contract drifts."""
    required_fragments = (
        "listen 4502;",
        "absolute_redirect off;",
        "location = /eval-dashboard {",
        "location = /eval-dashboard/ {",
        "location = /health {",
        "location = /api {",
        "location ^~ /api/ {",
        "location = /mcp {",
        "location ^~ /mcp/ {",
        "location = / {",
        "location = /index.html {",
        "location = /dashboard_data.json {",
        'add_header Cache-Control "no-store, no-cache, must-revalidate" always;',
        "location / {\n        return 404;",
    )
    missing = [fragment for fragment in required_fragments if fragment not in NGINX_CONF]
    if missing:
        raise RuntimeError(f"Nginx dashboard contract is incomplete: {missing}")
    if NGINX_CONF.count("return 308 /;") != 2:
        raise RuntimeError("Both compatibility URLs must return an exact 308 redirect")
    if NGINX_CONF.count("proxy_pass http://127.0.0.1:8001;") != 5:
        raise RuntimeError("API, MCP, and health proxy locations must target localhost:8001")
    if NGINX_CONF.count('add_header Cache-Control "no-store, no-cache, must-revalidate" always;') != 3:
        raise RuntimeError("Root HTML, index HTML, and dashboard JSON must disable caching")
    if NGINX_CONF.count("frame-ancestors 'none'") != 3:
        raise RuntimeError("Every dashboard response location must deny framing")
    mismatched_script_hashes = [
        digest for digest in dashboard_inline_script_hashes() if NGINX_CONF.count(digest) != 2
    ]
    if mismatched_script_hashes:
        raise RuntimeError(
            "Root and index CSP must both authorize the dashboard's current inline scripts: "
            f"{mismatched_script_hashes}"
        )
    if "try_files $uri $uri/ /index.html" in NGINX_CONF:
        raise RuntimeError("SPA fallback is forbidden in dashboard-only mode")


def install_nginx_config() -> None:
    print("  Installing dashboard-only Nginx configuration")
    validate_nginx_contract()
    write_atomic(NGINX_SITE, NGINX_CONF)
    NGINX_ENABLED_DEFAULT.parent.mkdir(parents=True, exist_ok=True)
    if NGINX_ENABLED_DEFAULT.is_dir() and not NGINX_ENABLED_DEFAULT.is_symlink():
        raise RuntimeError(f"Refusing to replace directory: {NGINX_ENABLED_DEFAULT}")
    NGINX_ENABLED_DEFAULT.unlink(missing_ok=True)
    NGINX_ENABLED_DEFAULT.symlink_to(NGINX_SITE)
    if NGINX_ENABLED_DUPLICATE != NGINX_ENABLED_DEFAULT:
        if NGINX_ENABLED_DUPLICATE.is_dir() and not NGINX_ENABLED_DUPLICATE.is_symlink():
            raise RuntimeError(f"Refusing to remove directory: {NGINX_ENABLED_DUPLICATE}")
        NGINX_ENABLED_DUPLICATE.unlink(missing_ok=True)
    run(["nginx", "-t"])


def _validate_fixed_web_root(path: Path) -> None:
    if path != Path("/var/www/aem-studio") or path.parent != Path("/var/www"):
        raise RuntimeError(f"Refusing unsafe dashboard target: {path}")
    if path.name != "aem-studio":
        raise RuntimeError(f"Refusing unexpected dashboard target: {path}")


def _remove_known_temporary(path: Path, prefix: str) -> None:
    expected_parent = Path("/var/www")
    if path.parent != expected_parent or not path.name.startswith(prefix):
        raise RuntimeError(f"Refusing unsafe cleanup target: {path}")
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _dashboard_run_ids(payload: object, *, label: str) -> set[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
        raise RuntimeError(f"{label} dashboard data must contain a runs list")
    run_ids: list[str] = []
    for row in payload["runs"]:
        if not isinstance(row, dict) or not isinstance(row.get("run_id"), str):
            raise RuntimeError(f"{label} dashboard data has a run without a string run_id")
        run_ids.append(row["run_id"])
    if len(run_ids) != len(set(run_ids)):
        raise RuntimeError(f"{label} dashboard data contains duplicate run IDs")
    return set(run_ids)


def aggregate_dashboard_data() -> tuple[bytes, bytes]:
    """Build dashboard artifacts in an isolated directory.

    ``aggregate_runs.py`` intentionally writes beside its own file. Running the
    checked-in copy would therefore dirty the repository and make the generated
    timestamp depend on any prior checkout artifact. Copying the immutable
    inputs with ``copy2`` preserves each run's source mtime while containing the
    generated JSON in a temporary directory.
    """
    for required in (AGGREGATOR, DASHBOARD_HTML):
        if not required.is_file():
            raise FileNotFoundError(f"Required dashboard source is missing: {required}")

    with tempfile.TemporaryDirectory(prefix="aem-dashboard-aggregate-") as temporary:
        workspace = Path(temporary)
        isolated_aggregator = workspace / AGGREGATOR.name
        isolated_html = workspace / "index.html"
        isolated_data = workspace / "dashboard_data.json"
        shutil.copy2(AGGREGATOR, isolated_aggregator)
        shutil.copy2(DASHBOARD_HTML, isolated_html)
        for source in sorted(DASHBOARD_DIR.glob("judge_pipeline*.json")):
            if source.is_file():
                shutil.copy2(source, workspace / source.name)

        run([sys.executable, isolated_aggregator], cwd=workspace)
        try:
            payload = json.loads(isolated_data.read_text(encoding="utf-8"))
            html_bytes = isolated_html.read_bytes()
            data_bytes = isolated_data.read_bytes()
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Generated dashboard bundle is invalid: {exc}") from exc
        generated_ids = _dashboard_run_ids(payload, label="Generated")

        if DASHBOARD_SNAPSHOT.is_file():
            try:
                snapshot = json.loads(DASHBOARD_SNAPSHOT.read_text(encoding="utf-8"))
                snapshot_bytes = DASHBOARD_SNAPSHOT.read_bytes()
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Checked-in dashboard snapshot is invalid: {exc}") from exc
            snapshot_ids = _dashboard_run_ids(snapshot, label="Checked-in")
            if generated_ids < snapshot_ids:
                print(
                    "  WARNING: available judge_pipeline inputs are a strict subset of "
                    "the checked-in dashboard history; retaining the checked-in snapshot "
                    f"({len(snapshot_ids)} runs instead of {len(generated_ids)})."
                )
                data_bytes = snapshot_bytes
            elif missing_ids := snapshot_ids - generated_ids:
                raise RuntimeError(
                    "Isolated aggregation would drop checked-in dashboard history while "
                    f"also changing the run set; missing IDs: {sorted(missing_ids)}"
                )
        return html_bytes, data_bytes


def deploy_dashboard(html_bytes: bytes, data_bytes: bytes) -> None:
    """Stage two dashboard files and swap the fixed web root with rollback."""
    _validate_fixed_web_root(WEB_ROOT)
    WEB_ROOT.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".aem-studio-stage-", dir=WEB_ROOT.parent))
    backup_holder = Path(tempfile.mkdtemp(prefix=".aem-studio-backup-", dir=WEB_ROOT.parent))
    backup_holder.rmdir()
    backup = backup_holder
    moved_existing = False
    try:
        (stage / "index.html").write_bytes(html_bytes)
        (stage / "dashboard_data.json").write_bytes(data_bytes)
        stage.chmod(0o755)
        for deployed_file in stage.iterdir():
            deployed_file.chmod(0o644)

        if {item.name for item in stage.iterdir()} != {"index.html", "dashboard_data.json"}:
            raise RuntimeError("Dashboard stage contains unexpected files")

        if WEB_ROOT.exists() or WEB_ROOT.is_symlink():
            os.replace(WEB_ROOT, backup)
            moved_existing = True
        try:
            os.replace(stage, WEB_ROOT)
        except Exception:
            if moved_existing and not WEB_ROOT.exists():
                os.replace(backup, WEB_ROOT)
                moved_existing = False
            raise
        if moved_existing:
            _remove_known_temporary(backup, ".aem-studio-backup-")
            moved_existing = False
    finally:
        if stage.exists() or stage.is_symlink():
            _remove_known_temporary(stage, ".aem-studio-stage-")
        if backup.exists() or backup.is_symlink():
            if not WEB_ROOT.exists() and moved_existing:
                os.replace(backup, WEB_ROOT)
            else:
                _remove_known_temporary(backup, ".aem-studio-backup-")


def activate_nginx() -> None:
    run(["nginx", "-t"])
    run(["systemctl", "enable", "--now", "nginx"])
    run(["systemctl", "reload", "nginx"])


def install_backend_service() -> tuple[Path, Path]:
    env_file = ROOT / ".env.docker"
    venv = select_backend_venv()
    uvicorn = venv / "bin" / "uvicorn"
    service = f"""[Unit]
Description=AEM Guides Dataset Studio Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={BACKEND_DIR}
EnvironmentFile={env_file}
Environment=PORT=8001
ExecStart={uvicorn} app.main:app --host 127.0.0.1 --port 8001 --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    write_atomic(Path("/etc/systemd/system/aem-backend.service"), service)
    run(["systemctl", "daemon-reload"])
    return venv, uvicorn


def install_backend_dependencies(venv: Path, uvicorn: Path) -> None:
    venv_python = venv / "bin" / "python"
    if venv.exists() and not python_version_supported(probe_python_version(venv_python)):
        raise RuntimeError(
            f"Backend virtual environment {venv} is not runnable with Python 3.11+. "
            "It was left untouched; move it aside after review and rerun setup_vm.py."
        )
    if uvicorn.exists():
        print("  Compatible backend venv already exists; dependency install skipped")
        return

    if not venv.exists():
        print("  Backend venv not found; creating a Python 3.11+ environment")
        interpreters = supported_system_pythons()
        if not interpreters:
            raise RuntimeError(
                "No compatible system interpreter found. Install Python 3.11+ with its "
                "venv package, then rerun setup_vm.py."
            )
        creation_errors: list[str] = []
        for interpreter in interpreters:
            result = run([interpreter, "-m", "venv", venv], check=False)
            if result.returncode == 0 and python_version_supported(
                probe_python_version(venv_python)
            ):
                break
            creation_errors.append(f"{interpreter} (exit {result.returncode})")
        else:
            raise RuntimeError(
                "Could not create a Python 3.11+ backend virtual environment using: "
                + ", ".join(creation_errors)
                + ". Any partial directory was left untouched for review."
            )

    install_env = dict(os.environ)
    install_env["TMPDIR"] = "/var/tmp"
    run([venv_python, "-m", "pip", "install", "--upgrade", "pip"], env=install_env)
    run(
        [
            venv_python,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--timeout",
            "300",
            "-r",
            BACKEND_DIR / "requirements.txt",
        ],
        env=install_env,
    )


def start_backend() -> None:
    run(["systemctl", "enable", "aem-backend"])
    run(["systemctl", "restart", "aem-backend"])
    print("  Waiting for backend health")
    for _ in range(30):
        result = run(
            ["curl", "-sf", "http://127.0.0.1:8001/health"],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            print(f"  Backend healthy: {result.stdout[:100]}")
            return
        time.sleep(1)
    raise RuntimeError("Backend health check failed; inspect: journalctl -u aem-backend -n 30")


def dashboard_only_setup() -> None:
    print("\n[1/2] Configuring Nginx...")
    install_nginx_config()
    print("\n[2/2] Aggregating and deploying dashboard...")
    deploy_dashboard(*aggregate_dashboard_data())
    activate_nginx()


def full_setup() -> None:
    print("\n[1/5] Configuring Nginx...")
    install_nginx_config()
    print("\n[2/5] Creating backend systemd service...")
    venv, uvicorn = install_backend_service()
    print("\n[3/5] Checking backend Python dependencies...")
    install_backend_dependencies(venv, uvicorn)
    print("\n[4/5] Starting backend service...")
    start_backend()
    print("\n[5/5] Aggregating and deploying dashboard...")
    deploy_dashboard(*aggregate_dashboard_data())
    activate_nginx()


def run_self_tests() -> None:
    """Exercise Python-selection contracts without changing system state."""
    assert not python_version_supported((3, 10, 99))
    assert python_version_supported((3, 11, 0))
    assert python_version_supported((3, 14, 1))
    assert probe_python_version(sys.executable) == tuple(sys.version_info[:3])

    locations = {
        "old-python": os.fspath(Path("/fake/python-3.10")),
        "new-python": os.fspath(Path("/fake/python-3.11")),
        "new-python-alias": os.fspath(Path("/fake/python-3.11")),
    }
    versions = {
        locations["old-python"]: (3, 10, 12),
        locations["new-python"]: (3, 11, 0),
    }
    selected = supported_system_pythons(
        tuple(locations),
        locator=locations.get,
        probe=lambda executable: versions.get(os.fspath(executable)),
    )
    assert selected == (Path(locations["new-python"]),)

    with tempfile.TemporaryDirectory(prefix="setup-vm-python-contract-") as temporary:
        backend_dir = Path(temporary)
        managed_python = backend_dir / "venv" / "bin" / "python"
        managed_python.parent.mkdir(parents=True)
        managed_python.touch()
        try:
            select_backend_venv(
                backend_dir,
                probe=lambda _executable: (3, 10, 12),
            )
        except RuntimeError as exc:
            assert "left untouched" in str(exc)
        else:
            raise AssertionError("An incompatible managed venv must fail closed")
        assert managed_python.exists()

    with tempfile.TemporaryDirectory(prefix="setup-vm-python-contract-") as temporary:
        backend_dir = Path(temporary)
        alternate_python = backend_dir / ".venv" / "bin" / "python"
        alternate_python.parent.mkdir(parents=True)
        alternate_python.touch()
        selected_venv = select_backend_venv(
            backend_dir,
            probe=lambda _executable: (3, 11, 0),
        )
        assert selected_venv == backend_dir / ".venv"

    print("setup_vm self-tests: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run installer contract tests without changing Nginx or systemd",
    )
    parser.add_argument(
        "--dashboard-only",
        action="store_true",
        help="refresh Nginx configuration and static dashboard without changing systemd",
    )
    args = parser.parse_args()
    if args.self_test:
        run_self_tests()
        return 0
    require_root()
    if args.dashboard_only:
        dashboard_only_setup()
    else:
        full_setup()

    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        ip = "your-vm-ip"
    print(
        f"""
============================================================
  AEM Guides UAC dashboard is running

  Dashboard:       http://{ip}:4502/
  Backend health:  http://{ip}:4502/health
  API gateway:     http://{ip}:4502/api/
  MCP gateway:     http://{ip}:4502/mcp

  Backend logs:    journalctl -u aem-backend -f
  Backend restart: systemctl restart aem-backend
============================================================
"""
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
