"""Local DITA-OT publishing helpers for chat tools."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zipfile
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.dita_publishing_construct_registry import (
    SUMMARY_FILENAME,
    build_publishing_corpus,
)


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


def _looks_like_copy_to_chunk_lang_request(value: str) -> bool:
    text = (value or "").lower()
    return (
        ("copy-to" in text or "copy to" in text or "copyto" in text)
        and ("chunk" in text or "chunking" in text)
        and ("xml:lang" in text or "xml lang" in text or "language" in text)
    )


def _xml_text(value: str) -> str:
    return escape(value or "", quote=False)


def _write_copy_to_chunk_lang_dataset(work_dir: Path, title: str) -> Path:
    """Write a focused DITA-OT publishing dataset for copy-to + chunk + xml:lang."""
    slug = _safe_slug(title, fallback="copy-to-chunk-lang-publishing")
    safe_title = _xml_text(title)
    topics_dir = work_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    map_path = work_dir / f"{slug}.ditamap"

    map_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map id="copy-to-chunk-lang-publishing" xml:lang="en-US">
  <title>{safe_title}</title>
  <topicref href="topics/intro.dita" chunk="by-topic"/>
  <topicref href="topics/reused-source.dita" copy-to="topics/reused-copy-a.dita" chunk="by-topic">
    <topicmeta><navtitle>Reuse instance A via copy-to</navtitle></topicmeta>
  </topicref>
  <topicref href="topics/reused-source.dita" copy-to="topics/reused-copy-b.dita" chunk="by-topic">
    <topicmeta><navtitle>Reuse instance B via copy-to</navtitle></topicmeta>
  </topicref>
  <topicref href="topics/french-overview.dita" copy-to="topics/fr-copy-target.dita" xml:lang="fr-FR" chunk="by-topic"/>
  <topicref href="topics/pdf-html5-oracles.dita" chunk="to-content"/>
</map>
""",
        encoding="utf-8",
    )

    (topics_dir / "intro.dita").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="intro" xml:lang="en-US">
  <title>copy-to, chunk, and xml:lang publishing behavior</title>
  <shortdesc>This topic introduces the behavior verified by the publishing corpus.</shortdesc>
  <conbody>
    <section id="behavior"><title>Behavior under test</title>
      <p><xmlatt>copy-to</xmlatt> gives a topic reference a distinct effective target URI for publishing while the source content remains at the original <xmlatt>href</xmlatt>.</p>
      <p><xmlatt>chunk</xmlatt> controls output boundaries, so the copied effective targets can become distinct HTML5 pages and distinct PDF navigation entries.</p>
      <p><xmlatt>xml:lang</xmlatt> controls language context and should not be changed just because a topicref uses <xmlatt>copy-to</xmlatt>.</p>
    </section>
  </conbody>
</concept>
""",
        encoding="utf-8",
    )

    (topics_dir / "reused-source.dita").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="reused-source" xml:lang="en-US">
  <title>Reusable source topic</title>
  <shortdesc>The map references this same physical topic twice with different copy-to targets.</shortdesc>
  <conbody>
    <section id="copy-to"><title>Expected copy-to effect</title>
      <p>This topic should publish once as <filepath>reused-copy-a</filepath> and once as <filepath>reused-copy-b</filepath> when chunked by topic.</p>
      <p>The source file remains <filepath>reused-source.dita</filepath>; <xmlatt>copy-to</xmlatt> does not rename or move the authored file.</p>
    </section>
  </conbody>
</concept>
""",
        encoding="utf-8",
    )

    (topics_dir / "french-overview.dita").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="french-overview" xml:lang="fr-FR">
  <title>Exemple français avec copy-to</title>
  <shortdesc>Ce sujet vérifie que la langue française reste associée au contenu publié.</shortdesc>
  <conbody>
    <section id="lang"><title>Contrôle de langue</title>
      <p>Le topicref de la carte utilise <codeph>copy-to="topics/fr-copy-target.dita"</codeph> et <codeph>xml:lang="fr-FR"</codeph>.</p>
      <p>La transformation ne doit pas convertir ce contenu en contexte anglais simplement parce que la carte racine utilise <codeph>en-US</codeph>.</p>
    </section>
  </conbody>
