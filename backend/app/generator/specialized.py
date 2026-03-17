"""
Specialized DITA content type generation.

This module generates Task, Concept, Reference, Glossary, and Bookmap content.
"""

from typing import Dict, List, Tuple, Optional
import os
import xml.etree.ElementTree as ET
from app.generator.dita_utils import stable_id
from app.generator.generate import safe_join, sanitize_filename, _map_xml
from app.utils.xml_escape import xml_escape_text, xml_escape_attr, xml_escape_href


class SpecializedContentGenerator:
    """Generate specialized DITA content types."""
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand
    
    def generate_task_topic(
        self,
        topic_id: str,
        title: str,
        step_count: int = 5,
        include_prereq: bool = True,
        include_result: bool = True,
        include_choicetable: bool = False,
        steps_list: Optional[List[str]] = None,
        shortdesc_override: Optional[str] = None,
    ) -> bytes:
        """Generate a Task topic with steps; optionally include choicetable in taskbody. Use steps_list for Jira-derived content."""
        task = ET.Element("task", {"id": topic_id, "xml:lang": "en"})
        
        # Title
        title_elem = ET.SubElement(task, "title")
        title_elem.text = xml_escape_text(title)
        
        # Short description
        shortdesc = ET.SubElement(task, "shortdesc")
        shortdesc.text = xml_escape_text(shortdesc_override if shortdesc_override else f"Task: {title}")
        
        # Prerequisites
        if include_prereq:
            prereq = ET.SubElement(task, "prereq")
            prereq_p = ET.SubElement(prereq, "p")
            prereq_p.text = xml_escape_text("Prerequisites for this task.")
        
        # Task body
        taskbody = ET.SubElement(task, "taskbody")
        
        # Context (optional)
        if self.rand.random() > 0.5:
            context = ET.SubElement(taskbody, "context")
            context_p = ET.SubElement(context, "p")
            context_p.text = xml_escape_text("Context information for this task.")
        
        # Steps
        steps = ET.SubElement(taskbody, "steps")
        steps.set("unordered", xml_escape_attr("no"))
        
        step_texts = steps_list if steps_list else [f"Step {i}: Perform action {i}" for i in range(1, step_count + 1)]
        for i, step_text in enumerate(step_texts):
            step = ET.SubElement(steps, "step")
            step.set("importance", xml_escape_attr("required"))
            
            cmd = ET.SubElement(step, "cmd")
            cmd.text = xml_escape_text(step_text)
            
            if self.rand.random() > 0.7 and not steps_list:  # 30% chance, skip when using Jira content
                info = ET.SubElement(step, "info")
                info_p = ET.SubElement(info, "p")
                info_p.text = xml_escape_text(f"Additional information for step {i + 1}.")
            
            if self.rand.random() > 0.8 and not steps_list:  # 20% chance, skip when using Jira content
                substeps = ET.SubElement(step, "substeps")
                for j in range(1, 3):
                    substep = ET.SubElement(substeps, "substep")
                    substep_cmd = ET.SubElement(substep, "cmd")
                    substep_cmd.text = xml_escape_text(f"Substep {i + 1}.{j}")
        
        # Result
        if include_result:
            result = ET.SubElement(taskbody, "result")
            result_p = ET.SubElement(result, "p")
            result_p.text = xml_escape_text("Expected result after completing this task.")
        
        # Choicetable (optional - valid in taskbody for options/choices)
        if include_choicetable:
            choicetable = ET.SubElement(taskbody, "choicetable")
            choicetable.set("id", xml_escape_attr(f"choices_{topic_id}"))
            for row_idx in range(1, 3):
                chrow = ET.SubElement(choicetable, "chrow")
                choption = ET.SubElement(chrow, "choption")
                choption.text = xml_escape_text(f"Option {row_idx}")
                chdesc = ET.SubElement(chrow, "chdesc")
                chdesc_p = ET.SubElement(chdesc, "p")
                chdesc_p.text = xml_escape_text(f"Description for option {row_idx}.")
        
        # Example (optional)
        if self.rand.random() > 0.7:
            example = ET.SubElement(taskbody, "example")
            example_p = ET.SubElement(example, "p")
            example_p.text = xml_escape_text("Example of completing this task.")
        
        # Generate XML
        xml_body = ET.tostring(task, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_topic}\n'
        return doc.encode("utf-8") + xml_body
    
    def generate_concept_topic(
        self,
        topic_id: str,
        title: str,
        section_count: int = 3,
        shortdesc_override: Optional[str] = None,
        body_snippets: Optional[List[str]] = None,
    ) -> bytes:
        """Generate a Concept topic. Use body_snippets for Jira-derived content."""
        concept = ET.Element("concept", {"id": topic_id, "xml:lang": "en"})
        
        # Title
        title_elem = ET.SubElement(concept, "title")
        title_elem.text = xml_escape_text(title)
        
        # Short description
        shortdesc = ET.SubElement(concept, "shortdesc")
        shortdesc.text = xml_escape_text(shortdesc_override if shortdesc_override else f"Concept: {title}")
        
        # Concept body
        conbody = ET.SubElement(concept, "conbody")
        
        if body_snippets:
            for snippet in body_snippets:
                p_elem = ET.SubElement(conbody, "p")
                p_elem.text = xml_escape_text(snippet)
        else:
            # Introduction paragraph
            intro_p = ET.SubElement(conbody, "p")
            intro_p.text = xml_escape_text(f"This concept explains {title.lower()}.")
            
            # Sections
            for i in range(1, section_count + 1):
                section = ET.SubElement(conbody, "section")
                section.set("id", xml_escape_attr(f"section_{topic_id}_{i}"))
                
                section_title = ET.SubElement(section, "title")
                section_title.text = xml_escape_text(f"Section {i}")
                
                section_p = ET.SubElement(section, "p")
                section_p.text = xml_escape_text(f"Content for section {i}.")
            
            # Nested sections (optional)
            if self.rand.random() > 0.7:
                nested_section = ET.SubElement(section, "section")
                nested_title = ET.SubElement(nested_section, "title")
                nested_title.text = xml_escape_text(f"Subsection {i}.1")
                nested_p = ET.SubElement(nested_section, "p")
                nested_p.text = xml_escape_text("Nested section content.")
        
        # Related links (optional)
        if self.rand.random() > 0.6:
            related_links = ET.SubElement(concept, "related-links")
            link = ET.SubElement(related_links, "link")
            link.set("href", xml_escape_attr("#"))
            linktext = ET.SubElement(link, "linktext")
            linktext.text = xml_escape_text("Related topic")
        
        # Generate XML
        xml_body = ET.tostring(concept, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_topic}\n'
        return doc.encode("utf-8") + xml_body
    
    def generate_reference_topic(
        self,
        topic_id: str,
        title: str,
        property_count: int = 5,
        include_choicetable: bool = False,
    ) -> bytes:
        """Generate a Reference topic with refbody, refsyn, section, properties; optionally choicetable."""
        reference = ET.Element("reference", {"id": topic_id, "xml:lang": "en"})
        
        # Title
        title_elem = ET.SubElement(reference, "title")
        title_elem.text = xml_escape_text(title)
        
        # Short description
        shortdesc = ET.SubElement(reference, "shortdesc")
        shortdesc.text = xml_escape_text(f"Reference: {title}")
        
        # Refbody
        refbody = ET.SubElement(reference, "refbody")
        
        # Refsyn
        refsyn = ET.SubElement(refbody, "refsyn")
        refsyn_p = ET.SubElement(refsyn, "p")
        refsyn_p.text = xml_escape_text(f"Syntax reference for {title}.")
        
        # Properties table
        if property_count > 0:
            properties = ET.SubElement(refbody, "properties")
            properties.set("outputclass", xml_escape_attr("reference-properties"))
            
            for i in range(1, property_count + 1):
                property_elem = ET.SubElement(properties, "property")
                property_elem.set("id", xml_escape_attr(f"prop_{topic_id}_{i}"))
                
                prop_title = ET.SubElement(property_elem, "title")
                prop_title.text = xml_escape_text(f"Property {i}")
                
                prop_value = ET.SubElement(property_elem, "value")
                prop_value.text = xml_escape_text(f"Value {i}")
                
                prop_desc = ET.SubElement(property_elem, "desc")
                prop_desc_p = ET.SubElement(prop_desc, "p")
                prop_desc_p.text = xml_escape_text(f"Description of property {i}.")
        
        # Choicetable (chrow, choption, chdesc) when requested
        if include_choicetable:
            choicetable = ET.SubElement(refbody, "choicetable")
            choicetable.set("id", xml_escape_attr(f"choices_{topic_id}"))
            for row_idx in range(1, 4):
                chrow = ET.SubElement(choicetable, "chrow")
                choption = ET.SubElement(chrow, "choption")
                choption.text = xml_escape_text(f"Option {row_idx}")
                chdesc = ET.SubElement(chrow, "chdesc")
                chdesc_p = ET.SubElement(chdesc, "p")
                chdesc_p.text = xml_escape_text(f"Description for option {row_idx}.")
        
        # Sections
        section = ET.SubElement(refbody, "section")
        section.set("id", xml_escape_attr(f"details_{topic_id}"))
        section_title = ET.SubElement(section, "title")
        section_title.text = xml_escape_text("Details")
        section_p = ET.SubElement(section, "p")
        section_p.text = xml_escape_text("Detailed reference information.")
        
        # Generate XML
        xml_body = ET.tostring(reference, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_topic}\n'
        return doc.encode("utf-8") + xml_body
    
    def generate_glossary_entry(
        self,
        entry_id: str,
        term: str,
        definition: str,
        acronym: Optional[str] = None,
    ) -> bytes:
        """Generate a Glossary entry."""
        glossentry = ET.Element("glossentry", {"id": entry_id, "xml:lang": "en"})
        
        # Glossterm
        glossterm = ET.SubElement(glossentry, "glossterm")
        glossterm.text = xml_escape_text(term)
        
        # Acronym (optional)
        if acronym:
            alt = ET.SubElement(glossentry, "alt")
            alt.set("platform", xml_escape_attr("acronym"))
            alt.text = xml_escape_text(acronym)
        
        # Glossdef
        glossdef = ET.SubElement(glossentry, "glossdef")
        glossdef_p = ET.SubElement(glossdef, "p")
        glossdef_p.text = xml_escape_text(definition)
        
        # GlossBody (optional, for extended definitions)
        if self.rand.random() > 0.7:
            glossbody = ET.SubElement(glossentry, "glossBody")
            body_p = ET.SubElement(glossbody, "p")
            body_p.text = xml_escape_text("Extended definition content.")
        
        # Generate XML
        xml_body = ET.tostring(glossentry, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_glossentry}\n'
        return doc.encode("utf-8") + xml_body

    def generate_bookmap(
        self,
        map_id: str,
        title: str,
        chapters: List[Tuple[str, str, List[Tuple[str, str]]]],  # (chapter_path, chapter_title, [(topic_path, topic_title), ...])
        map_path: str,
        include_frontmatter: bool = True,
        include_backmatter: bool = True,
    ) -> bytes:
        """Generate a Bookmap structure."""
        from app.generator.generate import _rel_href
        
        bookmap = ET.Element("bookmap", {"id": map_id, "xml:lang": "en"})
        
        # Title
        title_elem = ET.SubElement(bookmap, "title")
        title_elem.text = xml_escape_text(title)
        
        # Bookmeta
        bookmeta = ET.SubElement(bookmap, "bookmeta")
        
        # Booktitle
        booktitle = ET.SubElement(bookmeta, "booktitle")
        mainbooktitle = ET.SubElement(booktitle, "mainbooktitle")
        mainbooktitle.text = xml_escape_text(title)
        
        # Book abstract (optional)
        if self.rand.random() > 0.5:
            bookabstract = ET.SubElement(bookmeta, "bookabstract")
            abstract_p = ET.SubElement(bookabstract, "p")
            abstract_p.text = xml_escape_text(f"Abstract for {title}.")
        
        # Frontmatter
        if include_frontmatter:
            frontmatter = ET.SubElement(bookmap, "frontmatter")
            
            # Notices
            notices = ET.SubElement(frontmatter, "notices")
            notices_ref = ET.SubElement(notices, "topicref")
            notices_href = _rel_href(map_path, safe_join(os.path.dirname(map_path), "frontmatter", "notices.dita"))
            notices_ref.set("href", xml_escape_href(notices_href))
            notices_ref.set("type", xml_escape_attr("topic"))
            
            # Preface
            preface = ET.SubElement(frontmatter, "preface")
            preface_ref = ET.SubElement(preface, "topicref")
            preface_href = _rel_href(map_path, safe_join(os.path.dirname(map_path), "frontmatter", "preface.dita"))
            preface_ref.set("href", xml_escape_href(preface_href))
            preface_ref.set("type", xml_escape_attr("topic"))
        
        # Chapters
        for chapter_path, chapter_title, chapter_topics in chapters:
            chapter = ET.SubElement(bookmap, "chapter")
            chapter_ref = ET.SubElement(chapter, "topicref")
            chapter_href = _rel_href(map_path, chapter_path)
            chapter_ref.set("href", xml_escape_href(chapter_href))
            chapter_ref.set("type", xml_escape_attr("topic"))
            chapter_ref.set("navtitle", xml_escape_attr(chapter_title))
            
            # Add topicrefs for each topic in the chapter
            for topic_path, topic_title in chapter_topics:
                topic_ref = ET.SubElement(chapter, "topicref")
                topic_href = _rel_href(map_path, topic_path)
                topic_ref.set("href", xml_escape_href(topic_href))
                topic_ref.set("type", xml_escape_attr("topic"))
                topic_ref.set("navtitle", xml_escape_attr(topic_title))
        
        # Backmatter
        if include_backmatter:
            backmatter = ET.SubElement(bookmap, "backmatter")
            
            # Appendix
            appendix = ET.SubElement(backmatter, "appendix")
            appendix_ref = ET.SubElement(appendix, "topicref")
            appendix_href = _rel_href(map_path, safe_join(os.path.dirname(map_path), "backmatter", "appendix.dita"))
            appendix_ref.set("href", xml_escape_href(appendix_href))
            appendix_ref.set("type", xml_escape_attr("topic"))
            
            # Index
            index = ET.SubElement(backmatter, "indexlist")
            index_ref = ET.SubElement(index, "topicref")
            index_href = _rel_href(map_path, safe_join(os.path.dirname(map_path), "backmatter", "index.dita"))
            index_ref.set("href", xml_escape_href(index_href))
            index_ref.set("type", xml_escape_attr("topic"))
        
        # Generate XML
        xml_body = ET.tostring(bookmap, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_map}\n'
        return doc.encode("utf-8") + xml_body


