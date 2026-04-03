# AEM Guides Dataset Studio

> Generate spec-compliant DITA content from Jira issues using AI — powered by RAG, fine-tuned embeddings, and an MCP server for Cursor.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## What is this?

**AEM Guides Dataset Studio** is a tool that:

1. **Pulls real Jira issues** from your project
2. **Grounds generation** in actual DITA 1.2/1.3 spec rules (indexed from OASIS PDFs)
3. **Grounds generation** in real AEM Guides documentation (crawled from Experience League)
4. **Uses expert DITA examples** as few-shot references (DITAWriter GitHub repos)
5. **Generates spec-compliant DITA** via Cursor Agent — no API key needed
6. **Validates and enriches** output automatically

The result: production-quality DITA files from Jira issues in seconds, not hours.

---

## Architecture

```
aem-guides-dataset-studio/
├── backend/
│   └── app/
│       ├── services/          # Core services
│       │   ├── jira_client.py                 # Jira REST API client
│       │   ├── jira_dita_fetch_service.py     # Fetch issues for DITA
│       │   ├── jira_similarity_service.py     # Semantic issue search
│       │   ├── jira_index_service.py          # Index issues to DB
│       │   ├── doc_retriever_service.py       # Experience League RAG
│       │   ├── dita_knowledge_retriever.py    # DITA spec RAG
│       │   ├── dita_graph_service.py          # Element nesting graph
│       │   ├── dita_enrichment_service.py     # Auto-add shortdesc/prolog
│       │   ├── dita_pdf_index_service.py      # Index DITA spec PDFs
│       │   ├── crawl_service.py               # Crawl Experience League
│       │   ├── embedding_service.py           # Sentence transformers
│       │   └── jira_dita_analysis_service.py  # Full analysis pipeline
│       ├── db/                # SQLAlchemy models + session
│       ├── core/              # Logging, config
│       ├── storage/           # ChromaDB, JSON chunks, seed data
│       └── templates/prompts/ # LLM prompt templates
├── mcp_server.py              # MCP server — in-process tools (Jira, RAG, files)
├── mcp_api_adapter/           # MCP server — thin proxy to FastAPI /api/v1 only
├── dita_examples/             # Cloned expert DITA repos (git-ignored)
├── output/dita/               # Generated DITA files (git-ignored)
└── scripts/                   # CLI scripts (index, finetune, crawl)
```

---

## How it works

```
Jira Issue
    ↓
get_jira_issue_with_comments()     ← MCP fetches real data
    ↓
query_combined_context()           ← RAG grounds generation
  ├── Experience League docs        (AEM-specific patterns)
  ├── DITA 1.2/1.3 spec PDFs       (structural rules)
  └── DITA element graph            (nesting + attributes)
    ↓
query_dita_examples()              ← Expert examples as reference
    ↓
Cursor Agent generates DITA        ← No API key needed (Cursor is the LLM)
    ↓
validate_and_fix_dita()            ← Self-healing validation loop
    ↓
enrich_dita_output()               ← Auto-add shortdesc, prolog
    ↓
score_dita_quality()               ← Quality check
    ↓
✅ Spec-compliant DITA file
```

---

## Quickstart

### Prerequisites

- Python 3.11+
- Git
- Codex or Cursor with MCP enabled
- Jira access (corporate or cloud)

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/aem-guides-dataset-studio.git
cd aem-guides-dataset-studio
```

### 2. Create virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Jira Configuration
JIRA_BASE_URL=https://jira.corp.yourcompany.com
JIRA_USERNAME=your_username
JIRA_PASSWORD=your_password
# OR for Jira Cloud:
JIRA_EMAIL=your@email.com
JIRA_API_TOKEN=your_api_token
JIRA_API_VERSION=2

# Embedding Model
DITA_EMBEDDING_MODEL=all-MiniLM-L6-v2
USE_DITA_EMBEDDING=true
USE_DITA_HYBRID_SEARCH=true

# Optional: fine-tuned model path
# DITA_EMBEDDING_MODEL_PATH=models/dita_embeddings_v1
```

### 5. Initialize the database

```bash
python -m scripts.init_db
```

### 6. Configure Codex MCP (recommended)

This repo includes a project-scoped [`.codex/config.toml`](.codex/config.toml) that starts [`mcp_server.py`](mcp_server.py) with the local virtualenv and sets the workspace model to `gpt-5-codex`.

If you move the repo, update the absolute paths in `.codex/config.toml`.

If you also want the backend AI endpoints to use OpenAI/Codex, set these in `backend/.env`:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-5-codex
```

### 6b. MCP over REST (API adapter)

The package [`mcp_api_adapter/`](mcp_api_adapter/) runs a **stdio MCP server** that calls your running FastAPI app under **`/api/v1`** via httpx. It does **not** import application services; it only forwards REST requests. This is useful when agents must use the same contract as the UI/API, or when the API runs on another host.

**Prerequisite:** start the backend (for example from `backend/` with uvicorn on the configured port, often `8000`).

**Install MCP dependencies** (lightweight; can be the same venv as the backend or a separate one):

```bash
pip install -r requirements-mcp.txt
```

**Run (normally invoked by Cursor / Codex, not by hand):**

```bash
python -m mcp_api_adapter
```

**Environment** (optional): `DATASET_STUDIO_API_BASE_URL` (default `http://127.0.0.1:8000`), `DATASET_STUDIO_API_BEARER_TOKEN` or `API_BEARER_TOKEN`, `DATASET_STUDIO_API_TIMEOUT_SECONDS`, `DATASET_STUDIO_API_EXTRA_HEADERS_JSON`. See [`MCP_TOOL_MAP.md`](MCP_TOOL_MAP.md) for the full tool-to-endpoint table and copy-paste config for Cursor, Claude Code, and Codex.

