"""maps.topichead_basic honours ``topic_count`` end to end: generator, recipe spec and executor sanitising."""
from __future__ import annotations

import pytest

from app.generator.maps import generate_maps_topichead_basic
from app.jobs.schemas import DatasetConfig
from app.services import ai_executor_service


def _config() -> DatasetConfig:
    return DatasetConfig(name="t", seed="s", root_folder="/c", windows_safe_filenames=True, recipes=[])


def _counts(files: dict[str, bytes]) -> tuple[int, int, int]:
    ditamap = next(v for k, v in files.items() if k.endswith(".ditamap")).decode("utf-8")
    topics = sum(1 for k in files if k.endswith(".dita"))
    return topics, ditamap.count("<topichead"), ditamap.count("<topicref")


def test_default_is_three_topics_under_two_topicheads():
    assert _counts(generate_maps_topichead_basic(_config(), "out")) == (3, 2, 3)


@pytest.mark.parametrize("count, expected_topicheads", [(1, 1), (2, 2), (3, 2), (5, 2)])
def test_topic_count_controls_topics_and_every_topic_is_referenced(count, expected_topicheads):
    files = generate_maps_topichead_basic(_config(), "out", topic_count=count)
    topics, topicheads, topicrefs = _counts(files)
    assert (topics, topicrefs) == (count, count)
    assert topicheads == expected_topicheads, "a second topichead appears only when it has topics"
    ditamap = next(v for k, v in files.items() if k.endswith(".ditamap")).decode("utf-8")
    for key in files:
        if key.endswith(".dita"):
            assert key.rsplit("/", 1)[1] in ditamap, f"{key} is generated but not referenced from the map"


def test_topic_count_below_one_still_yields_one_topic():
    assert _counts(generate_maps_topichead_basic(_config(), "out", topic_count=0))[0] == 1


def test_recipe_spec_declares_topic_count_so_the_executor_forwards_it():
    spec = {s.id: s for s in ai_executor_service.discover_recipe_specs()}["maps.topichead_basic"]
    assert spec.params_schema.get("topic_count") == "int"
    assert spec.default_params.get("topic_count") == 3
    sanitized = ai_executor_service.sanitize_params_for_recipe(spec, {"topic_count": 2, "id_prefix": "t"})
    assert sanitized["topic_count"] == 2
