"""Advanced learned-QA seeds for DITA expert chatbot coverage."""

from __future__ import annotations

import re
from typing import Any

ANSWER_STYLE = "senior_technical_docs"

_QUESTIONS_TEXT = """
Cascading Metadata and Attribute Inheritance
How does metadata cascade from a root DITA map to nested topicref elements?
Which attributes cascade through the DITA map hierarchy, and which attributes do not?
How does metadata cascading differ from XML attribute inheritance?
If an audience attribute is defined on both a parent and child topicref, which value applies to the child?
Are profiling attribute values inherited, merged, or replaced during cascading?
How are multiple space-separated values handled when a child defines the same profiling attribute as its parent?
What happens when product="A" is specified on a map and product="B" is specified on a child topicref?
Can metadata defined in topicmeta cascade to referenced topics?
What is the difference between attribute cascading and metadata inheritance through topicmeta?
Does metadata physically get written into the referenced topic during map processing?
How does cascading behave when one DITA map references another DITA map?
Does metadata from a parent map cascade into the root element of a referenced submap?
How is cascading affected when the referenced map is processed as a resource-only map?
How does processing-role="resource-only" interact with cascading metadata?
If a child explicitly defines an empty attribute value, does that stop cascading?
Can an inherited metadata value be explicitly removed at a lower level?
What is the role of the cascade attribute in DITA?
How does cascade="merge" differ from cascade="nomerge"?
Which attributes are affected by the cascade attribute?
What happens when cascade="nomerge" is set on a parent topicref?
Does cascade="nomerge" stop inheritance, or only value merging?
How are specialized profiling attributes affected by cascading?
Can an attribute specialized from props cascade differently from props?
How does a subject scheme affect validation of cascaded metadata values?
Can subject-scheme-controlled values be inherited from a parent map branch?
How does cascading work when the same topic is referenced from two map branches with different metadata?
Does a topic have one effective metadata context or multiple contexts when reused?
How should a processor handle conflicting metadata applied to the same topic through multiple references?
Can a topic generate different output based on metadata inherited through separate map branches?
How does branch filtering affect inherited metadata?
Does metadata cascade through topicgroup and topichead elements?
Does metadata cascade through reltable, relrow, and relcell structures?
How does linking="none" affect metadata cascading?
How does toc="no" affect inherited metadata?
Can scope, format, or type cascade from a parent topicref?
Why might a profiling value appear in generated output even though it is absent from the topic source?
How can you inspect the effective metadata after DITA map preprocessing?
What intermediate DITA-OT files help diagnose incorrect cascading?
How would you test that cascading metadata works correctly across three nested maps?
How would you distinguish a metadata-cascading defect from a DITAVAL-filtering defect?
Advanced keyref Behavior
What elements are allowed to use keyref?
How does key-reference behavior differ between xref, link, image, keyword, and topicref?
What happens when an xref uses keyref but contains explicit link text?
What happens when an xref using keyref has no link text?
From where is fallback link text obtained?
How can a key definition provide variable text through keyword metadata?
What is the purpose of keydef elements?
Is keydef fundamentally different from a resource-only topicref with keys?
What happens when a key reference is unresolved?
When is fallback content used for an unresolved key reference?
Can a keyref element contain fallback text?
Does fallback text change key resolution or only rendered output?
What happens when the key resolves but the target has no usable title or metadata?
Can a keyword element use keyref to retrieve text without generating a hyperlink?
Can an image use keyref instead of href?
How are image properties inherited from a key definition?
What happens when both keyref and href are present on the same referencing element?
Is href used as a fallback when keyref fails?
Can a topicref use keyref to indirectly reference another topic?
How does a key-referenced topicref affect navigation and TOC generation?
Can a key definition specify navtitle used by key-referenced topic references?
How does locktitle affect titles resolved through keys?
Can a key reference inherit scope, format, and type from its key definition?
Which properties come from the referencing element, and which come from the key definition?
What happens when the referencing element and key definition provide conflicting scope values?
What happens when they provide conflicting format values?
How does key-based addressing improve file renaming and content migration?
Why can key-based addressing still break after a file move?
How should a content-management system update key definitions during asset moves?
How would you test key-based image, topic, and variable references in the same map?
Advanced conref Processing
What are the exact compatibility requirements between a conref source and target element?
Must the source and target have the same element name?
Can a specialized element reuse content from its generalized ancestor?
Can a generalized element reuse content from a specialized descendant?
How does the DITA class attribute determine conref compatibility?
What happens when the source and target elements are structurally incompatible?
Does the target element's local content remain when conref resolves successfully?
When is local content treated as fallback content?
What happens when the conref target cannot be resolved?
Can a conref reference an entire topic?
Can a conref reference a topic body?
Can a conref reference a table row or table entry?
Can a conref reuse an attribute value without reusing an element?
What is the purpose of conrefend?
How does conref range processing work?
What restrictions apply to the start and end elements in a conref range?
Can a conref range cross topic boundaries?
Can a conref range cross parent-element boundaries?
What happens when conrefend precedes the starting conref target?
How are IDs handled in reused content?
Can reused content create duplicate IDs in generated intermediate files?
How should processors rewrite or manage IDs introduced through conref?
How are relative links inside conrefed content resolved?
Are relative links resolved relative to the source topic or the consuming topic?
How are images inside conrefed content resolved?
What happens when conrefed content contains another conref?
Can conrefs be chained through multiple source topics?
How should a processor detect circular conrefs?
What happens when topic A conrefs topic B and topic B conrefs topic A?
How does conditional processing apply to the conref source and conref consumer?
What happens if the source element is excluded by a DITAVAL rule?
What happens if the consuming element is excluded?
Can the same source element be reused hundreds of times safely?
What performance and maintainability problems can excessive conrefs create?
How can conref resolution differ between authoring preview and final publishing?
How would you troubleshoot a conref that works in one publication map but fails in another?
How does xml:lang behave on reused conref content?
Which attributes come from the conref source and which remain from the consuming element?
Can locally specified attributes override attributes from the referenced element?
How would you test nested conrefs, conditional conrefs, and conref ranges together?
Advanced conkeyref Processing
What is the complete resolution process for a conkeyref?
How does conkeyref combine key resolution and element-fragment resolution?
What syntax is used to reference an element through conkeyref?
Can a conkeyref reference the complete resource identified by a key?
When is the slash portion of a conkeyref required?
What happens when the key resolves but the referenced element ID does not exist?
What happens when the key is unresolved but the consuming element contains fallback content?
Can conkeyref be used with scoped keys?
How is a qualified scoped key represented in conkeyref?
Can the same conkeyref resolve to different content in different key scopes?
How does conkeyref enable context-sensitive reuse?
How does moving the reusable source file affect conkeyref consumers?
What must be updated when the key target is moved?
Can the key target itself be an element fragment?
How should a processor combine a fragment in the key definition with a fragment in conkeyref?
Can conkeyref and conref appear on the same element?
Which reference takes precedence if both are present?
Can conrefend be combined with conkeyref?
How are conkeyref ranges resolved?
Can a conkeyref source contain nested key references?
How are relative links within conkeyrefed content resolved?
How does branch filtering affect conkeyref resolution?
What happens when the same key resolves to different reusable elements across branches?
Can the source element be outside the publication map but reachable through a resource-only key definition?
Why might conkeyref fail when a topic is opened outside its map context?
How should an editor discover the correct map context for conkeyref resolution?
How do nested key scopes affect reusable content resolution?
How should circular dependencies involving conkeyref and keyref be detected?
What diagnostic information should be reported for an unresolved conkeyref?
How would you verify that conkeyref does not accidentally resolve against a key from the wrong root map?
copy-to, Resource Identity, and Generated URIs
What is the purpose of the copy-to attribute?
How does copy-to differ from physically copying a source topic?
Does copy-to change the original topic's identity?
What is the effective output URI when copy-to is present?
Can the same source topic be assigned multiple copy-to values?
Why would a publication need multiple output instances of one source topic?
How does copy-to interact with key scopes?
How does copy-to interact with different profiling contexts?
Can two topic references use the same copy-to target?
What happens when duplicate copy-to target names are generated?
Can copy-to point to a resource outside the current directory?
What restrictions apply to the value of copy-to?
How do relative links inside a copied topic behave?
Should links be resolved against the source URI or generated copy URI?
How should links to the original source behave when a copy-to instance is generated?
How does DITA-OT rewrite links for copied topics?
Can a key definition target a topic reference that uses copy-to?
Does a key resolve to the source URI or the copied URI?
How does copy-to affect generated IDs and anchors?
How does copy-to interact with chunking?
What happens when copy-to and branch filtering are used together?
Can a filtered branch still reserve or conflict with a copy-to URI?
Why might HTML5 output honor copy-to while another transformation ignores it?
How should a CMS represent copy-to without creating duplicate source assets?
How would you test that links point to the correct generated copy rather than the original topic?
Chunking and Output Structure
What problem does DITA chunking solve?
What is the difference between source-topic organization and output chunk organization?
What does chunk="to-content" mean?
What does chunk="to-navigation" mean?
What does chunk="by-topic" mean?
What does chunk="by-document" mean?
How can multiple topics be combined into one output file?
How can one multi-topic source document be split into multiple output files?
How does chunking affect cross-reference rewriting?
How are fragment identifiers changed when topics are combined?
What happens to duplicate IDs when several topics are chunked together?
How does chunking interact with copy-to?
How does chunking interact with branch filtering?
How does chunking affect relationship-table links?
Can nested topic references specify conflicting chunking directives?
Which chunking directive takes precedence?
Can chunking behavior differ across transformation types?
Why might a processor ignore unsupported chunk tokens?
How does chunking affect PDF, where output is typically a single document?
How would you validate chunking independently from rendering behavior?
Specialization, Constraints, and Generalization
How does DITA specialization preserve compatibility with base DITA?
What role does the class attribute play in specialization processing?
How is structural specialization different from domain specialization?
Can a specialized element participate in conref with its base element?
Can specialized attributes participate in profiling and filtering?
How are specialized attributes represented in the domains contribution?
What is the purpose of a document-type shell?
Why should specializations normally be integrated through document-type shells?
What is a DITA constraint module?
How does a constraint differ from specialization?
Can a constraint remove elements without defining new semantics?
How can two compatible constraints be combined?
What happens when incompatible constraint modules are integrated?
What is generalization?
When is generalization required?
Can generalized content later be specialized back without information loss?
What information is needed for round-trip generalization and specialization?
How do specializations affect DITA-OT plug-in integration?
Why might specialized content validate but fail during publishing?
How do missing catalog entries affect specialized DTD resolution?
How can a processor recognize a specialized element without knowing its literal element name?
What happens if the class attribute of a specialized element is incorrect?
Can a custom specialization break conref compatibility?
How should Schematron validation complement specialization constraints?
How would you test specialized content across multiple DITA processors?
DITA-OT Processing and Intermediate Representation
What major preprocessing stages occur before DITA-OT transformation?
At which stage are key references resolved?
At which stage are conrefs resolved?
At which stage is map metadata cascaded?
At which stage is filtering applied?
Why does processing order matter for keys, conrefs, and filtering?
What is the purpose of the DITA-OT job file?
What information does the job file contain?
What is the role of the temporary directory?
How can temporary files reveal effective key and conref resolution?
What are .ditamap and .dita intermediate files used for?
Why may intermediate topic URIs differ from source URIs?
How does DITA-OT track source-to-output URI mappings?
What is the purpose of the .job.xml file?
How are copy-to mappings represented during preprocessing?
How are filtered resources represented or removed?
What causes a resource to be marked as resource-only?
What is the difference between a warning, informational message, and fatal error in DITA-OT?
What does an unresolved key warning indicate?
What does an unresolved conref warning indicate?
How can plug-ins override preprocessing or transformation behavior?
Why is overriding core preprocessing risky?
How can two plug-ins conflict through extension points?
Why may the same DITA source publish differently under two DITA-OT versions?
How would you perform a regression analysis after upgrading DITA-OT?
Difficult End-to-End Troubleshooting Scenarios
A keyref works in one map but not another. What processing contexts should be compared?
A conref resolves in the XML editor but fails in DITA-OT. What are the likely causes?
A conkeyref works when publishing the root map but fails when previewing the topic. Why?
A topic receives unexpected audience values even though none are present in the topic. How would you trace them?
A child topic unexpectedly has both parent and local product values. Which cascading rule should be examined?
A key resolves to different files depending on map order. What duplicate-definition behavior should be investigated?
A submap's keys are not visible in the parent publication. What map integration conditions should be checked?
A key inside a nested key scope resolves globally. What scope-construction defect might exist?
The same reused topic shows different variable values in two branches. How can you determine whether this is correct scoped behavior?
Two filtered branches overwrite each other's HTML files. Which branch-renaming properties are likely missing?
A direct href works, but an equivalent keyref does not. Which parts of the key definition should be validated?
A conrefed image path breaks only after publishing. Relative to which source should the image URI have been resolved?
A conref range includes too many elements. What structural boundary rules should be checked?
Circular conrefs cause a processor hang instead of an error. What protection should the processor implement?
A key definition is excluded, but its key remains usable. Which processing-order issue should be investigated?
An external URL is treated as a local file. Which scope and format values should be checked?
A %20 URI works in one processor but not another. What URI normalization differences should be investigated?
A file reference works on Windows but fails in a Linux pipeline. Which case-sensitivity and path-separator issues should be tested?
A resource-only topic unexpectedly appears in the TOC. Which map-level overrides or processor defects could cause it?
A topic with toc="no" is missing entirely from output. What semantic misunderstanding may exist?
Related links are generated in the wrong direction. Which linking values should be inspected?
A relationship-table link points to the original source rather than a copy-to instance. Which URI mapping stage may be faulty?
An inherited conditional value is not recognized by the subject scheme. What effective-value validation should be performed?
A specialized element fails conref compatibility even though it derives from the same base. Which class tokens should be compared?
HTML5 output resolves all keys, but Native PDF leaves one unresolved. How would you separate preprocessing defects from renderer defects?
A topic appears twice in output after reuse under two key scopes. How would you determine whether the duplication is expected?
Moving a source topic breaks indirect references even though keys were used. What dependency was not updated?
An editor shows an outdated key target after a key definition changes. What caching or map-context problem might be responsible?
Two root maps are open, and the editor resolves a key against the wrong map. What context-selection rules should the editor follow?
A DITAVAL excludes a topic but a conref to content inside that topic still resolves. Is that behavior necessarily incorrect?
A filtered-out key definition continues to provide variable text. What distinction between resource filtering and key-space construction must be examined?
A topic copied using copy-to links back to its source instead of its copied sibling. What link-rewriting data should be inspected?
A map validates but produces a circular-reference error only during publishing. Which references are not normally detectable by grammar validation?
A nested map causes metadata to be duplicated rather than inherited once. What merge behavior should be checked?
A topic's locally specified profiling value disappears after map processing. Could cascade="nomerge" explain it?
A scoped key works for xref but fails for conkeyref. Which syntax and fragment-resolution differences should be checked?
A link generated from a key has the wrong title. Which precedence rules among explicit link text, key metadata, navtitle, and target title should be evaluated?
A topic referenced normally and as resource-only is not published. How should the effective processing role be determined?
A branch-specific conkeyref resolves to content from another branch. What key-scope leakage should be tested?
A topic is published correctly but the chatbot gives the wrong explanation of why. How would you design a source-grounded evaluation to detect the hallucination?
Challenging DITA Expert Questions
A root map sets audience="admin", a nested topicgroup sets audience="developer", and a child topicref sets audience="reviewer". What is the child's effective audience under merge and no-merge behavior?
How can you determine whether metadata came from the source topic, a parent topicref, a referenced map, or a subject scheme?
Can a descendant topicref stop only one inherited profiling value while retaining the others?
What happens when the same topic is referenced from two branches with different inherited platform values?
Does cascading affect only filtering, or can it also influence link generation, search metadata, and publishing behavior?
How should a processor handle metadata conflicts between a map reference and the root element of the referenced map?
Can metadata cascade through a topichead even though the topichead has no target resource?
How does cascade="nomerge" affect a child that does not define the same attribute locally?
If a profiling attribute contains multiple values, are inherited and local values treated as sets, ordered lists, or strings?
How should a chatbot explain the difference between authored metadata and effective metadata without claiming the topic file was modified?
A key is defined three times: once globally, once inside a filtered branch, and once inside a key scope. Which definition should an unqualified reference use?
How should duplicate key definitions be resolved when one definition appears in a referenced map and another in the root map?
Can map order change the effective key definition, and if so, under what processing context?
What happens when a key definition is valid before filtering but removed after conditional processing?
Can a key definition point to another key definition that points to a third key?
How should a processor detect and report a circular chain of indirect key definitions?
If two key definitions use the same key name but different scope values, which properties come from the selected definition?
Can a key be valid for variable text but invalid as a link target?
What happens when a key definition has metadata but no href, and an xref references that key?
How should key resolution behave when the same submap is included twice under different key scopes?
An xref has a keyref, explicit text, and the key definition has a navtitle. Which text should be displayed?
What happens when a key-resolved target has no title, no short description, and the referencing element contains no fallback text?
Can scope, format, type, or role values be inherited through a key definition?
What happens when the referencing element and key definition provide conflicting format values?
Does locally authored link text override text derived from key metadata?
Can a keyword using keyref resolve text without creating a hyperlink?
What is the expected behavior when keyref resolves successfully but the target URI is broken?
Can keyref reference an element fragment rather than an entire topic?
What is the difference between an unresolved key and a resolved key with an invalid target?
How should an editor display a key-based reference when the active root map changes?
What exact conditions determine whether a conref source and target are structurally compatible?
Can a specialized element conref content from its base element?
Can a base element conref content from a specialized element without generalization?
What happens when the conref source contains attributes that are not permitted on the consuming element?
Which attributes belong to the source element after conref resolution, and which remain from the consuming element?
How are IDs inside reused content handled when the same source is reused multiple times?
What happens when reused content contains relative image paths and nested cross-references?
Are relative URIs inside conref content resolved against the source file or the consuming file?
Can conref reuse create duplicate ID collisions after chunking?
How should a processor behave when the conref target exists but has the wrong specialization ancestry?
A conkeyref resolves in one branch but not another even though both branches use the same topic. What scope-related conditions should be compared?
Can a conkeyref target be changed without modifying the consuming topic?
What happens when the key resolves to a topic but the requested element ID does not exist?
Can a fully qualified scoped key be used inside conkeyref?
How should nested key-scope qualification be represented in a conkeyref?
What happens when a conkeyref source contains another conkeyref?
Can a conkeyref participate in a conref range using conrefend?
How should a processor resolve a conkeyref when the key definition already contains a fragment identifier?
Can two branches reuse the same consumer topic while resolving the same conkeyref to different source fragments?
Why might conkeyref work in publishing but fail in standalone editor preview?
How does xml:base affect relative href, conref, and map-reference resolution?
What happens when xml:base is applied at multiple nested levels?
How should spaces and non-ASCII characters be represented in DITA URIs?
Why might the same URI work on Windows and fail on Linux?
Can two different relative URIs resolve to the same canonical resource?
How should case sensitivity be handled when a CMS stores assets case-insensitively but publishing runs on Linux?
What happens when a URI contains both a query component and a fragment identifier?
Can a direct URI reference point outside the publication root?
How should a processor distinguish a file-system path from a valid URI?
What diagnostic information should be reported when the file exists but the DITA fragment target does not?
How are multiple ditavalref elements on the same branch combined?
Can branch filtering produce multiple output copies of the same source topic?
How are output filename collisions prevented when the same topic is included through different branch filters?
How do resourceprefix and resourcesuffix affect generated URIs?
How do keyscopeprefix and keyscopesuffix affect branch-specific key resolution?
What happens when a cross-reference points to a topic excluded only in one branch?
Can a key definition remain available even if the topicref carrying it is filtered?
How should filtering interact with relationship-table-generated links?
Can a conref source be excluded while the conref consumer remains included?
How would you determine whether unexpected content comes from incorrect filtering or incorrect metadata cascading?
Can a subject scheme provide default values, or does it only constrain allowed values?
What happens when an inherited profiling value is not allowed by the active subject scheme?
Can different branches of one publication use different subject scheme contexts?
How should a processor handle multiple subject schemes defining conflicting controlled values for the same attribute?
Can subject schemes constrain specialized attributes derived from props?
How does subject scheme hierarchy differ from ordinary map hierarchy?
Can a subject scheme affect filtering even when no DITAVAL file is used?
What happens when an author uses a valid parent subject value but an invalid child value?
How should an editor determine which controlled values to show when multiple root maps are possible?
How would you verify whether a missing drop-down value is caused by the subject scheme, editor caching, or incorrect map context?
How does a mapref integrate the referenced map into the parent map's processing context?
Can a referenced map contribute keys while its topics remain excluded from navigation?
What is the difference between toc="no" and processing-role="resource-only"?
Can a resource-only topic still be used as a conref or key target?
What happens when the same topic is referenced once normally and once as resource-only?
Does processing-role cascade through referenced maps?
Can a topichead establish metadata, key scope, or filtering context for descendants?
How does navref differ semantically from including a submap through mapref?
Can keys from a navigation-referenced map participate in the parent key space?
What should happen when two nested maps reference each other indirectly?
When a topicref uses copy-to, which URI becomes the effective output identity?
Can two references to the same source topic use different copy-to targets?
How should links between two copied topic instances be rewritten?
Can a key definition resolve to a copied output identity rather than the source URI?
What happens when two map branches generate the same copy-to value?
How does copy-to interact with branch filtering and output renaming?
What happens to element fragment links when several topics are chunked into one file?
How are duplicate IDs handled when reused topics are combined through chunking?
Can transformation types legitimately differ in how they honor chunking instructions?
How would you distinguish a source-reference problem from an output-URI rewrite defect?
Why is the DITA class attribute more important than the literal specialized element name during processing?
Can two specialized elements with different names be conref-compatible?
What happens when a specialization has an incorrect or incomplete class attribute?
How can a constraint module restrict content without defining new semantics?
Can conflicting constraint modules be included in the same document-type shell?
Why might specialized content validate successfully but fail in DITA-OT?
How does generalization help processors that do not understand a custom specialization?
Can generalization lose information required to reconstruct the original specialized document?
How should specialized profiling attributes be represented for filtering and subject scheme use?
What tests should be run when upgrading a specialization from one DITA version to another?
A keyref works in DITA-OT HTML5 but fails in Native PDF. Which processing stages should be compared first?
A conref appears correctly in the editor but not in published output. What cached or intermediate artifacts should be inspected?
A subject scheme works in one root map but not another. Which map-context and inheritance factors should be compared?
A warning appears for an inactive tab in the Schematron panel. Is this a DITA issue, validation-engine issue, or editor-state issue?
Validation errors disappear when switching tabs. What state-management defect does this suggest?
A moved topic still resolves through a direct href but not through a key. What key-definition update may be missing?
A moved key-definition map causes hundreds of unresolved references. What dependency graph should the CMS maintain?
The editor and publishing pipeline choose different effective key definitions. What root-map, filtering, or precedence differences should be examined?
A topic publishes twice under two key scopes. How do you determine whether this is expected reuse or unintended duplication?
When the DITA specification is silent but two processors behave differently, how should the chatbot present the answer without hallucinating a universal rule?
Varied DITA Expert Evaluation Questions
Explain the difference between authored metadata and effective metadata in a DITA publication.
Explain why keyref requires a map context while href does not.
Explain how a DITA processor constructs the effective key space.
Explain the difference between content reuse and topic reuse in DITA.
Explain why a conkeyref can resolve differently in two branches of the same map.
Explain how metadata cascading differs from conditional processing.
Explain how a subject scheme influences authoring and validation.
Explain the role of the root map in key resolution.
Explain why a topic can publish correctly but fail during standalone preview.
Explain the difference between resource identity and output identity.
Compare href, keyref, conref, and conkeyref.
Compare scope and keyscope.
Compare topicref, mapref, navref, and anchorref.
Compare toc="no" with processing-role="resource-only".
Compare copy-to with physically duplicating a topic.
Compare global filtering with branch filtering.
Compare cascade="merge" and cascade="nomerge".
Compare a subject scheme map with a normal DITA map.
Compare conref reuse with key-based variable substitution.
Compare DTD validation, RELAX NG validation, and Schematron validation.
What will be the effective audience value if the parent has audience="admin" and the child has audience="developer"?
What happens when a child defines no local profiling value but its parent defines one?
What happens when a keyref points to a key definition that has no href?
What happens when conref resolves successfully but the consuming element contains local text?
What happens when a conkeyref key resolves but the requested element ID does not exist?
What happens when a resource-only topic is also referenced normally elsewhere?
What happens when the same key is defined twice in the same effective scope?
What happens when a DITAVAL excludes the target of an xref?
What happens when a referenced topic exists but its fragment identifier is invalid?
What happens when two branches generate the same copy-to output name?
Correct-the-Statement and Adversarial DITA Questions
Correct this statement: "All attributes automatically cascade in DITA maps."
Correct this statement: "cascade="nomerge" disables all metadata inheritance."
Correct this statement: "keyref is simply another syntax for href."
Correct this statement: "A conref can reuse any XML element."
Correct this statement: "toc="no" prevents the topic from being published."
Correct this statement: "Keys are always globally available."
Correct this statement: "A subject scheme automatically filters content."
Correct this statement: "A resource-only topic cannot be used anywhere in output."
Correct this statement: "If a key resolves, its target must also exist."
Correct this statement: "Editor preview and published output must always behave identically."
A keyref works in one root map but fails in another. What should be checked?
A conref works in the editor but fails during publishing. What are the likely causes?
A conkeyref works in HTML5 but fails in Native PDF. How would you isolate the issue?
A topic receives unexpected conditional metadata. How would you trace its origin?
A DITAVAL rule appears to be ignored. What should be validated?
A topic is missing from the TOC but is still generated. What map properties should be checked?
A topic is present in the TOC but has no separate output file. What processing behavior may explain it?
A referenced image works locally but fails in Jenkins. What platform-specific issues should be investigated?
A key-based link has the wrong link text. What precedence sources should be checked?
A topic publishes twice after introducing key scopes. How would you determine whether this is expected?
Why could a key resolve against the wrong map when multiple maps are open?
Why could Schematron warnings from an inactive topic appear in the active topic's panel?
Why could validation errors disappear after switching editor tabs?
Why could a cached key target remain visible after updating a key definition?
Why could a topic move break keyref even though indirect addressing is being used?
Why could a conrefed image resolve relative to the wrong topic?
Why could branch-filtered topics overwrite one another?
Why could two processors generate different related links from the same relationship table?
Why could a subject scheme dropdown contain outdated values?
Why could duplicate key definitions behave differently after filtering?
How would you design a key naming convention for a repository containing multiple products and versions?
How would you organize reusable conref fragments to avoid circular dependencies?
How would you design root-map selection in a DITA editor?
How would you represent DITA dependency relationships in a database?
How would you safely support asset rename and move operations?
How would you design a reusable product-specific map using key scopes?
How would you design a validation framework combining DTD and Schematron?
How would you manage reusable content shared across multiple releases?
How would you prevent keys from leaking between sibling scopes?
How would you design a DITA chatbot that distinguishes specification behavior from AEM Guides behavior?
When should direct URI addressing be preferred over key-based addressing?
When should conref be avoided?
When should conkeyref be preferred over conref?
What are the best practices for naming keys?
What are the best practices for maintaining subject schemes?
What are the best practices for writing reusable DITA fragments?
What are the best practices for deeply nested maps?
What are the best practices for DITAVAL management?
What are the best practices for preventing broken cross-references?
What are the best practices for debugging DITA-OT preprocessing?
How should a CMS index direct and indirect DITA dependencies?
How can key resolution be cached without returning stale results?
What should invalidate a cached key space?
How should a CMS handle hundreds of maps referencing the same reusable topic?
How can conref-heavy repositories affect publishing performance?
How should circular-reference detection scale for large repositories?
How should dependency recalculation work after moving a key-defining map?
How can branch filtering increase the number of generated topic instances?
How should a publishing system avoid output URI collisions?
How should a large DITA repository be partitioned for efficient search and publishing?
Why can deeply chained key references slow down processing?
What performance impact can nested conrefs have?
How can large subject scheme maps affect editor performance?
Why can opening multiple maps increase key-resolution time?
How can excessive relationship tables affect link-generation performance?
What parts of DITA preprocessing are good candidates for caching?
What risks arise from caching filtered map results?
How can incremental publishing reduce DITA build time?
How would you measure key-resolution performance?
How would you detect whether slowdown comes from retrieval, validation, or transformation?
What errors should grammar validation detect that Schematron should not duplicate?
What business rules are better implemented in Schematron?
How should warning, error, and fatal severities affect save behavior?
Can Schematron validate cross-file dependencies?
How would you validate that every keyref has an effective definition?
How would you validate that every conref target has a compatible DITA class?
How would you detect duplicate IDs across reused content?
How would you validate that every DITAVAL value exists in the subject scheme?
How would you test validation state across multiple open editor tabs?
How should validation results be associated with individual editor documents?
Why might a topic be present in HTML5 but absent from PDF?
Why might a cross-reference work in PDF but fail in HTML5?
How does chunking affect generated filenames?
How should links be rewritten after copy-to processing?
How should fragment identifiers behave when several topics are combined into one output file?
Why can TOC behavior differ from topic generation behavior?
How can output presets change effective publishing behavior?
What information should be preserved in the DITA-OT temporary directory for debugging?
How can intermediate files reveal the effective metadata context?
What should be compared when two DITA-OT versions generate different results?
How does AEM Guides determine the active root map for an opened topic?
What should happen when multiple root maps define the same key?
How should AEM Guides update references after moving a DAM asset?
How should outgoing references display self-references?
How should incoming references distinguish direct and indirect references?
How should the Editor display unresolved conkeyrefs?
How should validation results behave when users switch between multiple topic tabs?
How should the Schematron panel identify the file associated with each issue?
How should Native PDF and DITA-OT publishing differences be presented to users?
What should be captured in a Jira for an AEM Guides key-resolution defect?
Create a test scenario for duplicate key definitions.
Create a test scenario for nested key scopes.
Create a test scenario for a conref range spanning invalid boundaries.
Create a test scenario for branch-filtered duplicate output filenames.
Create a test scenario for a resource-only topic used as a conref source.
Create a test scenario for a keyref that works in one root map but fails in another.
Create a test scenario for subject scheme values inherited through a referenced map.
Create a test scenario for tab-specific Schematron validation results.
Create a test scenario for URI case sensitivity between Windows and Linux.
Create a test scenario for stale key resolution after moving a map.
Since conkeyref is indirect, it should always survive moving the target file. Is this correct?
Since a key is defined in a submap, it must be visible everywhere in the root map. Is this correct?
Since a topic is resource-only, it cannot contribute any content to output. Is this correct?
Since toc="no" hides the topic from navigation, the topic should not be generated. Is this correct?
Since a subject scheme defines allowed values, it must automatically exclude invalid content. Is this correct?
Since the editor resolves a key, every publishing engine must resolve it identically. Is this correct?
Since a conref target exists, the conref must be valid. Is this correct?
Since two URIs look different, they must point to different resources. Is this correct?
Since a warning does not block save, it does not need to remain visible after tab switching. Is this correct?
Since a DITA file validates against its DTD, it cannot contain broken key references. Is this correct?
A topic is reused under two key scopes, filtered by two DITAVAL files, and assigned two copy-to names. What processing contexts must remain separate?
A conref source is resource-only, conditionally excluded, and referenced through a key. Which processing stages determine whether reuse succeeds?
A child map defines a key also defined in the parent map and is included under a key scope. Which definition should consumers use?
A topic has inherited audience, local product, and a branch-specific DITAVAL. How is its effective filtering context calculated?
A key definition contains a fragment, while the conkeyref also contains an element identifier. How should the target be interpreted?
A topic is referenced directly, through a key, and through copy-to. How many identities may be involved?
A map is reused under two scopes and two different conditional contexts. Can the same source topic produce four effective instances?
A relationship table points to branch-filtered copied topics. How should links be generated?
A specialized element is reused through conkeyref under different subject scheme contexts. What validation and compatibility checks apply?
A topic opened standalone has unresolved keys, but publishing succeeds. Which behaviors are specification-related and which are editor-specific?
Why is my key not picking from the map?
Root map ke bina keyref resolve hoga kya?
Same key alag branches mein different value kyun de raha hai?
Parent metadata child topic pe automatically kaise aa raha hai?
conref source file move karne ke baad break kyun hua?
Topic save ho raha hai but warning dusre tab ki show ho rahi haiâ€”why?
Tab switch karte hi Schematron error clear kyun ho raha hai?
toc="no" diya hai phir bhi topic publish kyun hua?
Resource-only topic output mein indirectly kaise aa gaya?
HTML5 mein keyref chal raha hai but Native PDF mein fail kyun ho raha hai?
Did the answer distinguish scope from keyscope?
Did the answer identify the need for an active key space?
Did the answer incorrectly claim that all metadata cascades?
Did the answer separate source content from effective processed content?
Did the answer distinguish unresolved keys from broken key targets?
Did the answer identify processor-specific behavior?
Did the answer provide deterministic troubleshooting steps?
Did the answer invent any DITA element or attribute?
Did the answer correctly identify assumptions?
Did the answer cite the relevant source section?
Can filtering change which duplicate key definition becomes effective?
At what point should key scopes be constructed relative to branch filtering?
Can effective metadata differ for two instances of the same source topic?
How should a processor preserve context when a topic is reused under multiple scopes?
Can conref resolution change the effective dependency graph after preprocessing?
How should IDs be rewritten when reused content is duplicated through branch filtering?
What is the difference between source URI, resolved URI, normalized URI, and output URI?
How should a processor handle a valid key definition whose target is outside the publication context?
How can a chatbot determine whether a behavior is normative, implementation-defined, or a product defect?
When multiple valid processing interpretations exist, how should the chatbot answer without presenting one implementation as universally correct?
Broader DITA Expert Coverage Questions
How should xml:lang be applied in a DITA topic?
Does xml:lang cascade to child elements?
How does xml:lang affect generated language-specific text?
What happens when a topic's xml:lang differs from the map's language?
How should mixed-language content be represented in DITA?
How does language affect quotation marks, labels, and generated headings?
How should translated topics preserve IDs used by cross-references?
Should translated DITA files use the same filenames as source-language files?
How can key-based references support multilingual publications?
How can product names be excluded from translation?
What is the purpose of the translate attribute?
What happens when translate="no" is applied to a parent element?
Can a child override an inherited translate="no" value?
How should variable text be localized when it is supplied through keys?
How should conref source content be managed across multiple languages?
Can one language topic conref content from another language topic?
How can an incorrect xml:lang value affect PDF publishing?
Why might generated labels remain in English after switching the publication locale?
How should fallback behavior work when a translated topic is missing?
How would you test localization across English, German, French, Arabic, and Japanese outputs?
What is the purpose of the dir attribute in DITA?
What is the difference between dir="ltr", rtl, and lro or rlo behavior?
How should bidirectional content be handled inside code examples?
What happens when an Arabic paragraph contains English product names?
Can directionality be applied to an inline phrase?
How should table column order behave in right-to-left output?
How should numbered lists render in an RTL publication?
How should punctuation be handled in mixed RTL and LTR content?
Why might RTL content appear correct in HTML5 but incorrect in PDF?
How would you determine whether an RTL defect belongs to DITA processing, CSS, fonts, or the rendering engine?
When should a bookmap be used instead of a normal DITA map?
What is the semantic role of booktitle?
What is the difference between mainbooktitle and booktitlealt?
What is the purpose of bookmeta?
How is bookmeta different from ordinary topicmeta?
What is the purpose of frontmatter?
What is the purpose of backmatter?
How should prefaces, dedications, notices, and colophons be represented?
What is the difference between chapter, part, and appendix?
Can a regular topic reference be placed inside a chapter?
How should nested chapters be handled?
What happens when an appendix is placed before a chapter?
How should chapter numbering be controlled?
Can frontmatter pages use Roman numerals while body pages use Arabic numerals?
How can body page numbering restart at page 1?
Can backmatter page numbers be excluded from the table of contents?
How should blank pages be inserted for recto-verso publishing?
How should running headers differ for chapters and appendices?
How should book-level metadata appear in PDF properties?
How would you troubleshoot incorrect chapter order in generated PDF?
How is the table of contents generated from a DITA map?
What controls the depth of the generated TOC?
Can an element appear in the TOC without having a separate output page?
Can a generated topic be excluded from the TOC?
How does navtitle affect TOC text?
How does locktitle affect TOC text?
What happens when a topic has no title but its topic reference has a navtitle?
How should duplicate topic titles be handled in the TOC?
What is the purpose of booklists?
How is a list of figures generated?
How is a list of tables generated?
How is an index list generated?
How is a glossary list generated?
What happens when a generated list is declared but contains no entries?
Can generated lists be conditionally included?
How should generated-list titles be localized?
How would you test TOC consistency between HTML5 and PDF output?
What is the purpose of the indexterm element?
How are primary and secondary index terms represented?
How are tertiary index terms represented?
What is an index range?
How are start and end markers defined for an index range?
What happens when an index range has a start marker but no end marker?
How are duplicate index terms consolidated?
Are index terms case-sensitive?
How should singular and plural index terms be managed?
How can "see" and "see also" references be defined?
Can index terms be reused through conref?
Can index terms be conditionally filtered?
How should index terms inherited from reused content behave?
Can index terms be generated from map metadata?
How should index terms be sorted for different languages?
Why might an index entry appear in HTML5 but not in PDF?
How should page ranges be generated for repeated terms?
What happens when multiple index terms point to the same page?
How can nested index terms affect output formatting?
How would you validate that all index range markers are correctly paired?
What is the purpose of a glossary entry topic?
What is the difference between a glossary term and a glossary definition?
How are acronym and abbreviation forms represented?
How can the first occurrence of an acronym differ from later occurrences?
How can keys be used to insert glossary terms?
How should plural forms of glossary terms be handled?
Can one glossary entry contain multiple surface forms?
How should glossary terms be localized?
How should a glossary list be generated from referenced entries?
What happens when two glossary entries define the same term differently?
Can glossary entries be scoped by product or version?
How can conditional processing affect glossary inclusion?
Can glossary definitions be reused through conkeyref?
How should terminology validation be implemented with Schematron?
How would you detect use of a forbidden term in DITA content?
How should preferred and deprecated terminology be represented?
Can a glossary entry exist as resource-only content?
How should glossary links behave in PDF output?
How should glossary popups behave in HTML5 output?
How would you prevent inconsistent terminology across multiple maps?
What is the difference between note, tip, important, caution, warning, and danger?
Are all note types semantically equivalent?
How should hazard statements be structured in DITA?
What is the purpose of hazardstatement?
What is the purpose of hazardsymbol?
How should signal words be generated for hazard statements?
Can hazard symbols be SVG images?
How should accessibility text be supplied for hazard symbols?
How should severity levels be mapped to visual styles?
Can a hazard statement be reused through conref?
How should conditional processing be applied to safety statements?
What happens if a warning is excluded for one product but required for another?
How can Schematron ensure that a hazard statement includes a consequence and avoidance instruction?
How should safety notices be translated without altering regulated signal words?
Why might a hazard icon render in HTML but not in PDF?
How should hazard statements be numbered, if required?
What is the difference between semantic hazard markup and a styled paragraph?
How can product-specific hazards be maintained without duplicating complete topics?
How should missing hazard symbols be reported during publishing?
How would you validate compliance-sensitive safety content before release?
How should an image be referenced in DITA?
What is the difference between inline and block image placement?
How do width, height, and scale interact?
What happens when both dimensions and scale are specified?
How should responsive image behavior be handled in HTML5?
How should high-resolution images be managed for PDF?
Can SVG files contain links to external resources?
How should embedded fonts in SVG be handled?
Why might an SVG appear in the editor but disappear in PDF output?
How should an SVG's accessible title and description be provided?
Can SVG images be reused through keys?
How should image filenames containing spaces be represented?
What happens when the image format does not match the format attribute?
How should missing images affect publishing severity?
How is MathML included in DITA?
What is the difference between inline and block mathematical expressions?
How can MathML rendering differ between HTML and PDF?
What happens when the publishing engine does not support a MathML element?
How should fallback images be provided for mathematical content?
How would you test image, SVG, and MathML support across all output formats?
What accessibility information should be added to images?
When should alternative text be empty?
How should complex diagrams be described?
How should table headers be identified for screen readers?
How should row and column header relationships be represented?
How should link text be written for accessibility?
Why is "click here" weak link text?
How should heading levels be maintained in topic-based authoring?
Can map hierarchy create inaccessible heading jumps?
How should keyboard instructions be authored without assuming a mouse?
How should video captions and transcripts be referenced?
How should audio descriptions be provided?
How should color-dependent instructions be avoided?
How should language changes inside a topic be marked?
How can generated PDF tagging differ from DITA source semantics?
Why might accessible source content still produce an inaccessible PDF?
How should decorative icons be handled?
How can Schematron validate missing alternative text?
How should accessibility checks be included in CI pipelines?
How would you validate WCAG-related behavior in DITA-generated HTML?
What is the purpose of DITA learning and training topic types?
What is the difference between a learning overview and a learning content topic?
What is a learning assessment topic?
How should learning objectives be represented?
How are questions and answer choices structured?
How should correct and incorrect feedback be represented?
Can assessments be reused across multiple courses?
How should question banks be organized?
Can conditional processing generate different assessments for different audiences?
How should learner progress be tracked in generated HTML learning output?
How should multiple-choice and multiple-select questions differ?
How should true-or-false questions be represented?
How should fill-in-the-blank questions be authored?
How should matching questions be structured?
How should scoring rules be represented?
How should partial credit be handled?
What happens when no correct answer is defined?
How should randomized question order affect reproducibility?
Can answers contain code blocks, images, or tables?
How should accessibility be validated for interactive assessments?
Why might quiz state reset when a user opens a new browser tab?
How should course-map navigation differ from a standard DITA map?
How should failed attempts and retries be handled?
How should assessment results be exported to LMS systems?
How should SCORM or xAPI behavior be separated from DITA source semantics?
How can the same learning content be published both as documentation and a course?
How should localized assessments preserve answer correctness?
How should question IDs remain stable across versions?
How should removed questions affect historical learner records?
How would you test course progress, assessment state, and browser navigation together?
What is the structure of a DITA-OT plug-in?
What is the purpose of plugin.xml?
How are extension points used in DITA-OT?
How can a plug-in add a new transformation type?
How can a plug-in override XSLT processing?
How should DITA validation be integrated into a CI pipeline?
Which failures should block a documentation build?
Should warnings block deployment?
How should changed topics determine incremental publishing scope?
How should indirect dependencies be included in change-impact analysis?
If a key definition changes, which topics should be republished?
If a conref source changes, which consumers should be republished?
How should map-level metadata changes trigger rebuilds?
How should subject scheme changes affect validation scope?
How should DITAVAL changes affect publication rebuilds?
How should build artifacts be versioned?
How should publishing logs be retained?
How should DITA-OT version information be recorded in the build?
How should failed publications be reproduced locally?
How should environmental differences between local and Jenkins builds be detected?
How should output comparisons be automated?
How should PDF visual regression testing be performed?
How should broken-link reports be generated?
How should flaky publishing tests be identified?
How would you create a release gate for DITA content quality?
What is a publication baseline?
How does a baseline differ from a source-control branch?
How should topic versions be selected for a baseline?
What happens when a baseline includes a map version but not matching topic versions?
How should indirect key targets be resolved within a baseline?
How should conref sources be versioned in a baseline?
Can the same topic version be used in multiple baselines?
How should moved assets affect historical baselines?
How should deleted topics be represented in an old baseline?
How should a baseline ensure reproducible publishing?
How should review comments be associated with a topic version?
What happens when two authors edit the same topic?
How should merge conflicts in XML be resolved?
How should references be validated after merging branches?
How should map ordering conflicts be handled?
How should a key-definition conflict be reviewed?
How should baseline publication results be compared?
How should approval status affect baseline creation?
How should released and unreleased content be separated?
How would you reproduce a publication exactly six months later?
How should permissions affect DITA map resolution?
What happens when a user can access a map but not one of its referenced topics?
Should publishing fail if a referenced asset is not readable by the publishing service?
How should unauthorized conref sources be handled?
How should key resolution behave when the key target is restricted?
Can search expose metadata from restricted topics?
How should outgoing references display inaccessible targets?
How should broken and unauthorized references be distinguished?
How should external links be validated securely?
How should XML external entity processing be restricted?
What security risks arise from untrusted SVG files?
What security risks arise from custom DITA-OT plug-ins?
How should uploaded DITA files be scanned?
How should publishing credentials be protected?
How should audit logs capture content changes?
How should impersonated publishing sessions be traced?
How should service-user access be validated?
How should permissions be tested across author, reviewer, and publisher roles?
How should a chatbot answer questions about restricted content?
How would you test that unauthorized assets never appear in generated output?
Why is my page number restarting in the wrong section?
Why are my frontmatter pages using normal numbers instead of Roman numerals?
Why is my glossary term not appearing in the generated glossary?
Why is the same index term showing twice?
Why is my SVG visible in Author mode but missing in PDF?
Why is the image path working locally but failing on the server?
Why are my translated labels still coming in English?
Why is the Arabic table layout not right-to-left?
Why is the table header not repeating on the next PDF page?
Why is my warning being shown for another open topic?
Why is the Schematron result cleared when I change tabs?
Why is my course progress reset after reopening the page?
Why is my quiz answer marked incorrect after translation?
Why is my baseline publishing a different topic version?
Why is my old key target still appearing after I changed the map?
Why is my topic visible in search even though it is resource-only?
Why is my restricted topic appearing in outgoing references?
Why are duplicate assets affecting my DITA references?
Why does the same content have different titles in two publications?
Why does my build pass locally but fail in Jenkins?
Metadata, Authoring Model, and Refactoring Expert Questions
If a topic contains audience="admin" but its parent topicref applies audience="developer", what is the effective processing context?
How should conflicting metadata from topicmeta, topic prolog, and map hierarchy be handled?
Does metadata from a referenced map apply before or after metadata on the map-reference element?
Can the same topic have different effective metadata in two output presets?
How should metadata be handled when a topic is referenced both directly and indirectly?
What is the difference between map-level metadata, branch-level metadata, and topic-level metadata?
Can inherited metadata affect a topic that is not directly present in the map hierarchy?
How should metadata attached to a resource-only topic reference be interpreted?
Can metadata influence processing without appearing in the final output?
How can a processor expose effective metadata for debugging?
What happens when one element has multiple profiling attributes and only one matches the DITAVAL rules?
How should conflicting include and exclude rules be evaluated?
What happens when the same attribute value is included in one rule and excluded in another?
Can a parent element be excluded while a child element is explicitly included?
Does excluding a parent always remove all descendants?
How should filtering behave when a topic reference is excluded but the topic is used as a conref source?
What happens when a DITAVAL flag is applied to an inline element?
Can conditional flagging break the structure of a table?
How should overlapping conditional flags be rendered?
How should a processor report unused DITAVAL rules?
What is the purpose of the deliveryTarget attribute?
How does deliveryTarget differ from the older print attribute?
How should content intended only for PDF be marked?
How should content intended only for HTML output be marked?
Can deliveryTarget values be controlled through a subject scheme?
How should multiple delivery targets be specified on one element?
What happens when an output preset does not recognize a delivery-target value?
How should legacy content using print="yes" or print="no" be migrated?
Can DITAVAL rules filter content based on deliveryTarget?
How would you test the same topic across PDF, HTML5, and AEM Sites outputs?
What is the difference between title, navtitle, searchtitle, and linktext?
When should searchtitle be used?
How does searchtitle affect generated search indexes?
What happens when navtitle differs from the topic title?
Can a key definition supply navigation text?
How is fallback text selected when no title is available?
How does locktitle affect title resolution?
Can two references to the same topic display different navigation titles?
How should localized navigation titles be managed?
Why might the editor title, TOC title, and browser-page title differ?
What is the difference between shortdesc and abstract?
When should an abstract contain multiple paragraphs?
How is shortdesc used in generated links?
Can shortdesc be omitted?
What happens when a topic contains both an abstract and a short description?
Can short descriptions be reused through conref?
Can key metadata provide short-description text?
How should conditional content inside shortdesc be handled?
Why might a short description appear in HTML search results but not in PDF?
How should a chatbot explain the role of short descriptions in content discovery?
When should a concept topic be used?
When should a reference topic be used?
When should a task topic be used?
When should a troubleshooting topic be used?
When is a generic topic more appropriate than a specialized topic?
Can a task contain conceptual background information?
Can a reference topic contain procedural steps?
What problems arise when authors use the wrong topic type?
How does topic type affect validation and publishing?
How should an existing generic topic be converted into a task or concept?
What is the difference between steps, steps-unordered, and steps-informal?
When should substeps be used?
Can a step contain multiple cmd elements?
How should optional steps be represented?
How should alternative procedures be modeled?
What is the difference between stepresult and result?
How should a task represent a decision point?
Can a task include multiple prerequisites?
How should expected outcomes be written for each step?
How should a processor handle a task with no cmd element?
What is the recommended structure of a troubleshooting topic?
What is the difference between a condition, cause, and remedy?
Can one troubleshooting topic contain multiple causes?
How should multiple remedies be ordered?
How should error messages be marked up?
Can troubleshooting topics be linked automatically from task topics?
How should environment-specific causes be filtered?
How can one remedy be reused across several troubleshooting topics?
How should symptom-based search metadata be added?
How would you design a troubleshooting topic for an intermittent failure?
What is the difference between codeblock and codeph?
When should filepath be used?
What is the purpose of systemoutput?
What is the difference between userinput and systemoutput?
How should command names be marked up?
How should API method names be represented?
How should code line wrapping be controlled in PDF?
Can code blocks contain conrefs?
How should syntax highlighting be applied without changing semantic markup?
How should long code examples be externalized or reused?
What is the difference between uicontrol, wintitle, and menucascade?
How should nested menu paths be represented?
How should keyboard shortcuts be marked up?
What is the role of the shortcut element?
How should dialog-box titles be represented?
Should button labels be marked as uicontrol?
How should UI text changes across product versions be managed?
How can keys support reusable UI labels?
How should localized UI labels be handled?
How would you validate inconsistent UI-control naming across topics?
How should a property table be represented in a reference topic?
When should properties be used instead of a regular table?
What is the purpose of property rows?
How should default values and allowed values be represented?
How should API parameters be modeled?
How should optional and required parameters be distinguished?
How should return values be documented?
How should error codes be represented?
How should version-specific properties be filtered?
How can reference-topic structures improve automated content extraction?
How should link text be generated for topic references without explicit text?
What happens when a linked topic's title changes?
Should explicit xref text be updated when the target title changes?
How should links to non-DITA resources be represented?
How should email links be handled?
How should download links be distinguished from navigation links?
How can link roles influence output styling?
What happens when a link target is conditionally removed?
How should external-link validation be handled in CI?
How should redirected URLs be managed in long-lived documentation?
Can one topic participate in multiple relationship-table rows?
How should duplicate generated links be removed?
Can relationship tables use resource-only topic references?
How should relationship tables behave with scoped keys?
Can a relationship table reference a copied topic instance?
How should filtering affect relation rows with only one remaining member?
How are links generated when multiple topics exist in the same cell?
Can relation tables model asymmetric relationships?
How should related links be sorted?
How would you troubleshoot a relationship link pointing to the wrong topic instance?
How can keys be used as variables for product names?
What is the difference between a variable key and a navigational key?
Can one key definition provide both text and a target URI?
How should variable text be localized?
Can key-based variables contain inline markup?
What happens when a variable key has no keyword value?
How should fallback text be supplied for unresolved variables?
Can variable keys be scoped by product?
How should changes to variable definitions trigger republishing?
How would you prevent accidental use of a navigational key as a text variable?
When should conref push be preferred over normal conref pull?
How does pushreplace identify the target element?
What happens when multiple push operations target the same element?
In what order should pushbefore and pushafter operations be applied?
Can conref push cross map boundaries?
Can conref push modify content differently in separate publications?
How should push targets be validated?
What happens when a push target is filtered out?
How should circular push dependencies be detected?
Why can conref push be difficult to maintain in large repositories?
How unique must a topic ID be?
How unique must an element ID be within a topic?
Can the same element ID appear in different topics?
What happens when two topics in one file have the same ID?
How should generated IDs be handled?
Can IDs change during translation?
How should fragment references be updated after topic restructuring?
How should duplicate IDs introduced through reuse be handled?
How can Schematron validate ID naming conventions?
How should a CMS preserve references when IDs are changed?
What happens to cascading metadata when a topicref is moved to another branch?
How should key visibility be re-evaluated after moving a submap?
How should relationship-table links be updated after map restructuring?
What happens to branch-filtered output identities after moving a topicref?
How should navigation titles be preserved during refactoring?
How should map-level conditions be migrated when splitting a large map?
How should keys be reorganized when merging two maps?
How can circular map references be introduced accidentally?
What regression tests should run after a major map refactor?
How should a chatbot explain unexpected output changes after restructuring?
How should a large Word document be split into DITA topics?
How should headings be mapped to concepts, tasks, and references?
How should repeated text be identified for reuse?
How should embedded links be converted into DITA references?
How should tables be converted into CALS or simple tables?
How should document-level metadata be mapped to DITA maps and topics?
How should page-oriented content be adapted to topic-based authoring?
How should duplicated warnings be consolidated?
How should legacy filenames and IDs be preserved?
How would you validate semantic quality after automated conversion?
How should maximum topic length be governed?
How should overly deep map nesting be detected?
How should duplicate short descriptions be identified?
How should missing prerequisites in task topics be detected?
How should inconsistent terminology be reported?
How should direct references be restricted when keys are required by governance?
How should unused conref source fragments be detected?
How should invalid profiling values be prevented?
How should stale references be identified before release?
How should content-quality rules differ between warnings and release blockers?
A topic is referenced in two maps, uses a scoped variable key, and receives different cascading metadata. How many effective representations may exist?
A conref source contains a keyref whose definition differs by publication. Which context controls the final result?
A branch-filtered topic uses copy-to and participates in a relationship table. How should the related link target be selected?
A topic is resource-only in one branch and normal in another. How should output generation be determined?
A key definition is filtered out, but its target topic remains in the map. Can direct links still work?
A child map defines a subject scheme and is reused under two root maps. Which controlled values should the editor display?
A translated conref source has a different internal element structure. How should compatibility be validated?
A conref-push operation modifies a topic that is also reused through conkeyref. Which effective content should be processed?
A topic's title comes from the source in one map and from navtitle in another. How should search indexing represent both contexts?
A processor, editor, and CMS produce three different results for the same indirect reference. How should the chatbot separate normative behavior, implementation behavior, and possible defect?
Oxygen Root Map, WebHelp, and PDF Chemistry Expert Questions
Why does a key definition remain unresolved when the key map exists but no root map is selected in Oxygen?
How does selecting a root map change keyref resolution in an independently opened topic?
Why can the same topic show different profiling values under two different root maps?
What processing context does Oxygen use when a topic is opened outside the DITA Maps Manager?
How should Oxygen choose a root map when the same topic belongs to several publications?
Why can content completion suggest different key values after changing the root map?
How should a CMS behave when multiple root maps define the same key name?
Can Oxygen determine the correct subject scheme without an active root-map context?
Why might standalone topic validation differ from validation initiated from the DITA map?
What information should be cached when Oxygen associates a topic with a root map?
Why are key definitions in a referenced key map not available to the current topic?
Must a key map be directly referenced by the root map, or can it be referenced indirectly?
How does processing-role="resource-only" affect a key map?
Why might an unused key definition still be processed during map validation?
Can a key map define only variable keys without including content in navigation?
How should duplicate key names across multiple key maps be resolved?
Why might a key work in Author mode but fail during PDF transformation?
What is the difference between a missing key definition and an inaccessible key-definition map?
How can Oxygen's completeness check help diagnose unresolved keys?
How should key-definition changes invalidate previously resolved topic references?
Why does the same conkeyref resolve only once when its source topic is reused under multiple key scopes?
Can the same key-scope name be reused on several sibling topic references?
Why should sibling branches generally use distinct key-scope names?
How does a reused submap obtain the key scope assigned to its parent mapref?
Can nested conrefs preserve the key scope of the consuming branch?
Which context controls a keyref inside content pulled through conref?
Which context controls a keyref inside content pulled through conkeyref?
Why might the first scoped key definition be incorrectly reused for later topic instances?
How can the same template topic display different variable text in separate scopes?
What intermediate processing output should be inspected when key-scope resolution appears incorrect?
Can a conrefed element contain a keyref whose value depends on the consuming branch?
Does a normal conref preserve the key context of the source topic or the consumer topic?
Why can a conkeyref work in the original topic but fail when that topic is reused?
How should conkeyrefs nested inside conrefed content be resolved?
Can one reusable fragment contain multiple independently scoped key references?
What happens when a conkeyref resolves to a topic but not to the requested element ID?
Why might conkeyref resolution differ between Oxygen Author mode and DITA-OT?
How should circular dependencies involving keyref, conref, and conkeyref be detected?
Can a conref source be outside the root-map folder?
What completeness-check warnings should be expected for external conref targets?
Does metadata on the root map cascade through a topichead to its child topic references?
Why might metadata appear to stop cascading when topics are grouped under a topichead?
Can othermeta cascade in the same way as profiling attributes?
Is othermeta intended to become topic metadata or only map-processing metadata?
Can topichead contain topicmeta that applies to all descendants?
Does topichead create only navigation hierarchy, or also a metadata context?
How can inherited metadata be inspected after preprocessing?
What is the difference between metadata propagation and physically adding metadata to a topic?
How should metadata conflicts between a topichead and child topicref be resolved?
Can a topichead establish a key scope and conditional-processing context simultaneously?
What does lockmeta control in a DITA map?
Does lockmeta cause map metadata to overwrite metadata inside a topic?
Which map metadata is affected by lockmeta?
Why might a topic's local audience value take precedence over map metadata?
Does locktitle cascade from parent topic references?
What happens when locktitle="yes" is set but no local navtitle is provided?
Why might a navtitle appear in the TOC but not as the topic heading?
Can a topic use a keyref or conref in its title to obtain a variable title?
How should title selection work when navtitle, target title, and key metadata all exist?
Why can the title shown in Oxygen differ from the title in published output?
Why are controlled profiling values not loaded from a subject scheme?
Must the root map directly or indirectly reference the subject scheme map?
What happens to Oxygen project-level profiling values when a subject scheme is active?
Why might profiling values work in one Oxygen project but not another?
How can the Oxygen project file affect profiling-value suggestions?
Why can a subject scheme validate successfully but fail to populate the Attributes view?
Can a subject scheme be used without opening the main DITA map?
How should Oxygen prioritize subject-scheme, project-level, and global profiling definitions?
Why might a subject definition key be marked unresolved when no root map is selected?
What should be checked when only some subject-scheme values appear in content completion?
Can grouped profiling attributes be defined through a subject scheme?
How should grouped attribute values be represented in the subject-scheme hierarchy?
Why might a profiling group defined in Oxygen preferences conflict with an active subject scheme?
Can a subject scheme define both standalone values and grouped values?
How should props specialization participate in subject-scheme validation?
What happens when a grouped profiling value is not included in the allowed subject-scheme values?
Can different product groups share common subject definitions?
How should subject-scheme groups be presented in Oxygen's profiling dialog?
Can one subject-scheme map define controlled values for several specialized attributes?
How should invalid combinations of profiling values be validated?
How should multiple values be entered for one profiling attribute in Oxygen?
Are multiple profiling values stored as a space-separated XML attribute value?
Why might content completion allow one value but reject multiple values?
How does subject-scheme validation handle multiple values on the same attribute?
What happens when one profiling value is valid and another is invalid?
How should a DITAVAL evaluate an element with several audience values?
Can multiple values from different subject-scheme branches be assigned together?
How should duplicate values on a profiling attribute be normalized?
Does the order of profiling values have semantic meaning?
How should Oxygen display content that matches several active profiling conditions?
Why is profiled content shown with a colored background or border in Author mode?
How does Oxygen determine which conditional profile is currently active?
Can excluded content remain visible in Author mode while being omitted from publication?
How can authors distinguish included, excluded, and flagged content visually?
Why might Author mode use a different active filter than the transformation scenario?
Can profiling styles be customized without changing publication output?
How should content with several profiling attributes be highlighted?
Why might an element appear filtered even though its local attributes do not match the filter?
Can inherited map-level profiling values affect Author-mode visualization?
How should profile visualization update after changing the root map?
What is the difference between validating one DITA topic and validating a complete map?
Why does map validation process more resources than the visible topic references?
Should all resources defined by a key map be included in completeness validation?
Can completeness validation be restricted to only keys actually used by the publication?
Why can batch-validating individual topics be slower than validating the map?
Which checks are performed by "Validate and Check for Completeness" beyond grammar validation?
How can a custom Schematron file be added to map completeness validation?
Should orphan topics be included in map-level validation?
How should validation handle resources outside the root-map folder?
How can validation results distinguish unused resources from broken references?
How can a reusable Oxygen validation scenario combine DTD and Schematron validation?
Can Schematron be run as part of a DITA map completeness check?
How should Schematron results from multiple topics be grouped by source file?
Why might Schematron validation be slower during individual file batch validation?
Can an Oxygen framework define different Schematron rules for topics and maps?
How should warning, error, and fatal roles be represented in Oxygen results?
Can a Schematron rule inspect a referenced topic or map?
How should a validation scenario behave when the external Schematron file is missing?
Can authors run a predefined completeness check using a custom toolbar action?
How should stale Schematron findings be cleared when the underlying topic changes?
What does "topic referenced in other topics but not in the DITA map" mean?
Must every cross-reference target also appear in the publication map?
Why can an external topic link work in HTML but fail in PDF?
When should an xref target be added as a resource-only topic reference?
How should links to non-navigation topics be represented in the root map?
Why might a direct conref produce an outside-map warning while a conkeyref does not?
Should an unused but referenced topic be copied into WebHelp output?
How should completeness validation treat peer and external-scope links?
What is the difference between a missing map member and a broken URI?
How should a chatbot explain output-specific consequences of targets missing from the map?
Why can a topic outside the map directory publish successfully but produce a broken WebHelp navigation link?
How does WebHelp calculate output paths for topics located above the map folder?
Should publication resources be restricted to the root-map directory tree?
How are relative topic paths rewritten in WebHelp output?
What happens when two external topics have the same filename?
How should WebHelp preserve links between topics copied from different source directories?
Can copy-to normalize output paths for topics outside the map folder?
How should WebHelp handle absolute file URIs?
Why might the side TOC link differ from a link inside topic content?
Which generated files should be inspected when WebHelp navigation points to the wrong location?
How can metadata from topicmeta be added to WebHelp side-navigation entries?
Which intermediate TOC structure contains map metadata for WebHelp transformation?
Can audience metadata be converted into an HTML data attribute?
How should custom metadata be preserved during map-to-WebHelp processing?
Why might topic metadata be available to topic templates but not TOC templates?
How can an XSLT template access metadata associated with a navigation node?
Should inherited map metadata be added to every WebHelp menu item?
How can metadata-based CSS classes be applied to WebHelp navigation?
How should conditional filtering interact with custom navigation metadata?
How can WebHelp customization remain compatible across publishing-engine upgrades?
How should outputclass be converted into a CSS selector for PDF Chemistry?
How can custom fonts be embedded in a CSS-based PDF?
How can a full-page cover image be added to a PDF?
Why might a CSS property work in a browser but not in PDF Chemistry?
How should unsupported CSS such as z-index be handled?
Can several images be combined in SVG to simulate layered PDF content?
How can page numbering restart for each chapter?
How can page numbering restart only once after the frontmatter?
How should running headers change between chapters and appendices?
What should be considered when migrating an XSLT-based PDF customization to CSS?
How can glossary, acronym, safety, and introductory topics be excluded from chapter numbering?
Should unnumbered introductory topics be placed in frontmatter rather than as chapters?
How does a bookmap's semantic structure affect automatic chapter numbering?
Can a topic appear after the TOC but before Chapter 1?
How should "About this guide" content be represented in a bookmap?
Can appendix numbering use letters while chapter numbering uses numbers?
How can one chapter be excluded from numbering without removing it from the TOC?
Why might page numbering restart unexpectedly at each chapter?
How should part, chapter, and topic numbering interact?
What transformation-specific settings control chapter and page numbering?
Can one CSS file be shared across Oxygen Author mode, WebHelp, and PDF output?
Why do CSS selectors for DITA table attributes differ between Author mode and generated HTML?
Why is frame styling applied to different elements in Author mode and output?
How are rowsep and colsep represented in generated HTML classes?
Why might table row separators require styling on entries rather than rows?
How does browser margin collapsing differ from Oxygen Author and PDF layout?
Why does WebHelp's horizontal overflow behavior affect table margins?
How should platform-specific CSS be separated while retaining common rules?
How can the Author view approximate print layout without becoming output-specific?
What regression tests should validate shared CSS across all three renderers?
Why can an SVG render correctly in a browser but appear distorted in PDF?
Which Oxygen version and transformation scenario details are needed to reproduce an SVG defect?
Why might an SVG display as unavailable in Author mode?
How should SVG MIME type and file accessibility be validated?
Why are external images referenced inside svg-container not automatically copied?
Can resource-only map references force embedded SVG resources into output?
Does DITA-OT inspect links inside external SVG documents?
Why might an SVG have unexpected whitespace around the visible drawing?
How do SVG viewBox, width, and height affect DITA image scaling?
Why can PNG content embedded in SVG scale differently from SVG callouts?
Why does an image sized correctly for PDF appear too small in HTML?
Should scale, width, or CSS be used for output-specific image sizing?
Can conditional attributes select different image resources for PDF and HTML?
How can output-specific CSS resize the same source image differently?
What happens when both DITA image dimensions and CSS dimensions are provided?
How should images wider than the printable page area be handled?
Can physical dimensions in an image's metadata affect PDF rendering?
Why might vector and raster images respond differently to the same scale value?
How should image sizing be tested in Author mode, WebHelp, and PDF?
What information should a chatbot request when diagnosing an output-specific image-size issue?
How should index terms behave when a topic is published using copy-to?
Should the index point to the source topic or the copied output identity?
Can the same topic generate separate index entries for multiple copied instances?
Why might index terms inside sections create unexpected layout artifacts in PDF?
Are index terms allowed outside a topic prolog?
How can an index be suppressed while retaining indexterm markup in the source?
Can the index TOC entry be removed independently from the generated index?
How should page references be calculated for reused topic instances?
What happens when a copied topic contributes an index range?
How should duplicate index terms from reused topics be consolidated?
Why might glossary definitions ignore custom CSS?
How are glossary terms and definitions represented in generated HTML?
Can glossary styling differ between WebHelp and PDF?
How should glossary entries be included without appearing as normal chapters?
Can a glossary list include resource-only glossary topics?
How should duplicate glossary terms be resolved?
Why might a glossary xref resolve in Author mode but fail in publication?
Can keyrefs be used to generate glossary terms contextually?
How should localized glossary terms be sorted?
Which intermediate output should be inspected when glossary markup is transformed unexpectedly?
How should footnotes inside tables be rendered in PDF?
Should table footnotes appear at the bottom of the table or the bottom of the page?
Can a table footnote be reused through a normal fn reference?
How should repeated references to one footnote be numbered?
Why might footnote separators work for normal paragraphs but not tables?
How should footnotes behave when a table spans several pages?
Can footnotes inside a repeated table header create duplicate notes?
How should footnote numbering restart between chapters?
Why might a footnote work in DITA-OT PDF but not CSS-based PDF?
How should transformation-specific footnote behavior be explained by the chatbot?
What information about key definitions appears in DITA-OT temporary files?
How can resolved key properties be inspected after preprocessing?
Why might a keyref attribute disappear or change in temporary content?
How are image keyrefs converted into effective href values?
Can a custom XSLT read DITA-OT job or results files?
Why should custom transformations avoid depending on unstable internal temporary-file formats?
How does DITA-OT track key-definition resources in its job metadata?
How can temporary output reveal whether a problem occurs before rendering?
What is the difference between inspecting merged-map output and processed topic output?
How should a chatbot guide users to distinguish key-resolution defects from renderer defects?
Why can an Ant-based custom plug-in fail after upgrading DITA-OT?
Which deprecated Ant properties or targets should be checked during an upgrade?
How can changes in property scope affect an <antcall> task?
Why should complete transformation console output be collected before diagnosing a plug-in failure?
Can inheritAll or inheritRefs change property availability in nested Ant calls?
Which custom plug-in assumptions commonly break across major DITA-OT versions?
How should a custom transformation be tested against both old and new DITA-OT versions?
How can a plug-in determine the effective input map and temporary directory?
Why is using documented DITA-OT extension points safer than calling internal targets?
What migration checklist should be followed before upgrading an enterprise publishing engine?

Oxygen Forum Inspired Advanced Questions
Why does Oxygen report an unresolved key even though the key is defined in another open DITA map?
What is the difference between opening a map in the Project view and opening it in the DITA Maps Manager?
How does the Root Map/Context selection affect key resolution in Oxygen?
Why might changing the root map immediately remove unresolved-key warnings?
How should Oxygen determine the context for a topic included in several root maps?
What happens when a topic is opened without any map in the DITA Maps Manager?
Can validation use one root map while publishing uses another map?
Why might content completion show keys from the wrong publication?
How should an editor display the currently active map context to prevent author confusion?
What information should be collected when Oxygen and DITA-OT appear to use different root maps?
What does an externally imposed key context mean in Oxygen?
How is an externally imposed key manager different from the normal DITA Maps Manager?
Why would a key resolve only when Root Map is set to External Imposed?
Relative to which location should an externally supplied key target be resolved?
How should an external key manager supply the definition location for a relative href?
What happens if the external key manager supplies a key without a valid target base URI?
How should scoped keys be represented through a custom key manager?
How should a custom key manager invalidate old key definitions?
Can external keys and map-defined keys safely coexist?
How should Oxygen report conflicts between external and map-defined key definitions?
Why might moving key definitions into a separate key map cause all references to become unresolved?
Where should a key map be referenced from a bookmap?
Can a key map be included through more than one level of nested map references?
What happens if the mapref to a key map is filtered out by a DITAVAL?
Should key definitions remain available if their containing map reference is excluded?
How can an author verify that Oxygen expanded and loaded a referenced key map?
Why might a referenced map appear non-expandable in the DITA Maps Manager?
Can a framework association problem prevent Oxygen from recognizing a file as a DITA map?
How should key maps be organized so that they contribute keys without appearing in navigation?
How would you distinguish a missing key map from an incorrectly selected root map?
What happens when a subject definition and a normal key definition use the same key name?
Why can the order of a subject-scheme reference and a key-map reference affect behavior?
How should the first effective key definition be selected in an unscoped key space?
Can key scopes safely separate ordinary keys from subject-definition keys?
How should duplicate key names be detected before publication?
Can a duplicate key cause a subject-scheme value to disappear from content completion?
Should Oxygen warn when a subject key shadows a normal navigation key?
How can map traversal order create a different result after map restructuring?
What naming convention can prevent collisions between taxonomy keys and content keys?
How would you create a minimal test proving that key order changes effective resolution?
Why are values defined in Oxygen preferences ignored when an active subject scheme exists?
Must a subject-scheme map be referenced directly by the root map?
Can a subject scheme be discovered through nested map references?
Why might the same subject scheme work in one Oxygen project but fail in another?
Can project-level settings interfere with subject-scheme discovery?
How should Oxygen handle a subject scheme that cannot be loaded?
Why might only some subject definitions appear as allowed attribute values?
How should a user confirm which subject scheme is currently active?
Can different root maps expose different controlled values for the same topic?
How should cached controlled values be invalidated after a subject-scheme update?
Why can a manually entered keyref work even when Oxygenâ€™s key-reference dialog is empty?
Should keys defined on subjectdef elements appear in ordinary key-selection dialogs?
Can a subject scheme provide keyref values for a keyword element?
What is the difference between validating a keyref and proposing it through content completion?
Why might the Attributes view show profiling values but not keyref values from the same scheme?
Can enumerationdef constrain the keyref attribute of a specific element?
How should Oxygen distinguish taxonomy keys from link-target keys?
What should happen when a valid key is filtered out of an insertion dialog?
How can a UI limitation differ from DITA-OT processing behavior?
What test should verify consistency between manual entry, content completion, and publishing?
Can profiling groups be defined directly in a subject-scheme map?
How are grouped profiling attributes different from hierarchical subject definitions?
Why can a grouped profiling value be rejected by subject-scheme validation?
Should Oxygen combine subject-scheme values with groups configured in preferences?
What happens when a subject scheme takes control of an attribute already configured as a profiling group?
How should a group requiring several simultaneous values be represented?
Can a DITAVAL condition set represent combinations that a subject scheme cannot model?
How should invalid group combinations be reported?
Can specialized profiling attributes participate in Oxygen profiling groups?
What is the best way to test authoring, validation, and publishing of grouped conditions?
How can profiling attributes be discovered from a DITAVAL file?
What is the difference between importing a DITAVAL and referencing it during publishing?
Does importing a DITAVAL automatically create subject-scheme validation?
How can desktop profiling settings be transferred to Oxygen Web Author?
Why might Web Author show default profiling values instead of organization-specific values?
Does Web Author need to restart after imposed profiling options change?
How should several DITAVAL files with conflicting values be imported?
Can an imported profiling condition set be exported independently?
How should environment-specific profiling options be version-controlled?
How would you verify that Desktop Author and Web Author use identical profiling definitions?
How should Oxygen handle several space-separated values in one profiling attribute?
Why might a value be suggested by content completion but not formally validated?
Can cc_config.xml provide values without enforcing their validity?
When is a subject scheme preferable to content-completion configuration?
How can Schematron validate values that are configured only as editor suggestions?
What happens if one value in a multi-value attribute is invalid?
Should duplicate values in one profiling attribute be reported?
Does the order of profiling values affect filtering?
How should Oxygen display inherited and locally authored profiling values?
How would you test multi-value filtering against several DITAVAL rules?
How should hierarchical subject relationships affect conditional filtering?
If a parent subject is excluded, should its narrower subjects also be excluded?
Why might subject-scheme hierarchy work in one transformation scenario but not another?
What is the difference between referencing a DITAVAL in a map and passing it as a transformation argument?
Can a built-in transformation scenario use a different filtering path from a customized scenario?
How can an author prove that the active subject scheme was loaded during publishing?
Which temporary files can reveal whether hierarchical values were expanded?
Should Oxygen Author filtering and DITA-OT publishing produce identical hierarchical results?
How should a chatbot classify a hierarchy problem as configuration, DITA-OT, or Oxygen behavior?
What regression test should be added after a hierarchical-filtering defect is fixed?
Why can a publication build successfully while Oxygen still reports a keyref warning?
What does Validate and Check for Completeness validate beyond XML grammar?
Should all nested maps be expanded during completeness validation?
Why might a submap that publishes correctly appear unavailable in the DITA Maps Manager?
Can document-type association settings affect completeness validation?
How should completeness checking handle externally imposed keys?
Should unresolved resource-only keys fail validation?
How should the tool differentiate an unused key from an unresolved key?
Can filtering cause false unresolved-key warnings during validation?
What files should be included in a minimal reproduction for a map-completeness defect?
Why might relationship-table links from a nested map not appear in output?
Does a nested mapâ€™s relationship table become part of the root publication automatically?
Can relationship-table entries use glossary keys defined elsewhere?
Why can glossary references appear unresolved until the main map is opened in the DITA Maps Manager?
How should key context be applied to relationship tables in submaps?
Can filtering remove one relationship-table member while retaining the others?
What happens when a nested relationship table links to resource-only glossary entries?
Should relationship-table links be generated for multiple instances of a copied topic?
How can the temporary merged map be used to verify relationship-table integration?
How would you separate a missing key problem from a relationship-link generation problem?
How does chunk="to-content" combine parent and child topics into one output page?
Can selected child topics be excluded from a chunk while others remain combined?
How should select-topic, select-branch, and select-document affect chunk selection?
Why might a child topic still be included in a chunk after toc="no" is applied?
Does toc="no" control chunk inclusion or only navigation visibility?
How should links to child topics be rewritten after they are combined into the parent output?
What happens to child topic IDs after chunking?
Can a nested map define its own chunking rules inside a parent chunk?
Why might different DITA-OT versions interpret complex chunk tokens differently?
How should a chatbot respond when a requested chunking structure is not directly supported?
Why do chunked child-topic URLs sometimes contain generated identifiers?
Can a title ID influence the generated fragment URL of a chunked topic?
Should output URLs be based on topic IDs, title IDs, filenames, or copy-to values?
What happens if title IDs are not stable across translations?
How can descriptive URLs be maintained without misusing DITA IDs?
Can custom XSLT override the generated IDs used for chunked topics?
How should duplicate child titles be handled when generating readable URLs?
What impact can URL customization have on existing bookmarks?
How should chunked URLs be validated after a DITA-OT upgrade?
How would you test internal links to deeply nested topics inside one chunked page?
Why can a conref to a topicref that references a DITA map fail during preprocessing?
What happens to the map-reference element when its child map is integrated?
Can a conref target disappear before the conref stage processes it?
Why does the original id on a map-referencing topicref become unavailable?
Can a surrounding topicgroup provide a more stable conref target?
How should conref processing order interact with map-reference expansion?
What does an â€œunable to find targetâ€ error indicate when the target exists in the source map?
How can temporary merged-map output confirm that the original target was replaced?
Should a chatbot recommend conref reuse for complex map structures?
What safer alternatives exist for reusing a branch that contains a referenced map?
Why can copy-to work in the root map but fail in a nested child map?
Should the copy-to target include the same directory structure as the source href?
Relative to which map is a nested copy-to URI resolved?
Why might an incorrectly resolved copied topic generate a blank WebHelp page?
Is copy-to intended to rename the only occurrence of a topic?
What happens when the original topic is never referenced without copy-to?
How should the source and copied output identities be represented in the job file?
Why can older DITA-OT versions show different nested-map copy-to behavior?
Can moving the child map change the effective copy-to destination?
What test matrix should cover root maps, submaps, folders, and repeated topic instances?
Why can the TOC open the correct copied topic while an internal xref opens the wrong instance?
How should links between two topics duplicated through copy-to be rewritten?
What happens when an xref targets a figure or table inside a copied topic?
Why might topic-level links work while element-level fragment links fail?
Does the processor know which copied instance an unscoped source URI is intended to target?
Can scoped keys solve ambiguous links between copied topic instances?
How should relationship-table links target copied topics?
Should index terms point to the source identity or the effective copied identity?
What intermediate mappings should be inspected for a wrong copied-topic link?
How would you test navigation context after following links between duplicated topics?
Why can the same source topic create duplicate entries in a context-help map?
When should copy-to be used to create distinct context-help targets?
How should context IDs be associated with separate output instances?
Can two copied topics safely retain the same topic ID?
How should the context-help generator distinguish source URI from output URI?
What happens when one source topic appears under several navigation branches?
Should context-help mappings point to a topic, fragment, or publication context?
How can duplicate context IDs be detected before publishing?
How should copied topic names remain stable across releases?
What regression checks are needed after changing copy-to values used by context help?
Why must preprocessing always operate on temporary copies rather than original source files?
How can an incorrect args.root.map value cause source-map corruption?
What log entries indicate that input and output preprocessing paths are identical?
Which DITA-OT stages can modify maps in the temporary directory?
How should a transformation verify that its temporary root is isolated?
Why might running a transformation from an active topic differ from running it from the map?
Can a custom single-topic transformation accidentally treat the source map as a temporary artifact?
What safeguards should prevent a build from overwriting source content?
How should CI detect that source files changed during publishing?
What evidence should be collected before reporting a transformation that corrupts an input map?
A key publishes correctly but Oxygen marks it unresolved. Which editor-context checks should be performed before changing the DITA source?
A subject-scheme value disappears after adding an ordinary key with the same name. What collision should be investigated?
A nested map publishes but does not expand in the DITA Maps Manager. Which framework association could be wrong?
A copied topic opens correctly from the TOC but its figure link opens the original topic. Which URI mapping is likely incorrect?
A DITAVAL works when passed as a transformation argument but not when referenced in the map. Which filtering path should be compared?
A conref target exists in the authored map but disappears during publication. Which preprocessing transformation may have removed it?
Web Author proposes the wrong profiling values after server configuration changes. Which imported or imposed options should be checked?
A subject scheme validates one attribute but does not populate the keyref insertion dialog. Is this a DITA validity issue or editor-support issue?
A transformation modifies the source map only when launched from an opened topic. What root-map and temporary-path parameters should be traced?
When Oxygen Author, Web Author, and DITA-OT behave differently, how should the chatbot separate source validity, editing assistance, publishing behavior, and confirmed product defects?
"""


