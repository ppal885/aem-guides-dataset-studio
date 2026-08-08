from app.services import vector_store_service as service


class _Collection:
    def __init__(self):
        self.upserts = []

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)


class _Client:
    def __init__(self, collection):
        self.collection = collection

    def get_or_create_collection(self, **_kwargs):
        return self.collection


def test_chroma_upsert_reports_partial_failure_when_event_persistence_fails(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(service, "_get_client", lambda: _Client(collection))
    monkeypatch.setattr(service, "_queue_evidence_graph_events", lambda *args, **kwargs: False)

    result = service.add_documents(
        service.CHROMA_COLLECTION_AEM_GUIDES,
        ["doc-1"],
        ["Official documentation"],
        [{"source_url": "https://experienceleague.adobe.com/en/docs/example"}],
        [[0.1, 0.2]],
    )

    assert result is False
    assert len(collection.upserts) == 1


def test_event_capture_is_noop_success_when_graph_is_disabled(monkeypatch):
    monkeypatch.delenv("EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED", raising=False)
    monkeypatch.setenv("EVIDENCE_GRAPH_ENABLED", "false")

    assert service._queue_evidence_graph_events(
        service.CHROMA_COLLECTION_DITA_SPEC,
        ids=["dita-1"],
        documents=["dir attribute"],
        metadatas=[{}],
        event_type="upsert",
    ) is True


def test_event_capture_groups_jira_chunks_into_one_durable_event(monkeypatch):
    calls = []

    class FakeSession:
        def commit(self):
            calls.append(("commit",))

        def close(self):
            calls.append(("close",))

    monkeypatch.setenv("EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED", "true")
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        "app.services.evidence_graph_store.enqueue_source_event",
        lambda session, **kwargs: calls.append(("event", kwargs)),
    )

    result = service._queue_evidence_graph_events(
        service.CHROMA_COLLECTION_JIRA_QA,
        ids=["GUIDES-1::summary", "GUIDES-1::learning"],
        documents=["summary", "learning"],
        metadatas=[{"jira_key": "GUIDES-1"}, {"jira_key": "GUIDES-1"}],
        event_type="upsert",
    )

    events = [entry[1] for entry in calls if entry[0] == "event"]
    assert result is True
    assert len(events) == 1
    assert events[0]["source_kind"] == "jira"
    assert events[0]["source_record_id"] == "GUIDES-1"
    assert events[0]["source_hash"].startswith("sha256:")
