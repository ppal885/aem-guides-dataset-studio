# VM Chroma routing-only repair

This is a maintenance tool, not a corpus merger. Default invocation performs a
read-only preflight. `--apply` changes VM configuration and starts services; it
requires both explicit maintenance and background-writer-pause confirmations.

## What is preserved

- `/app/storage/chroma_db`: the current backend/MCP corpus, untouched by Chroma.
- `<repo>/backend/storage/chroma_db`: the separate direct-server corpus, untouched.
- Existing verified cold archives, audit copies, runtime trial copies and exports.
- Backend source, skills, evaluation metrics, Nginx configuration and public ports.

The new server uses a **fresh physical copy of the app store** beneath a private
`/app/storage/aem-chroma-routing-*` directory. Backend and MCP use that server on
`127.0.0.1:8000`; existing Nginx routes continue through port `4502`.

The observed app store contains seven collections: `jira_qa` 35,927;
`aem_guides` 3,682; `dita_spec` 5,357; `dita_ot_github` 2,990;
`kone_examples` 5,070; `kone_rag` 5,070; `learned_qa` 112.
Counts/UUIDs are read from the copied store, not substituted with these numbers.
The helper deliberately requires seven collections for this reviewed maintenance.

**49,890 backend-only records are NOT merged.** Shared IDs with conflicting
documents/metadata/vectors remain in their original separate stores. The six
tiny vector differences do not require re-embedding for this routing repair.

## Preconditions and limitations

1. Both `aem-backend.service` and `chroma.service` must already be inactive/dead.
   The script never stops an active service just to obtain its preflight.
2. No team traffic, direct Chroma clients, external ingestion jobs or other
   administrators may modify stores/configuration during the cutover.
   `--maintenance-confirmed` acknowledges this; it is NOT a traffic firewall.
3. Run as root on this Linux VM. The reviewed service uses
   `<repo>/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 1`.
   Unknown hooks, service identities, custom scopes/auth or launchers fail closed.
4. Use the existing **backend/venv** runtime with `chromadb==1.5.9`.
   The orchestrator is stdlib-only and also runs under VM `python3` 3.10.
   It installs/upgrades nothing. The incorrect VM `backend/.venv` is not selected.
5. Original stores must match both complete verified archives byte-for-byte
   according to SHA-256 manifests and `tar --compare`. Full archive member sets
   must also match. Symlinks, special files and hardlinked store files are rejected.
6. Nginx must already expose the actual Chroma `/api/v2/` route to loopback8000.
   `nginx -t` and live route checks are required. This script never rewrites Nginx,
   relaxes its access controls, or opens a new public port.
7. Required system tools: systemctl, nginx, lsof, GNU tar/cp and git. Source/config
   paths must be root-owned, not group/world-writable, without symlink redirects.
8. Runtime loader and vector-service source must match reviewed commit
   `551e475280c36f8d9f4014d16d235454885db39a` (LF/CRLF differences allowed).
   Newer unrelated commits are fine; a changed runtime contract needs review.

There is no global no-write backend-start switch. Normal backend startup can
initialize/migrate its **SQL application database**. This script does not roll
back those normal SQL startup effects. Confirm ordinary backend startup is safe
before applying; this is not a release deployment or database-migration tool.

## Why configuration is edited twice

`app.main` loads root `.env`, then backend `.env` with `override=True`, then raw
backend `.env.docker` assignments. A systemd Environment override alone loses.
The CSV importer loads backend `.env` with `override=False`.

The script appends the same bare routing assignments to backend `.env` and
`.env.docker`, preserving existing bytes. It also appends explicit `false` values
for the reviewed background writers: learned-QA startup synchronization; Jira
bootstrap/scheduling; DITA/bootstrap/PDF and AEM crawls; evidence-graph workers;
cleanup; shared-learning publication worker. These pauses **remain until reviewed**.
They do not disable request-triggered or external writes. Do not resume team
traffic or imports merely because the routing check passes.

Only two new systemd drop-ins are added. Before service startup the merged
effective settings must have the exact new Chroma command and read-only mounts
covering both original stores. A later conflicting override causes rollback
before any service starts. No existing unit file is replaced.

## Run the read-only preflight first

After the scripts have been published and pulled, from the repository directory:

