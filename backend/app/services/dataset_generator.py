"""Dataset generator for JIRA DITA analysis - sanitize and build records."""
import re
from typing import Any


def _prefix_ids_in_xml(xml_str: str, prefix: str) -> str:
    """Prefix id= attributes with {prefix}_ to avoid duplicate IDs across issues."""
    if not xml_str or not isinstance(xml_str, str):
        return xml_str
    # Match id="value" and id='value'
    def repl_double(m: re.Match) -> str:
        return f'id="{prefix}_{m.group(1)}"'
    def repl_single(m: re.Match) -> str:
        return f"id='{prefix}_{m.group(1)}'"
    result = re.sub(r'id="([^"]+)"', repl_double, xml_str)
    result = re.sub(r"id='([^']+)'", repl_single, result)
    return result


def sanitize_dataset_example(dataset_example: dict, issue_key: str) -> dict:
    """
    Ensure no duplicate IDs in generated DITA. Prefix IDs with {issue_key}_.
    Returns sanitized dataset_example dict.
    """
    if not dataset_example or not isinstance(dataset_example, dict):
        return {}
    prefix = (issue_key or "el").replace("-", "_")
    out = {}
    for key in ("map", "topic", "glossary", "subject_scheme"):
        val = dataset_example.get(key)
        if val and isinstance(val, str) and val.strip():
            out[key] = _prefix_ids_in_xml(val.strip(), prefix)
        else:
            out[key] = ""
    return out


def generate_dataset_record(issue: dict, llm_result: dict) -> dict:
    """
    Build final record with sanitized dataset_example.
    Returns dict suitable for JSONL output.
    """
    if not issue or not isinstance(issue, dict):
        return {}
    issue_key = issue.get("issue_key", "")
    summary = issue.get("summary", "")
    category = (llm_result.get("category") or "").strip() or "unknown"
    dita_features = llm_result.get("dita_features")
    if not isinstance(dita_features, list):
        dita_features = []
    root_cause = (llm_result.get("root_cause") or "").strip()
    fix = (llm_result.get("fix") or "").strip()
    dataset_example = llm_result.get("dataset_example")
    if not isinstance(dataset_example, dict):
        dataset_example = {}
    dataset_example = sanitize_dataset_example(dataset_example, issue_key)

    return {
        "issue_key": issue_key,
        "summary": summary,
        "category": category,
        "dita_features": dita_features,
        "root_cause": root_cause,
        "fix": fix,
        "dataset_example": dataset_example,
    }
