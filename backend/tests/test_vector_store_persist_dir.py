"""The embedded vector store must be shareable across checkouts.

Each checkout otherwise keeps its own store under its own storage directory, so
a fresh worktree starts with an empty index and silently degrades to
lexical-only retrieval while readiness still reports the corpus as present.
"""

from pathlib import Path

from app.services import vector_store_service


def test_persist_dir_defaults_to_the_checkout_storage_directory(monkeypatch):
    monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)

    path = vector_store_service._get_chroma_path()

    assert path.name == vector_store_service.CHROMA_DB_DIR
    assert path.parent.name == "storage"


def test_persist_dir_override_points_at_a_shared_store(monkeypatch, tmp_path):
    shared = tmp_path / "shared-index"
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(shared))

    path = vector_store_service._get_chroma_path()

    assert path == shared
    assert path.is_dir()


def test_blank_override_is_ignored_rather_than_creating_a_store_at_the_root(monkeypatch):
    monkeypatch.setenv("CHROMA_PERSIST_DIR", "   ")

    path = vector_store_service._get_chroma_path()

    assert path.name == vector_store_service.CHROMA_DB_DIR
    assert path != Path("   ")
