# Publishing knowledge refresh: 9 September 2026

Run these commands on the existing Linux VM as root after pulling the published
change with `git pull --ff-only`. Preserve local edits if Git stops. The URL list is
[`publishing-knowledge-urls-20260909.txt`](../../scripts/data/publishing-knowledge-urls-20260909.txt).

The wrapper uses the currently reviewed candidate interpreter and existing shared
Chroma service. It checks the live backend command, working directory, service
identities, paused-writer flags, and backend/gateway/direct collection identities.
It reconstructs the backend's launch environment plus root `.env`, backend `.env`,
and `.env.docker` precedence **in memory**, without starting the application.
Keep these configuration files unchanged from the running service's startup and
keep concurrent imports/team writes paused throughout the operation. A changed
runtime or configuration needs review; do not substitute `backend/venv` or `.venv`.

## 1. Check without ingestion

```bash
PY=/opt/aem-backend-candidate-sPxFr6YU/venv/bin/python
if [ -x "$PY" ]; then
  (cd /root/aem-guides-dataset-studio && "$PY" -I -B scripts/replay_publishing_knowledge.py --check)
else
  printf 'STOP: reviewed candidate Python is missing\n'
fi
```

Continue only on `PASS_CHECK_ONLY`. The default invocation also performs this
check. It requires HTTP 200 HTML responses for all nine URLs and REMOTE Chroma at
`127.0.0.1:8000`, SSL false, in the existing default tenant/database. It performs
no model load, ingestion, local backend import, or file write. The existing MCP
status call may initialize the running service's normal status dependencies.
If authentication is required, use the existing approved `AEM_STUDIO_TOKEN`
environment mechanism; never paste tokens into commands or share environment files.

## 2. Apply and verify

```bash
(cd /root/aem-guides-dataset-studio && "$PY" -I -B scripts/replay_publishing_knowledge.py --apply)
```

Require `PASS_APPLIED`. Before invoking the existing ingestion helper, the wrapper
checks the reviewed local model hash and compares three distinct stored examples
with that encoder. This proves sampled compatibility only. The process explicitly
uses loopback HTTP, the OS certificate bundle, the local model, and offline model
settings. It preserves `DATABASE_URL` and evidence-graph capture settings. When
capture is enabled, ingestion also queues SQL graph events; paused graph workers
remain paused. A graph-event failure can occur **after** vectors were written.

The wrapper requires nine successful `OK` results, then reads back every expected
ingest ID with nonempty text and matching URL metadata through the shared client.
It rechecks backend/gateway identity, collection UUIDs, and unchanged service
identities. The AEM collection count may grow or stay unchanged on a repeated run.
Receipt and crawl-config backup are written to the printed private directory under
`/root/aem-publishing-refresh-*`; `--output-parent /existing/private/directory`
selects another location outside the repository. No environment or raw child logs
are persisted. On `STOP`, preserve the receipt and inspect its phase/reason before
retrying; the operation is not transactional and no automatic rollback occurs.

The underlying `ingest_urls.py` processes URLs even when they are already in crawl
config, so `crawl config: +0` after pulling is expected. It rewrites that JSON file
even at `+0`; its prior bytes are saved beside the receipt. Its exit code alone is
insufficient. Stable IDs make repeated identical ingestion an upsert, but a shorter
page can leave trailing old chunks, and another crawler's IDs can coexist. This
procedure does not remove either set or run the collection-replacing full crawler.

## 3. Optional: download the page images

```bash
(
  set -e
  cd /root/aem-guides-dataset-studio
  umask 077
  IMAGE_DIR=$(mktemp -d /root/aem-publishing-images-XXXXXXXX)
  printf 'Images: %s\n' "$IMAGE_DIR"
  while IFS= read -r url; do
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
      "$PY" -I -B scripts/extract_ui_images.py "$url" --all-images \
        --out "$IMAGE_DIR/${url##*/}"
  done < scripts/data/publishing-knowledge-urls-20260909.txt
)
```

`--all-images` includes small icons and all recognized raw-HTML media references.
Missing referenced images fail the command; zero recognized references can still
return success. Downloads are not visual inspection, image indexing, or automatic
learning. The committed skill reference files contain the reviewed UI evidence.

## 4. Optional: update root's installed skill copies

Review differences between each installed `SKILL.md` and the canonical
`.codex/skills/test-plan-generation/SKILL.md` first. If either contains local
instructions that must remain, merge the new Required References into that copy
instead of running the replacement block below. The block backs up both complete
installed directories, synchronizes shared files, then explicitly replaces each
`SKILL.md`; the sync helper intentionally excludes this file from global updates.
Other client-specific extensions remain intact.

Both locations must already be installed. If either is absent, this optional
block stops without creating an installation; use the updated package only when
you intend to install that client. Parentheses keep failures inside a subshell,
so they do not exit the interactive SSH shell.

```bash
(
  set -e
  cd /root/aem-guides-dataset-studio
  umask 077
  for consumer in .claude .codex; do
    target="/root/$consumer/skills/test-plan-generation"
    if [ -L "$target" ] || [ -L "$target/SKILL.md" ] || [ ! -d "$target" ] || [ ! -f "$target/SKILL.md" ]; then
      printf 'STOP: existing ordinary skill installation required: %s\n' "$target"
      exit 1
    fi
  done
  SKILL_BACKUP=$(mktemp -d /root/aem-test-plan-skill-backup-XXXXXXXX)
  printf 'Skill backup: %s\n' "$SKILL_BACKUP"
  for consumer in .claude .codex; do
    cp -a -- "/root/$consumer/skills/test-plan-generation" "$SKILL_BACKUP/$consumer"
  done
  python3 -B scripts/sync_test_plan_skill_copies.py --source-only --include-global
  for consumer in .claude .codex; do
    cp -- .codex/skills/test-plan-generation/SKILL.md "/root/$consumer/skills/test-plan-generation/SKILL.md"
  done
)
```

This updates repository consumer copies and root's existing `~/.claude` /
`~/.codex` installations on this VM. It does not update teammates' local
installations, `~/.agents`, or another VM user's account. Teammates need the updated
published ZIP for their own client. The ZIPs do not need rebuilding on the VM.

No service restart is needed for successful Chroma upserts. If the running backend
has cached an older skill bundle and a restart is required after successful
verification, restart **only** `aem-backend.service`, then rerun `--check` and the
existing `python3 -B scripts/uac_eval/verify_vm_search_embeddings.py` diagnostic.
Leave `chroma.service`, routing overrides, and every paused writer setting intact.
