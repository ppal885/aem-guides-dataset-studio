# Reusable prompt: ingest an Experience League URL into RAG + learn + grow vocabulary

## Setup (one-time, platform-agnostic — macOS / Windows / Linux)

Run from the repo root. Use `python` or `python3` — whichever your OS has; nothing else
differs. Paths use forward slashes (Python and git accept them on every OS).

1. Clone the repo and `cd` into it. Ensure Python 3.10+ is installed.
2. (Recommended) create + activate a virtualenv: `python -m venv venv`, then activate it the
   way your OS/shell does. This is the only step that differs per OS; everything after is
   identical.
3. Install dependencies:
   ```
   python -m pip install -r backend/requirements.txt
   ```
   This provides httpx, chromadb, sentence-transformers, langchain*, python-dotenv.
4. Config: copy `backend/.env.example` to `backend/.env`. RAG uses a LOCAL embedding model
   by default (no API key needed). Only if you deliberately use Azure embeddings do you set
   `AZURE_OPENAI_API_KEY` etc. IMPORTANT: ingest with the SAME embedding model the corpus was
   built with (the default `DITA_EMBEDDING_MODEL` / bundled model) — mixing models makes the
   vectors incompatible.
5. RAG corpus: ensure `backend/storage/chroma_db/` exists. It is ~1.5 GB and NOT in git, so a
   fresh clone will not have it. Copy the whole `backend/storage/chroma_db/` folder from an
   environment that has it (e.g. the VM or an existing clone). Without it, the collection
   starts empty and queries return nothing until you ingest pages.
6. Verify setup (all should pass / print OK):
   ```
   python .codex/skills/test-plan-generation/scripts/guides_vocabulary.py --self-test
   python .codex/skills/test-plan-generation/scripts/test_skill_scripts.py
   python scripts/ingest_urls.py "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/output-gen-config/config-native-pdf-publish/native-pdf-language-variables"
   ```
   The last prints `OK <n> chunks`. Setup is done.

---



Paste the block below into Codex or Claude Code (run from the repo root). Replace
`<EXP_LEAGUE_URL>` with the Experience League doc URL. Works for both agents; it only
uses committed scripts so it is safe to re-run and reuse for every URL.

---

You are extending the AEM Guides RAG corpus and the `test-plan-generation` skill from a
single Experience League doc URL. Do ALL of the following, in order, and stop only if a
step genuinely fails (report the failure, do not fake success).

URL: `<EXP_LEAGUE_URL>`

Run every command FROM THE REPO ROOT (the aem-guides-dataset-studio checkout). All the
scripts self-locate `backend/` and load `backend/.env` themselves - do NOT `cd backend`.
The backend does NOT need to be running (the scripts open the local Chroma corpus at
`backend/storage/chroma_db` directly). `ingest_urls.py` has no hard langchain dependency
(it falls back to httpx), so it works on the VM without extra installs.

1. INGEST (non-destructive — NEVER call crawl_service.crawl_and_index with one URL; it
   does a full delete+replace that would wipe the corpus). From the repo root:
   ```bash
   python scripts/ingest_urls.py "<EXP_LEAGUE_URL>"
   ```
   This chunks + embeds + upserts the page into the `aem_guides` collection and adds the
   URL to `backend/config/aem_guides_crawl_urls.json`. Confirm it printed "OK <n> chunks".

2. LEARN THE BEHAVIOUR from RAG (do not invent — read what was ingested). From the repo root:
   ```bash
   python -c "
   import sys; sys.path.insert(0,'backend')
   from dotenv import load_dotenv; load_dotenv('backend/.env')
   from app.services.vector_store_service import _get_client, CHROMA_COLLECTION_AEM_GUIDES
   import re
   c=_get_client(); coll=c.get_collection(CHROMA_COLLECTION_AEM_GUIDES)
   got=coll.get(where={'url':{'\$eq':'<EXP_LEAGUE_URL>'}}, include=['documents'])
   print(re.sub(r'\s+',' ',' '.join(got.get('documents') or [])).encode('ascii','ignore').decode()[:3000])
   "
   ```
   Write a short, plain-English summary of the behaviour (especially any fallback /
   precedence / edge-case behaviour) grounded ONLY in the retrieved text.

