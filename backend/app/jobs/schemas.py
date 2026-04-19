from pydantic import BaseModel, Field, field_validator, model_validator, Discriminator
from typing import Literal, List, Optional, Union, Annotated
from datetime import datetime

class IncrementalTopicrefMapsRecipe(BaseModel):
    """
    Recipe for generating incremental topicref maps.
    
    Generates a pool of topics and multiple maps with varying topicref counts:
    - Pool of topic files (configurable size)
    - Multiple map files, each referencing different numbers of topics
    - Tests map parsing with varying topicref counts (10, 100, 1000, 5000, 10000+)
    
    Output includes:
    - Topic pool files (.dita)
    - Multiple map files with incremental topicref counts (.ditamap)
    """
    type: Literal["incremental_topicref_maps"] = "incremental_topicref_maps"
    pool_size: int = Field(default=10000, ge=1, description="Size of topic pool to generate. Must be >= max(map_topicref_counts)")
    map_topicref_counts: List[int] = Field(default=[10, 100, 1000, 5000, 10000])
    pretty_print: bool = True
    deep_folders: bool = False
    
    @field_validator('map_topicref_counts')
    @classmethod
    def validate_map_counts(cls, v):
        if not v:
            raise ValueError("map_topicref_counts cannot be empty")
        if max(v) > 10000:
            raise ValueError("max topicref count cannot exceed 10000")
        return v
    
    @model_validator(mode='after')
    def validate_pool_size(self):
        if max(self.map_topicref_counts) > self.pool_size:
            raise ValueError(f"max(map_topicref_counts) ({max(self.map_topicref_counts)}) must be <= pool_size ({self.pool_size})")
        return self

class HeavyTopicsTablesCodeblocksRecipe(BaseModel):
    """
    Recipe for generating topics with tables and codeblocks.
    
    Generates DITA topics containing:
    - Multiple tables per topic (configurable columns and rows)
    - Multiple codeblocks per topic (configurable lines and languages)
    - Heavy structured content for testing content processing performance
    
    Output includes:
    - DITA topic files with tables and codeblocks
    - Optional DITA map file referencing all topics
    """
    type: Literal["heavy_topics_tables_codeblocks"] = "heavy_topics_tables_codeblocks"
    topic_count: int = Field(default=50, ge=10, le=5000)
    tables_per_topic: int = Field(default=5, ge=0, le=20)
    codeblocks_per_topic: int = Field(default=5, ge=0, le=20)
    table_cols: int = Field(default=4, ge=2, le=10)
    table_rows: int = Field(default=10, ge=1, le=100)
    code_lines_per_codeblock: int = Field(default=20, ge=1, le=200)
    include_map: bool = True
    map_topicref_count: int = Field(default=50, ge=1)
    pretty_print: bool = True
    windows_safe_paths: bool = True
    
    @model_validator(mode='after')
    def validate_map_topicref_count(self):
        if self.include_map and self.map_topicref_count > self.topic_count:
            raise ValueError(f"map_topicref_count ({self.map_topicref_count}) must be <= topic_count ({self.topic_count})")
        return self

class CustomerReusePackRecipe(BaseModel):
    """Recipe for generating customer reuse pack."""
    type: Literal["customer_reuse_pack"] = "customer_reuse_pack"
    remove_map_count: int = Field(default=10, ge=1, le=100)
    shared_topics: int = Field(default=500, ge=10, le=10000)
    topic_references_per_map: int = Field(default=100, ge=1, le=1000)
    key_definitions: int = Field(default=200, ge=0, le=5000)
    key_groups: int = Field(default=5, ge=0, le=50)
    external_references: int = Field(default=10, ge=0, le=100)

class MapParseStressRecipe(BaseModel):
    """
    Recipe for map parsing stress tests.
    
    Generates maps with many topicrefs to stress test map parsing performance:
    - Multiple maps, each with a large number of topicrefs
    - Topics pool shared across maps
    - Tests map parser performance with high topicref counts
    
    Output includes:
    - Topic files (pool shared across maps)
    - Multiple map files, each with many topicrefs (1000+ per map)
    """
    type: Literal["map_parse_stress"] = "map_parse_stress"
    map_count: int = Field(default=10, ge=1, le=100)
    topicrefs_per_map: int = Field(default=1000, ge=10, le=10000)
    pretty_print: bool = True


class BulkDitaMapTopicsRecipe(BaseModel):
    """
    Single root DITAMAP referencing many simple DITA topics (bulk / scale testing).

    Same idea as ``generate_dita_20k_dataset.py``: ``topics/topic_XXXXX.dita`` and one
    ``rootmap_{N}.ditamap`` with navtitle on each topicref.
    """
    type: Literal["bulk_dita_map_topics"] = "bulk_dita_map_topics"
    topic_count: int = Field(
        default=20000,
        ge=1,
        le=25000,
        description="Number of topic files; one root map lists all topicrefs",
    )
    include_readme: bool = Field(default=True, description="Emit README.txt in dataset folder")
    pretty_print: bool = True
    include_local_dtd_stubs: bool = Field(
        default=True,
        description=(
            "Emit minimal topic.dtd/map.dtd under technicalContent/dtd/ and use doctypes that resolve "
            "from topics/ and the root map (Builder default). When false, stubs sit at dataset root only."
        ),
    )


class RelationshipTableRecipe(BaseModel):
    """Recipe for generating relationship tables."""
    type: Literal["relationship_table"] = "relationship_table"
    topic_count: int = Field(default=100, ge=10, le=10000)
    relationship_types: List[str] = Field(
        default=["next", "previous", "related"],
        description="Types of relationships to generate"
    )
    relationship_density: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Density of relationships (0.0 to 1.0)"
    )
    include_map: bool = True
    pretty_print: bool = True

