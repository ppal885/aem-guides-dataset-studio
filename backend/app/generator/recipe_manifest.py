"""Recipe manifest - discover RecipeSpecs from generator modules."""
from dataclasses import dataclass, field
from typing import Any, Optional
import importlib
import pkgutil


@dataclass
class RecipeSpec:
    """Specification for a generator recipe."""

    id: str
    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    module: str = ""
    function: str = ""
    params_schema: dict = field(default_factory=dict)
    examples: list[dict] = field(default_factory=list)
    default_params: dict = field(default_factory=dict)
    stability: str = "stable"
    # Richer metadata for LLM planner and retriever
    constructs: list[str] = field(default_factory=list)
    scenario_types: list[str] = field(default_factory=list)
    use_when: list[str] = field(default_factory=list)
    avoid_when: list[str] = field(default_factory=list)
    positive_negative: str = ""
    complexity: str = ""
    aem_guides_features: list[str] = field(default_factory=list)
    output_scale: str = ""  # minimal | medium | large | stress - for LLM to prefer scale-appropriate recipes
    mechanism_family: str = ""  # keyref | xref | conref | ditaval | etc. - for anti-blending validation


def get_mechanism_family(spec: RecipeSpec) -> str:
    """Derive mechanism family from spec. Uses mechanism_family if set, else infers from id."""
    if spec.mechanism_family:
        return spec.mechanism_family
    rid = (spec.id or "").lower()
    if rid.startswith("keys.") or "keydef" in rid or "keyref" in rid or "keyscope" in rid or "nested_keydef" in rid:
        return "keyref"
    if rid.startswith("xref") or "xref_" in rid:
        return "xref"
    if "conref" in rid:
        return "conref"
    if "conditional" in rid or "ditaval" in rid:
        return "ditaval"
    return ""


def _flatten_to_str(val) -> str:
    """Convert value to string, flattening lists."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return " ".join(_flatten_to_str(x) for x in val)
    return str(val)


def recipe_to_retrieval_text(spec: RecipeSpec) -> str:
    """Convert RecipeSpec into rich searchable text for lexical scoring and embeddings."""
    parts = [
        spec.id or "",
        spec.title or "",
        spec.description or "",
        _flatten_to_str(spec.tags),
        _flatten_to_str(spec.constructs),
        _flatten_to_str(spec.scenario_types),
        _flatten_to_str(spec.use_when),
        _flatten_to_str(spec.avoid_when),
        _flatten_to_str(spec.output_scale),
        _flatten_to_str(spec.complexity),
        _flatten_to_str(spec.positive_negative),
    ]
    for ex in spec.examples or []:
        if isinstance(ex, dict) and ex.get("prompt"):
            parts.append(str(ex["prompt"]))
    return " ".join(p for p in parts if p)


def discover_recipe_specs() -> list[RecipeSpec]:
    """Scan app.generator modules for RECIPE_SPECS attribute."""
    specs = []
    import app.generator as pkg
    for importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
        try:
            mod = importlib.import_module(f"app.generator.{modname}")
            recs = getattr(mod, "RECIPE_SPECS", None)
            if recs:
                for r in recs:
                    if isinstance(r, RecipeSpec):
                        specs.append(r)
                    elif isinstance(r, dict):
                        specs.append(RecipeSpec(**{k: v for k, v in r.items() if k in RecipeSpec.__dataclass_fields__}))
        except Exception:
            continue
    return specs
