# Repair the VM embedding runtime without undoing Chroma routing

## What is fixed in code, and what is not yet fixed on the VM

The routing repair already made backend and gateway use the same Chroma server.
It did not make text embedding work. The observed failure chain was:

1. The backend uses Python **3.11.0rc1**.
2. Torch imports `sys.get_int_max_str_digits`, which that prerelease lacks.
3. SentenceTransformer cannot load the local encoder.
4. The old embedding service silently tries Azure even with
   `USE_AZURE_EMBEDDING=false`. That request returns 1536-dimensional vectors.
5. The selected Chroma collections contain 384-dimensional vectors, so queries fail.

The repository repair makes the existing flag **exclusive**. Local failure returns
unavailable; Azure failure cannot switch to local either. It validates complete,
finite embedding responses and isolates query caches by provider/configuration and
runtime reset. No vector is padded, truncated, re-embedded into storage, or converted
to another model space. `is_embedding_available()` is a readiness predicate so a
remote provider can be retried; diagnostics additionally expose last-request status,
verified encoding availability, and dimension. Credentials alone do not prove a
successful embedding request or model parity.

This patch stops invalid fallback but **does not repair Python on the VM**. Do not
deploy it and report RAG restored just because dimension-error logs disappear.
Unavailable retrieval is still unavailable. Existing caller-specific degraded/empty
results are not promoted to successful search or coverage by this patch.

## Boundaries

- Preserve both original Chroma stores, cold archives, and the successful routing
  directory. Do not rerun `repair_vm_chroma_routing.py --apply`.
- Keep all existing background-writer pauses and team/import maintenance in place.
- Keep the old interpreter and `backend/venv` intact: Chroma uses them too.
- No OS Python replacement, dependency downgrade to dodge one import, monkeypatch
  of `sys`, database merge, corpus ingest, or automatic service cutover.
- The existing local-path-to-bundled/name fallback remains unchanged. Use an
  existing, absolute, hash-verified model path for this maintenance procedure.
  Provider pinning is not a claim that every historic collection used that model.

## 1. Prepare final CPython separately

`build_vm_python311.sh` builds the official, SHA256-verified CPython **3.11.16** into
the fresh prefix `/opt/aem-python-3.11.16`. It will not overwrite an existing prefix,
call APT/dpkg/systemctl, create a backend venv, or load a model. It uses a private
directory on disk, bounded compilation, `altinstall`, and final-interpreter/stdlib
checks. Failure preserves the partial build/install for inspection; do not delete
or reuse it blindly.

After these files are published and pulled, from the VM repository:

```bash
python3 -B -m unittest discover -s scripts/uac_eval -p test_build_vm_python311.py -v
bash scripts/uac_eval/build_vm_python311.sh --check
```

Only if the check passes:

```bash
bash scripts/uac_eval/build_vm_python311.sh --build
```

The VM was missing development headers for nine packages. APT also reported a
half-configured kernel. The build helper deliberately stops on missing headers;
it does **not** repair the kernel as a hidden prerequisite. The separately approved
kernel backup failed because `/var/lib/initramfs-tools` was treated as mandatory.
That directory must be optional in a corrected backup, with absence recorded.
Preserve the partial backup. Review installed kernel/initramfs hooks before any
targeted configuration retry, use an on-disk private `TMPDIR`, and do not reboot.

Sources: [official release and source hashes](https://www.python.org/downloads/release/python-31116/),
[Python Unix installation guidance](https://docs.python.org/3.11/using/unix.html).

## 2. Recreate dependencies in a separate backend-only venv

This remains an operator-reviewed step, not an action performed by the helper.

- Create the candidate venv using the final interpreter at its final absolute path.
- Inventory the old VM's exact installed versions and provenance privately. Do not
  paste credential-bearing direct URLs or an unrestricted environment dump.
- Reinstall reviewed exact wheel versions with hashes into the candidate, then run
  `pip check`. Do not copy the old venv/site-packages or upgrade its packages.
- Do not blindly use the current requirements file as an exact VM lock: it has
  broad ranges and differs from the deployed environment (including Click).
- Keep old Chroma running with its unchanged launcher; the new venv is backend-only.

[Python documents that venvs must be recreated, not copied](https://docs.python.org/3.11/library/venv.html).

## 3. Check the candidate model against frozen vectors before cutover

`verify_local_embedding_canaries.py` accepts one or more **existing** JSONL files
from `export_runtime_copies.py`, each with its SHA256 from the verified export
report. It never opens a live database. It loads only an absolute local model,
with remote code disabled and model-download/telemetry settings disabled. Invoke
it under `unshare --net` as an additional network barrier. Do not send historical
Jira text to Azure or any external provider for this check.

Example, replacing the three placeholders with verified paths/hash:

```bash
unshare --net env -i PATH=/usr/bin:/bin HOME=/nonexistent /ABSOLUTE/CANDIDATE/VENV/bin/python -I -B scripts/uac_eval/verify_local_embedding_canaries.py --model-path /ABSOLUTE/EXISTING/MODEL --export /ABSOLUTE/EXPORT/app-storage--jira_qa.jsonl EXPORT_SHA256
```

Repeat `--export JSONL_PATH SHA256` for `aem_guides` and `dita_spec` as well. Choose
exports from the store currently served by the repaired routing. The other old
store is not silently incorporated into this proof.

The check hashes the model before/after, verifies frozen export hashes, and compares
three distinct stored texts/vectors per export using the same fixed tolerance as
the existing importer (`rel_tol=1e-4`, `abs_tol=1e-6`). No tolerance override exists.
The JSON receipt excludes documents, IDs, vectors, metadata, and raw exceptions.
Normal local ML-library messages may appear on stderr; share the JSON receipt, not
unreviewed library logs. Tests use synthetic vectors only:

```bash
python3 -B -m unittest discover -s scripts/uac_eval -p test_verify_local_embedding_canaries.py -v
```

`PASS_OFFLINE_SAMPLES_ONLY` proves only those exported samples against that candidate
encoder. It does not establish whole-corpus homogeneity, live backend use, or permit
writes. A failure must be investigated, not bypassed by picking another 384-D model.

## 4. Backend-only cutover and live acceptance

Do not use the old routing rollback for this step: it stops both services and does
not know about a new runtime override. A separate reviewed backend-only override
and hash-guarded rollback are required before changing the launcher.

Before a controlled backend-only restart, snapshot the effective backend unit,
writer-pause configuration, Chroma PID/InvocationID, and collection identities/counts.
Keep port 8001, working directory, original-store read-only protections and remote
Chroma target unchanged. The real loader's `.env`/`.env.docker` precedence must be
checked; systemd settings alone are insufficient. Use `USE_AZURE_EMBEDDING=false`
and the validated absolute model path.

Acceptance after candidate backend startup:

1. Chroma PID/InvocationID, target fingerprint, collection UUIDs/counts unchanged.
2. Backend diagnostics show LOCAL, successful recent encoding, dimension 384 and
   no load error. A process restart ensures no pre-patch vector cache survives.
3. `verify_vm_search_embeddings.py` passes through both 8001 and 4502.
4. Product/DITA retrieval and a complete UAC run return useful, sourced evidence.
5. No fallback/dimension errors, and no index writes or resumed background writers.

Only after live checks should the repair be declared complete. Corpus merging,
customer import, writer resumption and opening team traffic remain separate
decisions. This change does not alter skills, UAC gates, prompts, evaluation
calculations, or the dashboard.