class LocalizedContentRecipe(BaseModel):
    """
    Recipe for generating localized/multi-language content.
    
    Generates language variants of base content:
    - Base content from selected base recipe
    - Language copies for each target language
    - Translation metadata files
    
    Output includes:
    - Base content files (from base_recipe)
    - Language variant files for each target language
    - Translation metadata JSON file
    """
    type: Literal["localized_content"] = "localized_content"
    base_recipe: dict = Field(
        description="Base recipe configuration to localize"
    )
    source_language: str = Field(default="en", description="Source language code")
    target_languages: List[str] = Field(
        default=["es", "fr", "de"],
        description="Target language codes"
    )
    include_translation_metadata: bool = True

class ConrefPackRecipe(BaseModel):
    """
    Recipe for generating conref-based content reuse.
    
    Generates topics with content references (conrefs) for content reuse:
    - Topics with reusable elements
    - Topics that reference reusable content via conrefs
    - Configurable conref density
    
    Output includes:
    - DITA topic files with conrefs
    - Optional DITA map file
    """
    type: Literal["conref_pack"] = "conref_pack"
    topic_count: int = Field(default=50, ge=10, le=5000)
    reusable_elements_per_topic: int = Field(default=3, ge=1, le=10)
    conref_density: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Density of conrefs (0.0 to 1.0)"
    )
    include_map: bool = True
    pretty_print: bool = True

class ConrefendCyclicDuplicateIdRecipe(BaseModel):
    """
    Recipe for conrefend + cyclic references causing false duplicate ID warnings.

    Generates topics with conref+conrefend where Topic A conrefs (range) to Topic B,
    and Topic B conrefs (range) back to Topic A. Reproduces false "Duplicate ID"
    warnings in Guides Web Editor (IBM scenario).
    """
    type: Literal["conrefend_cyclic_duplicate_id"] = "conrefend_cyclic_duplicate_id"
    id_prefix: str = Field(default="t", description="Unique ID prefix for generated elements")
    pretty_print: bool = True

class MapCyclicRecipe(BaseModel):
    """
    Recipe for map-level cyclic references (mapref cycle).

    Generates map_a.ditamap and map_b.ditamap where each maprefs the other.
    Cycle: map_a -> map_b -> map_a. For testing map processor handling of cyclic mapref.
    """
    type: Literal["map_cyclic"] = "map_cyclic"
    id_prefix: str = Field(default="t", description="Unique ID prefix for generated elements")
    pretty_print: bool = True

class DitaConrefTitleDatasetRecipe(BaseModel):
    """
    Recipe for DITA topics with conref in title.

    Generates a variables topic with reusable ph elements and target topics
    whose <title> uses conref to reference those variables. For AEM Guides QA,
    conref resolution testing, and LLM training.
    """
    type: Literal["dita_conref_title_dataset_recipe"] = "dita_conref_title_dataset_recipe"
    topic_count: int = Field(default=10, ge=1, le=50, description="Number of target topics")
    id_prefix: str = Field(default="t", description="Unique ID prefix for generated elements")
    pretty_print: bool = True

class DitaConrefKeyrefDatasetRecipe(BaseModel):
    """
    Recipe for DITA conref and keyref combinations.

    Generates keydef-map, variables.dita, and topics with conref only,
    keyref only, conref+keyref, and nested variants. For AEM Guides QA,
    conref/keyref resolution testing.
    """
    type: Literal["dita_conref_keyref_dataset_recipe"] = "dita_conref_keyref_dataset_recipe"
    topic_count: int = Field(default=15, ge=1, le=50, description="Number of target topics")
    id_prefix: str = Field(default="t", description="Unique ID prefix for generated elements")
    pretty_print: bool = True

class DitaSubjectSchemeDatasetRecipe(BaseModel):
    """
    Recipe for DITA subject scheme validation.

    Generates subject-scheme map with audience-values and topics with valid
    vs invalid audience attributes. For AEM Guides QA, subject scheme testing.
    """
    type: Literal["dita_subject_scheme_dataset_recipe"] = "dita_subject_scheme_dataset_recipe"
    valid_count: int = Field(default=10, ge=1, le=50, description="Number of valid topics")
    invalid_count: int = Field(default=10, ge=1, le=50, description="Number of invalid topics")
    id_prefix: str = Field(default="t", description="Unique ID prefix for generated elements")
    pretty_print: bool = True

class DitaGlossaryAbbrevDatasetRecipe(BaseModel):
    """
    Recipe for DITA glossary with term and abbreviated-form.

    Generates glossary entries with glossterm, glossdef, glossAlt/glossAbbreviation
    and usage topics with term/abbreviated-form keyrefs. For AEM Guides QA.
    """
    type: Literal["dita_glossary_abbrev_dataset_recipe"] = "dita_glossary_abbrev_dataset_recipe"
    entry_count: int = Field(default=15, ge=1, le=50, description="Number of glossary entries")
    usage_topic_count: int = Field(default=10, ge=1, le=50, description="Number of usage topics")
    id_prefix: str = Field(default="t", description="Unique ID prefix for generated elements")
    pretty_print: bool = True

