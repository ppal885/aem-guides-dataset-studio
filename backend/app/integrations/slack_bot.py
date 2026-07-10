"""Slack Socket Mode worker for DITA Expert Bot.

Run with:
    python -m app.integrations.slack_bot

Required environment variables:
    SLACK_BOT_TOKEN=xoxb-...
    SLACK_APP_TOKEN=xapp-...

Optional:
    SLACK_DEFAULT_TENANT=kone
    SLACK_ALLOWED_TEAM_IDS=T123,T456
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Any

from app.services.chat_service import chat_turn, create_session


_BOT_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")
_MAX_SLACK_TEXT = 36000


@dataclass(frozen=True)
class SlackRuntimeConfig:
    bot_token: str
    app_token: str
    default_tenant: str
    allowed_team_ids: set[str]


def load_slack_config() -> SlackRuntimeConfig:
    bot_token = (os.getenv("SLACK_BOT_TOKEN") or "").strip()
    app_token = (os.getenv("SLACK_APP_TOKEN") or "").strip()
    default_tenant = (os.getenv("SLACK_DEFAULT_TENANT") or "kone").strip() or "kone"
    allowed_team_ids = {
        item.strip()
        for item in (os.getenv("SLACK_ALLOWED_TEAM_IDS") or "").split(",")
        if item.strip()
    }
    if not bot_token:
        raise RuntimeError("SLACK_BOT_TOKEN is required for Slack integration")
    if not app_token:
        raise RuntimeError("SLACK_APP_TOKEN is required for Slack Socket Mode")
    return SlackRuntimeConfig(
        bot_token=bot_token,
        app_token=app_token,
        default_tenant=default_tenant,
        allowed_team_ids=allowed_team_ids,
    )


def clean_slack_question(text: str) -> str:
    """Remove Slack mention markup and normalize whitespace."""
    cleaned = _BOT_MENTION_RE.sub("", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def slack_user_id(body_or_event: dict[str, Any]) -> str:
    user = body_or_event.get("user")
    if isinstance(user, dict):
        user = user.get("id")
    return str(user or body_or_event.get("user_id") or "slack-user")


def is_allowed_team(team_id: str | None, allowed_team_ids: set[str]) -> bool:
    if not allowed_team_ids:
        return True
    return bool(team_id and team_id in allowed_team_ids)


def format_slack_answer(answer: str) -> str:
    """Keep Slack replies within platform limits while preserving useful content."""
    text = (answer or "").strip()
    if not text:
        return "I could not generate an answer. Please try again with a DITA, AEM Guides, DITA-OT, or Jira question."
    if len(text) <= _MAX_SLACK_TEXT:
        return text
    return text[: _MAX_SLACK_TEXT - 180].rstrip() + "\n\n…Answer truncated for Slack. Open the web app for the full response."


async def ask_dita_expert(question: str, *, tenant_id: str, slack_user: str) -> str:
    """Run a single backend chat turn and collect streamed chunks into one answer."""
    session_id = create_session(user_id=f"slack:{slack_user}", tenant_id=tenant_id)
    chunks: list[str] = []
    async for event in chat_turn(
        session_id,
        question,
        user_id=f"slack:{slack_user}",
        tenant_id=tenant_id,
        human_prompts=True,
    ):
        event_type = event.get("type")
        if event_type == "chunk":
            chunks.append(str(event.get("content") or ""))
        elif event_type == "error":
            chunks.append(f"Slack integration error: {event.get('message') or 'unknown error'}")
    return format_slack_answer("".join(chunks))


def ask_dita_expert_sync(question: str, *, tenant_id: str, slack_user: str) -> str:
    return asyncio.run(ask_dita_expert(question, tenant_id=tenant_id, slack_user=slack_user))


def build_app(config: SlackRuntimeConfig):
    """Build the Slack Bolt app lazily so tests do not require slack_bolt."""
    from slack_bolt import App

    app = App(token=config.bot_token)

    @app.command("/dita")
    def handle_dita_command(ack, body, respond):
        ack()
        team_id = body.get("team_id")
        if not is_allowed_team(team_id, config.allowed_team_ids):
            respond("This Slack workspace is not allowed to use DITA Expert Bot.")
            return
        question = clean_slack_question(body.get("text") or "")
        if not question:
            respond("Ask like: `/dita What is keyscope in DITA? Show example.`")
            return
        respond({"response_type": "ephemeral", "text": "Thinking…"})
        answer = ask_dita_expert_sync(
            question,
            tenant_id=config.default_tenant,
            slack_user=slack_user_id(body),
        )
        respond({"response_type": "in_channel", "text": answer})

    @app.event("app_mention")
    def handle_app_mention(event, say, body):
        team_id = (body.get("team_id") or (body.get("team") or {}).get("id") or "").strip()
        if not is_allowed_team(team_id, config.allowed_team_ids):
            return
        if event.get("bot_id"):
            return
        question = clean_slack_question(event.get("text") or "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        if not question:
            say("Ask me a DITA, AEM Guides, DITA-OT, or Jira troubleshooting question.", thread_ts=thread_ts)
            return
        say("Thinking…", thread_ts=thread_ts)
        answer = ask_dita_expert_sync(
            question,
            tenant_id=config.default_tenant,
            slack_user=slack_user_id(event),
        )
        say(answer, thread_ts=thread_ts)

    @app.event("message")
    def handle_direct_message(event, say, body):
        if event.get("channel_type") != "im" or event.get("bot_id"):
            return
        team_id = (body.get("team_id") or (body.get("team") or {}).get("id") or "").strip()
        if not is_allowed_team(team_id, config.allowed_team_ids):
            return
        question = clean_slack_question(event.get("text") or "")
        if not question:
            return
        say("Thinking…")
        answer = ask_dita_expert_sync(
            question,
            tenant_id=config.default_tenant,
            slack_user=slack_user_id(event),
        )
        say(answer)

    return app


def main() -> None:
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    config = load_slack_config()
    app = build_app(config)
    SocketModeHandler(app, config.app_token).start()


if __name__ == "__main__":
    main()

