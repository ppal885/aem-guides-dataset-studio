"""
Freeform LLM-first DITA generation.

Bypasses the recipe system entirely. The LLM:
  1. Plans a topic outline for the requested domain
  2. Fills each topic with real content in batches of 10

Output quality is dramatically higher than recipe-generated content because
the LLM uses actual domain knowledge instead of string templates.

Advanced modes (auto-detected from prompt keywords):
  - "mathml":        generates concept/reference/task topics with AEM Guides MathML structure
  - "bookmap":       generates a full bookmap with frontmatter, chapters, appendices, backmatter
  - "profiling":     generates topics with audience/platform/product profiling attributes +
                     .ditaval filter files defining include/exclude/flag rules
  - "reltable":      generates a map with <reltable> relationship sections that drive
                     automatic "Related Links" sections in output topics
  - "table_domain":  generates topics with complex <table>/<tgroup>/<colspec> markup including
                     spanning cells (namest/nameend/morerows) and <simpletable> comparisons
  - "nested_keydef": generates a root map + keyscoped submaps with key shadowing/cross-scope refs
  - "code_domain":   generates topics with <codeblock>, <codeph>, <coderef>, <filepath>, and
                     external-scope xrefs; creates real code files in code/ for <coderef> targets
  - "conref":        generates source topics with @id'd elements + consumer topics with @conref
  - "keydef":        generates a keydef map + consumer topics using @keyref
  - "glossary":      generates glossentry topics + consuming topics with <term> references
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.core.structured_logging import get_structured_logger
from app.services.llm_service import generate_json

logger = get_structured_logger(__name__)


def _sanitize_keywords_in_body(xml: str) -> str:
    """Move <keywords>...</keywords> from <body> to <prolog><metadata> (DTD fix).

    The DITA DTD forbids <keywords> inside <body>. This sanitizer detects the
    violation and relocates the block to the correct place. If no <body> violation
    is found the string is returned unchanged.
    """
    if "<keywords>" not in xml or "<body>" not in xml:
        return xml

    # Extract the <keywords> block(s) from inside <body>
    keywords_blocks: list[str] = re.findall(r"<keywords>.*?</keywords>", xml, re.DOTALL)
    if not keywords_blocks:
        return xml

    # Check that at least one is inside <body>
    body_match = re.search(r"<body>(.*?)</body>", xml, re.DOTALL)
    if not body_match or "<keywords>" not in body_match.group(1):
        return xml

    # Remove <keywords>...</keywords> from <body>
    def _strip_keywords_from_body(m: re.Match) -> str:
        cleaned = re.sub(r"\s*<keywords>.*?</keywords>", "", m.group(0), flags=re.DOTALL)
        return cleaned

    xml = re.sub(r"<body>.*?</body>", _strip_keywords_from_body, xml, flags=re.DOTALL)

    # Merge the collected keyword blocks into a single <keywords> element
    all_kw_children: list[str] = []
    for block in keywords_blocks:
        inner = re.sub(r"^<keywords>|</keywords>$", "", block.strip())
        all_kw_children.append(inner.strip())
    merged_kw = "<keywords>\n      " + "\n      ".join(all_kw_children) + "\n    </keywords>"

    # Insert into <prolog><metadata> if already present
    if "<prolog>" in xml and "<metadata>" in xml:
        xml = re.sub(
            r"(<metadata>)",
            lambda m: m.group(1) + "\n      " + merged_kw,
            xml,
            count=1,
        )
    elif "<prolog>" in xml:
        xml = re.sub(
            r"(<prolog>)",
            lambda m: m.group(1) + "\n    <metadata>" + merged_kw + "</metadata>",
            xml,
            count=1,
        )
    else:
        # Insert a prolog before <body>
        xml = xml.replace("<body>", f"<prolog><metadata>{merged_kw}</metadata></prolog>\n  <body>", 1)

    return xml


_DITA_MODE_CONREF = re.compile(
    r"\b(?:conref|content[\s-]?reuse|reusable[\s-]?content|content[\s-]?reference)\b",
    re.IGNORECASE,
)
_DITA_MODE_CONKEYREF = re.compile(
    r"\b(?:conkeyref|key[\s-]?based[\s-]?reuse)\b",
    re.IGNORECASE,
)
_DITA_MODE_BOOKMAP = re.compile(
    r"\b(?:bookmap|book[-\s]map|booktitle|bookabstract|frontmatter|front[-\s]matter"
    r"|backmatter|back[-\s]matter|chapter\b|appendix|colophon|booklist"
    r"|pdf[-\s]book|book[-\s]structure|book[-\s]chapter)\b",
    re.IGNORECASE,
)
_DITA_MODE_PROFILING = re.compile(
    r"\b(?:ditaval|dita[-\s]val|profiling|conditional[-\s](?:content|text|processing)"
    r"|audience\s*=|platform\s*=|product\s*=|otherprops\s*=|props\s*="
    r"|@audience|@platform|@product|@props|@otherprops"
    r"|filter(?:ing)?[-\s](?:content|attribute|rule|condition)"
    r"|flagging|include[-\s]exclude|conditional[-\s]filter)\b",
    re.IGNORECASE,
)
_DITA_MODE_RELTABLE = re.compile(
    r"\b(?:reltable|rel[-\s]table|relationship[-\s]table|relrow|relcell|relcolspec"
    r"|related[-\s]links?[-\s](?:map|section|table)|non[-\s]hierarchical[-\s]link"
    r"|map[-\s]relationship|topic[-\s]relationship)\b",
    re.IGNORECASE,
)
_DITA_MODE_TABLE_DOMAIN = re.compile(
    r"\b(?:tgroup|colspec|col[-\s]spec|namest|nameend|morerows"
    r"|spanning[-\s]cell|cell[-\s]span(?:ning)?|row[-\s]span(?:ning)?"
    r"|col(?:umn)?[-\s]span(?:ning)?|table[-\s](?:header|border|frame|align|colwidth)"
    r"|entrytbl|thead[-\s]row|simpletable[-\s]vs|relcolwidth)\b",
    re.IGNORECASE,
)
_DITA_MODE_CODE_DOMAIN = re.compile(
    r"\b(?:codeblock|code[-\s]block|codeph|code[-\s]phrase|coderef|code[-\s]ref"
    r"|filepath|file[-\s]path|programlisting|screen\b|userinput|systemoutput"
    r"|scope\s*=\s*[\"']?external|external\s+(?:link|url|href|scope)"
    r"|programming\s+domain|code\s+example|syntax\s+example|code\s+sample"
    r"|inline\s+code|fenced\s+code|language\s+class|outputclass)\b",
    re.IGNORECASE,
)
_DITA_MODE_NESTED_KEYDEF = re.compile(
    r"\b(?:nested\s+map|nested\s+maps|submap|sub[-\s]map|mapref|map[-\s]ref"
    r"|root\s+map|child\s+map|parent\s+map|keyscope|key[-\s]scope"
    r"|cross[-\s]map\s+key|key[-\s](?:resolution|inheritance|shadow|conflict|override)"
    r"|key(?:s)?\s+(?:across|between|in\s+different)\s+(?:\w+\s+)?maps?"
    r"|different\s+maps?\s+(?:and|with|key)|keys?\s+in\s+different\s+maps?)\b",
    re.IGNORECASE,
)
_DITA_MODE_KEYDEF = re.compile(
    r"\b(?:keydef|key[\s-]?definition|keyref|key[\s-]?reference|keyscope)\b",
    re.IGNORECASE,
)
_DITA_MODE_GLOSSARY = re.compile(
    r"\b(?:glossar(?:y|ies)|glossentry|term[\s-]?definition|glossdef)\b",
    re.IGNORECASE,
)
_DITA_MODE_MATHML = re.compile(
    r"\b(?:mathml|m:math|equation[-\s]?block|equation[-\s]?inline|mathematical?\s+equation"
    r"|inline\s+equation|display\s+equation|foreign\s+(?:element|tag|content)"
    r"|m:mrow|m:mfrac|m:msqrt|m:msup|m:msub|latex|formula|mathematical?\s+expression"
    r"|math(?:ematical)?\s+notation|math(?:ematical)?\s+content)\b",
    re.IGNORECASE,
)


def _detect_dita_mode(prompt: str) -> str:
    """Detect the most specific DITA authoring mode from the prompt/Jira content."""
    if _DITA_MODE_MATHML.search(prompt):
        return "mathml"
    if _DITA_MODE_BOOKMAP.search(prompt):
        return "bookmap"
    if _DITA_MODE_PROFILING.search(prompt):
        return "profiling"
    if _DITA_MODE_RELTABLE.search(prompt):
        return "reltable"
    if _DITA_MODE_TABLE_DOMAIN.search(prompt):
        return "table_domain"
    if _DITA_MODE_CODE_DOMAIN.search(prompt):
        return "code_domain"
    if _DITA_MODE_NESTED_KEYDEF.search(prompt):
        return "nested_keydef"
    if _DITA_MODE_CONKEYREF.search(prompt):
        return "conkeyref"
    if _DITA_MODE_CONREF.search(prompt):
        return "conref"
    if _DITA_MODE_KEYDEF.search(prompt):
        return "keydef"
    if _DITA_MODE_GLOSSARY.search(prompt):
        return "glossary"
    return "topics"


_OUTLINE_SYSTEM_BOOKMAP = """\
You are a DITA information architect designing a bookmap-based publication dataset.

Output ONLY a valid JSON object:
{{
  "book_title": "string",
  "subtitle": "string",
  "frontmatter_topics": [
    {{"id": "fm001", "title": "string", "role": "abstract|preface|notices"}}
  ],
  "chapters": [
    {{
      "id": "ch001",
      "title": "string",
      "href_topic": {{"id": "t001", "title": "string", "type": "concept|task|reference"}},
      "child_topics": [
        {{"id": "t002", "title": "string", "type": "concept|task|reference"}}
      ]
    }}
  ],
  "appendices": [
    {{"id": "ap001", "title": "string",
      "href_topic": {{"id": "ta001", "title": "string", "type": "concept|task|reference"}}}}
  ],
  "has_index": true
}}

Rules:
- frontmatter_topics: 1–2 topics (abstract describing the book, optional preface).
- chapters: 2–4 chapters. Each chapter has a root concept/task topic + 1–3 child topics. Total topics <= {limit}.
- appendices: 1–2 appendices (reference material, glossary-like content).
- Titles must be real and domain-specific. NEVER use "Chapter 1" — use real chapter names.
- has_index: true if the domain has indexable terminology.
"""

_FILL_SYSTEM_BOOKMAP = """\
You are a DITA 1.3 XML author generating a bookmap publication dataset for AEM Guides.

Output ONLY a valid JSON object:
{{
  "bookmap_xml": "...full bookmap XML...",
  "topic_files": [
    {{"id": "t001", "filename": "topics/topic-001.dita", "xml": "...full DITA XML..."}}
  ]
}}

BOOKMAP STRUCTURE:
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE bookmap PUBLIC "-//OASIS//DTD DITA BookMap//EN" "bookmap.dtd">
  <bookmap id="root-bookmap">
    <booktitle>
      <mainbooktitle>Real Book Title</mainbooktitle>
      <booktitlealt>Optional subtitle</booktitlealt>
    </booktitle>
    <bookmeta>
      <bookrights>
        <copyrfirst><year>2025</year></copyrfirst>
        <bookowner><organization>Real Organization Name</organization></bookowner>
      </bookrights>
    </bookmeta>
    <frontmatter>
      <bookabstract href="topics/abstract.dita"/>
      <preface href="topics/preface.dita"/>
      <booklists><toc/></booklists>
    </frontmatter>
    <chapter href="topics/chapter1-overview.dita">
      <topicref href="topics/chapter1-section1.dita"/>
      <topicref href="topics/chapter1-section2.dita"/>
    </chapter>
    <chapter href="topics/chapter2-installation.dita">
      <topicref href="topics/chapter2-prereqs.dita"/>
    </chapter>
    <appendix href="topics/appendix-a-reference.dita"/>
    <backmatter>
      <booklists>
        <indexlist/>
        <figurelist/>
        <tablelist/>
      </booklists>
    </backmatter>
  </bookmap>

TOPIC TYPES used in bookmaps:
- abstract / preface: <!DOCTYPE concept> with <conbody> summarizing the book's purpose.
- Chapter root topics: can be concept, task, or reference — use the chapter's subject.
- Appendix topics: typically reference topics with tables or reference lists.

CRITICAL:
- bookmap href paths are RELATIVE to the bookmap (which is at root level): topics/filename.dita
- frontmatter elements: bookabstract, preface, notices — MUST have real content topics.
- backmatter can contain indexlist, figurelist, tablelist inside <booklists>.
- DO NOT use <chapter> without an href — every chapter must point to a real topic.
- XML must be well-formed. id attributes must match the input exactly.
"""

_OUTLINE_SYSTEM_PROFILING = """\
You are a DITA information architect designing a conditional-profiling dataset.

This dataset exercises AEM Guides conditional content: DITAVAL filter files and
profiling attributes (audience, platform, product, props) on topic elements.

Output ONLY a valid JSON object:
{{
  "map_title": "string",
  "profiling_attributes": [
    {{
      "attribute": "audience|platform|product|props",
      "values": ["val1", "val2"],
      "description": "what this attribute distinguishes"
    }}
  ],
  "ditaval_files": [
    {{
      "filename": "filters/name.ditaval",
      "description": "what scenario this filter targets",
      "conditions": [
        {{"att": "audience", "val": "admin", "action": "include"}},
        {{"att": "audience", "val": "basic", "action": "exclude"}}
      ]
    }}
  ],
  "topics": [
    {{
      "id": "t001",
      "title": "string",
      "type": "concept|task|reference",
      "profiling_used": [
        {{"attribute": "audience", "values_present": ["admin", "basic"]}},
        {{"attribute": "platform", "values_present": ["windows", "linux"]}}
      ]
    }}
  ]
}}