class ConditionalContentRecipe(BaseModel):
    """
    Recipe for generating conditional processing content.
    
    Generates topics with conditional processing attributes:
    - Topics with audience, platform, and product attributes
    - DITAVAL files for conditional filtering
    - Multiple DITAVAL profiles for different output scenarios
    
    Output includes:
    - DITA topic files with conditional attributes
    - DITAVAL files for filtering
    - Optional DITA map file
    """
    type: Literal["conditional_content"] = "conditional_content"
    topic_count: int = Field(default=50, ge=10, le=5000)
    audiences: List[str] = Field(
        default=["admin", "user", "developer"],
        description="Audience values"
    )
    platforms: List[str] = Field(
        default=["windows", "mac", "linux"],
        description="Platform values"
    )
    products: List[str] = Field(
        default=["product-a", "product-b"],
        description="Product values"
    )
    generate_ditaval: bool = True
    ditaval_profiles: List[str] = Field(
        default=["admin-windows", "user-all"],
        description="DITAVAL profile names to generate"
    )
    include_map: bool = True
    pretty_print: bool = True

class TaskTopicsRecipe(BaseModel):
    """
    Recipe for generating Task topics.
    
    Generates DITA task topics with procedural steps:
    - Task topics with step-by-step instructions
    - Prerequisites and results sections
    - Optional substeps and examples
    
    Output includes:
    - DITA task topic files (.dita)
    - Optional DITA map file (.ditamap)
    """
    type: Literal["task_topics"] = "task_topics"
    topic_count: int = Field(default=50, ge=10, le=5000)
    steps_per_task: int = Field(default=5, ge=1, le=20)
    include_prereq: bool = True
    include_result: bool = True
    include_choicetable: bool = False
    include_map: bool = True
    pretty_print: bool = True

class ConceptTopicsRecipe(BaseModel):
    """
    Recipe for generating Concept topics.
    
    Generates DITA concept topics explaining ideas and concepts:
    - Concept topics with multiple sections
    - Explanatory content structure
    
    Output includes:
    - DITA concept topic files (.dita)
    - Optional DITA map file (.ditamap)
    """
    type: Literal["concept_topics"] = "concept_topics"
    topic_count: int = Field(default=50, ge=10, le=5000)
    sections_per_concept: int = Field(default=3, ge=1, le=10)
    include_map: bool = True
    pretty_print: bool = True

class ReferenceTopicsRecipe(BaseModel):
    """
    Recipe for generating Reference topics.
    
    Generates DITA reference topics with structured data:
    - Reference topics with property tables
    - Syntax references
    - Structured reference information
    
    Output includes:
    - DITA reference topic files (.dita)
    - Optional DITA map file (.ditamap)
    """
    type: Literal["reference_topics"] = "reference_topics"
    topic_count: int = Field(default=50, ge=10, le=5000)
    properties_per_ref: int = Field(default=5, ge=1, le=20)
    include_choicetable: bool = False
    include_map: bool = True
    pretty_print: bool = True


class PropertiesTableReferenceRecipe(BaseModel):
    """
    Recipe for DITA reference topics focused on <properties> tables.

    Each topic includes a refbody properties table using proptype, propvalue, and propdesc,
    optionally with prophead (column headers). Suited for AEM Guides / API-style reference QA.
    """
    type: Literal["properties_table_reference"] = "properties_table_reference"
    topic_count: int = Field(default=30, ge=5, le=5000)
    rows_per_table: int = Field(default=8, ge=3, le=25, description="Property rows per topic")
    include_prophead: bool = Field(default=True, description="Include prophead with Type/Value/Description headers")
    include_map: bool = True
    pretty_print: bool = True


class SyntaxDiagramReferenceRecipe(BaseModel):
    """
    Recipe for DITA reference topics with <syntaxdiagram> under <refsyn>.

    Emits groupseq / groupchoice patterns with kwd, delim, oper, sep, and repsep for tech comm syntax QA.
    """

    type: Literal["syntax_diagram_reference"] = "syntax_diagram_reference"
    topic_count: int = Field(default=30, ge=5, le=5000)
    include_map: bool = True
    pretty_print: bool = True


class GlossaryPackRecipe(BaseModel):
    """
    Recipe for generating Glossary entries.
    
    Generates glossary entries with definitions:
    - Glossary topic files with term definitions
    - Optional acronyms
    - Structured glossary content
    
    Output includes:
    - DITA glossary entry files (.dita)
    - Optional DITA map file (.ditamap)
    """
    type: Literal["glossary_pack"] = "glossary_pack"
    entry_count: int = Field(default=100, ge=10, le=10000)
    include_acronyms: bool = True
    include_map: bool = True
    pretty_print: bool = True

class ChoicetableTaskTopicsRecipe(BaseModel):
    """
    Recipe for generating Task topics with choicetables.

    Every topic includes a choicetable with realistic AEM Guides
    and DITA options (output presets, reuse strategies, conditional
    attributes, map elements, review actions, baselines, translation).

    Output includes:
    - DITA task topic files with choicetables (.dita)
    - Optional DITA map file (.ditamap)
    """
    type: Literal["choicetable_tasks"] = "choicetable_tasks"
    topic_count: int = Field(default=50, ge=10, le=5000)
    steps_per_task: int = Field(default=5, ge=1, le=20)
    choices_per_topic: int = Field(default=4, ge=2, le=10)
    include_map: bool = True
    pretty_print: bool = True

