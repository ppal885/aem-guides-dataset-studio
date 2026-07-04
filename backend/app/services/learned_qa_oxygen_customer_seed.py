"""Oxygen customer-language questions mapped to senior DITA troubleshooting answers."""

from __future__ import annotations

import re
from typing import Any


_QUESTIONS_TEXT = """
OXY-CUST-001: Why am I getting DITA-OT warnings in Oxygen 28 that did not appear in Oxygen 26?
OXY-CUST-002: Did Oxygen upgrade the bundled DITA-OT version, and could that change my existing output?
OXY-CUST-003: Why does content that published successfully in the previous Oxygen version now generate warnings?
OXY-CUST-004: How can I determine whether a new warning comes from Oxygen, DITA-OT, or one of my custom plug-ins?
OXY-CUST-005: Can I temporarily use the previous DITA-OT version with the latest Oxygen release?
OXY-CUST-006: Why are duplicate-key warnings appearing only after upgrading Oxygen?
OXY-CUST-007: How can I suppress a known false-positive DITA-OT warning without hiding real errors?
OXY-CUST-008: What should I compare before and after an Oxygen upgrade to detect publishing regressions?
OXY-CUST-009: Why does my old transformation scenario behave differently after importing it into a new Oxygen version?
OXY-CUST-010: How can I verify whether an issue has already been fixed in a newer Oxygen maintenance release?
OXY-CUST-011: Why is my saved PDF publishing template missing some of the settings I configured?
OXY-CUST-012: How can I move a PDF publishing template from one workstation to another?
OXY-CUST-013: Why does the cover image repeat when I force the TOC to start on an odd page?
OXY-CUST-014: How can I add two different pieces of topic content to the PDF front page?
OXY-CUST-015: Can a publishing template retrieve the document title and product version from different metadata elements?
OXY-CUST-016: How can I add custom footer content that changes according to the chapter?
OXY-CUST-017: Why is my footer image cut off after a certain page?
OXY-CUST-018: How can I ensure that every top-level topic starts on a new PDF page?
OXY-CUST-019: Why does a blank page appear between my cover and TOC?
OXY-CUST-020: How can I package fonts, CSS, images, and template settings into one reusable PDF template?
OXY-CUST-021: Why does my PDF build work normally but fail when accessibility mode is enabled?
OXY-CUST-022: Why does enabling PDF/A cause previously working cross-references to fail?
OXY-CUST-023: How can I identify which reference is breaking the accessible PDF build?
OXY-CUST-024: Does PDF accessibility mode require additional metadata on images and links?
OXY-CUST-025: How can I validate whether the generated PDF is properly tagged?
OXY-CUST-026: Why are table headers not correctly associated with cells in the accessible PDF?
OXY-CUST-027: Can decorative images be excluded from the PDF tag structure?
OXY-CUST-028: Why does the accessible PDF contain different bookmarks from the normal PDF?
OXY-CUST-029: What changes when PDF accessibility and archiving modes are enabled together?
OXY-CUST-030: How can I separate a PDF Chemistry issue from invalid DITA accessibility markup?
OXY-CUST-031: Can I generate WebHelp without the oxy_ resource folders?
OXY-CUST-032: What is the purpose of the WebHelp .properties file?
OXY-CUST-033: How can I rename or relocate the generated WebHelp resource directories?
OXY-CUST-034: Can several WebHelp guides share the same JavaScript and CSS resources?
OXY-CUST-035: How do I keep the TOCs of multiple WebHelp publications separate?
OXY-CUST-036: Can I publish several product guides into one enterprise documentation portal?
OXY-CUST-037: How can I prevent links from one product guide from appearing in another product's navigation?
OXY-CUST-038: Why is WebHelp trying to retrieve resources from the root of my drive?
OXY-CUST-039: How can I publish WebHelp directly to an existing website?
OXY-CUST-040: Which WebHelp files must be deployed, and which generated files are optional?
OXY-CUST-041: Why does the WebHelp search page say "No search has been performed" even after entering a query?
OXY-CUST-042: Why are some topics missing from WebHelp search results?
OXY-CUST-043: Can WebHelp search index conrefed content?
OXY-CUST-044: Are indexterm elements used by WebHelp full-text search?
OXY-CUST-045: Should I use keyword, indexterm, or both for search optimization?
OXY-CUST-046: How can I integrate Google search with Oxygen WebHelp Responsive?
OXY-CUST-047: Can I search across several separately generated WebHelp publications?
OXY-CUST-048: Why is resource-only content appearing in search results?
OXY-CUST-049: How can I exclude specific topics or metadata from the WebHelp search index?
OXY-CUST-050: How can I verify that the WebHelp search index was regenerated after a content update?
OXY-CUST-051: Why does my WebHelp template report that no CSS file is specified?
OXY-CUST-052: Why does adding topic.css break zebra striping in my tables?
OXY-CUST-053: How can I reduce the WebHelp header height while keeping the search bar sticky?
OXY-CUST-054: How can I add custom HTML attributes generated from DITA metadata?
OXY-CUST-055: Can I add a download button to the WebHelp home page?
OXY-CUST-056: How do I add a copy button to every generated code block?
OXY-CUST-057: How can I add a custom CSS class based on outputclass?
OXY-CUST-058: Why is my custom CSS loaded in the topic page but not on the landing page?
OXY-CUST-059: How can I migrate an older XSLT WebHelp customization to the current template system?
OXY-CUST-060: How can I ensure my WebHelp customization remains compatible after upgrading Oxygen?
OXY-CUST-061: Why does Oxygen Author freeze while saving a DITA topic?
OXY-CUST-062: How can I determine whether Schematron validation is making saves slow?
OXY-CUST-063: Can automatic reference checking delay file saving?
OXY-CUST-064: Why does saving become slower when a large root map is selected?
OXY-CUST-065: Could a custom framework action or listener block the save operation?
OXY-CUST-066: How can I collect thread dumps when Oxygen freezes during save?
OXY-CUST-067: Why does the same topic save quickly outside the project but slowly inside it?
OXY-CUST-068: Can Git, SVN, or network storage affect Oxygen save performance?
OXY-CUST-069: How can I disable specific save-time checks for troubleshooting?
OXY-CUST-070: What sample files and logs should I provide for an intermittent Oxygen freeze?
OXY-CUST-071: How can I control the ID that Oxygen generates when inserting a new element?
OXY-CUST-072: Why does Oxygen add a unique_ prefix to IDs in generated PDF content?
OXY-CUST-073: Why are hyphens in my topic filename converted to underscores in the generated topic ID?
OXY-CUST-074: Can I configure an ID pattern based on the filename and element type?
OXY-CUST-075: How can I prevent Oxygen from automatically generating IDs for elements that do not need them?
OXY-CUST-076: How can I force Oxygen to generate explicit start and end tags instead of empty-element syntax?
OXY-CUST-077: How can I prevent line breaks from being added between long XML attributes?
OXY-CUST-078: Why does formatting the XML change attribute order or whitespace?
OXY-CUST-079: Can ID-generation rules be shared through an Oxygen framework?
OXY-CUST-080: How can I detect duplicate IDs before publishing?
OXY-CUST-081: How can I make a custom action appear first in the Content Completion Assistant?
OXY-CUST-082: Why is a valid DITA element not appearing in content completion?
OXY-CUST-083: How can I add an organization-specific element insertion action?
OXY-CUST-084: Can content completion be filtered according to the active topic type?
OXY-CUST-085: Why does the reuse-content action automatically insert a ph element?
OXY-CUST-086: Can I configure the reuse action to insert the selected source element type instead?
OXY-CUST-087: How can I collapse specific large elements automatically in Author mode?
OXY-CUST-088: Can attribute-editing text boxes be styled using framework CSS?
OXY-CUST-089: How can I paste copied spreadsheet content as a complete DITA table row?
OXY-CUST-090: Can Oxygen automatically wrap pasted text in the correct DITA structure?
OXY-CUST-091: How can I search across all reusable DITA components in Oxygen?
OXY-CUST-092: Can Oxygen show only elements that are valid conref targets for the current element?
OXY-CUST-093: Why does the reuse-content dialog show elements that are structurally incompatible?
OXY-CUST-094: How can I organize reusable fragments so authors can find them easily?
OXY-CUST-095: Can reusable components be tagged with product, audience, or ownership metadata?
OXY-CUST-096: Why does my conref work in Author mode but fail during publishing?
OXY-CUST-097: How can I determine whether a conref target is inside the active publication?
OXY-CUST-098: Can Oxygen preview the effective content of nested conrefs?
OXY-CUST-099: How can I find every consumer of a reusable fragment before modifying it?
OXY-CUST-100: What is the safest way to reuse DITA topics across several independently versioned products?
OXY-CUST-101: Why do keyrefs stop working when the key map is stored in a Git submodule?
OXY-CUST-102: Can a root map reference key definitions from several Git repositories?
OXY-CUST-103: How should relative paths be managed when Git submodules are checked out at different locations?
OXY-CUST-104: Why do keyrefs work on one developer's computer but fail on another?
OXY-CUST-105: Should key maps be included in the same repository as their consuming topics?
OXY-CUST-106: Can an XML catalog or environment variable provide a portable base path for shared content?
OXY-CUST-107: How should CI clone Git submodules before running DITA publishing?
OXY-CUST-108: Can Oxygen validate key references when a required submodule has not been initialized?
OXY-CUST-109: How should version mismatches between a main repository and shared-content submodule be managed?
OXY-CUST-110: How can I create a reproducible publication from multiple Git repositories?
OXY-CUST-111: Why does a keyref work when publishing the root map but fail when publishing the submap alone?
OXY-CUST-112: Do I need to import parent-map keys into a submap?
OXY-CUST-113: Can one submap be published independently while still using root-map key definitions?
OXY-CUST-114: Why does a keyref to a nested topic element fail even though the topic key resolves?
OXY-CUST-115: Can a key definition point directly to an element inside a nested topic?
OXY-CUST-116: What happens when both the key definition and the keyref contain fragment identifiers?
OXY-CUST-117: Why does Oxygen show a missing-key warning even though the published content appears correctly?
OXY-CUST-118: How do I verify which root map Oxygen is using to resolve the key?
OXY-CUST-119: Can multiple root maps provide different definitions for the same key?
OXY-CUST-120: How should a chatbot explain that a valid submap may still lack an independent key space?
OXY-CUST-121: Why is topicmeta under a topichead not appearing in my WebHelp output?
OXY-CUST-122: Does metadata on a topichead cascade to all child topic references?
OXY-CUST-123: How can I make inherited map metadata available as HTML attributes?
OXY-CUST-124: Why is metadata visible in the map but missing from the generated topic?
OXY-CUST-125: Can a custom metadata element be used for filtering?
OXY-CUST-126: What is the difference between metadata used for filtering and metadata written to output?
OXY-CUST-127: Why does the same topic receive different metadata in two publications?
OXY-CUST-128: How can I see the effective metadata after cascading?
OXY-CUST-129: Can Oxygen display inherited metadata separately from locally authored attributes?
OXY-CUST-130: How can I troubleshoot a filter that works in Author mode but not in WebHelp?
OXY-CUST-131: Why do some cross-references disappear from my generated PDF?
OXY-CUST-132: How can I include the topic number together with the title in an xref?
OXY-CUST-133: Can I customize xref output differently for figures, tables, chapters, and sections?
OXY-CUST-134: Why does a link work in WebHelp but not in PDF?
OXY-CUST-135: How can I suppress the error for an intentionally href-less xref?
OXY-CUST-136: Why are relationship-table links displaying topic short descriptions?
OXY-CUST-137: Can I hide the short description from related-link output without removing it from the topic?
OXY-CUST-138: Why does an xref open the original topic instead of its copy-to instance?
OXY-CUST-139: How are links to topics outside the root-map folder handled?
OXY-CUST-140: Should a topic referenced only through an xref also be included in the map?
OXY-CUST-141: Why does the generated context-help map contain duplicate entries?
OXY-CUST-142: Can the same source topic have different context IDs in separate publications?
OXY-CUST-143: How should context help distinguish between two copy-to instances of one topic?
OXY-CUST-144: Why does a context-help link open the wrong occurrence of a reused topic?
OXY-CUST-145: How can I validate duplicate context IDs before publishing?
OXY-CUST-146: Should a context ID be associated with the source topic or generated output URI?
OXY-CUST-147: Can context-help mappings target an element inside a topic?
OXY-CUST-148: How can context-help URLs remain stable when files are renamed?
OXY-CUST-149: Can scoped keys provide separate context-help targets?
OXY-CUST-150: What should be republished when a context ID changes?
OXY-CUST-151: Why does adding a table column width cause the PDF transformation to fail?
OXY-CUST-152: Why does deleting an image from a table result in a publishing error?
OXY-CUST-153: How can I create a complex table layout that is not directly supported by simpletable?
OXY-CUST-154: Why does the same PDF table render differently on Windows and macOS?
OXY-CUST-155: How can I prevent page breaks between a list item and its image?
OXY-CUST-156: Why does a filtered table become invalid after some cells are removed?
OXY-CUST-157: How can I make table headers repeat correctly across PDF pages?
OXY-CUST-158: Why does an image overflow the table column in PDF but resize correctly in WebHelp?
OXY-CUST-159: Can I group several images and captions as one reusable unit?
OXY-CUST-160: What input files are needed to reproduce a cross-platform PDF layout difference?
OXY-CUST-161: How can I make the message panel of a hazard statement float to the right?
OXY-CUST-162: Why does a hazard statement look correct in WebHelp but not in PDF?
OXY-CUST-163: Can the hazard symbol and message text be placed in separate columns?
OXY-CUST-164: How can I style different hazard types without changing their semantic markup?
OXY-CUST-165: Why does a customized hazard statement break across page boundaries?
OXY-CUST-166: How can I hide lcCorrectResponse placeholders in the learning-assessment Author view?
OXY-CUST-167: Can correct answers remain hidden from normal authors but visible to reviewers?
OXY-CUST-168: How can I customize the Author-mode appearance of learning questions?
OXY-CUST-169: Why are learning-assessment elements visible in Oxygen but missing from published output?
OXY-CUST-170: How can I ensure learning-content customizations work in both Desktop Author and Web Author?
OXY-CUST-171: Why does MathML rendering break when I search within the Oxygen document?
OXY-CUST-172: Why does an equation display correctly before searching but become corrupted after highlighting?
OXY-CUST-173: How can I determine whether a MathML problem belongs to Author mode or the publishing engine?
OXY-CUST-174: Why is extra whitespace being generated around tm elements?
OXY-CUST-175: How can I prevent an unwanted space before or after a ph element?
OXY-CUST-176: Can Schematron detect inline elements that may introduce incorrect spacing?
OXY-CUST-177: Why does the same inline markup produce different spacing in PDF and WebHelp?
OXY-CUST-178: How should trademark text be authored so punctuation remains correct?
OXY-CUST-179: Can Author-mode CSS accurately represent spacing that will occur in published output?
OXY-CUST-180: How can I create regression tests for inline-spacing defects?
OXY-CUST-181: How can I create a custom element for use in a DITA topic?
OXY-CUST-182: Should I use specialization, a constraint, or Schematron for my custom requirement?
OXY-CUST-183: How can I generate sample files for a custom DITA specialization?
OXY-CUST-184: Why does Oxygen report errors for my RELAX NG document-type declaration?
OXY-CUST-185: How does plug-in order in catalog-dita.xml affect grammar resolution?
OXY-CUST-186: What happens when two DITA-OT plug-ins contribute conflicting catalog entries?
OXY-CUST-187: Why does my custom plug-in fail with InvocationTargetException?
OXY-CUST-188: How can I debug XSLT in a custom pdf2 transformation type?
OXY-CUST-189: Why does a custom plug-in work in Oxygen but fail from the command line?
OXY-CUST-190: How should a custom framework and DITA-OT plug-in be packaged for team-wide installation?
OXY-CUST-191: Why does map validation process more resources than the topics visible in my map?
OXY-CUST-192: Can Validate and Check for Completeness ignore unused resources from a key map?
OXY-CUST-193: How can I run the same Oxygen validation scenario from the command line?
OXY-CUST-194: Can I run fix.external.refs.com.oxygenxml during an automated build?
OXY-CUST-195: How can I save the complete transformation log inside the output directory?
OXY-CUST-196: How can I receive alerts when the nightly publishing build encounters warnings or errors?
OXY-CUST-197: Can Schematron warnings be grouped by source topic when validating an entire map?
OXY-CUST-198: How can I distinguish a validation warning from a publishing failure in automated reports?
OXY-CUST-199: What environment details should be recorded to reproduce a command-line build locally?
OXY-CUST-200: How can I compare Oxygen desktop publishing, Oxygen Publishing Engine, and CI output to find configuration differences?
OXY-CUST-201: How can I exclude the mini-TOC from only selected chapters?
OXY-CUST-202: Can outputclass be used to suppress a chapter-level mini-TOC?
OXY-CUST-203: Why does the mini-TOC still appear even after I hide child topics from the main TOC?
OXY-CUST-204: How can I display a mini-TOC only when a chapter has more than one child topic?
OXY-CUST-205: Why do links generated in the mini-TOC have different formatting from normal cross-references?
OXY-CUST-206: Can the mini-TOC show only direct children and exclude deeper descendants?
OXY-CUST-207: How can I change the mini-TOC heading for different languages?
OXY-CUST-208: Why does the mini-TOC include resource-only or hidden topics?
OXY-CUST-209: Can a chapter-specific CSS class control mini-TOC visibility in PDF Chemistry?
OXY-CUST-210: How can I verify whether a mini-TOC issue originates in the merged HTML, CSS, or PDF renderer?
OXY-CUST-211: Why is my DITAVAL excluding content that should be included?
OXY-CUST-212: Why does the same DITAVAL produce different results in Author mode and published output?
OXY-CUST-213: How can I verify which DITAVAL file a transformation scenario actually used?
OXY-CUST-214: What happens when a map contains ditavalref but the transformation also receives a global DITAVAL?
OXY-CUST-215: How are multiple DITAVAL files combined during branch filtering?
OXY-CUST-216: Why is an element excluded when only one of its profiling attributes matches an exclude rule?
OXY-CUST-217: Can an include rule override an exclude rule from another DITAVAL file?
OXY-CUST-218: Why do inherited profiling attributes affect content that has no local conditions?
OXY-CUST-219: How can I see the effective conditions applied to a topic after map processing?
OXY-CUST-220: What files should I provide to reproduce an Oxygen DITAVAL-filtering issue?
OXY-CUST-221: How can users dynamically filter WebHelp content after the site has been generated?
OXY-CUST-222: What is the difference between build-time DITAVAL filtering and runtime WebHelp filtering?
OXY-CUST-223: Can runtime filtering expose content that was excluded during publishing?
OXY-CUST-224: How are available runtime filter values defined in WebHelp?
OXY-CUST-225: Can subject-scheme values populate the WebHelp filtering interface?
OXY-CUST-226: How can I provide friendly labels for profiling values in the filter UI?
OXY-CUST-227: Can users select multiple products or audiences simultaneously?
OXY-CUST-228: How should WebHelp preserve selected filters while navigating between pages?
OXY-CUST-229: Why does dynamically hidden content still appear in WebHelp search results?
OXY-CUST-230: How can I automate testing of runtime filtering combinations?
OXY-CUST-231: Why are keys defined in a subject-scheme map not available in Oxygen Author mode?
OXY-CUST-232: Should subjectdef keys appear in the Insert Key Reference dialog?
OXY-CUST-233: Why can a subject-scheme key publish correctly even though Oxygen marks it unresolved?
OXY-CUST-234: Can the same subject-scheme key be used for both controlled values and variable text?
OXY-CUST-235: How should Oxygen distinguish a taxonomy key from a content-reference key?
OXY-CUST-236: Why do subject-scheme values appear in the Attributes view but not in key-reference completion?
OXY-CUST-237: Does the subject-scheme map need to be loaded in the DITA Maps Manager?
OXY-CUST-238: Can the selected root map change which subject-scheme keys are available?
OXY-CUST-239: What happens when a normal key definition uses the same name as a subject-definition key?
OXY-CUST-240: How can I test consistency between Author suggestions, validation, and DITA-OT publishing?
OXY-CUST-241: Why are my original topic IDs changed in the merged DITA-OT output?
OXY-CUST-242: Can DITA-OT preserve original element IDs after map merging?
OXY-CUST-243: Why does DITA-OT add prefixes to IDs in intermediate files?
OXY-CUST-244: How are duplicate IDs prevented when one topic is reused multiple times?
OXY-CUST-245: Can generated prefixes break custom XSLT that expects source IDs?
OXY-CUST-246: Should custom processing rely on intermediate IDs or source-document IDs?
OXY-CUST-247: How can I map a generated ID back to its original source element?
OXY-CUST-248: How does chunking affect topic and element IDs?
OXY-CUST-249: How does copy-to affect IDs in the merged publication?
OXY-CUST-250: What regression tests should be run before changing DITA-OT ID-generation behavior?
OXY-CUST-251: What output format must a custom validation engine return to Oxygen?
OXY-CUST-252: How should a custom validator report the source file, line, and column?
OXY-CUST-253: Can a custom validation engine report warning, error, and fatal severities?
OXY-CUST-254: How should validation results be represented when the issue originates in a referenced file?
OXY-CUST-255: Can a custom validator return quick-fix information?
OXY-CUST-256: Why are custom validation results not clickable in Oxygen?
OXY-CUST-257: How should filenames containing spaces or non-ASCII characters be encoded in validator output?
OXY-CUST-258: Can a custom validation engine validate an entire DITA map instead of one topic?
OXY-CUST-259: How should duplicate results from Schematron and a custom validator be consolidated?
OXY-CUST-260: How can I test a custom validation engine outside Oxygen before integrating it?
OXY-CUST-261: How can I prevent a Schematron quick fix from adding default attributes?
OXY-CUST-262: Why does a quick fix serialize attributes that were not present in the source?
OXY-CUST-263: Can one quick fix update several DITA files?
OXY-CUST-264: How can a quick fix preserve comments and processing instructions?
OXY-CUST-265: Can a quick fix replace a direct href with a keyref?
OXY-CUST-266: How can a quick fix generate a missing shortdesc placeholder?
OXY-CUST-267: Can quick fixes be limited to specific topic types?
OXY-CUST-268: Why is a quick fix available in Text mode but not Author mode?
OXY-CUST-269: How should quick fixes behave when several validation findings overlap?
OXY-CUST-270: How can Schematron quick-fix changes be tested for unintended XML serialization differences?
OXY-CUST-271: How can I create a custom Author action in an extended DITA framework?
OXY-CUST-272: Can an Author action invoke an XSLT operation on the current topic?
OXY-CUST-273: How can a custom action process all topics referenced by the active map?
OXY-CUST-274: Why does my custom action work in the base framework but not the extended framework?
OXY-CUST-275: How should framework-extension priority be configured?
OXY-CUST-276: Can a toolbar action be enabled only when the cursor is inside a specific element?
OXY-CUST-277: How can a custom action access the active root-map context?
OXY-CUST-278: Can the same framework action run in Desktop Author and Web Author?
OXY-CUST-279: Why does an action modify the XML correctly but not refresh Author mode?
OXY-CUST-280: How should framework customizations be packaged and versioned for an authoring team?
OXY-CUST-281: Why does pasting text into Author mode create unexpected DITA elements?
OXY-CUST-282: Why does copied content lose its profiling attributes?
OXY-CUST-283: Can Oxygen preserve IDs when copying elements between topics?
OXY-CUST-284: How should links be rewritten when content is pasted into another folder?
OXY-CUST-285: Why are copied images saved with unexpected filenames?
OXY-CUST-286: Can pasted HTML tables be converted automatically into valid CALS tables?
OXY-CUST-287: Why does pasting spreadsheet data create mismatched table columns?
OXY-CUST-288: How should tab characters be interpreted when pasting table data?
OXY-CUST-289: Can a custom paste handler normalize smart quotes and non-breaking spaces?
OXY-CUST-290: How can paste behavior be tested across Text, Grid, and Author modes?
OXY-CUST-291: How can I generate a two-column layout for selected chapters only?
OXY-CUST-292: Can one topic switch between one-column and two-column sections?
OXY-CUST-293: Why is a wide table clipped in a two-column PDF layout?
OXY-CUST-294: How can an image span both columns?
OXY-CUST-295: Can chapter titles remain full-width above two-column content?
OXY-CUST-296: Why do footnotes appear in the wrong column?
OXY-CUST-297: How should page breaks work when content flows between columns?
OXY-CUST-298: Can outputclass control column count in PDF Chemistry?
OXY-CUST-299: Why does the same CSS multicolumn rule work in a browser but fail in PDF?
OXY-CUST-300: How can I debug two-column layout problems in the intermediate HTML?
OXY-CUST-301: Can one transformation generate PDFs for several languages?
OXY-CUST-302: How should separate language root maps be organized?
OXY-CUST-303: Can a script iterate over language-specific DITA maps and output presets?
OXY-CUST-304: How should language-specific fonts be selected automatically?
OXY-CUST-305: Why are generated labels displayed in the wrong language?
OXY-CUST-306: How should localized CSS strings be maintained?
OXY-CUST-307: Can one PDF include topics written in several languages?
OXY-CUST-308: Why do Japanese or Chinese characters render as empty boxes?
OXY-CUST-309: How should right-to-left and left-to-right topics coexist in one PDF?
OXY-CUST-310: How can multilingual PDF builds be validated automatically in CI?
OXY-CUST-311: Does DITA-OT plug-in installation order affect catalog-dita.xml?
OXY-CUST-312: Which catalog entry wins when two plug-ins declare the same public identifier?
OXY-CUST-313: Why is Oxygen resolving my custom DTD from the wrong plug-in?
OXY-CUST-314: Can catalog conflicts produce different behavior in Oxygen and command-line DITA-OT?
OXY-CUST-315: How can I inspect the final generated XML catalog?
OXY-CUST-316: Should a specialization plug-in depend explicitly on its base grammar plug-in?
OXY-CUST-317: Why does reinstalling plug-ins change grammar-resolution behavior?
OXY-CUST-318: How should catalog URIs be written so the plug-in remains portable?
OXY-CUST-319: Can framework catalogs override DITA-OT plug-in catalogs?
OXY-CUST-320: What files should be compared when catalog resolution differs between environments?
OXY-CUST-321: Why does adding topic.css change the default styling of WebHelp tables?
OXY-CUST-322: How can custom CSS override only one table without affecting all tables?
OXY-CUST-323: Why does zebra striping stop working after adding custom row styles?
OXY-CUST-324: How can CSS specificity be debugged in generated WebHelp?
OXY-CUST-325: Why is my custom stylesheet loaded before the default WebHelp stylesheet?
OXY-CUST-326: Can I control the order in which custom CSS files are included?
OXY-CUST-327: Why does outputclass appear on a wrapper element instead of the element I expected?
OXY-CUST-328: How can I style only tables generated from properties elements?
OXY-CUST-329: Why does a CSS selector work on topic pages but not search or index pages?
OXY-CUST-330: How should CSS customizations be regression-tested after a WebHelp upgrade?
OXY-CUST-331: Why does the search-results page state that no search was performed?
OXY-CUST-332: How is the user's search query passed to the generated results page?
OXY-CUST-333: Can URL rewriting remove the WebHelp search-query parameter?
OXY-CUST-334: Why does search work locally but fail after deployment to a web server?
OXY-CUST-335: Can restrictive Content Security Policy settings break WebHelp search?
OXY-CUST-336: Why is the search index loaded from an incorrect relative path?
OXY-CUST-337: How can browser caching cause outdated search results?
OXY-CUST-338: Can multiple WebHelp publications conflict when hosted under the same domain?
OXY-CUST-339: How should search failures be diagnosed using browser developer tools?
OXY-CUST-340: Which generated search resources must be retained during deployment?
OXY-CUST-341: How can I hide correct-response placeholders from ordinary authors?
OXY-CUST-342: Can correct answers be shown only when a reviewer profile is active?
OXY-CUST-343: Why does Author-mode CSS hide a placeholder but leave empty space?
OXY-CUST-344: Can learning-assessment elements be collapsed by default?
OXY-CUST-345: How can I visually distinguish correct and incorrect feedback in Author mode?
OXY-CUST-346: Can CSS hide answer metadata without removing it from the source?
OXY-CUST-347: Why are hidden answers still visible in Outline or Attributes views?
OXY-CUST-348: Can a custom Author action toggle answer visibility?
OXY-CUST-349: How should the same customization be deployed in Web Author?
OXY-CUST-350: How can I verify that authoring-only CSS does not affect published assessment output?
OXY-CUST-351: Can Oxygen automatically remove attributes whose values are empty?
OXY-CUST-352: Why do default attributes appear in the serialized XML after validation?
OXY-CUST-353: Are default attributes physically added to the document or only exposed by the parser?
OXY-CUST-354: Can a save-time operation remove empty profiling attributes?
OXY-CUST-355: Should audience="" be treated differently from an absent audience attribute?
OXY-CUST-356: How can Schematron detect and remove redundant attributes?
OXY-CUST-357: Why does formatting or quick-fix processing add schema-defaulted attributes?
OXY-CUST-358: Can empty attributes affect DITAVAL filtering?
OXY-CUST-359: How should namespace declarations that are no longer used be cleaned up?
OXY-CUST-360: How can XML cleanup rules be shared consistently across the authoring team?
OXY-CUST-361: Why does an external Java process inherit unexpected Oxygen environment variables?
OXY-CUST-362: How can I invoke a Java-based validator in a clean environment?
OXY-CUST-363: Why does a command work in the terminal but fail when launched from Oxygen?
OXY-CUST-364: Which Java installation does Oxygen use for external tools?
OXY-CUST-365: How can environment variables be explicitly passed to an external process?
OXY-CUST-366: Why does an external process load Oxygen's bundled libraries instead of its own?
OXY-CUST-367: Can working-directory differences break relative resource paths?
OXY-CUST-368: How should stdout and stderr from an external validator be captured?
OXY-CUST-369: How can timeout and cancellation be implemented for long-running external tools?
OXY-CUST-370: How should Desktop, Web Author, and CI external-tool environments be aligned?
OXY-CUST-371: Why does placement="break" add extra vertical space around images in WebHelp?
OXY-CUST-372: Why did image placement change after upgrading Oxygen or WebHelp?
OXY-CUST-373: How do generated <br> elements affect block-image spacing?
OXY-CUST-374: Why does a CSS workaround behave differently in HTML5 and XHTML serialization?
OXY-CUST-375: Can WebHelp output use a CSS class instead of surrounding break elements?
OXY-CUST-376: Why is PDF Chemistry unaffected by the same image-placement change?
OXY-CUST-377: How should consecutive block images be spaced?
OXY-CUST-378: Can custom XSLT normalize image placement across HTML5 and WebHelp?
OXY-CUST-379: Which intermediate HTML should be inspected for image-spacing defects?
OXY-CUST-380: How can image-placement behavior be regression-tested across publishing versions?
OXY-CUST-381: How can I generate Open Graph metadata for every WebHelp topic?
OXY-CUST-382: Why are custom <meta> elements generated with empty content values?
OXY-CUST-383: How can XSLT access the current topic's title and short description?
OXY-CUST-384: Why does an XPath work against the source topic but not the WebHelp intermediate document?
OXY-CUST-385: How can map-level metadata be added to every generated HTML page?
OXY-CUST-386: Can key-based product names be resolved before generating Open Graph metadata?
OXY-CUST-387: How should missing short descriptions be handled in social metadata?
OXY-CUST-388: Can image metadata be selected differently for each topic?
OXY-CUST-389: How can custom metadata generation remain compatible with several topic types?
OXY-CUST-390: Which WebHelp extension point should be used for custom head metadata?
OXY-CUST-391: How can I find all tracked changes across an entire DITA map?
OXY-CUST-392: Can all changes in a publication be accepted or rejected in one operation?
OXY-CUST-393: Should map-wide review include indirectly referenced and resource-only topics?
OXY-CUST-394: How can I list all topics containing review comments?
OXY-CUST-395: Can comments be removed without accepting or rejecting tracked changes?
OXY-CUST-396: How should submaps be included in a map-wide review operation?
OXY-CUST-397: Can reviewers preview which files will be modified before accepting all changes?
OXY-CUST-398: How should conflicting changes from different reviewers be handled?
OXY-CUST-399: Can change-tracking status be included in CI or release validation?
OXY-CUST-400: How should review metadata be preserved when topics are moved or renamed?
"""


