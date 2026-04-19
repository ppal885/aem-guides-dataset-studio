"""Minimal DTD stub text for generated datasets (Oxygen / editor validation, not full OASIS compliance)."""

# Matches elements emitted by bulk_dita_map_topics (topic with body/p, map with topicmeta + topicref@navtitle).
BULK_MAP_TOPICS_TOPIC_DTD = """<!-- Minimal DITA Topic DTD stub for bulk_dita_map_topics -->
<!ENTITY % topic "topic">
<!ELEMENT topic (title, shortdesc?, body?)>
<!ATTLIST topic
  id CDATA #REQUIRED
  xml:lang CDATA #IMPLIED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT shortdesc (#PCDATA)>
<!ELEMENT body (p+)>
<!ELEMENT p (#PCDATA)>
"""

BULK_MAP_TOPICS_MAP_DTD = """<!-- Minimal DITA Map DTD stub for bulk_dita_map_topics -->
<!ENTITY % map "map">
<!ELEMENT map (title, topicmeta?, topicref*)>
<!ATTLIST map
  id CDATA #REQUIRED
  xml:lang CDATA #IMPLIED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT topicmeta (shortdesc?)>
<!ELEMENT shortdesc (#PCDATA)>
<!ELEMENT topicref EMPTY>
<!ATTLIST topicref
  href CDATA #REQUIRED
  navtitle CDATA #IMPLIED>
"""

# Default stubs for dataset-wide DTD resolution (paths fixed per file under technicalContent/dtd/).
STANDARD_TOPIC_DTD = """<!-- Minimal DITA Topic DTD stub (general topics) -->
<!ENTITY % topic "topic">
<!ELEMENT topic (title, shortdesc?, prolog?, body?, related-links?, topic*)>
<!ATTLIST topic
  id CDATA #REQUIRED
  xml:lang CDATA #IMPLIED
  audience CDATA #IMPLIED
  platform CDATA #IMPLIED
  product CDATA #IMPLIED
  otherprops CDATA #IMPLIED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT shortdesc (#PCDATA)>
<!ELEMENT prolog (metadata?)>
<!ELEMENT metadata (keywords*|category*|audience*|othermeta*|publisher*|data*)>
<!ELEMENT keywords (keyword+)>
<!ELEMENT keyword (#PCDATA)>
<!ATTLIST keyword id CDATA #IMPLIED keyref CDATA #IMPLIED>
<!ELEMENT category (#PCDATA)>
<!ELEMENT audience (#PCDATA)>
<!ELEMENT othermeta EMPTY>
<!ATTLIST othermeta name CDATA #IMPLIED content CDATA #IMPLIED>
<!ELEMENT publisher (#PCDATA)>
<!ELEMENT data EMPTY>
<!ATTLIST data name CDATA #IMPLIED value CDATA #IMPLIED>
<!ELEMENT body (section*|p*|table*|simpletable*|codeblock*|note*|example*|ul*|ol*|dl*|image*|xref*|draft-comment*|foreign*)>
<!ELEMENT foreign ANY>
<!ATTLIST foreign xmlns CDATA #IMPLIED>
<!ELEMENT related-links (link*|linklist*)>
<!ELEMENT link EMPTY>
<!ATTLIST link href CDATA #IMPLIED keyref CDATA #IMPLIED type CDATA #IMPLIED format CDATA #IMPLIED scope CDATA #IMPLIED>
<!ELEMENT linklist ANY>
<!ELEMENT section (title?, (p|table|simpletable|codeblock|note|example|ul|ol|dl|section)*)>
<!ATTLIST section id CDATA #IMPLIED>
<!ELEMENT p (#PCDATA|xref|ph|b|i|u|codeph|tm|keyword|image|foreign)*>
<!ELEMENT table ANY>
<!ELEMENT simpletable (sthead?, stbody)>
<!ELEMENT sthead (strow)>
<!ELEMENT stbody (strow+)>
<!ELEMENT strow (stentry+)>
<!ELEMENT stentry (#PCDATA)>
<!ELEMENT codeblock (#PCDATA)>
<!ATTLIST codeblock outputclass CDATA #IMPLIED>
<!ELEMENT note ANY>
<!ELEMENT example ANY>
<!ELEMENT ul (li+)>
<!ELEMENT li ANY>
<!ELEMENT ol (li+)>
<!ELEMENT dl (dlentry+)>
<!ELEMENT dlentry (dt, dd)>
<!ELEMENT dt (#PCDATA)>
<!ELEMENT dd ANY>
<!ELEMENT image EMPTY>
<!ATTLIST image href CDATA #IMPLIED placement CDATA #IMPLIED format CDATA #IMPLIED>
<!ELEMENT xref EMPTY>
<!ATTLIST xref href CDATA #IMPLIED keyref CDATA #IMPLIED>
<!ELEMENT ph (#PCDATA)>
<!ELEMENT b (#PCDATA|i|u)*>
<!ELEMENT i (#PCDATA|b|u)*>
<!ELEMENT u (#PCDATA|b|i)*>
<!ELEMENT codeph (#PCDATA)>
<!ELEMENT tm (#PCDATA)>
<!ELEMENT draft-comment ANY>
"""

