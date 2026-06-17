from __future__ import annotations

from app.services.dita_ot_github_rag_service import fetch_dita_ot_issues


class _FakeResponse:
    def __init__(self, status_code: int, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    def get(self, url, headers=None, params=None):
        del url, headers
        self.calls += 1
        page = int(params["page"])
        if page == 1:
            return _FakeResponse(
                200,
                [
                    {"number": 101, "title": "Issue one", "body": "A" * 250},
                    {"number": 102, "title": "Issue two", "body": "B" * 250},
                ],
                {"Link": '<next-page>; rel="next"'},
            )
        return _FakeResponse(422, {"message": "unprocessable"}, {})


def test_fetch_dita_ot_issues_treats_terminal_422_as_boundary(monkeypatch):
    monkeypatch.setattr("app.services.dita_ot_github_rag_service.httpx.Client", _FakeClient)
    issues, errors = fetch_dita_ot_issues(max_issues=100, state="all")
    assert len(issues) == 2
    assert errors == []
