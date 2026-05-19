"""Chat-first agent plan helpers: plan detection, approval state, and local summaries."""

from __future__ import annotations

import copy
import re
from typing import Any

from app.services.ai_flow_intelligence_service import recommend_recipe
from app.services.chat_tools import RECIPE_TYPE_ALLOWLIST

AGENT_PLAN_KEY = "_agent_plan"
AGENT_EXECUTION_KEY = "_agent_execution"
APPROVAL_STATE_KEY = "_approval_state"

APPROVAL_REQUIRED_TOOLS = frozenset({"create_job", "create_job_from_jira", "fix_dita_xml"})
READ_ONLY_TOOLS = frozenset(
    {
        "find_recipes",
        "search_jira_issues",
        "lookup_dita_spec",
        "review_dita_xml",
        "lookup_aem_guides",
        "search_tenant_knowledge",
        "lookup_output_preset",
        "list_jobs",
        "lookup_dita_attribute",
        "list_indexed_pdfs",
        "generate_native_pdf_config",
        "browse_dataset",
        "get_job_status",
    }
)

_DATASET_REQUEST_PATTERN = re.compile(
    r"\b(generate|create|build|make|run|start|need|want|prepare)\b.*\b(dataset|recipe|sample|test data|xml testing|dita dataset)\b|"
    r"\b(dataset|recipe|sample|test data)\b.*\b(generate|create|build|make|run|start|need|want|prepare)\b",
    re.IGNORECASE,
)
_XML_PAYLOAD_PATTERN = re.compile(
    r"(?s)(<\?xml|<!DOCTYPE|<(?:task|concept|topic|reference|glossentry|bookmap|map)\b)",
    re.IGNORECASE,
)
_XML_FIX_PATTERN = re.compile(
    r"\b(fix|auto-?fix|correct|repair|clean up|improve)\b.*\b(xml|dita|topic|map)\b|"
    r"\b(xml|dita)\b.*\b(fix|auto-?fix|correct|repair|clean up|improve)\b",
    re.IGNORECASE,
)
_SHORT_DEFINITION_PATTERN = re.compile(
    r"(?is)^\s*(what\s+is|what\s+are|define|explain|meaning\s+of)\b.{1,220}$"
)
_DOMAIN_PATTERN = re.compile(
    r"\b(aem guides|\baem\b|experience manager guides|dita|ditamap|topicref|topichead|mapref|navref|keydef|keyref|"
    r"conref|conkeyref|reltable|bookmap|glossentry|subject scheme|reference topic|concept topic|task topic|"
    r"native pdf|output preset|web editor|author view|source view|map editor|oxygen|chunk attribute|processing-role|"
    r"translation workflow|baseline|condition preset)\b",
    re.IGNORECASE,
)
_RESEARCH_QUESTION_PATTERN = re.compile(
    r"\b(how|why|when|where|difference|compare|versus|vs|resolve|required|require|troubleshoot|fix)\b",
    re.IGNORECASE,
)
_RESEARCH_SOURCE_ACTION_PATTERN = re.compile(
    r"\b(search|look\s*up|lookup|find|gather|collect|pull|compare|summari[sz]e|analy[sz]e|"
    r"troubleshoot|debug|fix|resolve)\b",
    re.IGNORECASE,
)
_COMPOUND_RESEARCH_PATTERN = re.compile(
    r"(,|\band\b|\bthen\b).{0,120}\b(how|why|when|where|difference|compare|versus|vs|resolve|required|require|troubleshoot|fix)\b",
    re.IGNORECASE,
)
_NATIVE_PDF_PATTERN = re.compile(r"\b(native pdf|pdf template|pdf preset|pdf config|header/footer|page layout)\b", re.IGNORECASE)
_JIRA_COMPARE_PATTERN = re.compile(r"\b(jira|issue|ticket)\b.*\b(compare|summari[sz]e|analy[sz]e|related)\b", re.IGNORECASE)
_APPROVE_PATTERN = re.compile(
    r"^\s*(approve|approved|continue|run it|go ahead|proceed|yes(?:\s+please)?|do it)\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_SKIP_FIX_PATTERN = re.compile(
    r"\b(skip fix|skip it|review only|don't fix|do not fix|leave it as is)\b",
    re.IGNORECASE,
)
_SHOW_STEP_PATTERN = re.compile(r"\bshow\s+step\s+(\d+)(?:\s+results?)?\b", re.IGNORECASE)

_LIST_BULK_PRESETS_PATTERN = re.compile(
    r"\b(?:list|show)\s+(?:my\s+)?(?:saved\s+)?bulk\s+(?:dataset\s+)?presets?\b",
    re.IGNORECASE,
)
_WHAT_ARE_BULK_PRESETS_PATTERN = re.compile(
    r"\bwhat\s+are\s+my\s+bulk\s+(?:dataset\s+)?presets?\b",
    re.IGNORECASE,
)
_SAVE_BULK_PRESET_WITH_JOB_PATTERN = re.compile(
    r"\bsave\s+bulk\s+preset\s+from\s+job\s+(\S+)\s+as\s+(.+)$",
    re.IGNORECASE,
)
_SAVE_BULK_PRESET_PATTERN = re.compile(
    r"\b(?:save|remember)\s+(?:this\s+)?bulk\s+(?:dataset\s+)?preset\s+as\s+(.+)$",
    re.IGNORECASE,
)
_RUN_BULK_PRESET_PATTERN = re.compile(
    r"\b(?:run|reuse|rerun)\s+bulk\s+preset\s+(.+)$",
    re.IGNORECASE,
)


def _find_latest_dataset_job_id_from_messages(messages: list[dict[str, Any]]) -> str:
    """Latest assistant tool result job_id from create_job or run_bulk_dataset_preset."""
    for message in reversed(messages or []):
        if str(message.get("role") or "") != "assistant":
            continue
        tool_results = message.get("tool_results") or {}
        if not isinstance(tool_results, dict):
            continue
        for key in ("create_job", "create_job_from_jira", "run_bulk_dataset_preset"):
            block = tool_results.get(key)
            if not isinstance(block, dict) or block.get("error"):
                continue
            jid = str(block.get("job_id") or "").strip()
            if jid:
                return jid
    return ""


