"""
THE MISSING ENDPOINT — add this to:
backend/app/api/v1/routes/ai_dataset.py

OR create a new file:
backend/app/api/v1/routes/dita_authoring.py
and register in router.py:
  from app.api.v1.routes import dita_authoring
  api_router.include_router(dita_authoring.router, tags=["dita-authoring"])
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import xml.etree.ElementTree as ET

router = APIRouter()


class GenerateDitaRequest(BaseModel):
    issue_key: str
    dita_type: str = "auto"
    issue: Optional[dict] = None


class GenerateDitaResponse(BaseModel):
    filename: str
    content: str
    dita_type: str
    quality_score: int
    quality_breakdown: dict
    validation: list
    sources_used: list


@router.post("/ai/generate-dita-from-jira", response_model=GenerateDitaResponse)
async def generate_dita_from_jira(body: GenerateDitaRequest):
    """
    THE CORE ENDPOINT — Generate spec-compliant DITA from a Jira issue.

    Called by the Authoring UI Generate button.

    Steps:
    1. Fetch Jira issue (from body or API)
    2. Query RAG context (DITA spec + Experience League)
    3. Generate DITA XML using LLM
    4. Validate and score
    5. Return structured response
    """
    try:
        from app.services.jira_client import JiraClient, extract_description_from_issue
        from app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt
        from app.services.dita_knowledge_retriever import (
            retrieve_dita_knowledge,
            retrieve_dita_graph_knowledge,
        )

        issue_key = body.issue_key

        # ── Step 1: Get issue data ────────────────────────────────────────────
        issue = body.issue or {}

        if not issue.get("summary"):
            try:
                jira   = JiraClient()
                raw    = jira.get_issue(issue_key)
                fields = raw.get("fields", {})
                desc   = extract_description_from_issue(raw)
                comments = jira.get_issue_comments(issue_key)
                issue = {
                    "issue_key":   raw.get("key"),
                    "summary":     fields.get("summary", ""),
                    "description": desc,
                    "issue_type":  fields.get("issuetype", {}).get("name", ""),
                    "status":      fields.get("status", {}).get("name", ""),
                    "priority":    fields.get("priority", {}).get("name", ""),
                    "labels":      fields.get("labels", []),
                    "comments":    [
                        {"author": c.get("author", ""), "body_text": c.get("body_text", "")}
                        for c in comments[:5]
                    ],
                }
            except Exception as e:
                raise ValueError(f"Failed to fetch Jira issue {issue_key}: {e}")

        summary    = issue.get("summary", "")
        desc       = issue.get("description", "")
        issue_type = issue.get("issue_type", "")
        labels     = issue.get("labels", [])
        comments   = issue.get("comments", [])

        # ── Step 2: Detect DITA type ──────────────────────────────────────────
        dita_type = body.dita_type
        if dita_type == "auto":
            dita_type = _detect_dita_type(issue_type, labels, summary, desc)

        # ── Step 3: RAG context ───────────────────────────────────────────────
        query = f"{summary} {desc[:300]}"
        sources_used = []

        el_docs    = retrieve_relevant_docs(query=query, k=3)
        el_text    = format_docs_for_prompt(el_docs) if el_docs else ""
        if el_docs:
            sources_used.append({
                "label": "Experience League",
                "count": len(el_docs),
                "color": "blue",
            })

        spec_chunks = retrieve_dita_knowledge(query_text=query, k=3)
        spec_text   = "\n---\n".join(
            (c.get("text_content") or "")[:500]
            for c in spec_chunks
        ) if spec_chunks else ""
        if spec_chunks:
            sources_used.append({
                "label": "DITA Spec 1.3",
                "count": len(spec_chunks),
                "color": "green",
            })

        graph_text = retrieve_dita_graph_knowledge(
            element_hint=f"{dita_type} {summary}"
        ) or ""

        # ── Step 4: Build generation prompt ──────────────────────────────────
        comment_text = "\n".join(
            f"{c.get('author', 'User')}: {c.get('body_text', '')[:200]}"
            for c in comments[:5]
            if c.get("body_text")
        )

        root_id  = issue_key.lower().replace("-", "_")
        filename = f"{issue_key.lower()}-{dita_type}.dita"

        # ── Step 5: Generate via LLM ──────────────────────────────────────────
        from app.services.llm_service import generate_text, is_llm_available

        if is_llm_available():
            content = await _generate_with_llm(
                issue_key=issue_key,
                summary=summary,
                description=desc,
                issue_type=issue_type,
                labels=labels,
                comment_text=comment_text,
                dita_type=dita_type,
                root_id=root_id,
                el_text=el_text,
                spec_text=spec_text,
                graph_text=graph_text,
            )
            sources_used.append({"label": "LLM generation", "count": 1, "color": "purple"})
        else:
            # Fallback — structured template generation (no LLM needed)
            content = _generate_from_template(
                issue_key=issue_key,
                summary=summary,
                description=desc,
                comment_text=comment_text,
                dita_type=dita_type,
                root_id=root_id,
                labels=labels,
            )

        # ── Step 6: Validate and score ────────────────────────────────────────
        validation      = _validate_dita(content, dita_type)
        quality_score   = _score_quality(content, dita_type)
        quality_breakdown = _score_breakdown(content, dita_type)

        # ── Step 7: Enrich if needed ──────────────────────────────────────────
        try:
            from app.services.dita_enrichment_service import _enrich_topic_file
            import tempfile, os
            from pathlib import Path
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.dita', delete=False, encoding='utf-8'
            ) as f:
                f.write(content)
                tmp_path = f.name
            _enrich_topic_file(Path(tmp_path))
            content = Path(tmp_path).read_text(encoding='utf-8')
            os.unlink(tmp_path)
        except Exception:
            pass  # enrichment is best-effort

        return GenerateDitaResponse(
            filename=filename,
            content=content,
            dita_type=dita_type,
            quality_score=quality_score,
            quality_breakdown=quality_breakdown,
            validation=validation,
            sources_used=sources_used,
        )

    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# ── LLM generation ────────────────────────────────────────────────────────────

async def _generate_with_llm(
    issue_key, summary, description, issue_type, labels,
    comment_text, dita_type, root_id,
    el_text, spec_text, graph_text,
) -> str:
    from app.services.llm_service import generate_text

    VALID_SECTIONS = {
        "task":      "shortdesc, prereq (optional), context (optional), steps (required), result (optional), note (optional)",
        "concept":   "shortdesc, conbody with p and section elements, example (optional)",
        "reference": "shortdesc, refbody with section and/or properties table",
        "glossentry": "glossterm, glossdef",
    }

    DOCTYPES = {
        "task":      '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">',
        "concept":   '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">',
        "reference": '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">',
        "glossentry":'<!DOCTYPE glossentry PUBLIC "-//OASIS//DTD DITA Glossary Entry//EN" "glossentry.dtd">',
    }

    system = f"""You are a DITA 1.3 expert technical writer.