Rules:
- profiling_attributes: 2–3 attributes. Always include audience + one of platform/product.
  Use REAL values for the domain (e.g. audience: ["developer","admin","end-user"]).
- ditaval_files: 2–4 filter files in filters/ dir. Each targets a distinct audience/platform.
  Actions: "include", "exclude", "flag". At least 1 file must use "flag".
- topics: {limit} topics. EVERY topic must use profiling attributes on at least some elements.
  Mix which attributes appear so the dataset exercises all combinations.
- Titles must be real and domain-specific.
"""

_FILL_SYSTEM_PROFILING = """\
You are a DITA 1.3 XML author generating a conditional-profiling dataset for AEM Guides.

Output ONLY a valid JSON object:
{{
  "ditaval_files": [
    {{"filename": "filters/admin.ditaval", "xml": "...ditaval XML..."}}
  ],
  "topic_files": [
    {{"id": "t001", "filename": "topics/topic-001.dita", "xml": "...full DITA XML..."}}
  ]
}}

DITAVAL FILE FORMAT:
  <?xml version="1.0" encoding="UTF-8"?>
  <val>
    <prop att="audience" val="admin" action="include"/>
    <prop att="audience" val="basic" action="exclude"/>
    <prop att="platform" val="windows" action="include"/>
    <prop att="platform" val="linux" action="flag">
      <startflag imageref="flag-linux.png"><alt-text>Linux only</alt-text></startflag>
    </prop>
  </val>
  Valid actions: "include" | "exclude" | "flag" | "passthrough"
  <prop> with no action = default (passthrough). Conditions are ANDed within an element.

PROFILING ATTRIBUTES ON TOPIC ELEMENTS:
  audience: "admin", "developer", "end-user", "expert", "basic", "advanced"
  platform: "windows", "linux", "macos", "unix", "all"
  product: use real product names for the domain (e.g. "aem-guides", "aem-cloud")
  props: free-form key=value pairs for custom conditions

HOW TO APPLY IN TOPICS:
  <!-- Paragraph visible only to admin audience -->
  <p audience="admin">This advanced setting requires root access.</p>

  <!-- Paragraph visible to all non-admin audiences -->
  <p audience="basic end-user">Use the default configuration.</p>

  <!-- Step visible only on Windows -->
  <step platform="windows">
    <cmd>Open Control Panel and navigate to System Properties.</cmd>
  </step>
  <step platform="linux">
    <cmd>Run <codeph>sudo systemctl restart aem-guides</codeph>.</cmd>
  </step>

  <!-- Section filtered by product -->
  <section product="aem-cloud" audience="developer">
    <title>Cloud-Specific Configuration</title>
    <p>Only applicable to AEM as a Cloud Service deployments.</p>
  </section>

  <!-- Multiple values (space-separated) = include if ANY value matches -->
  <note type="warning" platform="windows linux">
    <p>This operation is irreversible on all platforms.</p>
  </note>

CONCEPT template with profiling:
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
  <concept id="{{id}}">
    <title>Real concept title</title>
    <shortdesc>One sentence summary.</shortdesc>
    <conbody>
      <p>Common content visible to all audiences.</p>
      <p audience="admin">Administrator-specific explanation with real domain detail.</p>
      <p audience="developer">Developer note mentioning API or config file.</p>
      <section platform="windows"><title>Windows Setup</title>
        <p>Real Windows-specific instructions.</p>
      </section>
      <section platform="linux"><title>Linux Setup</title>
        <p>Real Linux-specific instructions.</p>
      </section>
    </conbody>
  </concept>

TASK template with profiling:
  <taskbody>
    <steps>
      <step><cmd>Common first step.</cmd></step>
      <step platform="windows"><cmd>Windows-specific command.</cmd></step>
      <step platform="linux macos"><cmd>Unix-specific command.</cmd></step>
      <step audience="admin"><cmd>Admin-only verification step.</cmd></step>
    </steps>
  </taskbody>

CRITICAL:
- Multiple attribute values are SPACE-SEPARATED, not comma-separated: audience="admin developer"
- DITAVAL actions are case-sensitive: use lowercase "include", "exclude", "flag"
- Do NOT put profiling on <topic>, <concept>, <task>, <reference> root elements — only on body elements.
- XML must be well-formed. id attributes must exactly match input.
"""

_OUTLINE_SYSTEM_RELTABLE = """\
You are a DITA information architect designing a relationship-table dataset.

Relationship tables (reltable) in DITA maps define non-hierarchical links between topics.
AEM Guides uses reltables to auto-generate "Related Links" sections in output topics.

Output ONLY a valid JSON object:
{{
  "map_title": "string",
  "topics": [
    {{"id": "t001", "title": "string", "type": "concept|task|reference",
      "summary": "one sentence — used to decide reltable groupings"}}
  ],
  "reltable_groups": [
    {{
      "description": "why these topics are related",
      "concept_ids": ["t001"],
      "task_ids": ["t002", "t003"],
      "reference_ids": ["t004"]
    }}
  ]
}}

Rules:
- topics: {limit} total. Mix at least 3 concepts, 4 tasks, 3 references.
- reltable_groups: 2–4 groups. Each group becomes one <relrow> in the reltable.
  A relrow links: concepts (explain) → tasks (how to) → references (spec).
  At least one group must have all three column types.
  Topics can appear in multiple groups (this is valid and common in DITA).
- Titles and summaries must be real and domain-specific.
"""

_FILL_SYSTEM_RELTABLE = """\
You are a DITA 1.3 XML author generating a relationship-table dataset for AEM Guides.

Output ONLY a valid JSON object:
{{
  "ditamap_xml": "...full DITA map XML including reltable...",
  "topic_files": [
    {{"id": "t001", "filename": "topics/topic-001.dita", "xml": "...full DITA XML..."}}
  ]
}}

RELTABLE IN THE MAP — structure and placement:
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
  <map>
    <title>Map Title</title>
    <!-- Normal topic hierarchy FIRST -->
    <topicref href="topics/concept-overview.dita"/>
    <topicref href="topics/task-install.dita"/>
    <topicref href="topics/reference-api.dita"/>

    <!-- Reltable AFTER all topicrefs — defines non-hierarchical relationships -->
    <reltable title="Related Information">
      <relheader>
        <relcolspec type="concept" linking="targetonly"/>
        <relcolspec type="task" linking="normal"/>
        <relcolspec type="reference" linking="targetonly"/>
      </relheader>
      <relrow>
        <!-- Each relcell groups the topics that are related in this row -->
        <relcell><topicref href="topics/concept-overview.dita"/></relcell>
        <relcell>
          <topicref href="topics/task-install.dita"/>
          <topicref href="topics/task-configure.dita"/>
        </relcell>
        <relcell><topicref href="topics/reference-api.dita"/></relcell>
      </relrow>
      <relrow>
        <relcell><topicref href="topics/concept-architecture.dita"/></relcell>
        <relcell><topicref href="topics/task-deploy.dita"/></relcell>
        <relcell/>  <!-- empty relcell is valid -->
      </relrow>
    </reltable>
  </map>

RELTABLE RULES:
- <reltable> comes AFTER all <topicref> hierarchy in the map.
- <relheader> defines columns: type="concept|task|reference", linking="normal|targetonly|sourceonly|none"
  linking="targetonly" means topics in that column get links TO them but do not link OUT.
  linking="normal" means bidirectional links (default).
- <relrow> = one relationship group. Columns correspond to relcolspec order.
- <relcell> can contain 0–N <topicref> elements. Empty <relcell/> is valid.
- A topic in a relrow gets "Related Links" to ALL other topics in the same row (per linking rules).
- href in reltable topicref: SAME relative path as in the main topicref hierarchy.

TOPIC CONTENT — write real substantive content appropriate to type:
- concept: explain a principle, include at least one <ul> or <table>.
- task: real step-by-step procedure, at least 3 <step> elements.
- reference: real API/parameter documentation with <properties> or <simpletable>.
- All topics must have <shortdesc> — this populates the Related Links preview in AEM Guides.

CRITICAL:
- Every href in <reltable> MUST match an href in the main <topicref> hierarchy.
  A topic referenced in reltable but missing from hierarchy causes broken links.
- <relrow> MUST have exactly as many <relcell> elements as <relcolspec> in <relheader>.
- XML must be well-formed. id attributes must match the input exactly.
"""

_OUTLINE_SYSTEM_TABLE_DOMAIN = """\
You are a DITA information architect designing a complex-table dataset.

This dataset exercises DITA table features that commonly break in AEM Guides output:
<table>/<tgroup>/<colspec>, column-spanning (namest/nameend), row-spanning (morerows),
multiple <tgroup> in one table, and <simpletable> for comparison matrices.

Output ONLY a valid JSON object:
{{
  "map_title": "string",
  "topics": [
    {{
      "id": "t001",
      "title": "string",
      "type": "concept|task|reference",
      "table_scenarios": [
        "basic_tgroup", "col_span", "row_span", "multi_tgroup",
        "simpletable", "relcolwidth", "table_in_step"
      ]
    }}
  ]
}}

Rules:
- topics: {limit} topics. Each must exercise at least 2 table_scenarios.
- table_scenarios: select from the list above. Distribute so ALL scenarios appear across the dataset.
  At least 2 topics must have "col_span". At least 2 must have "row_span".
  At least 1 must have "multi_tgroup". At least 2 must have "simpletable".
  At least 1 must have "table_in_step" (table inside a task step <info>).
- Titles must be domain-specific and real.
"""

_FILL_SYSTEM_TABLE_DOMAIN = """\
You are a DITA 1.3 XML author generating a complex-table dataset for AEM Guides.

Output ONLY a valid JSON array:
[
  {{"id": "t001", "filename": "topics/topic-001.dita", "xml": "...full DITA XML..."}}
]

TABLE ELEMENT REFERENCE:

1. BASIC <table> with <tgroup>:
   <table frame="all">
     <title>Real Table Title</title>
     <tgroup cols="3">
       <colspec colname="c1" colwidth="1*"/>
       <colspec colname="c2" colwidth="2*"/>
       <colspec colname="c3" colwidth="1*"/>
       <thead>
         <row><entry>Header 1</entry><entry>Header 2</entry><entry>Header 3</entry></row>
       </thead>
       <tbody>
         <row><entry>Real value</entry><entry>Real detail</entry><entry>Real note</entry></row>
       </tbody>
     </tgroup>
   </table>
   colwidth uses proportional (*) or fixed (pt/cm/mm/in) or mixed.
   frame values: "all" | "top" | "bottom" | "sides" | "topbot" | "none"

2. COLUMN SPANNING (namest/nameend):
   <tgroup cols="4">
     <colspec colname="c1" colwidth="1*"/>
     <colspec colname="c2" colwidth="1*"/>
     <colspec colname="c3" colwidth="1*"/>
     <colspec colname="c4" colwidth="1*"/>
     <tbody>
       <!-- This entry spans columns c2 through c4 -->
       <row>
         <entry>Normal</entry>
         <entry namest="c2" nameend="c4">Spans three columns</entry>
       </row>
     </tbody>
   </tgroup>
   RULE: namest and nameend MUST reference colname values defined in <colspec>.

3. ROW SPANNING (morerows):
   <tbody>
     <row>
       <!-- morerows="2" means this entry spans 3 rows total (this row + 2 more) -->
       <entry morerows="2" valign="middle">Spans 3 rows</entry>
       <entry>Row 1, col 2</entry>
     </row>
     <row><entry>Row 2, col 2</entry></row>
     <row><entry>Row 3, col 2</entry></row>
   </tbody>
   RULE: following rows must NOT include an entry for the spanned column.

4. MULTIPLE <tgroup> in one <table>:
   <table>
     <title>Multi-section Table</title>
     <tgroup cols="2">
       <colspec colname="c1" colwidth="1*"/>
       <colspec colname="c2" colwidth="3*"/>
       <thead><row><entry>Section A</entry><entry>Details</entry></row></thead>
       <tbody>...</tbody>
     </tgroup>
     <tgroup cols="3">
       <colspec colname="d1" colwidth="1*"/>
       <colspec colname="d2" colwidth="1*"/>
       <colspec colname="d3" colwidth="2*"/>
       <thead><row><entry>Col 1</entry><entry>Col 2</entry><entry>Notes</entry></row></thead>
       <tbody>...</tbody>
     </tgroup>
   </table>
   Each <tgroup> has its OWN colspec — colnames do NOT need to be unique across tgroups.

5. <simpletable> — for comparison matrices and property grids:
   <simpletable relcolwidth="1* 2* 1*">
     <sthead>
       <stentry>Feature</stentry><stentry>Description</stentry><stentry>Status</stentry>
     </sthead>
     <strow>
       <stentry>Real feature name</stentry>
       <stentry>Real description</stentry>
       <stentry>Supported</stentry>
     </strow>
   </simpletable>
   relcolwidth: space-separated proportional widths, one per column.
   <simpletable> does NOT support spanning. Use <table>/<tgroup> for spanning.

6. TABLE INSIDE TASK STEP:
   <step>
     <cmd>Review the configuration parameters:</cmd>
     <info>
       <table frame="all">
         <tgroup cols="2">
           <colspec colname="c1" colwidth="1*"/><colspec colname="c2" colwidth="3*"/>
           <thead><row><entry>Parameter</entry><entry>Value</entry></row></thead>
           <tbody>
             <row><entry>timeout</entry><entry>30 seconds</entry></row>
           </tbody>
         </tgroup>
       </table>
     </info>
   </step>
   <table> in step MUST be inside <info>, NOT directly in <step>.

