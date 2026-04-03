# Authoring Page — Setup Instructions

## File structure to create

```
frontend/src/
├── pages/
│   └── AuthoringPage.tsx          ← copy from output
└── components/
    └── Authoring/
        ├── JiraIssueBrowser.tsx   ← copy from output
        ├── DitaEditor.tsx         ← copy from output
        └── QualityPanel.tsx       ← copy from output
```

## Step 1 — Copy files

```bash
# Create the Authoring components folder
mkdir frontend\src\components\Authoring

# Copy files (from wherever you saved the Claude outputs)
copy AuthoringPage.tsx    frontend\src\pages\AuthoringPage.tsx
copy JiraIssueBrowser.tsx frontend\src\components\Authoring\JiraIssueBrowser.tsx
copy DitaEditor.tsx       frontend\src\components\Authoring\DitaEditor.tsx
copy QualityPanel.tsx     frontend\src\components\Authoring\QualityPanel.tsx
```

## Step 2 — Add route in App.tsx

Open frontend/src/App.tsx and add the import + route:

```tsx
// Add import at top
import AuthoringPage from './pages/AuthoringPage'

// Add inside your <Routes>
<Route path="/authoring" element={<AuthoringPage />} />
```

## Step 3 — Add nav link in Layout.tsx

Open frontend/src/components/Layout.tsx and add:

```tsx
// Add import
import { FileText } from 'lucide-react'

// Add to your nav items array or wherever your nav links are:
{ path: '/authoring', label: 'Authoring', icon: <FileText /> }
```

## Step 4 — Add backend API endpoints

Your FastAPI backend needs these 3 new endpoints:

### 4a. POST /api/v1/ai/generate-dita-from-jira

```python
# In your backend routes
from fastapi import APIRouter
router = APIRouter()

@router.post("/ai/generate-dita-from-jira")
async def generate_dita_from_jira_endpoint(body: dict):
    issue_key = body.get("issue_key")
    dita_type = body.get("dita_type", "auto")
    
    # Call your existing mcp_server logic directly
    # or call the service functions directly:
    from app.services.jira_client import JiraClient, extract_description_from_issue
    from app.services.doc_retriever_service import retrieve_relevant_docs
    from app.services.dita_knowledge_retriever import retrieve_dita_knowledge
    
    # ... your generation logic ...
    
    return {
        "filename": f"{issue_key}-task.dita",
        "content": "<?xml version...",
        "dita_type": "task",
        "quality_score": 91,
        "quality_breakdown": {
            "structure": 28,
            "content_richness": 25,
            "dita_features": 18,
            "aem_readiness": 20
        },
        "validation": [
            {"label": "XML well-formed", "passing": True},
            {"label": "Required elements present", "passing": True},
            {"label": "id attribute on root", "passing": True},
            {"label": "shortdesc present", "passing": True},
        ],
        "sources_used": [
            {"label": "Experience League", "count": 3, "color": "blue"},
            {"label": "DITA Spec 1.3", "count": 2, "color": "green"},
            {"label": "Expert examples", "count": 1, "color": "purple"},
        ]
    }
```

### 4b. POST /api/v1/jira/search

```python
@router.post("/jira/search")
async def search_jira(body: dict):
    jql = body.get("jql", "")
    max_results = body.get("max_results", 30)
    
    from app.services.jira_dita_fetch_service import fetch_jira_issues
    issues = fetch_jira_issues(jql, max_results=max_results, fetch_comments=False)
    return {"issues": issues}
```

### 4c. GET /api/v1/jira/issue/{issue_key}

```python
@router.get("/jira/issue/{issue_key}")
async def get_jira_issue(issue_key: str):
    from app.services.jira_client import JiraClient, extract_description_from_issue
    jira = JiraClient()
    issue = jira.get_issue(issue_key)
    fields = issue.get("fields", {})
    return {
        "issue_key": issue.get("key"),
        "summary": fields.get("summary", ""),
        "description": extract_description_from_issue(issue),
        "issue_type": fields.get("issuetype", {}).get("name", ""),
        "status": fields.get("status", {}).get("name", ""),
        "priority": fields.get("priority", {}).get("name", ""),
        "labels": fields.get("labels", []),
    }
```

## Step 5 — Run and test

```bash
# Terminal 1 — backend
cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend  
cd frontend && npm run dev

# Open browser
http://localhost:5173/authoring
```

## What you should see

1. Left panel: Jira issues load automatically (My Issues tab)
2. Click any issue → center panel shows Generate button
3. Click Generate → loading animation → DITA appears
4. Right panel shows quality score + validation
5. Use refine bar to improve with AI
6. Upload to AEM button in toolbar

## Troubleshooting

**Issues not loading:**
- Check Jira credentials in Settings
- Check browser console for API errors
- Verify /api/v1/jira/search endpoint exists

**Generate button does nothing:**
- Check /api/v1/ai/generate-dita-from-jira endpoint
- Check backend logs for errors
- Verify MCP server is running

**Quality score shows 0:**
- The endpoint needs to return quality_breakdown object
- Implement validate_dita_file logic in the endpoint
