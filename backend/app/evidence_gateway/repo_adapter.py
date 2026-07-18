from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from app.evidence_gateway.config import RepositoryConfig, EvidenceGatewaySettings
from app.evidence_gateway.models import (
    CodeSearchResult,
    FetchCodeContextResponse,
    GetCodeDiffResponse,
    RepositoryInfo,
)


_SAFE_REVISION = re.compile(r"^[A-Za-z0-9._/@:+-]{1,128}$")


def list_repositories(repositories: dict[str, RepositoryConfig], settings: EvidenceGatewaySettings) -> list[RepositoryInfo]:
    infos: list[RepositoryInfo] = []
    for alias, repo in sorted(repositories.items()):
        try:
            revision = _git(repo.root, ["rev-parse", "HEAD"], settings).strip() or None
            branch = _git(repo.root, ["rev-parse", "--abbrev-ref", "HEAD"], settings).strip() or None
        except Exception:
            revision = None
            branch = None
        infos.append(
            RepositoryInfo(
                alias=alias,
                revision=revision,
                branch=branch,
                diff_access_supported=repo.diff_access_supported,
            )
        )
    return infos


def search_code(repo: RepositoryConfig, query: str, revision: str | None, path_filters: list[str], max_results: int, settings: EvidenceGatewaySettings) -> list[CodeSearchResult]:
    rev = _resolve_revision(repo, revision, settings)
    _validate_filters(path_filters)
    args = ["grep", "-n", "-I", "--fixed-strings", "--ignore-case", "-e", query, rev, "--"]
    args.extend(path_filters)
    output = _git(repo.root, args, settings, allow_status=(0, 1))
    results: list[CodeSearchResult] = []
    for line in output.splitlines():
        if not line:
            continue
        parts = line.split(":", 3)
        if len(parts) != 4:
            continue
        _rev_label, current_path, line_no_text, text = parts
        if not line_no_text.isdigit():
            continue
        line_no = int(line_no_text)
        context_before, context_after = _file_context(repo, rev, current_path, line_no, settings)
        results.append(
            CodeSearchResult(
                repository_alias=repo.alias,
                revision=rev,
                relative_path=current_path,
                line_number=line_no,
                line=text[:1000],
                context_before=context_before,
                context_after=context_after,
                truncated=len(text) > 1000,
            )
        )
        if len(results) >= max_results:
            break
    return results


def fetch_code_context(repo: RepositoryConfig, revision: str, relative_path: str, start_line: int, end_line: int, correlation_id: str, settings: EvidenceGatewaySettings) -> FetchCodeContextResponse:
    rev = _resolve_revision(repo, revision, settings)
    safe_path = _validate_relative_path(repo, relative_path)
    requested = end_line - start_line + 1
    truncated = requested > settings.max_source_window_lines
    end = min(end_line, start_line + settings.max_source_window_lines - 1)
    text = _git(repo.root, ["show", f"{rev}:{safe_path.as_posix()}"], settings)
    lines = text.splitlines()
    window = lines[start_line - 1 : end]
    return FetchCodeContextResponse(
        correlation_id=correlation_id,
        repository_alias=repo.alias,
        revision=rev,
        relative_path=safe_path.as_posix(),
        start_line=start_line,
        end_line=end,
        lines=window,
        truncated=truncated,
    )


def get_code_diff(repo: RepositoryConfig, base_revision: str, head_revision: str, path_filters: list[str], max_bytes: int, correlation_id: str, settings: EvidenceGatewaySettings) -> GetCodeDiffResponse:
    if not repo.diff_access_supported:
        raise PermissionError("Diff access is not enabled for this repository.")
    base = _resolve_revision(repo, base_revision, settings)
    head = _resolve_revision(repo, head_revision, settings)
    _validate_filters(path_filters)
    args = ["diff", "--no-ext-diff", "--unified=3", base, head, "--"]
    args.extend(path_filters)
    diff = _git(repo.root, args, settings, allow_status=(0, 1))
    encoded = diff.encode("utf-8", errors="replace")
    truncated = len(encoded) > max_bytes
    if truncated:
        diff = encoded[:max_bytes].decode("utf-8", errors="replace") + "\n…"
    return GetCodeDiffResponse(
        correlation_id=correlation_id,
        repository_alias=repo.alias,
        base_revision=base,
        head_revision=head,
        diff=diff,
        truncated=truncated,
    )


def _resolve_revision(repo: RepositoryConfig, revision: str | None, settings: EvidenceGatewaySettings) -> str:
    candidate = revision or "HEAD"
    if not _SAFE_REVISION.match(candidate) or candidate.startswith("-"):
        raise ValueError("Invalid revision.")
    resolved = _git(repo.root, ["rev-parse", "--verify", f"{candidate}^{{commit}}"], settings).strip()
    if not resolved:
        raise ValueError("Unknown revision.")
    return resolved


def _validate_relative_path(repo: RepositoryConfig, relative_path: str) -> Path:
    if "\x00" in relative_path or relative_path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", relative_path):
        raise ValueError("Invalid path.")
    path = Path(relative_path)
    if any(part in {"..", ""} for part in path.parts):
        raise ValueError("Invalid path.")
    real = (repo.root / path).resolve()
    try:
        real.relative_to(repo.root.resolve())
    except ValueError as exc:
        raise ValueError("Path escapes repository root.") from exc
    return path


def _validate_filters(filters: list[str]) -> None:
    for item in filters:
        if item.startswith("-") or "\x00" in item or item.startswith(("/", "\\")) or ".." in Path(item).parts:
            raise ValueError("Invalid path filter.")


def _file_context(repo: RepositoryConfig, revision: str, relative_path: str, line_no: int, settings: EvidenceGatewaySettings) -> tuple[list[str], list[str]]:
    try:
        text = _git(repo.root, ["show", f"{revision}:{relative_path}"], settings)
    except Exception:
        return [], []
    lines = text.splitlines()
    before = lines[max(0, line_no - settings.repo_context_lines - 1) : max(0, line_no - 1)]
    after = lines[line_no : line_no + settings.repo_context_lines]
    return before, after


def _git(root: Path, args: list[str], settings: EvidenceGatewaySettings, allow_status: tuple[int, ...] = (0,)) -> str:
    if not root.exists() or not (root / ".git").exists():
        raise FileNotFoundError("Repository checkout is unavailable.")
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        text=True,
        capture_output=True,
        timeout=settings.subprocess_timeout_seconds,
        shell=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if completed.returncode not in allow_status:
        raise RuntimeError("Git command failed.")
    return completed.stdout
