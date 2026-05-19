import json
import shutil
import uuid
from pathlib import Path

import pytest

from app.services import chat_tools, tenant_service


def _temp_tenants_dir() -> Path:
    temp_root = Path(__file__).resolve().parents[1] / ".test_workdirs"
    temp_root.mkdir(parents=True, exist_ok=True)
    tenants_dir = temp_root / f"tenant-snippets-{uuid.uuid4().hex}"
    shutil.rmtree(tenants_dir, ignore_errors=True)
    tenants_dir.mkdir(parents=True, exist_ok=True)
    return tenants_dir


def test_retrieve_tenant_context_returns_local_knowledge_snippet_without_chroma(monkeypatch):
    tenants_dir = _temp_tenants_dir()
    monkeypatch.setattr(tenant_service, "_tenants_dir", lambda: tenants_dir)

    try:
        tenant_service.create_tenant(tenant_id="acme", name="ACME")
        tenant_service.upsert_tenant_knowledge_snippet(
            "acme",
            title="CopyFile syntaxdiagram example",
            content="<syntaxdiagram><title>CopyFile</title><groupseq><kwd>COPYF</kwd></groupseq></syntaxdiagram>",
            description="Syntax diagram example for a CopyFile command.",
            aliases=["syntaxdiagram", "copyfile"],
            tags=["dita", "xml", "groupseq"],
        )

        monkeypatch.setattr("app.services.embedding_service.is_embedding_available", lambda: False)
        monkeypatch.setattr("app.services.vector_store_service.is_chroma_available", lambda: False)

        results = tenant_service.retrieve_tenant_context("syntaxdiagram copyfile", tenant_id="acme", k=4)

        assert results
        assert "<syntaxdiagram>" in results[0]["content"]
        assert results[0]["metadata"]["doc_type"] == "knowledge_snippet"
        assert results[0]["metadata"]["source"] == "tenant_snippet"
    finally:
        shutil.rmtree(tenants_dir, ignore_errors=True)


@pytest.mark.anyio
async def test_search_tenant_knowledge_uses_local_snippets_even_without_indexed_pdfs(monkeypatch):
    tenants_dir = _temp_tenants_dir()
    monkeypatch.setattr(tenant_service, "_tenants_dir", lambda: tenants_dir)

    try:
        tenant_service.create_tenant(tenant_id="acme", name="ACME")
        tenant_service.upsert_tenant_knowledge_snippet(
            "acme",
            title="CopyFile syntaxdiagram example",
            content="<syntaxdiagram><title>CopyFile</title><groupchoice><kwd>*INFILE</kwd></groupchoice></syntaxdiagram>",
            description="Command syntax example.",
            aliases=["syntaxdiagram"],
            tags=["groupchoice"],
        )

        monkeypatch.setattr("app.services.embedding_service.is_embedding_available", lambda: False)
        monkeypatch.setattr("app.services.vector_store_service.is_chroma_available", lambda: False)
        monkeypatch.setattr("app.services.doc_pdf_index_service.list_indexed_docs", lambda tenant_id: [])

        result = await chat_tools.execute_search_tenant_knowledge("syntaxdiagram", tenant_id="acme", k=3)

        assert result["count"] == 1
        assert result["snippet_count"] == 1
        assert result["results"][0]["snippet_type"] == "xml_snippet"
        assert "syntaxdiagram" in result["results"][0]["content"]
    finally:
        shutil.rmtree(tenants_dir, ignore_errors=True)


def test_default_kone_snippet_seed_contains_copyfile_syntaxdiagram():
    path = Path(__file__).resolve().parents[1] / "storage" / "tenants" / "kone" / "knowledge_snippets.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert any(
        item.get("id") == "copyfile-syntaxdiagram" and "CopyFile" in (item.get("content") or "")
        for item in payload
    )