</concept>
""",
        encoding="utf-8",
    )

    (topics_dir / "pdf-html5-oracles.dita").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="pdf-html5-oracles" xml:lang="en-US">
  <title>PDF and HTML5 oracle for copy-to publishing</title>
  <shortdesc>These are the observable checks for generated PDF and HTML5 output.</shortdesc>
  <conbody>
    <section id="html5"><title>HTML5 checks</title>
      <ul>
        <li>HTML5 output should include pages named from the copy-to targets, such as <filepath>reused-copy-a.html</filepath> and <filepath>reused-copy-b.html</filepath>.</li>
        <li>Both copied pages should contain the same reusable source topic content.</li>
        <li>The French copy target should preserve French text and language context.</li>
      </ul>
    </section>
    <section id="pdf"><title>PDF checks</title>
      <ul>
        <li>PDF output should contain navigation entries for both copy-to instances.</li>
        <li>Internal links and TOC entries should resolve to distinct effective targets rather than collapsing both references into one ambiguous instance.</li>
        <li>PDF publishing should not report duplicate effective URI collisions for the unique copy-to targets.</li>
      </ul>
    </section>
  </conbody>
</concept>
""",
        encoding="utf-8",
    )

    (work_dir / "README.md").write_text(
        f"""# {safe_title}

This generated corpus validates DITA-OT publishing behavior for `copy-to`, `chunk`, and `xml:lang`.

## What it covers

- Same source topic reused twice with unique `copy-to` targets.
- `chunk="by-topic"` on copied topic references to force distinct output boundaries.
- Root map language `xml:lang="en-US"`.
- French topic/topicref override using `xml:lang="fr-FR"`.
- PDF and HTML5 observable oracles.

## Expected output

- HTML5 should create distinct copy-to target pages such as `reused-copy-a.html` and `reused-copy-b.html`.
- PDF should include both copy-to instances in TOC/navigation when included by the transform.
- The authored source remains `topics/reused-source.dita`; `copy-to` changes the effective publishing URI, not the physical source.

## Useful commands

```bash
dita --input={map_path.name} --format=pdf --output=publish/pdf
dita --input={map_path.name} --format=html5 --output=publish/html5
```
""",
        encoding="utf-8",
    )
    return map_path


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


def _write_sample_dataset(work_dir: Path, title: str, output_format: str = "pdf") -> Path:
    registry_result = build_publishing_corpus(work_dir, title, output_format=output_format)
    if registry_result:
        return Path(registry_result["map_path"])

    if _looks_like_copy_to_chunk_lang_request(title):
        return _write_copy_to_chunk_lang_dataset(work_dir, title)
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


