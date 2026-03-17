"""AI executor service - run generator plans and write output."""
import importlib
import inspect
import random
import traceback
from pathlib import Path
from typing import Any, Optional

from app.generator.recipe_manifest import RecipeSpec, discover_recipe_specs
from app.jobs.schemas import DatasetConfig, Recipe
from app.core.schemas_ai import GeneratorInvocationPlan, SelectedRecipe
from app.core.structured_logging import get_structured_logger
from app.utils.fs_guard import safe_join, SecurityError

logger = get_structured_logger(__name__)


def _coerce_value(value: Any, type_str: str, default: Any) -> Any:
    """Coerce value to expected type; return default on failure."""
    if value is None:
        return default
    type_str = (type_str or "str").lower()
    try:
        if type_str == "int":
            return int(value) if value is not None else default
        if type_str == "str":
            return str(value) if value is not None else default
        if type_str == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        if type_str == "float":
            return float(value) if value is not None else default
        if type_str == "list":
            return list(value) if isinstance(value, (list, tuple)) else default
        if type_str == "dict":
            return dict(value) if isinstance(value, dict) else default
    except (ValueError, TypeError):
        pass
    return default


CONTENT_PARAM_PREFIX = "content_"
# Params from Jira evidence that recipes may use (e.g. representative_xml from Representative Sample)
EVIDENCE_PARAM_KEYS = frozenset({"representative_xml", "evidence_pack"})

# Param caps for MIN_REPRO / AI-generated runs to prevent oversized datasets
PARAM_CAPS = {
    "topic_count": 50,
    "map_count": 10,
    "topicrefs_per_map": 20,
    "keydef_count": 30,
    "conref_density": 0.5,
}


def sanitize_params_for_recipe(spec: RecipeSpec, params: dict) -> dict:
    """
    Validate and coerce params against params_schema. Use default_params for missing
    or invalid values. Drop params not in params_schema or default_params.
    Content override params (content_titles, content_steps, etc.) from Jira evidence
    are always passed through when present.
    """
    schema = spec.params_schema or {}
    defaults = dict(spec.default_params or {})
    allowed = set(schema.keys()) | set(defaults.keys()) | {k for k in params.keys() if k.startswith(CONTENT_PARAM_PREFIX)} | EVIDENCE_PARAM_KEYS
    out: dict[str, Any] = {}
    for key in allowed:
        raw = params.get(key) if key in params else defaults.get(key)
        type_str = schema.get(key, "list" if key.startswith(CONTENT_PARAM_PREFIX) else "str")
        default_val = defaults.get(key)
        coerced = _coerce_value(raw, type_str, default_val)
        cap = PARAM_CAPS.get(key)
        if cap is not None and isinstance(coerced, (int, float)):
            coerced = min(coerced, cap)
        out[key] = coerced
    return out


def _build_recipe_from_selected(spec: RecipeSpec, selected: SelectedRecipe) -> dict:
    """Build recipe config dict for run_generate_dataset."""
    params = dict(spec.default_params or {})
    params.update(selected.params or {})
    return {"type": spec.id, **params}