```bash
if python3 scripts/uac_eval/repair_vm_chroma_routing.py --backup /root/aem-chroma-backups/20260905T234829Z-90ab157X; then
  echo "PREFLIGHT FINISHED: share the output before applying"
else
  echo "STOP: share the reason; do not change flags to bypass it"
fi
```

The `if` wrapper avoids terminating an SSH shell that already has `set -e`.
Preflight writes no report file, imports no backend/Chroma runtime, starts no
service and makes no API calls. It hashes ordinary cold files only. It may take
several minutes to verify multi-GB archives/stores. Output has no configuration
values other than the explicit nonsecret target and paths.

## Apply only after preflight review

The following is intentionally NOT part of the default command. It acknowledges
the persistent writer pause and exclusive maintenance window:

```bash
if python3 scripts/uac_eval/repair_vm_chroma_routing.py --backup /root/aem-chroma-backups/20260905T234829Z-90ab157X --apply --maintenance-confirmed --pause-background-writers; then
  echo "Share the routing result; keep imports and team traffic paused"
else
  echo "STOP: preserve ROUTING_RUN_DIR and share the redacted reason"
fi
```

If backend authentication is required, supply the existing `AEM_STUDIO_TOKEN`
through the current shell's approved secret mechanism. Never put a token in
source, command arguments, Git URLs or a shared report. The token is sent only
to backend/MCP loopback endpoints, not to Chroma. There is no auth bypass.

The script prints `ROUTING_RUN_DIR` immediately. Keep it. Its private config
backups contain secrets; do not attach or commit the directory or `journal.json`.
Share only the redacted console summary.

## Ownership-check failure and safe retry

