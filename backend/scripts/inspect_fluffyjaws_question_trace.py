"""Render one redacted FJ-10 question journey from an offline trace artifact."""

from __future__ import annotations

import argparse
import ctypes
import os
import stat
import sys
from pathlib import Path
from typing import NoReturn

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.reasoning_evidence_observability import (  # noqa: E402
    QuestionRetrievalTraceBundle,
    render_question_debug_report,
)


_MAX_TRACE_BYTES = 2 * 1024 * 1024
_REPARSE_POINT_FLAG = 0x400
_DRIVE_REMOTE = 4


class _RedactedArgumentParser(argparse.ArgumentParser):
    """Reject invalid arguments without echoing attacker-controlled input."""

    def error(self, _message: str) -> NoReturn:
        raise ValueError("invalid arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _RedactedArgumentParser(
        description="Inspect one question in a redacted FJ-10 retrieval trace."
    )
    parser.add_argument(
        "--trace",
        required=True,
        help="Path to an aem-guides-question-retrieval-trace-v1 JSON file.",
    )
    parser.add_argument(
        "--question-id",
        required=True,
        help="Canonical opaque ID in the form question:<32 lowercase hex>.",
    )
    return parser


def _is_remote_drive(path: Path) -> bool:
    """Return whether a Windows path is backed by a mapped/network drive."""

    if os.name != "nt" or not path.drive:
        return False
    drive_root = f"{path.drive}\\"
    return ctypes.windll.kernel32.GetDriveTypeW(drive_root) == _DRIVE_REMOTE


def _reject_reparse_components(path: Path) -> None:
    """Reject symlinks/junctions before resolving or opening a local trace."""

    chain = [path, *path.parents]
    for component in reversed(chain):
        try:
            component_stat = os.lstat(component)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(component_stat.st_mode) or (
            getattr(component_stat, "st_file_attributes", 0) & _REPARSE_POINT_FLAG
        ):
            raise ValueError("trace path cannot traverse a reparse point")


def _load_trace(raw_path: str) -> QuestionRetrievalTraceBundle:
    if not raw_path or "\x00" in raw_path:
        raise ValueError("invalid trace path")
    if raw_path.startswith(("\\\\", "//")):
        raise ValueError("network trace paths are not supported")
    supplied = Path(raw_path)
    if (
        supplied.suffix.casefold() != ".json"
        or ":" in supplied.name
    ):
        raise ValueError("trace must be a JSON file")
    absolute = Path(os.path.abspath(supplied))
    if _is_remote_drive(absolute):
        raise ValueError("network trace paths are not supported")
    if any(":" in part for part in absolute.parts[1:]):
        raise ValueError("alternate data streams are not supported")
    _reject_reparse_components(absolute)
    resolved = absolute.resolve(strict=True)
    if _is_remote_drive(resolved):
        raise ValueError("network trace paths are not supported")
    _reject_reparse_components(resolved)
    stat_result = resolved.stat()
    if not resolved.is_file() or (
        getattr(stat_result, "st_file_attributes", 0) & _REPARSE_POINT_FLAG
    ):
        raise ValueError("trace must be a regular non-reparse file")
    if stat_result.st_size <= 0 or stat_result.st_size > _MAX_TRACE_BYTES:
        raise ValueError("trace size is outside the supported range")
    with resolved.open("rb") as handle:
        opened_stat = os.fstat(handle.fileno())
        if (
            opened_stat.st_size != stat_result.st_size
            or getattr(opened_stat, "st_file_attributes", 0) & _REPARSE_POINT_FLAG
        ):
            raise ValueError("trace changed before it was opened")
        raw = handle.read(_MAX_TRACE_BYTES + 1)
        final_stat = os.fstat(handle.fileno())
    if (
        len(raw) != opened_stat.st_size
        or len(raw) > _MAX_TRACE_BYTES
        or final_stat.st_size != opened_stat.st_size
    ):
        raise ValueError("trace changed while it was being read")
    text = raw.decode("utf-8", errors="strict")
    return QuestionRetrievalTraceBundle.model_validate_json(text)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        trace = _load_trace(str(args.trace))
        report = render_question_debug_report(trace, str(args.question_id))
    except (LookupError, OSError, UnicodeError, ValueError):
        print("ERROR: QUESTION_TRACE_INPUT_INVALID", file=sys.stderr)
        return 2
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