def execute_plan(
    plan: GeneratorInvocationPlan,
    output_dir: str,
    seed: str = "ai-default",
    skip_experience_league_companion: bool = False,
) -> dict:
    """
    Execute generator plan: build DatasetConfig, run generators, write files to output_dir.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    base = str(output_path)
    recipes_executed = []
    warnings = []

    config = DatasetConfig(
        name="ai-generated",
        seed=seed,
        root_folder=base,
        recipes=[],
        doctype_topic='<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
        doctype_map='<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
        windows_safe_filenames=True,
    )

    specs_by_id = {s.id: s for s in discover_recipe_specs() if isinstance(s, RecipeSpec)}

    for selected in plan.recipes:
        spec = specs_by_id.get(selected.recipe_id)
        if not spec:
            warnings.append(f"Unknown recipe_id: {selected.recipe_id}")
            continue

        try:
            mod = importlib.import_module(spec.module)
            fn = getattr(mod, spec.function, None)
            if not fn:
                warnings.append(f"Function not found: {spec.module}.{spec.function}")
                continue

            merged = dict(spec.default_params or {})
            merged.update(selected.params or {})
            params = sanitize_params_for_recipe(spec, merged)
            rand = random.Random(seed)
            if "rand" in fn.__code__.co_varnames:
                params["rand"] = rand
            # Only pass params the generator accepts (avoids representative_xml etc. for recipes that don't use it)
            sig = inspect.signature(fn)
            skip = {"config", "self", "base_path", "base"}
            accepted = {p for p in sig.parameters if p not in skip and sig.parameters[p].kind != inspect.Parameter.VAR_KEYWORD}
            params = {k: v for k, v in params.items() if k in accepted}
            logger.info_structured(
                "Executing recipe",
                extra_fields={"recipe_id": selected.recipe_id, "base": base, "params_keys": list(params.keys())},
            )
            result = fn(config, base, **params)

            if isinstance(result, dict):
                base_resolved = Path(base).resolve()
                for file_path, content in result.items():
                    path_str = str(file_path).replace("\\", "/")
                    fp = Path(path_str)
                    if fp.is_absolute():
                        try:
                            rel = str(fp.resolve().relative_to(base_resolved)).replace("\\", "/")
                        except (ValueError, TypeError):
                            rel = path_str
                            if rel.startswith(str(base_resolved).replace("\\", "/")):
                                rel = rel[len(str(base_resolved).replace("\\", "/")):].lstrip("/")
                    else:
                        rel = path_str
                    try:
                        full = safe_join(output_path, rel)
                        full.parent.mkdir(parents=True, exist_ok=True)
                        full.write_bytes(content)
                    except SecurityError as se:
                        logger.warning_structured(
                            "Path rejected by safe_join",
                            extra_fields={"recipe_id": selected.recipe_id, "file_path": path_str, "rel": rel, "error": str(se)},
                        )
                        warnings.append(f"Recipe {selected.recipe_id}: path rejected: {rel}")
                recipes_executed.append(selected.recipe_id)
                logger.info_structured(
                    "Recipe completed",
                    extra_fields={
                        "recipe_id": selected.recipe_id,
                        "file_count": len(result),
                        "sample_keys": list(result.keys())[:2] if result else [],
                    },
                )
                if not result:
                    warnings.append(f"Recipe {selected.recipe_id} produced no output files")
            else:
                warnings.append(f"Recipe {selected.recipe_id} returned unexpected type: {type(result).__name__}")
        except Exception as e:
            tb_str = traceback.format_exc()
            warnings.append(f"Recipe {selected.recipe_id} failed: {e}")
            logger.warning_structured(
                "Recipe execution failed",
                extra_fields={
                    "recipe_id": selected.recipe_id,
                    "error": str(e),
                    "traceback": tb_str,
                },
            )

    # Companion: include scraped Experience League content when available (skip for generate-from-text)
    if not skip_experience_league_companion and "experience_league_to_dita" not in recipes_executed:
        try:
            from app.storage import get_storage
            from app.generator.experience_league_to_dita import generate_experience_league_to_dita
            storage = get_storage()
            chunks_path = storage.base_path / "aem_guides_doc_chunks.json"
            if chunks_path.exists():
                import json
                chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
                has_structured = any(
                    c.get("paragraphs") or c.get("list_items") or c.get("codeph") or c.get("codeblocks") or c.get("tables")
                    for c in (chunks if isinstance(chunks, list) else [])
                )
                if has_structured:
                    result = generate_experience_league_to_dita(config, base, max_topics=15)
                    if result:
                        for path_str, content in result.items():
                            p = str(path_str).replace("\\", "/")
                            if "experience_league_to_dita/" in p:
                                rel = "experience_league_to_dita/" + p.split("experience_league_to_dita/", 1)[1]
                            else:
                                rel = p
                            try:
                                full = safe_join(output_path, rel)
                                full.parent.mkdir(parents=True, exist_ok=True)
                                full.write_bytes(content)
                            except SecurityError:
                                pass
                        recipes_executed.append("experience_league_to_dita")
                        logger.info_structured(
                            "Companion recipe: experience_league_to_dita",
                            extra_fields={"file_count": len(result)},
                        )
        except Exception as e:
            logger.debug_structured(
                "Companion experience_league_to_dita skipped",
                extra_fields={"error": str(e)},
            )

    return {
        "scenario_dir": base,
        "recipes_executed": recipes_executed,
        "warnings": warnings,
    }
