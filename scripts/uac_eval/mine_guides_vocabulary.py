"""Mine product vocabulary (UI surfaces, features, terms) from the ingested AEM Guides
RAG corpus, so the whole ingested doc set actually GROWS the skill's vocabulary instead
of sitting unused. Extracts candidate UI/product terms from the `aem_guides` Chroma
collection, ranks them by document frequency, drops terms already in
data/guides_vocabulary.json canonical_terms, and prints the top candidates to review and
add.

Run from the backend env (needs the local Chroma corpus):
  cd backend && python ../scripts/uac_eval/mine_guides_vocabulary.py --top 50
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# UI/product suffixes that mark a Guides surface or feature (multi-word, Capitalized).
_UI_SUFFIX = (r"Panel|Dashboard|Reports?|Presets?|Console|Editor|Tab|Dialog|Wizard|View|"
              r"Menu|Pop-?up|Settings|Profile|Layout|Template|Variables?|Field|Fields|"
              r"Filter|Baseline|Scheme|Metadata|Preview|Collection|Workflow")
# Require EVERY word Title-Case (drops sentence-fragment / TOC-heading noise like
# "Migrate extension framework to Editor").
_TERM_RE = re.compile(
    r"\b([A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9-]+){0,3}\s+(?:" + _UI_SUFFIX + r"))\b")
# Also standalone capitalized product terms of these exact words.
_STANDALONE_RE = re.compile(
    r"\b((?:" + _UI_SUFFIX + r"))\b")
_STOP = {"The", "This", "You", "For", "See", "Note", "In", "To", "A", "An", "It",
         "Select", "Click", "Use", "Add", "Once", "When", "If", "These", "Your"}


def _load_canonical(vocab_path: Path) -> set[str]:
    try:
        d = json.loads(vocab_path.read_text(encoding="utf-8"))
        terms = set(t.lower() for t in d.get("canonical_terms", []))
        for e in d.get("block", []) + d.get("advise", []):
            terms.add(str(e.get("correct", "")).lower())
        return terms
    except Exception:  # noqa: BLE001
        return set()


def _iter_documents(coll, batch: int = 2000):
    total = coll.count()
    off = 0
    while off < total:
        got = coll.get(limit=batch, offset=off, include=["documents"])
        docs = got.get("documents") or []
        if not docs:
            break
        for d in docs:
            yield d or ""
        off += len(docs)


def mine(coll, canonical: set[str]) -> Counter:
    freq: Counter = Counter()
    for doc in _iter_documents(coll):
        found = set()
        for m in _TERM_RE.finditer(doc):
            term = re.sub(r"\s+", " ", m.group(1)).strip()
            first = term.split()[0]
            if first in _STOP:
                # keep the tail suffix phrase without the stopword lead
                parts = term.split()
                if len(parts) > 1:
                    term = " ".join(parts[1:])
                else:
                    continue
            if len(term) < 4 or term.lower() in canonical:
                continue
            found.add(term)
        for m in _STANDALONE_RE.finditer(doc):
            t = m.group(1)
            if t.lower() not in canonical:
                found.add(t)
        for t in found:
            freq[t] += 1
    return freq


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--min-freq", type=int, default=3)
    args = ap.parse_args()

    backend = Path(__file__).resolve().parents[2] / "backend"
    sys.path.insert(0, str(backend))
    try:
        from dotenv import load_dotenv
        load_dotenv(str(backend / ".env"))
        from app.services.vector_store_service import _get_client, CHROMA_COLLECTION_AEM_GUIDES
    except Exception as exc:  # noqa: BLE001
        print(f"Cannot load backend chroma services: {exc}", file=sys.stderr)
        return 2

    vocab = backend.parent / ".codex" / "skills" / "test-plan-generation" / "data" / "guides_vocabulary.json"
    canonical = _load_canonical(vocab)
    client = _get_client()
    if not client:
        print("Chroma client unavailable (is the corpus present?)", file=sys.stderr)
        return 2
    coll = client.get_collection(CHROMA_COLLECTION_AEM_GUIDES)
    freq = mine(coll, canonical)
    ranked = [(t, c) for t, c in freq.most_common() if c >= args.min_freq]
    print(f"corpus chunks: {coll.count()} | already-canonical terms skipped: {len(canonical)}")
    print(f"top {args.top} candidate product terms NOT yet in guides_vocabulary (freq >= {args.min_freq}):\n")
    for t, c in ranked[: args.top]:
        print(f"{c:5d}  {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
