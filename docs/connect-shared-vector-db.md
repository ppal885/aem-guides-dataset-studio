# Connect to the shared AEM Guides Vector DB (ChromaDB)

This is the shared vector database on the VM where we store RAG chunks (docs, past
tickets, automation feature-file chunks, etc.). Follow the part that applies to you.

> Connection details (ask the VM owner and fill these in):
>
> - `HOST` = `<vm-host-or-ip>`
> - `PORT` = `4503`
> - `TOKEN` = `<auth-token>`
> - Embedding model = **`all-MiniLM-L6-v2`** (everyone must use this — do not change it)

---

## Part A — VM owner: one-time server setup

Run ChromaDB in server mode, bound to localhost, and expose it through the existing
Nginx (a dedicated port, not a sub-path on 4502).

1. Install and run Chroma (localhost only) with a token:

   ```bash
   pip install chromadb
   CHROMA_SERVER_AUTHN_CREDENTIALS="<auth-token>" \
   CHROMA_SERVER_AUTHN_PROVIDER="chromadb.auth.token_authn.TokenAuthenticationServerProvider" \
   chroma run --host 127.0.0.1 --port 8000 --path /path/to/backend/storage/chroma_db
   ```

   (Tip: run it under systemd or `nohup`/screen so it stays up.)

2. Add an Nginx server block that proxies a dedicated port to Chroma (keep your
   existing 4502 → AEM block as-is):

   ```nginx
   server {
       listen 4503 ssl;
       server_name <vm-host>;
       # ssl_certificate ... ; ssl_certificate_key ... ;
       client_max_body_size 50m;
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_read_timeout 300s;
       }
   }
   ```

   Reload Nginx. Restrict port 4503 to the team/corp network (not public internet).

3. Share `HOST`, `PORT` (4503), and `TOKEN` with the team.

---

## Part B — Teammate: connect and store chunks (no repo needed)

You do **not** need to clone any repo or create a `.env`. Just install two packages
and point your own ingestion code at the VM.

1. Install:

   ```bash
   pip install chromadb sentence-transformers
   ```

2. In your ingestion script, connect and upsert:

   ```python
   import chromadb
   from chromadb.config import Settings
   from sentence_transformers import SentenceTransformer

   # --- connection (fill in from the VM owner) ---
   client = chromadb.HttpClient(
       host="<HOST>", port=4503, ssl=True,
       settings=Settings(
           chroma_client_auth_provider="chromadb.auth.token_authn.TokenAuthClientProvider",
           chroma_client_auth_credentials="<TOKEN>",
       ),
   )

   # --- must match everyone: same model, same collection name ---
   model = SentenceTransformer("all-MiniLM-L6-v2")
   coll = client.get_or_create_collection("automation_features", metadata={"hnsw:space": "cosine"})

   # --- your chunks ---
   texts = ["<chunk text 1>", "<chunk text 2>"]
   ids = ["<stable-id-1>", "<stable-id-2>"]           # use a content hash so re-runs don't duplicate
   metadatas = [{"file": "x.feature"}, {"file": "y.feature"}]

   coll.upsert(ids=ids, documents=texts,
               metadatas=metadatas,
               embeddings=model.encode(texts).tolist())
   print("stored", len(ids), "chunks")
   ```

3. Verify it worked:

   ```python
   print(coll.count())
   hits = coll.query(query_embeddings=model.encode(["your search text"]).tolist(), n_results=3)
   print(hits["documents"])
   ```

### Rules (so the shared DB stays clean)

- Use the **same embedding model** `all-MiniLM-L6-v2` — other models produce
  incompatible vectors and break search for everyone.
- Use the **agreed collection name** (e.g. `automation_features`) — don't invent
  your own per person.
- Use a **content-hash id** (e.g. `sha256` of the chunk text) so re-ingesting the
  same file updates in place instead of creating duplicates.

### Security

The DB is write-able, so treat the token like a password, keep port 4503 off the
public internet, and never commit the token to Git.
