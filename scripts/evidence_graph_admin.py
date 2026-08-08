#!/usr/bin/env python3
"""Operational CLI for the SQLite/PostgreSQL evidence graph."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _load_environment() -> None:
    try:
        from dotenv import load_dotenv

        for path in (ROOT / ".env", BACKEND / ".env"):
            if path.exists():
                load_dotenv(path, override=True, encoding="utf-8-sig")
    except ImportError:
        pass


def _print(value) -> None:
    print(json.dumps(value, indent=2, default=str, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    mode = build.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    build.add_argument("--batch-size", type=int, default=500)
    build.add_argument("--sources", default="jira,docs,dita")

    audit = sub.add_parser("audit")
    audit.add_argument("--generation-id", default="")

    sub.add_parser("status")
    sub.add_parser("enabled")

    sync = sub.add_parser("sync")
    sync.add_argument("--max-events", type=int, default=500)
    sync.add_argument("--max-retries", type=int, default=5)
    sync.add_argument("--batch-size", type=int, default=500)

    events = sub.add_parser("events")
    events.add_argument("--status", default="failed", choices=("pending", "retry", "failed", "completed", "all"))
    events.add_argument("--source-kind", default="")
    events.add_argument("--limit", type=int, default=100)

    replay = sub.add_parser("replay-events")
    replay.add_argument("--event-id", action="append", default=[])
    replay.add_argument("--source-kind", default="")
    replay.add_argument("--all-failed", action="store_true")

    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--dry-run", action="store_true")
    reconcile.add_argument("--batch-size", type=int, default=500)

    sub.add_parser("rollback")

    query = sub.add_parser("query")
    query.add_argument("query")
    query.add_argument("--jira-key", default="")
    query.add_argument("--customer", default="")
    query.add_argument("--component", default="")
    query.add_argument("--outputs", default="")
    query.add_argument("--dita-entities", default="")
    query.add_argument("--max-paths", type=int, default=20)
    query.add_argument("--aggregate-cross-customer", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    _load_environment()
    if args.command == "enabled":
        enabled = os.getenv("EVIDENCE_GRAPH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        _print({"enabled": enabled})
        return 0 if enabled else 3

    if args.command == "build":
        from app.services.evidence_graph_build_service import rebuild_evidence_graph

        result = rebuild_evidence_graph(
            dry_run=bool(args.dry_run),
            sources=[value.strip() for value in args.sources.split(",") if value.strip()],
            batch_size=args.batch_size,
            created_by="vm-cli",
        )
        _print(result)
        return 0 if result.get("valid") and (args.dry_run or result.get("promoted")) else 1

    if args.command == "status":
        from app.db.session import SessionLocal
        from app.services.evidence_graph_store import graph_status

        session = SessionLocal()
        try:
            result = graph_status(session)
        finally:
            session.close()
        _print(result)
        return 0 if result.get("status") in {"ready", "disabled"} else 1

    if args.command == "audit":
        from app.db.session import SessionLocal
        from app.services.evidence_graph_store import active_generation, audit_generation

        session = SessionLocal()
        try:
            generation_id = args.generation_id
            if not generation_id:
                generation = active_generation(session)
                generation_id = generation.id if generation else ""
            result = (
                audit_generation(session, generation_id)
                if generation_id
                else {"valid": False, "errors": ["No active evidence graph generation."]}
            )
        finally:
            session.close()
        _print(result)
        return 0 if result.get("valid") else 1

    if args.command == "sync":
        from app.services.evidence_graph_sync_service import drain_evidence_graph_events

        result = drain_evidence_graph_events(
            max_events=args.max_events,
            max_retries=args.max_retries,
            batch_size=args.batch_size,
            created_by="vm-cli-incremental",
        )
        _print(result)
        return 0 if result.get("success") else 1

    if args.command == "events":
        from app.db.session import SessionLocal
        from app.services.evidence_graph_store import list_source_events

        session = SessionLocal()
        try:
            rows = list_source_events(
                session,
                status=None if args.status == "all" else args.status,
                source_kind=args.source_kind.strip() or None,
                limit=args.limit,
            )
        finally:
            session.close()
        _print({"count": len(rows), "events": rows})
        return 0

    if args.command == "replay-events":
        from app.db.session import SessionLocal
        from app.services.evidence_graph_store import replay_source_events

        event_ids = list(dict.fromkeys(value.strip() for value in args.event_id if value.strip()))
        source_kind = args.source_kind.strip()
        if not event_ids and not source_kind and not args.all_failed:
            _print({"replayed": 0, "error": "Select --event-id/--source-kind or pass --all-failed."})
            return 2
        session = SessionLocal()
        try:
            result = replay_source_events(
                session,
                event_ids=event_ids,
                source_kind=source_kind or None,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        _print(result)
        return 0

    if args.command == "reconcile":
        from app.services.evidence_graph_sync_service import reconcile_evidence_graph

        result = reconcile_evidence_graph(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            created_by="vm-cli-reconciliation",
        )
        _print(result)
        return 0 if result.get("valid") and (args.dry_run or result.get("promoted")) else 1

    if args.command == "rollback":
        from app.db.session import SessionLocal
        from app.services.evidence_graph_store import rollback_generation

        session = SessionLocal()
        try:
            try:
                result = rollback_generation(session)
                session.commit()
            except Exception as exc:
                session.rollback()
                result = {"rolled_back": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            session.close()
        _print(result)
        return 0 if result.get("rolled_back") else 1

    if args.command == "query":
        from app.services.evidence_graph_query_service import query_test_evidence_graph

        result = query_test_evidence_graph(
            args.query,
            jira_key=args.jira_key,
            customer=args.customer,
            component=args.component,
            outputs=[value.strip() for value in args.outputs.split(",") if value.strip()],
            dita_entities=[value.strip() for value in args.dita_entities.split(",") if value.strip()],
            max_paths=args.max_paths,
            allow_cross_customer_details=not args.aggregate_cross_customer,
            actor_id="vm-cli",
            influence_mode="interactive",
        )
        _print(result)
        return 0 if result.get("available") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