def generate_task_topics_dataset(
    config,
    base: str,
    topic_count: int = 50,
    steps_per_task: int = 5,
    include_map: bool = True,
    include_choicetable: bool = False,
    rand=None,
    content_titles: Optional[List[str]] = None,
    content_shortdescs: Optional[List[str]] = None,
    content_steps: Optional[List[str]] = None,
) -> Dict[str, bytes]:
    """Generate a dataset with Task topics; optionally include choicetable in taskbody. Use content_* for Jira-derived production content."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    titles = content_titles if content_titles else None
    shortdescs = content_shortdescs if content_shortdescs else None
    steps = content_steps if content_steps else None
    use_content = bool(titles)
    n_topics = len(titles) if titles else topic_count
    
    generator = SpecializedContentGenerator(config, rand)
    files = {}
    used_ids = set()
    topic_dir = safe_join(base, "topics", "tasks")
    topic_paths = []
    
    for i in range(1, n_topics + 1):
        filename = sanitize_filename(f"task_{i:05d}.dita", config.windows_safe_filenames)
        path = safe_join(topic_dir, filename)
        topic_id = stable_id(config.seed, "task", str(i), used_ids)
        
        title = titles[i - 1] if titles else f"Task {i:05d}"
        shortdesc = shortdescs[i - 1] if shortdescs and i <= len(shortdescs) else None
        steps_list = steps if use_content and steps and i == 1 else None
        
        if steps_list:
            step_count = len(steps_list)
        else:
            min_steps = max(3, steps_per_task) if steps_per_task >= 3 else 3
            max_steps = max(steps_per_task, 5)
            step_count = rand.randint(min_steps, max_steps)
        
        topic_xml = generator.generate_task_topic(
            topic_id,
            title,
            step_count=step_count,
            steps_list=steps_list,
            shortdesc_override=shortdesc,
            include_choicetable=include_choicetable or rand.random() > 0.8,  # ~20% get choicetable when not explicit
        )
        
        files[path] = topic_xml
        topic_paths.append(path)
    
    # Validate that all topics were created before generating map
    import logging
    logger = logging.getLogger(__name__)
    
    if len(topic_paths) != n_topics:
        logger.error(
            f"Task topics generation mismatch: Expected {n_topics} topics, "
            f"but only {len(topic_paths)} paths were collected"
        )
    
    # Generate map if requested - ONLY after ALL topics are created
    if include_map:
        # Ensure we have all topic paths before generating map
        if len(topic_paths) != n_topics:
            logger.warning(
                f"Generating map with incomplete topic list: {len(topic_paths)}/{n_topics} topics"
            )
        
        map_filename = sanitize_filename("task_topics.ditamap", config.windows_safe_filenames)
        map_path = safe_join(base, map_filename)
        map_id = stable_id(config.seed, "task_topics_map", "", used_ids)
        
        from app.generator.generate import _rel_href
        hrefs = [_rel_href(map_path, tp) for tp in topic_paths]
        
        logger.debug(
            f"Generating task topics map with {len(hrefs)} topicrefs "
            f"(expected {n_topics} topics)"
        )
        
        map_xml = _map_xml(
            config,
            map_id=map_id,
            title="Task Topics Map",
            topicref_hrefs=hrefs,
            keydef_entries=[],
            scoped_blocks=[],
        )
        files[map_path] = map_xml
        
        logger.info(
            f"Task topics map generated: {len(hrefs)} topicrefs, "
            f"{len(files)} total files (including map)"
        )
    
    return files


def generate_concept_topics_dataset(
    config,
    base: str,
    topic_count: int = 50,
    sections_per_concept: int = 3,
    include_map: bool = True,
    rand=None,
    content_titles: Optional[List[str]] = None,
    content_shortdescs: Optional[List[str]] = None,
    content_body_snippets: Optional[List[str]] = None,
) -> Dict[str, bytes]:
    """Generate a dataset with Concept topics. Use content_* for Jira-derived production content."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    titles = content_titles if content_titles else None
    shortdescs = content_shortdescs if content_shortdescs else None
    body_snippets = content_body_snippets if content_body_snippets else None
    use_content = bool(titles)
    n_topics = len(titles) if titles else topic_count
    
    generator = SpecializedContentGenerator(config, rand)
    files = {}
    used_ids = set()
    topic_dir = safe_join(base, "topics", "concepts")
    topic_paths = []
    
    for i in range(1, n_topics + 1):
        filename = sanitize_filename(f"concept_{i:05d}.dita", config.windows_safe_filenames)
        path = safe_join(topic_dir, filename)
        topic_id = stable_id(config.seed, "concept", str(i), used_ids)
        
        title = titles[i - 1] if titles else f"Concept {i:05d}"
        shortdesc = shortdescs[i - 1] if shortdescs and i <= len(shortdescs) else None
        snippets = body_snippets if body_snippets and i == 1 else None
        
        topic_xml = generator.generate_concept_topic(
            topic_id,
            title,
            section_count=rand.randint(2, sections_per_concept),
            shortdesc_override=shortdesc,
            body_snippets=snippets,
        )
        
        files[path] = topic_xml
        topic_paths.append(path)
    
    # Validate that all topics were created before generating map
    import logging
    logger = logging.getLogger(__name__)
    
    if len(topic_paths) != n_topics:
        logger.error(
            f"Concept topics generation mismatch: Expected {n_topics} topics, "
            f"but only {len(topic_paths)} paths were collected"
        )
    
    # Generate map if requested - ONLY after ALL topics are created
    if include_map:
        # Ensure we have all topic paths before generating map
        if len(topic_paths) != n_topics:
            logger.warning(
                f"Generating map with incomplete topic list: {len(topic_paths)}/{n_topics} topics"
            )
        
        map_filename = sanitize_filename("concept_topics.ditamap", config.windows_safe_filenames)
        map_path = safe_join(base, map_filename)
        map_id = stable_id(config.seed, "concept_topics_map", "", used_ids)
        
        from app.generator.generate import _rel_href
        hrefs = [_rel_href(map_path, tp) for tp in topic_paths]
        
        logger.debug(
            f"Generating concept topics map with {len(hrefs)} topicrefs "
            f"(expected {n_topics} topics)"
        )
        
        map_xml = _map_xml(
            config,
            map_id=map_id,
            title="Concept Topics Map",
            topicref_hrefs=hrefs,
            keydef_entries=[],
            scoped_blocks=[],
        )
        files[map_path] = map_xml
        
        logger.info(
            f"Concept topics map generated: {len(hrefs)} topicrefs, "
            f"{len(files)} total files (including map)"
        )
    
    return files


