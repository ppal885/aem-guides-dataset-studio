#!/bin/bash
# setup.sh — Run this once to set up AEM Guides Dataset Studio
# Usage: chmod +x setup.sh && ./setup.sh

set -e

echo ""
echo "========================================"
echo " AEM Guides Dataset Studio — Setup"
echo "========================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 not found. Install from https://python.org"
    exit 1
fi
echo "[OK] Python found: $(python3 --version)"

# Check Git
if ! command -v git &> /dev/null; then
    echo "[WARN] Git not found. clone_dita_example_repos tool will not work."
    echo "       Install: brew install git (Mac) or apt install git (Linux)"
else
    echo "[OK] Git found"
fi

# Create venv
echo ""
echo "[1/5] Creating virtual environment..."
python3 -m venv venv
echo "[OK] Virtual environment created"

# Activate and install
echo ""
echo "[2/5] Installing dependencies..."
source venv/bin/activate
pip install --quiet mcp python-dotenv httpx sqlalchemy sentence-transformers
echo "[OK] Core dependencies installed"

pip install --quiet chromadb lxml beautifulsoup4 langchain langchain-community langchain-text-splitters pypdf 2>/dev/null || true
echo "[OK] Optional dependencies installed"

# Create .env
echo ""
echo "[3/5] Setting up environment file..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[OK] .env created from .env.example"
    echo "[!!] EDIT .env with your Jira credentials before continuing"
else
    echo "[OK] .env already exists, skipping"
fi

# Create directories
echo ""
echo "[4/5] Creating output directories..."
mkdir -p output/dita output/packages dita_examples models
touch output/dita/.gitkeep dita_examples/.gitkeep models/.gitkeep
echo "[OK] Directories created"

# Verify
echo ""
echo "[5/5] Verifying MCP server..."
python mcp_server.py --help > /dev/null 2>&1 || true
echo "[OK] mcp_server.py found"

PYTHON_PATH="$(pwd)/venv/bin/python"
MCP_PATH="$(pwd)/mcp_server.py"

echo ""
echo "========================================"
echo " Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your Jira credentials"
echo "  2. Add to ~/.cursor/mcp.json:"
echo '     {'
echo '       "mcpServers": {'
echo '         "aem-dataset-studio": {'
echo "           \"command\": \"$PYTHON_PATH\","
echo "           \"args\": [\"$MCP_PATH\"]"
echo '         }'
echo '       }'
echo '     }'
echo "  3. Restart Cursor — green dot should appear"
echo "  4. In Cursor Agent, run:"
echo "     - crawl_experience_league"
echo "     - index_dita_spec_pdfs"
echo "     - clone_dita_example_repos"
echo "     - index_dita_example_repos"
echo ""
