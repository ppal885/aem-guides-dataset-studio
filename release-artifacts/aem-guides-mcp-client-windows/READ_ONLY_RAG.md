# VM RAG connection for Claude Desktop, Claude Code and Codex

## Updating is not automatic

A repository push updates GitHub, not an installed client or a running assistant.
Extract the updated ZIP into a **new directory**. Keep the old client, its private
configuration and locally edited skill files. Do not delete or overwrite them.
An assistant that already uses a remote VM connector does not use this Python
client; its connection must be verified separately.

This profile provides four read-only tools: `check_rag_status`, `ask_dita_expert`,
`search_jira_history`, and `query_test_evidence_graph`. It has no local RAG fallback
and does not generate a final UAC. Claude/Codex continues to do the reasoning.
Feedback submission/review and local AEM upload are **not** exposed by this profile.
Keep those separate authenticated/local connections if needed.

## Prepare the Python client

Use an existing compatible Python environment, or create a new environment inside
the newly extracted directory and install `requirements.txt`. No Node dependency
is needed for these four read-only tools. Do not run the old `setup`/`install`,
`smoke_test`, or `doctor_claude` scripts for this profile: their legacy full-client
configuration and tool assertions do not implement this read-only profile.

Windows, from the new client directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS/Linux, from the new client directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Python 3.10+ is required. Use a supported final release, not a release candidate.

## Register an explicit read-only profile

In the chosen assistant's MCP configuration, add a server using the absolute path
to that environment's Python and the new `server.py`. Preserve all other servers.
The following is a server entry, **not a replacement for the entire config**:

```json
{
  "command": "<absolute path to the new environment's Python>",
  "args": ["<absolute path to the new client directory>/server.py"],
  "env": {
    "PYTHONUTF8": "1",
    "AEM_STUDIO_URL": "http://10.42.46.78:4502",
    "AEM_STUDIO_READ_ONLY": "true",
    "AEM_STUDIO_TOKEN": "",
    "AEM_STUDIO_ALLOW_INSECURE_HTTP": "true",
    "AEM_STUDIO_TIMEOUT_SECONDS": "30",
    "AEM_STUDIO_EXPECTED_INDEX_FINGERPRINT": "f95efbe8495f6d492d324e24808867a40d4469539720c41761a1315ad4bab125"
  }
}
```

Replace both path placeholders. JSON Windows paths require escaped backslashes
or forward slashes. The URL and fingerprint identify this team's reviewed VM;
other teams must use their own reviewed target, not remove the identity check.

- Claude Desktop: the entry goes under `mcpServers` in its Desktop MCP config.
- Claude Code: register this server entry at the intended user/project scope.
  A project `.mcp.json` is not automatically a Claude Desktop configuration.
- Codex: use the equivalent project TOML profile documented in
  `docs/runbooks/codex-vm-rag-transport.md` in the repository.

Avoid two competing AEM retrieval connections. Do not remove an older connection
blindly if it also provides feedback or local DITA tools; separate those tools
before retiring duplicate retrieval. Save work and reconnect/restart the chosen
assistant after the configuration change.

## Security and verification

The example deliberately opts into **anonymous plaintext intranet reads** on the
existing VM. It is not authenticated/encrypted team access or approval authority.
No token may be sent over non-loopback HTTP, including `dev-bypass`. The client now
rejects that legacy combination. Personal/team credentials require an approved
HTTPS origin or authenticated loopback tunnel; do not commit credentials. Setting
`AEM_STUDIO_TOKEN` to empty in the profile prevents an old client `.env` from
supplying a token. Keep TLS verification enabled for HTTPS.

In a fresh Claude/Codex session, call `check_rag_status`. Confirm `mode=REMOTE`,
the expected fingerprint, and the collection IDs against the VM report. Then ask
`ask_dita_expert` about `Native PDF Variables Variable Sets page layouts` and inspect
the actual source URLs. The required source ends in `native-pdf-variables`, not
`native-pdf-language-variables`. Successful routing alone does not prove that the
missing page has been ingested. Counts can change after approved ingestion.

The repository's guarded one-page VM ingestion and readback remain a separate
operator action. This client update neither ingests documents nor resumes writers.
Do not report team authentication, VM-loopback parity, or a full UAC benchmark as
passed based only on this connection test.
