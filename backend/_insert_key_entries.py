"""Insert key-related DITA spec entries into seed."""
import json, sys

SEED_PATH = "backend/app/storage/dita_spec_seed.json"

with open(SEED_PATH, encoding="utf-8") as f:
    data = json.load(f)

# Check if already inserted
if any(e.get("element_name") == "keys_attribute" for e in data):
    print("Already inserted. Skipping.")
    sys.exit(0)

# Insert after uri_based_addressing
insert_idx = None
for i, e in enumerate(data):
    if e.get("element_name") == "uri_based_addressing":
        insert_idx = i + 1
        break
if insert_idx is None:
    insert_idx = len(data)

new_entries = [
  {
    "element_name": "keys_attribute",
    "content_type": "attribute",
    "text_content": (
        "The @keys attribute defines one or more key names for a resource. "
        "Used on <topicref>, <keydef>, and specializations in DITA maps.\n\n"
        "Syntax: One or more space-separated key names.\n"
        "Example: keys=\"install install-topic setup\" defines 3 keys for the same resource.\n\n"
        "Naming rules:\n"
        "- Case-sensitive: 'Install' and 'install' are different keys\n"
        "- Legal characters: same as URI characters\n"
        "- Prohibited: { } [ ] / # ? and whitespace (except as separator)\n\n"
        "IMPORTANT: The attribute name is keys (PLURAL), NOT key.\n"
        "- WRONG: <topicref href=\"t.dita\" key=\"mykey\"/>\n"
        "- CORRECT: <topicref href=\"t.dita\" keys=\"mykey\"/>\n\n"
        "Key definitions bind key names to:\n"
        "1. URI-addressed resources via @href\n"
        "2. Metadata content in child <topicmeta> (variable text)\n"
        "3. Both simultaneously\n"
        "4. Nothing (valid but empty key definition)\n\n"
        "Precedence when duplicate keys exist:\n"
        "1. First definition in breadth-first map traversal wins\n"
        "2. Parent scope definitions override child scope definitions\n"
        "3. All key spaces resolved BEFORE any key reference processing\n\n"
        "Test data scenarios:\n"
        "```xml\n"
        "<map>\n"
        "  <!-- Single key -->\n"
        "  <keydef keys=\"product-name\">\n"
        "    <topicmeta><keywords><keyword>AEM Guides</keyword></keywords></topicmeta>\n"
        "  </keydef>\n"
        "  <!-- Multiple keys for same resource -->\n"
        "  <keydef keys=\"install setup getting-started\" href=\"install.dita\"/>\n"
        "  <!-- Key on topicref (visible in TOC + defines key) -->\n"
        "  <topicref href=\"config.dita\" keys=\"configuration\"/>\n"
        "  <!-- Key for external resource -->\n"
        "  <keydef keys=\"api-docs\" href=\"https://api.example.com\" format=\"html\" scope=\"external\"/>\n"
        "  <!-- Key for PDF -->\n"
        "  <keydef keys=\"user-guide-pdf\" href=\"guide.pdf\" format=\"pdf\" scope=\"local\"/>\n"
        "  <!-- Empty key (placeholder, overridden by parent map) -->\n"
        "  <keydef keys=\"brand-name\"/>\n"
        "</map>\n"
        "```"
    ),
    "parent_element": None,
    "children_elements": None,
    "attributes": "{\"keys\": \"space-separated key names (PLURAL, not key)\"}",
    "usage_contexts": [
      "keydef keys='product-name' \u2014 variable text key",
      "keydef keys='install' href='install.dita' \u2014 topic key",
      "topicref keys='config' href='config.dita' \u2014 visible + keyed",
      "keydef keys='api' href='https://...' format='html' scope='external' \u2014 external key"
    ],
    "common_mistakes": [
      "Using key= (singular) instead of keys= (PLURAL)",
      "Forgetting keys are case-sensitive",
      "Not understanding first-definition-wins precedence"
    ],
    "test_data_coverage": {
      "all_values": ["single-key", "multiple-keys", "variable-text-key", "topic-key", "external-key", "empty-key", "override-key"],
      "supported_elements": ["keydef", "topicref"],
      "combination_attributes": ["href", "format", "scope", "keyscope"]
    }
  },
  {
    "element_name": "keyref_attribute",
    "content_type": "attribute",
    "text_content": (
        "The @keyref attribute provides indirect, late-bound references to resources defined by keys.\n\n"
        "Syntax forms:\n"
        "1. Simple: keyref=\"keyname\" \u2014 resolves to the key's href target\n"
        "2. Element-specific: keyref=\"keyname/elementid\" \u2014 resolves to element within key's target\n\n"
        "Elements that support @keyref:\n"
        "- <topicref keyref=\"...\"> \u2014 indirect topic reference in map\n"
        "- <xref keyref=\"...\"> \u2014 indirect cross-reference in topic\n"
        "- <link keyref=\"...\"> \u2014 indirect related link\n"
        "- <keyword keyref=\"...\"> \u2014 variable text substitution\n"
        "- <term keyref=\"...\"> \u2014 glossary term reference\n"
        "- <image keyref=\"...\"> \u2014 indirect image reference\n"
        "- <ph keyref=\"...\"> \u2014 phrase-level variable text\n\n"
        "Interaction with @href:\n"
        "- If both keyref and href are specified, keyref takes precedence\n"
        "- href acts as fallback if key is undefined\n\n"
        "Variable text substitution:\n"
        "When keyref points to a key with <topicmeta>/<keywords>/<keyword>, "
        "the keyword text replaces the element content.\n\n"
        "Test data:\n"
        "```xml\n"
        "<map>\n"
        "  <keydef keys=\"product\" href=\"product-info.dita\">\n"
        "    <topicmeta><keywords><keyword>AEM Guides</keyword></keywords></topicmeta>\n"
        "  </keydef>\n"
        "  <keydef keys=\"api-ref\" href=\"https://api.example.com\" format=\"html\" scope=\"external\"/>\n"
        "  <topicref keyref=\"product\"/>  <!-- indirect topic reference -->\n"
        "</map>\n\n"
        "<!-- In topic body -->\n"
        "<p>Welcome to <keyword keyref=\"product\"/>.</p>  <!-- resolves to 'AEM Guides' -->\n"
        "<p>See <xref keyref=\"api-ref\">API documentation</xref>.</p>\n"
        "<p>See <xref keyref=\"product/install-section\" type=\"section\">install</xref>.</p>\n"
        "```"
    ),
    "parent_element": None,
    "children_elements": None,
    "attributes": "{\"keyref\": \"keyname or keyname/elementid\"}",
    "usage_contexts": [
      "topicref keyref='key' \u2014 indirect topic reference",
      "xref keyref='key' \u2014 indirect cross-reference",
      "keyword keyref='key' \u2014 variable text substitution",
      "image keyref='key' \u2014 indirect image reference"
    ],
    "test_data_coverage": {
      "all_values": ["simple-keyref", "element-keyref", "variable-text", "fallback-href", "undefined-key"],
      "supported_elements": ["topicref", "xref", "link", "keyword", "term", "image", "ph"],
      "combination_attributes": ["href", "type", "format"]
    }
  },
  {
    "element_name": "keyscope_attribute",
    "content_type": "attribute",
    "text_content": (
        "The @keyscope attribute creates a named scope for key definitions. "
        "Defined in OASIS DITA 1.3.\n\n"
        "Purpose: Allows different branches of a map to define different values for the same key name.\n\n"
        "Syntax: One or more space-separated scope names (same naming rules as keys).\n\n"
        "How scopes work:\n"
        "- Each scope has its own key space for resolution\n"
        "- Keys in a scope are accessed from outside via scope-qualified names: scope.keyname\n"
        "- The root map always defines an implicit (unnamed) scope\n"
        "- Nested scopes: inner scope can override outer scope keys\n\n"
        "Cross-deliverable linking with keyscope + scope='peer':\n"
        "```xml\n"
        "<!-- In book-a's map: reference book-b as peer -->\n"
        "<topicref href=\"../book-b/book-b.ditamap\" scope=\"peer\" \n"
        "         keyscope=\"book-b\" format=\"ditamap\"/>\n"
        "<!-- In topic: link to book-b's install topic -->\n"
        "<xref keyref=\"book-b.install\">See Book B installation</xref>\n"
        "```\n\n"
        "Variable text per scope (same key, different values):\n"
        "```xml\n"
        "<map>\n"
        "  <!-- Windows scope -->\n"
        "  <topicref keyscope=\"windows\">\n"
        "    <keydef keys=\"os-name\">\n"
        "      <topicmeta><keywords><keyword>Windows</keyword></keywords></topicmeta>\n"
        "    </keydef>\n"
        "    <topicref href=\"install.dita\"/>  <!-- uses 'Windows' for os-name -->\n"
        "  </topicref>\n"
        "  <!-- Linux scope -->\n"
        "  <topicref keyscope=\"linux\">\n"
        "    <keydef keys=\"os-name\">\n"
        "      <topicmeta><keywords><keyword>Linux</keyword></keywords></topicmeta>\n"
        "    </keydef>\n"
        "    <topicref href=\"install.dita\"/>  <!-- uses 'Linux' for os-name -->\n"
        "  </topicref>\n"
        "</map>\n"
        "```\n\n"
        "Conref redirection with keys:\n"
        "```xml\n"
        "<!-- conkeyref allows map-level control over reused content -->\n"
        "<note conkeyref=\"reuse/warning-1\">placeholder</note>\n"
        "<!-- Map defines which reuse topic provides the content: -->\n"
        "<keydef keys=\"reuse\" href=\"acme-reuse.dita\"/>\n"
        "<!-- Partner map overrides: -->\n"
        "<keydef keys=\"reuse\" href=\"partner-reuse.dita\"/>\n"
        "```"
    ),
    "parent_element": None,
    "children_elements": None,
    "attributes": "{\"keyscope\": \"space-separated scope names\"}",
    "usage_contexts": [
      "keyscope on topicref \u2014 creates named scope for branch",
      "keyscope + scope='peer' \u2014 cross-deliverable linking",
      "nested keyscopes \u2014 scope overrides within branches",
      "scope-qualified key: scope.keyname \u2014 access key from outside scope"
    ],
    "common_mistakes": [
      "Forgetting to qualify key names when accessing from outside scope (use scope.keyname)",
      "Not understanding that root map always has an implicit scope",
      "Using keyscope on peer map root (ignored by referencing map)"
    ],
    "test_data_coverage": {
      "all_values": ["single-scope", "multiple-scope-names", "nested-scopes", "peer-scope", "variable-text-per-scope"],
      "supported_elements": ["topicref", "map"],
      "combination_attributes": ["scope", "keys", "format"],
      "default_scenarios": ["no keyscope (implicit root scope)", "scope-qualified key reference"]
    }
  },
  {
    "element_name": "conkeyref_attribute",
    "content_type": "attribute",
    "text_content": (
        "The @conkeyref attribute provides key-based content reuse (conref redirection).\n\n"
        "Syntax: conkeyref=\"keyname/elementid\"\n"
        "- keyname \u2014 resolves to a topic via key definition\n"
        "- elementid \u2014 the @id of the element to reuse from that topic\n"
        "- MUST have both parts separated by /\n\n"
        "WRONG: conkeyref=\"keyname\" (missing /elementid)\n"
        "CORRECT: conkeyref=\"reuse/warning-note\"\n\n"
        "How it works:\n"
        "1. Processor resolves 'keyname' to a topic file via map's key definition\n"
        "2. Within that topic, finds element with id='elementid'\n"
        "3. Copies that element's content into the referencing location\n\n"
        "Advantage over @conref:\n"
        "- Map-level control: change which file provides content by changing key definition\n"
        "- Portable: topics don't hardcode file paths\n"
        "- Enables variant publishing (different maps -> different content)\n\n"
        "Test data:\n"
        "```xml\n"
        "<!-- Map with key definition -->\n"
        "<map>\n"
        "  <keydef keys=\"shared-warnings\" href=\"warnings-en.dita\"/>\n"
        "  <topicref href=\"install.dita\"/>\n"
        "</map>\n\n"
        "<!-- warnings-en.dita (source of reusable content) -->\n"
        "<topic id=\"warnings\">\n"
        "  <title>Warnings</title>\n"
        "  <body>\n"
        "    <note id=\"backup-warning\" type=\"caution\">Back up before proceeding.</note>\n"
        "    <p id=\"prereq-text\">Ensure you have admin privileges.</p>\n"
        "  </body>\n"
        "</topic>\n\n"
        "<!-- install.dita (uses conkeyref) -->\n"
        "<task id=\"install\">\n"
        "  <title>Install</title>\n"
        "  <taskbody>\n"
        "    <prereq>\n"
        "      <note conkeyref=\"shared-warnings/backup-warning\">placeholder</note>\n"
        "      <p conkeyref=\"shared-warnings/prereq-text\">placeholder</p>\n"
        "    </prereq>\n"
        "  </taskbody>\n"
        "</task>\n"
        "```"
    ),
    "parent_element": None,
    "children_elements": None,
    "attributes": "{\"conkeyref\": \"keyname/elementid (MUST have both parts)\"}",
    "usage_contexts": [
      "conkeyref='key/id' on <note> \u2014 reuse a note via key",
      "conkeyref='key/id' on <p> \u2014 reuse a paragraph via key",
      "conkeyref='key/id' on <step> \u2014 reuse a step via key",
      "variant publishing \u2014 different maps point key to different source files"
    ],
    "common_mistakes": [
      "Missing /elementid (conkeyref='keyname' is WRONG)",
      "Target element missing @id attribute",
      "Element type mismatch between source and reference",
      "Using conref when conkeyref is available (prefer key-based)"
    ],
    "test_data_coverage": {
      "all_values": ["note-conkeyref", "paragraph-conkeyref", "step-conkeyref", "variant-publishing", "fallback-conref"],
      "supported_elements": ["note", "p", "step", "li", "ph", "keyword", "any-element-with-id"],
      "combination_attributes": ["keys", "keydef", "href"]
    }
  }
]

for i, entry in enumerate(new_entries):
    data.insert(insert_idx + i, entry)

with open(SEED_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"OK: Inserted {len(new_entries)} key entries at index {insert_idx}. Total: {len(data)}")