STANDARD_MAP_DTD = """<!-- Minimal DITA Map DTD stub (general maps) -->
<!ENTITY % map "map">
<!ELEMENT map (title?, topicmeta?, (topicref|keydef|topichead|topicgroup|navref|anchor|reltable|mapref)*)>
<!ATTLIST map
  id CDATA #IMPLIED
  xml:lang CDATA #IMPLIED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT topicmeta (navtitle?, shortdesc?, data*, keywords?)>
<!ELEMENT navtitle (#PCDATA)>
<!ELEMENT shortdesc (#PCDATA)>
<!ELEMENT data EMPTY>
<!ATTLIST data name CDATA #IMPLIED value CDATA #IMPLIED>
<!ELEMENT keywords (keyword+)>
<!ELEMENT keyword (#PCDATA)>
<!ATTLIST keyword id CDATA #IMPLIED>
<!ELEMENT topicref EMPTY>
<!ATTLIST topicref
  href CDATA #IMPLIED
  keyref CDATA #IMPLIED
  keys CDATA #IMPLIED
  navtitle CDATA #IMPLIED
  format CDATA #IMPLIED
  type CDATA #IMPLIED
  keyscope CDATA #IMPLIED>
<!ELEMENT keydef EMPTY>
<!ATTLIST keydef keys CDATA #REQUIRED href CDATA #IMPLIED>
<!ELEMENT topichead EMPTY>
<!ATTLIST topichead navtitle CDATA #IMPLIED>
<!ELEMENT topicgroup (topicref|topicgroup)*>
<!ATTLIST topicgroup navtitle CDATA #IMPLIED>
<!ELEMENT navref EMPTY>
<!ATTLIST navref keyref CDATA #IMPLIED href CDATA #IMPLIED mapref CDATA #IMPLIED>
<!ELEMENT anchor EMPTY>
<!ATTLIST anchor id CDATA #IMPLIED>
<!ELEMENT mapref EMPTY>
<!ATTLIST mapref href CDATA #IMPLIED format CDATA #IMPLIED>
<!ELEMENT reltable (relheader?, relrow*)>
<!ELEMENT relheader (relcolspec+)>
<!ELEMENT relcolspec EMPTY>
<!ELEMENT relrow (relcell+)>
<!ELEMENT relcell (topicref)*>
"""

TASK_TOPIC_DTD = """<!-- Minimal DITA Task DTD stub -->
<!ENTITY % task "task">
<!ELEMENT task (title, shortdesc?, taskbody?, related-links?)>
<!ATTLIST task id CDATA #REQUIRED xml:lang CDATA #IMPLIED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT shortdesc (#PCDATA)>
<!ELEMENT taskbody (prereq?, context?, steps?, result?, example?, choicetable?)>
<!ELEMENT prereq (p+)>
<!ELEMENT context (p+)>
<!ELEMENT steps (step+)>
<!ATTLIST steps unordered CDATA #IMPLIED>
<!ELEMENT step (cmd, info?, substeps?)>
<!ATTLIST step importance CDATA #IMPLIED>
<!ELEMENT cmd (#PCDATA)>
<!ELEMENT info (p+)>
<!ELEMENT substeps (substep+)>
<!ELEMENT substep (cmd)>
<!ELEMENT result (p+)>
<!ELEMENT example (p+)>
<!ELEMENT choicetable (chrow+)>
<!ATTLIST choicetable id CDATA #IMPLIED>
<!ELEMENT chrow (choption, chdesc)>
<!ELEMENT choption (#PCDATA)>
<!ELEMENT chdesc (p+)>
<!ELEMENT p (#PCDATA)>
<!ELEMENT related-links (link*)>
<!ELEMENT link EMPTY>
<!ATTLIST link href CDATA #IMPLIED>
"""

CONCEPT_TOPIC_DTD = """<!-- Minimal DITA Concept DTD stub -->
<!ENTITY % concept "concept">
<!ELEMENT concept (title, shortdesc?, conbody?, related-links?)>
<!ATTLIST concept id CDATA #REQUIRED xml:lang CDATA #IMPLIED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT shortdesc (#PCDATA)>
<!ELEMENT conbody (p|section)*>
<!ELEMENT section (title?, p+)>
<!ATTLIST section id CDATA #IMPLIED>
<!ELEMENT p (#PCDATA)>
<!ELEMENT related-links (link*)>
<!ELEMENT link EMPTY>
<!ATTLIST link href CDATA #IMPLIED>
<!ELEMENT linktext (#PCDATA)>
"""

