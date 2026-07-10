# DITA Expert Bot Slack Integration

This project supports a Slack-first chat surface through a Socket Mode worker.

## Recommended mode

Use Slack Socket Mode when the backend runs on an internal Adobe VM and does not expose a public HTTPS endpoint.

```text
Slack /dita or @DITA Expert Bot
  -> Slack Socket Mode WebSocket
  -> python -m app.integrations.slack_bot
  -> existing backend chat/RAG/LLM service
  -> Slack thread reply
```

## Slack app configuration

Create the app at `https://api.slack.com/apps`.

### App-level token

Enable **Socket Mode** and create an app-level token:

- Token name: `dita-expert-socket`
- Scope: `connections:write`
- Token prefix: `xapp-`

### Bot OAuth scopes

Add these scopes under **OAuth & Permissions**:

- `chat:write`
- `commands`
- `app_mentions:read`
- `im:history`

Optional later:

- `channels:history`
- `reactions:read`

### Slash command

Create:

- Command: `/dita`
- Description: `Ask DITA Expert Bot`
- Usage hint: `What is keyscope in DITA? Show example.`

With Socket Mode, you do not need to expose a public request URL for the MVP worker.

### Event subscriptions

Subscribe to bot events:

- `app_mention`
- `message.im`

Then reinstall the app to the workspace after scope/event changes.

## Adobe VM environment

Set these environment variables on the VM:

```bash
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_APP_TOKEN="xapp-..."
export SLACK_DEFAULT_TENANT="kone"
export SLACK_ALLOWED_TEAM_IDS="T12345678"
```

`SLACK_ALLOWED_TEAM_IDS` is optional but recommended for org safety. Leave it empty only for initial local testing.

## Install dependencies

From the repository root:

```bash
cd backend
pip install -r requirements.txt
```

## Run the worker

Run this next to the normal FastAPI backend process:

```bash
cd backend
python -m app.integrations.slack_bot
```

Keep both processes running:

- FastAPI backend, for web/admin/review center.
- Slack worker, for Slack Socket Mode events.

## Smoke test

In Slack:

```text
/dita What is keyscope in DITA? Show an example.
```

Expected result:

- Slack immediately replies `Thinking…`.
- Bot posts a senior DITA answer with explanation, XML example, expected result, and relevant guidance.

## Production note

For a stable VM deployment, run the Slack worker as a service, for example with `systemd`, Supervisor, Docker Compose, or the existing VM process manager.

