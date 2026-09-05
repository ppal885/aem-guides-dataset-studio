"""Read-only index identity contracts; fakes only, no real Chroma or embeddings."""
import json
import sys
from types import ModuleType, SimpleNamespace
from uuid import UUID

import pytest

from app.services import vector_store_service as vectors


NAMES = ("aem_guides", "dita_spec", "jira_qa")
COLLECTION_ID = UUID("756ee538-01ee-49cb-ba8f-2a691b14b59f")
OTHER_ID = UUID("a7a64978-67bf-4120-a619-6e05341a7b14")


class Collection:
    def __init__(self, identifier=COLLECTION_ID, count=17):
        self.id = identifier
        self.observed_count = count

    def count(self):
        if isinstance(self.observed_count, Exception):
            raise self.observed_count
        return self.observed_count


class Client:
    tenant = "default_tenant"
    database = "default_database"

    def __init__(self):
        self.collections = {name: Collection() for name in NAMES}
        self.reads = []

    def get_collection(self, *, name):
        self.reads.append(name)
        return self.collections[name]

    def list_collections(self):
        return [SimpleNamespace(name=name) for name in self.collections]

    def heartbeat(self):
        return 123

    def get_or_create_collection(self, *args, **kwargs):
        raise AssertionError("Identity must not create a collection")


@pytest.fixture(autouse=True)
def isolate_client(monkeypatch):
    monkeypatch.setattr(vectors, "_chroma_client", None)
    monkeypatch.setattr(vectors, "_identity_client", None)
    monkeypatch.setattr(vectors, "_identity_snapshot", None)
    monkeypatch.setattr(vectors, "version", lambda _: "1.0.21")


def open_fake(monkeypatch, client=None, *, mode="EMBEDDED", target=None):
    client = client or Client()
    vectors._remember_client_identity(client, mode, target or {"path": "/private/storage/chroma_db"})
    monkeypatch.setattr(vectors, "_chroma_client", client)
    return client


def test_uninitialized_identity_has_nulls_and_never_initializes(monkeypatch):
    monkeypatch.setattr(vectors, "_get_client", lambda: pytest.fail("Must not initialize Chroma"))
    result = vectors.get_index_identity()
    assert result["status"] == "UNAVAILABLE"
    assert result["mode"] == "UNKNOWN"
    assert result["target_fingerprint"] is None
    assert all(row == {"id": None, "count": None, "status": "UNAVAILABLE"}
               for row in result["collections"].values())


def test_identity_contains_existing_uuid_count_and_no_private_path(monkeypatch):
    client = open_fake(monkeypatch)
    result = vectors.get_index_identity()
    assert result["status"] == "OK" and result["mode"] == "EMBEDDED"
    assert len(result["target_fingerprint"]) == 64
    assert result["client_version"] == "1.0.21"
    assert result["collections"]["jira_qa"] == {"id": str(COLLECTION_ID), "count": 17, "status": "OK"}
    assert client.reads == list(NAMES)
    assert "/private/" not in json.dumps(result)


def test_equal_counts_cannot_hide_different_collection_uuid(monkeypatch):
    first = open_fake(monkeypatch)
    one = vectors.get_index_identity()
    second = Client()
    second.collections["jira_qa"].id = OTHER_ID
    open_fake(monkeypatch, second, target={"path": "/another/store"})
    two = vectors.get_index_identity()
    assert one["collections"]["jira_qa"]["count"] == two["collections"]["jira_qa"]["count"]
    assert one["collections"]["jira_qa"]["id"] != two["collections"]["jira_qa"]["id"]
    assert one["target_fingerprint"] != two["target_fingerprint"]
    assert first is not second


def test_cached_identity_does_not_follow_mutated_environment(monkeypatch):
    open_fake(monkeypatch)
    before = vectors.get_index_identity()
    monkeypatch.setenv("CHROMA_HOST", "unrelated-host")
    monkeypatch.setenv("CHROMA_PORT", "9000")
    monkeypatch.setenv("STORAGE_PATH", "/different/storage")
    assert vectors.get_index_identity() == before


def test_unknown_replacement_client_cannot_reuse_old_snapshot(monkeypatch):
    open_fake(monkeypatch)
    monkeypatch.setattr(vectors, "_chroma_client", Client())
    result = vectors.get_index_identity()
    assert result["status"] == "PARTIAL" and result["mode"] == "UNKNOWN"
    assert result["target_fingerprint"] is None
    assert result["collections"]["jira_qa"]["count"] == 17


