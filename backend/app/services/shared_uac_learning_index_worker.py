"""One bounded projection process; invoked by the durable outbox worker only."""
import json
import sys
from types import SimpleNamespace


def main():
    from app.services.shared_uac_learning_service import _index_revision, _remove_revisions
    raw = sys.stdin.read(500_001)
    if len(raw) > 500_000:
        return 2
    data = json.loads(raw)
    rows = [SimpleNamespace(**row) for row in data["revisions"]]
    if data.get("operation") == "index" and len(rows) == 1:
        return 0 if _index_revision(rows[0]) else 1
    if data.get("operation") == "remove":
        return 0 if _remove_revisions(rows) else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
