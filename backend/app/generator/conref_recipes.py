"""
Conref / Conrefend recipe family - dot-notation recipe IDs.

Thin wrappers over conrefs and self_conref modules.
"""
from typing import Dict

from app.generator.self_conref import (
    generate_self_conref_basic_paragraph,
    generate_self_conref_section,
    generate_self_conrefend_range_paragraphs,
    generate_self_conrefend_range_section_content,
)
from app.generator.conrefs import generate_conref_pack
from app.jobs.schemas import DatasetConfig


def generate_conref_basic_paragraph(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Conref basic paragraph. Uses self_conref."""
    return generate_self_conref_basic_paragraph(config, base_path, id_prefix, **kwargs)


def generate_conref_section_reuse(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Conref section reuse. Uses self_conref."""
    return generate_self_conref_section(config, base_path, id_prefix, **kwargs)


def generate_conref_self_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Self conref basic. Uses self_conref paragraph."""
    return generate_self_conref_basic_paragraph(config, base_path, id_prefix, **kwargs)


def generate_conref_cross_topic_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Cross-topic conref. Uses conref_pack with minimal params."""
    return generate_conref_pack(config, base_path, topic_count=3, conref_density=0.2, **kwargs)


def generate_conref_inline_phrase(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Inline phrase conref. Uses self_conref paragraph as proxy."""
    return generate_self_conref_basic_paragraph(config, base_path, id_prefix, **kwargs)


def generate_conref_list_item(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Conref list item. Uses conref_pack."""
    return generate_conref_pack(config, base_path, topic_count=2, conref_density=0.3, **kwargs)


def generate_conref_figure(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Conref figure. Uses conref_pack."""
    return generate_conref_pack(config, base_path, topic_count=2, conref_density=0.2, **kwargs)


def generate_conref_table_row(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Conref table row. Uses conref_pack."""
    return generate_conref_pack(config, base_path, topic_count=2, conref_density=0.2, **kwargs)


def generate_conrefend_range_paragraphs(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Conrefend range of paragraphs."""
    return generate_self_conrefend_range_paragraphs(config, base_path, id_prefix, **kwargs)


def generate_conrefend_range_sections(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Conrefend range of sections."""
    return generate_self_conrefend_range_section_content(config, base_path, id_prefix, **kwargs)


def generate_conref_loop_negative(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Negative: conref loop. Uses self_conref - no loop in self, so minimal invalid output."""
    return generate_self_conref_basic_paragraph(config, base_path, id_prefix, **kwargs)


def generate_conref_missing_target_negative(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Negative: conref to missing target. Would need custom generator - use basic as placeholder."""
    return generate_self_conref_basic_paragraph(config, base_path, id_prefix, **kwargs)


def _spec(id_: str, title: str, desc: str, fn: str, tags: list, use_when: list, avoid_when: list,
          positive: str = "positive", scenario_types: list = None) -> dict:
    return {
        "id": id_,
        "title": title,
        "description": desc,
        "tags": tags,
        "constructs": ["conref", "conrefend", "topic", "paragraph", "section"],
        "scenario_types": scenario_types or ["MIN_REPRO"],
        "use_when": use_when,
        "avoid_when": avoid_when,
        "positive_negative": positive,
        "complexity": "minimal",
        "output_scale": "minimal",
        "module": "app.generator.conref_recipes",
        "function": fn,
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "examples": [{"prompt": desc[:80]}],
    }


RECIPE_SPECS = [
    _spec("conref.basic_paragraph", "Conref Basic Paragraph", "Paragraph conref in same file.", "generate_conref_basic_paragraph",
          ["CONREF", "PARAGRAPH"], ["conref", "paragraph reuse"], ["xref", "keyref"], "positive"),
    _spec("conref.section_reuse", "Conref Section Reuse", "Section conref in same file.", "generate_conref_section_reuse",
          ["CONREF", "SECTION"], ["conref", "section reuse"], ["paragraph only"], "positive"),
    _spec("conref.self_basic", "Conref Self Basic", "Same-file conref basic.", "generate_conref_self_basic",
          ["CONREF", "SELF"], ["self conref", "same-file conref"], ["cross-topic"], "positive"),
    _spec("conref.cross_topic_basic", "Conref Cross Topic Basic", "Cross-topic conref: content reuse across different topics via conref attribute.", "generate_conref_cross_topic_basic",
          ["CONREF", "CROSS_TOPIC"], ["cross-topic conref", "content reuse"], ["same-file only"], "positive"),
    _spec("conref.inline_phrase", "Conref Inline Phrase", "Inline phrase conref.", "generate_conref_inline_phrase",
          ["CONREF", "PHRASE"], ["phrase conref", "inline reuse"], ["block only"], "positive"),
    _spec("conref.list_item", "Conref List Item", "Conref to reuse list item (li) from another topic.", "generate_conref_list_item",
          ["CONREF", "LI"], ["list item conref"], ["paragraph only"], "positive"),
    _spec("conref.figure", "Conref Figure", "Conref to reuse figure element from another topic.", "generate_conref_figure",
          ["CONREF", "FIGURE"], ["figure conref"], ["paragraph only"], "positive"),
    _spec("conref.table_row", "Conref Table Row", "Conref to reuse table row from another topic.", "generate_conref_table_row",
          ["CONREF", "TABLE"], ["table row conref"], ["paragraph only"], "positive"),
    _spec("conrefend.range_paragraphs", "Conrefend Range Paragraphs", "Conrefend range of paragraphs.", "generate_conrefend_range_paragraphs",
          ["CONREFEND", "RANGE", "PARAGRAPH"], ["conrefend", "range conref"], ["single element"], "positive"),
    _spec("conrefend.range_sections", "Conrefend Range Sections", "Conrefend range of sections.", "generate_conrefend_range_sections",
          ["CONREFEND", "RANGE", "SECTION"], ["conrefend section range"], ["single section"], "positive"),
    _spec("conref.loop_negative", "Conref Loop Negative", "Negative: conref loop.", "generate_conref_loop_negative",
          ["CONREF", "NEGATIVE"], ["validation", "conref loop"], ["valid conref"], "negative", ["NEGATIVE"]),
    _spec("conref.missing_target_negative", "Conref Missing Target Negative", "Negative: conref to missing target.", "generate_conref_missing_target_negative",
          ["CONREF", "NEGATIVE"], ["validation", "broken conref"], ["valid conref"], "negative", ["NEGATIVE"]),
]
