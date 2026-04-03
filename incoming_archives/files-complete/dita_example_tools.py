# ─────────────────────────────────────────────────────────────────────────────
# ADD THESE TWO TOOLS TO YOUR mcp_server.py
# These clone the DITAWriter GitHub repos and index them as RAG examples
# ─────────────────────────────────────────────────────────────────────────────

# Known DITAWriter repos — best public DITA examples available
DITA_EXAMPLE_REPOS = [
    {
        "url": "https://github.com/DITAWriter/pilot_training_mitchell_bomber",
        "name": "pilot_training_mitchell_bomber",
        "description": "Full DITA book — tasks, concepts, references, maps, reltables, conrefs",
    },
    {
        "url": "https://github.com/DITAWriter/dita_keys_examples",
        "name": "dita_keys_examples",
        "description": "Key definitions, keyrefs, keyscopes — exactly what AEM Guides needs",
    },
    {
        "url": "https://github.com/DITAWriter/dita_glossary_example",
        "name": "dita_glossary_example",
        "description": "Glossary entries, glossary maps, abbreviated-form usage",
    },
]

DITA_EXAMPLES_DIR = PROJECT_ROOT / "dita_examples" / "community"


@mcp.tool()
def clone_dita_example_repos() -> str:
    """
    Clone the DITAWriter GitHub repos as gold-standard DITA examples.
    These are expert-authored, spec-compliant DITA files covering:
    - pilot_training_mitchell_bomber: full book with tasks/concepts/refs/maps/reltables/conrefs
    - dita_keys_examples: keydefs, keyrefs, keyscopes (critical for AEM Guides)
    - dita_glossary_example: glossary entries, maps, abbreviated-form

    Clones to: dita_examples/community/ in your project root.
    Run once, then call index_dita_example_repos to index them.
    Requires git to be installed and internet access.
    """
    import subprocess

    DITA_EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for repo in DITA_EXAMPLE_REPOS:
        target = DITA_EXAMPLES_DIR / repo["name"]

        # If already cloned, pull latest instead
        if target.exists():
            try:
                result = subprocess.run(
                    ["git", "-C", str(target), "pull", "--depth=1"],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0:
                    results.append(f"✅ Updated: {repo['name']}")
                else:
                    results.append(f"⚠️ Update failed {repo['name']}: {result.stderr[:100]}")
            except Exception as e:
                results.append(f"⚠️ Pull failed {repo['name']}: {e}")
            continue

        # Fresh clone
        try:
            result = subprocess.run(
                ["git", "clone", "--depth=1", repo["url"], str(target)],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                # Count DITA files
                dita_count = len(list(target.rglob("*.dita"))) + len(list(target.rglob("*.ditamap")))
                results.append(f"✅ Cloned: {repo['name']} ({dita_count} DITA files) — {repo['description']}")
            else:
                results.append(f"❌ Clone failed {repo['name']}: {result.stderr[:200]}")
        except FileNotFoundError:
            return "❌ git not found. Install git: https://git-scm.com/download/win"
        except subprocess.TimeoutExpired:
            results.append(f"⏱️ Timeout cloning {repo['name']} — check internet connection")
        except Exception as e:
            results.append(f"❌ Error cloning {repo['name']}: {e}")

    summary = "\n".join(results)
    total_dita = sum(
        len(list((DITA_EXAMPLES_DIR / r["name"]).rglob("*.dita"))) +
        len(list((DITA_EXAMPLES_DIR / r["name"]).rglob("*.ditamap")))
        for r in DITA_EXAMPLE_REPOS
        if (DITA_EXAMPLES_DIR / r["name"]).exists()
    )

    return f"""
{summary}

Total DITA files available: {total_dita}
Location: {DITA_EXAMPLES_DIR}

Next step: run index_dita_example_repos to index these into ChromaDB.
"""


@mcp.tool()
def index_dita_example_repos(repo_name: str = "") -> str:
    """
    Index cloned DITAWriter DITA examples into ChromaDB collection 'dita_examples'.
    Must run clone_dita_example_repos first.

    repo_name: optional — index just one repo e.g. 'dita_keys_examples'
               Leave empty to index ALL cloned repos.

    After indexing, query_dita_examples will return real expert DITA patterns
    grounded in the same constructs as your Jira issues.
    """
    try:
        from backend.app.services.embedding_service import embed_texts_batched, embed_texts, is_embedding_available
        from backend.app.services.vector_store_service import (
            add_documents, delete_collection, is_chroma_available
        )

        if not DITA_EXAMPLES_DIR.exists():
            return "No repos cloned yet. Run clone_dita_example_repos first."

        # Decide which repos to index
        if repo_name:
            target_dirs = [DITA_EXAMPLES_DIR / repo_name]
            if not target_dirs[0].exists():
                available = [r["name"] for r in DITA_EXAMPLE_REPOS]
                return f"Repo '{repo_name}' not found. Available: {', '.join(available)}"
        else:
            target_dirs = [
                DITA_EXAMPLES_DIR / r["name"]
                for r in DITA_EXAMPLE_REPOS
                if (DITA_EXAMPLES_DIR / r["name"]).exists()
            ]

        if not target_dirs:
            return "No repos found. Run clone_dita_example_repos first."

        documents, metadatas, ids = [], [], []
        skipped = 0

        for repo_dir in target_dirs:
            repo = repo_dir.name
            dita_files = (
                list(repo_dir.rglob("*.dita")) +
                list(repo_dir.rglob("*.ditamap"))
            )

            for i, f in enumerate(dita_files):
                try:
                    content = f.read_text(encoding="utf-8", errors="replace").strip()
                except Exception:
                    skipped += 1
                    continue

                if not content or len(content) < 50:
                    skipped += 1
                    continue

                # Detect topic type from root element
                topic_type = "unknown"
                for t in ["task", "concept", "reference", "glossentry", "glossmap", "map", "bookmap"]:
                    if f"<{t}" in content[:300]:
                        topic_type = t
                        break

                # Detect key DITA constructs present in this file
                constructs = []
                for c in ["conref", "keyref", "keydef", "keyscope", "reltable",
                          "topicgroup", "mapref", "abbreviated-form", "glossterm"]:
                    if c in content:
                        constructs.append(c)

                documents.append(content[:8000])
                metadatas.append({
                    "filename": f.name,
                    "repo": repo,
                    "topic_type": topic_type,
                    "constructs": ",".join(constructs),  # searchable
                    "relative_path": str(f.relative_to(DITA_EXAMPLES_DIR)),
                    "source": "dita_expert_example",
                })
                ids.append(f"ditaex_{repo}_{i}")

        if not documents:
            return f"No readable DITA files found in {[d.name for d in target_dirs]}"

        # Embed in batches (these repos can have 100+ files)
        if not is_embedding_available():
            return f"Found {len(documents)} files but embedding model not available."

        if not is_chroma_available():
            return f"Found {len(documents)} files but ChromaDB not available."

        embeddings = (
            embed_texts_batched(documents)
            if len(documents) > 64
            else embed_texts(documents)
        )

        if embeddings is None:
            return "Embedding failed."

        # Full replace of the collection
        delete_collection("dita_examples")
        success = add_documents(
            "dita_examples",
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=[e.tolist() for e in embeddings],
        )

        if not success:
            return "ChromaDB add_documents failed."

        # Summary by repo
        repo_counts = {}
        for m in metadatas:
            repo_counts[m["repo"]] = repo_counts.get(m["repo"], 0) + 1

        repo_summary = "\n".join(f"  {r}: {c} files" for r, c in repo_counts.items())
        topic_counts = {}
        for m in metadatas:
            topic_counts[m["topic_type"]] = topic_counts.get(m["topic_type"], 0) + 1
        topic_summary = "\n".join(f"  {t}: {c}" for t, c in sorted(topic_counts.items()))

        return f"""
✅ DITA Examples Indexed Successfully:

By repo:
{repo_summary}

By topic type:
{topic_summary}

Total indexed: {len(documents)} files
Skipped:       {skipped} files (empty/unreadable)

Now use query_dita_examples in your generation prompts!
"""

    except Exception as e:
        return f"Error indexing DITA examples: {e}"


@mcp.tool()
def query_dita_examples(
    query: str,
    topic_type: str = "",
    construct: str = "",
    k: int = 3,
) -> str:
    """
    Search expert DITAWriter examples for patterns matching your query.
    Returns real DITA XML you can use as generation reference.

    query: e.g. 'task with multiple steps and conref'
    topic_type: filter by type — 'task', 'concept', 'reference', 'map', 'glossentry'
    construct: filter by DITA feature — 'keyref', 'conref', 'keyscope', 'reltable',
               'topicgroup', 'mapref', 'abbreviated-form'
    k: number of examples to return (default 3)

    Use this BEFORE generating DITA so Cursor has a real expert pattern to follow.
    """
    try:
        from backend.app.services.embedding_service import embed_query, is_embedding_available
        from backend.app.services.vector_store_service import query_collection, is_chroma_available

        if not is_chroma_available():
            return "ChromaDB not available."
        if not is_embedding_available():
            return "Embedding model not available."

        query_emb = embed_query(query)
        if query_emb is None:
            return "Embedding failed."

        # Build ChromaDB where filter
        where = None
        if topic_type and construct:
            where = {
                "$and": [
                    {"topic_type": {"$eq": topic_type}},
                    {"constructs": {"$contains": construct}},
                ]
            }
        elif topic_type:
            where = {"topic_type": {"$eq": topic_type}}
        elif construct:
            where = {"constructs": {"$contains": construct}}

        rows = query_collection(
            "dita_examples",
            query_embedding=query_emb.tolist(),
            k=k,
            where=where,
        )

        if not rows:
            msg = "No matching examples found."
            if topic_type or construct:
                msg += f" Try without filters (topic_type='{topic_type}', construct='{construct}')."
            msg += " Run clone_dita_example_repos + index_dita_example_repos first."
            return msg

        parts = []
        for i, row in enumerate(rows, 1):
            meta = row.get("metadata") or {}
            doc = row.get("document") or ""
            constructs_found = meta.get("constructs", "")
            parts.append(
                f"[{i}] {meta.get('filename')} "
                f"| type: {meta.get('topic_type')} "
                f"| repo: {meta.get('repo')}"
                f"{' | constructs: ' + constructs_found if constructs_found else ''}\n\n"
                f"{doc[:3000]}"
                f"{'...[truncated]' if len(doc) > 3000 else ''}"
            )

        return "\n\n{'─'*60}\n\n".join(parts)

    except Exception as e:
        return f"Error querying DITA examples: {e}"


@mcp.tool()
def list_dita_example_repos() -> str:
    """
    List all cloned DITAWriter repos and their DITA file counts.
    Shows what's available for indexing and querying.
    """
    if not DITA_EXAMPLES_DIR.exists():
        return "No repos cloned yet. Run clone_dita_example_repos first."

    lines = []
    total = 0
    for repo in DITA_EXAMPLE_REPOS:
        repo_dir = DITA_EXAMPLES_DIR / repo["name"]
        if not repo_dir.exists():
            lines.append(f"❌ {repo['name']} — not cloned yet")
            continue

        dita_files = list(repo_dir.rglob("*.dita"))
        map_files = list(repo_dir.rglob("*.ditamap"))
        total += len(dita_files) + len(map_files)

        # Count by type
        types = {}
        for f in dita_files:
            content = ""
            try:
                content = f.read_text(encoding="utf-8", errors="replace")[:300]
            except Exception:
                pass
            for t in ["task", "concept", "reference", "glossentry"]:
                if f"<{t}" in content:
                    types[t] = types.get(t, 0) + 1
                    break

        type_str = ", ".join(f"{t}:{c}" for t, c in types.items())
        lines.append(
            f"✅ {repo['name']}\n"
            f"   {repo['description']}\n"
            f"   Files: {len(dita_files)} .dita, {len(map_files)} .ditamap\n"
            f"   Types: {type_str or 'mixed'}"
        )

    return f"""
DITAWriter Example Repos:
{'─' * 50}
{chr(10).join(lines)}
{'─' * 50}
Total DITA files: {total}
Location: {DITA_EXAMPLES_DIR}
"""