def generate_reference_topics_dataset(
    config,
    base: str,
    topic_count: int = 50,
    properties_per_ref: int = 5,
    include_map: bool = True,
    include_choicetable: bool = False,
    rand=None,
) -> Dict[str, bytes]:
    """Generate a dataset with Reference topics (refbody, refsyn, section, properties; optionally choicetable)."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    generator = SpecializedContentGenerator(config, rand)
    files = {}
    used_ids = set()
    topic_dir = safe_join(base, "topics", "references")
    topic_paths = []
    
    for i in range(1, topic_count + 1):
        filename = sanitize_filename(f"reference_{i:05d}.dita", config.windows_safe_filenames)
        path = safe_join(topic_dir, filename)
        topic_id = stable_id(config.seed, "reference", str(i), used_ids)
        
        topic_xml = generator.generate_reference_topic(
            topic_id,
            f"Reference {i:05d}",
            property_count=rand.randint(3, properties_per_ref),
            include_choicetable=include_choicetable or rand.random() > 0.7,  # ~30% get choicetable when not explicit
        )
        
        files[path] = topic_xml
        topic_paths.append(path)
    
    # Validate that all topics were created before generating map
    import logging
    logger = logging.getLogger(__name__)
    
    if len(topic_paths) != topic_count:
        logger.error(
            f"Reference topics generation mismatch: Expected {topic_count} topics, "
            f"but only {len(topic_paths)} paths were collected"
        )
    
    # Generate map if requested - ONLY after ALL topics are created
    if include_map:
        # Ensure we have all topic paths before generating map
        if len(topic_paths) != topic_count:
            logger.warning(
                f"Generating map with incomplete topic list: {len(topic_paths)}/{topic_count} topics"
            )
        
        map_filename = sanitize_filename("reference_topics.ditamap", config.windows_safe_filenames)
        map_path = safe_join(base, map_filename)
        map_id = stable_id(config.seed, "reference_topics_map", "", used_ids)
        
        from app.generator.generate import _rel_href
        hrefs = [_rel_href(map_path, tp) for tp in topic_paths]
        
        logger.debug(
            f"Generating reference topics map with {len(hrefs)} topicrefs "
            f"(expected {topic_count} topics)"
        )
        
        map_xml = _map_xml(
            config,
            map_id=map_id,
            title="Reference Topics Map",
            topicref_hrefs=hrefs,
            keydef_entries=[],
            scoped_blocks=[],
        )
        files[map_path] = map_xml
        
        logger.info(
            f"Reference topics map generated: {len(hrefs)} topicrefs, "
            f"{len(files)} total files (including map)"
        )
    
    return files


def generate_glossary_dataset(
    config,
    base: str,
    entry_count: int = 100,
    rand=None,
) -> Dict[str, bytes]:
    """Generate a Glossary dataset."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    generator = SpecializedContentGenerator(config, rand)
    files = {}
    used_ids = set()
    glossary_dir = safe_join(base, "glossary")
    
    # Generate individual glossary entries
    for i in range(1, entry_count + 1):
        filename = sanitize_filename(f"glossentry_{i:05d}.dita", config.windows_safe_filenames)
        path = safe_join(glossary_dir, filename)
        entry_id = stable_id(config.seed, "gloss", str(i), used_ids)
        
        term = f"Term {i}"
        definition = f"Definition for term {i}."
        acronym = f"T{i}" if rand.random() > 0.7 else None
        
        entry_xml = generator.generate_glossary_entry(
            entry_id,
            term,
            definition,
            acronym,
        )
        
        files[path] = entry_xml
    
    # Generate glossary map
    map_filename = sanitize_filename("glossary.ditamap", config.windows_safe_filenames)
    map_path = safe_join(glossary_dir, map_filename)
    map_id = stable_id(config.seed, "glossary-map", "", used_ids)
    
    refs = []
    for i in range(1, min(entry_count + 1, 50)):  # Limit map size
        filename = sanitize_filename(f"glossentry_{i:05d}.dita", config.windows_safe_filenames)
        ref_path = safe_join(glossary_dir, filename)
        refs.append(ref_path)
    
    from app.generator.generate import _rel_href
    hrefs = [_rel_href(map_path, ref) for ref in refs]
    
    map_xml = _map_xml(
        config,
        map_id=map_id,
        title="Glossary",
        topicref_hrefs=hrefs,
        keydef_entries=[],
        scoped_blocks=[],
    )
    
    files[map_path] = map_xml
    
    return files


