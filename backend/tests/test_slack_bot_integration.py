from app.integrations.slack_bot import (
    clean_slack_question,
    format_slack_answer,
    is_allowed_team,
    slack_user_id,
)


def test_clean_slack_question_removes_bot_mentions_and_extra_spaces():
    assert clean_slack_question("<@U123>   What is keyscope in DITA?   Show example.") == "What is keyscope in DITA? Show example."


def test_is_allowed_team_allows_all_when_not_configured():
    assert is_allowed_team("T123", set())


def test_is_allowed_team_blocks_unlisted_workspace():
    assert is_allowed_team("T123", {"T123"})
    assert not is_allowed_team("T999", {"T123"})


def test_slack_user_id_reads_command_and_event_shapes():
    assert slack_user_id({"user_id": "U1"}) == "U1"
    assert slack_user_id({"user": "U2"}) == "U2"
    assert slack_user_id({"user": {"id": "U3"}}) == "U3"


def test_format_slack_answer_has_empty_and_truncated_fallbacks():
    assert "could not generate" in format_slack_answer("").lower()
    long_answer = "A" * 40000
    formatted = format_slack_answer(long_answer)
    assert len(formatted) < len(long_answer)
    assert "truncated for Slack" in formatted