def test_mutated_client_scope_cannot_reuse_old_fingerprint(monkeypatch):
    client = open_fake(monkeypatch)
    client.database = "different_database"
    result = vectors.get_index_identity()
    assert result["status"] == "PARTIAL"
    assert result["target_fingerprint"] is None and result["database"] is None


@pytest.mark.parametrize("bad_count", [True, -1, "17", None, RuntimeError("secret-token")])
def test_bad_counts_are_not_fabricated_zero_or_secret_errors(monkeypatch, bad_count):
    client = open_fake(monkeypatch)
    client.collections["jira_qa"].observed_count = bad_count
    result = vectors.get_index_identity()
    assert result["status"] == "PARTIAL"
    assert result["collections"]["jira_qa"]["count"] is None
    assert "secret-token" not in json.dumps(result)


def test_existing_zero_is_valid_but_absent_collection_is_unavailable(monkeypatch):
    client = open_fake(monkeypatch)
    client.collections["jira_qa"].observed_count = 0
    del client.collections["dita_spec"]
    result = vectors.get_index_identity()
    assert result["collections"]["jira_qa"]["count"] == 0
    assert result["collections"]["dita_spec"] == {"id": None, "count": None, "status": "UNAVAILABLE"}
    assert client.reads == list(NAMES)


def test_invalid_uuid_is_null_not_provider_content(monkeypatch):
    client = open_fake(monkeypatch)
    client.collections["jira_qa"].id = "auth-secret-content"
    result = vectors.get_index_identity()
    assert result["collections"]["jira_qa"] == {"id": None, "count": 17, "status": "PARTIAL"}
    assert "auth-secret-content" not in json.dumps(result)


def test_remote_identity_never_exposes_host_or_auth(monkeypatch):
    monkeypatch.setenv("CHROMA_AUTH_TOKEN", "secret-token")
    open_fake(monkeypatch, mode="REMOTE", target={"host": "internal-host", "port": 8000, "ssl": False})
    result = vectors.get_index_identity()
    assert result["mode"] == "REMOTE" and result["status"] == "OK"
    assert "secret-token" not in json.dumps(result) and "internal-host" not in json.dumps(result)


def test_url_credentials_or_unsafe_namespace_stay_unknown(monkeypatch):
    client = open_fake(monkeypatch, mode="REMOTE", target={"host": "https://user:secret@host", "port": 8000, "ssl": True})
    assert vectors.get_index_identity()["target_fingerprint"] is None
    client.tenant = "unsafe/secret-tenant"
    vectors._remember_client_identity(client, "EMBEDDED", {"path": "/private/storage"})
    result = vectors.get_index_identity()
    assert result["mode"] == "UNKNOWN" and result["tenant"] is None
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize("remote", [False, True])
def test_real_initializer_captures_constructor_target_once(monkeypatch, tmp_path, remote):
    """Exercise production _get_client with fake module, not a live Chroma store."""
    fake_chroma = ModuleType("chromadb")
    fake_config = ModuleType("chromadb.config")
    fake_config.DEFAULT_DATABASE = "default_database"
    fake_config.DEFAULT_TENANT = "default_tenant"
    fake_config.Settings = lambda **kwargs: kwargs
    created = []
    client = Client()

    def constructor(**kwargs):
        created.append(kwargs)
        return client

    fake_chroma.PersistentClient = constructor
    fake_chroma.HttpClient = constructor
    monkeypatch.setitem(sys.modules, "chromadb", fake_chroma)
    monkeypatch.setitem(sys.modules, "chromadb.config", fake_config)
    monkeypatch.setattr(vectors, "_get_chroma_path", lambda: tmp_path / "chroma_db")
    monkeypatch.setenv("CHROMA_HOST", "private-host" if remote else "")
    monkeypatch.setenv("CHROMA_PORT", "8000")
    monkeypatch.setenv("CHROMA_SSL", "false")
    monkeypatch.delenv("CHROMA_AUTH_TOKEN", raising=False)
    assert vectors._get_client() is client
    result = vectors.get_index_identity()
    assert result["mode"] == ("REMOTE" if remote else "EMBEDDED")
    assert result["status"] == "OK"
    monkeypatch.setenv("CHROMA_HOST", "drifted-host")
    assert vectors._get_client() is client
    assert vectors.get_index_identity() == result
    assert len(created) == 1