def _questions() -> list[str]:
    questions: list[str] = []
    for raw_line in _QUESTIONS_TEXT.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        is_question = line.endswith("?")
        is_eval_prompt = bool(
            re.match(
                r"^(?:Explain\b|Compare\b|Correct this statement:|Create a test scenario\b|Since\b|Root map\b|"
                r"Same key\b|Parent metadata\b|conref source\b|Topic save\b|Tab switch\b|"
                r"Resource-only topic output\b|HTML5 mein\b|Did the answer\b)",
                line,
                re.IGNORECASE,
            )
        )
        if not is_question and not is_eval_prompt:
            continue
        line = re.sub(r"\s+", " ", line)
        if line not in questions:
            questions.append(line)
    return questions


def _domain(question: str) -> tuple[str, str, list[str]]:
    q = question.lower()
    if any(term in q for term in ("xml:lang", "translate", "translation", "translated", "language", "locale", "multilingual", "rtl", "right-to-left", "bidirectional", "arabic")):
        return "localization", "Localization, translation, bidirectional text, generated labels, and locale-specific publishing", ["localization", "translation", "xml:lang"]
    if any(term in q for term in ("bookmap", "booktitle", "mainbooktitle", "bookmeta", "frontmatter", "backmatter", "chapter", "appendix", "roman numerals", "page number")):
        return "bookmap_publishing", "Bookmap structure, page numbering, publication metadata, and PDF output semantics", ["bookmap", "pdf", "publishing"]
    if any(term in q for term in ("indexterm", "index term", "index range", "see also", "index list")):
        return "indexing", "DITA indexing, generated index lists, ranges, sorting, and conditional index behavior", ["indexterm", "index", "publishing"]
    if any(term in q for term in ("glossary", "glossentry", "glossary term", "acronym", "abbreviation", "terminology", "forbidden term")):
        return "glossary_terminology", "Glossary entries, terminology governance, acronyms, localization, and validation", ["glossary", "terminology", "keys"]
    if any(term in q for term in ("accessibility", "alternative text", "alt", "screen reader", "wcag", "captions", "transcripts", "decorative", "heading levels")):
        return "accessibility", "Accessibility semantics, alternative text, screen-reader behavior, PDF tagging, and WCAG validation", ["accessibility", "wcag", "validation"]
    if any(term in q for term in ("hazard", "hazardsymbol", "hazardstatement", "warning", "danger", "caution", "safety", "signal word")):
        return "safety_hazards", "Safety notes, hazard statements, compliance-sensitive content, symbols, and output styling", ["hazard", "safety", "schematron"]
    if any(term in q for term in ("svg", "mathml", "media", "high-resolution", "image", "figure")):
        return "media_images_math", "Images, SVG, MathML, media assets, accessibility, and output compatibility", ["image", "svg", "mathml"]
    if any(term in q for term in ("learning", "assessment", "quiz", "course", "scorm", "xapi", "learner", "question bank", "lms")):
        return "learning_training", "DITA learning and training content, assessments, course publishing, and LMS/runtime behavior", ["learning", "assessment", "course"]
    if any(term in q for term in ("ci", "jenkins", "pipeline", "build", "incremental", "release gate", "visual regression", "deployment")):
        return "ci_cd_publishing", "CI/CD validation, automated publishing, dependency impact, logs, and release gates", ["ci-cd", "publishing", "validation"]
    if any(term in q for term in ("baseline", "source-control", "branch", "version", "reproduce a publication", "six months")):
        return "baselines_versioning", "Baselines, versioning, release reproducibility, branches, and collaboration", ["baseline", "versioning", "aem-guides"]
    if any(term in q for term in ("permission", "restricted", "unauthorized", "service-user", "security", "credentials", "audit", "xxe", "external entity")):
        return "security_permissions", "Permissions, restricted content, secure publishing, search exposure, and auditability", ["security", "permissions", "publishing"]
    if any(term in q for term in ("cascade", "metadata", "topicmeta", "audience", "product", "subject scheme", "profiling")):
        return "metadata_cascade", "Cascading metadata, profiling attributes, and subject-scheme validation", ["metadata", "cascade", "profiling"]
    if any(term in q for term in ("deliverytarget", "delivery-target", "print attribute", "pdf", "html5", "aem sites", "output-specific")):
        return "output_targeting", "Output-specific processing with deliveryTarget, print, DITAVAL, and presets", ["deliveryTarget", "ditaval", "publishing"]
    if any(term in q for term in ("oxygen", "dita maps manager", "root map/context", "external imposed", "key manager", "author mode", "completeness check", "attributes view", "validation scenario")):
        return "oxygen_editor", "Oxygen Editor and Web Author root-map context, validation, profiling, and author-mode behavior", ["oxygen", "root-map", "validation"]
    if "webhelp" in q or "context-help" in q or "context help" in q:
        return "webhelp_publishing", "WebHelp output paths, TOC/navigation metadata, customization, and publishing compatibility", ["webhelp", "publishing", "navigation"]
    if "pdf chemistry" in q or "css-based pdf" in q or "css" in q and "pdf" in q:
        return "pdf_chemistry", "Oxygen PDF Chemistry, CSS-based PDF customization, pagination, fonts, and renderer limits", ["pdf-chemistry", "css", "pdf"]
    if any(term in q for term in ("footnote", "fn reference")):
        return "footnotes_layout", "Footnotes, table footnotes, page layout, numbering, and transform-specific behavior", ["footnote", "pdf", "layout"]
    if any(term in q for term in ("searchtitle", "navtitle", "linktext", "locktitle", "title resolution", "browser-page title")):
        return "titles_navigation", "Topic titles, navigation titles, search titles, link text, and title fallback", ["title", "navtitle", "searchtitle"]
    if any(term in q for term in ("shortdesc", "short description", "abstract")):
        return "shortdesc_abstract", "Short descriptions, abstracts, generated links, and content discovery", ["shortdesc", "abstract", "search"]
    if any(term in q for term in ("concept topic", "reference topic", "task topic", "troubleshooting topic", "topic type", "generic topic")):
        return "topic_typing", "DITA topic type selection, validation, and semantic authoring", ["topic-type", "concept", "task"]
    if any(term in q for term in ("steps-unordered", "steps-informal", "substeps", "stepresult", "cmd element", "decision point")):
        return "task_modeling", "DITA task structure, steps, substeps, commands, and outcomes", ["task", "steps", "cmd"]
    if any(term in q for term in ("condition, cause, and remedy", "troubleshooting topic", "error messages", "symptom")):
        return "troubleshooting_modeling", "Troubleshooting topic modeling, symptoms, causes, remedies, and reuse", ["troubleshooting", "remedy", "diagnostics"]
    if any(term in q for term in ("codeblock", "codeph", "filepath", "systemoutput", "userinput", "api method", "syntax highlighting")):
        return "software_markup", "Programming and software-domain markup for commands, code, paths, and output", ["software-domain", "codeblock", "userinput"]
    if any(term in q for term in ("uicontrol", "wintitle", "menucascade", "shortcut", "button labels", "ui labels")):
        return "ui_markup", "User-interface domain markup, UI labels, menu paths, and shortcuts", ["ui-domain", "uicontrol", "shortcut"]
    if any(term in q for term in ("properties", "property rows", "api parameters", "return values", "error codes", "reference topic")):
        return "reference_modeling", "Reference topic structures, properties tables, parameters, return values, and extraction", ["reference", "properties", "api"]
    if "conref push" in q or "pushreplace" in q or "pushbefore" in q or "pushafter" in q:
        return "conref_push", "Advanced conref push behavior, push targets, ordering, validation, and maintainability", ["conref-push", "reuse", "validation"]
    if any(term in q for term in ("topic id", "element id", "duplicate ids", "fragment references", "generated ids", "id naming")):
        return "ids_fragments", "DITA IDs, fragment references, uniqueness, generated IDs, translation, and CMS preservation", ["ids", "fragments", "cms"]
    if any(term in q for term in ("map refactor", "map refactoring", "restructuring", "splitting a large map", "merging two maps", "topicref is moved")):
        return "map_refactoring", "Map restructuring, refactoring, key visibility, metadata, relation links, and regression tests", ["map-refactoring", "keys", "metadata"]
    if any(term in q for term in ("word document", "unstructured", "automated conversion", "legacy filenames", "semantic quality")):
        return "migration", "Migration from unstructured content to DITA topics, maps, references, and reuse", ["migration", "word", "conversion"]
    if any(term in q for term in ("conkeyref", "conref", "reuse", "fallback content")):
        return "advanced_reuse", "Advanced conref, conkeyref, reuse compatibility, and circular dependency diagnostics", ["conref", "conkeyref", "reuse"]
    if any(term in q for term in ("keyref", "key definition", "key definition", "key-", "key ", "keys", "scope", "locktitle")):
        return "advanced_keys", "Advanced key resolution, key references, scoped keys, and map context", ["keyref", "keyscope", "keys"]
    if any(term in q for term in ("copy-to", "copied", "generated uri", "output uri")):
        return "resource_identity", "copy-to, resource identity, generated URIs, and link rewriting", ["copy-to", "uri", "resource-identity"]
    if "chunk" in q:
        return "chunking", "Chunking, output structure, generated files, and cross-reference rewriting", ["chunk", "output-structure", "links"]
    if any(term in q for term in ("specialization", "constraint", "generalization", "class attribute", "document-type shell", "catalog")):
        return "specialization", "Specialization, constraints, generalization, validation, and tool interoperability", ["specialization", "constraints", "validation"]
    if any(term in q for term in ("dita-ot", "preprocessing", "temporary", ".job.xml", "plug-in", "warning", "fatal", "html5", "native pdf")):
        return "dita_ot_processing", "DITA-OT preprocessing, intermediate files, diagnostics, and output transform behavior", ["dita-ot", "preprocessing", "troubleshooting"]
    return "expert_troubleshooting", "End-to-end DITA troubleshooting across source, map context, filtering, preprocessing, and output", ["troubleshooting", "dita-expert", "rag-eval"]


