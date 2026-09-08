"""Download the UI images from an Experience League doc page so an agent can VIEW them
and learn the UI. Experience League images are JS-loaded, but the raw HTML references
them as media_<hash>.png/.svg served from the same directory as the page.

Dependency-light: only needs httpx (already used by the backend). No langchain, no browser.

Usage (from the repo root, or anywhere):
  python scripts/extract_ui_images.py "<EXP_LEAGUE_URL>" [--out DIR] [--max N] [--all-images]

It saves the images to DIR (default ~/expleague_img/<page-slug>/), prints them sorted by
size (largest first = most likely the detailed UI screenshots), and prints the paths so
you can open the top few with the image-reading tool. --all-images includes small
icons and every referenced image, overriding --max without following other pages.
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


def _is_image(content: bytes) -> bool:
    """Recognize the supported media formats without accepting HTML error pages."""
    if content.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
        return True
    return re.match(
        rb"\s*(?:<\?xml\b[^>]*>\s*)?(?:<!--[\s\S]*?-->\s*)*<svg(?:\s|>)",
        content.removeprefix(b"\xef\xbb\xbf"),
    ) is not None


def extract(
    url: str, out_dir: Path, max_n: int, *, all_images: bool = False
) -> list[tuple[int, Path]]:
    import httpx
    base = url.rsplit("/", 1)[0] + "/"
    page = httpx.get(url, timeout=30, follow_redirects=True)
    page.raise_for_status()
    html = page.text
    refs = list(dict.fromkeys(re.findall(r"media_[0-9a-fA-F]+\.(?:png|jpg|jpeg|svg)", html)))
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[tuple[int, Path]] = []
    missing: list[str] = []
    for i, m in enumerate(refs):
        if not all_images and len(saved) >= max_n:
            break
        for cand in (base + m,
                     base.replace("/en/docs/", "/docs/") + m):
            try:
                r = httpx.get(cand, timeout=30, follow_redirects=True)
                r.raise_for_status()
                if _is_image(r.content) and (all_images or len(r.content) > 2000):
                    p = out_dir / f"{i:02d}_{m}"
                    p.write_bytes(r.content)
                    saved.append((len(r.content), p))
                    break
            except httpx.HTTPError:
                continue
        else:
            missing.append(m)
    saved.sort(key=lambda t: -t[0])
    if all_images and missing:
        raise ValueError(
            f"Incomplete extraction: {len(missing)} referenced image(s) could not be saved: "
            + ", ".join(missing)
            + f". Preserved {len(saved)} downloaded image(s) in {out_dir}."
        )
    return saved


def main(argv: list[str]) -> int:
    import httpx

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url")
    ap.add_argument("--out", default=None, help="output dir (default ~/expleague_img/<slug>)")
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument(
        "--all-images", action="store_true",
        help="include small icons and all page images, ignoring --max",
    )
    args = ap.parse_args(argv)
    if args.url.startswith("<") or "…" in args.url:
        print("ERROR: pass the REAL full URL, not a placeholder or ellipsis.", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path(os.path.expanduser("~/expleague_img")) / _slug(args.url)
    try:
        saved = extract(args.url, out, args.max, all_images=args.all_images)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        print(f"ERROR: image extraction failed: {exc}", file=sys.stderr)
        return 1
    if not saved:
        print("No images found (page may have none, or the media path differs).")
        return 0
    view_hint = "view all" if args.all_images else "view the top 2-3"
    print(f"saved {len(saved)} image(s) to {out} (largest first - {view_hint}):")
    for size, p in saved:
        print(f"  {size:8d}  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