**Compared to [`mcp_server.py`](mcp_server.py):** the root `mcp_server.py` exposes many **in-process** tools (Jira, RAG, DITA files). The API adapter exposes only the **13 REST-mapped** tools and requires a live HTTP API.

### 6c. Configure Cursor MCP (optional)

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "aem-dataset-studio": {
      "command": "C:\\path\\to\\aem-guides-dataset-studio\\venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\aem-guides-dataset-studio\\mcp_server.py"]
    },
    "dataset-studio-api": {
      "command": "C:\\path\\to\\aem-guides-dataset-studio\\venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_api_adapter"],
      "cwd": "C:\\path\\to\\aem-guides-dataset-studio",
      "env": {
        "DATASET_STUDIO_API_BASE_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

> **Mac/Linux:** use `venv/bin/python` instead of `venv\Scripts\python.exe`  
> **`dataset-studio-api`:** optional; REST-only MCP adapter — see [`MCP_TOOL_MAP.md`](MCP_TOOL_MAP.md).

### 7. Populate RAG knowledge base

In Codex or Cursor, run these once:

```
1. Run crawl_experience_league        # indexes AEM Guides docs (~5 min)
2. Run index_dita_spec_pdfs           # indexes DITA 1.2/1.3 PDFs (~5 min)  
3. Run clone_dita_example_repos       # clones expert DITA examples
4. Run index_dita_example_repos       # indexes them into ChromaDB
```

### 8. Generate your first DITA file

In Codex or Cursor:

```
Fetch Jira issue AEM-123 with comments.
Query combined context using the issue summary.
Query DITA examples for similar task topics.
Generate a DITA 1.3 compliant task topic.
Save as AEM-123-task.dita, validate, and enrich.
```

---

## MCP Tools Reference

### Jira Tools
| Tool | Description |
|------|-------------|
| `get_jira_issue` | Fetch single issue by key |
| `get_jira_issue_with_comments` | Fetch issue + all comments |
| `search_jira_issues` | Search via JQL |
| `find_similar_jira_issues` | Semantic similarity search |
| `index_jira_issues` | Index issues to local DB |

### RAG Tools
| Tool | Description |
|------|-------------|
| `check_rag_status` | Check what's indexed |
| `crawl_experience_league` | Crawl AEM Guides docs |
| `index_dita_spec_pdfs` | Index DITA 1.2/1.3 spec |
| `query_experience_league` | Search AEM docs |
| `query_dita_spec` | Search DITA spec |
| `query_dita_graph` | Query element nesting rules |
| `query_combined_context` | Query all sources at once |

### DITA Examples Tools
| Tool | Description |
|------|-------------|
| `clone_dita_example_repos` | Clone DITAWriter GitHub repos |
| `index_dita_example_repos` | Index expert DITA examples |
| `query_dita_examples` | Search expert examples |
| `list_dita_example_repos` | List available repos |

### Output Tools
| Tool | Description |
|------|-------------|
| `save_dita_file` | Save single DITA file |
| `save_dita_files` | Save multiple files at once |
| `enrich_dita_output` | Auto-add shortdesc + prolog |
| `list_dita_files` | List generated files |
| `read_dita_file` | Read a generated file |
| `validate_dita_file` | Validate DITA structure |
| `validate_and_fix_dita` | Validate + instruct Cursor to fix |
| `score_dita_quality` | Score output quality |

### Pipeline Tools
| Tool | Description |
|------|-------------|
| `run_jira_dita_analysis_pipeline` | Full Jira→DITA analysis |
| `batch_generate_plan` | Plan batch generation |
| `mark_issue_generated` | Track generation history |
| `check_issue_generated` | Check if already generated |
| `list_generation_history` | View all generated issues |

---

## Example Cursor Prompts

**Single issue:**
```
Fetch AEM-123 with comments, query combined context,
query DITA examples for task topics, generate DITA 1.3
task topic, save as AEM-123-task.dita, validate and enrich.
```

**Batch generation:**
```
Create a batch plan for JQL: "project = AEM AND status = Done
AND updated >= -7d". Execute each step, validate all files,
then bundle into a package.
```

**Find and generate similar:**
```
Find 5 issues similar to AEM-456, generate a concept topic
for each, assemble into a ditamap called AEM-456-cluster.ditamap
```

---

## Fine-tuning Embeddings

After generating 50+ validated DITA files, improve retrieval quality:

```bash
python -m scripts.finetune_dita_embeddings \
  --epochs 5 \
  --output models/dita_embeddings_v1
```

Then set in `.env`:
```env
DITA_EMBEDDING_MODEL_PATH=models/dita_embeddings_v1
```

---

## For Teams

### Run as shared server

```bash
# On a shared team server
python mcp_server.py --transport sse --host 0.0.0.0 --port 8765
```

Each teammate's `mcp.json`:
```json
{
  "mcpServers": {
    "aem-dataset-studio": {
      "url": "http://your-team-server:8765/sse"
    }
  }
}
```

No Python setup needed on individual machines.

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-tool`
3. Add your MCP tool following the patterns in `mcp_server.py`
4. Open a PR with a description of what the tool does

---

## License

MIT — see [LICENSE](LICENSE)

---

## Credits

- [DITAWriter](https://github.com/DITAWriter) — expert DITA example repos
- [OASIS DITA TC](https://www.oasis-open.org/committees/dita/) — DITA 1.2/1.3 spec
- [Adobe Experience League](https://experienceleague.adobe.com/en/docs/experience-manager-guides) — AEM Guides docs
- [Model Context Protocol](https://modelcontextprotocol.io/) — MCP SDK