def _short_answer(question: str) -> str:
    q = question.lower()
    if q.startswith("correct this statement:"):
        false_statement = question.split(":", 1)[-1].strip()
        if "all attributes automatically cascade" in q:
            return f"Correction: {false_statement} is false. Only applicable map metadata and defined cascading attributes become effective through map context; not every XML attribute automatically cascades."
        if "nomerge" in q:
            return f"Correction: {false_statement} is false. `cascade=\"nomerge\"` prevents value merging for applicable cascading attributes; it does not disable all inherited map context."
        if "keyref is simply another syntax for href" in q:
            return f"Correction: {false_statement} is false. `href` directly addresses a URI, while `keyref` resolves indirectly through the active map, key scope, and effective key space."
        if "conref can reuse any xml element" in q:
            return f"Correction: {false_statement} is false. `conref` requires compatible DITA elements, class ancestry, valid structure, and a resolvable target."
        if "toc=\"no\"" in q:
            return f"Correction: {false_statement} is false. `toc=\"no\"` affects navigation; it does not by itself mean the topic cannot be generated."
        if "keys are always globally available" in q:
            return f"Correction: {false_statement} is false. Key availability depends on the active root map, filtering, map inclusion, and key scopes."
        if "subject scheme automatically filters" in q:
            return f"Correction: {false_statement} is false. A subject scheme constrains or organizes allowed values; filtering requires DITAVAL or processor-specific filtering rules."
        if "resource-only topic cannot be used anywhere" in q:
            return f"Correction: {false_statement} is false. Resource-only content is normally excluded from reading-order navigation but can still support keys, conrefs, variables, or indirect output use."
        if "if a key resolves" in q:
            return f"Correction: {false_statement} is false. A key can resolve to metadata or to a definition whose target URI is missing or invalid; key resolution and target validation are separate checks."
        if "editor preview and published output" in q:
            return f"Correction: {false_statement} is false. Editor preview and published output can differ because they may use different root-map context, caches, filters, processors, or output transforms."
        return f"Correction: {false_statement} should be treated as an overgeneralization. State the narrower DITA rule, then verify it in the active map and processor context."
    if q.startswith("since "):
        if "conkeyref is indirect" in q:
            return "No. `conkeyref` reduces direct file coupling, but the key definition still has a target that must be updated or remain resolvable after a move."
        if "key is defined in a submap" in q:
            return "No. A submap key is visible only according to map integration, filtering, and key-scope rules; it is not automatically visible everywhere."
        if "resource-only" in q:
            return "No. Resource-only topics can still contribute indirectly through keys, conrefs, variables, or other resource use even if they are not normal reading-order topics."
        if "toc=\"no\"" in q:
            return "No. `toc=\"no\"` hides a topic from navigation; it does not by itself prevent output generation."
        if "subject scheme" in q:
            return "No. Subject schemes define or constrain controlled values; they do not automatically exclude content without filtering rules."
        if "editor resolves a key" in q:
            return "No. Editor key resolution and publishing key resolution can differ if root map, filtering, key scopes, caches, or processor implementations differ."
        if "conref target exists" in q:
            return "No. A conref target must exist and be structurally compatible with the consuming element; existence alone is not enough."
        if "two uris look different" in q:
            return "No. Different lexical URIs can normalize to the same resource after resolving `.`/`..`, escaping, case rules, or XML base."
        if "warning does not block save" in q:
            return "No. Non-blocking warnings still need stable document association and should not disappear because of tab state bugs."
        if "validates against its dtd" in q:
            return "No. DTD validation checks grammar, not all cross-file key, conref, filtering, or publishing dependencies."
        return "No. Treat the statement as a hypothesis, then verify it against DITA rules, map context, and processor behavior."
    if q.startswith("create a test scenario"):
        return "Create a minimal root map, two or three focused topics, the smallest required DITAVAL/key/conref setup, an expected result, and one negative assertion that proves the processor did not use the wrong context."
    if q.startswith("did the answer"):
        return "Evaluate the answer against explicit criteria: did it state the correct DITA mechanism, separate source from effective processed content, label processor/product scope, and avoid unsupported universal claims?"
    if "root map ke bina keyref resolve hoga" in q:
        return "Usually no for reliable resolution. `keyref` needs an active root map or equivalent key-space context; without it, an editor can only guess, use a configured map, or report unresolved keys."
    if "same key alag branches" in q:
        return "The same key can resolve differently in different branches because branch filtering, key scopes, and duplicate key definitions can create different effective key spaces."
    if "parent metadata child topic pe" in q:
        return "Parent metadata can appear on a child topic as effective cascaded metadata from the map branch; the child topic source file is not automatically rewritten."
    if "toc=\"no\" diya" in q:
        return "`toc=\"no\"` hides the topic from navigation, but it can still be generated as output unless processing-role, filtering, chunking, or transform behavior removes it."
    if "html5 mein keyref" in q and "native pdf" in q:
        return "First compare preprocessing and effective key resolution; if the intermediate resolved content is the same, then investigate Native PDF renderer, template, or plug-in behavior."
    if q == "how should xml:lang be applied in a dita topic?":
        return "`xml:lang` should be set on the topic or nearest element whose language differs from its context, so processors and output formats can choose correct generated text, hyphenation, quotation, and accessibility language metadata."
    if q == "what is the purpose of the translate attribute?":
        return "`translate` identifies content that should or should not be translated, commonly protecting product names, command names, code, identifiers, or regulated terms from localization changes."
    if q == "why might generated labels remain in english after switching the publication locale?":
        return "Generated labels can remain in English when the publishing locale, `xml:lang`, language plug-in/resources, PDF template, or transform configuration is not aligned with the target language."
    if q == "when should a bookmap be used instead of a normal dita map?":
        return "Use a `bookmap` when the publication needs book-specific semantics such as frontmatter, chapters, appendices, backmatter, book metadata, generated lists, and print/PDF-oriented structure."
    if q == "can frontmatter pages use roman numerals while body pages use arabic numerals?":
        return "Yes, many book/PDF publishing pipelines support Roman numeral frontmatter and Arabic body page numbering, but the exact control is usually output-transform or template specific."
    if q == "what is the purpose of the indexterm element?":
        return "`indexterm` marks text or concepts that should contribute to a generated index, including nested primary, secondary, and tertiary terms depending on the markup and output transform."
    if q == "what is an index range?":
        return "An index range marks a span of content for an index entry, typically using matching start and end markers so page ranges can be generated instead of single page references."
    if q == "what is the purpose of a glossary entry topic?":
        return "A glossary entry topic defines a controlled term and its definition, and can support terminology consistency, generated glossaries, key-based term insertion, and localization."
    if q == "how can keys be used to insert glossary terms?":
        return "Keys can point to glossary entries or term metadata so authors can insert consistent term text indirectly with `keyref`, while the active map controls the term form."
    if q == "what accessibility information should be added to images?":
        return "Meaningful images need alternative text or an equivalent description; complex diagrams need longer descriptions, while purely decorative images should be marked so assistive technology can ignore them."
    if q == "why is \"click here\" weak link text?":
        return "`Click here` is weak because it does not describe the link destination or purpose; accessible link text should make sense out of context."
    if q == "what is the difference between note, tip, important, caution, warning, and danger?":
        return "These note types communicate different semantic severity or intent; they should not be treated as merely visual styles, especially for safety or compliance-sensitive content."
    if q == "how should hazard statements be structured in dita?":
        return "Hazard statements should use semantic hazard markup where available and clearly identify the hazard, consequence, avoidance instruction, and any required symbol or signal word."
    if q == "why might an svg appear in the editor but disappear in pdf output?":
        return "An SVG can preview in an editor but disappear in PDF because the PDF renderer, security policy, linked resources, fonts, namespaces, or image conversion pipeline does not support it."
    if q == "how is mathml included in dita?":
        return "MathML is included using the DITA math domain or supported foreign/math markup, but rendering depends on the output transform and publishing engine."
    if q == "what is the purpose of dita learning and training topic types?":
        return "DITA learning and training topic types structure instructional content such as learning overviews, objectives, content, summaries, and assessments for course-oriented delivery."
    if q == "what happens when no correct answer is defined?":
        return "A learning assessment without a defined correct answer cannot be scored reliably; the processor or LMS integration should report the issue rather than silently guessing correctness."
    if q == "how should dita validation be integrated into a ci pipeline?":
        return "CI should validate XML well-formedness, grammar, Schematron/business rules, references, keys, conrefs, DITAVAL values, accessibility rules, and publishing smoke tests before release."
    if q == "if a key definition changes, which topics should be republished?":
        return "Republish topics and maps whose effective output depends on that key, including direct key references, conkeyref consumers, variable text users, related links, and branch-specific instances."
    if q == "what is a publication baseline?":
        return "A publication baseline is a reproducible selection of map, topic, asset, key, conref, and configuration versions used to publish a specific release."
    if q == "how does a baseline differ from a source-control branch?":
        return "A baseline records selected content versions for reproducible publishing; a source-control branch is an editable development line that may continue changing."
    if q == "how should permissions affect dita map resolution?":
        return "Map resolution should honor permissions for referenced topics, maps, keys, conref sources, and media; unauthorized dependencies should be reported distinctly from missing or broken references."
    if q == "can search expose metadata from restricted topics?":
        return "Search must not expose restricted topic content or sensitive metadata to unauthorized users; indexing and result rendering need permission-aware filtering."
    if q == "why does my build pass locally but fail in jenkins?":
        return "If a build passes locally but fails in Jenkins, compare the Jenkins environment against local: DITA-OT version, plug-ins, catalogs, filesystem case sensitivity, paths, permissions, fonts, locale, network access, and CI-specific variables."
    if q == "if a topic contains audience=\"admin\" but its parent topicref applies audience=\"developer\", what is the effective processing context?":
        return "The topic source still has `audience=\"admin\"`, but the effective processing context for that map branch can include or override with the parent topicref's `audience=\"developer\"` according to cascade and DITAVAL rules."
    if q == "what is the purpose of the deliverytarget attribute?":
        return "`deliveryTarget` identifies output-specific applicability, such as content intended for PDF, HTML, or another delivery channel, and can be used with filtering rules or publishing presets."
    if q == "what is the difference between title, navtitle, searchtitle, and linktext?":
        return "`title` is the topic's primary title, `navtitle` can control navigation text, `searchtitle` can supply search-specific title text, and `linktext` can provide link text metadata."
    if q == "what is the difference between shortdesc and abstract?":
        return "`shortdesc` is a concise summary commonly used for previews, generated links, and search snippets; `abstract` can provide a richer introductory summary and may contain more structure."
    if q == "when should a task topic be used?":
        return "Use a task topic when the primary purpose is to help the user complete a procedure with clear steps, commands, optional context, expected results, and postconditions."
    if q == "what is the difference between steps, steps-unordered, and steps-informal?":
        return "`steps` models ordered procedural steps, `steps-unordered` models steps that need not be performed in strict order, and `steps-informal` supports less rigid procedural structure when formal step markup is too constrained."
    if q == "what is the recommended structure of a troubleshooting topic?":
        return "A troubleshooting topic should describe the condition or symptom, probable cause, and remedy, with enough environment/context metadata for users and search systems to find the right fix."
    if q == "what is the difference between codeblock and codeph?":
        return "`codeblock` is for block-level code examples, while `codeph` marks inline code phrases inside running text."
    if q == "what is the difference between uicontrol, wintitle, and menucascade?":
        return "`uicontrol` marks controls such as buttons or fields, `wintitle` marks window or dialog titles, and `menucascade` represents a nested menu path."
    if q == "when should properties be used instead of a regular table?":
        return "Use `properties` when documenting named properties or parameters with structured rows such as type, value, description, default, or required status; use a regular table for general tabular data."
    if q == "how can keys be used as variables for product names?":
        return "Define product-name text in key definitions or keyword metadata and reference it with `keyref`, so each map or key scope can supply the correct product name without editing topic text."
    if q == "when should conref push be preferred over normal conref pull?":
        return "Prefer conref push only when a source must contribute content into a target without editing the target directly; normal conref pull is usually simpler, more explicit, and easier to maintain."
    if q == "how unique must a topic id be?":
        return "A topic ID must be unique within the addressable context of its DITA document, especially in multi-topic files where fragment references depend on the topic ID."
    if q == "how unique must an element id be within a topic?":
        return "An element ID should be unique within its containing topic because DITA fragment references commonly address `topicId/elementId`."
    if q == "what happens to cascading metadata when a topicref is moved to another branch?":
        return "Moving a `topicref` to another branch changes its effective inherited metadata, key scope, filtering context, and possibly output behavior even when the topic source file is unchanged."
    if q == "how should a large word document be split into dita topics?":
        return "Split a large Word document by user goal and information type: concepts for explanation, tasks for procedures, references for lookup data, and maps for the original document structure."
    if q == "a processor, editor, and cms produce three different results for the same indirect reference. how should the chatbot separate normative behavior, implementation behavior, and possible defect?":
        return "The chatbot should first state the DITA normative rule, then compare editor, processor, and CMS behavior against the same root map, key scope, filtering, and cache context, labeling any divergence as implementation-specific or a possible defect."
    if q == "why does a key definition remain unresolved when the key map exists but no root map is selected in oxygen?":
        return "In Oxygen, a key map file existing in the repository is not enough; key definitions are collected from the active root map context, so no selected root map can leave `keyref` values unresolved."
    if q == "how does selecting a root map change keyref resolution in an independently opened topic?":
        return "Selecting a root map gives the standalone topic an effective key space, subject schemes, profiling context, and map metadata that are unavailable or ambiguous when the topic is opened alone."
    if q == "can oxygen determine the correct subject scheme without an active root-map context?":
        return "Not reliably. Oxygen needs an active root map or equivalent project association to know which subject-scheme maps and profiling constraints apply to the topic."
    if q == "does metadata on the root map cascade through a topichead to its child topic references?":
        return "Yes, a `topichead` can participate in the map hierarchy for descendants; it creates navigation/grouping context and can carry effective metadata context even though it has no target topic."
    if q == "what does lockmeta control in a dita map?":
        return "`lockmeta` controls whether metadata specified in a map can override or lock corresponding metadata behavior for referenced topics, but it should not be described as physically rewriting the topic source."
    if q == "what is the difference between validating one dita topic and validating a complete map?":
        return "Topic validation checks the individual XML file and local grammar; complete map validation checks the publication context, including map references, keys, conrefs, profiling, resources, and output-relevant completeness."
    if q == "what does \"topic referenced in other topics but not in the dita map\" mean?":
        return "It means a topic is linked or referenced from content but is not included in the publication map, so some outputs may not copy or generate the target even though the source URI exists."
    if q == "why can a topic outside the map directory publish successfully but produce a broken webhelp navigation link?":
        return "WebHelp may generate or rewrite navigation paths relative to the map/output structure; topics outside the map directory can publish but still produce broken links if output path normalization or copy rules are wrong."
    if q == "which intermediate toc structure contains map metadata for webhelp transformation?":
        return "Inspect the WebHelp/DITA-OT intermediate merged map or TOC/navigation representation generated during preprocessing, because that is where map `topicmeta` and navigation nodes are usually available to templates."
    if q == "why might a css property work in a browser but not in pdf chemistry?":
        return "PDF Chemistry is a paged-media renderer, not a browser; some CSS properties or layout behaviors may be unsupported, interpreted differently, or constrained by PDF pagination and font handling."
    if q == "can one css file be shared across oxygen author mode, webhelp, and pdf output?":
        return "A shared CSS base is possible, but Author mode, generated WebHelp HTML, and PDF Chemistry use different DOMs/layout engines, so output-specific layers and regression tests are usually required."
    if q == "why can an svg render correctly in a browser but appear distorted in pdf?":
        return "SVG rendering can differ between browsers and PDF engines because of viewBox, dimensions, fonts, external resources, unsupported SVG/CSS features, and rasterization behavior."
    if q == "should the index point to the source topic or the copied output identity?":
        return "For `copy-to` output, the generated index should normally point to the copied output identity that readers see, not blindly to the original source topic URI."
    if q == "why might glossary definitions ignore custom css?":
        return "Glossary markup may be transformed into output-specific generated structures whose HTML/PDF classes differ from source DITA, so custom CSS may target the wrong generated element."
    if q == "what information about key definitions appears in dita-ot temporary files?":
        return "DITA-OT temporary files and job metadata can expose effective key definitions, resolved targets, resource roles, copy-to mappings, and processed references used after preprocessing."
    if q == "why can an ant-based custom plug-in fail after upgrading dita-ot?":
        return "An Ant-based plug-in can fail after a DITA-OT upgrade because internal targets, property names, property scope, extension points, or Ant call behavior changed; documented extension points are safer."
    if q == "what does an externally imposed key context mean in oxygen?":
        return "An externally imposed key context means Oxygen receives key definitions from a custom/external key manager instead of only collecting them from the selected DITA map context."
    if "manually entered keyref" in q and "key-reference dialog" in q:
        return "Manual `keyref` entry can work when the key is valid for processing but Oxygen's insertion dialog does not expose that key category, root-map context, or custom key-manager source."
    if q == "why do chunked child-topic urls sometimes contain generated identifiers?":
        return "Chunked child-topic URLs can contain generated identifiers because the processor must create stable fragments inside a combined output page when filenames or titles are not unique or not suitable as URL anchors."
    if q == "why can a conref to a topicref that references a dita map fail during preprocessing?":
        return "A `conref` to a map-referencing `topicref` can fail because map-reference preprocessing may replace or integrate that node before conref resolution can address the original element ID."
    if q == "why must preprocessing always operate on temporary copies rather than original source files?":
        return "Preprocessing must operate on temporary copies because stages can rewrite maps, resolve references, add generated metadata, and create intermediate state; writing those changes to source files risks source corruption."
    if q == "a key publishes correctly but oxygen marks it unresolved. which editor-context checks should be performed before changing the dita source?":
        return "Before changing source, check Oxygen's active root map, DITA Maps Manager context, external key manager, filtering profile, subject schemes, framework association, and cache state against the publishing command."
    if "root map sets audience=\"admin\"" in q:
        return "Under merge behavior, the child can have an effective audience set that includes inherited and local values; under no-merge behavior, the child's local `audience=\"reviewer\"` prevents value merging for that attribute while the source topic itself remains unchanged."
    if "key is defined three times" in q:
        return "An unqualified key reference should resolve in its effective key scope after filtering and map processing; the selected definition is not simply the global key or the last key, but the definition visible in the active scope and branch."
    if "xref has a keyref, explicit text" in q:
        return "For an `xref` with explicit authored link text, the local text normally wins for rendered link text; key metadata such as `navtitle` is used when the referencing element needs generated fallback text."
    if "key be valid for variable text but invalid as a link target" in q:
        return "Yes. A key can provide variable text or metadata without being a usable link target if it has no valid `href` or its target URI is invalid for the referencing context."
    if "keyref works in dita-ot html5 but fails in native pdf" in q:
        return "Compare preprocessing first: active root map, filtering, key scopes, effective key definitions, and intermediate resolved content. If preprocessing is identical, then investigate Native PDF-specific rendering or plug-in behavior."
    if "specification is silent but two processors behave differently" in q:
        return "The chatbot should say the DITA specification does not mandate one universal result, describe each processor's observed behavior separately, and provide evidence instead of inventing a single normative rule."
    if q == "explain the difference between authored metadata and effective metadata in a dita publication.":
        return "Authored metadata is what is physically present in a topic or map source file; effective metadata is the processing-time result after map context, cascading, branch filtering, subject schemes, and processor rules are applied."
    if q == "explain why keyref requires a map context while href does not.":
        return "`href` directly names a URI in source XML, while `keyref` names a key whose target is defined by the active map, key scope, filtering state, and effective key space."
    if q == "explain how a dita processor constructs the effective key space.":
        return "A processor constructs the effective key space from the active root map by walking included map branches, applying filtering and key scopes, collecting key definitions, and selecting visible definitions according to scope and precedence rules."
    if q == "compare href, keyref, conref, and conkeyref.":
        return "`href` is direct URI-based linking, `keyref` is indirect key-based linking, `conref` is direct content reuse, and `conkeyref` is indirect key-based content reuse."
    if q == "compare scope and keyscope.":
        return "`scope` describes the relationship of a reference target such as local, peer, or external; `keyscope` creates a named key-resolution context in a DITA map."
    if q == 'compare toc="no" with processing-role="resource-only".':
        return '`toc="no"` removes a normal topic reference from navigation; `processing-role="resource-only"` marks the resource as support material for keys/reuse rather than normal reading-order content.'
    if q == 'compare cascade="merge" and cascade="nomerge".':
        return '`cascade="merge"` allows applicable inherited and local metadata values to combine; `cascade="nomerge"` prevents value merging for applicable attributes but does not erase all map context.'
    if q == "what will be the effective audience value if the parent has audience=\"admin\" and the child has audience=\"developer\"?":
        return "With merge behavior, the effective audience can include both `admin` and `developer`; with no-merge behavior for that attribute, the childâ€™s local `developer` value controls the effective value."
    if q == "what happens when a child defines no local profiling value but its parent defines one?":
        return "The child normally receives the parentâ€™s applicable profiling value as effective metadata through cascading, while the child topic source remains unchanged."
    if q == "what happens when a keyref points to a key definition that has no href?":
        return "A key definition without `href` can still provide metadata or variable/link text, but a reference that needs a navigable target may have no usable link destination."
    if q == "what happens when conref resolves successfully but the consuming element contains local text?":
        return "When `conref` resolves successfully, the referenced content replaces the consuming elementâ€™s local fallback content; the local text is used only when resolution fails or as processor-defined fallback."
    if q == "what happens when a conkeyref key resolves but the requested element id does not exist?":
        return "The key portion resolves, but the content reference fails because the requested target element is missing; the processor should report an unresolved fragment or conkeyref diagnostic."
    if q == "what happens when a resource-only topic is also referenced normally elsewhere?":
        return "The same source can be resource-only in one map branch and normal in another; the effective processing role is determined per topic reference and publication context."
    if q == "what happens when the same key is defined twice in the same effective scope?":
        return "Duplicate key definitions in the same effective scope create a precedence decision; processors should use the effective map/key-resolution rules and report or expose enough diagnostics to avoid ambiguity."
    if q == "what happens when a ditaval excludes the target of an xref?":
        return "If filtering removes the referenced target from the effective publication, the `xref` can become unresolved, suppressed, rewritten, or reported depending on processor and output behavior."
    if q == "what happens when a referenced topic exists but its fragment identifier is invalid?":
        return "The file-level URI resolves, but the fragment target does not; a processor should report an invalid or unresolved fragment rather than treating the full reference as fully valid."
    if q == "what happens when two branches generate the same copy-to output name?":
        return "The branches collide on output identity; the processor or CMS should report the conflict or require branch-specific renaming such as prefixes, suffixes, or unique `copy-to` values."
    if q == "how does metadata cascade from a root dita map to nested topicref elements?":
        return "Map-level metadata and inheritable attributes become effective on descendant `topicref` branches during map processing; the referenced topic source is not rewritten, but each branch can publish with a different effective metadata context."
    if q == 'what does chunk="to-content" mean?':
        return "`chunk=\"to-content\"` requests that referenced topics be combined into a generated output content unit, so navigation/source hierarchy and final output-file structure may differ."
    if q == "how does dita specialization preserve compatibility with base dita?":
        return "DITA specialization preserves compatibility by keeping base ancestry in the `class` attribute, so processors can fall back to known base semantics even when they do not understand the specialized element name."
    if q == "what major preprocessing stages occur before dita-ot transformation?":
        return "Before final transformation, DITA-OT preprocessing typically resolves maps, applies filtering, cascades metadata, resolves keys and content references, handles copy-to/chunk/resource roles, and writes intermediate job state."
    if "cascade=\"merge\"" in q:
        return "In DITA metadata cascading, `cascade=\"merge\"` allows inherited and local values to combine where merging is defined; `cascade=\"nomerge\"` prevents value merging but does not mean every inherited context disappears."
    if "cascade=\"nomerge\"" in q:
        return "`cascade=\"nomerge\"` is used to prevent merging of cascaded values for applicable attributes; it should not be described as a universal switch that turns off all map context."
    if "physically get written" in q:
        return "Cascaded metadata is normally effective processing context, not a permanent rewrite of the referenced topic source."
    if "topic have one effective metadata context" in q:
        return "A reused topic can have multiple effective metadata contexts, one per map branch or topic reference, even though the source topic file remains single."
    if "what problem does dita chunking solve" in q:
        return "DITA chunking controls output file organization independently from source topic organization, letting processors combine or split topics for navigation and delivery."
    if "class attribute" in q and "specialization" in q:
        return "The DITA `class` attribute records specialization ancestry, allowing processors to treat specialized elements according to their base DITA semantics."
    if "job file" in q or ".job.xml" in q:
        return "The DITA-OT job file records preprocessing state such as resources, roles, generated URIs, copy-to mappings, and source-to-output relationships used by later pipeline stages."
    if question.startswith("A ") or question.startswith("An ") or question.startswith("The ") or question.startswith("Two "):
        return "Debug this by separating source markup, active root map, effective key/filter/cascade context, preprocessing artifacts, and output-transform behavior before deciding whether it is a source defect or processor defect."
    if question.startswith("Can "):
        return "The answer depends on the DITA construct and active map context; state whether the behavior is allowed, then verify it against effective processed content rather than only the source XML."
    if question.startswith("What happens"):
        return "Describe the expected processing result, the fallback or diagnostic behavior, and the evidence a processor or editor should report."
    if question.startswith("How would") or question.startswith("How can"):
        return "Use deterministic checks: identify the active root map, inspect effective preprocessing output, compare source and generated URIs, and review processor diagnostics."
    return "Explain the DITA mechanism directly, then distinguish specification behavior from DITA-OT, AEM Guides, editor, or output-specific behavior."