def _detect_bulk_preset_nl_command(
    user_content: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Chat-only phrases for saved bulk dataset presets (no Builder, no agent plan required)."""
    t = (user_content or "").strip()
    if not t:
        return None

    m_job = _SAVE_BULK_PRESET_WITH_JOB_PATTERN.search(t)
    if m_job:
        jid = (m_job.group(1) or "").strip()
        label = (m_job.group(2) or "").strip().rstrip(".!?")
        if jid and label:
            return {"type": "bulk_preset_save", "label": label, "job_id": jid}

    m_save = _SAVE_BULK_PRESET_PATTERN.search(t)
    if m_save:
        label = (m_save.group(1) or "").strip().rstrip(".!?")
        if label:
            jid = _find_latest_dataset_job_id_from_messages(messages)
            return {"type": "bulk_preset_save", "label": label, "job_id": jid}

    m_run = _RUN_BULK_PRESET_PATTERN.search(t)
    if m_run:
        key = (m_run.group(1) or "").strip().rstrip(".!?")
        if key:
            return {"type": "bulk_preset_run", "label_or_id": key}

    if _LIST_BULK_PRESETS_PATTERN.search(t) or _WHAT_ARE_BULK_PRESETS_PATTERN.search(t):
        return {"type": "bulk_preset_list"}

    return None


def reserved_agent_payload(
    *,
    plan: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
    approval_state: dict[str, Any] | None = None,
    tool_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if plan is not None:
        payload[AGENT_PLAN_KEY] = copy.deepcopy(plan)
    if execution is not None:
        payload[AGENT_EXECUTION_KEY] = copy.deepcopy(execution)
    if approval_state is not None:
        payload[APPROVAL_STATE_KEY] = copy.deepcopy(approval_state)
    for key, value in (tool_results or {}).items():
        payload[key] = value
    return payload


def find_latest_agent_state(
    messages: list[dict[str, Any]],
    *,
    pending_only: bool = False,
) -> dict[str, Any] | None:
    for message in reversed(messages):
        if str(message.get("role") or "") != "assistant":
            continue
        tool_results = message.get("tool_results") or {}
        if not isinstance(tool_results, dict):
            continue
        plan = tool_results.get(AGENT_PLAN_KEY)
        if not isinstance(plan, dict):
            continue
        approval = tool_results.get(APPROVAL_STATE_KEY)
        execution = tool_results.get(AGENT_EXECUTION_KEY)
        if pending_only:
            if isinstance(approval, dict) and str(approval.get("state") or "") == "required":
                return {
                    "message": message,
                    "plan": copy.deepcopy(plan),
                    "approval_state": copy.deepcopy(approval),
                    "execution": copy.deepcopy(execution) if isinstance(execution, dict) else None,
                    "tool_results": copy.deepcopy(tool_results),
                }
            continue
        return {
            "message": message,
            "plan": copy.deepcopy(plan),
            "approval_state": copy.deepcopy(approval) if isinstance(approval, dict) else None,
            "execution": copy.deepcopy(execution) if isinstance(execution, dict) else None,
            "tool_results": copy.deepcopy(tool_results),
        }
    return None


def detect_agent_command(
    user_content: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    text = (user_content or "").strip()
    if not text:
        return None

    show_match = _SHOW_STEP_PATTERN.search(text)
    if show_match:
        state = find_latest_agent_state(messages, pending_only=False)
        if state:
            return {
                "type": "show_step",
                "step_number": max(1, int(show_match.group(1))),
                "state": state,
            }

    bulk = _detect_bulk_preset_nl_command(text, messages)
    if bulk:
        return bulk

    pending = find_latest_agent_state(messages, pending_only=True)
    if not pending:
        return None

    if _APPROVE_PATTERN.match(text):
        return {"type": "approve", "state": pending}
    if _SKIP_FIX_PATTERN.search(text):
        return {"type": "skip_fix", "state": pending}
    return None


def build_agent_plan(
    user_content: str,
    *,
    tenant_id: str = "kone",
) -> dict[str, Any] | None:
    text = (user_content or "").strip()
    if not text:
        return None
    if _looks_like_dataset_request(text):
        return _build_dataset_plan(text)
    if _looks_like_xml_fix_request(text):
        return _build_xml_review_fix_plan(text)
    if _looks_like_research_request(text):
        return _build_research_plan(text, tenant_id=tenant_id)
    return None


def execution_from_plan(plan: dict[str, Any], *, current_step_id: str | None = None) -> dict[str, Any]:
    steps = []
    for step in plan.get("steps") or []:
        steps.append(
            {
                "id": step.get("id"),
                "title": step.get("title"),
                "tool_name": step.get("tool_name"),
                "status": step.get("status"),
                "approval_required": bool(step.get("approval_required")),
                "gate_type": step.get("gate_type") or "",
                "summary": step.get("summary"),
                "note": step.get("note") or "",
                "error": step.get("error") or "",
            }
        )
    return {
        "status": plan.get("status") or "pending",
        "current_step_id": current_step_id,
        "steps": steps,
    }


def mark_step_status(
    plan: dict[str, Any],
    step_id: str,
    status: str,
    *,
    note: str = "",
    error: str = "",
) -> dict[str, Any] | None:
    for step in plan.get("steps") or []:
        if step.get("id") != step_id:
            continue
        step["status"] = status
        if note:
            step["note"] = note
        if error:
            step["error"] = error
        return step
    return None


def resolve_followup_after_step(
    plan: dict[str, Any],
    step_id: str,
    result: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    step = next((candidate for candidate in plan.get("steps") or [] if candidate.get("id") == step_id), None)
    if not step:
        return plan, None

    tool_name = step.get("tool_name")
    if tool_name == "find_recipes":
        _apply_recipe_discovery(plan, result)
    elif tool_name == "review_dita_xml":
        return _apply_review_result(plan, result)
    return plan, None


def build_plan_preview_markdown(
    plan: dict[str, Any],
    *,
    approval_state: dict[str, Any] | None = None,
) -> str:
    lines = [
        "## Plan",
        f"- Goal: {plan.get('goal') or 'Complete the requested work'}",
        f"- Mode: {str(plan.get('mode') or 'multi_step').replace('_', ' ')}",
    ]
    expected_outputs = plan.get("expected_outputs") or []
    if expected_outputs:
        lines.append("- Expected outputs:")
        for item in expected_outputs:
            lines.append(f"  - {item}")
    preview = plan.get("preview") if isinstance(plan.get("preview"), dict) else None
    if isinstance(preview, dict):
        lines.append("")
        lines.append("## Preview")
        summary = str(preview.get("summary") or "").strip()
        if summary:
            lines.append(f"- Summary: {summary}")
        bundle_type = str(preview.get("bundle_type") or "").strip().replace("_", " ")
        if bundle_type:
            lines.append(f"- Bundle type: {bundle_type}")
        topic_family = str(preview.get("topic_family") or "").strip()
        if topic_family:
            lines.append(f"- Topic family: {topic_family}")
        subject = str(preview.get("subject") or "").strip()
        if subject:
            lines.append(f"- Subject: {subject}")
        artifacts = preview.get("artifacts") or []
        if isinstance(artifacts, list) and artifacts:
            lines.append("- Planned artifacts:")
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                label = str(artifact.get("label") or "").strip()
                if label:
                    lines.append(f"  - {label}")
        required_elements = preview.get("required_elements") or []
        if isinstance(required_elements, list) and required_elements:
            lines.append("- Required DITA tags:")
            for item in required_elements:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if name:
                    scope = str(item.get("scope") or "").strip()
                    lines.append(f"  - <{name}>{f' ({scope})' if scope else ''}")
        required_attributes = preview.get("required_attributes") or []
        if isinstance(required_attributes, list) and required_attributes:
            lines.append("- Required attributes:")
            for item in required_attributes:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("attribute_name") or "").strip()
                if not name:
                    continue
                values = [str(value).strip() for value in (item.get("required_values") or []) if str(value).strip()]
                scope = str(item.get("scope") or "").strip()
                rendered = f"@{name}" + (f"={' '.join(values)}" if values else "")
                lines.append(f"  - {rendered}{f' ({scope})' if scope else ''}")
        assumptions = preview.get("assumptions") or []
        if isinstance(assumptions, list) and assumptions:
            lines.append("- Assumptions:")
            for item in assumptions:
                item_text = str(item).strip()
                if item_text:
                    lines.append(f"  - {item_text}")
        warnings = preview.get("warnings") or []
        if isinstance(warnings, list) and warnings:
            lines.append("- Warnings:")
            for item in warnings:
                item_text = str(item).strip()
                if item_text:
                    lines.append(f"  - {item_text}")
        conflicts = preview.get("conflicts") or []
        if isinstance(conflicts, list) and conflicts:
            lines.append("- Constraint conflicts:")
            for item in conflicts:
                if isinstance(item, dict):
                    item_text = str(item.get("message") or "").strip()
                    if item_text:
                        lines.append(f"  - {item_text}")
        clarification_question = str(preview.get("clarification_question") or "").strip()
        if clarification_question:
            lines.append(f"- Clarification needed: {clarification_question}")
    lines.append("")
    lines.append("## Steps")
    for index, step in enumerate(plan.get("steps") or [], start=1):
        status = str(step.get("status") or "pending").replace("_", " ")
        gate_kind = str(step.get("gate_type") or "").strip().lower()
        gate = " (review)" if gate_kind == "review" else " (approval)" if step.get("approval_required") else ""
        lines.append(f"{index}. {step.get('title')}{gate} — {status}")
        if step.get("summary"):
            lines.append(f"   {step.get('summary')}")
        if step.get("note"):
            lines.append(f"   Note: {step.get('note')}")
    if approval_state and str(approval_state.get("state") or "") == "required":
        gate_kind = str(approval_state.get("kind") or "").strip().lower()
        lines.append("")
        lines.append("## Review needed" if gate_kind == "review" else "## Approval needed")
        lines.append(
            str(
                approval_state.get("prompt")
                or (
                    "Reply `approve` or `continue` to run the next reviewed step."
                    if gate_kind == "review"
                    else "Reply `approve` or `continue` to run the next gated step."
                )
            )
        )
        affected = approval_state.get("affected_artifacts") or []
        if affected:
            lines.append("")
            lines.append("Affected artifacts:")
            for item in affected:
                lines.append(f"- {item}")
        lines.append("")
        if gate_kind == "review":
            lines.append("Reply with `approve` or `continue` when you want me to generate the bundle.")
        else:
            lines.append("Reply with `approve`, `continue`, or `skip fix` when you want to proceed.")
    return "\n".join(lines).strip()


def build_step_result_markdown(
    plan: dict[str, Any],
    tool_results: dict[str, dict[str, Any]],
    step_number: int,
) -> str:
    steps = plan.get("steps") or []
    if step_number < 1 or step_number > len(steps):
        return f"I only have {len(steps)} step(s) in the latest plan."
    step = steps[step_number - 1]
    tool_name = str(step.get("tool_name") or "")
    result = tool_results.get(tool_name) or {}
    lines = [
        f"## Step {step_number}",
        f"- Title: {step.get('title')}",
        f"- Status: {step.get('status') or 'pending'}",
    ]
    if step.get("summary"):
        lines.append(f"- Summary: {step.get('summary')}")
    if step.get("note"):
        lines.append(f"- Note: {step.get('note')}")
    if step.get("error"):
        lines.append(f"- Error: {step.get('error')}")
    if not result:
        lines.append("")
        lines.append("No stored tool result is available for this step yet.")
        return "\n".join(lines).strip()

    lines.append("")
    lines.append("## Result")
    rendered = _summarize_tool_result(tool_name, result)
    if rendered:
        lines.extend(f"- {item}" for item in rendered)
    else:
        lines.append("```json")
        lines.append(str(result))
        lines.append("```")
    return "\n".join(lines).strip()


def _agent_tools_used_line(tool_results: dict[str, dict[str, Any]]) -> str:
    """Short italic line listing tools that contributed (for user orientation)."""
    labels = {
        "lookup_aem_guides": "AEM Guides docs",
        "lookup_dita_spec": "DITA spec",
        "lookup_dita_attribute": "DITA attribute lookup",
        "search_tenant_knowledge": "tenant knowledge",
        "generate_native_pdf_config": "Native PDF guidance",
        "search_jira_issues": "Jira",
        "find_recipes": "recipe search",
    }
    used: list[str] = []
    for key, label in labels.items():
        payload = tool_results.get(key) or {}
        if not isinstance(payload, dict) or payload.get("error"):
            continue
        if key == "find_recipes" and not (payload.get("recipes") or []):
            continue
        if key == "lookup_aem_guides" and not (
            (payload.get("results") or []) or _normalized_summary(payload)
        ):
            continue
        if key == "lookup_dita_spec" and not (
            (payload.get("spec_chunks") or []) or _normalized_summary(payload)
        ):
            continue
        used.append(label)
    if not used:
        return ""
    return f"_Based on: {', '.join(used)}._"


def summarize_agent_results_locally(
    user_request: str,
    plan: dict[str, Any],
    tool_results: dict[str, dict[str, Any]],
) -> str:
    tools_line = _agent_tools_used_line(tool_results)
    research_bullets = _collect_research_bullets(tool_results)
    if research_bullets:
        lines = [
            "## At a glance",
            _local_research_short_answer(research_bullets),
        ]
        if tools_line:
            lines.extend(["", tools_line])
        lines.extend(["", "## Details"])
        for bullet in research_bullets[:6]:
            lines.append(f"- {bullet}")
        notes: list[str] = []
        warnings = _collect_unverified_notes(plan, tool_results)
        completed = _completed_source_labels(tool_results)
        if completed:
            notes.append(f"Verified channels: {', '.join(completed)}.")
        if warnings:
            for warning in warnings:
                w = str(warning).strip()
                if w:
                    notes.append(w)
        elif not completed:
            notes.append("Scope is limited to the tool results from this run.")
        if notes:
            lines.extend(["", "### Notes"] + [f"- {n}" for n in notes if n])
        lines.extend(["", "## Sources"])
        sources = _collect_sources(tool_results)
        if sources:
            for source in sources:
                lines.append(f"- {source}")
        else:
            lines.append("- See tool result cards in the chat for full excerpts.")
        return "\n".join(lines).strip()

    lines = [
        "## At a glance",
        _local_short_answer(user_request, plan, tool_results),
    ]
    if tools_line:
        lines.extend(["", tools_line])
    lines.extend(["", "## Details"])
    for step in plan.get("steps") or []:
        title = str(step.get("title") or step.get("tool_name") or "Step")
        status = str(step.get("status") or "pending").replace("_", " ")
        lines.append(f"- {title}: {status}.")
        tool_name = str(step.get("tool_name") or "")
        result = tool_results.get(tool_name) or {}
        for bullet in _summarize_tool_result(tool_name, result)[:2]:
            lines.append(f"  - {bullet}")
    note_lines: list[str] = []
    warnings = _collect_unverified_notes(plan, tool_results)
    if warnings:
        for warning in warnings:
            w = str(warning).strip()
            if w:
                note_lines.append(w)
    else:
        note_lines.append("Answer is limited to completed plan steps and their tool results.")
    if note_lines:
        lines.extend(["", "### Notes"] + [f"- {n}" for n in note_lines if n])
    lines.extend(["", "## Sources"])
    sources = _collect_sources(tool_results)
    if sources:
        for source in sources:
            lines.append(f"- {source}")
    else:
        lines.append("- See tool result cards in the chat for full excerpts.")
    return "\n".join(lines).strip()


def _looks_like_dataset_request(text: str) -> bool:
    return bool(_DATASET_REQUEST_PATTERN.search(text))


def _looks_like_xml_fix_request(text: str) -> bool:
    return bool(_XML_PAYLOAD_PATTERN.search(text) and _XML_FIX_PATTERN.search(text))


def _looks_like_research_request(text: str) -> bool:
    if _SHORT_DEFINITION_PATTERN.match(text):
        return False
    if _looks_like_dataset_request(text) or _looks_like_xml_fix_request(text):
        return False
    if _JIRA_COMPARE_PATTERN.search(text):
        return True
    if not _DOMAIN_PATTERN.search(text):
        return False
    if _NATIVE_PDF_PATTERN.search(text) and _RESEARCH_SOURCE_ACTION_PATTERN.search(text):
        return True
    if _COMPOUND_RESEARCH_PATTERN.search(text):
        return True
    return bool(_RESEARCH_SOURCE_ACTION_PATTERN.search(text) and not text.lower().startswith(("how does ", "how do ", "what is ", "what are ", "explain ")))


def _build_dataset_plan(text: str) -> dict[str, Any]:
    explicit_recipe = _extract_explicit_recipe_type(text)
    pattern = _dataset_pattern(text)
    default_recipe = explicit_recipe or _infer_recipe_from_text(text)
    recommended_recipe, learning_note = recommend_recipe("chat_dataset", pattern, default_recipe)
    recipe_choice = explicit_recipe or recommended_recipe or default_recipe

    steps: list[dict[str, Any]] = []
    if explicit_recipe:
        steps.append(
            {
                "id": "step-1",
                "title": "Start dataset generation",
                "tool_name": "create_job",
                "tool_input": {"recipe_type": recipe_choice},
                "kind": "generate",
                "approval_required": True,
                "status": "pending",
                "summary": f"Create a dataset job with recipe `{recipe_choice}`.",
            }
        )
    else:
        steps.extend(
            [
                {
                    "id": "step-1",
                    "title": "Find the closest matching dataset recipe",
                    "tool_name": "find_recipes",
                    "tool_input": {"query": text, "k": 5},
                    "kind": "read_only",
                    "approval_required": False,
                    "status": "pending",
                    "summary": "Search the available recipe catalog and pick the safest match before generation.",
                },
                {
                    "id": "step-2",
                    "title": "Start dataset generation",
                    "tool_name": "create_job",
                    "tool_input": {"recipe_type": recipe_choice},
                    "kind": "generate",
                    "approval_required": True,
                    "status": "pending",
                    "summary": f"Create the dataset job with the recommended recipe `{recipe_choice}`.",
                    "tentative_recipe": recipe_choice,
                },
            ]
        )
    if learning_note and steps:
        steps[0]["note"] = learning_note
    return {
        "goal": "Generate a dataset safely from chat",
        "mode": "multi_step",
        "requires_approval": True,
        "expected_outputs": [
            "An in-chat dataset status card",
            "A ZIP download action when the dataset is ready",
        ],
        "status": "proposed",
        "resume_tokens": ["approve", "continue", "show step 1 results", "show step 2 results"],
        "user_request": text,
        "steps": steps,
    }


def _build_xml_review_fix_plan(text: str) -> dict[str, Any]:
    xml = text.strip()
    steps = [
        {
            "id": "step-1",
            "title": "Review the provided DITA XML",
            "tool_name": "review_dita_xml",
            "tool_input": {"xml": xml, "context": "Agent review from chat"},
            "kind": "review",
            "approval_required": False,
            "status": "pending",
            "summary": "Score the XML, surface structural issues, and decide whether an auto-fix is warranted.",
        },
        {
            "id": "step-2",
            "title": "Apply an XML auto-fix",
            "tool_name": "fix_dita_xml",
            "tool_input": {"xml": xml, "context": "Approved agentic auto-fix from chat"},
            "kind": "generate",
            "approval_required": True,
            "status": "pending",
            "summary": "Apply the safest structural repairs after review approval.",
        },
    ]
    return {
        "goal": "Review and optionally auto-fix the provided DITA XML",
        "mode": "multi_step",
        "requires_approval": True,
        "expected_outputs": [
            "A quality review snapshot",
            "An optional fixed XML result after approval",
        ],
        "status": "proposed",
        "resume_tokens": ["approve", "continue", "skip fix", "show step 1 results", "show step 2 results"],
        "user_request": text[:500],
        "steps": steps,
    }


def _build_research_plan(text: str, *, tenant_id: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    if _JIRA_COMPARE_PATTERN.search(text):
        steps.append(
            {
                "id": "step-1",
                "title": "Search related Jira issues",
                "tool_name": "search_jira_issues",
                "tool_input": {"query": text},
                "kind": "read_only",
                "approval_required": False,
                "status": "pending",
                "summary": "Pull the closest Jira matches before answering.",
            }
        )

    if _NATIVE_PDF_PATTERN.search(text):
        steps.append(
            {
                "id": f"step-{len(steps) + 1}",
                "title": "Collect Native PDF guidance",
                "tool_name": "generate_native_pdf_config",
                "tool_input": {"query": text},
                "kind": "read_only",
                "approval_required": False,
                "status": "pending",
                "summary": "Gather AEM Guides Native PDF configuration guidance first.",
            }
        )

    steps.extend(
        [
            {
                "id": f"step-{len(steps) + 1}",
                "title": "Search AEM Guides documentation",
                "tool_name": "lookup_aem_guides",
                "tool_input": {"query": text, "k": 5},
                "kind": "read_only",
                "approval_required": False,
                "status": "pending",
                "summary": "Pull Experience League guidance that directly matches the question.",
            },
            {
                "id": f"step-{len(steps) + 1}",
                "title": "Check DITA specification details",
                "tool_name": "lookup_dita_spec",
                "tool_input": {"query": text},
                "kind": "read_only",
                "approval_required": False,
                "status": "pending",
                "summary": "Validate element, attribute, and resolution rules against the DITA spec.",
            },
            {
                "id": f"step-{len(steps) + 1}",
                "title": "Search tenant knowledge",
                "tool_name": "search_tenant_knowledge",
                "tool_input": {"query": text, "k": 5},
                "kind": "read_only",
                "approval_required": False,
                "status": "pending",
                "summary": f"Check uploaded tenant references for workspace `{tenant_id}`.",
            },
        ]
    )
    return {
        "goal": "Research the question with verified sources before answering",
        "mode": "multi_step",
        "requires_approval": False,
        "expected_outputs": [
            "A structured answer based on the completed read-only lookups",
            "Tool result cards for the source lookups",
        ],
        "status": "proposed",
        "resume_tokens": ["show step 1 results", "show step 2 results"],
        "user_request": text,
        "steps": steps,
    }


def _extract_explicit_recipe_type(text: str) -> str | None:
    lowered = text.lower()
    matches = [recipe for recipe in RECIPE_TYPE_ALLOWLIST if recipe in lowered]
    if not matches:
        return None
    return sorted(matches, key=len, reverse=True)[0]


def _infer_recipe_from_text(text: str) -> str:
    lowered = text.lower()
    if "1000" in lowered or "100 kb" in lowered or "100kb" in lowered or "large" in lowered:
        return "large_root_map_1000_topics_100kb"
    if "compact" in lowered and "key" in lowered:
        return "compact_parent_child_key_resolution"
    if any(token in lowered for token in ("conref", "conkeyref", "parent map", "child map", "key resolution", "self reference")):
        return "parent_child_maps_keys_conref_conkeyref_selfrefs"
    return "task_topics"


def _dataset_pattern(text: str) -> str:
    lowered = text.lower()
    if "large" in lowered or "1000" in lowered:
        return "large_scale"
    if "compact" in lowered:
        return "compact"
    if any(token in lowered for token in ("conref", "conkeyref", "key resolution", "parent", "child map")):
        return "enterprise_xml"
    return "generic"


def _apply_recipe_discovery(plan: dict[str, Any], result: dict[str, Any]) -> None:
    recipes = result.get("recipes") or []
    next_step = next((step for step in plan.get("steps") or [] if step.get("tool_name") == "create_job" and step.get("status") == "pending"), None)
    if not next_step:
        return
    chosen_recipe = next_step.get("tool_input", {}).get("recipe_type")
    if isinstance(recipes, list) and recipes:
        top = recipes[0] or {}
        top_recipe = str(top.get("recipe_id") or "").strip()
        if top_recipe:
            next_step["tool_input"]["recipe_type"] = top_recipe
            next_step["summary"] = f"Create the dataset job with the discovered recipe `{top_recipe}`."
            chosen_recipe = top_recipe
    if chosen_recipe:
        next_step["note"] = f"Pending approval for recipe `{chosen_recipe}`."


def _apply_review_result(plan: dict[str, Any], result: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    fix_step = next((step for step in plan.get("steps") or [] if step.get("tool_name") == "fix_dita_xml"), None)
    if not fix_step:
        return plan, None
    validation = result.get("validation_issues") or []
    score = int(result.get("quality_score") or 0)
    if score >= 90 and not validation:
        fix_step["status"] = "skipped"
        fix_step["note"] = "The review found no structural issues that need an auto-fix."
        plan["status"] = "completed"
        return plan, "The XML review did not surface any structural issues that need an auto-fix."
    return plan, None


def _local_short_answer(
    user_request: str,
    plan: dict[str, Any],
    tool_results: dict[str, dict[str, Any]],
) -> str:
    if "generate_dita" in tool_results:
        dita = tool_results.get("generate_dita") or {}
        bundle_summary = str(dita.get("bundle_summary") or dita.get("summary") or "").strip()
        if bundle_summary:
            return bundle_summary
        counts = dita.get("artifact_counts") or {}
        total = counts.get("total_files")
        if total is not None:
            return f"Generated a DITA bundle with {total} file{'s' if total != 1 else ''}."
        jira_id = str(dita.get("jira_id") or "").strip()
        return f"Generated a DITA bundle{f' for {jira_id}' if jira_id else ''}."
    if "create_job" in tool_results or "create_job_from_jira" in tool_results:
        return "The job was prepared from an approval-gated plan and started successfully."
    if "fix_dita_xml" in tool_results:
        changed = bool((tool_results.get("fix_dita_xml") or {}).get("changed"))
        return "I reviewed the XML and applied a safe auto-fix." if changed else "I reviewed the XML and no structural changes were required."
    if "review_dita_xml" in tool_results and plan.get("status") == "awaiting_approval":
        return "I finished the XML review and paused before the auto-fix so you can approve it explicitly."
    if any(key in tool_results for key in ("lookup_aem_guides", "lookup_dita_spec", "search_tenant_knowledge", "generate_native_pdf_config", "search_jira_issues")):
        return "Here is the answer built from the retrieved sources."
    return f"I prepared an agent plan for: {user_request[:120]}"


def _clean_evidence_text(value: str, *, max_len: int = 280) -> str:
    text = " ".join((value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _normalized_summary(result: dict[str, Any]) -> str:
    return _clean_evidence_text(str(result.get("summary") or "").strip(), max_len=220)


def _normalized_warnings(result: dict[str, Any]) -> list[str]:
    warnings = result.get("warnings") or []
    if isinstance(warnings, list):
        return [_clean_evidence_text(str(item).strip(), max_len=220) for item in warnings if str(item).strip()]
    if isinstance(warnings, str) and warnings.strip():
        return [_clean_evidence_text(warnings.strip(), max_len=220)]
    return []


def _normalized_sources(result: dict[str, Any]) -> list[str]:
    sources = result.get("sources") or []
    normalized: list[str] = []
    if not isinstance(sources, list):
        return normalized
    for item in sources:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("title") or item.get("id") or "").strip()
            url = str(item.get("url") or item.get("uri") or "").strip()
            snippet = _clean_evidence_text(str(item.get("snippet") or "").strip(), max_len=140)
            line = label or url
            if label and url:
                line = f"{label} — {url}"
            elif url:
                line = url
            if snippet and snippet not in line:
                line = f"{line}: {snippet}" if line else snippet
            if line:
                normalized.append(line)
        else:
            text = str(item).strip()
            if text:
                normalized.append(_clean_evidence_text(text, max_len=220))
    return normalized


def _collect_research_bullets(tool_results: dict[str, dict[str, Any]]) -> list[str]:
    bullets: list[str] = []
    for tool_name in (
        "lookup_aem_guides",
        "lookup_dita_spec",
        "search_tenant_knowledge",
        "generate_native_pdf_config",
        "search_jira_issues",
    ):
        result = tool_results.get(tool_name) or {}
        summary = _normalized_summary(result)
        if summary:
            bullets.append(summary)

    aem = tool_results.get("lookup_aem_guides") or {}
    for item in (aem.get("results") or [])[:4]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("url") or "").strip()
        snippet = _clean_evidence_text(str(item.get("snippet") or "").strip())
        if title and snippet:
            bullets.append(f"{title}: {snippet}")
        elif title:
            bullets.append(title)

    dita = tool_results.get("lookup_dita_spec") or {}
    for item in (dita.get("spec_chunks") or [])[:3]:
        if not isinstance(item, dict):
            continue
        element_name = str(item.get("element_name") or "").strip()
        text_content = _clean_evidence_text(str(item.get("text_content") or "").strip())
        if element_name and text_content:
            bullets.append(f"DITA spec for {element_name}: {text_content}")
        elif text_content:
            bullets.append(f"DITA specification: {text_content}")
    graph_knowledge = _clean_evidence_text(str(dita.get("graph_knowledge") or "").strip())
    if graph_knowledge:
        bullets.append(f"DITA graph knowledge: {graph_knowledge}")

    tenant = tool_results.get("search_tenant_knowledge") or {}
    for item in (tenant.get("results") or [])[:3]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("doc_type") or "Tenant knowledge").strip()
        content = _clean_evidence_text(str(item.get("content") or "").strip())
        if content:
            bullets.append(f"{label}: {content}")

    pdf = tool_results.get("generate_native_pdf_config") or {}
    short_answer = _clean_evidence_text(str(pdf.get("short_answer") or "").strip())
    if short_answer:
        bullets.append(f"Native PDF guidance: {short_answer}")
    for action in (pdf.get("recommended_actions") or [])[:3]:
        action_text = _clean_evidence_text(str(action or "").strip())
        if action_text:
            bullets.append(f"Recommended action: {action_text}")
    for item in (pdf.get("evidence") or pdf.get("doc_results") or [])[:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("url") or "").strip()
        snippet = _clean_evidence_text(str(item.get("snippet") or "").strip())
        if title and snippet:
            bullets.append(f"{title}: {snippet}")

    jira = tool_results.get("search_jira_issues") or {}
    for item in (jira.get("issues") or [])[:3]:
        if not isinstance(item, dict):
            continue
        issue_key = str(item.get("issue_key") or "").strip()
        summary = _clean_evidence_text(str(item.get("summary") or "").strip(), max_len=180)
        if issue_key and summary:
            bullets.append(f"{issue_key}: {summary}")

    deduped: list[str] = []
    seen: set[str] = set()
    for bullet in bullets:
        normalized = bullet.lower()
        if not bullet or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(bullet)
    return deduped


def _local_research_short_answer(research_bullets: list[str]) -> str:
    if not research_bullets:
        return "Here is the best verified answer I could build from the retrieved sources."
    primary = research_bullets[0]
    if ": " in primary:
        primary = primary.split(": ", 1)[1]
    primary = primary.rstrip(". ")
    return primary + "."


def _summarize_tool_result(tool_name: str, result: dict[str, Any]) -> list[str]:
    if not isinstance(result, dict):
        return []
    if result.get("error"):
        return [f"{tool_name} failed: {result.get('error')}"]
    bullets: list[str] = []
    summary = _normalized_summary(result)
    if summary:
        bullets.append(summary)
    for warning in _normalized_warnings(result):
        if warning not in bullets:
            bullets.append(warning)
    if tool_name == "find_recipes":
        recipes = result.get("recipes") or []
        if not recipes:
            return bullets or ["No matching recipes were returned."]
        top = recipes[0] or {}
        detail_bullets = [f"Top recipe: `{top.get('recipe_id')}`."]
        if top.get("description"):
            detail_bullets.append(str(top.get("description")))
        return bullets + [item for item in detail_bullets if item not in bullets]
    if tool_name in ("create_job", "create_job_from_jira"):
        recipe_type = result.get("recipe_type")
        job_id = result.get("job_id")
        detail_bullets = [
            f"Started recipe `{recipe_type}`." if recipe_type else "Started a dataset generation job.",
            f"Job ID: `{job_id}`." if job_id else "The in-chat dataset card will track progress.",
        ]
        if tool_name == "create_job_from_jira":
            jk = str(result.get("jira_key") or "").strip()
            if jk:
                detail_bullets.append(f"Jira: `{jk}`.")
        return bullets + [item for item in detail_bullets if item not in bullets]
    if tool_name == "generate_dita":
        detail_bullets: list[str] = []
        bundle_summary = str(result.get("bundle_summary") or "").strip()
        if bundle_summary and bundle_summary not in bullets:
            detail_bullets.append(bundle_summary)
        artifact_counts = result.get("artifact_counts") or {}
        total_files = artifact_counts.get("total_files")
        map_files = artifact_counts.get("map_files")
        topic_files = artifact_counts.get("topic_files")
        if total_files is not None:
            counts_parts = [f"total files: {total_files}"]
            if map_files is not None:
                counts_parts.append(f"map files: {map_files}")
            if topic_files is not None:
                counts_parts.append(f"topic files: {topic_files}")
            detail_bullets.append("Bundle counts: " + ", ".join(counts_parts) + ".")
        representative_files = [
            str(item).strip() for item in (result.get("representative_files") or []) if str(item).strip()
        ]
        if representative_files:
            detail_bullets.append(f"Representative files: {', '.join(representative_files[:5])}.")
        resolution_warning = str(result.get("resolution_warning") or "").strip()
        if resolution_warning:
            detail_bullets.append(f"Warning: {resolution_warning}")
        return bullets + [item for item in detail_bullets if item not in bullets]
    if tool_name == "review_dita_xml":
        score = result.get("quality_score")
        issues = result.get("validation_issues") or []
        detail_bullets = [f"Quality score: {score}." if score is not None else "Review completed."]
        detail_bullets.append(f"Validation issues found: {len(issues)}.")
        return bullets + [item for item in detail_bullets if item not in bullets]
    if tool_name == "fix_dita_xml":
        changed = bool(result.get("changed"))
        change_summary = str(result.get("change_summary") or "").strip()
        detail_bullets = ["Auto-fix applied." if changed else "No XML changes were needed."]
        if change_summary:
            detail_bullets.append(change_summary)
        return bullets + [item for item in detail_bullets if item not in bullets]
    if tool_name == "generate_native_pdf_config":
        short_answer = str(result.get("short_answer") or "").strip()
        if short_answer and short_answer not in bullets:
            bullets.append(short_answer)
        actions = [str(item).strip() for item in (result.get("recommended_actions") or []) if str(item).strip()]
        if actions:
            action_line = f"Recommended next step: {actions[0]}."
            if action_line not in bullets:
                bullets.append(action_line)
        evidence = result.get("evidence") or result.get("doc_results") or []
        titles = [str(item.get("title") or item.get("url") or "").strip() for item in evidence[:3] if isinstance(item, dict)]
        if titles:
            verified_line = f"Verified against: {', '.join(title for title in titles if title)}."
            if verified_line not in bullets:
                bullets.append(verified_line)
        if bullets:
            return bullets
        return ["No Native PDF guidance was retrieved."]
    if tool_name == "lookup_aem_guides":
        results = result.get("results") or result.get("doc_results") or []
        if not results:
            return bullets or ["No matching AEM Guides documentation was found."]
        titles = [str(item.get("title") or item.get("url") or "").strip() for item in results[:3] if isinstance(item, dict)]
        detail = f"Relevant Adobe docs: {', '.join(title for title in titles if title)}."
        return bullets + ([detail] if detail not in bullets else [])
    if tool_name == "lookup_dita_spec":
        element_name = str(result.get("element_name") or "").strip()
        content_model_summary = str(result.get("content_model_summary") or "").strip()
        placement_summary = str(result.get("placement_summary") or "").strip()
        if content_model_summary and content_model_summary not in bullets:
            bullets.append(content_model_summary)
        if placement_summary and placement_summary not in bullets:
            bullets.append(placement_summary)
        allowed_children = [str(item).strip() for item in (result.get("allowed_children") or []) if str(item).strip()]
        if element_name and allowed_children:
            detail = f"Allowed children for `<{element_name}>`: {', '.join(allowed_children[:12])}."
            if detail not in bullets:
                bullets.append(detail)
        parent_elements = [str(item).strip() for item in (result.get("parent_elements") or []) if str(item).strip()]
        if element_name and parent_elements:
            detail = f"`<{element_name}>` can appear inside {', '.join(parent_elements[:12])}."
            if detail not in bullets:
                bullets.append(detail)
        chunks = result.get("spec_chunks") or []
        if not chunks and not bullets:
            return bullets or ["No DITA spec excerpts were returned."]
        if chunks:
            names = [str(item.get("element_name") or "").strip() for item in chunks[:3] if isinstance(item, dict)]
            detail = f"Relevant DITA spec elements: {', '.join(name for name in names if name)}."
            if detail not in bullets:
                bullets.append(detail)
        return bullets
    if tool_name == "search_tenant_knowledge":
        results = result.get("results") or []
        indexed_count = result.get("indexed_doc_count")
        if not results:
            return bullets or [f"No tenant matches found. Indexed docs: {indexed_count or 0}."]
        labels = [str(item.get("label") or "").strip() for item in results[:3] if isinstance(item, dict)]
        detail = f"Tenant knowledge hits: {', '.join(label for label in labels if label)}."
        return bullets + ([detail] if detail not in bullets else [])
    if tool_name == "search_jira_issues":
        issues = result.get("issues") or []
        if not issues:
            return bullets or ["No Jira issues matched the request."]
        labels = [f"{issue.get('issue_key')}: {issue.get('summary')}" for issue in issues[:3] if isinstance(issue, dict)]
        return bullets + [label for label in labels if label not in bullets]
    if tool_name == "list_jobs":
        jobs = result.get("jobs") or []
        detail = f"Recent jobs returned: {len(jobs)}."
        return bullets + ([detail] if detail not in bullets else [])
    if tool_name == "browse_dataset":
        if result.get("file_path"):
            detail = f"Opened `{result.get('file_path')}` from the dataset."
            return bullets + ([detail] if detail not in bullets else [])
        detail = f"Dataset contains {result.get('total_files') or 0} files."
        return bullets + ([detail] if detail not in bullets else [])
    return bullets


def _collect_unverified_notes(plan: dict[str, Any], tool_results: dict[str, dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for step in plan.get("steps") or []:
        if step.get("status") == "failed" and step.get("error"):
            notes.append(str(step.get("error")))
        if step.get("status") == "skipped" and step.get("note"):
            notes.append(str(step.get("note")))
    generate_dita = tool_results.get("generate_dita") or {}
    resolution_warning = str(generate_dita.get("resolution_warning") or "").strip()
    if resolution_warning:
        notes.append(resolution_warning)
    if "search_tenant_knowledge" in tool_results:
        tenant = tool_results.get("search_tenant_knowledge") or {}
        if not tenant.get("results"):
            notes.append("No tenant-specific evidence was returned, so the answer leans on shared sources only.")
    return notes[:4]


def _completed_source_labels(tool_results: dict[str, dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    if _normalized_sources(tool_results.get("lookup_aem_guides") or {}):
        labels.append("AEM Guides documentation")
    if _normalized_sources(tool_results.get("lookup_dita_spec") or {}):
        labels.append("DITA specification excerpts")
    if _normalized_sources(tool_results.get("search_tenant_knowledge") or {}):
        labels.append("tenant knowledge")
    native_pdf = tool_results.get("generate_native_pdf_config") or {}
    if _normalized_sources(native_pdf) or _normalized_summary(native_pdf) or native_pdf.get("evidence") or native_pdf.get("doc_results") or native_pdf.get("short_answer"):
        labels.append("Native PDF guidance")
    if _normalized_sources(tool_results.get("search_jira_issues") or {}):
        labels.append("Jira issue matches")
    return labels


def _source_display_and_key(line: str) -> tuple[str, str]:
    """Return (dedupe_key, trimmed display). Prefer URL as key when present."""
    raw = (line or "").strip()
    if not raw:
        return "", ""
    m = re.search(r"https?://[^\s)>\]}\"']+", raw)
    key = m.group(0).strip().rstrip(".,);") if m else re.sub(r"\s+", " ", raw.lower())[:160]
    display = raw if len(raw) <= 220 else raw[:217] + "..."
    return key, display


def _collect_sources(tool_results: dict[str, dict[str, Any]]) -> list[str]:
    sources: list[str] = []
    for tool_name in (
        "lookup_aem_guides",
        "lookup_dita_spec",
        "search_tenant_knowledge",
        "generate_native_pdf_config",
        "search_jira_issues",
        "find_recipes",
        "lookup_dita_attribute",
    ):
        for item in _normalized_sources(tool_results.get(tool_name) or {}):
            sources.append(item)
    aem = tool_results.get("lookup_aem_guides") or {}
    for item in (aem.get("results") or [])[:4]:
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("url") or "").strip()
            url = str(item.get("url") or "").strip()
            if title and url:
                sources.append(f"{title} — {url}")
            elif url:
                sources.append(url)
    pdf_cfg = tool_results.get("generate_native_pdf_config") or {}
    for item in (pdf_cfg.get("evidence") or pdf_cfg.get("doc_results") or [])[:4]:
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("url") or "").strip()
            url = str(item.get("url") or "").strip()
            if title and url:
                sources.append(f"{title} — {url}")
            elif url:
                sources.append(url)
    jira = tool_results.get("search_jira_issues") or {}
    for item in (jira.get("issues") or [])[:3]:
        if isinstance(item, dict):
            label = str(item.get("issue_key") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if label:
                sources.append(f"{label} — {summary}" if summary else label)
    by_key: dict[str, str] = {}
    order: list[str] = []
    for line in sources:
        key, display = _source_display_and_key(line)
        if not key:
            continue
        if key not in by_key:
            by_key[key] = display
            order.append(key)
    return [by_key[k] for k in order[:6]]
