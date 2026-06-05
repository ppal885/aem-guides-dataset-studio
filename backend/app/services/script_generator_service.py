"""
Generates downloadable Python scripts for DITA tooling.

  make_link_checker_script()  → standalone script, stdlib-only, works on any DITA directory
  make_regeneration_script()  → pre-filled API call script to reproduce a generation run
"""
from __future__ import annotations

import json
import textwrap
from datetime import datetime


_LINK_CHECKER_SCRIPT = textwrap.dedent('''\
    #!/usr/bin/env python3
    """
    DITA Link Checker — standalone, no dependencies required (Python 3.8+).

    Scans a DITA bundle directory for broken links:
      - href on topicref / xref / link / image / mapref / keydef (file existence + id fragment)
      - conref (file.dita#topicid/elemid — file + both id parts)
      - keyref (key not defined in any <keydef> in the bundle)

    Usage:
        python check_dita_links.py /path/to/bundle/
        python check_dita_links.py /path/to/bundle/ --json
        python check_dita_links.py /path/to/bundle/ --csv report.csv
        python check_dita_links.py /path/to/bundle/ --no-keyref   # skip keyref check

    Exit code: 0 = no broken links, 1 = broken links found.
    """
    import argparse
    import csv
    import json as _json
    import sys
    import xml.etree.ElementTree as ET
    from pathlib import Path
    from urllib.parse import urlparse


    def _is_external(href: str) -> bool:
        return bool(urlparse(href).scheme in ("http", "https", "ftp", "mailto", "data"))


    def _tag_local(elem: ET.Element) -> str:
        tag = elem.tag
        return tag.split("}")[-1] if "}" in tag else tag


    def _collect_ids(filepath: Path, cache: dict) -> set:
        if filepath in cache:
            return cache[filepath]
        ids: set = set()
        try:
            for _, elem in ET.iterparse(str(filepath), events=("start",)):
                eid = elem.get("id")
                if eid:
                    ids.add(eid)
        except ET.ParseError:
            pass
        cache[filepath] = ids
        return ids


    def _collect_keydefs(filepath: Path) -> set:
        keys: set = set()
        try:
            tree = ET.parse(str(filepath))
            for elem in tree.iter():
                if _tag_local(elem) == "keydef":
                    for k in (elem.get("keys") or "").split():
                        if k:
                            keys.add(k)
        except ET.ParseError:
            pass
        return keys


    def _check_file(source: Path, bundle_root: Path, defined_keys: set, id_cache: dict,
                    check_keyrefs: bool) -> tuple:
        broken = []
        external = []
        try:
            tree = ET.parse(str(source))
        except ET.ParseError as exc:
            return [{"source_file": str(source.relative_to(bundle_root)),
                     "element_tag": "?", "attribute": "xml",
                     "value": source.name, "reason": f"XML parse error: {exc}"}], []

        rel = str(source.relative_to(bundle_root))

        for elem in tree.iter():
            tag = _tag_local(elem)
            scope = elem.get("scope", "")

            # href
            href = elem.get("href")
            if href and scope not in ("external", "peer"):
                if _is_external(href):
                    external.append(href)
                else:
                    path_part, frag = (href.split("#", 1) + [None])[:2]
                    if path_part:
                        resolved = (source.parent / path_part).resolve()
                        if not resolved.exists():
                            broken.append({"source_file": rel, "element_tag": tag,
                                           "attribute": "href", "value": href,
                                           "reason": "File not found"})
                        elif frag and resolved.suffix in (".dita", ".ditamap"):
                            ids = _collect_ids(resolved, id_cache)
                            missing = [p for p in frag.split("/") if p and p not in ids]
                            if missing:
                                broken.append({"source_file": rel, "element_tag": tag,
                                               "attribute": "href", "value": href,
                                               "reason": f"ID(s) not found in target: {', '.join(missing)}"})
                    elif frag:
                        ids = _collect_ids(source, id_cache)
                        missing = [p for p in frag.split("/") if p and p not in ids]
                        if missing:
                            broken.append({"source_file": rel, "element_tag": tag,
                                           "attribute": "href", "value": href,
                                           "reason": f"Same-document ID(s) not found: {', '.join(missing)}"})

            # conref
            conref = elem.get("conref")
            if conref:
                path_part, frag = (conref.split("#", 1) + [None])[:2]
                if path_part:
                    resolved = (source.parent / path_part).resolve()
                    if not resolved.exists():
                        broken.append({"source_file": rel, "element_tag": tag,
                                       "attribute": "conref", "value": conref,
                                       "reason": "File not found"})
                    elif frag:
                        ids = _collect_ids(resolved, id_cache)
                        missing = [p for p in frag.split("/") if p and p not in ids]
                        if missing:
                            broken.append({"source_file": rel, "element_tag": tag,
                                           "attribute": "conref", "value": conref,
                                           "reason": f"ID(s) not found in target: {', '.join(missing)}"})

            # keyref
            if check_keyrefs and defined_keys:
                keyref = elem.get("keyref")
                if keyref:
                    base = keyref.split(".")[-1] if "." in keyref else keyref
                    if base not in defined_keys:
                        broken.append({"source_file": rel, "element_tag": tag,
                                       "attribute": "keyref", "value": keyref,
                                       "reason": "Key not defined in any map in this bundle"})

        return broken, external


    def validate(bundle_dir: Path, check_keyrefs: bool = True) -> dict:
        dita_files = sorted(
            list(bundle_dir.rglob("*.dita")) + list(bundle_dir.rglob("*.ditamap"))
        )

        # Pass 1 — collect keydefs
        defined_keys: set = set()
        if check_keyrefs:
            for f in dita_files:
                defined_keys.update(_collect_keydefs(f))

        # Pass 2 — validate
        all_broken, all_external = [], []
        id_cache: dict = {}
        for f in dita_files:
            b, e = _check_file(f, bundle_dir, defined_keys, id_cache, check_keyrefs)
            all_broken.extend(b)
            all_external.extend(e)

        summary = {
            "broken_hrefs":      sum(1 for b in all_broken if b["attribute"] == "href"),
            "broken_conrefs":    sum(1 for b in all_broken if b["attribute"] == "conref"),
            "broken_keyrefs":    sum(1 for b in all_broken if b["attribute"] == "keyref"),
            "xml_parse_errors":  sum(1 for b in all_broken if b["attribute"] == "xml"),
        }

        return {
            "bundle_dir": str(bundle_dir),
            "total_files": len(dita_files),
            "defined_key_count": len(defined_keys),
            "broken_link_count": len(all_broken),
            "broken_links": all_broken,
            "external_links": sorted(set(all_external)),
            "summary": summary,
        }


    def main():
        ap = argparse.ArgumentParser(
            description="Check a DITA bundle directory for broken links."
        )
        ap.add_argument("bundle_dir", help="Path to the DITA bundle root directory")
        ap.add_argument("--json", dest="as_json", action="store_true",
                        help="Output full report as JSON")
        ap.add_argument("--csv", metavar="FILE",
                        help="Write broken-links table to a CSV file")
        ap.add_argument("--no-keyref", action="store_true",
                        help="Skip keyref validation (faster for large bundles)")
        args = ap.parse_args()

        bundle = Path(args.bundle_dir).resolve()
        if not bundle.is_dir():
            print(f"ERROR: not a directory: {bundle}", file=sys.stderr)
            sys.exit(2)

        report = validate(bundle, check_keyrefs=not args.no_keyref)

        if args.as_json:
            print(_json.dumps(report, indent=2))
        else:
            print(f"\\nDITA Link Check Report")
            print(f"Bundle     : {report['bundle_dir']}")
            print(f"Files      : {report['total_files']}")
            print(f"Keys found : {report['defined_key_count']}")
            print(f"Broken     : {report['broken_link_count']}")
            s = report["summary"]
            if any(s.values()):
                print(f"  hrefs    : {s['broken_hrefs']}")
                print(f"  conrefs  : {s['broken_conrefs']}")
                print(f"  keyrefs  : {s['broken_keyrefs']}")
                print(f"  xml-err  : {s['xml_parse_errors']}")
            if report["broken_links"]:
                print()
                for b in report["broken_links"]:
                    print(f"  [{b['attribute'].upper():7s}] {b['source_file']}")
                    print(f"           -> {b['value']}")
                    print(f"           Reason: {b['reason']}")
            if report["external_links"]:
                print(f"\\nExternal links ({len(report['external_links'])}) — not validated:")
                for u in report["external_links"][:20]:
                    print(f"  {u}")
                if len(report["external_links"]) > 20:
                    print(f"  ... and {len(report['external_links']) - 20} more")

        if args.csv:
            with open(args.csv, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(
                    fh,
                    fieldnames=["source_file", "element_tag", "attribute", "value", "reason"],
                )
                w.writeheader()
                w.writerows(report["broken_links"])
            if not args.as_json:
                print(f"\\nCSV written to: {args.csv}")

        sys.exit(0 if report["broken_link_count"] == 0 else 1)


    if __name__ == "__main__":
        main()
''')


