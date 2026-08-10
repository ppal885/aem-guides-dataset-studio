"""
UAC Benchmark Runner — generates UAC for each golden ticket and scores the output.

Usage (from backend/):
    python -m app.evaluation.uac_eval.runner [--keys DXML-62001,DXML-61540] [--out report.json]

Or import and call run_benchmark() programmatically.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import yaml

from app.evaluation.uac_eval.audits import run_all_audits, TicketAuditReport
from app.evaluation.uac_eval.scoring import score_similarity, aggregate_scores, BenchmarkScore

_GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.yaml"


# ── golden set loading ────────────────────────────────────────────────────────

@dataclass
class GoldenEntry:
    jira_key: str
    summary: str
    domain: str
    risk_level: str
    tags: list[str]
    reference_scenarios: list[str]
    notes: str = ""


def load_golden_set(path: Path = _GOLDEN_SET_PATH) -> list[GoldenEntry]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    entries: list[GoldenEntry] = []
    for item in data.get("golden", []):
        entries.append(GoldenEntry(
            jira_key=item["jira_key"],
            summary=item.get("summary", ""),
            domain=item.get("domain", "unknown"),
            risk_level=item.get("risk_level", "medium"),
            tags=item.get("tags", []),
            reference_scenarios=item.get("reference_scenarios", []),
            notes=item.get("notes", ""),
        ))
    return entries


# ── UAC generation ────────────────────────────────────────────────────────────

def _extract_scenarios_from_uac(uac_result: dict) -> list[str]:
    """Pull acceptance-criteria scenario strings from run_uac_analyze() output."""
    scenarios: list[str] = []

    # path 1: uac_ui.must_test_scenario_table.rows[].scenario
    uac_ui = uac_result.get("uac_ui") or {}
    table = uac_ui.get("must_test_scenario_table") or {}
    for row in table.get("rows") or []:
        s = str(row.get("scenario") or "").strip()
        if s:
            # strip leading "DXML-12345: " prefix if present
            s = re.sub(r'^[A-Z][A-Z0-9_]+-\d+:\s*', '', s)
            scenarios.append(s)

    if scenarios:
        return scenarios

    # path 2: parsed.scenarios[].scenario (legacy markdown)
    parsed = uac_result.get("parsed") or {}
    for item in parsed.get("scenarios") or []:
        s = str(item.get("scenario") or "").strip()
        if s:
            scenarios.append(s)

    return scenarios


import re  # noqa: E402  (after function definition that uses re)


def generate_uac(jira_key: str, timeout_seconds: int = 180) -> dict:
    """Call run_uac_analyze and return the raw result dict.

    Uses asyncio.run() so it works both standalone and when called from a
    thread spawned by asyncio.to_thread() inside a FastAPI handler.
    """
    import asyncio
    from app.services.uac_copilot_analyze_service import run_uac_analyze

    async def _run() -> dict:
        return await asyncio.wait_for(run_uac_analyze(jira_key), timeout=timeout_seconds)

    try:
        return asyncio.run(_run()) or {}
    except asyncio.TimeoutError:
        return {"error": f"UAC generation timed out after {timeout_seconds}s"}
    except Exception as exc:
        return {"error": str(exc)}


# ── per-ticket evaluation ─────────────────────────────────────────────────────

@dataclass
class TicketResult:
    entry: GoldenEntry
    generated_scenarios: list[str]
    similarity: object          # SimilarityResult
    audit: TicketAuditReport
    error: str | None = None
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "jira_key": self.entry.jira_key,
            "summary": self.entry.summary,
            "domain": self.entry.domain,
            "risk_level": self.entry.risk_level,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "error": self.error,
            "generated_scenario_count": len(self.generated_scenarios),
            "reference_scenario_count": len(self.entry.reference_scenarios),
            "similarity": self.similarity.to_dict() if self.similarity else None,
            "audit": self.audit.to_dict() if self.audit else None,
        }


def evaluate_ticket(entry: GoldenEntry) -> TicketResult:
    """Generate UAC for one golden entry and score it."""
    from app.services.jira_client import JiraClient
    t0 = time.perf_counter()

    # fetch live Jira text for audit checks
    jira_summary = entry.summary
    jira_description = ""
    try:
        client = JiraClient()
        issue = client.get_issue(entry.jira_key)
        fields = issue.get("fields") or {}
        jira_summary = str(fields.get("summary") or entry.summary)
        desc = fields.get("description") or ""
        jira_description = str(desc) if isinstance(desc, str) else ""
    except Exception:
        pass  # use placeholder summary if Jira is unavailable

    # generate UAC
    raw_result = generate_uac(entry.jira_key)
    error = raw_result.get("error") if isinstance(raw_result, dict) else None
    generated = _extract_scenarios_from_uac(raw_result) if not error else []

    elapsed = time.perf_counter() - t0

    # similarity scoring
    sim = score_similarity(entry.jira_key, entry.reference_scenarios, generated)

    # quality audits
    audit = run_all_audits(
        jira_key=entry.jira_key,
        jira_summary=jira_summary,
        jira_description=jira_description,
        generated_scenarios=generated,
    )

    return TicketResult(
        entry=entry,
        generated_scenarios=generated,
        similarity=sim,
        audit=audit,
        error=error,
        elapsed_seconds=elapsed,
    )


# ── benchmark orchestration ───────────────────────────────────────────────────

@dataclass
class BenchmarkReport:
    run_id: str
    ticket_count: int
    success_count: int
    error_count: int
    total_seconds: float
    similarity: BenchmarkScore
    audit_summary: dict
    tickets: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "ticket_count": self.ticket_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "total_seconds": round(self.total_seconds, 1),
            "similarity": self.similarity.to_dict(),
            "audit_summary": self.audit_summary,
            "tickets": self.tickets,
        }


def run_benchmark(
    keys: Sequence[str] | None = None,
    golden_path: Path = _GOLDEN_SET_PATH,
    verbose: bool = True,
) -> BenchmarkReport:
    """Run the full UAC benchmark. Pass `keys` to restrict to a subset."""
    import uuid
    from datetime import datetime, timezone

    run_id = f"uac_bench_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}"
    entries = load_golden_set(golden_path)
    if keys:
        key_set = {k.strip().upper() for k in keys}
        entries = [e for e in entries if e.jira_key.upper() in key_set]

    if verbose:
        print(f"[benchmark] run_id={run_id} | tickets={len(entries)}")

    t_global = time.perf_counter()
    ticket_results: list[TicketResult] = []
    sim_inputs: list[tuple[str, str, object]] = []

    for i, entry in enumerate(entries, 1):
        if verbose:
            print(f"  [{i}/{len(entries)}] {entry.jira_key} …", end="", flush=True)
        result = evaluate_ticket(entry)
        ticket_results.append(result)
        if not result.error:
            sim_inputs.append((entry.jira_key, entry.domain, result.similarity))
        if verbose:
            status = f"✓ f1={result.similarity.f1_score:.2f}" if not result.error else f"✗ {result.error[:60]}"
            print(f" {status} ({result.elapsed_seconds:.1f}s)")

    total_seconds = time.perf_counter() - t_global
    errors = [r for r in ticket_results if r.error]
    successes = [r for r in ticket_results if not r.error]

    bench_score = aggregate_scores(sim_inputs)

    # audit summary
    all_hal = [r.audit.hallucination.score for r in successes]
    all_scope = [r.audit.scope_expansion.score for r in successes]
    all_perf = [r.audit.performance_false_positive.score for r in successes]
    audit_summary = {
        "mean_hallucination_score": round(sum(all_hal) / len(all_hal), 1) if all_hal else 0.0,
        "mean_scope_score": round(sum(all_scope) / len(all_scope), 1) if all_scope else 0.0,
        "mean_perf_score": round(sum(all_perf) / len(all_perf), 1) if all_perf else 0.0,
        "tickets_all_audits_passed": sum(1 for r in successes if r.audit.passed),
    }

    return BenchmarkReport(
        run_id=run_id,
        ticket_count=len(entries),
        success_count=len(successes),
        error_count=len(errors),
        total_seconds=total_seconds,
        similarity=bench_score,
        audit_summary=audit_summary,
        tickets=[r.to_dict() for r in ticket_results],
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Run the UAC golden benchmark.")
    ap.add_argument("--keys", help="Comma-separated Jira keys to restrict the run (e.g. DXML-62001,DXML-61540)")
    ap.add_argument("--out", default=None, help="Write JSON report to this file")
    ap.add_argument("--golden", default=str(_GOLDEN_SET_PATH), help="Path to golden_set.yaml")
    args = ap.parse_args()

    keys = [k.strip() for k in args.keys.split(",")] if args.keys else None
    report = run_benchmark(keys=keys, golden_path=Path(args.golden), verbose=True)

    print("\n=== Benchmark Summary ===")
    print(f"  Tickets run    : {report.ticket_count}")
    print(f"  Succeeded      : {report.success_count}")
    print(f"  Errors         : {report.error_count}")
    print(f"  Mean F1        : {report.similarity.mean_f1:.3f}")
    print(f"  Mean coverage  : {report.similarity.mean_coverage:.3f}")
    print(f"  Mean precision : {report.similarity.mean_precision:.3f}")
    print(f"  Hallucination  : {report.audit_summary['mean_hallucination_score']}/100")
    print(f"  Scope          : {report.audit_summary['mean_scope_score']}/100")
    print(f"  Perf FP        : {report.audit_summary['mean_perf_score']}/100")
    print(f"  Total time     : {report.total_seconds:.1f}s")

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        print(f"\nReport written to {out_path}")
    else:
        print("\nRaw JSON:")
        print(json.dumps(report.to_dict(), indent=2)[:3000])


if __name__ == "__main__":
    main()
