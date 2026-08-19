"""CLI entry point.

  python -m ui_harvester --config config/ui_crawler.yaml --mode smoke --max-states 30
  python -m ui_harvester --dry-run
  python -m ui_harvester auth        # interactive-headed login (run locally)

Flags: --config --mode --max-states --max-depth --seed --output-dir --dry-run
"""

import argparse
import json
import sys

from .config import load_config
from .auth import interactive_login, storage_state_exists, AUTHENTICATION_REQUIRED
from .harvester import Harvester
from . import reports, indexer


def _apply_overrides(cfg, args):
    if args.mode:
        cfg.mode = args.mode
    if args.max_states is not None:
        cfg.max_states = args.max_states
    if args.max_depth is not None:
        cfg.max_depth = args.max_depth
    if args.output_dir:
        cfg.output_dir = args.output_dir
    if args.seed:
        cfg.base_url = args.seed
    if args.dry_run:
        cfg.mode = "dry_run"
    return cfg


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ui_harvester")
    parser.add_argument("subcommand", nargs="?", default="crawl", choices=["crawl", "auth"])
    parser.add_argument("--config", default="config/ui_crawler.yaml")
    parser.add_argument("--mode", default=None, choices=["dry_run", "smoke", "core", "expanded"])
    parser.add_argument("--max-states", type=int, default=None)
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--seed", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-index", action="store_true", help="skip Chroma upsert (write records to disk only)")
    args = parser.parse_args(argv)

    cfg = _apply_overrides(load_config(args.config), args)

    if args.subcommand == "auth":
        path = interactive_login(cfg)
        print(f"[ui_harvester] storage_state saved to {path}")
        return 0

    # crawl / dry-run
    if not storage_state_exists(cfg):
        print(f"[ui_harvester] {AUTHENTICATION_REQUIRED}: no valid session at {cfg.storage_state}.")
        print("[ui_harvester] Run `python -m ui_harvester auth` locally to sign in first. STOP.")
        _emit_final_report(None, cfg, verdict="NOT_READY",
                           reason=f"{AUTHENTICATION_REQUIRED}: no storage_state")
        return 3

    harvester = Harvester(cfg)
    result = harvester.run(mode=cfg.mode)
    if result.auth_status == AUTHENTICATION_REQUIRED:
        _emit_final_report(result, cfg, verdict="NOT_READY", reason=AUTHENTICATION_REQUIRED)
        return 3

    flows = reports.write_metadata(result, cfg.output_dir)
    reports.write_graphs(result, cfg.output_dir, flows)
    records = reports.build_rag_records(result, flows)
    reports.write_reports(result, cfg.output_dir, flows)
    indexer.write_records(cfg.output_dir, records)
    rag_status = {"chroma_upserted": False, "reason": "skipped (--no-index)"}
    if not args.no_index:
        rag_status = indexer.upsert_to_chroma(cfg.output_dir, records)

    verdict = _verdict(result, rag_status)
    _emit_final_report(result, cfg, verdict=verdict, rag_status=rag_status, records=len(records), flows=len(flows))
    return 0


def _verdict(result, rag_status):
    if result.auth_status != "OK":
        return "NOT_READY"
    if result.states and (result.transitions or result.safe_executed >= 0):
        return "READY_FOR_CORE_UI_CRAWL" if result.transitions else "PARTIALLY_READY"
    return "PARTIALLY_READY"


def _emit_final_report(result, cfg, *, verdict, reason="", rag_status=None, records=0, flows=0):
    summ = result.summary() if result else {}
    report = {
        "TARGET_SERVER": cfg.base_url,
        "AUTH_STATUS": (result.auth_status if result else AUTHENTICATION_REQUIRED),
        "MODE": cfg.mode,
        "UNIQUE_UI_STATES": summ.get("unique_states", 0),
        "TRANSITIONS_CAPTURED": summ.get("transitions", 0),
        "WORKFLOWS_DISCOVERED": flows,
        "UI_CAPABILITIES": summ.get("capabilities", 0),
        "SAFE_ACTIONS_EXECUTED": summ.get("safe_executed", 0),
        "BLOCKED_ACTIONS": summ.get("blocked", 0),
        "UNKNOWN_ACTIONS": summ.get("unknown", 0),
        "DUPLICATES_SKIPPED": summ.get("duplicates_skipped", 0),
        "VISION_REQUIRED_COUNT": summ.get("vision_required", 0),
        "VERSION_RESOLUTION": summ.get("product_version", "UNKNOWN"),
        "RAG_RECORDS_CREATED": records,
        "RAG_INGESTION_STATUS": (rag_status or {}).get("reason") or ("upserted" if (rag_status or {}).get("chroma_upserted") else "written-to-disk"),
        "SECURITY_AUDIT": "credentials from env only; storage_state git-ignored; no secrets in outputs",
        "VERDICT": verdict,
        "REASON": reason,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    sys.exit(main())
