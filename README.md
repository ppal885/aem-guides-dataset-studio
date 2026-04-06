# AEM Guides Dataset Studio

> AI-powered DITA authoring platform with an intelligent chat copilot, content migration, visual diagram generation, and one-click AEM Cloud upload -- built for Technical Writers.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/react-18.2-61dafb.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/fastapi-latest-009688.svg)](https://fastapi.tiangolo.com/)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## What is this?

**AEM Guides Dataset Studio** is a full-stack platform that helps Technical Writers produce spec-compliant DITA content at scale. It combines:

- **AI Chat Copilot** -- a multi-tool agentic chat that generates, validates, fixes, and enriches DITA XML in real time
- **RAG-Grounded Generation** -- every generation is grounded in DITA 1.3 spec rules, AEM Guides documentation, and expert DITA examples
- **Content Intelligence** -- smart shortdesc generation, topic type classification, style guide enforcement
- **Content Migration** -- auto-convert Markdown, HTML, and plain text into properly structured DITA topics
- **Visual Diagrams** -- generate Mermaid flowcharts, concept maps, and map structure diagrams from DITA content
- **Dataset Factory** -- bulk generate DITA datasets from Jira issues or templates with 20+ recipe types
- **AEM Cloud Upload** -- upload generated datasets directly to AEM Cloud Service or on-premise instances

---

## Key Features

### AI Chat Copilot
| Feature | Description |
|---------|-------------|
| Multi-tool agent loop | Chat autonomously calls up to 22 tools -- generate, validate, fix, search, browse |
| Streaming responses | Real-time token streaming with tool execution indicators |
| Multi-provider LLM | OpenAI, Anthropic, Groq (free tier) with automatic fallback |
| RAG context assembly | Retrieves from AEM docs, DITA spec, tenant knowledge, and indexed PDFs |
| Smart tool selection | Dynamically selects the most relevant tools per query (optimized for Groq token limits) |
| Inline XML recovery | Recovers tool calls when Groq outputs raw XML instead of API tool_use blocks |
| Conversation sessions | Persistent chat sessions with message history |
| Grounding panel | Shows citations and source evidence for AI responses |

### Content Intelligence (Phase F)
| Tool | Description |
|------|-------------|
| Smart Shortdesc Generator | LLM-enhanced + rule-based shortdesc generation following information-typing rules |
| Topic Type Advisor | Pure rule-based classifier -- detects task/concept/reference misclassification |
| Style Guide Enforcer | 10 built-in rules: passive voice, sentence length, banned terms, step imperatives, etc. |

### Content Migration (Phase G)
| Tool | Description |
|------|-------------|
| Content Migration Copilot | Auto-detect format (Markdown/HTML/plain text), classify sections, generate DITA topics + ditamap |
| Section Classification | Heading-based splitting with task/concept/reference/glossentry type detection |
| DITA Generation | Proper DOCTYPE declarations, xml:lang, slugified IDs, structural elements per topic type |

### Visual Diagrams (Phase I)
| Tool | Description |
|------|-------------|
| Task Flowcharts | Steps to Mermaid flowchart with decision diamonds for choices |
| Concept Mind Maps | Sections to hierarchical Mermaid mindmap |
| Map Structure Diagrams | Topicref hierarchy to navigable flowchart |
| Map Visualizer | Interactive tree component with color-coded nodes, stats, and AI suggestions |

### Dataset Generation
| Feature | Description |
|---------|-------------|
| 20+ recipe types | Task topics, concept topics, glossary packs, relationship tables, conref packs, bookmaps, and more |
| Jira integration | Pull real issues and generate grounded DITA content |
| Batch processing | Generate hundreds of topics from JQL queries or CSV templates |
| Quality scoring | Automated quality checks with validation and enrichment pipeline |
| Job management | Track, browse, and download generated datasets |

### AEM Upload
| Feature | Description |
|---------|-------------|
| Cloud Service support | Bearer token auth via AEM Developer Console |
| On-premise support | Basic Auth (username/password) for AEM on-premise and AMS |
| Auto-detection | Automatically detects `adobeaemcloud.com` URLs and switches to token auth |
| Deep upload | Preserves directory structure with content/dam path optimization |
| Concurrent uploads | Configurable concurrency (1-100 simultaneous file uploads) |

---

## Architecture

```
aem-guides-dataset-studio/
├── frontend/                          # React 18 + Vite + Tailwind CSS
│   └── src/
│       ├── pages/                     # 8 pages (Chat, Builder, Upload, Explorer, etc.)
│       ├── components/                # 51 components
│       │   ├── Chat/                  # Chat UI (messages, input, markdown, sidebar)
│       │   ├── ui/                    # Radix UI primitives
│       │   └── ...                    # Recipe configs, feedback, layout
│       └── utils/                     # API clients, helpers
│
├── backend/
│   └── app/
│       ├── api/v1/routes/             # 20 route modules (chat, datasets, recipes, etc.)
│       ├── services/                  # 90+ service modules
│       │   ├── chat_service.py        # Agentic chat orchestrator
│       │   ├── chat_tools.py          # 22 tool definitions + dispatch
│       │   ├── llm_service.py         # Multi-provider LLM (OpenAI/Anthropic/Groq)
│       │   ├── vector_store_service.py # ChromaDB vector store
│       │   ├── hierarchical_retriever.py # Weighted multi-signal retrieval
│       │   ├── chunk_metadata_extractor.py # DITA-aware metadata extraction
│       │   ├── shortdesc_generator_service.py  # Phase F1
│       │   ├── topic_type_advisor_service.py   # Phase F2
│       │   ├── style_guide_enforcer_service.py # Phase F4
│       │   ├── content_migration_service.py    # Phase G2
│       │   ├── diagram_generation_service.py   # Phase I1
│       │   ├── map_visualizer_service.py       # Phase I2
│       │   ├── tool_result_cache.py   # D7: LRU cache with TTL
│       │   └── ...                    # Jira, RAG, enrichment, validation
│       ├── db/                        # SQLAlchemy models + session
│       ├── core/                      # Auth, config, structured logging
│       └── storage/                   # ChromaDB, seed data, JSON chunks
│
├── backend/scripts/
│   └── aem_upload.js                  # Node.js AEM upload (Basic Auth + Bearer Token)
│
├── backend/tests/                     # 78 test files, 211+ tests
│
├── mcp_server.py                      # MCP server -- in-process tools (Jira, RAG, files)
├── mcp_api_adapter/                   # MCP server -- REST proxy to FastAPI
└── scripts/                           # CLI scripts (index, finetune, crawl)
```

---

## How It Works

```
                    ┌─────────────────────────────────┐
                    │         React Frontend           │
                    │  Chat  │ Builder │ Upload │ ...  │
                    └──────────────┬──────────────────┘
                                   │ REST API
                    ┌──────────────▼──────────────────┐
                    │       FastAPI Backend             │
                    │                                   │
                    │  ┌─────────────────────────────┐ │
                    │  │      Chat Service            │ │
                    │  │  (agentic tool loop)         │ │
                    │  │  ┌─────┐ ┌──────┐ ┌──────┐  │ │
                    │  │  │Tools│ │ RAG  │ │ LLM  │  │ │
                    │  │  │(22) │ │Blend │ │Multi │  │ │
                    │  │  └─────┘ └──────┘ └──────┘  │ │
                    │  └─────────────────────────────┘ │
                    │                                   │
                    │  ┌──────────┐ ┌───────────────┐  │
                    │  │ Dataset  │ │  AEM Upload    │  │
                    │  │ Pipeline │ │  (Node.js)     │  │
                    │  └──────────┘ └───────────────┘  │
                    └──────────────┬──────────────────┘
                    ┌──────────────▼──────────────────┐
                    │      Knowledge Layer             │
                    │  ChromaDB │ SQLite │ JSON Seeds  │
                    │  AEM Docs │ DITA Spec │ Jira     │
                    └─────────────────────────────────┘
```

### Chat Copilot Flow
```
User message
    ↓
_build_rag_context()          ← Hierarchical retrieval from AEM docs + DITA spec
    ↓
Smart tool selection          ← Pick 5 most relevant tools (Groq) or all 22
    ↓
LLM generates response        ← Streaming with tool_use blocks
    ↓
Tool execution loop (max 8 rounds)
  ├── generate_dita            → DITA XML generation
  ├── review_dita_xml          → Validation
  ├── fix_dita_xml             → Auto-repair
  ├── generate_shortdesc       → Smart shortdesc
  ├── advise_topic_type        → Classification
  ├── check_style_guide        → Style enforcement
  ├── migrate_content          → Format conversion
  ├── generate_diagram         → Mermaid diagrams
  ├── visualize_map            → Map structure graph
  └── ... (13 more tools)
    ↓
Streaming response to user
```

---

## Quickstart

### Prerequisites

- Python 3.11+
- Node.js 18+ (for AEM upload)
- Git

### 1. Clone and setup

```bash
git clone https://github.com/YOUR_USERNAME/aem-guides-dataset-studio.git
cd aem-guides-dataset-studio

# Backend
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
# LLM Provider (pick one)
LLM_PROVIDER=openai                    # or: anthropic, groq
OPENAI_API_KEY=sk-...                  # GPT-4o-mini recommended ($0.15/M input)
# ANTHROPIC_API_KEY=sk-ant-...         # Claude Sonnet
# GROQ_API_KEY=gsk_...                 # Free tier (12K TPM limit)

# Jira (optional -- for dataset generation)
JIRA_BASE_URL=https://jira.yourcompany.com
JIRA_USERNAME=your_username
JIRA_PASSWORD=your_password

# Embedding Model
DITA_EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### 3. Initialize and run

```bash
# Initialize database
cd backend
python -m scripts.init_db

# Start backend (terminal 1)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start frontend (terminal 2)
cd frontend
npx vite --port 5173 --host 0.0.0.0
```

Open `http://localhost:5173` -- the chat copilot is ready to use.

### 4. Populate RAG knowledge base (optional, improves quality)

```bash
# In the chat, or via API:
# 1. Crawl AEM Guides docs
POST /api/v1/ai/crawl-aem-guides

# 2. Index DITA spec
POST /api/v1/ai/index-dita-spec
```

---

## Chat Copilot -- Example Prompts

**Generate DITA:**
```
Generate a DITA task topic about configuring OAuth authentication in AEM
```

**Validate and fix:**
```
Review this DITA XML and fix any issues:
<task id="my-task"><title>Test</title><taskbody>...</taskbody></task>
```

**Content migration:**
```
Convert this Markdown to DITA:
# Installation Guide
## Prerequisites
- Node.js 18+
## Steps
1. Clone the repository
2. Run npm install
```

**Visual diagrams:**
```
Generate a flowchart diagram for this task topic:
<task id="deploy"><title>Deploy App</title><taskbody><steps>...</steps></taskbody></task>
```

**Map visualization:**
```
Visualize this map:
<map><title>User Guide</title><topicref href="intro.dita">...</topicref></map>
```

**Style check:**
```
Check this topic against style guidelines:
<concept id="overview"><title>Overview</title><conbody>...</conbody></concept>
```

---

## AEM Upload

The platform supports uploading generated datasets directly to AEM instances.

### AEM Cloud Service (AEMaaCS)
1. Go to your AEM Developer Console
2. Navigate to **Integrations** > **Local Token**
3. Copy the `accessToken` (valid for 24 hours)
4. On the Upload page, select **Bearer Token** auth mode and paste the token

### AEM On-Premise / AMS
1. Use **Basic Auth** mode with your AEM username and password

The upload page auto-detects `adobeaemcloud.com` URLs and switches to Bearer Token mode.

---

## Chat Tools Reference (22 Tools)

### Core DITA Tools
| Tool | Description |
|------|-------------|
| `generate_dita` | Generate DITA XML from natural language descriptions |
| `review_dita_xml` | Validate DITA structure and content |
| `fix_dita_xml` | Auto-fix DITA XML issues |
| `lookup_dita_spec` | Look up DITA 1.3 specification details |
| `lookup_dita_attribute` | Look up valid values for DITA attributes |

### Content Intelligence
| Tool | Description |
|------|-------------|
| `generate_shortdesc` | Generate DITA-compliant short descriptions |
| `advise_topic_type` | Classify and recommend correct topic type |
| `check_style_guide` | Enforce style rules (passive voice, sentence length, etc.) |
| `migrate_content` | Convert Markdown/HTML/plain text to DITA |

### Visual Tools
| Tool | Description |
|------|-------------|
| `generate_diagram` | Generate Mermaid flowcharts, mindmaps, and process flows |
| `visualize_map` | Parse DITA maps into interactive graph visualizations |

### Search and Retrieval
| Tool | Description |
|------|-------------|
| `lookup_aem_guides` | Search AEM Guides documentation |
| `search_tenant_knowledge` | Search tenant-specific knowledge base |
| `search_jira_issues` | Search related Jira issues |
| `find_recipes` | Search available dataset generation recipes |
| `lookup_output_preset` | Look up AEM output preset configuration |
| `list_indexed_pdfs` | List indexed PDF documents |

### Job Management
| Tool | Description |
|------|-------------|
| `create_job` | Create dataset generation job with recipe type |
| `get_job_status` | Check job progress and status |
| `list_jobs` | List recent dataset generation jobs |
| `browse_dataset` | Browse generated dataset files |
| `generate_native_pdf_config` | Get Native PDF template configuration guidance |

---

## MCP Server

Two MCP integrations are available for use with Cursor, Claude Code, or Codex:

### In-Process MCP (`mcp_server.py`)
Full-featured MCP server with direct access to all services (Jira, RAG, DITA tools).

```json
{
  "mcpServers": {
    "aem-dataset-studio": {
      "command": "python",
      "args": ["mcp_server.py"]
    }
  }
}
```

### REST API Adapter (`mcp_api_adapter/`)
Lightweight MCP proxy that forwards to the FastAPI backend over HTTP.

```json
{
  "mcpServers": {
    "dataset-studio-api": {
      "command": "python",
      "args": ["-m", "mcp_api_adapter"],
      "env": {
        "DATASET_STUDIO_API_BASE_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

See [`MCP_TOOL_MAP.md`](MCP_TOOL_MAP.md) for the full tool-to-endpoint mapping.

---

## Dataset Recipes (20+ Types)

| Category | Recipes |
|----------|---------|
| **Topics** | Task topics, concept topics, reference topics, glossary entries |
| **Maps** | Bookmaps, relationship tables, incremental topicref maps |
| **Advanced** | Conref packs, keydef chains, keyscope demos, conditional content |
| **Enterprise** | Customer reuse packs, localization, insurance domain, media-rich content |
| **Testing** | Performance scale, map parse stress, heavy conditional |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18, Vite, Tailwind CSS, Radix UI, react-markdown, react-syntax-highlighter |
| Backend | Python 3.11+, FastAPI, SQLAlchemy, Pydantic |
| Vector Store | ChromaDB (persistent, cosine similarity) |
| Embeddings | Sentence Transformers (all-MiniLM-L6-v2) |
| LLM Providers | OpenAI, Anthropic, Groq |
| AEM Upload | Node.js, @adobe/aem-upload v3+ |
| MCP | Model Context Protocol SDK |

---

## Testing

```bash
cd backend
python -m pytest tests/ -v
```

**78 test files** covering:
- Chat service (tool dispatch, grounding, fallback, streaming)
- Content intelligence (shortdesc, topic type, style rules)
- Content migration (Markdown/HTML/plain text to DITA)
- Diagram generation (flowcharts, mindmaps, process flows)
- Map visualizer (graph parsing, Mermaid output)
- DITA validation (conref, keyref, xref, glossary)
- Recipe execution and scoring
- Tool result caching, error taxonomy, observability
- AEM upload service

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | LLM provider: `openai`, `anthropic`, `groq` | `openai` |
| `OPENAI_API_KEY` | OpenAI API key | -- |
| `ANTHROPIC_API_KEY` | Anthropic API key | -- |
| `GROQ_API_KEY` | Groq API key (free tier available) | -- |
| `JIRA_BASE_URL` | Jira instance URL | -- |
| `JIRA_USERNAME` / `JIRA_PASSWORD` | Jira credentials | -- |
| `DITA_EMBEDDING_MODEL` | Sentence transformer model | `all-MiniLM-L6-v2` |
| `CHUNK_METADATA_ENABLED` | Enable DITA-aware metadata extraction | `false` |
| `HIERARCHICAL_RETRIEVAL_ENABLED` | Enable weighted multi-signal retrieval | `false` |
| `CHAT_TOOL_CACHE_ENABLED` | Enable tool result LRU caching | `false` |
| `DITA_IMAGE_GENERATION_ENABLED` | Enable AI image generation in DITA | `false` |
| `DATABASE_URL` | SQLite/Postgres connection string | `sqlite:///...` |

---

## Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-tool`
3. Add your changes with tests
4. Run `python -m pytest tests/ -v` to verify
5. Open a PR with a description of what changed

---

## License

MIT -- see [LICENSE](LICENSE)

---

## Credits

- [DITAWriter](https://github.com/DITAWriter) -- expert DITA example repos
- [OASIS DITA TC](https://www.oasis-open.org/committees/dita/) -- DITA 1.2/1.3 spec
- [Adobe Experience League](https://experienceleague.adobe.com/en/docs/experience-manager-guides) -- AEM Guides docs
- [Model Context Protocol](https://modelcontextprotocol.io/) -- MCP SDK
- [Mermaid.js](https://mermaid.js.org/) -- diagram rendering