def _parse_questions() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for raw_line in _QUESTIONS_TEXT.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^(OXY-CUST-\d{3}):\s*(.+\?)$", line)
        if match:
            rows.append((match.group(1), match.group(2)))
    return rows


def _category(record_id: str, question: str) -> tuple[str, str, list[str], str]:
    number = int(record_id.rsplit("-", 1)[-1])
    q = question.lower()
    if number <= 10:
        return "oxygen_upgrade_regression", "Oxygen upgrades, bundled DITA-OT changes, warnings, and regression triage", ["oxygen", "dita-ot", "upgrade", "warnings"], "Oxygen editor behavior + bundled DITA-OT implementation"
    if number <= 20:
        return "pdf_chemistry_template", "PDF Chemistry templates, CSS layout, front matter, footers, fonts, and reusable template packaging", ["oxygen", "pdf-chemistry", "css", "template"], "Oxygen PDF Chemistry / CSS-based PDF implementation"
    if number <= 30:
        return "pdf_accessibility_archiving", "Accessible PDF and PDF/A failures, metadata, tagging, bookmarks, and validation", ["pdf", "accessibility", "pdf-a", "dita-ot"], "DITA source semantics + Oxygen PDF Chemistry implementation"
    if number <= 50:
        return "webhelp_search_resources", "WebHelp resources, generated search index, deployment, shared assets, and search behavior", ["webhelp", "search", "resources", "oxygen"], "Oxygen WebHelp implementation"
    if number <= 60:
        return "webhelp_customization", "WebHelp template CSS, custom HTML, outputclass, migration, and upgrade-safe customization", ["webhelp", "css", "template", "outputclass"], "Oxygen WebHelp implementation"
    if number <= 70:
        return "oxygen_author_performance", "Oxygen Author save-time freezes, validation, thread dumps, framework hooks, VCS, and logs", ["oxygen", "author-mode", "performance", "schematron"], "Oxygen editor implementation"
    if number <= 80:
        return "oxygen_ids_formatting", "Oxygen ID generation, XML formatting, duplicate IDs, and team framework rules", ["oxygen", "ids", "formatting", "validation"], "Oxygen editor implementation + DITA ID validity"
    if number <= 90:
        return "oxygen_author_customization", "Content completion, Author actions, framework CSS, paste behavior, and custom authoring assistance", ["oxygen", "author-mode", "framework", "content-completion"], "Oxygen editor/framework implementation"
    if number <= 100:
        return "reuse_conref_governance", "Reusable fragments, conref compatibility, effective content, consumers, metadata, and versioned reuse", ["conref", "reuse", "oxygen", "governance"], "DITA reuse semantics + editor/publisher implementation"
    if number <= 110:
        return "git_submodule_key_governance", "Key maps across Git repositories, submodules, portable paths, catalogs, CI clone strategy, and reproducible publishing", ["keyref", "git", "submodule", "ci"], "DITA key resolution + repository architecture"
    if number <= 120:
        return "root_map_key_context", "Root-map context, submap independence, nested fragments, duplicate key definitions, and chatbot explanation quality", ["keyref", "root-map", "keyspace", "oxygen"], "DITA key resolution + Oxygen root-map context"
    if number <= 130:
        return "metadata_cascade_output", "Cascading topicmeta, inherited metadata, filtering metadata, generated output metadata, and effective context inspection", ["metadata", "topicmeta", "cascade", "webhelp"], "DITA map metadata semantics + output implementation"
    if number <= 140:
        return "xref_related_links", "Cross-reference output, related links, shortdesc, copy-to, outside-map links, and PDF/WebHelp differences", ["xref", "related-links", "copy-to", "pdf"], "DITA linking semantics + output implementation"
    if number <= 150:
        return "context_help_identity", "Context-help maps, duplicate context IDs, output URI identity, copy-to instances, scoped keys, and republishing impact", ["context-help", "copy-to", "keys", "output-uri"], "Oxygen/WebHelp context-help implementation + DITA resource identity"
    if number <= 160:
        return "tables_pdf_layout", "DITA table validity, filtered tables, PDF table layout, images, captions, and cross-platform reproduction", ["table", "simpletable", "pdf", "filtering"], "DITA table model + PDF renderer implementation"
    if number <= 165:
        return "hazard_statement_layout", "Hazard statement semantics, PDF/WebHelp layout, symbols, message panels, and compliance-safe styling", ["hazardstatement", "hazard", "pdf", "webhelp"], "DITA hazard semantics + output styling implementation"
    if number <= 170:
        return "learning_authoring_visibility", "DITA learning assessment visibility, Author-mode CSS, reviewer-only views, and Desktop/Web Author parity", ["learning", "assessment", "oxygen", "web-author"], "DITA learning domain + Oxygen editor implementation"
    if number <= 180:
        return "mathml_inline_spacing", "MathML Author rendering, search highlighting, inline spacing, trademark markup, Schematron, and regression testing", ["mathml", "tm", "ph", "schematron"], "DITA inline semantics + editor/output implementation"
    if number <= 190:
        return "specialization_plugin_debugging", "Specialization, constraints, grammar/catalog resolution, plug-in conflicts, XSLT debugging, and team packaging", ["specialization", "plugin", "catalog", "dita-ot"], "DITA specialization + DITA-OT/Oxygen implementation"
    if number <= 200:
        return "validation_ci_operations", "Map validation, completeness checks, command-line execution, logs, alerts, warning classification, and environment capture", ["validation", "ci", "oxygen", "dita-ot"], "Oxygen validation + DITA-OT/CI implementation"
    if number <= 210:
        return "pdf_minitoc_layout", "Mini-TOC generation, chapter-level CSS/outputclass controls, merged HTML, and PDF Chemistry rendering", ["mini-toc", "pdf-chemistry", "css", "chapter"], "Oxygen PDF Chemistry / CSS-based PDF implementation"
    if number <= 220:
        return "ditaval_branch_filtering", "DITAVAL selection, branch filtering, profiling precedence, inherited conditions, and effective filtered content", ["ditaval", "ditavalref", "branch-filtering", "profiling"], "DITA filtering semantics + Oxygen/DITA-OT implementation"
    if number <= 230:
        return "webhelp_runtime_filtering", "Runtime WebHelp filtering, build-time DITAVAL exclusions, search exposure, subject-scheme labels, and browser-state testing", ["webhelp", "runtime-filtering", "ditaval", "search"], "Oxygen WebHelp implementation"
    if number <= 240:
        return "subject_scheme_authoring", "Subject-scheme keys, controlled values, key-reference completion, root-map context, and validation/publishing consistency", ["subject-scheme", "keys", "oxygen", "validation"], "DITA subject-scheme semantics + Oxygen editor implementation"
    if number <= 250:
        return "dita_ot_intermediate_ids", "DITA-OT merged output IDs, generated prefixes, chunking, copy-to, source-to-output traceability, and XSLT stability", ["dita-ot", "ids", "chunk", "copy-to"], "DITA-OT preprocessing implementation"
    if number <= 260:
        return "oxygen_custom_validation", "Custom validation engine output, severities, source locations, clickable results, URI encoding, map validation, and duplicate consolidation", ["oxygen", "custom-validation", "schematron", "validation"], "Oxygen validation integration"
    if number <= 270:
        return "schematron_quick_fix", "Schematron quick fixes, XML serialization, default attributes, multi-file edits, href-to-keyref migration, and Author/Text mode parity", ["schematron", "quick-fix", "xml-serialization", "keyref"], "Schematron Quick Fix + Oxygen editor implementation"
    if number <= 280:
        return "oxygen_framework_actions", "Custom Author actions, extended frameworks, XSLT operations, root-map access, Desktop/Web Author parity, and team packaging", ["oxygen", "framework", "author-action", "web-author"], "Oxygen framework implementation"
    if number <= 290:
        return "oxygen_paste_handling", "Author-mode paste handling, copied IDs, profiling attributes, path rewriting, image names, CALS table conversion, and smart-character cleanup", ["oxygen", "paste", "cals", "ids"], "Oxygen editor/framework implementation"
    if number <= 300:
        return "pdf_multicolumn_layout", "Two-column PDF layout, outputclass/CSS controls, wide tables, images, footnotes, page breaks, and intermediate HTML debugging", ["pdf-chemistry", "css", "multicolumn", "layout"], "Oxygen PDF Chemistry / CSS-based PDF implementation"
    if number <= 310:
        return "multilingual_pdf_publishing", "Multilingual PDF builds, language root maps, fonts, generated labels, localized CSS strings, RTL/LTR, and CI validation", ["localization", "pdf", "fonts", "rtl"], "DITA localization + PDF implementation"
    if number <= 320:
        return "catalog_resolution_conflicts", "DITA-OT plug-in catalog order, public identifiers, framework catalogs, portable URIs, and environment comparison", ["catalog", "plugin", "specialization", "dita-ot"], "DITA-OT/Oxygen catalog resolution"
    if number <= 330:
        return "webhelp_css_regression", "WebHelp CSS load order, specificity, outputclass wrappers, table styling, properties tables, search/index pages, and upgrade regression tests", ["webhelp", "css", "outputclass", "tables"], "Oxygen WebHelp implementation"
    if number <= 340:
        return "webhelp_search_deployment", "WebHelp search query parameters, URL rewriting, CSP, relative paths, browser caching, multi-publication conflicts, and deployment resources", ["webhelp", "search", "deployment", "browser"], "Oxygen WebHelp implementation"
    if number <= 350:
        return "learning_authoring_visibility", "DITA learning assessment visibility, Author-mode CSS, reviewer-only views, custom toggles, Web Author deployment, and output isolation", ["learning", "assessment", "oxygen", "web-author"], "DITA learning domain + Oxygen editor implementation"
    if number <= 360:
        return "xml_cleanup_defaults", "Empty attributes, schema-defaulted attributes, parser exposure versus physical serialization, DITAVAL impact, namespaces, and team cleanup rules", ["xml-cleanup", "default-attributes", "ditaval", "schematron"], "XML parser/schema behavior + Oxygen editor implementation"
    if number <= 370:
        return "external_tool_environment", "External Java validators, clean environments, Oxygen JVM/libraries, working directories, stdout/stderr, timeout, and Desktop/Web/CI parity", ["oxygen", "external-tools", "java", "ci"], "Oxygen external-tool integration"
    if number <= 380:
        return "webhelp_image_placement", "Image placement behavior, generated break elements, HTML5/XHTML serialization, CSS/XSLT workarounds, intermediate HTML, and regression testing", ["webhelp", "image", "placement", "css"], "DITA image semantics + Oxygen WebHelp implementation"
    if number <= 390:
        return "webhelp_head_metadata", "Open Graph metadata, custom meta elements, XSLT against intermediate documents, map-level metadata, key resolution, and extension points", ["webhelp", "metadata", "open-graph", "xslt"], "Oxygen WebHelp customization"
    if number <= 400:
        return "map_wide_review_tracking", "Tracked changes, review comments, indirect/resource-only topics, submaps, preview of modified files, reviewer conflicts, and release validation", ["oxygen", "tracked-changes", "review", "ci"], "Oxygen review workflow + repository governance"
    if "validation" in q or "nightly" in q or "command line" in q:
        return "validation_ci_operations", "Map validation, completeness checks, command-line execution, logs, alerts, warning classification, and environment capture", ["validation", "ci", "oxygen", "dita-ot"], "Oxygen validation + DITA-OT/CI implementation"
    return "oxygen_customer_troubleshooting", "Customer-language Oxygen, DITA, and DITA-OT troubleshooting", ["oxygen", "dita", "troubleshooting"], "DITA behavior + Oxygen/DITA-OT implementation"


