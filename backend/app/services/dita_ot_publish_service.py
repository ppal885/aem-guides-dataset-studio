"""Local DITA-OT publishing helpers for chat tools."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = PROJECT_ROOT / "output" / "dita-ot-chat"


def _safe_slug(value: str, fallback: str = "dita-ot-publish") -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip()).strip("-")
    return (slug or fallback)[:80]


def _dita_ot_cli_path() -> Path | None:
    configured = (os.getenv("DITA_OT_CLI") or "").strip()
    if configured:
        path = Path(configured)
        if path.exists():
            return path
    unix_candidates = (
        PROJECT_ROOT / "tools" / "dita-ot-4.4-runtime" / "dita-ot-4.4" / "bin" / "dita",
        PROJECT_ROOT / "tools" / "dita-ot-4.4" / "bin" / "dita",
        PROJECT_ROOT / "tools" / "dita-ot" / "bin" / "dita",
    )
    windows_candidates = (
        PROJECT_ROOT / "tools" / "dita-ot-4.4-runtime" / "dita-ot-4.4" / "bin" / "dita.bat",
        PROJECT_ROOT / "tools" / "dita-ot-4.4" / "bin" / "dita.bat",
        PROJECT_ROOT / "tools" / "dita-ot" / "bin" / "dita.bat",
    )
    candidates = windows_candidates + unix_candidates if os.name == "nt" else unix_candidates + windows_candidates
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _resolve_workspace_path(value: str | None) -> Path | None:
    raw = (value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    root = PROJECT_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("input_map must be inside the project workspace")
    if not resolved.exists() or not resolved.is_file():
        raise ValueError(f"input_map does not exist: {resolved}")
    if resolved.suffix.lower() != ".ditamap":
        raise ValueError("input_map must point to a .ditamap file")
    return resolved


def _artifact_download_url(run_id: str, artifact_type: str, filename: str) -> str:
    safe_filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return f"/api/v1/chat/dita-ot-artifacts/{run_id}/{artifact_type}/{safe_filename}?download=1"


def _looks_like_xml_lang_chunk_request(value: str) -> bool:
    text = (value or "").lower()
    return (
        ("xml:lang" in text or "xml lang" in text or "language" in text)
        and ("chunk" in text or "chunking" in text)
    )


def _write_xml_lang_chunk_dataset(work_dir: Path, title: str) -> Path:
    """Write a focused DITA-OT publishing dataset for xml:lang + chunk behavior."""
    slug = _safe_slug(title, fallback="xml-lang-chunk-publishing")
    topics_dir = work_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    map_path = work_dir / f"{slug}.ditamap"

    map_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map id="xml-lang-chunk-publishing" xml:lang="en-US">
  <title>{title}</title>
  <topicref href="topics/overview.dita" chunk="by-topic"/>
  <topicref href="topics/publishing-branch.dita" chunk="select-branch to-content">
    <topicref href="topics/pdf-oracles.dita" chunk="by-topic"/>
    <topicref href="topics/html5-oracles.dita" xml:lang="fr-FR" chunk="by-topic"/>
  </topicref>
  <topicref href="topics/mixed-language.dita" xml:lang="fr-FR" chunk="to-content"/>
</map>
""",
        encoding="utf-8",
    )

    (topics_dir / "overview.dita").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="overview" xml:lang="en-US">
  <title>How xml:lang and chunk are tested together</title>
  <shortdesc>This topic defines the publishing behavior that the dataset is intended to verify.</shortdesc>
  <conbody>
    <section id="behavior"><title>Behavior under test</title>
      <p>The root map declares <codeph>xml:lang="en-US"</codeph>, so topics without an overriding language inherit English language context through the publishing pipeline.</p>
      <p>The map also applies valid DITA chunk tokens on topic references: <codeph>by-topic</codeph>, <codeph>to-content</codeph>, and <codeph>select-branch</codeph>.</p>
    </section>
    <section id="invalid-tokens"><title>Invalid tokens guarded by this dataset</title>
      <p>The dataset intentionally avoids non-standard tokens such as <codeph>split</codeph> and <codeph>to-navigation</codeph>.</p>
    </section>
  </conbody>
