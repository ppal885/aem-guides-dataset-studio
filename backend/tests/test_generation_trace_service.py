from pathlib import Path
from types import SimpleNamespace

from app.services import generation_trace_service


def test_log_generation_trace_event_does_not_pass_event_keyword_to_observability_logger(monkeypatch):
    captured: dict[str, object] = {}

    def fake_info(event: str, **kwargs):
        captured["event"] = event
        captured.update(kwargs)

    monkeypatch.setattr(generation_trace_service.obs_log, "info", fake_info)
    monkeypatch.setattr(generation_trace_service.logger, "info_structured", lambda *args, **kwargs: None)
    monkeypatch.setattr(generation_trace_service.logger, "warning_structured", lambda *args, **kwargs: None)

    trace = SimpleNamespace(
        trace_id="trace-1",
        jira_id="TEXT-123",
        outcome="success",
        attempts=[{"attempt_index": 0}],
        final_semantic_validation={"ok": True},
        validation_failure_summary="",
    )

    generation_trace_service.log_generation_trace_event(trace, Path("generation_trace.json"))

    assert captured["event"] == "dita_generation_trace"
    assert captured["event_name"] == "dita_generation_trace"
    assert "trace_id" in captured
    assert "jira_id" in captured