class ChoicetableReferenceTopicsRecipe(BaseModel):
    """
    Recipe for generating Reference topics with option tables (simpletable).

    Every topic includes a simpletable listing DITA-OT parameters,
    XML attribute types, AEM Guides API endpoints, Native PDF CSS
    properties, or chunk attribute values. Uses <simpletable> instead
    of <choicetable> because choicetable is only valid inside <step>
    in task.dtd and does not exist in reference.dtd.

    Output includes:
    - DITA reference topic files with simpletables (.dita)
    - Optional DITA map file (.ditamap)
    """
    type: Literal["choicetable_references"] = "choicetable_references"
    topic_count: int = Field(default=50, ge=10, le=5000)
    choices_per_topic: int = Field(default=5, ge=2, le=10)
    include_map: bool = True
    pretty_print: bool = True

class BookmapStructureRecipe(BaseModel):
    """
    Recipe for generating Bookmap structures.

    Generates bookmap with chapters and structure:
    - Bookmap file with chapter organization
    - Chapter topics with multiple topics per chapter
    - Optional frontmatter (notices, preface)
    - Optional backmatter (appendix, index)
    
    Output includes:
    - Chapter topic files (.dita)
    - Frontmatter and backmatter topics (.dita)
    - Bookmap file (.ditamap)
    """
    type: Literal["bookmap_structure"] = "bookmap_structure"
    chapter_count: int = Field(default=10, ge=1, le=100)
    topics_per_chapter: int = Field(default=5, ge=1, le=50)
    include_frontmatter: bool = True
    include_backmatter: bool = True
    pretty_print: bool = True

class MediaRichContentRecipe(BaseModel):
    """
    Recipe for generating media-rich content.
    
    Generates topics with embedded images and media:
    - Topics with image references
    - Optional generated placeholder images
    - Media metadata
    
    Output includes:
    - DITA topic files with image references (.dita)
    - Optional image files (if generate_images is enabled)
    - Optional DITA map file (.ditamap)
    """
    type: Literal["media_rich_content"] = "media_rich_content"
    topic_count: int = Field(default=50, ge=10, le=5000)
    images_per_topic: int = Field(default=3, ge=0, le=20)
    generate_images: bool = True
    image_width: int = Field(default=800, ge=100, le=4000)
    image_height: int = Field(default=600, ge=100, le=4000)
    include_map: bool = True
    pretty_print: bool = True

class WorkflowEnabledContentRecipe(BaseModel):
    """
    Recipe for generating workflow-enabled content.
    
    Generates DITA content from a base recipe and adds workflow metadata including:
    - Review workflows with reviewer assignments, comments, and approval status
    - Translation workflows with language pairs and progress tracking
    - Approval workflows with multi-level approval chains
    
    Output includes:
    - Base DITA topics and maps from the selected base recipe
    - workflow-states.json metadata file with all workflow information
    """
    type: Literal["workflow_enabled_content"] = "workflow_enabled_content"
    base_recipe: dict = Field(description="Base recipe to add workflows to (e.g., task_topics, concept_topics)")
    include_review: bool = Field(default=True, description="Include review workflow metadata")
    include_translation: bool = Field(default=True, description="Include translation workflow metadata")
    include_approval: bool = Field(default=True, description="Include approval workflow metadata")
    reviewers: List[str] = Field(default=["reviewer1", "reviewer2"], description="List of reviewer user IDs")
    target_languages: List[str] = Field(default=["es", "fr"], description="Target languages for translation workflows")

class OutputOptimizedRecipe(BaseModel):
    """
    Recipe for generating output-optimized content.
    
    Optimizes base content for specific output formats:
    - AEM Site: Navigation and breadcrumb metadata
    - PDF: Page breaks and TOC metadata
    - HTML5: Responsive design and accessibility attributes
    - Mobile: Mobile-optimized images and simplified structure
    
    Output includes:
    - Optimized DITA topic files from base_recipe
    - Output format metadata JSON file
    """
    type: Literal["output_optimized"] = "output_optimized"
    base_recipe: dict = Field(description="Base recipe to optimize")
    output_format: Literal["aemsite", "pdf", "html5", "mobile"] = "aemsite"
    optimization_options: dict = Field(default_factory=dict)

class LargeScaleRecipe(BaseModel):
    """
    Recipe for large-scale dataset generation (100k+ topics).
    
    Generates a large number of topics for performance testing:
    - 100,000+ topic files
    - Batch processing for efficiency
    - Minimal formatting for speed
    
    Output includes:
    - Large number of DITA topic files (.dita)
    - No map files (too large for practical use)
    """
    type: Literal["large_scale"] = "large_scale"
    topic_count: int = Field(default=100000, ge=1000, le=1000000)
    batch_size: int = Field(default=1000, ge=100, le=10000)
    include_map: bool = False
    pretty_print: bool = False

class DeepHierarchyRecipe(BaseModel):
    """
    Recipe for deep hierarchy testing (10+ levels).
    
    Generates deeply nested topic hierarchies:
    - Topics organized in 10+ levels of nesting
    - Parent-child relationships
    - Tests hierarchy traversal performance
    
    Output includes:
    - DITA topic files in deep hierarchy (.dita)
    - DITA map files reflecting hierarchy (.ditamap)
    """
    type: Literal["deep_hierarchy"] = "deep_hierarchy"
    depth: int = Field(default=10, ge=1, le=20)
    children_per_level: int = Field(default=5, ge=2, le=100)
    include_maps: bool = True
    pretty_print: bool = True

class WideBranchingRecipe(BaseModel):
    """
    Recipe for wide branching testing (1000+ children).
    
    Generates topics with many children per parent:
    - Root topics with 1000+ child topics
    - Wide branching structure
    - Tests handling of many siblings
    
    Output includes:
    - DITA topic files with wide branching (.dita)
    - DITA map files with many topicrefs per parent (.ditamap)
    """
    type: Literal["wide_branching"] = "wide_branching"
    root_topics: int = Field(default=10, ge=1, le=100)
    children_per_root: int = Field(default=1000, ge=10, le=10000)
    include_maps: bool = True
    pretty_print: bool = True