Older revisions can stop with `COMMAND_FAILED_LSOF` even after the correct
Chroma process opened the fresh copy. `lsof +D` searches every directory entry;
an unopened entry can produce exit 1 while other open files are listed. Exit 1
alone does not prove a command execution failure. Also, `-t` suppresses warnings
unless followed by `+w`. These are documented in the [lsof FAQ, section 3.21.3](https://github.com/lsof-org/lsof/blob/master/00FAQ)
and [manual](https://github.com/lsof-org/lsof/blob/4.95.0/Lsof.8).

The old error wrapper did not retain return code/stdout/stderr. Consequently that
message alone cannot establish the specific VM cause; do not attribute it to
mount namespaces or corrupt data without further evidence.

PID-only `lsof` can also omit file-level `NOFD` diagnostics from an unreadable
process. The updated check first verifies access to the visible processes' maps
and FD metadata through `/proc`, with process/FD count caps and a deadline checked
between operations. This is not a hard timeout on a blocked kernel stat call. Restricted
`hidepid` mounts, permission failures, inconclusive inspection and PID reuse
stop the operation. Normal process/FD exits are counted, not mistaken for an
access failure. This requires root in the VM's host process namespace; it cannot
prove absence of processes hidden outside that namespace or on another host.

It then accepts 0 or 1 only after checking warning-enabled, strictly numeric
PID output. Any stderr diagnostic, malformed output, unexpected exit, missing
owner or extra owner still stops the operation. It independently requires the
service's SQLite FD and filesystem view to match the copy's device/inode,
verifies its loopback socket, and rechecks PID/start time and file identity.
This is a point-in-time ownership check, not protection against later external
writers; exclusive maintenance is still required. It does not ignore warnings
or add `-Q`.

On failure, `OWNERSHIP_CHECK=...` reports the failing step, PID observations,
return code, stderr byte count/hash and allowlisted warning categories. The
same redacted report is written to `ROUTING_RUN_DIR/ownership-check.json` before
rollback. Successful inventory observations are also persisted before the owner
check. Raw stderr, process command lines and environment/config contents are
never included. This report is safe to share; the private journal/backups are not.

After a rolled-back attempt:

1. Preserve its entire run directory and both cold archives. Do not reuse the
   failed copy as the new source, merge/import, or start either service manually.
2. Pull the reviewed fix without overwriting local edits. Run the tests below.
   On Linux, as root, the ownership suite includes a real `lsof` test on temporary ordinary
   files only; it does not open a Chroma store or start any service. On Windows
   this native test is explicitly skipped, not counted as VM proof.
3. Confirm both services are stopped and rerun the read-only preflight. Share
   the test/preflight results before another apply. A new apply creates a new
   copy from the verified cold original, with all existing guards intact.

No raw subprocess evidence can be recovered retroactively from an old
`COMMAND_FAILED_LSOF` report. The stopped services also mean a post-rollback
`lsof` check cannot reproduce the earlier live owner list.

## Success means routing parity, not a merged or fully revalidated corpus

`PASS_ROUTING_ONLY_WRITERS_PAUSED` requires:

- Initial copy file hashes match the cold source; both originals still hash the
  same after validation, and lsof finds no process holding either original open.
- Exactly the expected seven collection names/UUIDs/counts through both8000
  and existing4502 direct routes.
- The Chroma service's actual PID/cgroup, sole database-file ownership, SQLite FD
  and exclusive loopback8000 listener point to the fresh copy.
- A stored-vector sample query succeeds for each nonempty collection, without
  loading an embedding model.
- Fresh8001 and4502 MCP identities both say REMOTE and hash the exact target
  `127.0.0.1:8000`, SSL false, `default_tenant/default_database`; canonical
  collection UUIDs/counts agree with the copied source.

This is not full post-start document/vector equality, exhaustive HNSW validation,
embedding-model parity, import authorization or customer-corpus consolidation.
The importer still performs its own identity and embedding-canary checks.
Shell overrides can differ from `.env`; use the same explicit `CHROMA_HOST`,
`CHROMA_PORT`, `CHROMA_SSL` values for future approved ingestion. Existing importer
guards reject a different target rather than silently falling back to embedded.

Chroma version warning: in official1.5.9, Python package version is1.5.9, CLI
reports1.4.4, and `/api/v2/version` is hardcoded to1.0.0. The HTTP value alone does
not identify an outdated server. The supported launcher is the venv's `chroma`
console script, not `python -m chromadb.cli.cli`.
[CLI entry point](https://github.com/chroma-core/chroma/blob/1.5.9/chromadb/cli/cli.py),
[Rust version endpoint](https://github.com/chroma-core/chroma/blob/1.5.9/rust/frontend/src/server.rs#L624-L629),
[CLI arguments](https://github.com/chroma-core/chroma/blob/1.5.9/rust/cli/src/commands/run.rs).

## Rollback

Catchable failures after config installation stop the two services, restore
exact previous config bytes/ownership/mode, remove only hash-verified newly
created overrides, and leave services stopped. A process lock prevents two copies
of this maintenance tool from applying concurrently. It cannot lock out unrelated
administrator edits or recover automatically from SIGKILL/power failure.
Services retain their existing boot-enabled state. **Do not reboot or manually
start services mid-operation.** A reboot after an interrupted multi-file config
installation could start a partial configuration before journal recovery. After
such an interruption, stop both services before recovery and review their state;
the journal is not persistent startup inhibition or a filesystem transaction.

For an interrupted operation, or an explicit rollback while still in maintenance,
replace the example run directory with the printed value:

```bash
if python3 scripts/uac_eval/repair_vm_chroma_routing.py --rollback /app/storage/aem-chroma-routing-REPLACE_WITH_PRINTED_VALUE --maintenance-confirmed; then
  echo "Previous configuration restored; services remain stopped"
else
  echo "STOP: manual review required; do not overwrite changed configuration"
fi
```

Rollback rejects changed config/backups. It never deletes the fresh database,
never copies an old database over a newer one, and never automatically restarts
the previous split-store setup. Any writes made to the fresh database remain
recoverable there. Empty script-created drop-in directories and the private run
directory are retained. A failure before configuration changes leaves only the
fresh copy/journal and requires no config rollback.

## Local automated checks

```bash
python -I -B scripts/uac_eval/test_repair_vm_chroma_routing.py
python -I -B scripts/uac_eval/test_vm_chroma_ownership.py
python -I -B scripts/uac_eval/test_vm_chroma_routing_checks.py
python -I -B scripts/uac_eval/test_export_runtime_copies.py
python -I -B scripts/uac_eval/test_inspect_export_vectors.py
```

Routing tests use synthetic files and mocked services/HTTP; the existing export
suite also exercises a temporary synthetic Chroma store when available. They do not constitute
VM execution or production cutover evidence. Obtain the VM preflight first.
