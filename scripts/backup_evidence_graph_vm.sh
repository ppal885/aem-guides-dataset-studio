#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PYTHON_BIN="${PYTHON_BIN:-$BACKEND_DIR/.venv/bin/python}"
SERVICE_NAME="${AEM_BACKEND_SERVICE:-aem-backend.service}"
MANAGE_SERVICE=false
OUTPUT_DIR=""

usage() {
  cat >&2 <<'EOF'
Usage: bash scripts/backup_evidence_graph_vm.sh [--manage-service] [--output /absolute/backup/directory]

Creates a consistent SQLite backup and a compressed ChromaDB snapshot. If the
backend is running, pass --manage-service so the script stops it for the
snapshot and always attempts to restart it before exiting.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manage-service)
      MANAGE_SERVICE=true
      shift
      ;;
    --output)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      OUTPUT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi
if ! command -v tar >/dev/null 2>&1 || ! command -v sha256sum >/dev/null 2>&1; then
  echo "ERROR: tar and sha256sum are required." >&2
  exit 1
fi

if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="/root/rag-backups/evidence-graph-$(date -u +%Y%m%d-%H%M%S)"
fi
if [[ "$OUTPUT_DIR" != /* ]]; then
  echo "ERROR: --output must be an absolute path." >&2
  exit 2
fi
if [[ -e "$OUTPUT_DIR" ]]; then
  echo "ERROR: backup destination already exists: $OUTPUT_DIR" >&2
  exit 1
fi

mapfile -t STORAGE_PATHS < <(
  ROOT_DIR="$ROOT_DIR" BACKEND_DIR="$BACKEND_DIR" PYTHONPATH="$BACKEND_DIR" "$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

root = Path(os.environ["ROOT_DIR"]).resolve()
backend = Path(os.environ["BACKEND_DIR"]).resolve()

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    for env_path in (root / ".env", backend / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=True, encoding="utf-8-sig")

from app.db.session import engine

if engine.dialect.name != "sqlite":
    raise SystemExit("ERROR: backup helper supports SQLite only; use the database-native backup tool for DATABASE_URL.")

database_value = str(engine.url.database or "").strip()
if database_value == ":memory:":
    raise SystemExit("ERROR: an in-memory SQLite database cannot be backed up.")
if not database_value:
    raise SystemExit("ERROR: the running application SQLite path could not be resolved.")
database = Path(database_value)

storage = Path(os.getenv("STORAGE_PATH", "./storage"))
if not storage.is_absolute():
    storage = backend / storage

print(database.resolve())
print((storage / "chroma_db").resolve())
PY
)

if [[ "${#STORAGE_PATHS[@]}" -ne 2 ]]; then
  echo "ERROR: could not resolve SQLite and ChromaDB paths." >&2
  exit 1
fi
DATABASE_PATH="${STORAGE_PATHS[0]}"
CHROMA_PATH="${STORAGE_PATHS[1]}"

if [[ ! -f "$DATABASE_PATH" ]]; then
  echo "ERROR: SQLite database not found: $DATABASE_PATH" >&2
  exit 1
fi
if [[ ! -d "$CHROMA_PATH" ]]; then
  echo "ERROR: ChromaDB directory not found: $CHROMA_PATH" >&2
  exit 1
fi

if [[ "$EUID" -eq 0 ]]; then
  SYSTEMCTL=(systemctl)
else
  SYSTEMCTL=(sudo systemctl)
fi

SERVICE_WAS_ACTIVE=false
SERVICE_STOPPED=false
if "${SYSTEMCTL[@]}" is-active --quiet "$SERVICE_NAME"; then
  SERVICE_WAS_ACTIVE=true
  if [[ "$MANAGE_SERVICE" != true ]]; then
    echo "ERROR: $SERVICE_NAME is running. Re-run with --manage-service for a consistent ChromaDB snapshot." >&2
    exit 1
  fi
fi

restore_service() {
  local exit_code=$?
  trap - EXIT INT TERM
  if [[ "$SERVICE_STOPPED" == true && "$SERVICE_WAS_ACTIVE" == true ]]; then
    echo "Restarting $SERVICE_NAME..."
    if ! "${SYSTEMCTL[@]}" start "$SERVICE_NAME"; then
      echo "ERROR: failed to restart $SERVICE_NAME; start it manually." >&2
      exit_code=1
    fi
  fi
  exit "$exit_code"
}
trap restore_service EXIT INT TERM

if [[ "$SERVICE_WAS_ACTIVE" == true ]]; then
  echo "Stopping $SERVICE_NAME for a consistent backup..."
  "${SYSTEMCTL[@]}" stop "$SERVICE_NAME"
  SERVICE_STOPPED=true
fi

umask 077
mkdir -p "$OUTPUT_DIR"
DATABASE_BACKUP="$OUTPUT_DIR/app.db"
CHROMA_BACKUP="$OUTPUT_DIR/chroma_db.tar.gz"

echo "Backing up SQLite: $DATABASE_PATH"
SOURCE_DATABASE="$DATABASE_PATH" DESTINATION_DATABASE="$DATABASE_BACKUP" "$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote

source_path = Path(os.environ["SOURCE_DATABASE"])
destination_path = Path(os.environ["DESTINATION_DATABASE"])
source = sqlite3.connect(f"file:{quote(source_path.as_posix(), safe='/:')}?mode=ro", uri=True)
destination = sqlite3.connect(destination_path)
try:
    source.backup(destination)
    result = destination.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise RuntimeError(f"SQLite integrity_check failed: {result}")
finally:
    destination.close()
    source.close()
PY

echo "Archiving ChromaDB: $CHROMA_PATH"
tar -C "$(dirname "$CHROMA_PATH")" -czf "$CHROMA_BACKUP" "$(basename "$CHROMA_PATH")"

(
  cd "$OUTPUT_DIR"
  sha256sum app.db chroma_db.tar.gz > SHA256SUMS
)

BACKUP_CREATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GIT_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || printf 'unknown')"
BACKUP_CREATED_AT="$BACKUP_CREATED_AT" GIT_SHA="$GIT_SHA" \
SOURCE_DATABASE="$DATABASE_PATH" SOURCE_CHROMA="$CHROMA_PATH" \
DESTINATION="$OUTPUT_DIR" SERVICE_NAME="$SERVICE_NAME" \
SERVICE_WAS_ACTIVE="$SERVICE_WAS_ACTIVE" "$PYTHON_BIN" - <<'PY' > "$OUTPUT_DIR/manifest.json"
import json
import os
from pathlib import Path

destination = Path(os.environ["DESTINATION"])
manifest = {
    "backup_version": "evidence-graph-v1",
    "created_at": os.environ["BACKUP_CREATED_AT"],
    "git_sha": os.environ["GIT_SHA"],
    "service": os.environ["SERVICE_NAME"],
    "service_was_active": os.environ["SERVICE_WAS_ACTIVE"] == "true",
    "sources": {
        "sqlite": os.environ["SOURCE_DATABASE"],
        "chroma": os.environ["SOURCE_CHROMA"],
    },
    "artifacts": {
        "sqlite": {"file": "app.db", "bytes": (destination / "app.db").stat().st_size},
        "chroma": {"file": "chroma_db.tar.gz", "bytes": (destination / "chroma_db.tar.gz").stat().st_size},
        "checksums": "SHA256SUMS",
    },
}
print(json.dumps(manifest, indent=2, sort_keys=True))
PY

chmod 600 "$OUTPUT_DIR/app.db" "$OUTPUT_DIR/chroma_db.tar.gz" "$OUTPUT_DIR/SHA256SUMS" "$OUTPUT_DIR/manifest.json"
sync

if [[ "$SERVICE_STOPPED" == true ]]; then
  echo "Restarting $SERVICE_NAME..."
  "${SYSTEMCTL[@]}" start "$SERVICE_NAME"
  SERVICE_STOPPED=false
  "${SYSTEMCTL[@]}" is-active --quiet "$SERVICE_NAME"
fi
trap - EXIT INT TERM

echo "Backup complete: $OUTPUT_DIR"
cat "$OUTPUT_DIR/SHA256SUMS"