def _answer(question: str, category_label: str) -> str:
    return f"""## Short answer
{_short_answer(question)}

## Senior explanation
For this question, answer from the effective DITA processing context, not only from the literal source file. A senior answer should identify the relevant source construct, explain how map context changes the effective result, and call out whether the behavior is defined by the DITA specification or by a processor such as DITA-OT, AEM Guides, an XML editor, or a specific output transform.

## Deterministic checks
- Confirm the active root map and the exact topicref branch being processed.
- Inspect preprocessing or temporary files to see effective keys, conrefs, branch filters, cascaded metadata, generated URIs, and resource roles.
- Compare source XML, effective intermediate content, processor logs, and final output artifacts.
- For reused topics, test each branch independently because one source topic can have multiple effective contexts.
- For specialization questions, inspect the DITA `class` ancestry tokens and catalog or document-type-shell integration before blaming rendering.

## Must not claim
- Do not claim source XML was permanently changed merely because metadata, keys, filters, or conrefs affected processed output.
- Do not present DITA-OT, AEM Guides, editor preview, HTML5, or PDF behavior as universal DITA specification behavior unless the source specifically supports it.
- Do not ignore map context when the question involves `keyref`, `conkeyref`, `ditavalref`, `copy-to`, `chunk`, `processing-role`, or cascading metadata.

## Behavior scope
{category_label}.
"""


def get_advanced_dita_seed_items() -> list[dict[str, Any]]:
    """Return approved learned-QA entries for the advanced DITA expert corpus."""

    items: list[dict[str, Any]] = []
    for question in _questions():
        topic, category_label, tags = _domain(question)
        items.append(
            {
                "prompt": question,
                "topic": topic,
                "tags": [*tags, "advanced-dita", "dita-expert"],
                "answer_style": ANSWER_STYLE,
                "final_answer": _answer(question, category_label),
            }
        )
    return items

