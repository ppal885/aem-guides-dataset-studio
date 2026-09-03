"""Gold-quality classifier for the UAC eval corpus.

The eval judges each pipeline plan against the ticket's human "gold" acceptance
criteria. A small number of corpus rows carry a gold that is NOT acceptance
criteria at all - a pointer to another ticket, a resolution marker, or a
conversational comment. Scoring a plan against such a gold produces meaningless
coverage/hallucination numbers (a strong plan is penalised for not matching a
"thank you" comment). This module flags those rows so the scorer can exclude them.

Deliberately NOT length-based: many valid acceptance criteria are terse (one or
two bullets). Length is a poor proxy for quality, so this classifies by CONTENT:

  xref_or_pointer_only  - the gold is essentially "same as GUIDES-N" / a bare URL /
                          "UAC: GUIDES-N" with no self-contained criterion.
  resolution_marker_no_ac - "Not Reproducible" / "Duplicate" / "By Design" and nothing else.
  conversational_no_ac  - a comment-sourced greeting/thanks that only asks questions,
                          with no imperative acceptance criterion.
  near_empty            - effectively no alphabetic content.

Everything else is "high". Standard library only.
"""
from __future__ import annotations

import re

_GUIDES_REF = re.compile(r"GUIDES-\d+", re.IGNORECASE)
_URL = re.compile(r"https?://\S+")
_RESOLUTION = (
    "not reproducible", "won't fix", "wont fix", "duplicate", "by design",
    "cannot reproduce", "works as designed", "not a bug",
)
_AC_IMPERATIVES = ("should", "must", "will ", "shall", "verify", "ensure")


def classify(gold: str | None, source: str | None = None) -> tuple[str, str]:
    """Return (quality, reason). quality is 'high' or 'low'."""

    g = " ".join((gold or "").split())
    low = g.lower()
    # Residual alphabetic content once cross-references and URLs are removed.
    residual = _URL.sub(" ", _GUIDES_REF.sub(" ", g))
    residual = re.sub(r"[^a-zA-Z]", " ", residual)
    letters = len(residual.replace(" ", ""))

    if letters < 12 and (
        _GUIDES_REF.search(g) or _URL.search(g) or "same as" in low or low.startswith("uac:")
    ):
        return "low", "xref_or_pointer_only"
    if len(g) < 40 and any(marker in low for marker in _RESOLUTION):
        return "low", "resolution_marker_no_ac"
    conversational = low.startswith(("hi,", "hi ", "hello", "thank", "thanks", "[~"))
    if (
        str(source) == "comment"
        and conversational
        and "?" in g
        and not any(m in low for m in _AC_IMPERATIVES)
    ):
        return "low", "conversational_no_ac"
    if letters < 12:
        return "low", "near_empty"
    return "high", ""


def is_scorable(row: dict) -> bool:
    """A corpus row is scorable when its gold is genuine acceptance criteria."""

    quality, _ = classify(row.get("human_ac"), row.get("uac_source"))
    return quality == "high"


def run_self_tests() -> None:
    assert classify("UAC: GUIDES-30909", "ac_field") == ("low", "xref_or_pointer_only")
    assert classify("Same as # GUIDES-29065", "ac_field")[0] == "low"
    assert classify("# Not Reproducible", "ac_field") == ("low", "resolution_marker_no_ac")
    assert classify("[~x] Thank you for the fix. Let me confirm. Was this resolved?", "comment")[0] == "low"
    # Valid terse ACs must stay high.
    assert classify("* Correct image should be displayed for valid MathML; broken image for invalid", "ac_field")[0] == "high"
    assert classify("The create dita map should return 200 instead of 503.", "ac_field")[0] == "high"
    assert classify("* The user should be able to send assets to the translation job directly.", "ac_field")[0] == "high"
    print("gold_quality self-tests: PASS")


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(Path(__file__).with_name("corpus.jsonl")))
    ap.add_argument("--tag", action="store_true", help="write gold_quality back into the corpus")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_tests()
        raise SystemExit(0)
    path = Path(args.corpus)
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    low = 0
    for r in rows:
        q, reason = classify(r.get("human_ac"), r.get("uac_source"))
        r["gold_quality"] = q
        r["gold_quality_reason"] = reason
        if q == "low":
            low += 1
            print(f"  low: {r['key']:14s} {reason:24s} | {' '.join((r.get('human_ac') or '').split())[:70]}")
    print(f"{low}/{len(rows)} low-quality gold ({100*low/len(rows):.1f}%)")
    if args.tag:
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        print(f"tagged corpus written: {path}")
