# Reusable prompt: ingest an Experience League URL into RAG + learn + grow vocabulary

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
   `media_<hash>.png`). Download and VIEW the key ones. From the repo root:
   ```bash
   python -c "
   import httpx, re, os
   url='<EXP_LEAGUE_URL>'; base=url.rsplit('/',1)[0]+'/'
   h=httpx.get(url, timeout=30, follow_redirects=True).text
   pngs=list(dict.fromkeys(re.findall(r'media_[0-9a-fA-F]+\.png', h)))
   out=os.path.expanduser('~/expleague_img'); os.makedirs(out, exist_ok=True)
   for i,m in enumerate(pngs):
       r=httpx.get(base+m, timeout=30, follow_redirects=True)
       if r.status_code==200 and len(r.content)>2000: open(os.path.join(out,f'{i:02d}_{m}'),'wb').write(r.content)
   print('saved', out)
   "
   ```
   Then open the largest 2-3 saved PNGs with the image-reading tool and describe the UI
   surfaces/panels/controls they show.

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

5. SYNC + TEST + COMMIT. Keep all skill copies byte-identical and green:
   ```bash
   python .codex/skills/test-plan-generation/scripts/guides_vocabulary.py --self-test
   python scripts/sync_test_plan_skill_copies.py --include-global
   python .codex/skills/test-plan-generation/scripts/test_skill_scripts.py   # must print ALL SELF-TESTS PASSED
   git add "*/test-plan-generation/data/guides_vocabulary.json" backend/config/aem_guides_crawl_urls.json
   git commit -m "chore(rag+skill): ingest <page-name>; grow vocabulary from RAG"
   git push
   ```
   Commit `guides_vocabulary.json` and the crawl config only (do not sweep unrelated
   working-tree changes). End `git commit` messages with:
   `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

6. REPORT: the ingested chunk count, the behaviour summary, the UI surfaces seen, the
   terms you added (and any you left out for human review), and the final commit hash.

Notes:
- The VM shared corpus is separate. After committing, on the VM run
  `git pull --ff-only && cd backend && python ../scripts/ingest_urls.py "<EXP_LEAGUE_URL>"`
  so the VM corpus matches. The VM's dataset-studio backend on :8001 must be reachable there.
- Non-negotiable: RAG DRIVES the terminology — never invent a term/behaviour for a
  concept the ingested doc documents.