Generate a complete, spec-compliant DITA {dita_type} topic XML.
Output ONLY the XML — no explanation, no markdown, no code blocks.

DITA 1.3 rules for {dita_type}:
- Valid sections: {VALID_SECTIONS.get(dita_type, 'shortdesc, body')}
- Root element: <{dita_type} id="{root_id}" xml:lang="en-US">
- DOCTYPE: {DOCTYPES.get(dita_type, '')}
- Every <step> must have <cmd> as first child
- <shortdesc> is required
- Content must reflect the actual Jira issue — not generic"""

    user = f"""Jira Issue:
Key:         {issue_key}
Summary:     {summary}
Type:        {issue_type}
Labels:      {', '.join(labels) or 'None'}
Description: {description[:1500]}
Comments:    {comment_text or 'None'}

AEM Guides Context:
{el_text[:800] if el_text else 'Not available'}

DITA Spec Rules:
{spec_text[:600] if spec_text else 'Not available'}

Element Nesting:
{graph_text[:400] if graph_text else 'Not available'}

Generate complete DITA 1.3 {dita_type} XML now.
Start with: <?xml version="1.0" encoding="UTF-8"?>
Output XML only:"""

    content = await generate_text(
        system_prompt=system,
        user_prompt=user,
        max_tokens=2000,
        step_name="dita_authoring_generate",
    )

    # Clean up any markdown code blocks if LLM added them
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(
            l for l in lines
            if not l.strip().startswith("```")
        ).strip()

    return content


# ── Template fallback (no LLM needed) ────────────────────────────────────────

def _generate_from_template(
    issue_key, summary, description, comment_text,
    dita_type, root_id, labels,
) -> str:
    """
    Generate DITA from a template when LLM is not available.
    Uses the actual issue content — not Lorem Ipsum.
    """
    from datetime import datetime

    today = datetime.utcnow().strftime("%Y-%m-%d")
    # Clean description for XML
    desc_clean = (description or "")[:500].replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
    summary_clean = summary.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")

    if dita_type == "task":
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">
<task id="{root_id}" xml:lang="en-US">
  <title>{summary_clean}</title>
  <shortdesc>{summary_clean[:120]}</shortdesc>
  <prolog>
    <metadata>
      <othermeta name="author" content="AEM Guides Dataset Studio"/>
      <othermeta name="created" content="{today}"/>
      <othermeta name="jira-key" content="{issue_key}"/>
    </metadata>
  </prolog>
  <taskbody>
    <context>
      <p>{desc_clean or 'See Jira issue ' + issue_key + ' for full context.'}</p>
    </context>
    <steps>
      <step>
        <cmd>Review the issue description in Jira issue {issue_key}.</cmd>
      </step>
      <step>
        <cmd>Apply the fix described in the issue.</cmd>
        <info>
          <p>{comment_text[:300] if comment_text else 'Refer to comments in ' + issue_key}</p>
        </info>
      </step>
      <step>
        <cmd>Verify the fix resolves the reported issue.</cmd>
      </step>
    </steps>
    <result>
      <p>The issue described in {issue_key} is resolved.</p>
    </result>
  </taskbody>
</task>"""

    elif dita_type == "concept":
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="{root_id}" xml:lang="en-US">
  <title>{summary_clean}</title>
  <shortdesc>{summary_clean[:120]}</shortdesc>
  <prolog>
    <metadata>
      <othermeta name="author" content="AEM Guides Dataset Studio"/>
      <othermeta name="created" content="{today}"/>
      <othermeta name="jira-key" content="{issue_key}"/>
    </metadata>
  </prolog>
  <conbody>
    <p>{desc_clean or 'Content from Jira issue ' + issue_key}</p>
    <section>
      <title>Details</title>
      <p>{comment_text[:400] if comment_text else 'See ' + issue_key + ' for full details.'}</p>
    </section>
  </conbody>