class AdvancedRelationshipRecipe(BaseModel):
    """
    Recipe for advanced relationship patterns.
    
    Generates complex relationship patterns:
    - Hierarchical relationships
    - Cross-map relationships
    - Conditional relationships
    
    Output includes:
    - DITA topic files with advanced relationships (.dita)
    - DITA map files with relationship tables (.ditamap)
    """
    type: Literal["advanced_relationships"] = "advanced_relationships"
    topic_count: int = Field(default=200, ge=50, le=10000)
    relationship_patterns: List[str] = Field(
        default=["hierarchical", "cross-map", "conditional"],
        description="List of relationship patterns to generate"
    )
    include_map: bool = True
    pretty_print: bool = True

class HubSpokeInboundRecipe(BaseModel):
    """
    Legacy recipe type - Hub-Spoke Inbound pattern.
    
    Generates hub-spoke content pattern:
    - One central hub topic
    - Multiple spoke topics that reference the hub
    - Tests inbound reference patterns
    
    Output includes:
    - Hub topic file (.dita)
    - Spoke topic files with xrefs to hub (.dita)
    - Optional DITA map file (.ditamap)
    """
    type: Literal["hub_spoke_inbound"] = "hub_spoke_inbound"
    topic_count: int = Field(default=100, ge=10, le=5000)
    include_map: bool = True
    pretty_print: bool = True

class KeydefHeavyRecipe(BaseModel):
    """
    Legacy recipe type - Keydef Heavy pattern.
    
    Generates maps with many key definitions:
    - Topics with key definitions
    - Maps with many keydefs
    - Topicrefs using keyrefs
    
    Output includes:
    - DITA topic files (.dita)
    - DITA map files with many keydefs (.ditamap)
    """
    type: Literal["keydef_heavy"] = "keydef_heavy"
    topic_count: int = Field(default=100, ge=10, le=5000)
    keydef_count: int = Field(default=50, ge=0, le=1000)
    include_map: bool = True
    pretty_print: bool = True

class KeyscopeDemoRecipe(BaseModel):
    """
    Recipe for generating keyscope demo dataset demonstrating scoped key resolution.
    
    Generates maps and topics demonstrating scoped key resolution:
    - Maps with keyscopes
    - Topics with scoped key references
    - Examples of qualified keyrefs (s1.prod, s2.prod)
    
    Output includes:
    - DITA topic files with keyrefs (.dita)
    - DITA map files with keyscopes and keydefs (.ditamap)
    """
    type: Literal["keyscope_demo"] = "keyscope_demo"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs (must start with letter/underscore)")
    include_qualified_keyrefs: bool = Field(default=True, description="Include explicit qualified keyrefs (s1.prod, s2.prod) for diagnostics")
    pretty_print: bool = True
    
    @field_validator('id_prefix')
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == '_'):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v

class KeywordMetadataRecipe(BaseModel):
    """
    Recipe for generating keyword metadata key map dataset.
    
    Generates topics with keyword metadata keys:
    - Metadata map defining keyword and category keys
    - Consumer topics using keyrefs to reference metadata
    - Examples of reusable metadata across topics
    
    Output includes:
    - Metadata map file with key definitions (.ditamap)
    - Keyword/metadata topic files (.dita)
    - Consumer topics with keyrefs (.dita)
    """
    type: Literal["keyword_metadata"] = "keyword_metadata"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs (must start with letter/underscore)")
    num_keywords: int = Field(default=10, ge=1, le=50, description="Number of keyword metadata keys to generate")
    num_categories: int = Field(default=5, ge=1, le=20, description="Number of category metadata keys to generate")
    num_topics: int = Field(default=8, ge=1, le=30, description="Number of consumer topics to generate")
    pretty_print: bool = True
    
    @field_validator('id_prefix')
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == '_'):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v

class InsuranceIncrementalRecipe(BaseModel):
    """
    Recipe for generating Insurance Incremental Maps dataset.
    
    Generates insurance domain DITA content with:
    - Large pool of insurance topics (10k+)
    - Multiple maps with incremental topicref counts (10, 100, 1k, 5k, 10k)
    - Insurance-specific content: policies, claims, underwriting, compliance
    - Rotating themes: Term Life, Health, Motor, Endorsements, Surveyor Notes
    - DTD-safe IDs (start with letter)
    
    Output includes:
    - Insurance topic files (.dita) with domain-specific content
    - Multiple map files with incremental topicref counts (.ditamap)
    - Optional DTD stub files (technicalContent/dtd/)
    """
    type: Literal["insurance_incremental"] = "insurance_incremental"
    max_topics: int = Field(default=10000, ge=10, le=50000, description="Maximum number of topics to generate")
    map_sizes: List[int] = Field(default=[10, 100, 1000, 5000, 10000], description="List of topicref counts for each map")
    include_local_dtd_stubs: bool = Field(default=True, description="Generate DTD stub files in technicalContent/dtd/")
    output_root_folder_name: str = Field(default="aem_guides_insurance_incremental", description="Root folder name for output")
    
    @field_validator('map_sizes')
    @classmethod
    def validate_map_sizes(cls, v):
        if not v:
            raise ValueError("map_sizes cannot be empty")
        if not all(isinstance(x, int) and x > 0 for x in v):
            raise ValueError("map_sizes must contain positive integers")
        # Dedupe and sort (UI can briefly send duplicates after edits; order no longer needs to match input)
        return sorted(set(v))
    
    @model_validator(mode='after')
    def validate_max_topics(self):
        if max(self.map_sizes) > self.max_topics:
            raise ValueError(f"max(map_sizes) ({max(self.map_sizes)}) must be <= max_topics ({self.max_topics})")
        return self

