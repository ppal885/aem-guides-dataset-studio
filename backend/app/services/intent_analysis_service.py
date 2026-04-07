"""Extract IntentRecord from user/Jira text (LLM JSON + keyword boosts).

Keyword rules are loaded from ``topic_type_keywords.json`` so they can be
updated without touching code.  The JSON file is re-read on every call in
dev mode (``RELOAD_KEYWORDS=true``) and cached otherwise.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from app.core.schemas_dita_pipeline import DetectedDitaConstruct, DomainSignals, IntentRecord
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"
_KEYWORDS_PATH = PROMPTS_DIR / "topic_type_keywords.json"

# ── JSON keyword config loader (hot-reloadable) ──
_keyword_config_cache: dict[str, Any] | None = None
_keyword_config_mtime: float = 0.0


def _load_keyword_config() -> dict[str, Any]:
    """Load topic_type_keywords.json, with optional hot-reload in dev mode."""
    global _keyword_config_cache, _keyword_config_mtime

    if not _KEYWORDS_PATH.exists():
        return {}

    mtime = _KEYWORDS_PATH.stat().st_mtime
    reload = os.getenv("RELOAD_KEYWORDS", "true").lower() == "true"

    if _keyword_config_cache is not None and (not reload or mtime == _keyword_config_mtime):
        return _keyword_config_cache

    try:
        raw = _KEYWORDS_PATH.read_text(encoding="utf-8")
        _keyword_config_cache = json.loads(raw)
        _keyword_config_mtime = mtime
        return _keyword_config_cache  # type: ignore[return-value]
    except Exception as e:
        logger.warning_structured(
            "Failed to load topic_type_keywords.json, using hardcoded fallback",
            extra_fields={"error": str(e)},
        )
        return {}


def _match_any(text: str, patterns: list[str]) -> bool:
    """Return True if any regex pattern from the list matches text."""
    for p in patterns:
        try:
            if re.search(rf"\b(?:{p})\b", text, re.IGNORECASE):
                return True
        except re.error:
            continue
    return False


# Jira issue type → (dita_topic_type_guess, content_intent) mapping
_JIRA_TYPE_TO_DITA: dict[str, tuple[str, str]] = {
    "bug": ("task", "bug_repro"),
    "story": ("concept", "feature_request"),
    "task": ("task", "task_procedure"),
    "epic": ("map_only", "documentation"),
    "improvement": ("concept", "feature_request"),
    "sub-task": ("task", "task_procedure"),
    "new feature": ("concept", "feature_request"),
    "documentation": ("concept", "documentation"),
}


# ── DITA attribute/element detection patterns ──
_DITA_ATTRIBUTE_PATTERNS: dict[str, re.Pattern[str]] = {
    # ── Map/topicref attributes ──
    "format": re.compile(r'\b(?:format\s*(?:=|attribute)|@format|format\s*=\s*["\']?\w+)\b', re.I),
    "scope": re.compile(r'\b(?:scope\s*(?:=|attribute)|@scope|scope\s*=\s*["\']?(?:local|peer|external))\b', re.I),
    "chunk": re.compile(r'\b(?:chunk\s*(?:=|attribute)|@chunk|chunk\s*=\s*["\']?\w+)\b', re.I),
    "type": re.compile(r'\b(?:@type|type\s*=\s*["\']?(?:topic|concept|task|reference|fig|fn|section|table))\b', re.I),
    "collection-type": re.compile(r'\b(?:collection[\-.]type|@collection-type)\b', re.I),
    "processing-role": re.compile(r'\b(?:processing[\-.]role|@processing-role|resource[\-.]only)\b', re.I),
    "linking": re.compile(r'\b(?:linking\s*(?:=|attribute)|@linking|targetonly|sourceonly)\b', re.I),
    "locktitle": re.compile(r'\b(?:locktitle|@locktitle|lock[\-.]title)\b', re.I),
    "href": re.compile(r'\b(?:href\s*(?:=|attribute)|@href)\b', re.I),
    "navtitle": re.compile(r'\b(?:navtitle\s*(?:=|attribute)|@navtitle)\b', re.I),
    "toc": re.compile(r'\b(?:@toc|toc\s*=\s*["\']?(?:yes|no))\b', re.I),
    "print": re.compile(r'\b(?:@print|print\s*=\s*["\']?(?:yes|no|printonly))\b', re.I),
    "copy-to": re.compile(r'\b(?:copy[\-.]to|@copy-to)\b', re.I),
    "cascade": re.compile(r'\b(?:cascade\s*(?:=|attribute)|@cascade|cascade\s*=\s*["\']?(?:merge|nomerge))\b', re.I),
    "search": re.compile(r'\b(?:@search|search\s*=\s*["\']?(?:yes|no))\b', re.I),
    # ── Key-related attributes ──
    "conref": re.compile(r'\b(?:conref\s*(?:=|attribute)|@conref|conref\b)', re.I),
    "conkeyref": re.compile(r'\b(?:conkeyref\s*(?:=|attribute)|@conkeyref|conkeyref\b)', re.I),
    "conrefend": re.compile(r'\b(?:conrefend\s*(?:=|attribute)|@conrefend|conrefend\b)', re.I),
    "conaction": re.compile(r'\b(?:conaction\s*(?:=|attribute)|@conaction|conaction\s*=\s*["\']?(?:pushafter|pushbefore|pushreplace|mark))\b', re.I),
    "keyref": re.compile(r'\b(?:keyref\s*(?:=|attribute)|@keyref|keyref\b)', re.I),
    "keys": re.compile(r'\b(?:keys\s*(?:=|attribute)|@keys|\bkeys\b)', re.I),
    "keyscope": re.compile(r'\b(?:keyscope\s*(?:=|attribute)|@keyscope|keyscope\b)', re.I),
    # ── Conditional/filtering attributes ──
    "audience": re.compile(r'\b(?:audience\s*(?:=|attribute)|@audience)\b', re.I),
    "platform": re.compile(r'\b(?:platform\s*(?:=|attribute)|@platform)\b', re.I),
    "product": re.compile(r'\b(?:product\s*(?:=|attribute)|@product)\b', re.I),
    "otherprops": re.compile(r'\b(?:otherprops\s*(?:=|attribute)|@otherprops)\b', re.I),
    "props": re.compile(r'\b(?:props\s*(?:=|attribute)|@props)\b', re.I),
    "rev": re.compile(r'\b(?:rev\s*(?:=|attribute)|@rev)\b', re.I),
    "deliveryTarget": re.compile(r'\b(?:delivery[\-.]?target|@deliveryTarget)\b', re.I),
    # ── Localization attributes ──
    "translate": re.compile(r'\b(?:translate\s*(?:=|attribute)|@translate|translate\s*=\s*["\']?(?:yes|no))\b', re.I),
    "xml:lang": re.compile(r'\b(?:xml[:\-]lang|@xml:lang|language\s+attribute)\b', re.I),
    "dir": re.compile(r'\b(?:@dir|dir\s*=\s*["\']?(?:ltr|rtl|lro|rlo))\b', re.I),
    # ── ID/metadata attributes ──
    "id": re.compile(r'\b(?:@id|id\s+attribute|topic\s+id|element\s+id)\b', re.I),
    "outputclass": re.compile(r'\b(?:outputclass\s*(?:=|attribute)|@outputclass)\b', re.I),
    "class": re.compile(r'\b(?:@class\s+attribute|dita\s+class\s+attribute)\b', re.I),
    "domains": re.compile(r'\b(?:@domains|domains\s+attribute)\b', re.I),
    "specializations": re.compile(r'\b(?:@specializations|specializations\s+attribute)\b', re.I),
    # ── Status/importance attributes ──
    "status": re.compile(r'\b(?:status\s*(?:=|attribute)|@status|status\s*=\s*["\']?(?:new|changed|deleted|unchanged))\b', re.I),
    "importance": re.compile(r'\b(?:importance\s*(?:=|attribute)|@importance|importance\s*=\s*["\']?(?:obsolete|deprecated|optional|default|low|normal|high|recommended|required|urgent))\b', re.I),
    # ── Xref/link attributes ──
    "role": re.compile(r'\b(?:@role|role\s*=\s*["\']?(?:parent|child|sibling|friend|next|previous|cousin|ancestor|descendant|sample|external|other))\b', re.I),
    # ── Table attributes ──
    "colsep": re.compile(r'\b(?:colsep|@colsep)\b', re.I),
    "rowsep": re.compile(r'\b(?:rowsep|@rowsep)\b', re.I),
    "frame": re.compile(r'\b(?:frame\s*(?:=|attribute)|@frame|frame\s*=\s*["\']?(?:all|bottom|none|sides|top|topbot))\b', re.I),
    "scale": re.compile(r'\b(?:scale\s*(?:=|attribute)|@scale)\b', re.I),
    "expanse": re.compile(r'\b(?:expanse\s*(?:=|attribute)|@expanse|expanse\s*=\s*["\']?(?:column|page|spread|textline))\b', re.I),
    "relcolwidth": re.compile(r'\b(?:relcolwidth|@relcolwidth)\b', re.I),
    "align": re.compile(r'\b(?:@align|align\s*=\s*["\']?(?:left|right|center|justify|char))\b', re.I),
    "valign": re.compile(r'\b(?:@valign|valign\s*=\s*["\']?(?:top|middle|bottom))\b', re.I),
    "cols": re.compile(r'\b(?:@cols|cols\s*=\s*["\']?\d+)\b', re.I),
    "colname": re.compile(r'\b(?:colname|@colname)\b', re.I),
    "colnum": re.compile(r'\b(?:colnum|@colnum)\b', re.I),
    "colwidth": re.compile(r'\b(?:colwidth|@colwidth)\b', re.I),
    "namest": re.compile(r'\b(?:namest|@namest)\b', re.I),
    "nameend": re.compile(r'\b(?:nameend|@nameend)\b', re.I),
    "morerows": re.compile(r'\b(?:morerows|@morerows)\b', re.I),
    "spanname": re.compile(r'\b(?:spanname|@spanname)\b', re.I),
    # ── Image/media attributes ──
    "placement": re.compile(r'\b(?:placement\s*(?:=|attribute)|@placement|placement\s*=\s*["\']?(?:inline|break))\b', re.I),
    "height": re.compile(r'\b(?:@height|image\s+height)\b', re.I),
    "width": re.compile(r'\b(?:@width|image\s+width)\b', re.I),
    "scalefit": re.compile(r'\b(?:scalefit|@scalefit)\b', re.I),
    # ── Note attributes ──
    "note-type": re.compile(r'\b(?:note\s+type|type\s*=\s*["\']?(?:note|tip|important|remember|restriction|attention|caution|danger|warning|trouble|notice|other))\b', re.I),
    # ── Bookmap-specific attributes ──
    "anchorref": re.compile(r'\b(?:anchorref|@anchorref)\b', re.I),
    # ── DITA-OT / processing attributes ──
    "xtrf": re.compile(r'\b(?:xtrf|@xtrf)\b', re.I),
    "xtrc": re.compile(r'\b(?:xtrc|@xtrc)\b', re.I),
    # ── XML universal attributes ──
    "xml:space": re.compile(r'\b(?:xml[:\-]space|@xml:space|xml:space\s*=\s*["\']?preserve)\b', re.I),
    "xml:base": re.compile(r'\b(?:xml[:\-]base|@xml:base)\b', re.I),
    # ── CALS table advanced attributes ──
    "char": re.compile(r'\b(?:@char|char\s+alignment|align\s*=\s*["\']?char)\b', re.I),
    "charoff": re.compile(r'\b(?:charoff|@charoff)\b', re.I),
    "pgwide": re.compile(r'\b(?:pgwide|@pgwide|pgwide\s*=\s*["\']?[01])\b', re.I),
    "orient": re.compile(r'\b(?:orient\s*(?:=|attribute)|@orient|orient\s*=\s*["\']?(?:port|land))\b', re.I),
    "rowheader": re.compile(r'\b(?:rowheader|@rowheader|rowheader\s*=\s*["\']?(?:firstcol|norowheader|headers))\b', re.I),
    # ── Simpletable-specific attributes ──
    "keycol": re.compile(r'\b(?:keycol|@keycol|keycol\s*=\s*["\']?\d+)\b', re.I),
    "specentry": re.compile(r'\b(?:specentry|@specentry)\b', re.I),
    "spectitle": re.compile(r'\b(?:spectitle|@spectitle)\b', re.I),
    # ── List attributes ──
    "compact": re.compile(r'\b(?:compact\s*(?:=|attribute)|@compact|compact\s*=\s*["\']?(?:yes|no))\b', re.I),
    # ── Universal DITA base attribute ──
    "base": re.compile(r'\b(?:@base|base\s+attribute)\b', re.I),
    # ── DITA-OT build/processing arguments ──
    "dita-ot-args": re.compile(r'\b(?:args\.[\w.]+|transtype|dita[\-\.]command)\b', re.I),
}

_DITA_ELEMENT_PATTERNS: dict[str, re.Pattern[str]] = {
    # ── Map elements ──
    "map": re.compile(r'\b(?:<map\b|ditamap\b|dita\s+map)\b', re.I),
    "topicref": re.compile(r'\btopicref\b', re.I),
    "xref": re.compile(r'\b(?:xref|cross[\-\s]?ref)\b', re.I),
    "keydef": re.compile(r'\bkeydef\b', re.I),
    "reltable": re.compile(r'\b(?:reltable|relationship\s+table|relheader)\b', re.I),
    "mapref": re.compile(r'\bmapref\b', re.I),
    "topichead": re.compile(r'\btopichead\b', re.I),
    "topicgroup": re.compile(r'\btopicgroup\b', re.I),
    "topicset": re.compile(r'\btopicset\b', re.I),
    "topicsetref": re.compile(r'\btopicsetref\b', re.I),
    "navref": re.compile(r'\bnavref\b', re.I),
    "anchor": re.compile(r'\b(?:<anchor\b|anchor\s+element|anchorref)\b', re.I),
    "topicmeta": re.compile(r'\btopicmeta\b', re.I),
    # ── Bookmap elements ──
    "bookmap": re.compile(r'\bbookmap\b', re.I),
    "bookmeta": re.compile(r'\bbookmeta\b', re.I),
    "chapter": re.compile(r'\b(?:<chapter\b|bookmap\s+chapter)\b', re.I),
    "part": re.compile(r'\b(?:<part\b|bookmap\s+part)\b', re.I),
    "appendices": re.compile(r'\b(?:appendices|appendix)\b', re.I),
    "frontmatter": re.compile(r'\bfrontmatter\b', re.I),
    "backmatter": re.compile(r'\bbackmatter\b', re.I),
    "booktitle": re.compile(r'\bbooktitle\b', re.I),
    "bookabstract": re.compile(r'\bbookabstract\b', re.I),
    "booklists": re.compile(r'\bbooklists\b', re.I),
    "toc-element": re.compile(r'\b(?:<toc\b|toc\s+element)\b', re.I),
    "tablelist": re.compile(r'\btablelist\b', re.I),
    "figurelist": re.compile(r'\bfigurelist\b', re.I),
    "glossarylist": re.compile(r'\bglossarylist\b', re.I),
    "indexlist": re.compile(r'\bindexlist\b', re.I),
    # ── Topic structural elements ──
    "topic": re.compile(r'\b(?:<topic\b|generic\s+topic)\b', re.I),
    "title": re.compile(r'\b(?:<title\b|dita\s+title|topic\s+title)\b', re.I),
    "titlealts": re.compile(r'\btitlealts\b', re.I),
    "searchtitle": re.compile(r'\bsearchtitle\b', re.I),
    "shortdesc": re.compile(r'\b(?:shortdesc|short\s+description)\b', re.I),
    "abstract": re.compile(r'\b(?:<abstract\b|abstract\s+element)\b', re.I),
    "body": re.compile(r'\b(?:<body\b|topic\s+body)\b', re.I),
    "section": re.compile(r'\b(?:<section\b|dita\s+section)\b', re.I),
    "example": re.compile(r'\b(?:<example\b|example\s+element)\b', re.I),
    "prolog": re.compile(r'\b(?:prolog|topic\s+prolog)\b', re.I),
    "related-links": re.compile(r'\b(?:related[\-\s]links|relatedlinks)\b', re.I),
    "link": re.compile(r'\b(?:<link\b|dita\s+link\b)\b', re.I),
    "linklist": re.compile(r'\blinklist\b', re.I),
    "linkpool": re.compile(r'\blinkpool\b', re.I),
    "linktext": re.compile(r'\blinktext\b', re.I),
    "linkinfo": re.compile(r'\blinkinfo\b', re.I),
    # ── Task elements ──
    "task": re.compile(r'\b(?:<task\b|task\s+(?:topic|element))\b', re.I),
    "taskbody": re.compile(r'\btaskbody\b', re.I),
    "steps": re.compile(r'\b(?:<steps\b|task\s+steps)\b', re.I),
    "steps-unordered": re.compile(r'\bsteps[\-\s]unordered\b', re.I),
    "steps-informal": re.compile(r'\bsteps[\-\s]informal\b', re.I),
    "step": re.compile(r'\b(?:<step\b|task\s+step)\b', re.I),
    "cmd": re.compile(r'\b(?:<cmd\b|step\s+cmd|command\s+element)\b', re.I),
    "substeps": re.compile(r'\bsubsteps\b', re.I),
    "substep": re.compile(r'\bsubstep\b', re.I),
    "info": re.compile(r'\b(?:<info\b|step\s+info)\b', re.I),
    "stepresult": re.compile(r'\bstepresult\b', re.I),
    "steptroubleshooting": re.compile(r'\bsteptroubleshooting\b', re.I),
    "choices": re.compile(r'\b(?:<choices\b|step\s+choices)\b', re.I),
    "choice": re.compile(r'\b(?:<choice\b|choice\s+element)\b', re.I),
    "choicetable": re.compile(r'\bchoicetable\b', re.I),
    "chhead": re.compile(r'\bchhead\b', re.I),
    "chrow": re.compile(r'\bchrow\b', re.I),
    "choption": re.compile(r'\bchoption\b', re.I),
    "chdesc": re.compile(r'\bchdesc\b', re.I),
    "prereq": re.compile(r'\b(?:prereq|prerequisite)\b', re.I),
    "context": re.compile(r'\b(?:<context\b|task\s+context)\b', re.I),
    "result": re.compile(r'\b(?:<result\b|task\s+result)\b', re.I),
    "postreq": re.compile(r'\b(?:postreq|post[\-\s]?requisite)\b', re.I),
    "tasktroubleshooting": re.compile(r'\btasktroubleshooting\b', re.I),
    # ── Concept elements ──
    "concept": re.compile(r'\b(?:<concept\b|concept\s+(?:topic|element))\b', re.I),
    "conbody": re.compile(r'\bconbody\b', re.I),
    # ── Reference elements ──
    "reference": re.compile(r'\b(?:<reference\b|reference\s+(?:topic|element))\b', re.I),
    "refbody": re.compile(r'\brefbody\b', re.I),
    "properties": re.compile(r'\b(?:<properties\b|properties\s+(?:table|element)|prophead|property\b)\b', re.I),
    "proptype": re.compile(r'\bproptype\b', re.I),
    "propvalue": re.compile(r'\bpropvalue\b', re.I),
    "propdesc": re.compile(r'\bpropdesc\b', re.I),
    "refsyn": re.compile(r'\brefsyn\b', re.I),
    # ── Glossary elements ──
    "glossentry": re.compile(r'\bglossentry\b', re.I),
    "glossterm": re.compile(r'\bglossterm\b', re.I),
    "glossdef": re.compile(r'\bglossdef\b', re.I),
    "glossBody": re.compile(r'\bglossbody\b', re.I),
    "glossSurfaceForm": re.compile(r'\bgloss[\-\s]?surface[\-\s]?form\b', re.I),
    "glossUsage": re.compile(r'\bgloss[\-\s]?usage\b', re.I),
    "glossAlt": re.compile(r'\bgloss[\-\s]?alt\b', re.I),
    "glossScopeNote": re.compile(r'\bgloss[\-\s]?scope[\-\s]?note\b', re.I),
    "glossAbbreviation": re.compile(r'\bgloss[\-\s]?abbreviation\b', re.I),
    "glossAcronym": re.compile(r'\bgloss[\-\s]?acronym\b', re.I),
    # ── Table elements ──
    "table": re.compile(r'\b(?:<table\b|dita\s+table|cals\s+table)\b', re.I),
    "tgroup": re.compile(r'\btgroup\b', re.I),
    "thead": re.compile(r'\b(?:<thead\b|table\s+head(?:er)?)\b', re.I),
    "tbody": re.compile(r'\b(?:<tbody\b|table\s+body)\b', re.I),
    "row": re.compile(r'\b(?:<row\b|table\s+row)\b', re.I),
    "entry": re.compile(r'\b(?:<entry\b|table\s+(?:entry|cell))\b', re.I),
    "colspec": re.compile(r'\bcolspec\b', re.I),
    "spanspec": re.compile(r'\bspanspec\b', re.I),
    "simpletable": re.compile(r'\bsimpletable\b', re.I),
    "sthead": re.compile(r'\bsthead\b', re.I),
    "strow": re.compile(r'\bstrow\b', re.I),
    "stentry": re.compile(r'\bstentry\b', re.I),
    # ── List elements ──
    "ol": re.compile(r'\b(?:<ol\b|ordered\s+list)\b', re.I),
    "ul": re.compile(r'\b(?:<ul\b|unordered\s+list|bulleted?\s+list)\b', re.I),
    "li": re.compile(r'\b(?:<li\b|list\s+item)\b', re.I),
    "sl": re.compile(r'\b(?:<sl\b|simple\s+list)\b', re.I),
    "sli": re.compile(r'\bsli\b', re.I),
    "dl": re.compile(r'\b(?:<dl\b|definition\s+list)\b', re.I),
    "dlhead": re.compile(r'\bdlhead\b', re.I),
    "dlentry": re.compile(r'\bdlentry\b', re.I),
    "dt": re.compile(r'\b(?:<dt\b|definition\s+term)\b', re.I),
    "dd": re.compile(r'\b(?:<dd\b|definition\s+description)\b', re.I),
    # ── Block elements ──
    "p": re.compile(r'\b(?:<p\b|paragraph\s+element)\b', re.I),
    "note": re.compile(r'\b(?:<note\b|dita\s+note|note\s+element)\b', re.I),
    "lq": re.compile(r'\b(?:<lq\b|long\s+quote)\b', re.I),
    "fig": re.compile(r'\b(?:<fig\b|figure\s+element)\b', re.I),
    "codeblock": re.compile(r'\bcodeblock\b', re.I),
    "screen": re.compile(r'\b(?:<screen\b|screen\s+element)\b', re.I),
    "lines": re.compile(r'\b(?:<lines\b|lines\s+element)\b', re.I),
    "pre": re.compile(r'\b(?:<pre\b|preformatted)\b', re.I),
    "msgblock": re.compile(r'\bmsgblock\b', re.I),
    "draft-comment": re.compile(r'\bdraft[\-\s]comment\b', re.I),
    "required-cleanup": re.compile(r'\brequired[\-\s]cleanup\b', re.I),
    "fn": re.compile(r'\b(?:<fn\b|footnote)\b', re.I),
    # ── Inline elements ──
    "ph": re.compile(r'\b(?:<ph\b|phrase\s+element)\b', re.I),
    "b": re.compile(r'\b(?:<b\b|bold\s+element)\b', re.I),
    "i": re.compile(r'\b(?:<i\b|italic\s+element)\b', re.I),
    "u": re.compile(r'\b(?:<u\b|underline\s+element)\b', re.I),
    "sub": re.compile(r'\b(?:<sub\b|subscript)\b', re.I),
    "sup": re.compile(r'\b(?:<sup\b|superscript)\b', re.I),
    "codeph": re.compile(r'\bcodeph\b', re.I),
    "filepath": re.compile(r'\bfilepath\b', re.I),
    "varname": re.compile(r'\bvarname\b', re.I),
    "cmdname": re.compile(r'\bcmdname\b', re.I),
    "option": re.compile(r'\b(?:<option\b|option\s+element)\b', re.I),
    "parmname": re.compile(r'\bparmname\b', re.I),
    "synph": re.compile(r'\bsynph\b', re.I),
    "apiname": re.compile(r'\bapiname\b', re.I),
    "msgph": re.compile(r'\bmsgph\b', re.I),
    "systemoutput": re.compile(r'\bsystemoutput\b', re.I),
    "userinput": re.compile(r'\buserinput\b', re.I),
    # ── UI domain elements ──
    "menucascade": re.compile(r'\b(?:menucascade|menu\s+cascade)\b', re.I),
    "uicontrol": re.compile(r'\buicontrol\b', re.I),
    "wintitle": re.compile(r'\bwintitle\b', re.I),
    "shortcut": re.compile(r'\b(?:<shortcut\b|shortcut\s+element)\b', re.I),
    "screen-element": re.compile(r'\b(?:screen\s+capture|screenshot\s+element)\b', re.I),
    # ── Media elements ──
    "image": re.compile(r'\b(?:<image\b|image\s+element)\b', re.I),
    "alt": re.compile(r'\b(?:<alt\b|alt\s+text|alternate\s+text)\b', re.I),
    "audio": re.compile(r'\b(?:<audio\b|audio\s+element)\b', re.I),
    "video": re.compile(r'\b(?:<video\b|video\s+element)\b', re.I),
    "media-source": re.compile(r'\b(?:media[\-\s]source)\b', re.I),
    # ── Metadata elements ──
    "metadata": re.compile(r'\b(?:<metadata\b|dita\s+metadata|topic\s+metadata)\b', re.I),
    "othermeta": re.compile(r'\bothermeta\b', re.I),
    "audience-element": re.compile(r'\b(?:<audience\b|audience\s+element)\b', re.I),
    "category": re.compile(r'\b(?:<category\b|category\s+element)\b', re.I),
    "keywords-element": re.compile(r'\b(?:<keywords\b|keywords\s+element)\b', re.I),
    "prodinfo": re.compile(r'\bprodinfo\b', re.I),
    "prodname": re.compile(r'\bprodname\b', re.I),
    "brand": re.compile(r'\b(?:<brand\b|brand\s+element)\b', re.I),
    "permissions": re.compile(r'\b(?:<permissions\b|permissions\s+element)\b', re.I),
    "resourceid": re.compile(r'\bresourceid\b', re.I),
    # ── Data/foreign elements ──
    "data": re.compile(r'\b(?:<data\b|data\s+element)\b', re.I),
    "data-about": re.compile(r'\bdata[\-\s]about\b', re.I),
    "foreign": re.compile(r'\b(?:<foreign\b|foreign\s+element)\b', re.I),
    "unknown-element": re.compile(r'\b(?:<unknown\b|unknown\s+element)\b', re.I),
    # ── Indexing elements ──
    "indexterm": re.compile(r'\bindexterm\b', re.I),
    "index-see": re.compile(r'\bindex[\-\s]see\b', re.I),
    "index-see-also": re.compile(r'\bindex[\-\s]see[\-\s]also\b', re.I),
    "index-sort-as": re.compile(r'\bindex[\-\s]sort[\-\s]as\b', re.I),
    # ── DITAVAL elements ──
    "ditaval": re.compile(r'\bditaval\b', re.I),
    "val-prop": re.compile(r'\b(?:val\s+prop|ditaval\s+prop)\b', re.I),
    "val-revprop": re.compile(r'\brevprop\b', re.I),
    "val-startflag": re.compile(r'\bstartflag\b', re.I),
    "val-endflag": re.compile(r'\bendflag\b', re.I),
    # ── Subject scheme elements ──
    "subjectScheme": re.compile(r'\b(?:subject[\-\s]?scheme)\b', re.I),
    "subjectdef": re.compile(r'\bsubjectdef\b', re.I),
    "hasNarrower": re.compile(r'\bhas[\-\s]?narrower\b', re.I),
    "subjectHead": re.compile(r'\bsubject[\-\s]?head\b', re.I),
    "enumerationdef": re.compile(r'\benumeration[\-\s]?def\b', re.I),
    "attributedef": re.compile(r'\battribute[\-\s]?def\b', re.I),
    # ── Troubleshooting topic elements ──
    "troubleshooting": re.compile(r'\b(?:<troubleshooting\b|troubleshooting\s+topic)\b', re.I),
    "troublebody": re.compile(r'\btroublebody\b', re.I),
    "condition": re.compile(r'\b(?:<condition\b|trouble\s+condition)\b', re.I),
    "troubleSolution": re.compile(r'\btrouble[\-\s]?solution\b', re.I),
    "cause": re.compile(r'\b(?:<cause\b|trouble\s+cause)\b', re.I),
    "remedy": re.compile(r'\b(?:<remedy\b|trouble\s+remedy)\b', re.I),
    # ── Hazard statement elements ──
    "hazardstatement": re.compile(r'\bhazard[\-\s]?statement\b', re.I),
    "messagepanel": re.compile(r'\bmessage[\-\s]?panel\b', re.I),
    "typeofhazard": re.compile(r'\btype[\-\s]?of[\-\s]?hazard\b', re.I),
    "howtoavoid": re.compile(r'\bhow[\-\s]?to[\-\s]?avoid\b', re.I),
    "consequence": re.compile(r'\b(?:<consequence\b|hazard\s+consequence)\b', re.I),
    # ── Structural container elements ──
    "bodydiv": re.compile(r'\bbodydiv\b', re.I),
    "sectiondiv": re.compile(r'\bsectiondiv\b', re.I),
    "div": re.compile(r'\b(?:<div\b|dita\s+div\s+element)\b', re.I),
    # ── Terminology/keyword domain elements ──
    "term": re.compile(r'\b(?:<term\b|term\s+element)\b', re.I),
    "keyword": re.compile(r'\b(?:<keyword\b|keyword\s+element)\b', re.I),
    "abbreviated-form": re.compile(r'\b(?:abbreviated[\-\s]?form)\b', re.I),
    "abbrev": re.compile(r'\b(?:<abbrev\b|abbreviation\s+element)\b', re.I),
    # ── Quotation/inline elements ──
    "cite": re.compile(r'\b(?:<cite\b|cite\s+element)\b', re.I),
    "q": re.compile(r'\b(?:<q\b|inline\s+quote)\b', re.I),
    "tt": re.compile(r'\b(?:<tt\b|teletype|monospace\s+element)\b', re.I),
    "var": re.compile(r'\b(?:<var\b|var\s+element)\b', re.I),
    # ── Description element ──
    "desc": re.compile(r'\b(?:<desc\b|desc\s+element|description\s+child\s+element)\b', re.I),
    # ── Task sub-elements ──
    "stepxmp": re.compile(r'\bstepxmp\b', re.I),
    "stepsection": re.compile(r'\bstepsection\b', re.I),
    # ── Choicetable header cells ──
    "choptionhd": re.compile(r'\bchoptionhd\b', re.I),
    "chdeschd": re.compile(r'\bchdeschd\b', re.I),
    # ── Definition list headers ──
    "dthd": re.compile(r'\bdthd\b', re.I),
    "ddhd": re.compile(r'\bddhd\b', re.I),
    # ── Prolog metadata elements ──
    "author": re.compile(r'\b(?:<author\b|author\s+element)\b', re.I),
    "source": re.compile(r'\b(?:<source\b|source\s+element)\b', re.I),
    "copyright": re.compile(r'\b(?:<copyright\b|copyright\s+element)\b', re.I),
    "copyryear": re.compile(r'\bcopyryear\b', re.I),
    "copyrholder": re.compile(r'\bcopyrholder\b', re.I),
    # ── Glossary extension elements ──
    "glossPartOfSpeech": re.compile(r'\bgloss[\-\s]?part[\-\s]?of[\-\s]?speech\b', re.I),
    "glossSynonym": re.compile(r'\bgloss[\-\s]?synonym\b', re.I),
    "glossgroup": re.compile(r'\bglossgroup\b', re.I),
    "glossref": re.compile(r'\bglossref\b', re.I),
    # ── Subject scheme extension elements ──
    "schemeref": re.compile(r'\bschemeref\b', re.I),
    "hasInstance": re.compile(r'\bhas[\-\s]?instance\b', re.I),
    "subjectref": re.compile(r'\bsubjectref\b', re.I),
    "topicsubject": re.compile(r'\btopic[\-\s]?subject\b', re.I),
    "defaultSubject": re.compile(r'\bdefault[\-\s]?subject\b', re.I),
    "hasKind": re.compile(r'\bhas[\-\s]?kind\b', re.I),
    "hasPart": re.compile(r'\bhas[\-\s]?part\b', re.I),
    "hasRelated": re.compile(r'\bhas[\-\s]?related\b', re.I),
    # ── Reltable children (explicit keys for precise detection) ──
    "relrow": re.compile(r'\brelrow\b', re.I),
    "relcell": re.compile(r'\brelcell\b', re.I),
    "relcolspec": re.compile(r'\brelcolspec\b', re.I),
    # ── Indexing extension ──
    "index-base": re.compile(r'\bindex[\-\s]base\b', re.I),
    # ── Media extension ──
    "imagemap": re.compile(r'\bimagemap\b', re.I),
}

_ATTR_VALUE_PATTERNS: dict[str, re.Pattern[str]] = {
    "format": re.compile(r'format\s*=\s*["\']?(\w+)', re.I),
    "scope": re.compile(r'scope\s*=\s*["\']?(local|peer|external)', re.I),
    "type": re.compile(r'type\s*=\s*["\']?(\w+(?:/\w+)?)', re.I),
    "chunk": re.compile(r'chunk\s*=\s*["\']?(to-content|to-navigation|by-topic|by-document|select-topic|select-document|select-branch|[\w\-]+)', re.I),
    "collection-type": re.compile(r'collection[\-.]type\s*=\s*["\']?(choice|family|sequence|unordered|tree|\w+)', re.I),
    "processing-role": re.compile(r'processing[\-.]role\s*=\s*["\']?([\w\-]+)', re.I),
    "linking": re.compile(r'linking\s*=\s*["\']?(\w+)', re.I),
    "toc": re.compile(r'toc\s*=\s*["\']?(yes|no)', re.I),
    "print": re.compile(r'print\s*=\s*["\']?(yes|no|printonly)', re.I),
    "audience": re.compile(r'audience\s*=\s*["\']?([\w\-]+)', re.I),
    "platform": re.compile(r'platform\s*=\s*["\']?([\w\-]+)', re.I),
    "product": re.compile(r'product\s*=\s*["\']?([\w\-]+)', re.I),
    "rev": re.compile(r'rev\s*=\s*["\']?([\w\-.]+)', re.I),
    "status": re.compile(r'status\s*=\s*["\']?(new|changed|deleted|unchanged)', re.I),
    "importance": re.compile(r'importance\s*=\s*["\']?(obsolete|deprecated|optional|default|low|normal|high|recommended|required|urgent)', re.I),
    "translate": re.compile(r'translate\s*=\s*["\']?(yes|no)', re.I),
    "dir": re.compile(r'dir\s*=\s*["\']?(ltr|rtl|lro|rlo)', re.I),
    "xml:lang": re.compile(r'xml:lang\s*=\s*["\']?([\w\-]+)', re.I),
    "conaction": re.compile(r'conaction\s*=\s*["\']?(pushafter|pushbefore|pushreplace|mark|markpush)', re.I),
    "cascade": re.compile(r'cascade\s*=\s*["\']?(merge|nomerge)', re.I),
    "deliveryTarget": re.compile(r'deliveryTarget\s*=\s*["\']?([\w\-]+)', re.I),
    "role": re.compile(r'role\s*=\s*["\']?(parent|child|sibling|friend|next|previous|cousin|ancestor|descendant|sample|external|other)', re.I),
    "placement": re.compile(r'placement\s*=\s*["\']?(inline|break)', re.I),
    "frame": re.compile(r'frame\s*=\s*["\']?(all|bottom|none|sides|top|topbot)', re.I),
    "expanse": re.compile(r'expanse\s*=\s*["\']?(column|page|spread|textline)', re.I),
    "align": re.compile(r'align\s*=\s*["\']?(left|right|center|justify|char)', re.I),
    "valign": re.compile(r'valign\s*=\s*["\']?(top|middle|bottom)', re.I),
    "note-type": re.compile(r'type\s*=\s*["\']?(note|tip|important|remember|restriction|attention|caution|danger|warning|trouble|notice|other)', re.I),
    "search": re.compile(r'search\s*=\s*["\']?(yes|no)', re.I),
    "copy-to": re.compile(r'copy-to\s*=\s*["\']?([\w\-./]+)', re.I),
    "outputclass": re.compile(r'outputclass\s*=\s*["\']?([\w\-\s]+)', re.I),
    "conref-fragment": re.compile(r'conref\s*=\s*["\']?[^"\']*#([\w\-]+/[\w\-]+)', re.I),
    "keycol": re.compile(r'keycol\s*=\s*["\']?(\d+)', re.I),
    "compact": re.compile(r'compact\s*=\s*["\']?(yes|no)', re.I),
    "pgwide": re.compile(r'pgwide\s*=\s*["\']?([01])', re.I),
    "orient": re.compile(r'orient\s*=\s*["\']?(port|land)', re.I),
    "rowheader": re.compile(r'rowheader\s*=\s*["\']?(firstcol|norowheader|headers)', re.I),
    "xml:space": re.compile(r'xml:space\s*=\s*["\']?(preserve|default)', re.I),
}


def _detect_dita_construct(text: str, evidence_fields: dict | None = None) -> DetectedDitaConstruct:
    """Identify which DITA attributes/elements a Jira ticket is about."""
    ef = evidence_fields or {}
    search_text = (text or "") + " " + (ef.get("summary") or "") + " " + (ef.get("description") or "")

    detected_attrs: list[str] = []
    detected_elems: list[str] = []
    specific_values: dict[str, list[str]] = {}

    for attr_name, pattern in _DITA_ATTRIBUTE_PATTERNS.items():
        if pattern.search(search_text):
            detected_attrs.append(attr_name)
            val_pat = _ATTR_VALUE_PATTERNS.get(attr_name)
            if val_pat:
                vals = val_pat.findall(search_text)
                if vals:
                    specific_values[attr_name] = list(dict.fromkeys(vals))

    for elem_name, pattern in _DITA_ELEMENT_PATTERNS.items():
        if pattern.search(search_text):
            detected_elems.append(elem_name)

    confidence = 0.0
    if detected_attrs or detected_elems:
        confidence = 0.5
        if detected_attrs and detected_elems:
            confidence = 0.8
        if specific_values:
            confidence = min(1.0, confidence + 0.15)

    return DetectedDitaConstruct(
        attributes=detected_attrs,
        elements=detected_elems,
        specific_values=specific_values,
        confidence=confidence,
    )


def _keyword_boost_intent(
    user_text: str,
    base: IntentRecord,
    evidence_fields: dict | None = None,
) -> IntentRecord:
    """Merge rule-based signals so table/alignment issues never miss anti_fallback flags.

    When evidence_fields contains structured Jira data (issue_type, steps_to_reproduce, etc.),
    use them to boost topic type and content intent accuracy.
    """
    t = (user_text or "").lower()
    patterns = list(base.required_dita_patterns)
    anti = list(base.anti_fallback_signals)
    dom = base.domain_signals.model_copy()
    topic_type = base.dita_topic_type_guess
    content_intent = base.content_intent

    ef = evidence_fields or {}

    # --- Jira issue type → DITA topic type boost ---
    jira_type = (ef.get("issue_type") or "").strip().lower()
    if jira_type and jira_type in _JIRA_TYPE_TO_DITA:
        mapped_type, mapped_intent = _JIRA_TYPE_TO_DITA[jira_type]
        # Only override if LLM wasn't confident (unknown or low-confidence)
        if topic_type in ("unknown", "topic"):
            topic_type = mapped_type
        if content_intent == "unknown":
            content_intent = mapped_intent

    # --- Structured field signals ---
    if ef.get("steps_to_reproduce"):
        if "steps" not in patterns:
            patterns.append("steps")
        if topic_type in ("unknown", "topic", "concept"):
            topic_type = "task"
        if content_intent == "unknown":
            content_intent = "bug_repro"

    if ef.get("acceptance_criteria"):
        if "checklist" not in patterns:
            patterns.append("checklist")

    if ef.get("expected_behavior") and ef.get("actual_behavior"):
        # Troubleshooting pattern: symptom (actual) + remedy (expected)
        if content_intent == "unknown":
            content_intent = "bug_repro"
        if topic_type in ("unknown", "topic"):
            topic_type = "task"

    # --- BDD / user story patterns ---
    if re.search(r"\bgiven\b.*\bwhen\b.*\bthen\b", t, re.DOTALL):
        if "steps" not in patterns:
            patterns.append("steps")
        if topic_type in ("unknown", "topic"):
            topic_type = "task"

    if re.search(r"\bas\s+a\b.*\bi\s+want\b", t, re.DOTALL):
        if topic_type in ("unknown", "topic"):
            topic_type = "concept"
        if content_intent == "unknown":
            content_intent = "feature_request"

    # ══════════════════════════════════════════════════════════════
    # JSON-driven keyword engine (edit topic_type_keywords.json to add keywords)
    # ══════════════════════════════════════════════════════════════
    kw_cfg = _load_keyword_config()
    intent_map = kw_cfg.get("content_intent_map", {})

    # ── 1. Explicit overrides (highest priority — user explicitly asked for a type) ──
    explicit = kw_cfg.get("explicit_overrides", {})
    for tt, tt_patterns in explicit.items():
        if tt.startswith("_"):
            continue
        if isinstance(tt_patterns, list) and _match_any(t, tt_patterns):
            topic_type = tt
            content_intent = intent_map.get(tt, content_intent if content_intent != "unknown" else "documentation")
            # Add related patterns (e.g., glossary → glossary pattern)
            if tt == "glossentry" and "glossary" not in patterns:
                patterns.append("glossary")
            break

    # ── 2. Inferred keywords (secondary — only when type is still ambiguous) ──
    if topic_type in ("unknown", "topic"):
        inferred = kw_cfg.get("inferred_keywords", {})
        for tt in ("reference", "task", "concept"):  # priority order
            tt_patterns = inferred.get(tt, [])
            if isinstance(tt_patterns, list) and _match_any(t, tt_patterns):
                topic_type = tt
                if content_intent == "unknown":
                    content_intent = intent_map.get(tt, "documentation")
                break

    # ── 3. Pattern boosters (add required_dita_patterns from keywords) ──
    boosters = kw_cfg.get("pattern_boosters", {})
    for pat_name, pat_keywords in boosters.items():
        if pat_name.startswith("_"):
            continue
        if isinstance(pat_keywords, list) and _match_any(t, pat_keywords):
            if pat_name not in patterns:
                patterns.append(pat_name)
            # Some patterns also imply a topic type
            if pat_name == "task_steps" and topic_type in ("unknown", "topic"):
                topic_type = "task"
            elif pat_name == "properties" and topic_type in ("unknown", "topic"):
                topic_type = "reference"

    # ── 4. Domain signal detection (from JSON) ──
    domain_cfg = kw_cfg.get("domain_signals", {})
    if isinstance(domain_cfg.get("aem_guides"), list) and _match_any(t, domain_cfg["aem_guides"]):
        dom.aem_guides = True
    if isinstance(domain_cfg.get("web_editor"), list) and _match_any(t, domain_cfg["web_editor"]):
        dom.web_editor = True
    if isinstance(domain_cfg.get("ui_workflow"), list) and _match_any(t, domain_cfg["ui_workflow"]):
        dom.ui_workflow = True
    if isinstance(domain_cfg.get("dita_ot"), list) and _match_any(t, domain_cfg["dita_ot"]):
        dom.dita_ot = True
    # Note: localization and publishing signals are informational (no DomainSignals field yet)
    # but they still help the LLM intent analyzer via keyword presence.

    # ── Legacy table/alignment patterns (kept for backward compat) ──
    if "table" in t or "tables" in t or "cell" in t or "column" in t:
        if "table" not in patterns and "none" not in patterns:
            patterns.append("table")
        if any(x in t for x in ("align", "alignment", "right-click", "right click", "menu", "menus", "justify")):
            anti.extend(["table_alignment", "no_prose_only"])
            if "menucascade" not in patterns:
                patterns.append("menucascade")
    if any(x in t for x in ("aem", "xml documentation", "guides", "web editor", "oxygen")):
        dom.aem_guides = True
    if any(x in t for x in ("web editor", "author", "preview", "rte", "rich text")):
        dom.web_editor = True
    if any(x in t for x in ("menu", "click", "ui", "dialog", "context")):
        dom.ui_workflow = True

    # Dedupe patterns (remove none if we added real patterns)
    if any(p != "none" for p in patterns):
        patterns = [p for p in patterns if p != "none"]
    anti = list(dict.fromkeys(anti))

    # DITA construct detection (for test data generation)
    construct = _detect_dita_construct(user_text, evidence_fields=ef)

    spec = base.specialized_construct_required or bool(
        [p for p in patterns if p and p != "none"]
    )
    if construct.confidence >= 0.5:
        spec = True

    return base.model_copy(
        update={
            "required_dita_patterns": patterns or base.required_dita_patterns,
            "anti_fallback_signals": anti or base.anti_fallback_signals,
            "domain_signals": dom,
            "specialized_construct_required": spec,
            "dita_topic_type_guess": topic_type,
            "content_intent": content_intent,
            "detected_dita_construct": construct,
        }
    )


def _load_intent_prompt() -> str:
    p = PROMPTS_DIR / "intent_analysis.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _fallback_intent(user_text: str, evidence_fields: dict | None = None) -> IntentRecord:
    ir = IntentRecord(
        content_intent="unknown",
        dita_topic_type_guess="unknown",
        specialized_construct_required=False,
        user_expectation="Generate appropriate DITA from the request.",
        confidence=0.3,
    )
    return _keyword_boost_intent(user_text, ir, evidence_fields=evidence_fields)


async def analyze_intent_async(
    user_text: str,
    *,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
    evidence_fields: dict | None = None,
) -> IntentRecord:
    from app.services.llm_service import generate_json, is_llm_available

    text = (user_text or "").strip()
    if not text:
        return _fallback_intent(text, evidence_fields=evidence_fields)

    prompt = _load_intent_prompt()
    if not prompt or not is_llm_available():
        logger.info_structured(
            "Intent analysis: LLM unavailable or prompt missing; keyword-only",
            extra_fields={"jira_id": jira_id},
        )
        return _keyword_boost_intent(text, _fallback_intent(text, evidence_fields=evidence_fields), evidence_fields=evidence_fields)

    try:
        raw = await generate_json(
            prompt,
            f"USER TEXT:\n{text[:12000]}\n\nOutput JSON only:",
            max_tokens=1200,
            step_name="intent_analysis",
            trace_id=trace_id,
            jira_id=jira_id,
        )
        if not isinstance(raw, dict):
            raw = {}
        dom = raw.get("domain_signals") or {}
        base = IntentRecord(
            content_intent=raw.get("content_intent", "unknown"),
            dita_topic_type_guess=raw.get("dita_topic_type_guess", "unknown"),
            specialized_construct_required=bool(raw.get("specialized_construct_required", False)),
            required_dita_patterns=list(raw.get("required_dita_patterns") or []),
            domain_signals=DomainSignals(
                aem_guides=bool(dom.get("aem_guides", False)),
                dita_ot=bool(dom.get("dita_ot", False)),
                web_editor=bool(dom.get("web_editor", False)),
                ui_workflow=bool(dom.get("ui_workflow", False)),
            ),
            user_expectation=str(raw.get("user_expectation") or "")[:500],
            anti_fallback_signals=list(raw.get("anti_fallback_signals") or []),
            evidence_phrases=list(raw.get("evidence_phrases") or [])[:20],
            confidence=float(raw.get("confidence") or 0.5),
            assumptions=list(raw.get("assumptions") or [])[:10],
        )
        merged = _keyword_boost_intent(text, base, evidence_fields=evidence_fields)
        logger.info_structured(
            "Intent analysis complete",
            extra_fields={
                "jira_id": jira_id,
                "content_intent": merged.content_intent,
                "specialized_construct_required": merged.specialized_construct_required,
                "patterns": merged.required_dita_patterns[:8],
            },
        )
        return merged
    except Exception as e:
        logger.warning_structured(
            "Intent analysis LLM failed; keyword fallback",
            extra_fields={"error": str(e), "jira_id": jira_id},
        )
        return _keyword_boost_intent(text, _fallback_intent(text, evidence_fields=evidence_fields), evidence_fields=evidence_fields)


def analyze_intent_sync(user_text: str, evidence_fields: dict | None = None) -> IntentRecord:
    """Synchronous keyword-only intent (for tight loops / tests)."""
    return _keyword_boost_intent(user_text, _fallback_intent(user_text, evidence_fields=evidence_fields), evidence_fields=evidence_fields)
