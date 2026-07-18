from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusConfig:
    corpus_id: str
    collection: str
    display_name: str
    source_type: str
    versions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepositoryConfig:
    alias: str
    root: Path
    diff_access_supported: bool = True


DEFAULT_CORPORA: dict[str, CorpusConfig] = {
    "aem_guides": CorpusConfig("aem_guides", "aem_guides", "AEM Guides documentation", "documentation"),
    "dita_spec": CorpusConfig("dita_spec", "dita_spec", "DITA specifications", "specification", ("1.2", "1.3")),
    "dita_ot": CorpusConfig("dita_ot", "dita_ot_github", "DITA-OT documentation and curated references", "documentation"),
    "learned_qa": CorpusConfig("learned_qa", "learned_qa", "Curated learned QA", "curated_qa"),
}


class EvidenceGatewaySettings:
    def __init__(self) -> None:
        self.environment = (os.getenv("ENVIRONMENT") or "development").strip().lower()
        self.service_version = os.getenv("EVIDENCE_GATEWAY_VERSION", "0.1.0")
        self.max_passage_chars = _int_env("EVIDENCE_MAX_PASSAGE_CHARS", 1200, 200, 5000)
        self.max_full_chunk_chars = _int_env("EVIDENCE_MAX_FULL_CHUNK_CHARS", 12000, 1000, 30000)
        self.repo_context_lines = _int_env("EVIDENCE_REPO_CONTEXT_LINES", 3, 0, 10)
        self.max_source_window_lines = _int_env("EVIDENCE_MAX_SOURCE_WINDOW_LINES", 300, 1, 1000)
        self.subprocess_timeout_seconds = _float_env("EVIDENCE_SUBPROCESS_TIMEOUT_SECONDS", 8.0, 1.0, 60.0)
        self.default_corpora = _csv_env("EVIDENCE_DEFAULT_CORPORA") or tuple(DEFAULT_CORPORA)
        self.required_role = os.getenv("EVIDENCE_REQUIRED_ROLE", "").strip()
        self.corpora = _load_corpora()
        self.repositories = _load_repositories()


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


def _float_env(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _load_corpora() -> dict[str, CorpusConfig]:
    allowed = set(_csv_env("EVIDENCE_CORPORA_ALLOWLIST") or tuple(DEFAULT_CORPORA))
    corpora = {key: cfg for key, cfg in DEFAULT_CORPORA.items() if key in allowed}
    raw = os.getenv("EVIDENCE_EXTRA_CORPORA_JSON", "").strip()
    if raw:
        payload = json.loads(raw)
        for item in payload:
            cfg = CorpusConfig(
                corpus_id=str(item["corpus_id"]),
                collection=str(item["collection"]),
                display_name=str(item.get("display_name") or item["corpus_id"]),
                source_type=str(item.get("source_type") or "documentation"),
                versions=tuple(str(v) for v in item.get("versions", [])),
            )
            corpora[cfg.corpus_id] = cfg
    return corpora


def _load_repositories() -> dict[str, RepositoryConfig]:
    raw = os.getenv("EVIDENCE_REPOSITORIES_JSON", "").strip()
    if not raw:
        return {}
    payload = json.loads(raw)
    repositories: dict[str, RepositoryConfig] = {}
    for item in payload:
        alias = str(item["alias"]).strip()
        root = Path(str(item["root"])).expanduser().resolve()
        repositories[alias] = RepositoryConfig(
            alias=alias,
            root=root,
            diff_access_supported=bool(item.get("diff_access_supported", True)),
        )
    return repositories


def get_settings() -> EvidenceGatewaySettings:
    return EvidenceGatewaySettings()

