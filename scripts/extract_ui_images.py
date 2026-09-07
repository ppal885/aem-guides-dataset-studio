"""Download the UI images from an Experience League doc page so an agent can VIEW them
and learn the UI. Experience League images are JS-loaded, but the raw HTML references
them as media_<hash>.png/.svg served from the same directory as the page.

Dependency-light: only needs httpx (already used by the backend). No langchain, no browser.

Usage (from the repo root, or anywhere):
  python scripts/extract_ui_images.py "<EXP_LEAGUE_URL>" [--out DIR] [--max N]

It saves the images to DIR (default ~/expleague_img/<page-slug>/), prints them sorted by
size (largest first = most likely the detailed UI screenshots), and prints the paths so
you can open the top few with the image-reading tool.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def _slug(url: str) -> str:
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_.-]", "_", tail) or "page"


def extract(url: str, out_dir: Path, max_n: int) -> list[tuple[int, Path]]:
    import httpx
    base = url.rsplit("/", 1)[0] + "/"
    html = httpx.get(url, timeout=30, follow_redirects=True).text
    refs = list(dict.fromkeys(re.findall(r"media_[0-9a-fA-F]+\.(?:png|jpg|jpeg|svg)", html)))
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[tuple[int, Path]] = []
    for i, m in enumerate(refs):
        if len(saved) >= max_n:
            break
        for cand in (base + m,
                     base.replace("/en/docs/", "/docs/") + m):
            try:
                r = httpx.get(cand, timeout=30, follow_redirects=True)
                if r.status_code == 200 and len(r.content) > 2000:
                    p = out_dir / f"{i:02d}_{m}"
                    p.write_bytes(r.content)
                    saved.append((len(r.content), p))
                    break
            except Exception:  # noqa: BLE001
                continue
    saved.sort(key=lambda t: -t[0])
    return saved


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url")
    ap.add_argument("--out", default=None, help="output dir (default ~/expleague_img/<slug>)")
    ap.add_argument("--max", type=int, default=20)
    args = ap.parse_args(argv)
    if args.url.startswith("<") or "…" in args.url:
        print("ERROR: pass the REAL full URL, not a placeholder or ellipsis.", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path(os.path.expanduser("~/expleague_img")) / _slug(args.url)
    saved = extract(args.url, out, args.max)
    if not saved:
        print("No images found (page may have none, or the media path differs).")
        return 0
    print(f"saved {len(saved)} image(s) to {out} (largest first - view the top 2-3):")
    for size, p in saved:
        print(f"  {size:8d}  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
