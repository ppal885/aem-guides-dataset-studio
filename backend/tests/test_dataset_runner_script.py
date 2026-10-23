"""Tests for server-generated Python client scripts (render_jobs_api_python_script).

The former ``POST /api/v1/jobs/render-python-client`` route belonged to the retired web application and is
not exposed any more; the service function is still tested directly."""

import json
import base64
import re

from app.services.dataset_runner_script_service import render_jobs_api_python_script


def test_render_script_roundtrips_config_via_base64():
    cfg = {
        "name": "t",
        "seed": "s",
        "root_folder": "/c",
        "windows_safe_filenames": True,
        "recipes": [{"type": "inline_formatting_nested", "id_prefix": "x", "pretty_print": True}],
    }
    src = render_jobs_api_python_script(config=cfg, api_base_url="http://127.0.0.1:8001")
    m = re.search(r'_CONFIG_B64 = "([A-Za-z0-9+/=]+)"', src)
    assert m, "missing base64 payload"
    decoded = json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
    assert decoded == cfg
    assert "urllib.request" in src
    assert "/api/v1/jobs" in src


_AUTH_HEADERS = {"Authorization": "Bearer test-token"}


def test_render_python_client_route_is_not_exposed(client):
    """Former application routes must return 404; this path also matches ``GET /jobs/{job_id}``, so 405 is accepted."""
    body = {
        "config": {
            "name": "Script export test",
            "seed": "script-export-seed",
            "root_folder": "/content/dam/dataset-studio",
            "windows_safe_filenames": True,
            "recipes": [{"type": "inline_formatting_nested", "id_prefix": "spex", "pretty_print": True}],
        }
    }
    r = client.post("/api/v1/jobs/render-python-client", json=body, headers=_AUTH_HEADERS)
    assert r.status_code in (404, 405), r.text