class KeyrefNestedKeydefChainRecipe(BaseModel):
    """
    Recipe for nested keydef chain resolution (Map A -> Map B -> Topic C).

    Reproduces AEM Guides Web Editor bug: nested keys not resolved when Map A is context,
    but resolve when Map B is opened as root. DITA-OT publishes correctly.
    Minimal repro for recursive keydef loading across map -> map -> topic keyword sources.
    """
    type: Literal["keyref_nested_keydef_chain_map_to_map_to_topic"] = "keyref_nested_keydef_chain_map_to_map_to_topic"
    root_map_name: str = Field(default="map_a.ditamap", description="Outer context map filename")
    intermediate_map_name: str = Field(default="map_b.ditamap", description="Intermediate keymap filename")
    keyword_topic_name: str = Field(default="topic_c_keywords.dita", description="Keyword source topic filename")
    consumer_topic_name: str = Field(default="topic_d_consumer.dita", description="Consumer topic filename")
    root_map_title: str = Field(default="Outer Context Map", description="Map A title")
    intermediate_map_title: str = Field(default="Static Key Map", description="Map B title")
    keyword_topic_title: str = Field(default="Keyword Source Topic", description="Topic C title")
    consumer_topic_title: str = Field(default="Consumer Topic", description="Topic D title")
    root_to_intermediate_key: str = Field(default="staticKeyMap", description="Key in Map A pointing to Map B")
    direct_intermediate_key_name: str = Field(default="productName", description="Direct key in Map B (topicmeta)")
    nested_keyword_file_key_name: str = Field(default="keywordFile", description="Key in Map B pointing to Topic C")
    nested_keyword_id: str = Field(default="versionString", description="Keyword id in Topic C")
    consumer_keyrefs: List[str] = Field(
        default_factory=lambda: ["productName", "versionString"],
        description="Keyrefs used in Topic D",
    )
    include_direct_key_in_root_map: bool = Field(default=True, description="Add direct key in Map A for comparison")
    include_direct_key_in_intermediate_map: bool = Field(default=True, description="Add direct key in Map B")
    include_nested_keyword_topic: bool = Field(default=True, description="Include Topic C with keywords")
    include_workaround_notes: bool = Field(default=True, description="Add README with workaround notes")
    generation_mode: str = Field(default="minimal_repro", description="minimal_repro | extended_repro")
    add_negative_variant: bool = Field(default=False, description="Add intentionally broken chain variant")
    add_workaround_variant: bool = Field(default=False, description="Add variant with Map B as root")
    id_prefix: str = Field(default="t", description="ID prefix for generated elements")
    pretty_print: bool = True


class ParentChildMapsKeysConrefConkeyrefSelfrefsRecipe(BaseModel):
    """Conservative parent-child maps with keys, conref, conkeyref, and self references."""

    type: Literal["parent_child_maps_keys_conref_conkeyref_selfrefs"] = "parent_child_maps_keys_conref_conkeyref_selfrefs"
    pretty_print: bool = True


class CompactParentChildKeyResolutionRecipe(BaseModel):
    """Compact parent-child key resolution dataset."""

    type: Literal["compact_parent_child_key_resolution"] = "compact_parent_child_key_resolution"
    pretty_print: bool = True


class LargeRootMap1000Topics100kbRecipe(BaseModel):
    """Root map plus 1000 conservative generic topics of approximately 100 KB each."""

    type: Literal["large_root_map_1000_topics_100kb"] = "large_root_map_1000_topics_100kb"
    topic_count: int = Field(default=1000, ge=1, le=5000)
    approx_topic_size_kb: int = Field(default=100, ge=8, le=512)
    pretty_print: bool = False


class HeavyConditionalTopic6000LinesRecipe(BaseModel):
    """
    Recipe for generating a single extremely large condition-heavy DITA topic.

    Generates one 6000+ line topic with heavy audience/platform/otherprops profiling
    for performance, filtering, and rendering stress tests. Builder-first, deterministic.
    Output stats: line_count, section_count, paragraph_count, table_count, codeblock_count,
    note_count, example_count, conditional_attribute_count, generated_files.
    """
    type: Literal["heavy_conditional_topic_6000_lines"] = "heavy_conditional_topic_6000_lines"
    topic_id: str = Field(default="heavy_conditional_topic_001", description="ID for the generated topic")
    title: str = Field(default="Enterprise Conditional Processing Heavy Topic", description="Topic title")
    target_lines: int = Field(default=6000, ge=1000, le=50000, description="Target line count")
    section_count: int = Field(default=120, ge=10, le=500, description="Max sections to generate")
    subsections_per_section: int = Field(default=4, ge=1, le=20, description="Subsections per section")
    paragraphs_per_subsection: int = Field(default=6, ge=1, le=20, description="Paragraphs per subsection")
    include_tables: bool = True
    include_codeblocks: bool = True
    include_notes: bool = True
    include_examples: bool = True
    include_xrefs: bool = False
    include_images: bool = False
    include_ditaval: bool = True
    condition_density: str = Field(default="high", description="high, medium, or none")
    audience_values: List[str] = Field(
        default_factory=lambda: ["beginner", "advanced", "admin", "developer", "author", "reviewer"],
        description="Audience attribute values",
    )
    platform_values: List[str] = Field(
        default_factory=lambda: ["windows", "linux", "mac", "cloud", "web"],
        description="Platform attribute values",
    )
    otherprops_values: List[str] = Field(
        default_factory=lambda: ["cloud", "onprem", "hybrid", "internal", "external", "beta", "prod", "staging"],
        description="Otherprops attribute values",
    )
    tables_per_n_sections: int = Field(default=2, ge=1, le=20, description="Add table every N sections")
    codeblocks_per_n_sections: int = Field(default=2, ge=1, le=20, description="Add codeblock every N sections")
    notes_per_n_sections: int = Field(default=3, ge=1, le=20, description="Add note every N sections")
    examples_per_n_sections: int = Field(default=3, ge=1, le=20, description="Add example every N sections")
    pretty_print: bool = True