def generate_bookmap_dataset(
    config,
    base: str,
    chapter_count: int = 10,
    topics_per_chapter: int = 5,
    include_frontmatter: bool = True,
    include_backmatter: bool = True,
    rand=None,
) -> Dict[str, bytes]:
    """Generate a Bookmap dataset."""
    if rand is None:
        import random
        rand = random.Random(config.seed)
    
    generator = SpecializedContentGenerator(config, rand)
    files = {}
    used_ids = set()
    
    # Generate chapter topics and topics within each chapter
    chapters = []
    chapters_dir = safe_join(base, "book", "chapters")
    
    for i in range(1, chapter_count + 1):
        # Generate chapter topic
        chapter_filename = sanitize_filename(f"chapter_{i:05d}.dita", config.windows_safe_filenames)
        chapter_path = safe_join(chapters_dir, chapter_filename)
        chapter_id = stable_id(config.seed, "chapter", str(i), used_ids)
        
        chapter_xml = generator.generate_concept_topic(
            chapter_id,
            f"Chapter {i}",
            section_count=3,
        )
        files[chapter_path] = chapter_xml
        
        # Generate topics for this chapter
        chapter_topics = []
        for j in range(1, topics_per_chapter + 1):
            topic_filename = sanitize_filename(f"chapter_{i:05d}_topic_{j:03d}.dita", config.windows_safe_filenames)
            topic_path = safe_join(chapters_dir, topic_filename)
            topic_id = stable_id(config.seed, "chapter_topic", f"{i}_{j}", used_ids)
            
            # Alternate between concept and task topics
            if j % 2 == 0:
                topic_xml = generator.generate_task_topic(
                    topic_id,
                    f"Chapter {i} - Task {j}",
                    step_count=3,
                    include_prereq=True,
                    include_result=True,
                )
            else:
                topic_xml = generator.generate_concept_topic(
                    topic_id,
                    f"Chapter {i} - Concept {j}",
                    section_count=2,
                )
            
            files[topic_path] = topic_xml
            chapter_topics.append((topic_path, f"Chapter {i} - Topic {j}"))
        
        chapters.append((chapter_path, f"Chapter {i}", chapter_topics))
    
    # Generate frontmatter topics
    if include_frontmatter:
        frontmatter_dir = safe_join(base, "book", "frontmatter")
        notices_path = safe_join(frontmatter_dir, "notices.dita")
        notices_xml = generator.generate_concept_topic(
            stable_id(config.seed, "notices", "", used_ids),
            "Notices",
            section_count=2,
        )
        files[notices_path] = notices_xml
        
        preface_path = safe_join(frontmatter_dir, "preface.dita")
        preface_xml = generator.generate_concept_topic(
            stable_id(config.seed, "preface", "", used_ids),
            "Preface",
            section_count=2,
        )
        files[preface_path] = preface_xml
    
    # Generate backmatter topics
    if include_backmatter:
        backmatter_dir = safe_join(base, "book", "backmatter")
        appendix_path = safe_join(backmatter_dir, "appendix.dita")
        appendix_xml = generator.generate_reference_topic(
            stable_id(config.seed, "appendix", "", used_ids),
            "Appendix",
            property_count=3,
        )
        files[appendix_path] = appendix_xml
        
        index_path = safe_join(backmatter_dir, "index.dita")
        index_xml = generator.generate_reference_topic(
            stable_id(config.seed, "index", "", used_ids),
            "Index",
            property_count=0,
        )
        files[index_path] = index_xml
    
    # Generate bookmap
    bookmap_dir = safe_join(base, "book")
    bookmap_filename = sanitize_filename("bookmap.ditamap", config.windows_safe_filenames)
    bookmap_path = safe_join(bookmap_dir, bookmap_filename)
    bookmap_id = stable_id(config.seed, "bookmap", "", used_ids)
    
    bookmap_xml = generator.generate_bookmap(
        bookmap_id,
        "Generated Book",
        chapters,
        bookmap_path,
        include_frontmatter=include_frontmatter,
        include_backmatter=include_backmatter,
    )
    
    files[bookmap_path] = bookmap_xml
    
    return files


