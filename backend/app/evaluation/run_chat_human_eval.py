"""Run difficult humanized DITA / DITA-OT / AEM Guides chat prompt evaluations.

Uses the local grounded fallback path (learned Q&A seed + DITA-OT runtime fallback)
so the run works without billing live LLM chat turns.

Usage:
    cd backend
    python -m app.evaluation.merge_difficult_eval_seed   # sync seed bank first
    python -m app.evaluation.run_chat_human_eval
    python -m app.evaluation.run_chat_human_eval --limit 120 --json-out storage/eval/chat_human_eval_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import chat_service  # noqa: E402

SEED_PATH = BACKEND_ROOT / "app" / "storage" / "learned_qa_seed.json"
DEFAULT_REPORT = BACKEND_ROOT / "storage" / "eval" / "chat_human_eval_report.json"

HUMAN_PREFIXES = (
    "{prompt}",
    "Quick question for our docs team: {prompt}",
    "I'm trying to explain this to a new writer — {prompt}",
    "Can you walk me through this like a senior tech writer would? {prompt}",
    "We hit this in a customer map today. {prompt}",
)

# Hardest prefix for the expanded 110+ difficult suite (single variant).
DIFFICULT_HUMAN_PREFIX = "Can you walk me through this like a senior tech writer would? {prompt}"

DITA_OT_CASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "What does the DITA-OT copy-to preprocess step do?",
        ("copy-to", "preprocess", "@copy-to", "effective resource"),
    ),
    (
        "What does conrefpush do in DITA-OT preprocessing?",
        ("conrefpush", "pushbefore", "pushafter", "pushreplace"),
    ),
    (
        "Which DITA-OT module resolves normal conref references?",
        ("conref", "@conref", "xslt", "effective processed content"),
    ),
    (
        "Which DITA-OT preprocess step filters content with DITAVAL and print rules?",
        ("profile", "ditaval", "@print", "preprocessing"),
    ),
    (
        "What are DITA command arguments like --input, --format, and --output used for?",
        ("--input", "--format", "--output", "--filter"),
    ),
    (
        "My copied topic is there but the reused note inside it vanished in PDF. How should I debug this like a DITA-OT expert?",
        ("copy-to", "conref", "profile", "ditaval", "expected result"),
    ),
    (
        "I need a full example where one topic becomes two outputs and one version filters internal text.",
        ("copy-to", "two effective topic resources", "filter", "expected result"),
    ),
    (
        "Can you explain why the XML I authored is not the same as the XML DITA-OT transforms?",
        ("source xml", "effective processed content", "copy-to", "conref"),
    ),
    (
        "A pushed warning should appear before a step but does not. Show how it should work.",
        ("conrefpush", "pushbefore", "target element", "expected result"),
    ),
    (
        "I passed --filter but nothing changed. Give me exact checks and expected behavior.",
        ("--filter", "ditaval", "profile", "expected result"),
    ),
)

WEAK_PHRASES = (
    "i couldn't verify this directly",
    "best available guidance",
    "what it usually means",
    "retrieved from",
    "## quick reference",
)

SECTION_MARKERS = ("## short answer", "## example", "## expected result")


@dataclass
class EvalCase:
    id: str
    prompt: str
    source: str
    domain: str
    must_have: tuple[str, ...]
    min_length: int
    require_sections: bool
    route: str  # "local" | "dita_ot"


def _domain_from_seed(item: dict[str, Any]) -> str:
    tags = [str(t).lower() for t in (item.get("tags") or [])]
    if "aem-guides" in tags:
        return "aem_guides"
    if "dita-ot" in tags:
        return "dita_ot"
    if "dita-spec" in tags:
        return "dita_spec"
    topic = str(item.get("topic") or "").lower()
    if topic in {"publishing", "conditional"} and any("dita-ot" in t for t in tags):
        return "dita_ot"
    return "dita_spec"


DOMAIN_TAGS = frozenset({"dita-spec", "dita-ot", "aem-guides"})


def _extract_must_have_from_seed(item: dict[str, Any]) -> list[str]:
    raw_tags = [
        str(t).strip()
        for t in (item.get("tags") or [])
        if str(t).strip() and str(t).strip().lower() not in DOMAIN_TAGS
    ]
    answer = str(item.get("final_answer") or "")
    answer_lower = answer.lower()
    tags: list[str] = []
    for tag in raw_tags:
        key = tag.lower()
        alt = key.replace("-", " ")
        if key in answer_lower or alt in answer_lower:
            tags.append(tag)
    attrs = re.findall(r"@[\w-]+", answer)[:2]
    elems = re.findall(r"<[\w-]+>", answer)[:2]
    terms = tags[:3] + attrs + elems
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(term)
    return deduped[:5] or tags[:2] or ["dita"]


def build_cases(
    limit: int = 110,
    *,
    suite: str = "difficult",
    variants: int = 1,
) -> list[EvalCase]:
    seed_items = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    cases: list[EvalCase] = []

    prefix_templates = HUMAN_PREFIXES[: max(1, min(variants, len(HUMAN_PREFIXES)))]
    if suite == "difficult":
        prefix_templates = (DIFFICULT_HUMAN_PREFIX,)

    for index, item in enumerate(seed_items):
        base_prompt = str(item.get("prompt") or "").strip()
        must_have = tuple(_extract_must_have_from_seed(item))
        domain = _domain_from_seed(item)
        for variant, template in enumerate(prefix_templates):
            human_prompt = template.format(prompt=base_prompt)
            cases.append(
                EvalCase(
                    id=f"seed_{index + 1:03d}_v{variant + 1}",
                    prompt=human_prompt,
                    source="learned_qa_seed",
                    domain=domain,
                    must_have=must_have,
                    min_length=180,
                    require_sections=False,
                    route="local",
                )
            )

    for index, (prompt, terms) in enumerate(DITA_OT_CASES):
        cases.append(
            EvalCase(
                id=f"dita_ot_{index + 1:03d}",
                prompt=prompt,
                source="dita_ot_humanized",
                domain="dita_ot",
                must_have=tuple(terms),
                min_length=900,
                require_sections=True,
                route="dita_ot",
            )
        )
        if suite != "difficult":
            cases.append(
                EvalCase(
                    id=f"dita_ot_{index + 1:03d}_human",
                    prompt=f"Need a senior answer here — {prompt}",
                    source="dita_ot_humanized",
                    domain="dita_ot",
                    must_have=tuple(terms),
                    min_length=900,
                    require_sections=True,
                    route="dita_ot",
                )
            )

    return cases[:limit] if limit > 0 else cases


def _term_in_text(term: str, lowered: str) -> bool:
    key = term.lower().strip()
    if not key:
        return False
    if key in lowered:
        return True
    spaced = key.replace("-", " ")
    if spaced in lowered:
        return True
    compact = key.replace("-", "")
    return compact in lowered.replace(" ", "").replace("-", "")


def score_answer(answer: str, case: EvalCase) -> dict[str, Any]:
    text = (answer or "").strip()
    lowered = text.lower()
    checks: dict[str, bool] = {}

    checks["non_empty"] = bool(text)
    checks["min_length"] = len(text) >= case.min_length
    checks["no_weak_phrases"] = not any(phrase in lowered for phrase in WEAK_PHRASES)

    for term in case.must_have:
        checks[f"must_have:{term}"] = _term_in_text(term, lowered)

    if case.require_sections:
        for marker in SECTION_MARKERS:
            checks[f"section:{marker}"] = marker in lowered

    passed = all(checks.values())
    score = round(100 * sum(1 for ok in checks.values() if ok) / max(len(checks), 1), 1)
    failed_checks = [name for name, ok in checks.items() if not ok]
    return {
        "passed": passed,
        "score": score,
        "checks": checks,
        "failed_checks": failed_checks,
        "answer_chars": len(text),
        "answer_preview": text[:220].replace("\n", " "),
    }


async def _answer_for_case(case: EvalCase) -> str:
    if case.route == "dita_ot":
        return chat_service._build_dita_ot_preprocess_runtime_fallback_response(case.prompt) or ""

    from app.services.learned_qa_service import try_build_learned_qa_fallback_answer

    learned = try_build_learned_qa_fallback_answer(case.prompt)
    if learned:
        return learned

    return await chat_service._build_local_fallback_response(
        case.prompt,
        tenant_id="kone",
        answer_mode="grounded_dita_answer",
    )


async def run_eval(cases: list[EvalCase], concurrency: int = 8) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(concurrency)

    async def _run_one(case: EvalCase) -> dict[str, Any]:
        async with semaphore:
            try:
                answer = await _answer_for_case(case)
            except Exception as exc:  # noqa: BLE001
                answer = ""
                error = str(exc)
            else:
                error = ""
            scored = score_answer(answer, case)
            return {
                "id": case.id,
                "prompt": case.prompt,
                "source": case.source,
                "domain": case.domain,
                "route": case.route,
                "error": error,
                **scored,
            }

    rows = await asyncio.gather(*[_run_one(case) for case in cases])

    passed = sum(1 for row in rows if row.get("passed"))
    avg_score = round(sum(float(row.get("score") or 0) for row in rows) / max(len(rows), 1), 1)

    def _bucket(rows_subset: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in rows_subset:
            bucket = out.setdefault(
                str(row.get(key)),
                {"total": 0, "passed": 0, "avg_score": 0.0, "scores": []},
            )
            bucket["total"] += 1
            bucket["passed"] += 1 if row.get("passed") else 0
            bucket["scores"].append(float(row.get("score") or 0))
        for bucket in out.values():
            scores = bucket.pop("scores", [])
            bucket["avg_score"] = round(sum(scores) / max(len(scores), 1), 1)
            bucket["pass_rate"] = round(bucket["passed"] / max(bucket["total"], 1), 4)
        return out

    failures = [row for row in rows if not row.get("passed")]
    failures.sort(key=lambda row: float(row.get("score") or 0))

    return {
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "pass_rate": round(passed / max(len(rows), 1), 4),
        "average_score": avg_score,
        "by_source": _bucket(rows, "source"),
        "by_domain": _bucket(rows, "domain"),
        "worst_failures": failures[:20],
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run difficult DITA / DITA-OT / AEM Guides chat evals.")
    parser.add_argument("--limit", type=int, default=0, help="Max cases (0 = all available)")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--suite", choices=("difficult", "full"), default="difficult")
    parser.add_argument("--variants", type=int, default=1, help="Human prefix variants for seed cases")
    parser.add_argument("--json-out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    cases = build_cases(limit=args.limit, suite=args.suite, variants=args.variants)
    report = asyncio.run(run_eval(cases, concurrency=max(1, args.concurrency)))

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Total: {report['total']}")
    print(f"Passed: {report['passed']}")
    print(f"Failed: {report['failed']}")
    print(f"Pass rate: {report['pass_rate']:.1%}")
    print(f"Average score: {report['average_score']}")
    print("\nBy domain:")
    for domain, stats in sorted(report.get("by_domain", {}).items()):
        print(f"  {domain}: {stats['passed']}/{stats['total']} ({stats['pass_rate']:.1%}) avg={stats['avg_score']}")
    print(f"\nReport: {args.json_out}")
    if report["worst_failures"]:
        print("\nWorst failures:")
        for row in report["worst_failures"][:8]:
            print(f"- {row['id']} [{row.get('domain')}] score={row['score']} failed={', '.join(row['failed_checks'][:3])}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
