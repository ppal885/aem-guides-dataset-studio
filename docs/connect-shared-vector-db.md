# Connect to the shared AEM Guides Vector DB (ChromaDB)

Shared vector database on the VM for RAG chunks (docs, past tickets, automation
feature-file chunks, etc.). It runs on the VM behind the existing Nginx port; the
Chroma `/api/v2` path is proxied to the Chroma server, restricted to the team
network.

> Fill these in from the VM owner:
> - `HOST` = `<vm-ip>` (e.g. `10.42.46.78`)
> - `PORT` = `4502`   ·   `SSL` = `False` (4502 is plain HTTP)
> - Embedding model = **`all-MiniLM-L6-v2`** (everyone must use this)

Note: the Chroma client validates its API path as an enum (`/api/v1` | `/api/v2`)
and rejects custom sub-paths, so we route the real `/api/v2` path in Nginx and
teammates connect with **no custom settings**.

---

## Part A — VM owner: one-time setup

Easiest: run the repo script (idempotent, sets up a systemd service + the Nginx
route + team-only allowlist):

```bash
cd ~/aem-guides-dataset-studio && git pull
sudo bash scripts/setup_shared_chroma.sh            # or: ALLOW_SUBNET=10.42.0.0/16 sudo bash scripts/setup_shared_chroma.sh
```

What it does: installs chromadb, runs it as a `chroma` systemd service bound to
`127.0.0.1:8000`, adds `location /api/v2/ { allow 127.0.0.1; allow <subnet>; deny all; proxy_pass http://127.0.0.1:8000; }`
to the live 4502 server block, reloads Nginx, and verifies the heartbeat.

Manage it: `systemctl status|restart chroma` · logs: `journalctl -u chroma -f`.

---

## Part B — Teammate: connect and store chunks (no repo, no settings)

```bash
pip install chromadb sentence-transformers
```

```python
import chromadb
from sentence_transformers import SentenceTransformer

client = chromadb.HttpClient(host="<HOST>", port=4502, ssl=False)   # no custom settings needed
model  = SentenceTransformer("all-MiniLM-L6-v2")
coll   = client.get_or_create_collection("automation_features", metadata={"hnsw:space": "cosine"})

texts     = ["<chunk 1>", "<chunk 2>"]
ids       = ["<content-hash-1>", "<content-hash-2>"]   # sha256 of the chunk -> idempotent, no dupes
metadatas = [{"file": "x.feature"}, {"file": "y.feature"}]
coll.upsert(ids=ids, documents=texts, metadatas=metadatas, embeddings=model.encode(texts).tolist())
print("stored", coll.count())
```

Verify:
```python
print(client.heartbeat())
hits = coll.query(query_embeddings=model.encode(["search text"]).tolist(), n_results=3)
print(hits["documents"])
```

### Rules (keep the shared DB clean)
- Same embedding model **`all-MiniLM-L6-v2`** (other models = incompatible vectors).
- Same agreed collection name (e.g. `automation_features`), not one per person.
- Content-hash `ids` so re-ingesting updates in place instead of duplicating.

### Security
4502 is plain HTTP with no token, so the `/api/v2` route is restricted to the team
subnet (`allow <subnet>; deny all;`). Keep it off the public internet.
