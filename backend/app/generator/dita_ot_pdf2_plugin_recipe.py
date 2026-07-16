"""Generate a sample DITA-OT PDF2 plugin (layout/FO customization) alongside a small
bookmap + topics that would be published through it.

This models the real, officially documented DITA-OT PDF2 plugin customization
mechanism (the ``dita.xsl.pdf2`` extension point): a ``plugin.xml`` descriptor plus a
``cfg/fo/attrs/custom.xsl`` file overriding standard PDF2 attribute-sets (body font,
TOC styling). This is distinct from AEM Guides' Native PDF output preset -- it targets
DITA-OT's own PDF2 transform, installed as a plugin under DITA-OT's ``plugins/`` dir.
"""
from __future__ import annotations

from typing import Dict, Optional

from app.generator.dita_utils import stable_id
from app.generator.generate import safe_join, sanitize_filename
from app.utils.xml_escape import xml_escape_text, xml_escape_attr

_BOOKMAP_DOCTYPE = '<!DOCTYPE bookmap PUBLIC "-//OASIS//DTD DITA BookMap//EN" "technicalContent/dtd/bookmap.dtd">'
_TOPIC_DOCTYPE = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">'


def _plugin_xml(plugin_id: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<plugin id="{xml_escape_text(plugin_id)}">\n'
        '  <!-- dita.xsl.pdf2 is the standard DITA-OT PDF2 extension point for FO\n'
        '       attribute-set / template overrides. Install this folder under\n'
        '       DITA-OT install dir, "plugins" subfolder, then reload DITA-OT. -->\n'
        '  <feature extension="dita.xsl.pdf2" file="cfg/fo/attrs/custom.xsl"/>\n'
        "</plugin>\n"
    ).encode("utf-8")


def _custom_attrs_xsl(*, body_font: str, body_size: str, toc_font: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="2.0">\n\n'
        "  <!-- Overrides the base PDF2 body text attribute-set (font-family/size). -->\n"
        '  <xsl:attribute-set name="__body__">\n'
        f'    <xsl:attribute name="font-family">{xml_escape_text(body_font)}</xsl:attribute>\n'
        f'    <xsl:attribute name="font-size">{xml_escape_text(body_size)}</xsl:attribute>\n'
        "  </xsl:attribute-set>\n\n"
        "  <!-- Overrides the generated table-of-contents entry styling. -->\n"
        '  <xsl:attribute-set name="__toc__">\n'
        f'    <xsl:attribute name="font-family">{xml_escape_text(toc_font)}</xsl:attribute>\n'
        "  </xsl:attribute-set>\n\n"
        "</xsl:stylesheet>\n"
    ).encode("utf-8")


def _plugin_readme(plugin_id: str) -> bytes:
    return (
        f"# {plugin_id}\n\n"
        "Sample DITA-OT PDF2 plugin customizing PDF layout via the `dita.xsl.pdf2` "
        "extension point (body font/size, TOC entry styling).\n\n"
        "## Install\n\n"
        "1. Copy this folder to `<DITA-OT install dir>/plugins/" + plugin_id + "/`\n"
        "2. Run `dita --reload` (or `dita --install` if packaged as a zip) so DITA-OT "
        "picks up the new plugin.\n"
        "3. Publish with the standard PDF2 transtype -- the customization applies "
        "automatically, no extra `--args.*` flag needed:\n\n"
        "   ```\n"
        "   dita -i sample.ditamap -f pdf2 -o out/\n"
        "   ```\n\n"
        "## What this is NOT\n\n"
        "This is a **DITA-OT PDF2** plugin, separate from AEM Guides' **Native PDF** "
        "output preset -- Native PDF has its own preset-based styling/template "
        "mechanism (Output Presets > Native-PDF), not DITA-OT plugins. Do not assume "
        "layout parity between the two; validate each independently.\n"
    ).encode("utf-8")


def _sample_topic(topic_id: str, title: str, shortdesc: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"{_TOPIC_DOCTYPE}\n"
        f'<topic id="{xml_escape_text(topic_id)}" xml:lang="en">\n'
        f"  <title>{xml_escape_text(title)}</title>\n"
        f"  <shortdesc>{xml_escape_text(shortdesc)}</shortdesc>\n"
        "  <body>\n"
        f"    <p>Sample content for {xml_escape_text(title)}, published through the "
        "custom PDF2 plugin to exercise the overridden body font/size and TOC styling.</p>\n"
        "  </body>\n"
        "</topic>\n"
    ).encode("utf-8")


