#!/usr/bin/env bash
set -euo pipefail

CLIENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$CLIENT_DIR"

VM_URL="${1:-${AEM_STUDIO_URL:-}}"
TOKEN="${2:-${AEM_STUDIO_TOKEN:-dev-bypass}}"

if [[ -z "$VM_URL" ]]; then
  echo "Usage: ./install.sh http://<VM-IP-or-host>:4502 [token]"
  echo "Example: ./install.sh http://10.42.46.78:4502 dev-bypass"
  exit 2
fi

VM_URL="${VM_URL%/}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.10+ first."
  exit 1
fi

if ! python3 -m venv .venv >/dev/null 2>&1; then
  echo "Could not create venv."
  echo "Ubuntu/Debian: sudo apt-get install -y python3-venv"
  echo "macOS: install Python 3 from python.org or Homebrew."
  exit 1
fi

".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -r requirements.txt

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js 18+ not found. Install Node.js, then rerun setup. Local AEM upload needs Node.js."
  exit 1
fi
NODE_MAJOR="$(node -p "process.versions.node.split('.')[0]")"
if [[ "$NODE_MAJOR" -lt 18 ]]; then
  echo "Node.js 18+ is required for local AEM upload. Found: $(node --version)"
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js with npm, then rerun setup."
  exit 1
fi

npm install --omit=dev

cat > .env <<EOF
AEM_STUDIO_URL=$VM_URL
AEM_STUDIO_TOKEN=$TOKEN
AEM_STUDIO_TIMEOUT_SECONDS=300
PYTHONUTF8=1
EOF

PYTHON_PATH="$CLIENT_DIR/.venv/bin/python"
SERVER_PATH="$CLIENT_DIR/server.py"

cat > claude-mcp-server.json <<EOF
{
  "command": "$PYTHON_PATH",
  "args": ["$SERVER_PATH"],
  "cwd": "$CLIENT_DIR",
  "env": {
    "AEM_STUDIO_URL": "$VM_URL",
    "AEM_STUDIO_TOKEN": "$TOKEN",
    "AEM_STUDIO_TIMEOUT_SECONDS": "300",
    "PYTHONUTF8": "1"
  }
}
EOF

cat > .mcp.json <<EOF
{
  "mcpServers": {
    "aem-guides-dataset-studio": $(cat claude-mcp-server.json)
  }
}
EOF

chmod +x install.sh smoke_test.sh install_claude_assets.sh doctor_claude.sh

echo
echo "Installed AEM Guides MCP client."
echo "Client dir: $CLIENT_DIR"
echo "VM backend: $VM_URL"
echo
echo "Running smoke test..."
if ./smoke_test.sh; then
  echo "Smoke test passed."
else
  echo "Smoke test failed. Check VPN, backend URL, token, and VM service: systemctl status aem-backend"
fi
echo
echo "Next:"
echo "  ./install_claude_assets.sh"
echo "  ./doctor_claude.sh"
echo "  claude mcp add-json aem-guides-dataset-studio \"\$(cat claude-mcp-server.json)\""
echo
echo "If your Claude Code version does not support add-json, run Claude from this folder so .mcp.json is picked up:"
echo "  cd \"$CLIENT_DIR\" && claude"
echo
echo "For local uploads, create config/aem-upload.properties and pass a local source_path to upload_dataset_to_aem."
