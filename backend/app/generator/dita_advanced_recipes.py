"""
DITA advanced markup recipes: nested topics, ph/keyword/related-links, SVG/MathML in foreign,
referenced SVG images, and a minimal bookmap shell aligned with project DTD stubs.
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import make_dita_id, stable_id
from app.generator.generate import safe_join, sanitize_filename, _map_xml, _rel_href
from app.jobs.schemas import DatasetConfig
from app.utils.xml_escape import xml_escape_text, xml_escape_attr, xml_escape_href

MATHML_NS = "http://www.w3.org/1998/Math/MathML"
SVG_NS = "http://www.w3.org/2000/svg"


def _topic_to_bytes(config: DatasetConfig, topic_elem: ET.Element, pretty_print: bool = True) -> bytes:
    ET.indent(topic_elem, space="  ")
    xml_body = ET.tostring(topic_elem, encoding="utf-8", xml_declaration=False)
    if pretty_print:
        try:
            from xml.dom import minidom

            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    return doc.encode("utf-8") + xml_body


def _bookmap_to_bytes(config: DatasetConfig, bookmap_elem: ET.Element, pretty_print: bool = True) -> bytes:
    ET.indent(bookmap_elem, space="  ")
    xml_body = ET.tostring(bookmap_elem, encoding="utf-8", xml_declaration=False)
    if pretty_print:
        try:
            from xml.dom import minidom

            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass
    doctype = getattr(config, "doctype_bookmap", None) or (
        '<!DOCTYPE bookmap PUBLIC "-//OASIS//DTD DITA BookMap//EN" "technicalContent/dtd/bookmap.dtd">'
    )
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{doctype}\n'
    return doc.encode("utf-8") + xml_body


def _simple_topic(topic_id: str, title: str, shortdesc: str, body_p_text: str) -> ET.Element:
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = xml_escape_text(title)
    ET.SubElement(topic, "shortdesc").text = xml_escape_text(shortdesc)
    body = ET.SubElement(topic, "body")
    ET.SubElement(body, "p").text = xml_escape_text(body_p_text)
    return topic


def generate_nested_topic_inline(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
    **kwargs,
) -> Dict[str, bytes]:
    """Topic with nested b/i/u plus a nested child topic (RTE + structure repro)."""
    used_ids: set[str] = set()
    topic_id = make_dita_id("nested_inline", id_prefix, used_ids)
    filename = "nested_topic_inline.dita"
    topic_rel = f"topics/{filename}"
    topic_path = safe_join(base_path, topic_rel)

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = xml_escape_text("Inline Formatting Nested Tags")
    shortdesc = ET.SubElement(topic, "shortdesc")
    shortdesc.text = xml_escape_text(
        "Topic with nested bold, italic, and underline for RTE cursor navigation reproduction."
    )
    body = ET.SubElement(topic, "body")

    p = ET.SubElement(body, "p")
    p.text = "Place cursor before the tag and use arrow keys: "
    b = ET.SubElement(p, "b")
    b.text = "bold "
    i = ET.SubElement(b, "i")
    i.text = "italic "
    u = ET.SubElement(i, "u")
    u.text = "underline"
    u.tail = ""
    i.tail = ""
    b.tail = " and navigate back."

    p2 = ET.SubElement(body, "p")
    p2.text = "Alternate nesting: "
    u2 = ET.SubElement(p2, "u")
    u2.text = "underline "
    i2 = ET.SubElement(u2, "i")
    i2.text = "italic "
    b2 = ET.SubElement(i2, "b")
    b2.text = "bold"
    b2.tail = ""
    i2.tail = ""
    u2.tail = " text."

    child = ET.SubElement(topic, "topic", {"id": "topic_1"})
    ET.SubElement(child, "title").text = ""

    map_id = stable_id(config.seed, "nested_topic_inline_map", "", used_ids)
    win_safe = getattr(config, "windows_safe_filenames", True)
    map_filename = sanitize_filename("nested_topic_inline.ditamap", win_safe)
    map_path = safe_join(base_path, map_filename)
    href = _rel_href(map_path, topic_path)
    map_xml = _map_xml(config, map_id, "Nested topic inline map", [href], [], [])

    return {
        topic_path: _topic_to_bytes(config, topic, pretty_print),
        map_path: map_xml,
    }


def generate_topic_ph_keyword_related_links(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
    **kwargs,
) -> Dict[str, bytes]:
    used_ids: set[str] = set()
    peer_id = make_dita_id("ph_kw_peer", id_prefix, used_ids)
    peer_rel = "topics/ph_kw_related_peer.dita"
    peer_path = safe_join(base_path, peer_rel)

    main_id = make_dita_id("ph_kw_main", id_prefix, used_ids)
    main_rel = "topics/ph_keyword_related.dita"
    main_path = safe_join(base_path, main_rel)

    peer_topic = _simple_topic(
        peer_id,
        "Related concepts peer",
        "Peer topic for related-links href tests.",
        "Body text for the peer topic.",
    )

    topic = ET.Element("topic", {"id": main_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = xml_escape_text("ph, keyword, and related-links")
    ET.SubElement(topic, "shortdesc").text = xml_escape_text(
        "Prolog keywords, inline ph and keyword, and related-links with link@href."
    )
    prolog = ET.SubElement(topic, "prolog")
    md = ET.SubElement(prolog, "metadata")
    kws = ET.SubElement(md, "keywords")
    for kw in ("DITA", "related-links", "keyword"):
        ET.SubElement(kws, "keyword").text = xml_escape_text(kw)

    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "This line uses "
    ph = ET.SubElement(p, "ph")
    ph.text = xml_escape_text("a highlighted phrase")
    ph.tail = " and a controlled term: "
    kw = ET.SubElement(p, "keyword")
    kw.text = xml_escape_text("controlled-term")
    kw.tail = "."

    rel = ET.SubElement(topic, "related-links")
    peer_href = _rel_href(main_path, peer_path)
    lk = ET.SubElement(rel, "link")
    lk.set("href", xml_escape_href(peer_href))
    lk.set("type", xml_escape_attr("topic"))
    lk.set("format", xml_escape_attr("dita"))
    lk.set("scope", xml_escape_attr("local"))

    map_id = stable_id(config.seed, "ph_kw_map", "", used_ids)
    win_safe = getattr(config, "windows_safe_filenames", True)
    map_filename = sanitize_filename("ph_keyword_related.ditamap", win_safe)
    map_path = safe_join(base_path, map_filename)
    map_xml = _map_xml(
        config,
        map_id,
        "ph / keyword / related-links map",
        [_rel_href(map_path, main_path), _rel_href(map_path, peer_path)],
        [],
        [],
    )

    return {
        peer_path: _topic_to_bytes(config, peer_topic, pretty_print),
        main_path: _topic_to_bytes(config, topic, pretty_print),
        map_path: map_xml,
    }


def generate_topic_svg_mathml_foreign(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
    **kwargs,
) -> Dict[str, bytes]:
    used_ids: set[str] = set()
    svg_rel = "images/sample_diagram.svg"
    svg_path = safe_join(base_path, svg_rel)

    svg_bytes = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80" viewBox="0 0 120 80">
  <rect x="10" y="10" width="100" height="60" fill="#4a90d9" stroke="#333" stroke-width="2"/>
  <text x="60" y="48" text-anchor="middle" fill="#ffffff" font-size="14" font-family="sans-serif">SVG</text>
</svg>
"""

    peer_id = make_dita_id("svg_math_peer", id_prefix, used_ids)
    peer_rel = "topics/svg_math_peer.dita"
    peer_path = safe_join(base_path, peer_rel)
    peer_topic = _simple_topic(
        peer_id,
        "SVG and MathML peer",
        "Peer for related-links from the media topic.",
        "Supporting content for foreign and image references.",
    )

    main_id = make_dita_id("svg_math_main", id_prefix, used_ids)
    main_rel = "topics/svg_mathml_foreign.dita"
    main_path = safe_join(base_path, main_rel)

    topic = ET.Element("topic", {"id": main_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = xml_escape_text("SVG image, inline SVG, and MathML in foreign")
    ET.SubElement(topic, "shortdesc").text = xml_escape_text(
        "Referenced SVG via image, SVG and MathML embedded under foreign for editor validation."
    )
    prolog = ET.SubElement(topic, "prolog")
    md = ET.SubElement(prolog, "metadata")
    kws = ET.SubElement(md, "keywords")
    for kw in ("svg", "mathml", "foreign"):
        ET.SubElement(kws, "keyword").text = xml_escape_text(kw)

    body = ET.SubElement(topic, "body")

    p_img = ET.SubElement(body, "p")
    p_img.text = "Referenced diagram (separate .svg file): "
    img_href = _rel_href(main_path, svg_path)
    img = ET.SubElement(p_img, "image")
    img.set("href", xml_escape_href(img_href))
    img.set("format", xml_escape_attr("svg"))
    img.set("placement", xml_escape_attr("inline"))

    ET.SubElement(body, "p").text = "Inline SVG inside foreign:"
    foreign_svg = ET.SubElement(body, "foreign")
    svg = ET.SubElement(foreign_svg, "{%s}svg" % SVG_NS)
    svg.set("width", "100")
    svg.set("height", "40")
    svg.set("viewBox", "0 0 100 40")
    rect = ET.SubElement(svg, "{%s}rect" % SVG_NS)
    rect.set("x", "5")
    rect.set("y", "5")
    rect.set("width", "90")
    rect.set("height", "30")
    rect.set("fill", "#6abf69")

    ET.SubElement(body, "p").text = "MathML inside foreign (inline equation):"
    foreign_math = ET.SubElement(body, "foreign")
    math = ET.SubElement(foreign_math, "{%s}math" % MATHML_NS)
    math.set("display", "inline")
    mrow = ET.SubElement(math, "{%s}mrow" % MATHML_NS)
    mi1 = ET.SubElement(mrow, "{%s}mi" % MATHML_NS)
    mi1.text = "x"
    mo = ET.SubElement(mrow, "{%s}mo" % MATHML_NS)
    mo.text = "+"
    mi2 = ET.SubElement(mrow, "{%s}mi" % MATHML_NS)
    mi2.text = "y"

    rel = ET.SubElement(topic, "related-links")
    peer_href = _rel_href(main_path, peer_path)
    lk = ET.SubElement(rel, "link")
    lk.set("href", xml_escape_href(peer_href))
    lk.set("type", xml_escape_attr("topic"))
    lk.set("format", xml_escape_attr("dita"))
    lk.set("scope", xml_escape_attr("local"))

    map_id = stable_id(config.seed, "svg_math_map", "", used_ids)
    win_safe = getattr(config, "windows_safe_filenames", True)
    map_filename = sanitize_filename("svg_mathml_foreign.ditamap", win_safe)
    map_path = safe_join(base_path, map_filename)
    map_xml = _map_xml(
        config,
        map_id,
        "SVG and MathML topic map",
        [_rel_href(map_path, main_path), _rel_href(map_path, peer_path)],
        [],
        [],
    )

    return {
        svg_path: svg_bytes,
        peer_path: _topic_to_bytes(config, peer_topic, pretty_print),
        main_path: _topic_to_bytes(config, topic, pretty_print),
        map_path: map_xml,
    }


def generate_bookmap_elements_reference(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "t",
    pretty_print: bool = True,
    **kwargs,
) -> Dict[str, bytes]:
    """
    Minimal bookmap using stub-aligned bookmeta, frontmatter, chapter, backmatter.
    """
    used_ids: set[str] = set()
    win_safe = getattr(config, "windows_safe_filenames", True)
    book_dir = safe_join(base_path, "book")

    def tp(rel: str) -> str:
        return safe_join(base_path, rel)

    paths = {
        "chapter": tp("book/topics/bookmap_ref_chapter.dita"),
        "notices": tp("book/frontmatter/notices.dita"),
        "preface": tp("book/frontmatter/preface.dita"),
        "appendix": tp("book/backmatter/appendix.dita"),
        "index": tp("book/backmatter/index.dita"),
    }

    chapter_id = make_dita_id("book_ch", id_prefix, used_ids)
    notices_id = make_dita_id("book_notices", id_prefix, used_ids)
    preface_id = make_dita_id("book_pref", id_prefix, used_ids)
    appendix_id = make_dita_id("book_appx", id_prefix, used_ids)
    index_id = make_dita_id("book_idx", id_prefix, used_ids)

    files: Dict[str, bytes] = {
        paths["chapter"]: _topic_to_bytes(
            config,
            _simple_topic(
                chapter_id,
                "Chapter body topic",
                "Primary chapter topic for bookmap shell reference.",
                "Content for the chapter topicref in bookmap_elements_reference.",
            ),
            pretty_print,
        ),
        paths["notices"]: _topic_to_bytes(
            config,
            _simple_topic(
                notices_id,
                "Notices",
                "Frontmatter notices placeholder.",
                "Legal notices and frontmatter stub content.",
            ),
            pretty_print,
        ),
        paths["preface"]: _topic_to_bytes(
            config,
            _simple_topic(
                preface_id,
                "Preface",
                "Frontmatter preface placeholder.",
                "Preface content for bookmap shell reference.",
            ),
            pretty_print,
        ),
        paths["appendix"]: _topic_to_bytes(
            config,
            _simple_topic(
                appendix_id,
                "Appendix",
                "Backmatter appendix placeholder.",
                "Appendix topics for bookmap shell reference.",
            ),
            pretty_print,
        ),
        paths["index"]: _topic_to_bytes(
            config,
            _simple_topic(
                index_id,
                "Index",
                "Backmatter index placeholder.",
                "Index list topicref target.",
            ),
            pretty_print,
        ),
    }

    bookmap_filename = sanitize_filename("bookmap_elements_reference.ditamap", win_safe)
    map_path = safe_join(book_dir, bookmap_filename)
    bookmap_id = make_dita_id("bookmapref", id_prefix, used_ids)

    bookmap = ET.Element("bookmap", {"id": bookmap_id, "xml:lang": "en"})
    ET.SubElement(bookmap, "title").text = xml_escape_text("Bookmap elements reference")

    bookmeta = ET.SubElement(bookmap, "bookmeta")
    booktitle = ET.SubElement(bookmeta, "booktitle")
    ET.SubElement(booktitle, "mainbooktitle").text = xml_escape_text("Bookmap elements reference")
    bookabstract = ET.SubElement(bookmeta, "bookabstract")
    ET.SubElement(bookabstract, "p").text = xml_escape_text(
        "Minimal bookmap with frontmatter, chapter, and backmatter for DTD-stub validation."
    )

    frontmatter = ET.SubElement(bookmap, "frontmatter")
    notices = ET.SubElement(frontmatter, "notices")
    nref = ET.SubElement(notices, "topicref")
    nref.set("href", xml_escape_href(_rel_href(map_path, paths["notices"])))
    nref.set("type", xml_escape_attr("topic"))
    preface = ET.SubElement(frontmatter, "preface")
    prefref = ET.SubElement(preface, "topicref")
    prefref.set("href", xml_escape_href(_rel_href(map_path, paths["preface"])))
    prefref.set("type", xml_escape_attr("topic"))

    chapter = ET.SubElement(bookmap, "chapter")
    cref = ET.SubElement(chapter, "topicref")
    cref.set("href", xml_escape_href(_rel_href(map_path, paths["chapter"])))
    cref.set("type", xml_escape_attr("topic"))
    cref.set("navtitle", xml_escape_attr("Main chapter"))

    backmatter = ET.SubElement(bookmap, "backmatter")
    appendix = ET.SubElement(backmatter, "appendix")
    aref = ET.SubElement(appendix, "topicref")
    aref.set("href", xml_escape_href(_rel_href(map_path, paths["appendix"])))
    aref.set("type", xml_escape_attr("topic"))
    indexlist = ET.SubElement(backmatter, "indexlist")
    iref = ET.SubElement(indexlist, "topicref")
    iref.set("href", xml_escape_href(_rel_href(map_path, paths["index"])))
    iref.set("type", xml_escape_attr("topic"))

    files[map_path] = _bookmap_to_bytes(config, bookmap, pretty_print)
    return files


RECIPE_SPECS = [
    {
        "id": "nested_topic_inline",
        "title": "Nested topic + inline b i u",
        "description": "Map + parent topic with nested bold/italic/underline and a nested child topic (empty title).",
        "tags": ["nested topic", "inline", "b", "i", "u", "RTE"],
        "module": "app.generator.dita_advanced_recipes",
        "function": "generate_nested_topic_inline",
        "params_schema": {},
        "default_params": {},
        "stability": "stable",
        "constructs": ["topic", "body", "b", "i", "u", "nested topic"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["nested topic", "child topic", "inline formatting"],
        "avoid_when": [],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "topic_ph_keyword_related_links",
        "title": "ph, keyword, related-links",
        "description": "Prolog keywords, inline ph and keyword, related-links with link, map + two topics.",
        "tags": ["ph", "keyword", "related-links", "prolog"],
        "module": "app.generator.dita_advanced_recipes",
        "function": "generate_topic_ph_keyword_related_links",
        "params_schema": {},
        "default_params": {},
        "stability": "stable",
        "constructs": ["topic", "prolog", "keywords", "ph", "related-links", "link"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["ph", "keyword", "related-links"],
        "avoid_when": [],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "topic_svg_mathml_foreign",
        "title": "SVG + MathML in foreign",
        "description": "image@href to .svg, inline SVG and MathML under foreign, peer topic and map.",
        "tags": ["svg", "mathml", "foreign", "image"],
        "module": "app.generator.dita_advanced_recipes",
        "function": "generate_topic_svg_mathml_foreign",
        "params_schema": {},
        "default_params": {},
        "stability": "stable",
        "constructs": ["topic", "image", "foreign", "svg", "math"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["svg", "mathml", "foreign"],
        "avoid_when": [],
        "positive_negative": "positive",
        "complexity": "low",
        "output_scale": "minimal",
    },
    {
        "id": "bookmap_elements_reference",
        "title": "Bookmap elements shell",
        "description": "Bookmap with bookmeta, frontmatter, chapter, backmatter; DITA BookMap doctype.",
        "tags": ["bookmap", "frontmatter", "backmatter", "chapter"],
        "module": "app.generator.dita_advanced_recipes",
        "function": "generate_bookmap_elements_reference",
        "params_schema": {},
        "default_params": {},
        "stability": "stable",
        "constructs": ["bookmap", "bookmeta", "chapter", "topicref"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": ["bookmap", "book structure"],
        "avoid_when": [],
        "positive_negative": "positive",
        "complexity": "low",
        "output_scale": "minimal",
    },
]