CRITICAL:
- colname values in namest/nameend MUST match a defined <colspec colname="...">.
- Row count after morerows: the spanned entry covers (morerows + 1) rows — next N rows skip that column.
- Always use real domain data in table cells — NEVER "Value 1", "Row 1", "Data".
- XML must be well-formed. Use &lt; &amp; for XML special chars in content.
"""

_OUTLINE_SYSTEM_CODE_DOMAIN = """\
You are a DITA information architect designing a programming-domain dataset.

This dataset must exercise real AEM Guides programming-domain elements:
  <codeblock>, <codeph>, <coderef>, <filepath>, <userinput>, <systemoutput>,
  and external-scope xrefs (scope="external" format="html").

Output ONLY a valid JSON object:
{{
  "map_title": "string",
  "code_files": [
    {{
      "filename": "code/example-001.py",
      "language": "python",
      "description": "What this code file demonstrates"
    }}
  ],
  "topics": [
    {{
      "id": "t001",
      "title": "string",
      "type": "concept|task|reference",
      "code_elements": ["codeblock", "codeph", "filepath"],
      "coderef_files": ["code/example-001.py"],
      "has_external_link": true
    }}
  ]
}}

Rules:
- code_files: 2–5 real code files (python, xml, bash, json, yaml) with meaningful names.
  Each file will be written to code/ directory and referenced via <coderef href="../code/filename"/>.
- topics: {limit} topics mixing concept (explain API/command), task (procedure with code steps),
  reference (syntax tables with codeph).
- code_elements: list which elements each topic MUST include. Every topic must use at least
  codeblock OR coderef. At least 3 topics must use codeph. At least 2 must use filepath.
  At least 1 must use scope="external" xref.
- coderef_files: list the code/ filenames this topic references (can be empty []).
- Titles must be real and domain-specific. NEVER use "Topic 1" placeholders.
"""

_FILL_SYSTEM_CODE_DOMAIN = """\
You are a DITA 1.3 XML author generating a programming-domain dataset for AEM Guides.

Output ONLY a valid JSON object — no markdown fences, no explanation:
{{
  "code_file_contents": [
    {{"filename": "code/example-001.py", "content": "...real code content..."}}
  ],
  "topic_files": [
    {{"id": "t001", "filename": "topics/topic-001.dita", "xml": "...full DITA XML..."}}
  ]
}}

PROGRAMMING DOMAIN ELEMENT RULES:

1. <codeblock> — multi-line code examples. Use outputclass for syntax highlighting:
   <codeblock outputclass="language-python">
   def publish_map(map_id: str) -> bool:
       client = AEMClient()
       return client.publish(map_id, baseline="latest")
   </codeblock>
   Valid outputclass values: language-xml, language-python, language-bash, language-json,
   language-yaml, language-javascript, language-java, language-sql
   NEVER put <codeblock> inside <p>. Valid parents: body, section, conbody, taskbody, li, dd.

2. <codeph> — inline code phrase, ALWAYS inside a <p> or <cmd>:
   <p>Run <codeph>aem-publish --map main.ditamap --env prod</codeph> to deploy.</p>
   <cmd>Set <codeph>JAVA_HOME</codeph> to the JDK installation path.</cmd>

3. <coderef> — references an external code file. Path MUST be relative from topics/ to code/:
   <codeblock><coderef href="../code/example-001.py"/></codeblock>
   The code file must actually exist in the bundle. <coderef> always lives INSIDE <codeblock>.

4. <filepath> — file system paths, always inline inside <p> or <cmd>:
   <p>Open <filepath>/opt/aem-guides/conf/settings.xml</filepath> in a text editor.</p>
   <cmd>Navigate to <filepath>C:\\\\AEM\\\\crx-quickstart\\\\logs</filepath>.</cmd>

5. External xref — links to external URLs. MUST have scope="external" and format="html":
   <xref href="https://experienceleague.adobe.com/docs/experience-manager.html"
         scope="external" format="html">AEM Documentation</xref>
   NEVER omit scope="external" on non-DITA links. NEVER use bare <a> tags.

6. <userinput> — text the user types literally:
   <p>At the prompt, type <userinput>yes</userinput> to confirm.</p>

7. <systemoutput> — output displayed by the system:
   <p>The terminal displays: <systemoutput>Build successful. 42 topics processed.</systemoutput></p>

CONCEPT template (explain a programming concept with code):
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
  <concept id="{{id}}">
    <title>Real concept title</title>
    <shortdesc>One sentence. Mention <codeph>key-element</codeph> or API inline.</shortdesc>
    <conbody>
      <p>Explanation paragraph mentioning <codeph>ClassName</codeph> and
         <filepath>/path/to/config.xml</filepath>.</p>
      <codeblock outputclass="language-python">
# Real, runnable code for the domain
def example_function(param: str) -> dict:
    return {{"status": "ok", "param": param}}
      </codeblock>
      <p>For full reference, see the
         <xref href="https://experienceleague.adobe.com/docs/..." scope="external" format="html">
         official documentation</xref>.</p>
    </conbody>
  </concept>

TASK template (procedure with code steps):
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">
  <task id="{{id}}">
    <title>Real procedure title</title>
    <shortdesc>Steps to accomplish a real task.</shortdesc>
    <taskbody>
      <prereq>
        <p>Install <codeph>aem-guides-cli</codeph> version 3.x or later.</p>
      </prereq>
      <steps>
        <step>
          <cmd>Open <filepath>/etc/aem-guides/config.yaml</filepath> in a text editor.</cmd>
        </step>
        <step>
          <cmd>Set the <codeph>output.format</codeph> property:</cmd>
          <info>
            <codeblock outputclass="language-yaml">
output:
  format: pdf
  baseline: latest
            </codeblock>
          </info>
        </step>
        <step>
          <cmd>Run the publish command:</cmd>
          <info>
            <codeblock><coderef href="../code/publish.sh"/></codeblock>
          </info>
        </step>
      </steps>
      <result>
        <p>The system outputs: <systemoutput>Published successfully to prod.</systemoutput></p>
      </result>
    </taskbody>
  </task>

REFERENCE template (syntax/API reference with codeph):
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">
  <reference id="{{id}}">
    <title>Real reference title</title>
    <shortdesc>API or command reference for the domain.</shortdesc>
    <refbody>
      <section><title>Syntax</title>
        <codeblock outputclass="language-bash">aem-publish [OPTIONS] --map &lt;map-file&gt;</codeblock>
      </section>
      <properties>
        <prophead><proptypehd>Option</proptypehd><propvaluehd>Type</propvaluehd><propdeschd>Description</propdeschd></prophead>
        <property>
          <proptype>string</proptype>
          <propvalue><codeph>--map</codeph></propvalue>
          <propdesc><p>Path to the root <filepath>.ditamap</filepath> file.</p></propdesc>
        </property>
        <property>
          <proptype>flag</proptype>
          <propvalue><codeph>--dry-run</codeph></propvalue>
          <propdesc><p>Validate without publishing. Default: <codeph>false</codeph>.</p></propdesc>
        </property>
      </properties>
    </refbody>
  </reference>

CODE FILE CONTENT RULES:
- Write REAL, runnable code for the domain — actual Python/Bash/XML/JSON, not pseudocode.
- Include comments explaining what the code does.
- Length: 15–40 lines per file. Enough to be meaningful, not padded.
- XML/DITA code files: include proper DOCTYPE and namespace declarations.

CRITICAL:
- <codeblock> NEVER inside <p>. Use <info>, <section>, <conbody>, <taskbody>, or <li>.
- <coderef href> path MUST be ../code/filename (one level up from topics/, into code/).
- scope="external" REQUIRED on all non-DITA href values (http/https URLs).
- XML special chars in codeblock content: use &lt; &gt; &amp; — never raw < > &.
- id attributes must exactly match the input.
- XML must be well-formed.
"""

_OUTLINE_SYSTEM_NESTED_KEYDEF = """\
You are a DITA information architect designing a nested-map key-resolution dataset.

This dataset must exercise real AEM Guides key resolution scenarios:
- Keys defined in a root map and inherited by submaps
- Keys defined in a submap that shadow the root definition within that scope
- Keyscoped submaps where the same key name exists in multiple scopes
- Topics that use cross-scope keyref syntax (scope-name.key-name)
- A key conflict where two submaps define the same key differently

Output ONLY a valid JSON object:
{{
  "root_map_title": "string",
  "root_keys": [
    {{"key": "string", "keyword_value": "string", "description": "purpose of this key"}}
  ],
  "submaps": [
    {{
      "id": "sm001",
      "filename": "submaps/module-name.ditamap",
      "title": "string",
      "keyscope": "scope-name",
      "local_keys": [
        {{"key": "string", "keyword_value": "string", "shadows_root": true}},
        {{"key": "string", "keyword_value": "string", "shadows_root": false}}
      ],
      "topics": [
        {{"id": "t001", "title": "string", "type": "concept|task|reference",
          "uses_root_keys": ["key1"],
          "uses_local_keys": ["key2"],
          "uses_cross_scope_keys": [{{"scope": "other-scope-name", "key": "key3"}}]}}
      ]
    }}
  ]
}}

Rules:
- root_keys: 3–6 globally shared keys (e.g. product-name, version, support-url, company-name).
- submaps: 2–3 submaps, each with a unique keyscope name.
- Each submap: 2–4 local keys; at least ONE must shadow a root key (same key name, different value).
- At least ONE topic must use a cross-scope keyref to access a key in a sibling submap.
- Topics total across all submaps: {limit}. Use real domain-specific titles.
- The key conflict scenario: same key name in two different submaps with different values — topics from each submap see their own local definition.
"""

_FILL_SYSTEM_NESTED_KEYDEF = """\
You are a DITA 1.3 XML author generating a nested-map keydef dataset.

Output ONLY a valid JSON object:
{{
  "root_map_xml": "...full root DITA map XML...",
  "submap_files": [
    {{"filename": "submaps/module.ditamap", "xml": "...full submap DITA map XML..."}}
  ],
  "topic_files": [
    {{"id": "t001", "filename": "topics/topic-001.dita", "xml": "...full DITA topic XML..."}}
  ]
}}

KEY RESOLUTION RULES IN DITA 1.3:
1. Root map keys are the baseline — visible to all topics in all submaps.
2. A submap with keyscope="install" creates a key namespace. Keys inside that scope are
   referenced from outside as: install.key-name (scope-prefix + "." + key-name).
3. If a submap defines the same key name as the root map, the submap definition SHADOWS
   the root within that scope. Topics inside the scoped submap see the local value.
4. Cross-scope keyref syntax: <keyword keyref="install.product-name"/> — resolves to the
   "product-name" key in the "install" keyscope.
5. From OUTSIDE a keyscope, use scoped reference: keyref="scopeName.keyName".
   From INSIDE a keyscope, unscoped keyref="keyName" resolves locally first, then root.

ROOT MAP TEMPLATE:
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
  <map>
    <title>Root Map Title</title>
    <!-- Root-level keys: visible globally unless shadowed by a keyscope -->
    <keydef keys="product-name"><topicmeta><keywords><keyword>Real Product Name</keyword></keywords></topicmeta></keydef>
    <keydef keys="version-num"><topicmeta><keywords><keyword>4.6</keyword></keywords></topicmeta></keydef>
    <keydef keys="support-url" href="https://helpx.adobe.com/support.html" format="html" scope="external"/>
    <!-- Submaps — each defines a keyscope to namespace its keys -->
    <mapref href="submaps/installation.ditamap" keyscope="install"/>
    <mapref href="submaps/configuration.ditamap" keyscope="config"/>
    <!-- Root-level topic (no keyscope, sees root keys directly) -->
    <topicref href="topics/overview.dita"/>
  </map>

SUBMAP TEMPLATE (installation.ditamap):
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
  <map>
    <title>Installation Guide</title>
    <!-- Shadow root "product-name" with installation-specific value inside this scope -->
    <keydef keys="product-name"><topicmeta><keywords><keyword>AEM Guides Installer</keyword></keywords></topicmeta></keydef>
    <!-- Local keys — only available as install.install-dir from outside this scope -->
    <keydef keys="install-dir"><topicmeta><keywords><keyword>/opt/aem-guides</keyword></keywords></topicmeta></keydef>
    <keydef keys="prereq-link" href="topics/prereqs.dita" format="dita"/>
    <topicref href="../topics/install-prereqs.dita"/>
    <topicref href="../topics/run-installer.dita"/>
  </map>

TOPIC USING ROOT + LOCAL + CROSS-SCOPE KEYS:
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
  <concept id="t001">
    <title>Installation Overview</title>
    <shortdesc>How to install <keyword keyref="product-name"/> on your system.</shortdesc>
    <conbody>
      <!-- Unscoped: resolves to local "product-name" shadow (install scope overrides root) -->
      <p>Install <keyword keyref="product-name"/> to directory <keyword keyref="install-dir"/>.</p>
      <!-- Cross-scope: access a key from the sibling "config" keyscope -->
      <p>After installation, configure using the default file at <keyword keyref="config.config-file"/>.</p>
      <!-- Root key (no shadow in this scope): resolves from root map -->
      <p>Contact <xref keyref="support-url">support</xref> if issues arise.</p>
    </conbody>
  </concept>