</concept>
""",
        encoding="utf-8",
    )

    (topics_dir / "publishing-branch.dita").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="publishing-branch">
  <title>Publishing branch with selected content</title>
  <shortdesc>This parent topic inherits English from the map and owns a branch selected for publishing.</shortdesc>
  <conbody>
    <section id="branch"><title>Branch selection</title>
      <p>The parent topicref uses <codeph>chunk="select-branch to-content"</codeph> so the selected branch contributes content to the generated result while preserving predictable child-topic behavior.</p>
      <p>This catches regressions where a processor ignores branch selection, drops descendants, or treats chunk values as a single unsupported token.</p>
    </section>
  </conbody>
</concept>
""",
        encoding="utf-8",
    )

    (topics_dir / "pdf-oracles.dita").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="pdf-oracles" xml:lang="en-US">
  <title>PDF2 publishing oracle</title>
  <shortdesc>PDF output should preserve the selected branch and language-sensitive generated text.</shortdesc>
  <conbody>
    <section id="pdf-checks"><title>PDF checks</title>
      <ul>
        <li>DITA-OT exits with code 0 for the <codeph>pdf</codeph> transtype.</li>
        <li>The generated PDF is non-empty and includes this topic title.</li>
        <li>English topics remain in the English language context inherited from the map.</li>
        <li>The table of contents or bookmarks include selected branch topics rather than omitting descendants.</li>
      </ul>
    </section>
  </conbody>
</concept>
""",
        encoding="utf-8",
    )

    (topics_dir / "html5-oracles.dita").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="html5-oracles" xml:lang="fr-FR">
  <title>Oracle de publication HTML5</title>
  <shortdesc>Ce sujet vérifie que la langue française peut remplacer la langue héritée de la carte.</shortdesc>
  <conbody>
    <section id="html5-checks"><title>Vérifications HTML5</title>
      <ul>
        <li>La transformation <codeph>html5</codeph> se termine avec le code 0.</li>
        <li>La page générée conserve le contenu français et les liens vers les sujets du même embranchement.</li>
        <li>Le contexte de langue du sujet est <codeph>fr-FR</codeph>, même si la carte racine utilise <codeph>en-US</codeph>.</li>
      </ul>
    </section>
  </conbody>
</concept>
""",
        encoding="utf-8",
    )

    (topics_dir / "mixed-language.dita").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="mixed-language">
  <title>Mixed language inheritance checkpoint</title>
  <shortdesc>This topic has no topic-level xml:lang and relies on the map topicref override.</shortdesc>
  <conbody>
    <section id="topicref-override"><title>Topicref language override</title>
      <p>The map references this topic with <codeph>xml:lang="fr-FR"</codeph> and <codeph>chunk="to-content"</codeph>.</p>
      <p>Publishing should keep the topic included in output and should not lose the language context when the content is chunked into the output.</p>
    </section>
  </conbody>
</concept>
""",
        encoding="utf-8",
    )

    (work_dir / "README.md").write_text(
        f"""# {title}

This generated corpus is for DITA-OT publishing validation of `xml:lang` and `chunk`.

## What it covers

- Map-level `xml:lang="en-US"` inheritance.
- Topic-level `xml:lang="fr-FR"` override.
- Topicref-level `xml:lang="fr-FR"` override.
- Valid chunk tokens only: `by-topic`, `to-content`, and `select-branch`.
- PDF, classic XHTML, and HTML5 publishing oracles.

## Explicit guardrail

Do not use invalid chunk values such as `split` or `to-navigation`.

## Useful commands

```bash
dita --input={map_path.name} --format=pdf --output=publish/pdf
dita --input={map_path.name} --format=xhtml --output=publish/xhtml
dita --input={map_path.name} --format=html5 --output=publish/html5
```
""",
        encoding="utf-8",
    )
    return map_path


def _write_sample_dataset(work_dir: Path, title: str) -> Path:
    if _looks_like_xml_lang_chunk_request(title):
        return _write_xml_lang_chunk_dataset(work_dir, title)

    slug = _safe_slug(title)
    map_path = work_dir / f"{slug}.ditamap"
    topic_path = work_dir / f"{slug}-topic.dita"
    map_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map id="{slug}" xml:lang="en-US">
  <title>{title}</title>
  <topicref href="{topic_path.name}"/>
</map>
""",
        encoding="utf-8",
    )
    topic_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="{slug}-topic" xml:lang="en-US">
  <title>{title}</title>
  <shortdesc>DITA-OT publish smoke test generated from the chatbot.</shortdesc>
  <body>
    <p>This topic verifies that the local DITA-OT CLI can publish a DITA map to PDF.</p>
    <section id="oracle"><title>Expected oracle</title>
      <p>The PDF build passes when DITA-OT exits with code 0 and produces a non-empty PDF file.</p>
    </section>
  </body>
