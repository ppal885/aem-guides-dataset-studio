"""Natural-language bulk preset commands in chat (no Builder)."""

from app.services.chat_agent_service import detect_agent_command


def test_detect_list_bulk_presets():
    cmd = detect_agent_command("list bulk presets", [])
    assert cmd is not None
    assert cmd["type"] == "bulk_preset_list"


def test_detect_run_bulk_preset():
    cmd = detect_agent_command("run bulk preset my-label", [])
    assert cmd is not None
    assert cmd["type"] == "bulk_preset_run"
    assert cmd["label_or_id"] == "my-label"


def test_detect_save_bulk_preset_with_explicit_job():
    cmd = detect_agent_command("save bulk preset from job job-123 as k8s-pack", [])
    assert cmd is not None
    assert cmd["type"] == "bulk_preset_save"
    assert cmd["job_id"] == "job-123"
    assert cmd["label"] == "k8s-pack"


def test_detect_save_bulk_preset_uses_latest_job_from_history():
    messages = [
        {"role": "assistant", "tool_results": {"create_job": {"job_id": "abc-1"}}},
    ]
    cmd = detect_agent_command("save bulk preset as my-snap", messages)
    assert cmd is not None
    assert cmd["type"] == "bulk_preset_save"
    assert cmd["label"] == "my-snap"
    assert cmd["job_id"] == "abc-1"


def test_show_step_takes_precedence_over_bulk():
    messages = [
        {
            "role": "assistant",
            "tool_results": {
                "_agent_plan": {"steps": []},
            },
        }
    ]
    cmd = detect_agent_command("show step 1", messages)
    assert cmd is not None
    assert cmd["type"] == "show_step"