RECIPE_SPECS = [
    {
        "id": "task_topics",
        "title": "Task Topics",
        "description": "Generate DITA task topics with procedural steps, prerequisites, and results",
        "tags": ["task", "procedure", "steps"],
        "module": "app.generator.specialized",
        "function": "generate_task_topics_dataset",
        "params_schema": {"topic_count": "int", "steps_per_task": "int", "include_map": "bool", "include_choicetable": "bool"},
        "default_params": {"topic_count": 50, "steps_per_task": 5, "include_map": True, "include_choicetable": False},
        "stability": "stable",
        "constructs": ["task", "steps", "prereq", "result"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY", "SCALE"],
        "use_when": ["task topic", "procedure", "steps", "how-to"],
        "avoid_when": ["concept only", "reference only"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "medium",
    },
    {
        "id": "concept_topics",
        "title": "Concept Topics",
        "description": "Generate DITA concept topics with sections and explanatory content",
        "tags": ["concept", "explanation", "sections"],
        "module": "app.generator.specialized",
        "function": "generate_concept_topics_dataset",
        "params_schema": {"topic_count": "int", "sections_per_concept": "int", "include_map": "bool"},
        "default_params": {"topic_count": 50, "sections_per_concept": 3, "include_map": True},
        "stability": "stable",
        "constructs": ["concept", "section", "explanation"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY", "SCALE"],
        "use_when": ["concept topic", "explanation", "background"],
        "avoid_when": ["task only", "reference only"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "medium",
    },
    {
        "id": "reference_topics",
        "title": "Reference Topics",
        "description": "Generate DITA reference topics with refbody, refsyn, section, properties, choicetable",
        "tags": ["reference", "properties", "definitions", "refbody", "refsyn", "choicetable"],
        "module": "app.generator.specialized",
        "function": "generate_reference_topics_dataset",
        "params_schema": {"topic_count": "int", "properties_per_ref": "int", "include_map": "bool", "include_choicetable": "bool"},
        "default_params": {"topic_count": 50, "properties_per_ref": 5, "include_map": True, "include_choicetable": False},
        "stability": "stable",
        "constructs": ["reference", "properties", "definitions"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY", "SCALE"],
        "use_when": ["reference topic", "properties", "API reference"],
        "avoid_when": ["task only", "concept only"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "medium",
    },
    {
        "id": "glossary",
        "title": "Glossary",
        "description": "Generate glossary entries with terms, definitions, and optional acronyms",
        "tags": ["glossary", "terms", "definitions"],
        "module": "app.generator.specialized",
        "function": "generate_glossary_dataset",
        "params_schema": {"entry_count": "int"},
        "default_params": {"entry_count": 100},
        "stability": "stable",
        "constructs": ["glossentry", "glossterm", "glossdef"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY", "SCALE"],
        "use_when": ["glossary", "terms", "definitions", "acronyms"],
        "avoid_when": ["no glossary", "concept only"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "medium",
    },
    {
        "id": "bookmap",
        "title": "Bookmap",
        "description": "Generate bookmap structure with chapters, frontmatter, and backmatter",
        "tags": ["bookmap", "chapters", "book"],
        "module": "app.generator.specialized",
        "function": "generate_bookmap_dataset",
        "params_schema": {"chapter_count": "int", "topics_per_chapter": "int", "include_frontmatter": "bool", "include_backmatter": "bool"},
        "default_params": {"chapter_count": 10, "topics_per_chapter": 5, "include_frontmatter": True, "include_backmatter": True},
        "stability": "stable",
        "constructs": ["bookmap", "chapter", "frontmatter", "backmatter"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY", "SCALE"],
        "use_when": ["bookmap", "chapters", "book structure", "frontmatter backmatter"],
        "avoid_when": ["simple map", "flat map"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "medium",
    },
]