</topic>
""",
        encoding="utf-8",
    )
    return map_path


def _run_dita(input_map: Path, fmt: str, output_dir: Path, timeout_seconds: int) -> dict[str, Any]:
    cli = _dita_ot_cli_path()
    if cli is None:
        return {
            "ok": False,
            "format": fmt,
            "exit_code": None,
            "stdout": "",
            "stderr": "DITA-OT CLI not found. Set DITA_OT_CLI or install tools/dita-ot-4.4-runtime.",
            "output_dir": str(output_dir),
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(cli), "--input", str(input_map), "--format", fmt, "--output", str(output_dir)]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )
    return {
        "ok": proc.returncode == 0,
        "format": fmt,
        "exit_code": proc.returncode,
        "command": " ".join(cmd),
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "output_dir": str(output_dir),
    }


async def publish_with_dita_ot(
    *,
    input_map: str | None = None,
    prompt: str = "DITA-OT PDF smoke test",
    output_format: str = "pdf",
    package_name: str = "",
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Generate or publish DITA content with local DITA-OT and return artifact paths."""
    requested = (output_format or "pdf").strip().lower()
    if requested == "pdf2":
        requested = "pdf"
    if requested == "html":
        requested = "xhtml"
    if requested not in {"pdf", "xhtml", "html5", "both", "all"}:
        raise ValueError("output_format must be one of: pdf, html, xhtml, html5, both, all")

    run_id = str(uuid4())
    slug = _safe_slug(package_name or prompt)
    work_dir = OUTPUT_ROOT / run_id / "source"
    publish_dir = OUTPUT_ROOT / run_id / "publish"
    work_dir.mkdir(parents=True, exist_ok=True)
    publish_dir.mkdir(parents=True, exist_ok=True)

    resolved_map = _resolve_workspace_path(input_map)
    if resolved_map:
        source_map = work_dir / resolved_map.name
        if resolved_map.parent != work_dir:
            for item in resolved_map.parent.iterdir():
                target = work_dir / item.name
                if item.is_file():
                    shutil.copy2(item, target)
                elif item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
        input_for_build = source_map if source_map.exists() else resolved_map
    else:
        input_for_build = _write_sample_dataset(work_dir, prompt or slug)

    if requested == "both":
        formats = ["pdf", "html5"]
    elif requested == "all":
        formats = ["pdf", "xhtml", "html5"]
    else:
        formats = [requested]
    publish: dict[str, Any] = {}
    for fmt in formats:
        publish[fmt] = _run_dita(input_for_build, fmt, publish_dir / fmt, timeout_seconds)

    pdf_files = sorted((publish_dir / "pdf").glob("*.pdf")) if (publish_dir / "pdf").exists() else []
    xhtml_files = sorted((publish_dir / "xhtml").rglob("*.html")) if (publish_dir / "xhtml").exists() else []
    html_files = sorted((publish_dir / "html5").rglob("*.html")) if (publish_dir / "html5").exists() else []
    zip_path = OUTPUT_ROOT / run_id / f"{slug}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for base in (work_dir, publish_dir):
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(OUTPUT_ROOT / run_id).as_posix())
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "run_id": run_id,
                    "prompt": prompt,
                    "input_map": str(input_for_build),
                    "output_format": requested,
                    "created_at": datetime.now().isoformat(),
                    "pdf_files": [str(path) for path in pdf_files],
                    "xhtml_files": [str(path) for path in xhtml_files],
                    "html_files": [str(path) for path in html_files],
                },
                indent=2,
            ),
        )

    ok = all(bool(item.get("ok")) for item in publish.values()) if publish else False
    return {
        "status": "success" if ok else "error",
        "summary": "DITA-OT publish completed." if ok else "DITA-OT publish failed; inspect stderr.",
        "run_id": run_id,
        "input_map": str(input_for_build),
        "output_format": requested,
        "publish": publish,
        "pdf_files": [str(path) for path in pdf_files],
        "pdf_download_urls": [_artifact_download_url(run_id, "pdf", path.name) for path in pdf_files],
        "xhtml_files": [str(path) for path in xhtml_files],
        "html_files": [str(path) for path in html_files],
        "artifact_zip": str(zip_path),
        "artifact_zip_download_url": _artifact_download_url(run_id, "zip", zip_path.name),
        "artifact_counts": {
            "pdf_files": len(pdf_files),
            "xhtml_files": len(xhtml_files),
            "html_files": len(html_files),
        },
        "oracle": {
            "dita_ot_exit_zero": ok,
            "pdf_created": bool(pdf_files and pdf_files[0].stat().st_size > 0) if "pdf" in formats else None,
            "xhtml_created": bool(xhtml_files) if "xhtml" in formats else None,
            "html_created": bool(html_files) if "html5" in formats else None,
        },
    }