def _short_answer(topic: str, question: str) -> str:
    if topic == "oxygen_upgrade_regression":
        return "Treat this as an environment and processor-version regression first: Oxygen may bundle a newer DITA-OT, updated plug-ins, or changed scenario defaults, so compare versions, plug-ins, parameters, and logs before changing source DITA."
    if topic == "root_map_key_context":
        return "`keyref` resolution depends on the active root map and effective key space; a submap or standalone topic can be valid XML but still lack the key definitions available during root-map publishing."
    if topic == "reuse_conref_governance":
        return "A conref that previews in Oxygen can still fail in publishing when the active publication, filtering, structural compatibility, or preprocessing context differs from the editor context."
    if topic == "webhelp_search_resources":
        return "WebHelp search and resources are generated output artifacts, not pure DITA semantics; inspect the generated index/resources, deployment paths, and filtering/resource-only rules."
    if topic == "pdf_accessibility_archiving":
        return "Accessible PDF and PDF/A modes add stricter tagging, metadata, and reference constraints, so failures often expose missing image/link metadata or renderer-specific PDF conformance issues."
    if topic == "tables_pdf_layout":
        return "PDF table failures usually need two checks: the DITA table must remain structurally valid after filtering, and the PDF renderer must support the requested layout, widths, images, and page breaks."
    if topic == "specialization_plugin_debugging":
        return "Debug specialization and plug-in issues by separating grammar/catalog resolution from DITA-OT transformation behavior and from Oxygen framework configuration."
    if topic == "validation_ci_operations":
        return "For automated validation and publishing, preserve the exact Oxygen/DITA-OT versions, scenario parameters, catalogs, plug-ins, logs, and environment variables used by the build."
    return "Answer this as senior DITA troubleshooting: identify whether the behavior belongs to DITA source rules, DITA-OT processing, Oxygen editor behavior, or output-specific implementation."


