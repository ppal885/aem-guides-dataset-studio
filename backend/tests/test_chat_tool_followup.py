from app.services.chat_service import _build_post_tool_assistant_text


def test_generate_dita_followup_uses_in_app_download_action():
    text = _build_post_tool_assistant_text(
        {
            "generate_dita": {
                "jira_id": "TEXT-1234",
                "run_id": "run-5678",
                "download_url": "/api/v1/ai/bundle/TEXT-1234/run-5678/download",
                "scenarios": [{"id": "topic-1"}],
            }
        }
    )

    assert "DITA bundle generated" in text
    assert "Download DITA Bundle action below" in text
    assert "example.com" not in text
    assert "Run ID: `run-5678`" in text


def test_create_job_followup_keeps_download_in_chat():
    text = _build_post_tool_assistant_text(
        {
            "create_job": {
                "job_id": "job-123",
                "recipe_type": "task_topics",
                "status": "pending",
                "status_url": "/api/v1/jobs/job-123",
                "download_url": "/api/v1/datasets/job-123/download",
            }
        }
    )

    assert "Dataset generation started" in text
    assert "Job History" not in text
    assert "in-chat dataset card" in text


def test_search_jira_followup_lists_only_verified_issue_matches():
    text = _build_post_tool_assistant_text(
        {
            "search_jira_issues": {
                "query": "reltables",
                "source": "jira_api",
                "issues": [
                    {
                        "issue_key": "GUIDES-42533",
                        "summary": "Reltable references fail in nested maps",
                        "status": "Open",
                        "issue_type": "Bug",
                        "url": "https://jira.example.com/browse/GUIDES-42533",
                    }
                ],
            }
        }
    )

    assert "real Jira issue" in text
    assert "GUIDES-42533" in text
    assert "Reltable references fail in nested maps" in text
    assert "AEM-6453" not in text
