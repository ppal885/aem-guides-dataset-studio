"""Filesystem safety utilities for path traversal prevention."""
from pathlib import Path
from typing import Union


class SecurityError(Exception):
    """Raised when a path escapes the allowed base directory."""

    pass


def safe_join(base_dir: Union[str, Path], relative_path: str) -> Path:
    """
    Join base_dir with relative_path and ensure the result is under base_dir.
    Raises SecurityError if the resolved path escapes base_dir.
    """
    base = Path(base_dir).resolve()
    candidate = (base / relative_path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise SecurityError(
            f"Path escapes base directory: {relative_path!r} resolves outside {base!s}"
        )
    return candidate