</concept>"""

    elif dita_type == "reference":
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">
<reference id="{root_id}" xml:lang="en-US">
  <title>{summary_clean}</title>
  <shortdesc>{summary_clean[:120]}</shortdesc>
  <prolog>
    <metadata>
      <othermeta name="author" content="AEM Guides Dataset Studio"/>
      <othermeta name="created" content="{today}"/>
      <othermeta name="jira-key" content="{issue_key}"/>
    </metadata>
  </prolog>
  <refbody>
    <section>
      <title>Description</title>
      <p>{desc_clean or 'Reference content from ' + issue_key}</p>
    </section>
  </refbody>
</reference>"""

    else:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="{root_id}" xml:lang="en-US">
  <title>{summary_clean}</title>
  <shortdesc>{summary_clean[:120]}</shortdesc>
  <body>
    <p>{desc_clean or 'Content from Jira issue ' + issue_key}</p>
  </body>
</topic>"""


# ── Topic type detection ──────────────────────────────────────────────────────

def _detect_dita_type(issue_type: str, labels: list, summary: str, desc: str) -> str:
    itype = issue_type.lower()
    text  = f"{summary} {desc} {' '.join(labels)}".lower()

    if any(l.lower() in ("task", "howto", "procedure") for l in labels):
        return "task"
    if any(l.lower() in ("concept", "overview", "explanation") for l in labels):
        return "concept"
    if any(l.lower() in ("reference", "api", "syntax") for l in labels):
        return "reference"
    if any(l.lower() in ("glossary", "term") for l in labels):
        return "glossentry"

    if any(x in itype for x in ("bug", "defect", "task", "subtask")):
        return "task"
    if any(x in itype for x in ("story", "epic", "feature")):
        return "concept"

    task_score    = sum(1 for s in ("how to", "configure", "install", "fix", "resolve", "steps") if s in text)
    concept_score = sum(1 for s in ("what is", "overview", "understand", "about", "introduction") if s in text)
    ref_score     = sum(1 for s in ("api", "syntax", "parameters", "reference", "specification") if s in text)

    if ref_score > concept_score and ref_score > task_score:
        return "reference"
    if concept_score > task_score:
        return "concept"
    return "task"


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_dita(content: str, dita_type: str) -> list:
    checks = []
    try:
        ET.fromstring(content.encode("utf-8"))
        checks.append({"label": "XML well-formed", "passing": True})
    except ET.ParseError as e:
        checks.append({"label": f"XML parse error: {str(e)[:60]}", "passing": False})
        return checks

    checks.append({"label": "id attribute on root", "passing": 'id="' in content})
    checks.append({"label": "shortdesc present",     "passing": "<shortdesc" in content})
    checks.append({"label": "xml:lang present",      "passing": "xml:lang=" in content})

    if dita_type == "task":
        checks.append({"label": "taskbody present", "passing": "<taskbody" in content})
        checks.append({"label": "steps present",    "passing": "<steps" in content})
        checks.append({"label": "cmd in steps",     "passing": "<cmd" in content})
    elif dita_type == "concept":
        checks.append({"label": "conbody present",  "passing": "<conbody" in content})
    elif dita_type == "reference":
        checks.append({"label": "refbody present",  "passing": "<refbody" in content})

    return checks


# ── Quality scoring ───────────────────────────────────────────────────────────

def _score_quality(content: str, dita_type: str) -> int:
    bd = _score_breakdown(content, dita_type)
    return sum(bd.values())


def _score_breakdown(content: str, dita_type: str) -> dict:
    structure = 0
    if "<shortdesc" in content:   structure += 8
    if 'id="'       in content:   structure += 7
    if "<prolog"    in content:   structure += 5
    if "xml:lang="  in content:   structure += 5
    if dita_type == "task"      and "<taskbody" in content: structure += 5
    if dita_type == "concept"   and "<conbody"  in content: structure += 5
    if dita_type == "reference" and "<refbody"  in content: structure += 5

    richness = 0
    if "<example"   in content: richness += 10
    if "<note"      in content: richness += 5
    if "<codeblock" in content: richness += 10
    if dita_type == "task" and "<context" in content: richness += 5

    features = 0
    if "keyref=" in content: features += 5
    if "conref=" in content: features += 5
    if "<xref"   in content: features += 5
    if "<fig"    in content: features += 5

    aem = 0
    if "xml:lang="   in content: aem += 7
    if len(content) > 500:        aem += 5
    if "<shortdesc"  in content:  aem += 5
    if "<prolog"     in content:  aem += 3

    return {
        "structure":        min(structure, 30),
        "content_richness": min(richness,  30),
        "dita_features":    min(features,  20),
        "aem_readiness":    min(aem,       20),
    }


# ── Refine endpoint ───────────────────────────────────────────────────────────

class RefineDitaRequest(BaseModel):
    filename: str
    current_content: str
    instruction: str


@router.post("/ai/refine-dita")
async def refine_dita(body: RefineDitaRequest):
    """
    Refine existing DITA content with AI instruction.
    Called by the AI Refine bar at the bottom of DitaEditor.
    """
    try:
        from app.services.llm_service import generate_text, is_llm_available

        if not is_llm_available():
            from fastapi import HTTPException
            raise HTTPException(
                status_code=503,
                detail="LLM not available. Configure ANTHROPIC_API_KEY in .env"
            )

        system = """You are a DITA 1.3 expert. Refine the provided DITA XML
according to the instruction. Output ONLY the complete updated XML.
Keep all existing content unless the instruction says to remove something.
Maintain DITA 1.3 compliance throughout."""

        user = f"""Current DITA content:
{body.current_content}

Instruction: {body.instruction}

Output the complete updated DITA XML only:"""

        content = await generate_text(
            system_prompt=system,
            user_prompt=user,
            max_tokens=2000,
            step_name="dita_refine",
        )

        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(l for l in lines if not l.strip().startswith("```")).strip()

        # Detect dita type from content
        dita_type = "task"
        for t in ("concept", "reference", "glossentry", "task"):
            if f"<{t}" in content:
                dita_type = t
                break

        issue_key = body.filename.split("-")[0].upper() + "-" + body.filename.split("-")[1].split(".")[0] if "-" in body.filename else "unknown"

        return {
            "filename":          body.filename,
            "content":           content,
            "dita_type":         dita_type,
            "quality_score":     _score_quality(content, dita_type),
            "quality_breakdown": _score_breakdown(content, dita_type),
            "validation":        _validate_dita(content, dita_type),
            "sources_used":      [{"label": "LLM refinement", "count": 1, "color": "purple"}],
        }

    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))