DTD STRUCTURE RULES:
- In topic body: <keyword keyref="name"/> is INLINE in <p>, <cmd>, <title> — NEVER wrap in <keywords> in body
- <keywords><keyword>...</keyword></keywords> belongs ONLY in keydef <topicmeta> or topic <prolog><metadata>
- WRONG (DTD violation): <body><keywords><keyword>v1</keyword></keywords></body>
- CORRECT (inline): <body><p>Version <keyword keyref="version-num"/>.</p></body>
- Root map MUST use <mapref href="submaps/filename.ditamap" keyscope="scope-name"/>.
- Submap topics use RELATIVE href: ../topics/filename.dita (submap is one level deeper).
- Root-level topics use: topics/filename.dita (relative to root map).
- Shadow scenario: submap defines same key name as root — topic inside that submap sees the submap value.
- Cross-scope scenario: at least one topic uses keyref="otherscope.keyname" to access a sibling submap's key.
- Conflict demo: same key name in two submaps — each submap's topics see its own value.
- XML must be well-formed. id attributes must exactly match input.
"""

_OUTLINE_SYSTEM_CONREF = """\
You are a DITA information architect designing a content-reuse dataset.

Output ONLY a valid JSON object:
{{
  "map_title": "string",
  "source_topics": [
    {{"id": "src001", "title": "string", "elements": ["elem_id_1", "elem_id_2"]}}
  ],
  "consumer_topics": [
    {{"id": "con001", "title": "string", "type": "task|concept|reference",
       "conrefs": [{{"source_topic_id": "src001", "element_id": "elem_id_1"}}]}}
  ]
}}

Rules:
- source_topics: 2–4 reusable library topics. Each has 2–4 named element IDs (e.g. "prereq-note", "warning-caution").
- consumer_topics: {limit} topics (task/concept/reference) that reuse content via @conref.
- Use real, domain-specific titles. NEVER use "Topic 1" placeholders.
- Each consumer topic conrefs at least one element from a source topic.
- Produce at least 5 consumer topics total.
"""

_FILL_SYSTEM_CONREF = """\
You are a DITA 1.3 XML author generating a conref dataset.
All topics live in the same "topics/" directory, so conref paths are relative within that folder.

Output ONLY a valid JSON array — no markdown, no explanation:
[
  {{"id": "t001", "filename": "topic-001.dita", "xml": "...full DITA XML..."}},
  ...
]

SOURCE TOPICS — contain @id'd elements that others will reuse:
  <!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
  <topic id="{{id}}">
    <title>Real reusable content title</title>
    <body>
      <p id="prereq-note">Real prerequisite text for the domain.</p>
      <note id="warning-caution" type="caution">Real caution text.</note>
      <section id="common-steps"><title>Common Steps</title><p>Shared step content.</p></section>
    </body>
  </topic>