REFERENCE_TOPIC_DTD = """<!-- Minimal DITA Reference DTD stub (properties align with OASIS proptype/propvalue/propdesc) -->
<!ENTITY % reference "reference">
<!ELEMENT reference (title, shortdesc?, refbody?, related-links?)>
<!ATTLIST reference id CDATA #REQUIRED xml:lang CDATA #IMPLIED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT shortdesc (#PCDATA)>
<!ELEMENT refbody (refsyn?, properties?, section*, choicetable?)>
<!ELEMENT refsyn (p|syntaxdiagram)+>
<!ELEMENT syntaxdiagram (title?, (groupseq|groupchoice)+)>
<!ELEMENT groupseq ((kwd|oper|delim|sep|repsep|groupseq|groupchoice)+)>
<!ELEMENT groupchoice ((kwd|oper|delim|sep|repsep|groupseq|groupchoice)+)>
<!ELEMENT kwd (#PCDATA)>
<!ELEMENT oper (#PCDATA)>
<!ELEMENT delim (#PCDATA)>
<!ELEMENT sep (#PCDATA)>
<!ELEMENT repsep (#PCDATA)>
<!ELEMENT properties (prophead?, property+)>
<!ATTLIST properties outputclass CDATA #IMPLIED>
<!ELEMENT prophead (proptypehd, propvaluehd, propdeschd)>
<!ELEMENT proptypehd (#PCDATA)>
<!ELEMENT propvaluehd (#PCDATA)>
<!ELEMENT propdeschd (#PCDATA)>
<!ELEMENT property (proptype?, propvalue?, propdesc?)>
<!ATTLIST property id CDATA #IMPLIED>
<!ELEMENT proptype (#PCDATA)>
<!ELEMENT propvalue (#PCDATA)>
<!ELEMENT propdesc (p|foreign)+>
<!ELEMENT foreign (p+)>
<!ELEMENT section (title?, p+)>
<!ATTLIST section id CDATA #IMPLIED>
<!ELEMENT choicetable (chrow+)>
<!ATTLIST choicetable id CDATA #IMPLIED>
<!ELEMENT chrow (choption, chdesc)>
<!ELEMENT choption (#PCDATA)>
<!ELEMENT chdesc (p+)>
<!ELEMENT p (#PCDATA)>
<!ELEMENT related-links (link*)>
<!ELEMENT link EMPTY>
<!ATTLIST link href CDATA #IMPLIED>
"""

GLOSENTRY_DTD = """<!-- Minimal DITA glossentry DTD stub -->
<!ENTITY % glossentry "glossentry">
<!ELEMENT glossentry (glossterm, alt*, glossdef, glossBody?)>
<!ATTLIST glossentry id CDATA #REQUIRED xml:lang CDATA #IMPLIED>
<!ELEMENT glossterm (#PCDATA)>
<!ELEMENT alt (#PCDATA)>
<!ATTLIST alt platform CDATA #IMPLIED>
<!ELEMENT glossdef (p+)>
<!ELEMENT glossBody (p+)>
<!ELEMENT p (#PCDATA)>
"""

BOOKMAP_DTD = """<!-- Minimal DITA bookmap DTD stub -->
<!ENTITY % bookmap "bookmap">
<!ELEMENT bookmap (title, bookmeta?, frontmatter?, chapter*, backmatter?)>
<!ATTLIST bookmap id CDATA #REQUIRED xml:lang CDATA #IMPLIED>
<!ELEMENT title (#PCDATA)>
<!ELEMENT bookmeta (booktitle?, bookabstract?)>
<!ELEMENT booktitle (mainbooktitle)>
<!ELEMENT mainbooktitle (#PCDATA)>
<!ELEMENT bookabstract (p+)>
<!ELEMENT frontmatter (notices?, preface?)>
<!ELEMENT notices (topicref)>
<!ELEMENT preface (topicref)>
<!ELEMENT chapter (topicref+)>
<!ELEMENT backmatter (appendix?, indexlist?)>
<!ELEMENT appendix (topicref)>
<!ELEMENT indexlist (topicref)>
<!ELEMENT topicref EMPTY>
<!ATTLIST topicref href CDATA #IMPLIED type CDATA #IMPLIED navtitle CDATA #IMPLIED>
<!ELEMENT p (#PCDATA)>
"""

SUBJECT_SCHEME_DTD = """<!-- Minimal subjectScheme map DTD stub -->
<!ELEMENT subjectScheme (subjectdef|enumerationdef)*>
<!ATTLIST subjectScheme id CDATA #IMPLIED>
<!ELEMENT subjectdef (#PCDATA|subjectdef)*>
<!ATTLIST subjectdef keys CDATA #IMPLIED keyref CDATA #IMPLIED>
<!ELEMENT enumerationdef (elementdef, attributedef, subjectdef)>
<!ELEMENT elementdef EMPTY>
<!ATTLIST elementdef name CDATA #REQUIRED>
<!ELEMENT attributedef EMPTY>
<!ATTLIST attributedef name CDATA #REQUIRED>
"""

DATASET_DTD_STUBS: dict[str, str] = {
    "topic.dtd": STANDARD_TOPIC_DTD,
    "map.dtd": STANDARD_MAP_DTD,
    "task.dtd": TASK_TOPIC_DTD,
    "concept.dtd": CONCEPT_TOPIC_DTD,
    "reference.dtd": REFERENCE_TOPIC_DTD,
    "glossentry.dtd": GLOSENTRY_DTD,
    "bookmap.dtd": BOOKMAP_DTD,
    "subjectScheme.dtd": SUBJECT_SCHEME_DTD,
}