# Map structure recipes (topicgroup, topicref, mapref, topichead, reltable, topicset, navref)
class MapsTopicgroupBasicRecipe(BaseModel):
    """Map with topicgroup for grouping topicrefs."""
    type: Literal["maps_topicgroup_basic"] = "maps_topicgroup_basic"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator('id_prefix')
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == '_'):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class MapsTopicgroupNestedRecipe(BaseModel):
    """Nested topicgroup elements for hierarchical grouping."""
    type: Literal["maps_topicgroup_nested"] = "maps_topicgroup_nested"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator('id_prefix')
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == '_'):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class MapsTopicrefBasicRecipe(BaseModel):
    """Map with basic topicrefs."""
    type: Literal["maps_topicref_basic"] = "maps_topicref_basic"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator('id_prefix')
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == '_'):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class MapsNestedTopicrefsRecipe(BaseModel):
    """Map with nested topicref hierarchy."""
    type: Literal["maps_nested_topicrefs"] = "maps_nested_topicrefs"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator('id_prefix')
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == '_'):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class MapsMaprefBasicRecipe(BaseModel):
    """Map with mapref to submap."""
    type: Literal["maps_mapref_basic"] = "maps_mapref_basic"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator('id_prefix')
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == '_'):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class MapsTopicheadBasicRecipe(BaseModel):
    """Map with topichead section headings without href."""
    type: Literal["maps_topichead_basic"] = "maps_topichead_basic"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator('id_prefix')
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == '_'):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class MapsReltableBasicRecipe(BaseModel):
    """Map with reltable for next/prev/related relationships."""
    type: Literal["maps_reltable_basic"] = "maps_reltable_basic"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator('id_prefix')
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == '_'):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class MapsTopicsetBasicRecipe(BaseModel):
    """Map with topicset for navigation grouping (DITA 1.3)."""
    type: Literal["maps_topicset_basic"] = "maps_topicset_basic"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator('id_prefix')
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == '_'):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class MapsNavrefBasicRecipe(BaseModel):
    """Map with navref referencing another map for navigation."""
    type: Literal["maps_navref_basic"] = "maps_navref_basic"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator('id_prefix')
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == '_'):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class TableSemanticsReferenceRecipe(BaseModel):
    """Map + topic with reference table documenting table @align values."""
    type: Literal["table_semantics_reference"] = "table_semantics_reference"
    id_prefix: str = Field(default="tblalign", description="Prefix for generated IDs")
    issue_summary: str = Field(default="", description="Optional text used as topic title when non-empty")

    @field_validator("id_prefix")
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "tblalign"
        if not (v[0].isalpha() or v[0] == "_"):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class InlineFormattingNestedRecipe(BaseModel):
    """Map + topic with nested inline b/i/u for RTE-style reproduction."""
    type: Literal["inline_formatting_nested"] = "inline_formatting_nested"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator("id_prefix")
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == "_"):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


def _validate_id_prefix_t(v: str) -> str:
    if not v:
        return "t"
    if not (v[0].isalpha() or v[0] == "_"):
        raise ValueError("id_prefix must start with a letter or underscore")
    return v


class NestedTopicInlineRecipe(BaseModel):
    """Map + topic with nested b/i/u and a nested child topic (empty title)."""

    type: Literal["nested_topic_inline"] = "nested_topic_inline"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator("id_prefix")
    @classmethod
    def validate_id_prefix(cls, v):
        return _validate_id_prefix_t(v)


class TopicPhKeywordRelatedLinksRecipe(BaseModel):
    """Map + two topics: prolog keywords, ph/keyword in body, related-links."""

    type: Literal["topic_ph_keyword_related_links"] = "topic_ph_keyword_related_links"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator("id_prefix")
    @classmethod
    def validate_id_prefix(cls, v):
        return _validate_id_prefix_t(v)


class TopicSvgMathmlForeignRecipe(BaseModel):
    """Map + topics + SVG file: image href, foreign SVG/MathML, related-links."""

    type: Literal["topic_svg_mathml_foreign"] = "topic_svg_mathml_foreign"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator("id_prefix")
    @classmethod
    def validate_id_prefix(cls, v):
        return _validate_id_prefix_t(v)


class BookmapElementsReferenceRecipe(BaseModel):
    """Bookmap shell (bookmeta, frontmatter, chapter, backmatter) + topic targets."""

    type: Literal["bookmap_elements_reference"] = "bookmap_elements_reference"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator("id_prefix")
    @classmethod
    def validate_id_prefix(cls, v):
        return _validate_id_prefix_t(v)


