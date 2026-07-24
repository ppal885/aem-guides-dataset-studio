#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="/etc/nginx/sites-enabled/default"
RELOAD_NGINX="0"
SKIP_NGINX_TEST="0"

usage() {
  cat <<'EOF'
Usage:
  scripts/configure_vm_remote_mcp_nginx.sh [--config /etc/nginx/sites-enabled/default] [--reload] [--skip-nginx-test]

What it does:
  - Backs up the nginx site config.
  - Removes any existing /mcp nginx location blocks, including accidentally nested ones.
  - Inserts the correct /mcp proxy locations as top-level siblings inside the server block that listens on 4502.
  - Runs `nginx -t`.
  - Reloads nginx only when --reload is passed.

Example:
  cd ~/aem-guides-dataset-studio
  bash scripts/configure_vm_remote_mcp_nginx.sh --reload

EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      CONFIG_PATH="${2:-}"
      if [[ -z "$CONFIG_PATH" ]]; then
        echo "ERROR: --config requires a path" >&2
        exit 2
      fi
      shift 2
      ;;
    --reload)
      RELOAD_NGINX="1"
      shift
      ;;
    --skip-nginx-test)
      SKIP_NGINX_TEST="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "ERROR: nginx config not found: $CONFIG_PATH" >&2
  exit 1
fi

if [[ "$(id -u)" -ne 0 && "$CONFIG_PATH" == /etc/nginx/* ]]; then
  echo "ERROR: run with sudo/root so the script can update nginx config." >&2
  echo "Example: sudo bash scripts/configure_vm_remote_mcp_nginx.sh --reload" >&2
  exit 1
fi

BACKUP_PATH="${CONFIG_PATH}.bak.$(date +%Y%m%d-%H%M%S)"
cp "$CONFIG_PATH" "$BACKUP_PATH"
echo "Backup written: $BACKUP_PATH"

python3 - "$CONFIG_PATH" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
text = config_path.read_text(encoding="utf-8", errors="replace")
lines = text.splitlines(keepends=True)

MCP_SNIPPET = """\
    # Remote MCP endpoint for Claude Code / team usage
    location = /mcp {
        proxy_pass http://127.0.0.1:8001/mcp;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_buffering off;
    }

    location /mcp/ {
        proxy_pass http://127.0.0.1:8001/mcp/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_buffering off;
    }

"""


def brace_delta(line: str) -> int:
    stripped = re.sub(r"#.*$", "", line)
    return stripped.count("{") - stripped.count("}")


def remove_existing_mcp_locations(source_lines: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    start_pattern = re.compile(r"^\s*location\s+(?:=\s*/mcp|/mcp/)\s*\{")
    comment_pattern = re.compile(r"^\s*#\s*Remote MCP endpoint for Claude Code")
    while index < len(source_lines):
        line = source_lines[index]
        if comment_pattern.match(line) and index + 1 < len(source_lines) and start_pattern.match(source_lines[index + 1]):
            index += 1
            line = source_lines[index]
        if start_pattern.match(line):
            depth = brace_delta(line)
            index += 1
            while index < len(source_lines) and depth > 0:
                depth += brace_delta(source_lines[index])
                index += 1
            while index < len(source_lines) and source_lines[index].strip() == "":
                index += 1
            continue
        result.append(line)
        index += 1
    return result


def find_server_blocks(source_lines: list[str]) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    index = 0
    server_pattern = re.compile(r"^\s*server\s*\{")
    while index < len(source_lines):
        if not server_pattern.match(source_lines[index]):
            index += 1
            continue
        start = index
        depth = brace_delta(source_lines[index])
        index += 1
        while index < len(source_lines) and depth > 0:
            depth += brace_delta(source_lines[index])
            index += 1
        if depth == 0:
            blocks.append((start, index))
    return blocks


def block_listens_on_4502(block_lines: list[str]) -> bool:
    return any(re.search(r"^\s*listen\s+4502\b", line) for line in block_lines)


def top_level_insertion_index(block_lines: list[str]) -> int:
    depth = 0
    api_pattern = re.compile(r"^\s*location\s+/api\b")
    root_pattern = re.compile(r"^\s*location\s+/\s*\{")
    fallback = len(block_lines) - 1
    for offset, line in enumerate(block_lines):
        current_depth = depth
        if current_depth == 1 and api_pattern.match(line):
            return offset
        if current_depth == 1 and root_pattern.match(line):
            fallback = min(fallback, offset)
        depth += brace_delta(line)
    return fallback


lines = remove_existing_mcp_locations(lines)
blocks = find_server_blocks(lines)
target: tuple[int, int] | None = None
for block in blocks:
    if block_listens_on_4502(lines[block[0]:block[1]]):
        target = block
        break

if target is None:
    raise SystemExit("ERROR: Could not find nginx server block with `listen 4502;`")

start, end = target
block_lines = lines[start:end]
insert_offset = top_level_insertion_index(block_lines)
insert_at = start + insert_offset
snippet_lines = MCP_SNIPPET.splitlines(keepends=True)
updated_lines = lines[:insert_at] + snippet_lines + lines[insert_at:]
updated_text = "".join(updated_lines)

if "location = /mcp" not in updated_text or "location /mcp/" not in updated_text:
    raise SystemExit("ERROR: Failed to insert /mcp locations")

config_path.write_text(updated_text, encoding="utf-8")
print(f"Updated nginx config: {config_path}")
PY

if [[ "$SKIP_NGINX_TEST" == "1" ]]; then
  echo "Skipping nginx config test (--skip-nginx-test)."
elif [[ "$RELOAD_NGINX" == "1" ]]; then
  echo "Running nginx config test..."
  nginx -t
  echo "Reloading nginx..."
  systemctl reload nginx
  echo "nginx reloaded."
else
  echo "Running nginx config test..."
  nginx -t
  echo "nginx config is valid. Reload manually with: sudo systemctl reload nginx"
fi

echo "Next tests:"
echo "  curl -s http://127.0.0.1:8001/mcp/health"
echo "  curl -s http://127.0.0.1:4502/mcp/health"