_REGENERATION_SCRIPT_TEMPLATE = textwrap.dedent('''\
    #!/usr/bin/env python3
    """
    DITA Dataset Regenerator — pre-filled with your generation parameters.
    Generated: {generated_at}

    Usage:
        python regenerate.py
        python regenerate.py --api-url http://127.0.0.1:8001 --token dev-bypass
        python regenerate.py --async-mode   # returns immediately, poll for status

    Requirements: Python 3.8+, no third-party packages.
    The backend must be running at --api-url before executing this script.
    """
    import argparse
    import json
    import sys
    import time
    import urllib.error
    import urllib.request

    # Pre-filled generation parameters — edit as needed
    PAYLOAD = {payload_json}

    def post_json(url: str, payload: dict, token: str) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={{"Content-Type": "application/json", "Authorization": f"Bearer {{token}}"}},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            print(f"HTTP {{exc.code}}: {{body}}", file=sys.stderr)
            sys.exit(1)

    def poll_status(api_url: str, run_id: str, token: str) -> dict:
        url = f"{{api_url}}/api/v1/ai/generate-status/{{run_id}}"
        while True:
            result = post_json(url, {{}}, token)  # GET via urllib
            status = result.get("status", "running")
            pct = result.get("progress_percent", 0)
            stage = result.get("current_stage") or ""
            print(f"  Status: {{status}} {{pct}}% {{stage}}")
            if status in ("completed", "failed"):
                return result
            time.sleep(3)

    def main():
        ap = argparse.ArgumentParser(description="Regenerate a DITA dataset via the backend API.")
        ap.add_argument("--api-url", default="{api_url}",
                        help="Backend base URL (default: {{default}})")
        ap.add_argument("--token", default="{token}",
                        help="Bearer auth token (default: {{default}})")
        ap.add_argument("--async-mode", action="store_true",
                        help="Submit and poll asynchronously instead of waiting inline")
        ap.add_argument("--show-payload", action="store_true",
                        help="Print the generation payload and exit")
        args = ap.parse_args()

        if args.show_payload:
            print(json.dumps(PAYLOAD, indent=2))
            return

        endpoint = f"{{args.api_url}}/api/v1/ai-dataset/generate-from-text"
        if args.async_mode:
            endpoint += "?async=true"

        print(f"Submitting to: {{endpoint}}")
        result = post_json(endpoint, PAYLOAD, args.token)

        if args.async_mode:
            run_id = result.get("run_id")
            if not run_id:
                print("No run_id in response:", result, file=sys.stderr)
                sys.exit(1)
            print(f"Run ID: {{run_id}} — polling for completion...")
            result = poll_status(args.api_url, run_id, args.token)

        print(json.dumps(result, indent=2))
        if result.get("status") == "failed" or result.get("error"):
            sys.exit(1)

    if __name__ == "__main__":
        main()
''')


def make_link_checker_script() -> str:
    """Return the complete standalone link-checker Python script source."""
    return _LINK_CHECKER_SCRIPT


def make_regeneration_script(
    api_url: str,
    token: str,
    payload: dict,
) -> str:
    """Return a pre-filled standalone regeneration script for the given payload."""
    return _REGENERATION_SCRIPT_TEMPLATE.format(
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        api_url=api_url,
        token=token,
        payload_json=json.dumps(payload, indent=4),
    )