def _specific_checks(topic: str) -> list[str]:
    checks_by_topic = {
        "reuse_conref_governance": [
            "Inspect the exact `@conref` URI, topic ID, element ID, and `@conrefend` range if present.",
            "Verify the target element exists after filtering and is the same element type or a structurally compatible specialization.",
            "Confirm the reusable topic or fragment is reachable from the active publication dependency graph, not only from the editor project.",
            "Compare Oxygen Author's resolved preview with DITA-OT preprocessing output to find where the effective content diverges.",
        ],
        "root_map_key_context": [
            "Identify the active root map, selected key scope, imported submaps, and any filtered-out key definitions.",
            "Check whether the submap is being published independently without the parent map that supplies the key space.",
            "For nested targets, verify both the key-defined target and any fragment identifier on the key reference.",
            "Report duplicate key definitions by effective scope and map order after filtering, not merely by file search.",
        ],
        "ditaval_branch_filtering": [
            "List every DITAVAL source: global transformation parameter, branch `ditavalref`, output preset, and editor preview setting.",
            "Inspect effective profiling attributes inherited from map ancestors before deciding why content was excluded.",
            "Check whether branch filtering creates multiple effective copies with different keys, links, and generated resource names.",
            "Compare the authored source with filtered/preprocessed output to prove which rule removed the content.",
        ],
        "subject_scheme_authoring": [
            "Separate subject-scheme controlled values from ordinary key definitions used for link text or variable text.",
            "Verify the subject-scheme map is included through the active root map or project context used by Oxygen.",
            "Check whether Oxygen completion support, DITA-OT publishing, and validation are reading the same map context.",
            "Investigate key-name collisions between `subjectdef` keys and normal content/key-reference keys.",
        ],
        "webhelp_search_resources": [
            "Verify the generated WebHelp search index files were regenerated and deployed with the topic HTML files.",
            "Check browser developer tools for missing JavaScript, blocked resources, wrong relative paths, or CSP failures.",
            "Confirm filtered, resource-only, or conrefed content is included or excluded from the search index as intended.",
            "Test the same output locally and from the target web server to separate generation issues from deployment issues.",
        ],
        "webhelp_search_deployment": [
            "Check the search-query URL parameter, URL rewriting rules, base paths, cache headers, and deployed search resources.",
            "Use browser developer tools to verify index JSON/JavaScript requests, HTTP status codes, and console errors.",
            "Confirm multiple WebHelp publications do not overwrite each other's search assets under the same domain path.",
            "Retain all generated search resources during deployment unless the WebHelp template explicitly supports relocation.",
        ],
        "webhelp_runtime_filtering": [
            "Distinguish build-time DITAVAL exclusion from runtime hiding; runtime filters cannot reveal content removed at publish time.",
            "Verify where runtime filter values and friendly labels are defined, including any subject-scheme-derived metadata.",
            "Check whether hidden runtime content is still present in HTML/search artifacts and whether that is acceptable.",
            "Automate filter-combination tests for navigation, topic body, search results, and persisted browser state.",
        ],
        "pdf_chemistry_template": [
            "Inspect the PDF template package for CSS, fonts, images, parameters, and paths that must move together.",
            "Check page-sequence, front-matter, cover, TOC, and footer CSS separately from DITA source validity.",
            "Compare the merged HTML/intermediate artifacts with rendered PDF to separate transform output from renderer layout.",
            "Validate fonts and image dimensions on the same workstation or CI image used for final publishing.",
        ],
        "pdf_accessibility_archiving": [
            "Validate image alternative text, table header structure, link destinations, bookmark structure, and document metadata.",
            "Separate DITA source accessibility problems from PDF Chemistry tagging/PDF-A conformance behavior.",
            "Run a tagged-PDF validator and inspect the first failing reference or structure element rather than suppressing all warnings.",
            "Check whether accessibility and archiving modes change resource embedding, link validation, or bookmark generation.",
        ],
        "tables_pdf_layout": [
            "Validate CALS table grid consistency after filtering, especially `@morerows`, `@namest`, `@nameend`, and removed cells.",
            "Prefer CALS `<table>` for complex spans; do not expect `<simpletable>` to support full CALS spanning behavior.",
            "Inspect image intrinsic size, column width, page-break rules, repeated headers, and renderer support.",
            "Create a minimal table-only repro for cross-platform PDF layout differences, including fonts and image files.",
        ],
        "dita_ot_intermediate_ids": [
            "Map generated IDs back to source using DITA-OT job/intermediate files instead of assuming merged IDs equal source IDs.",
            "Check reuse, chunking, `copy-to`, and duplicate topic inclusion before changing ID-generation behavior.",
            "Avoid custom XSLT that depends on unstable intermediate IDs when source IDs or generated output URIs are available.",
            "Regression-test links, context help, bookmarks, and copied-topic instances before altering ID logic.",
        ],
        "oxygen_custom_validation": [
            "Confirm the validator returns Oxygen-readable file URI, line, column, severity, message, and optional quick-fix metadata.",
            "Encode spaces and non-ASCII filenames consistently so validation results remain clickable.",
            "For map-level validation, report findings against the actual referenced source file, not only the root map.",
            "Deduplicate findings from Schematron and custom validators by source location, rule ID, and message intent.",
        ],
        "schematron_quick_fix": [
            "Check whether default attributes are parser-exposed or physically serialized by the quick-fix operation.",
            "Test Text mode and Author mode because quick-fix availability and serialization can differ.",
            "Preserve comments, processing instructions, namespaces, and attribute order where the workflow requires clean diffs.",
            "For href-to-keyref fixes, verify the key definition exists in the active root map before rewriting references.",
        ],
        "oxygen_framework_actions": [
            "Verify framework extension priority, inherited actions, operation bindings, and enablement conditions.",
            "If an action processes map topics, confirm it uses the active root-map context and handles submaps consistently.",
            "After XML mutation, refresh Author mode or the relevant document model so the UI reflects the change.",
            "Package framework customizations with versioned dependencies for Desktop Author and Web Author separately.",
        ],
        "oxygen_paste_handling": [
            "Check paste mode, source format, target element context, ID preservation rules, and profiling-attribute copy rules.",
            "For table paste, validate column count, CALS entry structure, spans, and tab/newline interpretation.",
            "Rewrite links and image references relative to the new target folder instead of preserving stale paths.",
            "Normalize smart quotes, non-breaking spaces, and copied HTML only through an explicit paste handler or cleanup rule.",
        ],
        "catalog_resolution_conflicts": [
            "Inspect the effective XML catalog order after plug-in installation and framework catalog contribution.",
            "Check duplicate public identifiers, system IDs, URI rewrites, and plug-in dependencies.",
            "Compare Oxygen resolution with command-line DITA-OT using the same catalogs and working directory.",
            "Use portable catalog URIs rather than workstation-specific absolute paths.",
        ],
        "validation_ci_operations": [
            "Save the full transformation/validation log, DITA-OT version, Oxygen Publishing Engine version, plug-ins, catalogs, and parameters.",
            "Classify findings as grammar validation, Schematron/business-rule warning, reference completeness issue, or publishing failure.",
            "Run the same validation scenario from command line or CI using the same root map and environment.",
            "Record environment details: OS, Java, fonts, locale, filesystem case sensitivity, network paths, and permissions.",
        ],
    }
    return checks_by_topic.get(
        topic,
        [
            "Identify the active root map, output preset/scenario, filters, key scopes, and processor versions.",
            "Compare authored source XML with effective processed content before debugging final output styling.",
            "Collect the smallest reproducible map, topics, assets, configuration files, and full logs.",
        ],
    )


