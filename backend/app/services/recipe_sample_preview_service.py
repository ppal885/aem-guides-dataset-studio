"""Run generators with minimal params to produce accurate Builder catalog samples."""

from __future__ import annotations

import importlib
import inspect
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.logging_config import get_logger
from app.generator.recipe_manifest import RecipeSpec, discover_recipe_specs
from app.jobs.schemas import DatasetConfig
from app.services.ai_executor_service import sanitize_params_for_recipe

logger = get_logger(__name__)

SKIP_SAMPLE_RECIPE_IDS = frozenset(
    {
        "llm_generated_dita",
    }
)

SAMPLE_PARAM_OVERRIDES: dict[str, Any] = {
    "topic_count": 1,
    "map_count": 1,
    "pool_size": 2,
    "map_topicref_counts": [1, 2],
    "map_topicref_count": 1,
    "topicrefs_per_map": 2,
    "shared_topics": 2,
    "remove_map_count": 1,
    "topic_references_per_map": 2,
    "key_definitions": 2,
    "key_groups": 1,
    "external_references": 1,
    "tables_per_topic": 1,
    "codeblocks_per_topic": 1,
    "table_rows": 2,
    "table_cols": 2,
    "code_lines_per_codeblock": 3,
    "fetch_live": False,
    "batch_size": 2,
    "map_sample_size": 2,
    "root_topics": 1,
    "children_per_root": 1,
    "depth": 2,
    "children_per_level": 1,
    "max_topics": 2,
    "include_map": True,
    "pretty_print": True,
}

MAX_SAMPLE_FILES = 3
MAX_SAMPLE_CHARS = 14_000


@dataclass(frozen=True)
class RecipeSamplePreview:
    xml: str
    summary: str
    file_count: int


def _specs_by_id() -> dict[str, RecipeSpec]:
    return {spec.id: spec for spec in discover_recipe_specs() if isinstance(spec, RecipeSpec)}


def _apply_sample_overrides(spec: RecipeSpec, params: dict[str, Any]) -> dict[str, Any]:
    out = dict(params)
    schema = spec.params_schema or {}
    for key, override in SAMPLE_PARAM_OVERRIDES.items():
        if key not in out and key not in (spec.default_params or {}):
            continue
        current = out.get(key)
        type_str = str(schema.get(key, "str")).lower()
        if isinstance(override, bool) and type_str == "bool":
            out[key] = override
        elif isinstance(override, int) and isinstance(current, int):
            out[key] = min(current, override)
        elif isinstance(override, list) and isinstance(current, list):
            if key == "map_topicref_counts":
                out[key] = [min(v, 2) for v in current[:2]] or [1, 2]
            else:
                out[key] = current[:2]
    return out


def _accepted_params(fn, params: dict[str, Any]) -> dict[str, Any]:
    sig = inspect.signature(fn)
    skip = {"config", "self", "base_path", "base", "stream_callback"}
    accepted = {
        name
        for name, param in sig.parameters.items()
        if name not in skip and param.kind != inspect.Parameter.VAR_KEYWORD
    }
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()):
        return params
    return {key: value for key, value in params.items() if key in accepted}


def _sort_sample_paths(paths: list[str], spec_id: str = "") -> list[str]:
    prefer_maps = "map" in spec_id.lower()

    def rank(path: str) -> tuple[int, str]:
        lower = path.lower()
        if prefer_maps and (lower.endswith(".bookmap") or lower.endswith(".ditamap")):
            return (-1, lower)
        if lower.endswith(".dita"):
            return (0, lower)
        if lower.endswith((".ditamap", ".bookmap")):
            return (1, lower)
        if lower.endswith(".json"):
            return (2, lower)
        return (3, lower)

    return sorted(paths, key=rank)


def _format_sample_bundle(files: dict[str, bytes], spec_id: str = "") -> str:
    paths = _sort_sample_paths(list(files.keys()), spec_id)[:MAX_SAMPLE_FILES]
    parts: list[str] = []
    total = 0
    for path in paths:
        text = files[path].decode("utf-8", errors="replace").strip()
        block = f"<!-- File: {path} -->\n{text}"
        if total + len(block) > MAX_SAMPLE_CHARS:
            remaining = MAX_SAMPLE_CHARS - total
            if remaining > 200:
                parts.append(block[:remaining] + "\n<!-- truncated -->")
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def _summarize_sample(spec: RecipeSpec, files: dict[str, bytes]) -> str:
    paths = list(files.keys())
    dita_count = sum(1 for path in paths if path.lower().endswith(".dita"))
    map_count = sum(1 for path in paths if path.lower().endswith((".ditamap", ".bookmap")))
    json_count = sum(1 for path in paths if path.lower().endswith(".json"))
    bits = [f"{len(paths)} file(s)"]
    if dita_count:
        bits.append(f"{dita_count} topic(s)")
    if map_count:
        bits.append(f"{map_count} map(s)")
    if json_count:
        bits.append(f"{json_count} manifest/metadata file(s)")
    joined = ", ".join(bits)
    return f"`{spec.id}` generates {joined}. Sample output below is produced by the real generator with minimal params."


def generate_recipe_sample_preview(spec: RecipeSpec) -> RecipeSamplePreview | None:
    if spec.id in SKIP_SAMPLE_RECIPE_IDS:
        return None
    if not spec.module or not spec.function:
        return None

    try:
        mod = importlib.import_module(spec.module)
        fn = getattr(mod, spec.function, None)
        if not callable(fn):
            return None

        merged = dict(spec.default_params or {})
        params = sanitize_params_for_recipe(spec, merged)
        params = _apply_sample_overrides(spec, params)
        params = _accepted_params(fn, params)

        config = DatasetConfig(
            name="catalog-sample",
            seed="catalog-sample",
            root_folder="bundle",
            windows_safe_filenames=True,
        )
        if "rand" in fn.__code__.co_varnames:
            params["rand"] = random.Random(config.seed)

        result = fn(config, "bundle", **params)
        if not isinstance(result, dict) or not result:
            return None

        xml = _format_sample_bundle(result, spec.id)
        if "<" not in xml:
            return None
        return RecipeSamplePreview(
            xml=xml,
            summary=_summarize_sample(spec, result),
            file_count=len(result),
        )
    except Exception as exc:
        logger.debug("Recipe sample preview failed for %s: %s", spec.id, exc)
        return None


@lru_cache(maxsize=512)
def get_recipe_sample_preview(recipe_id: str) -> tuple[str, str] | None:
    spec = _specs_by_id().get(recipe_id)
    if not spec:
        return None
    if spec.example_output and "<" in spec.example_output:
        summary = f"`{spec.id}` uses a hand-authored representative sample aligned to this recipe."
        return str(spec.example_output).strip(), summary
    preview = generate_recipe_sample_preview(spec)
    if not preview:
        return None
    return preview.xml, preview.summary