class SelfConrefendRangeRecipe(BaseModel):
    """Same-file conref + conrefend range in one topic."""
    type: Literal["self_conrefend_range"] = "self_conrefend_range"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator("id_prefix")
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == "_"):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class SelfXrefConrefPositiveRecipe(BaseModel):
    """Minimal same-file xref and conref in one topic (positive)."""
    type: Literal["self_xref_conref_positive"] = "self_xref_conref_positive"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")
    pretty_print: bool = True

    @field_validator("id_prefix")
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == "_"):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class ValidationDuplicateIdNegativeRecipe(BaseModel):
    """Intentionally invalid DITA: duplicate xml:id (validator negative test)."""
    type: Literal["validation_duplicate_id_negative"] = "validation_duplicate_id_negative"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")

    @field_validator("id_prefix")
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == "_"):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class ValidationInvalidChildNegativeRecipe(BaseModel):
    """Intentionally invalid DITA: invalid element nesting."""
    type: Literal["validation_invalid_child_negative"] = "validation_invalid_child_negative"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")

    @field_validator("id_prefix")
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == "_"):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


class ValidationMissingBodyNegativeRecipe(BaseModel):
    """Intentionally invalid DITA: topic without required body."""
    type: Literal["validation_missing_body_negative"] = "validation_missing_body_negative"
    id_prefix: str = Field(default="t", description="Prefix for generated IDs")

    @field_validator("id_prefix")
    @classmethod
    def validate_id_prefix(cls, v):
        if not v:
            return "t"
        if not (v[0].isalpha() or v[0] == "_"):
            raise ValueError("id_prefix must start with a letter or underscore")
        return v


# Configure Recipe as a discriminated union using the 'type' field
Recipe = Annotated[
    Union[
        IncrementalTopicrefMapsRecipe,
        HeavyTopicsTablesCodeblocksRecipe,
        CustomerReusePackRecipe,
        MapParseStressRecipe,
        BulkDitaMapTopicsRecipe,
        RelationshipTableRecipe,
        LocalizedContentRecipe,
        ConrefPackRecipe,
        ConrefendCyclicDuplicateIdRecipe,
        MapCyclicRecipe,
        DitaConrefTitleDatasetRecipe,
        DitaConrefKeyrefDatasetRecipe,
        DitaSubjectSchemeDatasetRecipe,
        DitaGlossaryAbbrevDatasetRecipe,
        ConditionalContentRecipe,
        TaskTopicsRecipe,
        ConceptTopicsRecipe,
        ReferenceTopicsRecipe,
        PropertiesTableReferenceRecipe,
        SyntaxDiagramReferenceRecipe,
        GlossaryPackRecipe,
        BookmapStructureRecipe,
        MediaRichContentRecipe,
        WorkflowEnabledContentRecipe,
        OutputOptimizedRecipe,
        LargeScaleRecipe,
        DeepHierarchyRecipe,
        WideBranchingRecipe,
        AdvancedRelationshipRecipe,
        HubSpokeInboundRecipe,
        KeydefHeavyRecipe,
        KeyscopeDemoRecipe,
        KeywordMetadataRecipe,
        InsuranceIncrementalRecipe,
        HeavyConditionalTopic6000LinesRecipe,
        KeyrefNestedKeydefChainRecipe,
        ParentChildMapsKeysConrefConkeyrefSelfrefsRecipe,
        CompactParentChildKeyResolutionRecipe,
        LargeRootMap1000Topics100kbRecipe,
        MapsTopicgroupBasicRecipe,
        MapsTopicgroupNestedRecipe,
        MapsTopicrefBasicRecipe,
        MapsNestedTopicrefsRecipe,
        MapsMaprefBasicRecipe,
        MapsTopicheadBasicRecipe,
        MapsReltableBasicRecipe,
        MapsTopicsetBasicRecipe,
        MapsNavrefBasicRecipe,
        TableSemanticsReferenceRecipe,
        InlineFormattingNestedRecipe,
        NestedTopicInlineRecipe,
        TopicPhKeywordRelatedLinksRecipe,
        TopicSvgMathmlForeignRecipe,
        BookmapElementsReferenceRecipe,
        SelfConrefendRangeRecipe,
        SelfXrefConrefPositiveRecipe,
        ValidationDuplicateIdNegativeRecipe,
        ValidationInvalidChildNegativeRecipe,
        ValidationMissingBodyNegativeRecipe,
        ChoicetableTaskTopicsRecipe,
        ChoicetableReferenceTopicsRecipe,
    ],
    Discriminator('type')
]

class DatasetConfig(BaseModel):
    """Dataset generation configuration."""
    name: str
    seed: str = "default"
    root_folder: str = "/content/dam/dataset-studio"
    windows_safe_filenames: bool = True
    doctype_topic: str = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">'
    doctype_task: str = '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">'
    doctype_reference: str = (
        '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "technicalContent/dtd/reference.dtd">'
    )
    doctype_map: str = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">'
    doctype_bookmap: str = (
        '<!DOCTYPE bookmap PUBLIC "-//OASIS//DTD DITA BookMap//EN" "technicalContent/dtd/bookmap.dtd">'
    )
    doctype_glossentry: str = '<!DOCTYPE glossentry PUBLIC "-//OASIS//DTD DITA Glossentry//EN" "technicalContent/dtd/glossentry.dtd">'
    recipes: List[Recipe] = Field(default_factory=list)
    use_ai_content: bool = False
    ai_domain: Optional[str] = None
    ai_content_style: str = "professional"

class JobCreateRequest(BaseModel):
    """Request to create a dataset generation job."""
    config: DatasetConfig

class JobResponse(BaseModel):
    """Response from job creation."""
    id: str
    status: str
    created_at: datetime
    config: DatasetConfig