def _build_generation_summary(
    *,
    prompt: str,
    input_map: Path,
    work_dir: Path,
    formats: list[str],
) -> dict[str, Any]:
    source_files = sorted(
        path.relative_to(work_dir).as_posix()
        for path in work_dir.rglob("*")
        if path.is_file()
    )
    registry_summary_path = work_dir / SUMMARY_FILENAME
    if registry_summary_path.exists():
        try:
            registry_summary = json.loads(registry_summary_path.read_text(encoding="utf-8"))
            if isinstance(registry_summary, dict):
                registry_summary["source_files"] = source_files
                registry_summary["formats_requested"] = formats
                registry_summary["input_map"] = str(input_map)
                return registry_summary
        except Exception:
            pass

    if _looks_like_copy_to_chunk_lang_request(prompt):
        return {
            "title": "copy-to + chunk + xml:lang DITA-OT publishing dataset",
            "what_was_generated": [
                "One DITA map with root `xml:lang=\"en-US\"`.",
                "A reusable source topic referenced twice with unique `copy-to` targets.",
                "A French topic referenced with `copy-to`, `xml:lang=\"fr-FR\"`, and `chunk=\"by-topic\"`.",
                "An oracle topic describing PDF and HTML5 checks.",
                "PDF, classic XHTML, and/or HTML5 outputs depending on the selected transformation.",
            ],
            "source_files": source_files,
            "expected_behavior": [
                "`copy-to` changes the effective publishing URI/output target; it does not rename the physical source file.",
                "The same source topic can publish as two distinct outputs when each topicref has a unique `copy-to` value.",
                "`chunk=\"by-topic\"` should create distinct HTML5 output pages for copied topicrefs.",
                "`xml:lang` should remain a language/locale signal and should not be changed by `copy-to`.",
            ],
            "qa_checklist": [
                "Confirm DITA-OT exits with code 0 for every requested format.",
                "Open the ZIP and verify the map, reusable source topic, French topic, and oracle topic are present.",
                "Inspect the map for unique `copy-to` targets: `reused-copy-a.dita`, `reused-copy-b.dita`, and `fr-copy-target.dita`.",
                "Verify the authored source remains `topics/reused-source.dita` and is not physically renamed by generation.",
                "Compare PDF and HTML5 outputs to ensure copied topicrefs remain distinct and language context is preserved.",
            ],
            "expected_pdf_review_areas": [
                "PDF title/TOC should include both copy-to instances: `Reuse instance A via copy-to` and `Reuse instance B via copy-to`.",
                "PDF should include the reusable source topic content for both effective references.",
                "PDF should include the French topic content without treating `copy-to` as a language override.",
                "PDF should not report duplicate effective URI collisions for the unique copy-to targets.",
                "PDF file should be non-empty and readable from the Download PDF link.",
            ],
            "expected_html_review_areas": [
                "HTML5 output should include distinct pages for copy-to targets, especially `reused-copy-a.html` and `reused-copy-b.html`.",
                "Both copied HTML5 pages should contain the reusable source topic content.",
                "French HTML5 output should preserve French text and language context.",
                "Generated navigation should point to copy-to target filenames rather than only the original source filename.",
            ],
            "recommended_user_next_step": "Download the ZIP, inspect the map copy-to targets, then open HTML5 pages and PDF TOC/navigation to verify distinct copied instances.",
            "formats_requested": formats,
            "input_map": str(input_map),
        }
    if _looks_like_xml_lang_chunk_request(prompt):
        return {
            "title": "xml:lang + chunk DITA-OT publishing dataset",
            "what_was_generated": [
                "One DITA map with root `xml:lang=\"en-US\"`.",
                "Four concept topics covering language inheritance, topic-level override, topicref-level override, and branch chunking.",
                "A selected publishing branch using `chunk=\"select-branch to-content\"`.",
                "PDF2, classic XHTML, and/or HTML5 outputs depending on the selected transformation.",
            ],
            "source_files": source_files,
            "expected_behavior": [
                "Topics without their own `xml:lang` inherit the root map language context.",
                "A topic with `xml:lang=\"fr-FR\"` keeps French language context despite the English root map.",
                "A topicref-level `xml:lang=\"fr-FR\"` override remains meaningful when the referenced topic is chunked into output.",
                "Only valid DITA chunk tokens are used: `by-topic`, `to-content`, and `select-branch`.",
            ],
            "qa_checklist": [
                "Confirm DITA-OT exits with code 0 for every requested format.",
                "Open the ZIP and verify the source map plus all four topic files are present.",
                "Inspect the map for `xml:lang=\"en-US\"`, `xml:lang=\"fr-FR\"`, `chunk=\"by-topic\"`, `chunk=\"to-content\"`, and `chunk=\"select-branch to-content\"`.",
                "Verify no invalid chunk values such as `split` or `to-navigation` appear in the generated source.",
                "Compare PDF and HTML5 navigation/content to ensure selected branch topics are not dropped.",
            ],
            "expected_pdf_review_areas": [
                "PDF title/TOC should include `How xml:lang and chunk are tested together`.",
                "PDF should include `PDF2 publishing oracle` and selected branch content.",
                "PDF should include the French HTML5-oracle topic content when the branch is selected.",
                "PDF should not show processor errors or warnings caused by invalid chunk values.",
                "PDF file should be non-empty and readable from the Download PDF link.",
            ],
            "expected_html_review_areas": [
                "HTML5 output should contain separate generated pages for chunked topics.",
                "Generated links should navigate between the overview, branch, PDF oracle, HTML5 oracle, and mixed-language topics.",
                "French content should remain present in the HTML5 page for the `fr-FR` topic.",
            ],
            "recommended_user_next_step": "Download the ZIP first to inspect the source corpus, then open the PDF and HTML5 files to verify navigation, language overrides, and branch inclusion.",
            "formats_requested": formats,
            "input_map": str(input_map),
        }

    return {
        "title": "DITA-OT publishing smoke dataset",
        "what_was_generated": [
            "One DITA map and one topic generated from the prompt.",
            "Requested DITA-OT transformation outputs were produced from that map.",
        ],
        "source_files": source_files,
        "expected_behavior": [
            "DITA-OT should publish the generated map without fatal errors.",
            "Requested output files should be non-empty and downloadable.",
        ],
        "qa_checklist": [
            "Confirm DITA-OT exits with code 0 for every requested format.",
            "Open the source map and topic from the ZIP.",
            "Open the generated output and verify the topic title/body appear.",
        ],
        "expected_pdf_review_areas": [
            "PDF should open successfully from the Download PDF link.",
            "PDF should contain the generated topic title and expected-oracle section.",
            "PDF should be non-empty and readable.",
        ],
        "expected_html_review_areas": [
            "HTML output should open successfully.",
            "Generated page should contain the topic title and body.",
        ],
        "recommended_user_next_step": "Download the ZIP to inspect source plus generated outputs.",
        "formats_requested": formats,
        "input_map": str(input_map),
    }


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
    combined_output = f"{proc.stdout}\n{proc.stderr}"
    has_build_failure = "BUILD FAILED" in combined_output or "[ERROR]" in combined_output
    return {
        "ok": proc.returncode == 0 and not has_build_failure,
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
        input_for_build = _write_sample_dataset(work_dir, prompt or slug, output_format=requested)

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
    generation_summary = _build_generation_summary(
        prompt=prompt,
        input_map=input_for_build,
        work_dir=work_dir,
        formats=formats,
    )
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
                    "generation_summary": generation_summary,
                },
                indent=2,
            ),
        )

    ok = all(bool(item.get("ok")) for item in publish.values()) if publish else False
    return {
        "status": "success" if ok else "error",
        "summary": "DITA-OT publish completed." if ok else "DITA-OT publish failed; inspect stderr.",
        "generation_summary": generation_summary,
        "detected_constructs": generation_summary.get("detected_constructs", []),
        "source_files": generation_summary.get("source_files", []),
        "what_was_generated": generation_summary["what_was_generated"],
        "expected_behavior": generation_summary["expected_behavior"],
        "qa_checklist": generation_summary["qa_checklist"],
        "expected_pdf_review_areas": generation_summary["expected_pdf_review_areas"],
        "expected_html_review_areas": generation_summary["expected_html_review_areas"],
        "negative_or_risk_cases": generation_summary.get("negative_or_risk_cases", []),
        "validation_oracles": generation_summary.get("validation_oracles", []),
        "recommended_user_next_step": generation_summary["recommended_user_next_step"],
        "confidence_contract": generation_summary.get("confidence_contract", []),
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