CONSUMER TOPICS — use @conref to reference source elements.
  Conref syntax: conref="<relative-filename>#<topic-id>/<element-id>"
  Example: if this topic is "topics/consumer.dita" and source is "topics/library.dita", topicid="lib001":
    <p conref="library.dita#lib001/prereq-note"/>
  The @conref attribute uses a RELATIVE path from consumer to source (they're in same folder, so no path prefix).

  <!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">
  <task id="{{id}}">
    <title>Real task title</title>
    <shortdesc>One sentence.</shortdesc>
    <taskbody>
      <prereq><p conref="library.dita#lib001/prereq-note"/></prereq>
      <steps>
        <step><cmd>Real command.</cmd></step>
      </steps>
    </taskbody>
  </task>

CRITICAL:
- id attributes must exactly match the input.
- @conref path must be FILENAME ONLY (no directory prefix) since all topics are siblings.
- Generate REAL domain content, never placeholders.
- XML must be well-formed.
"""

_OUTLINE_SYSTEM_KEYDEF = """\
You are a DITA information architect designing a key-definition and key-reference dataset.

Output ONLY a valid JSON object:
{{
  "map_title": "string",
  "keydefs": [
    {{"key": "string", "href": "optional-path-or-empty", "keyword": "real domain term"}}
  ],
  "topics": [
    {{"id": "t001", "title": "string", "type": "task|concept|reference",
      "uses_keys": ["key1", "key2"]}}
  ]
}}

Rules:
- keydefs: 5–15 real domain keys (e.g. "product-name", "version-num", "support-url"). Use real values.
- topics: {limit} topics that reference those keys via <keyword keyref="key-name"/> inline in body text.
- Titles must be domain-specific, never "Topic 1" style.
- IMPORTANT: <keyword keyref="..."/> goes INLINE inside <p> or <cmd> — NOT wrapped in <keywords> in body.
  The <keywords> wrapper belongs only in <prolog><metadata> or keydef <topicmeta>.
- Produce at least 5 topics.
"""

_FILL_SYSTEM_KEYDEF = """\
You are a DITA 1.3 XML author generating a keydef dataset.
The DITA map defines keys; topics use <keyword keyref="..."/> INLINE in body text.

Output ONLY a valid JSON object:
{{
  "keydef_map_xml": "...full DITA map XML with <keydef> elements...",
  "topics": [
    {{"id": "t001", "filename": "topic-001.dita", "xml": "...full DITA XML..."}}
  ]
}}

KEYDEF MAP — keyword value inside <topicmeta><keywords><keyword>:
  <keydef keys="product-name"><topicmeta><keywords><keyword>Real Product Name</keyword></keywords></topicmeta></keydef>
  <keydef keys="version-num"><topicmeta><keywords><keyword>4.6</keyword></keywords></topicmeta></keydef>

TOPIC — <keyword keyref="..."/> INLINE in <p> (NOT wrapped in <keywords> in body):
  <concept id="t001"><title>Using <keyword keyref="product-name"/></title>
    <conbody><p>Install <keyword keyref="product-name"/> version <keyword keyref="version-num"/>.</p></conbody>
  </concept>

DTD RULES (strictly follow):
1. <keyword keyref="name"/> is INLINE — valid inside <p>, <title>, <cmd>, <li>
2. <keywords><keyword>...</keyword></keywords> belongs ONLY in <keydef><topicmeta> OR <prolog><metadata>
3. NEVER place <keywords> inside <body> — DTD violation
4. Use real domain values, never placeholders like "key1" or "Real Product Name"
5. keyref values must exactly match the @keys attributes in keydef
"""

_OUTLINE_SYSTEM_GLOSSARY = """\
You are a DITA information architect designing a glossary dataset.

Output ONLY a valid JSON object:
{{
  "map_title": "string",
  "glossary_entries": [
    {{"id": "g001", "term": "string", "definition": "string", "acronym": "optional"}}
  ],
  "consumer_topics": [
    {{"id": "t001", "title": "string", "type": "task|concept|reference"}}
  ]
}}

Rules:
- glossary_entries: {limit} real domain terms with concise definitions. Use actual terminology.
- consumer_topics: 3–5 topics that use <term> references to glossary entries.
- Entries must be real vocabulary for the domain, never "Term 1" style.
"""

_FILL_SYSTEM_GLOSSARY = """\
You are a DITA 1.3 XML author generating a glossary dataset.

Output ONLY a valid JSON array:
[
  {{"id": "g001", "filename": "glossentry-001.dita", "xml": "...glossentry DITA XML..."}},
  {{"id": "t001", "filename": "topic-001.dita", "xml": "...topic DITA XML using <term>..."}}
]

GLOSSENTRY template:
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE glossentry PUBLIC "-//OASIS//DTD DITA Glossary Entry//EN" "glossentry.dtd">
  <glossentry id="{{id}}">
    <glossterm>Real Term</glossterm>
    <glossdef>Concise, accurate definition.</glossdef>
  </glossentry>

TOPIC using glossary terms (via <term> with keyref when glossary is keyed):
  <concept id="{{id}}">
    <title>Real title</title>
    <conbody>
      <p>A <term>Real Term</term> is used when...</p>
    </conbody>
  </concept>

CRITICAL:
- REAL definitions — never "Definition for Term 1".
- XML must be well-formed.
"""

_OUTLINE_SYSTEM_MATHML = """\
You are a DITA information architect designing a MathML equation dataset for AEM Guides.

Output ONLY a valid JSON object:
{{
  "map_title": "string",
  "topics": [
    {{
      "id": "t001",
      "title": "string",
      "type": "concept|reference|task",
      "equation_count": 2,
      "equation_types": ["fraction", "superscript"]
    }}
  ]
}}

Rules:
- topics: {limit} topics mixing concept (explain formula), reference (formula tables), task (apply formula).
- equation_count: 1–4 equations per topic. Be specific about equation types.
- equation_types: any combination of: simple_arithmetic, superscript, subscript, fraction, sqrt,
  nested_fraction, summation, integral, matrix, radical, binomial, limit, product, logarithm.
- Titles must be domain-specific and descriptive: "Quadratic Formula for Root Finding", not "Topic 1".
- Produce at least 5 topics.
"""

_FILL_SYSTEM_MATHML = """\
You are a DITA 1.3 XML author generating AEM Guides MathML equation content.

Output ONLY a valid JSON array — no markdown fences, no explanation:
[
  {{"id": "t001", "filename": "topic-001.dita", "xml": "...full DITA XML with MathML..."}},
  ...
]

AEM GUIDES MATHML RULES (CRITICAL — violations cause DTD errors):
1. ALWAYS use the m: namespace prefix on ALL MathML elements: m:math, m:mrow, m:mi, m:mo,
   m:mn, m:msup, m:msub, m:mfrac, m:msqrt, m:mtable, m:mtr, m:mtd, m:mtext, m:mover,
   m:munder, m:munderover, m:mroot, m:mspace, m:mfenced, m:menclose, m:msqrt.
   NEVER write unprefixed <math>, <mrow>, <mi>, etc.
2. Block equations: wrap in <equation-block><mathml>...</mathml></equation-block>
   NEVER place <equation-block> inside a <p> element.
   Valid parents: <body>, <section>, <conbody>, <taskbody>.
3. Inline equations: wrap in <equation-inline><mathml>...</mathml></equation-inline>
   Inline CAN appear inside <p>.
4. The m:math root element must declare the namespace:
   <m:math xmlns:m="http://www.w3.org/1998/Math/MathML" display="block">
   For inline: display="inline"
5. Every equation must have real mathematical content — not placeholder symbols.

EQUATION EXAMPLES by type:
  Fraction:     <m:mfrac><m:mi>a</m:mi><m:mi>b</m:mi></m:mfrac>
  Superscript:  <m:msup><m:mi>x</m:mi><m:mn>2</m:mn></m:msup>
  Subscript:    <m:msub><m:mi>x</m:mi><m:mn>0</m:mn></m:msub>
  Sqrt:         <m:msqrt><m:mi>x</m:mi></m:msqrt>
  Summation:    <m:munderover><m:mo>&#x2211;</m:mo><m:mrow><m:mi>i</m:mi><m:mo>=</m:mo><m:mn>1</m:mn></m:mrow><m:mi>n</m:mi></m:munderover>
  Matrix (2x2): <m:mtable><m:mtr><m:mtd><m:mi>a</m:mi></m:mtd><m:mtd><m:mi>b</m:mi></m:mtd></m:mtr><m:mtr><m:mtd><m:mi>c</m:mi></m:mtd><m:mtd><m:mi>d</m:mi></m:mtd></m:mtr></m:mtable>

CONCEPT template with equation-block:
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
  <concept id="{{id}}">
    <title>Real concept title</title>
    <shortdesc>One sentence explaining the mathematical concept.</shortdesc>
    <conbody>
      <p>Introductory paragraph explaining context.</p>
      <equation-block>
        <mathml>
          <m:math xmlns:m="http://www.w3.org/1998/Math/MathML" display="block">
            <m:mrow>
              <!-- real equation here, fully formed -->
            </m:mrow>
          </m:math>
        </mathml>
      </equation-block>
      <p>Explanation of the equation terms using <equation-inline><mathml><m:math xmlns:m="http://www.w3.org/1998/Math/MathML" display="inline"><m:mi>x</m:mi></m:math></mathml></equation-inline> as variable.</p>
    </conbody>
  </concept>

REFERENCE template with equation table:
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">
  <reference id="{{id}}">
    <title>Real reference title</title>
    <shortdesc>Formula reference for the domain.</shortdesc>
    <refbody>
      <section><title>Formula</title>
        <equation-block>
          <mathml>
            <m:math xmlns:m="http://www.w3.org/1998/Math/MathML" display="block">
              <m:mrow><!-- real equation --></m:mrow>
            </m:math>
          </mathml>
        </equation-block>
      </section>
      <properties>
        <prophead><proptypehd>Variable</proptypehd><propvaluehd>Symbol</propvaluehd><propdeschd>Description</propdeschd></prophead>
        <property><proptype>independent</proptype><propvalue>x</propvalue><propdesc><p>Real variable description.</p></propdesc></property>
      </properties>
    </refbody>
  </reference>

TASK template with equation steps:
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">
  <task id="{{id}}">
    <title>Real procedure title involving calculation</title>
    <shortdesc>Steps to apply the formula.</shortdesc>
    <taskbody>
      <context><p>When to apply this formula.</p></context>
      <steps>
        <step><cmd>Identify variables: <equation-inline><mathml><m:math xmlns:m="http://www.w3.org/1998/Math/MathML" display="inline"><m:mi>x</m:mi></m:math></mathml></equation-inline>.</cmd></step>
        <step><cmd>Apply the formula:</cmd>
          <info>
            <equation-block>
              <mathml>
                <m:math xmlns:m="http://www.w3.org/1998/Math/MathML" display="block">
                  <m:mrow><!-- real equation --></m:mrow>
                </m:math>
              </mathml>
            </equation-block>
          </info>
        </step>
      </steps>
    </taskbody>
  </task>

CRITICAL:
- Every equation must be mathematically correct and domain-appropriate.
- NEVER omit the m: prefix. NEVER write bare <math> or <mrow>.
- NEVER place <equation-block> inside <p>.
- id attributes must exactly match the input.
- XML must be well-formed.
"""

_OUTLINE_SYSTEM = """\
You are a DITA information architect. Given a user's content request, produce a structured topic outline.

Output ONLY a valid JSON object — no markdown fences, no explanation:
{{
  "map_title": "string",
  "topics": [
    {{
      "id": "t001",
      "title": "string",
      "type": "reference|concept|task",
      "subtopics": []
    }}
  ]
}}

Rules:
- Use real, domain-specific titles. NEVER use placeholders like "Topic 1", "Setting 1", "Option A".
- reference: one topic per resource/API attribute/element (e.g. aws_s3_bucket, kubectl apply)
- task: one topic per procedure or workflow (e.g. "Create an S3 Bucket", "Configure IAM Role")
- concept: one topic per principle or architecture concept (e.g. "IAM Permission Model")
- Nest subtopics where meaningful (max 2 levels deep)
- Total topics including all subtopics must not exceed {limit}
- Produce at least 5 topics
"""

_FILL_SYSTEM = """\
You are a DITA 1.3 XML author. Generate production-quality DITA XML for each topic.

Output ONLY a valid JSON array — no markdown fences, no explanation:
[
  {{"id": "t001", "xml": "<?xml version=\\"1.0\\" encoding=\\"UTF-8\\"?>...full DITA XML..."}},
  ...
]

Templates per topic type:

REFERENCE — real field/attribute documentation:
  DOCTYPE: <!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">
  <reference id="{{id}}">
    <title>Real title</title>
    <shortdesc>One sentence.</shortdesc>
    <refbody>
      <properties>
        <prophead><proptypehd>Type</proptypehd><propvaluehd>Value/Default</propvaluehd><propdeschd>Description</propdeschd></prophead>
        <property><proptype>string</proptype><propvalue>actual_field_name</propvalue><propdesc><p>Real description.</p></propdesc></property>
        <!-- at least 3 properties with real field names and descriptions -->
      </properties>
      <simpletable relcolwidth="1* 3*">
        <sthead><stentry>Attribute</stentry><stentry>Notes</stentry></sthead>
        <strow><stentry>real_attr</stentry><stentry>Real notes.</stentry></strow>
      </simpletable>
    </refbody>
  </reference>

TASK — real step-by-step procedure:
  DOCTYPE: <!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">
  <task id="{{id}}">
    <title>Real procedure title</title>
    <shortdesc>What this accomplishes.</shortdesc>
    <taskbody>
      <prereq><p>Any prerequisites.</p></prereq>
      <steps>
        <step><cmd>Real command or action.</cmd><info><p>Context.</p></info></step>
        <!-- at least 3 real steps -->
      </steps>
      <result><p>What the user achieves.</p></result>
    </taskbody>
  </task>

CONCEPT — real explanatory content:
  DOCTYPE: <!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
  <concept id="{{id}}">
    <title>Real concept title</title>
    <shortdesc>One sentence definition.</shortdesc>
    <conbody>
      <p>Real explanation paragraph.</p>
      <ul><li>Real point 1</li><li>Real point 2</li></ul>
    </conbody>
  </concept>

CRITICAL:
- Use REAL content — actual field names, real CLI commands, accurate descriptions
- NEVER use placeholders: "Option 1", "Description for option 1", "setting.1", "Value1"
- The id attribute must exactly match the id in the input
- XML must be well-formed
"""


async def run_freeform_generation(
    prompt: str,
    jira_id: str,
    run_id: str,
    scenario_dir: Path,
    trace_id: str,
    topic_limit: int = 20,
) -> dict[str, Any]:
    """
    Phase 1: LLM produces a topic outline (titles, types, hierarchy).
    Phase 2: LLM fills each topic with real DITA XML in batches of 10.
    Writes files to scenario_dir. Returns an exec_result-compatible dict.

    Advanced modes are auto-detected from prompt keywords:
    - conref/conkeyref/keydef/glossary → specialized outline + fill prompts.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return {"error": "prompt is required", "recipes_executed": [], "warnings": ["No prompt provided"]}

    topic_limit = max(5, min(topic_limit, 50))
    dita_mode = _detect_dita_mode(prompt)

    if dita_mode == "mathml":
        return await _run_freeform_mathml(prompt, jira_id, scenario_dir, trace_id, topic_limit)
    if dita_mode == "bookmap":
        return await _run_freeform_bookmap(prompt, jira_id, scenario_dir, trace_id, topic_limit)
    if dita_mode == "profiling":
        return await _run_freeform_profiling(prompt, jira_id, scenario_dir, trace_id, topic_limit)
    if dita_mode == "reltable":
        return await _run_freeform_reltable(prompt, jira_id, scenario_dir, trace_id, topic_limit)
    if dita_mode == "table_domain":
        return await _run_freeform_table_domain(prompt, jira_id, scenario_dir, trace_id, topic_limit)
    if dita_mode == "code_domain":
        return await _run_freeform_code_domain(prompt, jira_id, scenario_dir, trace_id, topic_limit)
    if dita_mode == "nested_keydef":
        return await _run_freeform_nested_keydef(prompt, jira_id, scenario_dir, trace_id, topic_limit)
    if dita_mode in ("conref", "conkeyref"):
        return await _run_freeform_conref(prompt, jira_id, scenario_dir, trace_id, topic_limit)
    if dita_mode == "keydef":
        return await _run_freeform_keydef(prompt, jira_id, scenario_dir, trace_id, topic_limit)
    if dita_mode == "glossary":
        return await _run_freeform_glossary(prompt, jira_id, scenario_dir, trace_id, topic_limit)

    # ── Default: standard topic generation ───────────────────────────────
    # ── Phase 1: Outline ──────────────────────────────────────────────────
    logger.info_structured("freeform_outline_start", extra_fields={"jira_id": jira_id, "limit": topic_limit})
    try:
        outline = await generate_json(
            system_prompt=_OUTLINE_SYSTEM.format(limit=topic_limit),
            user_prompt=f"Generate a DITA topic outline for:\n\n{prompt}",
            max_tokens=3000,
            step_name="freeform_outline",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        logger.warning_structured("freeform_outline_failed", extra_fields={"error": str(exc)})
        return {"error": f"Outline phase failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    flat_topics = _flatten_topics(outline.get("topics") or [])[:topic_limit]
    map_title = str(outline.get("map_title") or "Generated DITA Dataset").strip()

    if not flat_topics:
        return {"error": "LLM returned empty topic list", "recipes_executed": [], "warnings": ["outline empty"]}

    logger.info_structured("freeform_outline_done", extra_fields={"count": len(flat_topics), "title": map_title})

    # ── Phase 2: Fill topics in batches of 10 ─────────────────────────────
    BATCH_SIZE = 10
    filled: dict[str, str] = {}  # id → xml

    for batch_start in range(0, len(flat_topics), BATCH_SIZE):
        batch = flat_topics[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        logger.info_structured("freeform_fill_batch", extra_fields={"batch": batch_num, "size": len(batch)})
        try:
            raw = await generate_json(
                system_prompt=_FILL_SYSTEM,
                user_prompt=(
                    f"Domain context: {prompt}\n\n"
                    f"Generate DITA XML for these {len(batch)} topics:\n"
                    + json.dumps(batch, indent=2)
                ),
                max_tokens=12000,
                step_name=f"freeform_fill_{batch_num}",
                trace_id=trace_id,
                jira_id=jira_id,
            )
        except Exception as exc:
            logger.warning_structured("freeform_fill_failed", extra_fields={"batch": batch_num, "error": str(exc)})
            continue

        items = raw if isinstance(raw, list) else (raw.get("topics") or [])
        for item in items:
            if isinstance(item, dict) and item.get("id") and item.get("xml"):
                filled[item["id"]] = item["xml"]

    # ── Phase 3: Write files ──────────────────────────────────────────────
    topics_dir = scenario_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)

    written: list[tuple[str, str, str]] = []  # (id, filename, type)
    for topic in flat_topics:
        tid = topic["id"]
        xml = filled.get(tid, "")
        if not xml:
            logger.warning_structured("freeform_topic_missing", extra_fields={"id": tid})
            continue
        fname = f"{tid}_{_slugify(topic['title'])}.dita"
        (topics_dir / fname).write_text(xml, encoding="utf-8")
        written.append((tid, fname, topic.get("type", "reference")))

    if not written:
        return {"error": "No topics were produced by LLM", "recipes_executed": [], "warnings": ["All fill batches failed"]}

    # ── Phase 4: DITA map ─────────────────────────────────────────────────
    (scenario_dir / "generated.ditamap").write_text(_build_ditamap(map_title, written), encoding="utf-8")

    logger.info_structured("freeform_done", extra_fields={"written": len(written), "title": map_title})

    return {
        "recipes_executed": ["freeform_llm"],
        "generate_mode": "freeform",
        "topic_count": len(written),
        "map_title": map_title,
        "warnings": [],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _flatten_topics(topics: list, depth: int = 0) -> list[dict]:
    result: list[dict] = []
    for t in (topics or []):
        result.append({
            "id": str(t.get("id") or f"t{len(result)+1:03d}").strip(),
            "title": str(t.get("title") or "Untitled").strip(),
            "type": str(t.get("type") or "reference").strip().lower(),
        })
        if depth < 1 and t.get("subtopics"):
            result.extend(_flatten_topics(t["subtopics"], depth=depth + 1))
    return result


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").lower()).strip("_")[:40]


def _build_ditamap(title: str, topics: list[tuple[str, str, str]]) -> str:
    safe = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    refs = "\n  ".join(f'<topicref href="topics/{fname}"/>' for (_, fname, _) in topics)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">\n'
        f"<map>\n  <title>{safe}</title>\n  {refs}\n</map>\n"
    )


# ── Advanced mode generators ──────────────────────────────────────────────────

async def _run_freeform_conref(
    prompt: str,
    jira_id: str,
    scenario_dir: Path,
    trace_id: str,
    topic_limit: int,
) -> dict[str, Any]:
    """Generate a conref dataset: library source topics + consumer topics with correct relative @conref paths."""
    logger.info_structured("freeform_conref_start", extra_fields={"jira_id": jira_id})
    try:
        outline = await generate_json(
            system_prompt=_OUTLINE_SYSTEM_CONREF.format(limit=topic_limit),
            user_prompt=f"Design a conref dataset for:\n\n{prompt}",
            max_tokens=3000,
            step_name="freeform_conref_outline",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        return {"error": f"Conref outline failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    source_topics = outline.get("source_topics") or []
    consumer_topics = outline.get("consumer_topics") or []
    map_title = str(outline.get("map_title") or "Conref Dataset").strip()

    # Build a lookup of source_topic_id → assigned filename so the fill prompt can reference them
    src_filenames: dict[str, str] = {}
    for i, src in enumerate(source_topics, 1):
        sid = str(src.get("id") or f"src{i:03d}").strip()
        fname = f"{sid}_{_slugify(str(src.get('title') or sid))}.dita"
        src_filenames[sid] = fname

    all_topics = (
        [{"id": t.get("id"), "title": t.get("title"), "type": "topic", "role": "source",
          "elements": t.get("elements", []), "filename": src_filenames.get(str(t.get("id") or ""))}
         for t in source_topics]
        + [{"id": t.get("id"), "title": t.get("title"), "type": t.get("type", "task"), "role": "consumer",
            "conrefs": t.get("conrefs", []),
            "source_filenames": {c["source_topic_id"]: src_filenames.get(c["source_topic_id"], "")
                                 for c in t.get("conrefs", []) if isinstance(c, dict)}}
           for t in consumer_topics]
    )

    BATCH_SIZE = 8
    filled: dict[str, dict] = {}  # id → {filename, xml}

    for batch_start in range(0, len(all_topics), BATCH_SIZE):
        batch = all_topics[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        try:
            raw = await generate_json(
                system_prompt=_FILL_SYSTEM_CONREF,
                user_prompt=(
                    f"Domain: {prompt}\n\n"
                    f"Source topic filenames: {json.dumps(src_filenames)}\n\n"
                    f"Generate DITA XML for these {len(batch)} topics:\n"
                    + json.dumps(batch, indent=2)
                ),
                max_tokens=12000,
                step_name=f"freeform_conref_fill_{batch_num}",
                trace_id=trace_id,
                jira_id=jira_id,
            )
        except Exception as exc:
            logger.warning_structured("freeform_conref_fill_failed", extra_fields={"batch": batch_num, "error": str(exc)})
            continue
        items = raw if isinstance(raw, list) else (raw.get("topics") or [])
        for item in items:
            if isinstance(item, dict) and item.get("id") and item.get("xml"):
                filled[item["id"]] = {"filename": str(item.get("filename") or f"{item['id']}.dita"), "xml": item["xml"]}

    topics_dir = scenario_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)

    written: list[tuple[str, str, str]] = []
    for t in all_topics:
        tid = str(t.get("id") or "")
        f_info = filled.get(tid)
        if not f_info:
            continue
        fname = f_info["filename"]
        (topics_dir / fname).write_text(f_info["xml"], encoding="utf-8")
        written.append((tid, fname, t.get("type", "topic")))

    if not written:
        return {"error": "No conref topics produced", "recipes_executed": [], "warnings": ["All fill batches failed"]}

    (scenario_dir / "generated.ditamap").write_text(_build_ditamap(map_title, written), encoding="utf-8")
    logger.info_structured("freeform_conref_done", extra_fields={"written": len(written)})
    return {"recipes_executed": ["freeform_conref"], "generate_mode": "freeform_conref",
            "topic_count": len(written), "map_title": map_title, "warnings": []}


async def _run_freeform_keydef(
    prompt: str,
    jira_id: str,
    scenario_dir: Path,
    trace_id: str,
    topic_limit: int,
) -> dict[str, Any]:
    """Generate a keydef dataset: a keydef DITA map + topics using @keyref/@conkeyref."""
    logger.info_structured("freeform_keydef_start", extra_fields={"jira_id": jira_id})
    try:
        outline = await generate_json(
            system_prompt=_OUTLINE_SYSTEM_KEYDEF.format(limit=topic_limit),
            user_prompt=f"Design a keydef dataset for:\n\n{prompt}",
            max_tokens=3000,
            step_name="freeform_keydef_outline",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        return {"error": f"Keydef outline failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    flat_topics = _flatten_topics(outline.get("topics") or [])[:min(topic_limit, 5)]  # cap at 5 for fill budget
    keydefs = (outline.get("keydefs") or [])[:10]  # cap keydefs too
    map_title = str(outline.get("map_title") or "Keydef Dataset").strip()

    try:
        raw = await generate_json(
            system_prompt=_FILL_SYSTEM_KEYDEF,
            user_prompt=(
                f"Domain: {prompt[:400]}\n\nKeydefs: {json.dumps(keydefs)}\n\n"
                f"Topics to generate:\n" + json.dumps(flat_topics, indent=2)
            ),
            max_tokens=6000,
            step_name="freeform_keydef_fill",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        return {"error": f"Keydef fill failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    topics_dir = scenario_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)

    keydef_map_xml = raw.get("keydef_map_xml") if isinstance(raw, dict) else None
    topic_items = (raw.get("topics") or []) if isinstance(raw, dict) else []

    written: list[tuple[str, str, str]] = []
    for item in topic_items:
        if not isinstance(item, dict) or not item.get("id") or not item.get("xml"):
            continue
        fname = str(item.get("filename") or f"{item['id']}.dita")
        xml_out = _sanitize_keywords_in_body(item["xml"])
        (topics_dir / fname).write_text(xml_out, encoding="utf-8")
        written.append((item["id"], fname, "topic"))

    if not written:
        return {"error": "No keydef topics produced", "recipes_executed": [], "warnings": ["fill failed"]}

    if keydef_map_xml:
        (scenario_dir / "generated.ditamap").write_text(keydef_map_xml, encoding="utf-8")
    else:
        (scenario_dir / "generated.ditamap").write_text(_build_ditamap(map_title, written), encoding="utf-8")

    logger.info_structured("freeform_keydef_done", extra_fields={"written": len(written), "keydefs": len(keydefs)})
    return {"recipes_executed": ["freeform_keydef"], "generate_mode": "freeform_keydef",
            "topic_count": len(written), "map_title": map_title, "warnings": []}


async def _run_freeform_glossary(
    prompt: str,
    jira_id: str,
    scenario_dir: Path,
    trace_id: str,
    topic_limit: int,
) -> dict[str, Any]:
    """Generate a glossary dataset: glossentry topics + consuming topics with <term> references."""
    logger.info_structured("freeform_glossary_start", extra_fields={"jira_id": jira_id})
    entry_limit = max(5, min(topic_limit, 30))
    try:
        outline = await generate_json(
            system_prompt=_OUTLINE_SYSTEM_GLOSSARY.format(limit=entry_limit),
            user_prompt=f"Design a glossary dataset for:\n\n{prompt}",
            max_tokens=3000,
            step_name="freeform_glossary_outline",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        return {"error": f"Glossary outline failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    entries = (outline.get("glossary_entries") or [])[:entry_limit]
    consumer_topics = outline.get("consumer_topics") or []
    map_title = str(outline.get("map_title") or "Glossary Dataset").strip()
    all_items = [{"id": e.get("id"), "title": e.get("term"), "type": "glossentry",
                  "term": e.get("term"), "definition": e.get("definition"), "acronym": e.get("acronym")}
                 for e in entries] + list(_flatten_topics(consumer_topics))

    BATCH_SIZE = 10
    filled: dict[str, dict] = {}
    for batch_start in range(0, len(all_items), BATCH_SIZE):
        batch = all_items[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        try:
            raw = await generate_json(
                system_prompt=_FILL_SYSTEM_GLOSSARY,
                user_prompt=(f"Domain: {prompt}\n\nGenerate DITA XML:\n" + json.dumps(batch, indent=2)),
                max_tokens=12000,
                step_name=f"freeform_glossary_fill_{batch_num}",
                trace_id=trace_id,
                jira_id=jira_id,
            )
        except Exception as exc:
            logger.warning_structured("freeform_glossary_fill_failed", extra_fields={"error": str(exc)})
            continue
        items = raw if isinstance(raw, list) else (raw.get("topics") or [])
        for item in items:
            if isinstance(item, dict) and item.get("id") and item.get("xml"):
                filled[item["id"]] = {"filename": str(item.get("filename") or f"{item['id']}.dita"), "xml": item["xml"]}

    topics_dir = scenario_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, str, str]] = []
    for t in all_items:
        tid = str(t.get("id") or "")
        f_info = filled.get(tid)
        if not f_info:
            continue
        fname = f_info["filename"]
        (topics_dir / fname).write_text(f_info["xml"], encoding="utf-8")
        written.append((tid, fname, t.get("type", "glossentry")))

    if not written:
        return {"error": "No glossary topics produced", "recipes_executed": [], "warnings": ["fill failed"]}

    (scenario_dir / "generated.ditamap").write_text(_build_ditamap(map_title, written), encoding="utf-8")
    logger.info_structured("freeform_glossary_done", extra_fields={"written": len(written)})
    return {"recipes_executed": ["freeform_glossary"], "generate_mode": "freeform_glossary",
            "topic_count": len(written), "map_title": map_title, "warnings": []}


async def _run_freeform_mathml(
    prompt: str,
    jira_id: str,
    scenario_dir: Path,
    trace_id: str,
    topic_limit: int,
) -> dict[str, Any]:
    """Generate MathML equation dataset for AEM Guides.

    Produces concept/reference/task topics with correct AEM Guides MathML structure:
    <equation-block><mathml><m:math xmlns:m="..."> using m: prefix throughout.
    """
    logger.info_structured("freeform_mathml_start", extra_fields={"jira_id": jira_id})

    # Phase 1: Outline — plan topics with equation types
    try:
        outline = await generate_json(
            system_prompt=_OUTLINE_SYSTEM_MATHML.format(limit=topic_limit),
            user_prompt=f"Design a MathML equation DITA dataset for:\n\n{prompt}",
            max_tokens=3000,
            step_name="freeform_mathml_outline",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        logger.warning_structured("freeform_mathml_outline_failed", extra_fields={"error": str(exc)})
        return {"error": f"MathML outline failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    flat_topics = _flatten_topics(outline.get("topics") or [])[:topic_limit]
    map_title = str(outline.get("map_title") or "MathML Equation Dataset").strip()

    if not flat_topics:
        return {"error": "LLM returned empty topic list", "recipes_executed": [], "warnings": ["outline empty"]}

    logger.info_structured("freeform_mathml_outline_done", extra_fields={"count": len(flat_topics), "title": map_title})

    # Attach equation metadata back to flattened topics for the fill prompt
    outline_by_id = {str(t.get("id") or ""): t for t in (outline.get("topics") or [])}
    for t in flat_topics:
        meta = outline_by_id.get(t["id"], {})
        t["equation_count"] = meta.get("equation_count", 2)
        t["equation_types"] = meta.get("equation_types", ["fraction", "superscript"])

    # Phase 2: Fill topics in batches — smaller batch (6) to stay within token limits
    # because MathML XML is significantly longer than plain DITA
    BATCH_SIZE = 6
    filled: dict[str, dict] = {}  # id → {filename, xml}

    for batch_start in range(0, len(flat_topics), BATCH_SIZE):
        batch = flat_topics[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        logger.info_structured("freeform_mathml_fill_batch", extra_fields={"batch": batch_num, "size": len(batch)})
        try:
            raw = await generate_json(
                system_prompt=_FILL_SYSTEM_MATHML,
                user_prompt=(
                    f"Domain context: {prompt}\n\n"
                    f"Generate AEM Guides MathML DITA XML for these {len(batch)} topics. "
                    f"Each topic MUST include the specified number and types of equations "
                    f"using correct m: prefix and equation-block/equation-inline wrappers:\n"
                    + json.dumps(batch, indent=2)
                ),
                max_tokens=14000,
                step_name=f"freeform_mathml_fill_{batch_num}",
                trace_id=trace_id,
                jira_id=jira_id,
            )
        except Exception as exc:
            logger.warning_structured("freeform_mathml_fill_failed", extra_fields={"batch": batch_num, "error": str(exc)})
            continue

        items = raw if isinstance(raw, list) else (raw.get("topics") or [])
        for item in items:
            if isinstance(item, dict) and item.get("id") and item.get("xml"):
                filled[item["id"]] = {
                    "filename": str(item.get("filename") or f"{item['id']}.dita"),
                    "xml": item["xml"],
                }

    # Phase 3: Write files
    topics_dir = scenario_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)

    written: list[tuple[str, str, str]] = []
    warnings: list[str] = []
    for topic in flat_topics:
        tid = topic["id"]
        f_info = filled.get(tid)
        if not f_info:
            logger.warning_structured("freeform_mathml_topic_missing", extra_fields={"id": tid})
            warnings.append(f"Topic {tid} not produced by LLM")
            continue
        xml = f_info["xml"]
        # Sanity check: warn if m: prefix is absent (LLM hallucinated bare <math>)
        if "<math" in xml and "m:math" not in xml:
            warnings.append(f"Topic {tid} may be missing m: namespace prefix — review output")
        fname = f_info["filename"]
        if not fname.endswith(".dita"):
            fname = f"{tid}_{_slugify(topic['title'])}.dita"
        (topics_dir / fname).write_text(xml, encoding="utf-8")
        written.append((tid, fname, topic.get("type", "concept")))

    if not written:
        return {"error": "No MathML topics produced by LLM", "recipes_executed": [], "warnings": warnings or ["All fill batches failed"]}

    # Phase 4: DITA map
    (scenario_dir / "generated.ditamap").write_text(_build_ditamap(map_title, written), encoding="utf-8")

    logger.info_structured("freeform_mathml_done", extra_fields={"written": len(written), "title": map_title})
    return {
        "recipes_executed": ["freeform_mathml"],
        "generate_mode": "freeform_mathml",
        "topic_count": len(written),
        "map_title": map_title,
        "warnings": warnings,
    }


async def _run_freeform_bookmap(
    prompt: str,
    jira_id: str,
    scenario_dir: Path,
    trace_id: str,
    topic_limit: int,
) -> dict[str, Any]:
    """Generate a bookmap publication dataset with frontmatter, chapters, appendices, backmatter."""
    logger.info_structured("freeform_bookmap_start", extra_fields={"jira_id": jira_id})
    try:
        outline = await generate_json(
            system_prompt=_OUTLINE_SYSTEM_BOOKMAP.format(limit=topic_limit),
            user_prompt=f"Design a bookmap publication for:\n\n{prompt}",
            max_tokens=3000,
            step_name="freeform_bookmap_outline",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        return {"error": f"Bookmap outline failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    book_title = str(outline.get("book_title") or "Product Guide").strip()

    # Flatten all topics from the outline for the fill prompt
    all_topics: list[dict] = []
    for t in (outline.get("frontmatter_topics") or []):
        all_topics.append({"id": t.get("id"), "title": t.get("title"), "type": "concept", "role": t.get("role", "abstract")})
    for ch in (outline.get("chapters") or []):
        if ch.get("href_topic"):
            all_topics.append({**ch["href_topic"], "role": "chapter_root"})
        for ct in (ch.get("child_topics") or []):
            all_topics.append({**ct, "role": "chapter_child"})
    for ap in (outline.get("appendices") or []):
        if ap.get("href_topic"):
            all_topics.append({**ap["href_topic"], "role": "appendix"})

    all_topics = [t for t in all_topics if t.get("id")][:topic_limit]

    try:
        raw = await generate_json(
            system_prompt=_FILL_SYSTEM_BOOKMAP,
            user_prompt=(
                f"Domain: {prompt}\n\nBook title: {book_title}\n\n"
                f"Bookmap structure: {json.dumps(outline, indent=2)}\n\n"
                f"Generate the bookmap XML and all topic files:\n"
                + json.dumps(all_topics, indent=2)
            ),
            max_tokens=16000,
            step_name="freeform_bookmap_fill",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        return {"error": f"Bookmap fill failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    warnings: list[str] = []
    topics_dir = scenario_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)

    bookmap_xml = (raw.get("bookmap_xml") or "") if isinstance(raw, dict) else ""
    if bookmap_xml:
        (scenario_dir / "generated.ditamap").write_text(bookmap_xml, encoding="utf-8")
        if "bookmap" not in bookmap_xml:
            warnings.append("generated.ditamap may not be a valid bookmap — verify DOCTYPE")
    else:
        warnings.append("LLM did not produce bookmap_xml")
        (scenario_dir / "generated.ditamap").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!DOCTYPE bookmap PUBLIC "-//OASIS//DTD DITA BookMap//EN" "bookmap.dtd">\n'
            f'<bookmap><booktitle><mainbooktitle>{book_title}</mainbooktitle></booktitle></bookmap>\n',
            encoding="utf-8",
        )

    written: list[tuple[str, str, str]] = []
    for tf in ((raw.get("topic_files") or []) if isinstance(raw, dict) else []):
        if not isinstance(tf, dict) or not tf.get("id") or not tf.get("xml"):
            continue
        fname = str(tf.get("filename") or f"{tf['id']}.dita").replace("topics/", "")
        if not fname.endswith(".dita"):
            fname = f"{fname}.dita"
        (topics_dir / fname).write_text(tf["xml"], encoding="utf-8")
        written.append((tf["id"], fname, "topic"))

    if not written:
        return {"error": "No bookmap topics produced", "recipes_executed": [], "warnings": warnings or ["fill failed"]}

    logger.info_structured("freeform_bookmap_done", extra_fields={"topics": len(written), "title": book_title})
    return {
        "recipes_executed": ["freeform_bookmap"],
        "generate_mode": "freeform_bookmap",
        "topic_count": len(written),
        "map_title": book_title,
        "warnings": warnings,
    }


async def _run_freeform_profiling(
    prompt: str,
    jira_id: str,
    scenario_dir: Path,
    trace_id: str,
    topic_limit: int,
) -> dict[str, Any]:
    """Generate a conditional-profiling dataset: topics with audience/platform/product attributes + DITAVAL files."""
    logger.info_structured("freeform_profiling_start", extra_fields={"jira_id": jira_id})
    try:
        outline = await generate_json(
            system_prompt=_OUTLINE_SYSTEM_PROFILING.format(limit=topic_limit),
            user_prompt=f"Design a conditional-profiling DITA dataset for:\n\n{prompt}",
            max_tokens=3000,
            step_name="freeform_profiling_outline",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        return {"error": f"Profiling outline failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    map_title = str(outline.get("map_title") or "Conditional Content Dataset").strip()
    ditaval_plan = outline.get("ditaval_files") or []
    flat_topics = _flatten_topics(outline.get("topics") or [])[:topic_limit]

    # Carry profiling metadata into the fill prompt
    outline_by_id = {str(t.get("id") or ""): t for t in (outline.get("topics") or [])}
    for t in flat_topics:
        meta = outline_by_id.get(t["id"], {})
        t["profiling_used"] = meta.get("profiling_used") or []

    if not flat_topics:
        return {"error": "LLM returned empty topic list", "recipes_executed": [], "warnings": ["outline empty"]}

    BATCH_SIZE = 7
    filled_topics: dict[str, dict] = {}
    ditaval_outputs: list[dict] = []
    ditaval_done = False

    for batch_start in range(0, len(flat_topics), BATCH_SIZE):
        batch = flat_topics[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        include_ditaval = not ditaval_done
        try:
            raw = await generate_json(
                system_prompt=_FILL_SYSTEM_PROFILING,
                user_prompt=(
                    f"Domain: {prompt}\n\n"
                    + (f"DITAVAL files to generate: {json.dumps(ditaval_plan)}\n\n" if include_ditaval else "")
                    + f"Profiling attributes in use: {json.dumps(outline.get('profiling_attributes') or [])}\n\n"
                    + f"Generate DITA XML for these {len(batch)} topics. Each MUST use profiling attributes "
                    + f"on body elements as specified in profiling_used:\n"
                    + json.dumps(batch, indent=2)
                ),
                max_tokens=14000,
                step_name=f"freeform_profiling_fill_{batch_num}",
                trace_id=trace_id,
                jira_id=jira_id,
            )
        except Exception as exc:
            logger.warning_structured("freeform_profiling_fill_failed", extra_fields={"batch": batch_num, "error": str(exc)})
            continue

        if isinstance(raw, dict):
            if include_ditaval and not ditaval_done:
                ditaval_outputs = raw.get("ditaval_files") or []
                ditaval_done = True
            for tf in (raw.get("topic_files") or []):
                if isinstance(tf, dict) and tf.get("id") and tf.get("xml"):
                    filled_topics[tf["id"]] = {
                        "filename": str(tf.get("filename") or f"{tf['id']}.dita"),
                        "xml": tf["xml"],
                    }

    # Write DITAVAL files
    filters_dir = scenario_dir / "filters"
    filters_dir.mkdir(parents=True, exist_ok=True)
    written_filters: list[str] = []
    for dv in ditaval_outputs:
        if not isinstance(dv, dict) or not dv.get("filename") or not dv.get("xml"):
            continue
        fname = str(dv["filename"]).replace("filters/", "")
        if not fname.endswith(".ditaval"):
            fname = f"{fname}.ditaval"
        (filters_dir / fname).write_text(dv["xml"], encoding="utf-8")
        written_filters.append(fname)

    # Fallback: write placeholder ditaval from plan if LLM omitted
    if not written_filters and ditaval_plan:
        for dv_plan in ditaval_plan:
            fname = str(dv_plan.get("filename") or "default.ditaval").replace("filters/", "")
            conditions = dv_plan.get("conditions") or []
            props = "\n  ".join(
                f'<prop att="{c["att"]}" val="{c["val"]}" action="{c["action"]}"/>'
                for c in conditions if c.get("att") and c.get("val") and c.get("action")
            )
            xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<val>\n  {props}\n</val>\n'
            (filters_dir / fname).write_text(xml, encoding="utf-8")
            written_filters.append(fname)

    # Write topics + build map
    topics_dir = scenario_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    written: list[tuple[str, str, str]] = []

    for topic in flat_topics:
        tid = topic["id"]
        f_info = filled_topics.get(tid)
        if not f_info:
            warnings.append(f"Topic {tid} ('{topic['title']}') not produced")
            continue
        xml = f_info["xml"]
        if not any(a in xml for a in ('audience=', 'platform=', 'product=', 'props=')):
            warnings.append(f"Topic {tid} has no profiling attributes — check fill output")
        fname = f_info["filename"].replace("topics/", "")
        if not fname.endswith(".dita"):
            fname = f"{tid}_{_slugify(topic['title'])}.dita"
        (topics_dir / fname).write_text(xml, encoding="utf-8")
        written.append((tid, fname, topic.get("type", "concept")))

    if not written:
        return {"error": "No profiling topics produced", "recipes_executed": [], "warnings": warnings or ["fill failed"]}

    (scenario_dir / "generated.ditamap").write_text(_build_ditamap(map_title, written), encoding="utf-8")

    logger.info_structured("freeform_profiling_done", extra_fields={
        "topics": len(written), "filters": len(written_filters), "title": map_title,
    })
    return {
        "recipes_executed": ["freeform_profiling"],
        "generate_mode": "freeform_profiling",
        "topic_count": len(written),
        "ditaval_count": len(written_filters),
        "map_title": map_title,
        "warnings": warnings,
    }


async def _run_freeform_reltable(
    prompt: str,
    jira_id: str,
    scenario_dir: Path,
    trace_id: str,
    topic_limit: int,
) -> dict[str, Any]:
    """Generate a reltable dataset: DITA map with <reltable> + topics that get Related Links sections."""
    logger.info_structured("freeform_reltable_start", extra_fields={"jira_id": jira_id})
    try:
        outline = await generate_json(
            system_prompt=_OUTLINE_SYSTEM_RELTABLE.format(limit=topic_limit),
            user_prompt=f"Design a relationship-table DITA dataset for:\n\n{prompt}",
            max_tokens=3000,
            step_name="freeform_reltable_outline",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        return {"error": f"Reltable outline failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    map_title = str(outline.get("map_title") or "Reltable Dataset").strip()
    flat_topics = _flatten_topics(outline.get("topics") or [])[:topic_limit]

    if not flat_topics:
        return {"error": "LLM returned empty topic list", "recipes_executed": [], "warnings": ["outline empty"]}

    try:
        raw = await generate_json(
            system_prompt=_FILL_SYSTEM_RELTABLE,
            user_prompt=(
                f"Domain: {prompt}\n\n"
                f"Map structure: {json.dumps(outline, indent=2)}\n\n"
                f"Generate the full DITA map (with reltable) and all topic files:\n"
                + json.dumps(flat_topics, indent=2)
            ),
            max_tokens=16000,
            step_name="freeform_reltable_fill",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        return {"error": f"Reltable fill failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    warnings: list[str] = []
    topics_dir = scenario_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)

    ditamap_xml = (raw.get("ditamap_xml") or "") if isinstance(raw, dict) else ""
    if ditamap_xml:
        (scenario_dir / "generated.ditamap").write_text(ditamap_xml, encoding="utf-8")
        if "<reltable" not in ditamap_xml:
            warnings.append("generated.ditamap has no <reltable> — verify fill output")
    else:
        warnings.append("LLM did not produce ditamap_xml with reltable")
        (scenario_dir / "generated.ditamap").write_text(_build_ditamap(map_title, []), encoding="utf-8")

    written: list[tuple[str, str, str]] = []
    for tf in ((raw.get("topic_files") or []) if isinstance(raw, dict) else []):
        if not isinstance(tf, dict) or not tf.get("id") or not tf.get("xml"):
            continue
        fname = str(tf.get("filename") or f"{tf['id']}.dita").replace("topics/", "")
        if not fname.endswith(".dita"):
            fname = f"{fname}.dita"
        (topics_dir / fname).write_text(tf["xml"], encoding="utf-8")
        written.append((tf["id"], fname, "topic"))

    if not written:
        return {"error": "No reltable topics produced", "recipes_executed": [], "warnings": warnings or ["fill failed"]}

    logger.info_structured("freeform_reltable_done", extra_fields={"topics": len(written), "title": map_title})
    return {
        "recipes_executed": ["freeform_reltable"],
        "generate_mode": "freeform_reltable",
        "topic_count": len(written),
        "map_title": map_title,
        "warnings": warnings,
    }


async def _run_freeform_table_domain(
    prompt: str,
    jira_id: str,
    scenario_dir: Path,
    trace_id: str,
    topic_limit: int,
) -> dict[str, Any]:
    """Generate complex-table topics: tgroup/colspec, col-span, row-span, multi-tgroup, simpletable."""
    logger.info_structured("freeform_table_domain_start", extra_fields={"jira_id": jira_id})
    try:
        outline = await generate_json(
            system_prompt=_OUTLINE_SYSTEM_TABLE_DOMAIN.format(limit=topic_limit),
            user_prompt=f"Design a complex-table DITA dataset for:\n\n{prompt}",
            max_tokens=3000,
            step_name="freeform_table_domain_outline",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        return {"error": f"Table domain outline failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    map_title = str(outline.get("map_title") or "Complex Table Dataset").strip()
    flat_topics = _flatten_topics(outline.get("topics") or [])[:topic_limit]

    outline_by_id = {str(t.get("id") or ""): t for t in (outline.get("topics") or [])}
    for t in flat_topics:
        t["table_scenarios"] = outline_by_id.get(t["id"], {}).get("table_scenarios") or ["basic_tgroup", "simpletable"]

    if not flat_topics:
        return {"error": "LLM returned empty topic list", "recipes_executed": [], "warnings": ["outline empty"]}

    # Smaller batch: table XML is verbose
    BATCH_SIZE = 5
    filled: dict[str, dict] = {}
    for batch_start in range(0, len(flat_topics), BATCH_SIZE):
        batch = flat_topics[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        try:
            raw = await generate_json(
                system_prompt=_FILL_SYSTEM_TABLE_DOMAIN,
                user_prompt=(
                    f"Domain: {prompt}\n\n"
                    f"Generate DITA XML for these {len(batch)} topics. "
                    f"Each MUST include the table_scenarios listed — use real domain data in all cells:\n"
                    + json.dumps(batch, indent=2)
                ),
                max_tokens=14000,
                step_name=f"freeform_table_domain_fill_{batch_num}",
                trace_id=trace_id,
                jira_id=jira_id,
            )
        except Exception as exc:
            logger.warning_structured("freeform_table_domain_fill_failed", extra_fields={"batch": batch_num, "error": str(exc)})
            continue
        items = raw if isinstance(raw, list) else (raw.get("topics") or raw.get("topic_files") or [])
        for item in items:
            if isinstance(item, dict) and item.get("id") and item.get("xml"):
                filled[item["id"]] = {
                    "filename": str(item.get("filename") or f"{item['id']}.dita"),
                    "xml": item["xml"],
                }

    topics_dir = scenario_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    written: list[tuple[str, str, str]] = []

    for topic in flat_topics:
        tid = topic["id"]
        f_info = filled.get(tid)
        if not f_info:
            warnings.append(f"Topic {tid} ('{topic['title']}') not produced")
            continue
        xml = f_info["xml"]
        # Sanity: warn if a required scenario is absent
        scenario_markers = {
            "col_span": "namest=",
            "row_span": "morerows=",
            "simpletable": "<simpletable",
            "multi_tgroup": "<tgroup",
        }
        for scenario in (topic.get("table_scenarios") or []):
            marker = scenario_markers.get(scenario)
            if marker and marker not in xml:
                warnings.append(f"Topic {tid}: scenario '{scenario}' may be missing (no '{marker}' found)")
        fname = f_info["filename"].replace("topics/", "")
        if not fname.endswith(".dita"):
            fname = f"{tid}_{_slugify(topic['title'])}.dita"
        (topics_dir / fname).write_text(xml, encoding="utf-8")
        written.append((tid, fname, topic.get("type", "reference")))

    if not written:
        return {"error": "No table domain topics produced", "recipes_executed": [], "warnings": warnings or ["fill failed"]}

    (scenario_dir / "generated.ditamap").write_text(_build_ditamap(map_title, written), encoding="utf-8")

    logger.info_structured("freeform_table_domain_done", extra_fields={"topics": len(written), "title": map_title})
    return {
        "recipes_executed": ["freeform_table_domain"],
        "generate_mode": "freeform_table_domain",
        "topic_count": len(written),
        "map_title": map_title,
        "warnings": warnings,
    }


async def _run_freeform_nested_keydef(
    prompt: str,
    jira_id: str,
    scenario_dir: Path,
    trace_id: str,
    topic_limit: int,
) -> dict[str, Any]:
    """Generate a nested-map keydef dataset exercising real AEM Guides key resolution.

    Produces:
    - Root DITA map with global keydefs + <mapref keyscope="..."> to submaps
    - 2–3 submap files, each in submaps/ directory, each with a keyscope
    - Local keys that shadow root keys within their scope
    - Topics that demonstrate cross-scope keyref (scope.keyname) and key inheritance
    - At least one key conflict scenario (same key name, different values across submaps)
    """
    logger.info_structured("freeform_nested_keydef_start", extra_fields={"jira_id": jira_id})

    # Phase 1: Outline — design the nested map structure
    try:
        outline = await generate_json(
            system_prompt=_OUTLINE_SYSTEM_NESTED_KEYDEF.format(limit=topic_limit),
            user_prompt=f"Design a nested-map key-resolution dataset for:\n\n{prompt}",
            max_tokens=4000,
            step_name="freeform_nested_keydef_outline",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        logger.warning_structured("freeform_nested_keydef_outline_failed", extra_fields={"error": str(exc)})
        return {"error": f"Nested keydef outline failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    root_map_title = str(outline.get("root_map_title") or "Nested Map Dataset").strip()
    root_keys = outline.get("root_keys") or []
    submaps = outline.get("submaps") or []

    if not submaps:
        return {"error": "LLM returned no submaps in nested keydef outline", "recipes_executed": [], "warnings": ["outline empty"]}

    # Collect all topics across submaps for the fill prompt
    all_topics_for_fill: list[dict] = []
    submap_meta: list[dict] = []  # keyscope, filename, topic ids
    for sm in submaps:
        sm_id = str(sm.get("id") or f"sm{len(submap_meta)+1:03d}")
        sm_filename = str(sm.get("filename") or f"submaps/{sm_id}.ditamap")
        sm_keyscope = str(sm.get("keyscope") or sm_id)
        sm_topics = sm.get("topics") or []
        submap_meta.append({
            "id": sm_id,
            "filename": sm_filename,
            "keyscope": sm_keyscope,
            "title": str(sm.get("title") or sm_keyscope),
            "local_keys": sm.get("local_keys") or [],
            "topic_ids": [str(t.get("id") or "") for t in sm_topics],
        })
        for t in sm_topics:
            all_topics_for_fill.append({
                "id": str(t.get("id") or ""),
                "title": str(t.get("title") or "Untitled"),
                "type": str(t.get("type") or "concept"),
                "submap_keyscope": sm_keyscope,
                "submap_filename": sm_filename,
                "uses_root_keys": t.get("uses_root_keys") or [],
                "uses_local_keys": t.get("uses_local_keys") or [],
                "uses_cross_scope_keys": t.get("uses_cross_scope_keys") or [],
            })

    all_topics_for_fill = all_topics_for_fill[:topic_limit]

    logger.info_structured("freeform_nested_keydef_outline_done", extra_fields={
        "submaps": len(submaps), "topics": len(all_topics_for_fill),
    })

    # Phase 2: Fill — one LLM call generates root map, all submaps, all topics
    # Split into one structural call (maps) + topic fill batches
    BATCH_SIZE = 8
    try:
        map_raw = await generate_json(
            system_prompt=_FILL_SYSTEM_NESTED_KEYDEF,
            user_prompt=(
                f"Domain: {prompt}\n\n"
                f"Root map title: {root_map_title}\n"
                f"Root keys: {json.dumps(root_keys)}\n\n"
                f"Submap structure: {json.dumps(submap_meta, indent=2)}\n\n"
                f"Topics to generate (ALL topics across all submaps):\n"
                + json.dumps(all_topics_for_fill, indent=2)
            ),
            max_tokens=16000,
            step_name="freeform_nested_keydef_fill",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        logger.warning_structured("freeform_nested_keydef_fill_failed", extra_fields={"error": str(exc)})
        return {"error": f"Nested keydef fill failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    warnings: list[str] = []

    # Phase 3: Write files
    # Write root map
    root_map_xml = (map_raw.get("root_map_xml") or "") if isinstance(map_raw, dict) else ""
    if root_map_xml:
        (scenario_dir / "generated.ditamap").write_text(root_map_xml, encoding="utf-8")
    else:
        warnings.append("LLM did not produce root_map_xml — generated.ditamap will be empty scaffold")
        (scenario_dir / "generated.ditamap").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">\n'
            f'<map><title>{root_map_title}</title></map>\n',
            encoding="utf-8",
        )

    # Write submaps
    submaps_dir = scenario_dir / "submaps"
    submaps_dir.mkdir(parents=True, exist_ok=True)
    submap_files = (map_raw.get("submap_files") or []) if isinstance(map_raw, dict) else []
    written_submaps = 0
    for sf in submap_files:
        if not isinstance(sf, dict) or not sf.get("filename") or not sf.get("xml"):
            continue
        sm_path = scenario_dir / sf["filename"]
        sm_path.parent.mkdir(parents=True, exist_ok=True)
        sm_path.write_text(sf["xml"], encoding="utf-8")
        written_submaps += 1

    if written_submaps == 0:
        warnings.append("No submap files written — check fill prompt output")

    # Write topics
    topics_dir = scenario_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    topic_files = (map_raw.get("topic_files") or []) if isinstance(map_raw, dict) else []
    written: list[tuple[str, str, str]] = []
    filled_ids = set()

    for tf in topic_files:
        if not isinstance(tf, dict) or not tf.get("id") or not tf.get("xml"):
            continue
        tid = tf["id"]
        # LLM may return filename with or without topics/ prefix
        fname_raw = str(tf.get("filename") or f"{tid}.dita")
        fname = fname_raw.replace("topics/", "")
        if not fname.endswith(".dita"):
            fname = f"{fname}.dita"
        fpath = topics_dir / fname
        fpath.write_text(_sanitize_keywords_in_body(tf["xml"]), encoding="utf-8")
        written.append((tid, fname, "topic"))
        filled_ids.add(tid)

    # Warn about any topics the LLM dropped
    for t in all_topics_for_fill:
        if t["id"] and t["id"] not in filled_ids:
            warnings.append(f"Topic {t['id']} ('{t['title']}') not produced by LLM")

    if not written:
        return {
            "error": "No topics produced by nested keydef fill",
            "recipes_executed": [],
            "warnings": warnings or ["fill returned no topic_files"],
        }

    logger.info_structured("freeform_nested_keydef_done", extra_fields={
        "topics": len(written), "submaps": written_submaps, "title": root_map_title,
    })
    return {
        "recipes_executed": ["freeform_nested_keydef"],
        "generate_mode": "freeform_nested_keydef",
        "topic_count": len(written),
        "submap_count": written_submaps,
        "map_title": root_map_title,
        "warnings": warnings,
    }


async def _run_freeform_code_domain(
    prompt: str,
    jira_id: str,
    scenario_dir: Path,
    trace_id: str,
    topic_limit: int,
) -> dict[str, Any]:
    """Generate a programming-domain DITA dataset.

    Produces topics with <codeblock outputclass="language-X">, <codeph>, <filepath>,
    <coderef href="../code/file"> pointing to real code files, and external-scope xrefs.
    Code files are written to scenario_dir/code/ so <coderef> hrefs resolve in the bundle.
    """
    logger.info_structured("freeform_code_domain_start", extra_fields={"jira_id": jira_id})

    # Phase 1: Outline — plan topics and code files
    try:
        outline = await generate_json(
            system_prompt=_OUTLINE_SYSTEM_CODE_DOMAIN.format(limit=topic_limit),
            user_prompt=f"Design a programming-domain DITA dataset for:\n\n{prompt}",
            max_tokens=3000,
            step_name="freeform_code_domain_outline",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        logger.warning_structured("freeform_code_domain_outline_failed", extra_fields={"error": str(exc)})
        return {"error": f"Code domain outline failed: {exc}", "recipes_executed": [], "warnings": [str(exc)]}

    map_title = str(outline.get("map_title") or "Programming Domain Dataset").strip()
    code_files_plan = outline.get("code_files") or []
    flat_topics = _flatten_topics(outline.get("topics") or [])[:topic_limit]

    # Carry coderef metadata into the fill prompt
    outline_by_id = {str(t.get("id") or ""): t for t in (outline.get("topics") or [])}
    for t in flat_topics:
        meta = outline_by_id.get(t["id"], {})
        t["code_elements"] = meta.get("code_elements") or ["codeblock", "codeph"]
        t["coderef_files"] = meta.get("coderef_files") or []
        t["has_external_link"] = bool(meta.get("has_external_link"))

    if not flat_topics:
        return {"error": "LLM returned empty topic list", "recipes_executed": [], "warnings": ["outline empty"]}

    logger.info_structured("freeform_code_domain_outline_done", extra_fields={
        "topics": len(flat_topics), "code_files": len(code_files_plan), "title": map_title,
    })

    # Phase 2: Fill — topics + code file contents in one call
    # Batch topics to stay within token limits (code-heavy XML is large)
    BATCH_SIZE = 6
    filled_topics: dict[str, dict] = {}  # id → {filename, xml}
    code_file_contents: dict[str, str] = {}  # filename → content (from first batch only)
    code_files_requested = False

    for batch_start in range(0, len(flat_topics), BATCH_SIZE):
        batch = flat_topics[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        logger.info_structured("freeform_code_domain_fill_batch", extra_fields={"batch": batch_num, "size": len(batch)})

        # Include code file plan only in the first batch so LLM generates their contents once
        include_code = not code_files_requested
        try:
            raw = await generate_json(
                system_prompt=_FILL_SYSTEM_CODE_DOMAIN,
                user_prompt=(
                    f"Domain context: {prompt}\n\n"
                    + (f"Code files to create: {json.dumps(code_files_plan)}\n\n" if include_code else "")
                    + f"Generate DITA XML for these {len(batch)} topics. "
                    f"Each topic MUST include the listed code_elements. "
                    f"<coderef> href must be ../code/<filename> (relative from topics/ to code/):\n"
                    + json.dumps(batch, indent=2)
                ),
                max_tokens=14000,
                step_name=f"freeform_code_domain_fill_{batch_num}",
                trace_id=trace_id,
                jira_id=jira_id,
            )
        except Exception as exc:
            logger.warning_structured("freeform_code_domain_fill_failed", extra_fields={"batch": batch_num, "error": str(exc)})
            continue

        if isinstance(raw, dict):
            # Collect code file contents from first batch response
            if include_code and not code_files_requested:
                for cf in (raw.get("code_file_contents") or []):
                    if isinstance(cf, dict) and cf.get("filename") and cf.get("content"):
                        code_file_contents[cf["filename"]] = cf["content"]
                code_files_requested = True

            for tf in (raw.get("topic_files") or []):
                if isinstance(tf, dict) and tf.get("id") and tf.get("xml"):
                    filled_topics[tf["id"]] = {
                        "filename": str(tf.get("filename") or f"{tf['id']}.dita"),
                        "xml": tf["xml"],
                    }

    # Phase 3: Write code files
    code_dir = scenario_dir / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    written_code: list[str] = []

    for cf_plan in code_files_plan:
        fname = str(cf_plan.get("filename") or "").replace("code/", "")
        if not fname:
            continue
        content = code_file_contents.get(cf_plan.get("filename", "")) or code_file_contents.get(fname, "")
        if content:
            (code_dir / fname).write_text(content, encoding="utf-8")
            written_code.append(fname)
        else:
            # Write a placeholder so coderef hrefs don't break bundle validation
            lang = str(cf_plan.get("language") or "text")
            placeholder = f"# {fname}\n# Code file for {map_title}\n# Language: {lang}\n"
            (code_dir / fname).write_text(placeholder, encoding="utf-8")
            written_code.append(fname)

    # Phase 4: Write topic files
    topics_dir = scenario_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    written: list[tuple[str, str, str]] = []

    for topic in flat_topics:
        tid = topic["id"]
        f_info = filled_topics.get(tid)
        if not f_info:
            warnings.append(f"Topic {tid} ('{topic['title']}') not produced by LLM")
            continue
        xml = f_info["xml"]
        # Sanity checks
        if "codeblock" in (topic.get("code_elements") or []) and "<codeblock" not in xml:
            warnings.append(f"Topic {tid} is missing <codeblock> — check fill output")
        if "coderef" in (topic.get("code_elements") or []) and "<coderef" not in xml:
            warnings.append(f"Topic {tid} is missing <coderef> — check fill output")
        if topic.get("has_external_link") and 'scope="external"' not in xml:
            warnings.append(f"Topic {tid} is missing scope=\"external\" xref")

        fname_raw = f_info["filename"].replace("topics/", "")
        fname = fname_raw if fname_raw.endswith(".dita") else f"{tid}_{_slugify(topic['title'])}.dita"
        (topics_dir / fname).write_text(xml, encoding="utf-8")
        written.append((tid, fname, topic.get("type", "concept")))

    if not written:
        return {
            "error": "No code domain topics produced by LLM",
            "recipes_executed": [],
            "warnings": warnings or ["All fill batches failed"],
        }

    # Phase 5: DITA map
    (scenario_dir / "generated.ditamap").write_text(_build_ditamap(map_title, written), encoding="utf-8")

    logger.info_structured("freeform_code_domain_done", extra_fields={
        "topics": len(written), "code_files": len(written_code), "title": map_title,
    })
    return {
        "recipes_executed": ["freeform_code_domain"],
        "generate_mode": "freeform_code_domain",
        "topic_count": len(written),
        "code_file_count": len(written_code),
        "map_title": map_title,
        "warnings": warnings,
    }
