"""Attachment-ingestion helper for UAC/test-plan authoring (skill gap G7).

Turns a Jira ticket's attachments into analysable artifacts so a UAC author never has
to describe an attachment from its filename:
  - video (mp4/mov/webm/mkv) -> evenly spaced frames (PNG) via OpenCV, so the workflow
    the customer performed can be read frame by frame.
  - pdf                       -> per-page extracted text index (+ pages matching optional
    keywords flagged), via pypdf.
  - image (png/jpg/gif/webp)  -> downloaded as-is (already readable).
  - other                     -> downloaded as-is and listed.

Writes everything under an output directory plus a manifest.json describing each
artifact and its derived files, and prints the manifest so the caller can then read
the frames / images / pdf-text.

Auth: uses the backend JiraClient (loads backend/.env), the same path the test-plan
skill uses when the Atlassian MCP is unavailable. External (non-Jira) URLs can be
ingested with --url; those are fetched without Jira auth and may fail on gated hosts.

Usage:
  python scripts/jira_attachment_ingest.py GUIDES-52444 --out <dir> [--frames 14]
        [--keywords "baseline,removed,503"] [--max-pdf-pages 40]
  python scripts/jira_attachment_ingest.py --url https://host/clip.mp4 --out <dir>

Dependencies are optional and degrade gracefully: without OpenCV, videos are still
downloaded (frames skipped with a note); without pypdf, PDFs are downloaded (text
skipped with a note).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
PDF_EXT = {".pdf"}


def _classify_kind(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in IMAGE_EXT:
        return "image"
    if ext in PDF_EXT:
        return "pdf"
    return "other"


def _extract_video_frames(video_path: str, out_dir: str, count: int) -> list[str]:
    try:
        import cv2
    except Exception:
        return []
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames: list[str] = []
    if total <= 0:
        cap.release()
        return frames
    for i in range(count):
        fno = int(total * i / count)
        cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = 1400 / max(w, 1)
        if scale < 1:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        secs = int(fno / fps) if fps else i
        out = os.path.join(out_dir, f"frame_{i:02d}_t{secs}s.png")
        cv2.imwrite(out, frame)
        frames.append(out)
    cap.release()
    return frames


def _extract_pdf_text(pdf_path: str, out_dir: str, max_pages: int, keywords: list[str]) -> dict:
    try:
        from pypdf import PdfReader
    except Exception:
        return {"available": False}
    reader = PdfReader(pdf_path)
    pages = len(reader.pages)
    kw = [k.lower() for k in keywords]
    lines = []
    hits = []
    for i, page in enumerate(reader.pages[: max_pages or pages]):
        text = " ".join((page.extract_text() or "").split())
        lines.append(f"--- page {i} ---\n{text}")
        if kw and any(k in text.lower() for k in kw):
            hits.append(i)
    txt_path = os.path.join(out_dir, os.path.basename(pdf_path) + ".txt")
    Path(txt_path).write_text("\n\n".join(lines), encoding="utf-8")
    return {"available": True, "pages": pages, "text_index": txt_path, "keyword_hit_pages": hits}


def _download(url: str, dest: str, headers: dict | None) -> int:
    import requests
    r = requests.get(url, headers=headers or {}, timeout=120, verify=False)
    Path(dest).write_bytes(r.content)
    return len(r.content)


def ingest(
    issue_key: str | None,
    out_dir: str,
    *,
    url: str | None = None,
    frames: int = 14,
    keywords: list[str] | None = None,
    max_pdf_pages: int = 40,
) -> dict:
    keywords = keywords or []
    os.makedirs(out_dir, exist_ok=True)
    items = []  # list of (filename, url)
    headers = None

    if url:
        items.append((os.path.basename(url.split("?")[0]) or "download.bin", url))
    if issue_key:
        from dotenv import load_dotenv
        load_dotenv(str(Path(__file__).resolve().parents[1] / "backend" / ".env"))
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        from app.services.jira_client import JiraClient
        client = JiraClient()
        headers = client._headers()
        issue = client.get_issue(issue_key, fields="attachment")
        for a in issue["fields"].get("attachment", []):
            items.append((a["filename"], a.get("content")))

    manifest = {"issue_key": issue_key, "out_dir": out_dir, "attachments": []}
    for filename, content_url in items:
        safe = filename.replace("/", "_").replace("\\", "_")
        dest = os.path.join(out_dir, safe)
        entry = {"filename": filename, "kind": _classify_kind(filename), "path": dest, "derived": []}
        try:
            size = _download(content_url, dest, headers)
            entry["bytes"] = size
        except Exception as exc:
            entry["error"] = f"download failed: {exc}"
            manifest["attachments"].append(entry)
            continue
        if entry["kind"] == "video":
            fr = _extract_video_frames(dest, out_dir, frames)
            entry["derived"] = fr
            if not fr:
                entry["note"] = "OpenCV unavailable or unreadable video; frames not extracted"
        elif entry["kind"] == "pdf":
            pdf = _extract_pdf_text(dest, out_dir, max_pdf_pages, keywords)
            entry["pdf_text"] = pdf
            if not pdf.get("available"):
                entry["note"] = "pypdf unavailable; PDF downloaded, text not extracted"
        manifest["attachments"].append(entry)

    Path(os.path.join(out_dir, "manifest.json")).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def run_self_tests() -> None:
    assert _classify_kind("demo.mp4") == "video"
    assert _classify_kind("Screenshot.PNG") == "image"
    assert _classify_kind("log.pdf") == "pdf"
    assert _classify_kind("data.zip") == "other"
    print("jira_attachment_ingest self-tests: PASS")


if __name__ == "__main__":
    try:  # Windows consoles default to cp1252; attachment names carry Unicode.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("issue_key", nargs="?", default=None)
    ap.add_argument("--url", default=None)
    ap.add_argument("--out", required=False, default=None)
    ap.add_argument("--frames", type=int, default=14)
    ap.add_argument("--keywords", default="")
    ap.add_argument("--max-pdf-pages", type=int, default=40)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_tests()
        raise SystemExit(0)
    if not args.out:
        ap.error("--out is required")
    kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
    m = ingest(args.issue_key, args.out, url=args.url, frames=args.frames,
               keywords=kws, max_pdf_pages=args.max_pdf_pages)
    for a in m["attachments"]:
        d = a.get("derived") or []
        pdf = a.get("pdf_text") or {}
        extra = f"{len(d)} frames" if d else (f"{pdf.get('pages')}p text, hits {pdf.get('keyword_hit_pages')}" if pdf.get("available") else a.get("note", ""))
        print(f"{a['kind']:6s} {a['filename']}  -> {a.get('bytes','?')} bytes  {extra}")
    print(f"manifest: {os.path.join(args.out, 'manifest.json')}")