3. EXTRACT THE UI IMAGES (Experience League images are JS-loaded; the raw HTML lists
   `media_<hash>.png`). Use the script (dependency-light, httpx only). From the repo root:
   ```bash
   python scripts/extract_ui_images.py "<EXP_LEAGUE_URL>"
   ```
   It saves the images to `~/expleague_img/<page-slug>/`, sorted largest first. Then open
   the top 2-3 with the image-reading tool and describe the UI surfaces/panels/controls
   they show (this is how you learn the UI behind a term).

4. GROW THE VOCABULARY (this is the payoff of ingesting). Run the corpus miner and REVIEW
   its candidates — it is a review aid, NOT an auto-adder. From the repo root:
   ```bash
   python scripts/uac_eval/mine_guides_vocabulary.py --top 40 --min-freq 4
   ```
   From the candidates AND the page you just read, add ONLY genuine AEM Guides product
   terms to `.codex/skills/test-plan-generation/data/guides_vocabulary.json`:
   - `canonical_terms`: correct Guides UI/feature names.
   - `advise` / `block`: for a WRONG term you can name, add a rule mapping it to the right one.
   - `synonyms`: for two names of the same thing.
   HARD RULE: verify every term against the product before adding. Do NOT add AEM
   platform / Forms / Sites terms that merely leaked into the corpus (e.g. Rule Editor,
   Visual Rule Editor, Adaptive Forms, Sites/Page Editor, Adobe *Console) and do NOT add
   heading/sentence fragments. When unsure, leave it out and note it for human review.

5. FINALIZE — platform-agnostic steps (identical on macOS, Windows, Linux). Every command
   is `python` + git; use forward slashes in paths (Python and git accept them on all OSes).
   On macOS/Linux the interpreter may be `python3` instead of `python` - use whichever your
   env has; nothing else changes. Do NOT translate these into shell-specific syntax (no
   bash heredocs, no PowerShell cmdlets) - run them verbatim from the repo root.

   a. Gate + sync + test (all must pass before you commit):
      ```
      python .codex/skills/test-plan-generation/scripts/guides_vocabulary.py --self-test
      python scripts/sync_test_plan_skill_copies.py --include-global
      python .codex/skills/test-plan-generation/scripts/test_skill_scripts.py
      ```
      The last must print `ALL SELF-TESTS PASSED`. If any fails, fix it - do NOT commit.

   b. Rebuild the offline skill zips ONLY if you changed skill files (vocabulary / SKILL.md /
      gates). Ingesting a page alone does NOT need this (the RAG corpus is not in the zip):
      ```
      python scripts/package_mcp_client_bundles.py
      ```

   c. Commit ONLY the files you changed (never `git add -A`). Use single-line `-m` messages
      (works in every shell). Typical sets:
      ```
      git add .codex/skills/test-plan-generation/data/guides_vocabulary.json .claude/skills/test-plan-generation/data/guides_vocabulary.json skills/test-plan-generation/data/guides_vocabulary.json release-artifacts/aem-guides-mcp-client-unix/.claude/skills/test-plan-generation/data/guides_vocabulary.json release-artifacts/aem-guides-mcp-client-windows/.claude/skills/test-plan-generation/data/guides_vocabulary.json backend/config/aem_guides_crawl_urls.json
      git commit -m "chore(rag+skill): ingest <page-name>; grow vocabulary from RAG"
      ```
      If you rebuilt zips in (b), also:
      ```
      git add release-artifacts/aem-guides-mcp-client-unix.zip release-artifacts/aem-guides-mcp-client-windows.zip
      git commit -m "chore(release): rebuild mcp-client zips with latest skill"
      ```
      End every commit message with a final line:
      `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

   d. Push and get it onto main:
      ```
      git push origin HEAD
      ```
      Then open a PR (branch -> main) and merge it. Creating/merging a PR may be blocked by
      the agent's token/policy; if so, print the compare URL
      `https://github.com/<owner>/<repo>/compare/main...<branch>` for a human, OR (only if the
      branch is exactly ahead of main with no divergence) fast-forward main directly:
      `git push origin <branch>:main`. Never force-push; never bypass a failing gate.

   e. Propagate to every environment that consumes the corpus (VM, other clones): from that
      env's repo root, `git pull` then re-run `python scripts/ingest_urls.py "<EXP_LEAGUE_URL>"`
      so its RAG corpus matches (the corpus is per-environment, not shipped in git or the zip).

