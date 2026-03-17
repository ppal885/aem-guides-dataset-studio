"""
DITA utility functions for ID generation and validation.
"""
import hashlib
import re
from typing import Set


DITA_ID_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_.-]*$')
MAX_ID_LENGTH = 80


def make_dita_id(raw: str, prefix: str = "t", used_ids: Set[str] = None) -> str:
    """
    Generate a DITA-compliant ID from raw input.
    
    DITA ID rules:
    - Must start with letter or underscore: [A-Za-z_]
    - Followed by: letters, digits, underscore, hyphen, dot: [A-Za-z0-9_.-]*
    - Regex: ^[A-Za-z_][A-Za-z0-9_.-]*$
    
    Args:
        raw: Raw input string to convert to ID
        prefix: Prefix to use if first char is invalid (default: "t")
        used_ids: Set of already used IDs to ensure uniqueness
    
    Returns:
        DITA-compliant ID string
    """
    if used_ids is None:
        used_ids = set()
    
    if not raw:
        raw = prefix
    
    raw = raw.strip()
    
    if not raw:
        raw = prefix
    
    sanitized = []
    for char in raw:
        if char.isalnum() or char in ['_', '-', '.']:
            sanitized.append(char)
        else:
            sanitized.append('_')
    
    result = ''.join(sanitized)
    
    result = re.sub(r'_+', '_', result)
    
    if not result:
        result = prefix
    elif result[0].isdigit():
        result = f"{prefix}_{result}"
    elif not (result[0].isalpha() or result[0] == '_'):
        result = f"{prefix}_{result}"
    
    if len(result) > MAX_ID_LENGTH:
        base = result[:MAX_ID_LENGTH - 10]
        result = base
    
    original_result = result
    counter = 1
    while result in used_ids:
        suffix = f"_{counter}"
        if len(original_result) + len(suffix) > MAX_ID_LENGTH:
            truncate_len = MAX_ID_LENGTH - len(suffix)
            result = original_result[:truncate_len] + suffix
        else:
            result = original_result + suffix
        counter += 1
    
    used_ids.add(result)
    
    if not DITA_ID_PATTERN.match(result):
        result = f"{prefix}_{result}"
        used_ids.add(result)
    
    return result


def is_valid_dita_id(id_str: str) -> bool:
    """
    Check if a string is a valid DITA ID.
    
    Args:
        id_str: String to validate
    
    Returns:
        True if valid DITA ID, False otherwise
    """
    if not id_str:
        return False
    if len(id_str) > MAX_ID_LENGTH:
        return False
    return bool(DITA_ID_PATTERN.match(id_str))


def stable_id(seed: str, prefix: str, suffix: str, used_ids: Set[str] = None) -> str:
    """
    Generate a stable, DITA-compliant ID from seed, prefix, and suffix.
    
    This function generates stable IDs (same input = same output) while ensuring
    DITA compliance (always starts with letter or underscore).
    
    Args:
        seed: Seed string for stability
        prefix: Prefix for the ID (will be used as fallback prefix if needed)
        suffix: Suffix string (can be numeric)
        used_ids: Set of already used IDs to ensure uniqueness
    
    Returns:
        DITA-compliant ID string that starts with a letter or underscore
    """
    if used_ids is None:
        used_ids = set()
    
    combined = f"{seed}-{prefix}-{suffix}"
    hash_obj = hashlib.md5(combined.encode())
    hash_hex = hash_obj.hexdigest()[:8]
    
    raw_id = f"{prefix}_{hash_hex}"
    
    return make_dita_id(raw_id, prefix or "t", used_ids)
