"""JIRA DITA Issue Analysis service - orchestrates fetch, LLM analysis, and dataset storage."""
import json
from collections import Counter
from pathlib import Path
from typing import Optional

from backend.app.storage import get_storage
from backend.app.services.jira_dita_fetch_service import fetch_jira_issues
from backend.app.services.llm_analyzer import normalize_issue_text, analyze_issue
from backend.app.services.dataset_generator import generate_dataset_record
from backend.app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

DATASET_SUBDIR = "datasets"
JIRA_DITA_ANALYSIS_DIR = "jira_dita_analysis"
RECORDS_FILENAME = "records.jsonl"


def _get_records_path() -> Path:
    """Path for records.jsonl."""
    storage = get_storage()
    return storage.base_path / DATASET_SUBDIR / JIRA_DITA_ANALYSIS_DIR / RECORDS_FILENAME


async def run_jira_dita_analysis(
    jql: str,
    max_issues: int = 50,
    append: bool = True,
) -> dict:
    """
    Run the full pipeline: fetch -> normalize -> analyze -> generate -> store.
    Returns {records_count, categories_distribution, dataset_path}.
    """
    records_path = _get_records_path()
    records_path.parent.mkdir(parents=True, exist_ok=True)

    issues = fetch_jira_issues(jql, max_results=max_issues)
    if not issues:
        return {
            "records_count": 0,
            "categories_distribution": {},
            "dataset_path": str(records_path),
        }

    records = []
    categories: list[str] = []

    for issue in issues:
        issue_key = issue.get("issue_key", "")
        issue_text = normalize_issue_text(issue)
        if not issue_text or issue_text == "No content":
            continue
        llm_result = await analyze_issue(issue_text, issue_key)
        if not llm_result:
            continue
        record = generate_dataset_record(issue, llm_result)
        if record:
            records.append(record)
            cat = record.get("category", "unknown")
            if cat:
                categories.append(cat)

    if not records:
        return {
            "records_count": 0,
            "categories_distribution": {},
            "dataset_path": str(records_path),
        }

    categories_distribution = dict(Counter(categories))

    mode = "a" if append else "w"
    with open(records_path, mode, encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info_structured(
        "JIRA DITA analysis completed",
        extra_fields={
            "records_count": len(records),
            "categories": categories_distribution,
            "dataset_path": str(records_path),
        },
    )

    return {
        "records_count": len(records),
        "categories_distribution": categories_distribution,
        "dataset_path": str(records_path),
    }