6. REPORT: the ingested chunk count, the behaviour summary, the UI surfaces seen, the
   terms you added (and any you left out for human review), and the final commit hash.

## GUARDRAILS — do NOT do these (prevent wrong implementation)

- **NEVER wipe the corpus.** Do not call `crawl_service.crawl_and_index` (or any full
  re-crawl) to add one page — it does a full delete+replace of the whole `aem_guides`
  collection. Only ever use `scripts/ingest_urls.py` (append/upsert). Re-running it on the
  same URL is safe (idempotent: same ids), so never "clear and reload".
- **Verify success; never fake it.** Confirm ingest printed `OK <n> chunks` with n>0. If it
  printed 0 chunks, a FAIL, or an error, STOP and report — do not proceed as if it worked.
- **Use the REAL full URL.** Never run with the literal placeholder `<EXP_LEAGUE_URL>` or a
  `…` ellipsis; paste the complete Experience League URL.
- **RAG drives terminology — never invent.** For every product concept the ingested doc
  documents, use the doc's exact terms and behaviour (especially fallback/precedence). If
  RAG lacks it, say so and mark it unverified. Do not write invented framing (e.g. no
  "regional value / generic value / N-character locale" — a language variable has a value
  per language; missing value falls back to the UI language).
- **Human-verify EVERY mined term before adding.** The miner surfaces candidates only. Add
  a term to `guides_vocabulary.json` ONLY if you can confirm it is a real AEM Guides UI
  surface/feature. REJECT, and do not add:
  - AEM platform / Forms / Sites terms that leaked into the corpus: Rule Editor, Visual
    Rule Editor, Adaptive Forms/Form, Sites Editor, Page Editor, Component Image Editor,
    Adobe Developer/Admin/Web Console, Offers Console, Universal Editor.
  - Heading/sentence fragments (e.g. "Configure New Baseline", "Schematron Validation
    Reports", "Utilize Metadata").
  Known corrections already encoded (do not re-add the wrong side): Advanced Map Editor ==
  Map console; Theme Editor -> Theme Page; there is no Rule Editor in Guides (the editor is
  the Editor with Author View / Source View / Preview); Schematron -> Schematron Panel /
  Schematron File / Content Health report (no "Validation Reports"); Baseline/Map/Translation/
  Conditions/Subject Scheme are PANELS not dashboards; Editor Preview (not simple/conditional
  preview); "generated file" -> the fmdita-outputs folder; no "stale preset"; no run "workflow"
  (use output history). When unsure, LEAVE IT OUT and note it for human review.
- **Gate before commit.** `guides_vocabulary.py --self-test` AND `test_skill_scripts.py` must
  print PASS / `ALL SELF-TESTS PASSED`. If either fails, DO NOT commit — fix first. Keep all
  skill copies byte-identical via `sync_test_plan_skill_copies.py --include-global` (the
  `skill_bundle_fingerprint` test fails otherwise).
- **Commit ONLY your two files.** `git add` exactly `*/test-plan-generation/data/guides_vocabulary.json`
  and `backend/config/aem_guides_crawl_urls.json` — never `git add -A` (do not sweep unrelated
  concurrent working-tree changes). Push to the working branch, never force-push, never commit
  straight to main.
- **Anti-hardcoding.** Do not put a Jira key, a customer name, or a fixture value inside
  `guides_vocabulary.json` or any active skill script (the anti-hardcoding audit fails). Use
  `"source": "human-correction"`.

Notes:
- The VM shared corpus is separate. After committing, on the VM run (from the repo root):
  `git pull --ff-only && python scripts/ingest_urls.py "<EXP_LEAGUE_URL>"` so the VM corpus
  matches. `ingest_urls.py` needs no langchain (httpx fallback); it only needs the local
  Chroma corpus + the backend's embedding model, both already on the VM.
- The learn-behaviour read (step 2) is OPTIONAL inspection; only ingest (1) + mine (4) change
  anything. The skill queries RAG for behaviour automatically at UAC-authoring time.