def _answer(record_id: str, question: str, topic: str, description: str, behavior_scope: str) -> str:
    specific_checks = "\n".join(f"- {check}" for check in _specific_checks(topic))
    return (
        f"## Short answer\n"
        f"{_short_answer(topic, question)}\n\n"
        f"## Scope\n"
        f"- Customer-language seed: `{record_id}`.\n"
        f"- Behavior scope: {behavior_scope}.\n"
        f"- This record is a paraphrased Oxygen customer intent, not an authoritative forum citation.\n\n"
        f"## Senior troubleshooting answer\n"
        f"For this question, first classify the symptom under: {description}. Then verify the effective publication context rather than only the opened source file. "
        f"Check the root map or scenario being used, active DITAVAL/profiling values, key and conref availability, installed DITA-OT/Oxygen versions, custom plug-ins/frameworks, and the generated transformation log. "
        f"If editor behavior differs from publishing behavior, compare Oxygen Author/Web Author context against DITA-OT command-line output using the same map, parameters, catalogs, fonts, and resources. "
        f"If HTML/WebHelp and PDF differ, inspect preprocessing output first; if the effective resolved content is identical, continue into the output transform, CSS/template, renderer, and deployment layer.\n\n"
        f"## Topic-specific checks\n"
        f"{specific_checks}\n\n"
        f"## Deterministic checks\n"
        f"- Reproduce with the smallest root map, topic, asset, DITAVAL, and scenario that still shows the issue.\n"
        f"- Capture Oxygen version, bundled or external DITA-OT version, plug-in list, framework, transformation parameters, and full logs.\n"
        f"- Compare source XML with effective processed content and generated output artifacts.\n"
        f"- Label any conclusion as DITA specification behavior, DITA-OT behavior, Oxygen behavior, AEM Guides behavior, or output-specific behavior.\n\n"
        f"## Must not claim\n"
        f"- Do not claim that Oxygen-specific behavior is mandated by the DITA specification.\n"
        f"- Do not claim that a valid source file guarantees identical WebHelp, PDF, editor preview, and CI output."
    )


def get_oxygen_customer_seed_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record_id, question in _parse_questions():
        topic, description, tags, behavior_scope = _category(record_id, question)
        items.append(
            {
                "prompt": question,
                "final_answer": _answer(record_id, question, topic, description, behavior_scope),
                "tags": [record_id, "oxygen-customer-question", *tags, topic],
                "topic": topic,
                "source_type": "oxygen_customer_questions",
                "answer_style": "senior_technical_docs",
                "status": "approved",
            }
        )
    return items
