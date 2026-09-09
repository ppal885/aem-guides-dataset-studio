# Codex VM-backed RAG: scoped transport repair

## What changed

The project `.codex/config.toml` previously launched `mcp_server.py` under
`aem_dataset_studio`. That server imports the workstation backend and reads its
local corpus. Configuring an unrelated HTTP client does not change those tools.

The same server name now launches the existing packaged Windows thin client in
an explicit read-only profile. It exposes only:

- `check_rag_status`
- `ask_dita_expert`
- `search_jira_history`
- `query_test_evidence_graph`

The client uses the existing VM `/mcp` gateway and documented `/api/v1/mcp/lookup-*`
routes. `ask_dita_expert` returns evidence for the calling assistant; it does not
invoke the VM chat/synthesis endpoint or generate a final UAC. A failed VM request
never falls back to the local backend or a local Chroma collection.

The old root server is retained as `aem_local_dita_tools`, with the shared four
tools and its two local RAG-status aliases disabled. Local DITA generation,
validation, file access, local registries and other specialist tools remain
available, clearly under the local namespace. This is not a migration of every
local generator's internal dependencies to the VM. Backend/evaluation/skill
implementation is not changed by this transport patch.

Codex supports project-scoped `command`, `args`, `env`, `env_vars`,
`enabled_tools`, and `disabled_tools`; see the
[official MCP configuration reference](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Activation and proof

Reload the MCP connection or restart Codex after saving ongoing work. An already
running chat can retain its old server process. Editing the file or passing the
following fresh-process test does not prove that an existing chat was reloaded.

From the Windows checkout, run:

```powershell
.\venv\Scripts\python.exe -B scripts/verify_codex_vm_rag.py
```

The script reads the actual project profile, initializes a fresh MCP subprocess,
checks its four advertised tools, calls status and evidence/history tools, and
compares the observed index identity with the same VM's HTTP status response.
It also lists (without invoking) the retained local DITA tools. It does not ingest,
create a chat session, call a planner, restart services, or open a database.

Expected status is `PASS_FRESH_STDIO_VM_ROUTING_ONLY`. This proves this profile's
read path, not full corpus equivalence, a live UAC benchmark, fresh backend
loopback parity, or a teammate's authenticated identity. The result reports
`variables_source_gap` separately: successful routing must not hide missing docs.
An optional `--output <new-file>` writes a redacted JSON receipt; existing files
are never overwritten. `--require-variables` makes a missing exact source fail.

The reviewed fingerprint pin in the project config is checked before retrieval.
Counts may grow after approved ingestion; the stable target fingerprint should
not change. A mismatch is an error, not permission to remove the pin. Investigate
the actual target and approve any necessary pin change separately.

## Authentication boundary

The existing VM endpoint is `http://10.42.46.78:4502`. This workstation profile
explicitly opts into anonymous, plaintext intranet **reads** with an empty token.
This is not authenticated team access, and traffic is not encrypted. No personal,
shared development or administrator token is sent. It does not grant write or
feedback-review authority. Restrict network access to the intended team.

Before using personal credentials, configure an approved HTTPS endpoint (or
properly authenticated loopback SSH tunnel). Configure `AEM_STUDIO_TOKEN` through
the client's environment, never in a committed config. Do not send a token over
non-loopback HTTP; the new transport rejects that even with HTTP opt-in. Do not
use `dev-bypass` as an identity. Feedback capture/review is deliberately excluded
from this read-only profile and requires the separately authenticated team client.
Provisioning team credentials or changing VM authentication is not performed here.

Read-only HTTP responses have a 4 MiB decoded limit and a maximum 30-second total
deadline per request. Redirects, unexpected routes, malformed RPC results and
index-pin mismatches fail explicitly. Proxy environment settings are not inherited
by this profile. TLS verification stays enabled for HTTPS.

## Missing Variables source

The required page is the documented
[Variables feature](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/output-gen-config/config-native-pdf-publish/native-pdf-variables),
not the separate Language Variables page. It is now included in the crawl config.

Use the [one-page guarded append procedure](publishing-knowledge-refresh.md#optional-append-one-missing-guides-page-without-refreshing-other-urls)
on the VM, after publishing/pulling these scripts. The procedure verifies the
reviewed Python/model, paused writers, backend/gateway/direct Chroma identity,
then adds only an absent page and verifies all inserted payloads. It never calls
the collection-replacing full crawler. No workstation-to-Chroma write shortcut
is provided.

After `PASS_SINGLE_URL_APPENDED`, rerun on this workstation:

```powershell
.\venv\Scripts\python.exe -B scripts/verify_codex_vm_rag.py --require-variables
```

Also run `scripts/uac_eval/verify_vm_search_embeddings.py` **on the VM** for the
fresh loopback comparison. These checks do not replace a blinded full UAC run.
Do not resume paused writers, re-ingest unrelated corpora, or restart Chroma as
part of this procedure. A successful append does not itself require a restart.

## Claude activation is separate

The shared Windows/Unix `server.py` fix is also shipped in the team client ZIPs,
with `READ_ONLY_RAG.md` describing an explicit four-tool profile. Git push does
not update separately extracted clients or Claude Desktop/Code MCP registrations.
The existing full-client installers/doctor scripts are not read-only installers:
their old `dev-bypass` over HTTP configuration is rejected by the transport.
Use the new guide, preserve other connections and private settings, then restart
the relevant assistant. Do not silently turn a feedback/review connection into
anonymous read-only access. No teammate identity or installed Claude connection
was changed as part of this release.

## Offline tests and rollback

```text
python -B -m unittest scripts.test_vm_read_only_mcp_client scripts.test_verify_codex_vm_rag scripts.test_replay_publishing_knowledge
```

Windows and Unix client source files must byte-match. The release ZIPs carry the
updated client and read-only activation guide, with unrelated archive members
preserved. Updating the repository ZIPs does not update installed team copies
automatically. Preserve unrelated local and global skill edits.

The previous project config was preserved in the local analysis directory before
the edit. A rollback is only a reviewed config restore and MCP restart; it must
not delete or revert corpora. The former local backend source was left unchanged.
