"""Small stdlib helpers shared by authoring scaffolds and their gates."""

import re


AUTHOR_CONFIRM = "AUTHOR MUST CONFIRM"


def pending_review(record):
    """An untouched placeholder is not an investigation or a reviewed decision."""
    return record.get("author_review_required", False) is not False or any(
        AUTHOR_CONFIRM.casefold() in str(record.get(field, "")).casefold()
        for field in ("reason", "review_note", "note")
    )


def next_id(records, field, prefix):
    """Append IDs, never renumber authored records or reuse a removed middle ID."""
    numbers = [int(match.group(1)) for row in records
               if (match := re.fullmatch(re.escape(prefix) + r"-(\d+)", str(row.get(field, ""))))]
    return f"{prefix}-{max(numbers, default=0) + 1:02d}"


def object_list(value, name):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{name} must be a list of objects")
    return value


def strings(value, name):
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return list(dict.fromkeys(value))
