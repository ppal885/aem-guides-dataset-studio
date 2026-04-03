"""
Regression: POST /api/v1/jobs with Builder-shaped JSON (same as browser / Vite proxy).

Mirrors curl to http://localhost:5173/api/v1/jobs using FastAPI TestClient against /api/v1/jobs.
"""
import pytest
from fastapi.testclient import TestClient

# Matches [frontend/src/pages/Builder.tsx](frontend/src/pages/Builder.tsx) job payload base fields.
BUILDER_LIKE_BASE_CONFIG = {
    "name": "My Dataset",
    "seed": "test-seed",
    "root_folder": "/content/dam/dataset-studio",
    "windows_safe_filenames": True,
    "doctype_topic": '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
    "doctype_map": '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
}

_AUTH_HEADERS = {"Authorization": "Bearer test-token"}

# Lightweight wired recipes only (small output, fast synchronous run_dataset_job).
_REGRESSION_RECIPES = [
    pytest.param(
        {"type": "inline_formatting_nested", "id_prefix": "t", "pretty_print": True},
        id="inline_formatting_nested",
    ),
    pytest.param(
        {"type": "table_semantics_reference", "id_prefix": "tblalign", "issue_summary": ""},
        id="table_semantics_reference",
    ),
    pytest.param(
        {"type": "self_conrefend_range", "id_prefix": "t", "pretty_print": True},
        id="self_conrefend_range",
    ),
    pytest.param(
        {"type": "self_xref_conref_positive", "id_prefix": "t", "pretty_print": True},
        id="self_xref_conref_positive",
    ),
    pytest.param(
        {"type": "validation_duplicate_id_negative", "id_prefix": "t"},
        id="validation_duplicate_id_negative",
    ),
    pytest.param(
        {"type": "nested_topic_inline", "id_prefix": "t", "pretty_print": True},
        id="nested_topic_inline",
    ),
    pytest.param(
        {"type": "topic_ph_keyword_related_links", "id_prefix": "t", "pretty_print": True},
        id="topic_ph_keyword_related_links",
    ),
]


@pytest.mark.parametrize("recipe", _REGRESSION_RECIPES)
def test_post_jobs_create_regression(client: TestClient, recipe: dict) -> None:
    """POST /api/v1/jobs accepts config, runs generation, returns completed job summary."""
    config = {**BUILDER_LIKE_BASE_CONFIG, "recipes": [recipe]}
    response = client.post(
        "/api/v1/jobs",
        json={"config": config},
        headers=_AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "id" in data and data["id"]
    assert data.get("status") == "completed", data


def test_post_jobs_invalid_config_returns_structured_422(client: TestClient) -> None:
    """Invalid recipe type yields 422 with detail + errors[] (not a stringified Python list)."""
    config = {
        **BUILDER_LIKE_BASE_CONFIG,
        "recipes": [{"type": "not_a_registered_recipe_xyz", "pretty_print": True}],
    }
    response = client.post(
        "/api/v1/jobs",
        json={"config": config},
        headers=_AUTH_HEADERS,
    )
    assert response.status_code == 422, response.text
    data = response.json()
    assert data.get("detail") == "Invalid configuration"
    assert "errors" in data and isinstance(data["errors"], list) and len(data["errors"]) >= 1
    first = data["errors"][0]
    assert "field" in first and "message" in first and "type" in first


def test_post_validate_config_ok_and_invalid(client: TestClient) -> None:
    """POST /api/v1/jobs/validate-config mirrors job config validation."""
    ok_config = {
        **BUILDER_LIKE_BASE_CONFIG,
        "recipes": [{"type": "inline_formatting_nested", "id_prefix": "t", "pretty_print": True}],
    }
    ok = client.post(
        "/api/v1/jobs/validate-config",
        json={"config": ok_config},
        headers=_AUTH_HEADERS,
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body.get("valid") is True
    assert "config" in body and body["config"].get("name") == "My Dataset"

    bad = client.post(
        "/api/v1/jobs/validate-config",
        json={"config": {**BUILDER_LIKE_BASE_CONFIG, "recipes": [{"type": "bad_type"}]}},
        headers=_AUTH_HEADERS,
    )
    assert bad.status_code == 422, bad.text
    err = bad.json()
    assert err.get("detail") == "Invalid configuration"
    assert isinstance(err.get("errors"), list) and err["errors"]


def test_insurance_incremental_duplicate_map_sizes_normalizes(client: TestClient) -> None:
    """Duplicate map_sizes no longer cause 422 (deduped server-side)."""
    config = {
        **BUILDER_LIKE_BASE_CONFIG,
        "recipes": [
            {
                "type": "insurance_incremental",
                "max_topics": 10000,
                "map_sizes": [10, 100, 100, 1000, 5000, 10000],
                "include_local_dtd_stubs": True,
                "output_root_folder_name": "aem_guides_insurance_incremental",
            }
        ],
    }
    response = client.post(
        "/api/v1/jobs/validate-config",
        json={"config": config},
        headers=_AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text
    normalized = response.json()["config"]["recipes"][0]["map_sizes"]
    assert normalized == [10, 100, 1000, 5000, 10000]