def _sample_bookmap(bookmap_id: str, title: str, topic_refs: list[tuple[str, str]]) -> bytes:
    topicref_lines = "\n".join(
        f'    <chapter href="{href}" navtitle="{xml_escape_attr(navtitle)}"/>'
        for href, navtitle in topic_refs
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"{_BOOKMAP_DOCTYPE}\n"
        f'<bookmap id="{xml_escape_text(bookmap_id)}" xml:lang="en">\n'
        f"  <booktitle><mainbooktitle>{xml_escape_text(title)}</mainbooktitle></booktitle>\n"
        "  <frontmatter>\n"
        "    <booklists>\n"
        "      <toc/>\n"
        "    </booklists>\n"
        "  </frontmatter>\n"
        f"{topicref_lines}\n"
        "  <backmatter>\n"
        "    <booklists>\n"
        "      <indexlist/>\n"
        "    </booklists>\n"
        "  </backmatter>\n"
        "</bookmap>\n"
    ).encode("utf-8")


def generate_dita_ot_pdf2_plugin_dataset(
    config,
    base: str,
    plugin_id: str = "com.example.pdf2.custom",
    topic_count: int = 3,
    body_font: str = "Helvetica",
    body_size: str = "10pt",
    toc_font: str = "Helvetica",
    rand=None,
) -> Dict[str, bytes]:
    """Generate a sample DITA-OT PDF2 plugin (plugin.xml + cfg/fo/attrs/custom.xsl)
    plus a bookmap + topics that would be published through it."""
    if rand is None:
        import random
        rand = random.Random(config.seed)

    files: Dict[str, bytes] = {}
    used_ids: set = set()

    plugin_dir = safe_join(base, "plugin")
    files[safe_join(plugin_dir, "plugin.xml")] = _plugin_xml(plugin_id)
    files[safe_join(plugin_dir, "cfg", "fo", "attrs", "custom.xsl")] = _custom_attrs_xsl(
        body_font=body_font, body_size=body_size, toc_font=toc_font
    )
    files[safe_join(plugin_dir, "README.md")] = _plugin_readme(plugin_id)

    topic_dir = safe_join(base, "topics")
    topic_refs: list[tuple[str, str]] = []
    for i in range(1, max(1, topic_count) + 1):
        topic_id = stable_id(config.seed, "pdf2plugin", str(i), used_ids)
        title = f"PDF2 Plugin Sample Topic {i}"
        filename = sanitize_filename(f"pdf2_plugin_topic_{i:02d}.dita", getattr(config, "windows_safe_filenames", False))
        path = safe_join(topic_dir, filename)
        files[path] = _sample_topic(topic_id, title, f"Sample topic {i} for PDF2 plugin layout testing.")
        topic_refs.append((f"topics/{filename}", title))

    bookmap_id = stable_id(config.seed, "pdf2plugin_map", "1", used_ids)
    files[safe_join(base, "pdf2_plugin_sample.ditamap")] = _sample_bookmap(
        bookmap_id, "PDF2 Plugin Layout Sample", topic_refs
    )

    return files


RECIPE_SPECS = [
    {
        "id": "dita_ot_pdf2_plugin_layout",
        "title": "DITA-OT PDF2 Plugin Layout",
        "description": (
            "Generate a sample DITA-OT PDF2 plugin (plugin.xml + cfg/fo/attrs/custom.xsl "
            "overriding body font/size and TOC styling via the dita.xsl.pdf2 extension "
            "point) plus a bookmap + topics to publish through it."
        ),
        "tags": ["dita-ot", "pdf2", "plugin", "layout", "publishing", "fo", "customization"],
        "module": "app.generator.dita_ot_pdf2_plugin_recipe",
        "function": "generate_dita_ot_pdf2_plugin_dataset",
        "params_schema": {
            "plugin_id": "str",
            "topic_count": "int",
            "body_font": "str",
            "body_size": "str",
            "toc_font": "str",
        },
        "default_params": {
            "plugin_id": "com.example.pdf2.custom",
            "topic_count": 3,
            "body_font": "Helvetica",
            "body_size": "10pt",
            "toc_font": "Helvetica",
        },
        "stability": "experimental",
        "constructs": ["bookmap", "plugin.xml", "fo/attrs", "toc", "indexlist"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": [
            "dita-ot pdf2 plugin",
            "custom pdf layout dita-ot",
            "fo attribute customization",
            "dita.xsl.pdf2",
        ],
        "avoid_when": ["native pdf output preset", "aem guides output preset only"],
        "positive_negative": "positive",
        "complexity": "low",
        "output_scale": "minimal",
        "mechanism_family": "pdf2_plugin",
        "topic_type": "mixed",
    },
]
