#!/usr/bin/env python3
"""Verify key services: vector store, doc retriever, crawl, Jira embedding, migrations."""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def main():
    errors = []
    print("=" * 60)
    print("Service Verification")
    print("=" * 60)

    # 1. Vector store service
    print("\n1. Vector store service...")
    try:
        from app.services.vector_store_service import is_chroma_available, get_collection_count
        avail = is_chroma_available()
        print(f"   ChromaDB available: {avail}")
        if avail:
            count = get_collection_count("aem_guides")
            print(f"   aem_guides collection count: {count}")
    except Exception as e:
        errors.append(f"Vector store: {e}")
        print(f"   ERROR: {e}")

    # 2. Doc retriever
    print("\n2. Doc retriever service...")
    try:
        from app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt
        docs = retrieve_relevant_docs("keyref resolution", k=2)
        print(f"   Retrieved {len(docs)} docs")
        if docs:
            print(f"   First doc keys: {list(docs[0].keys())}")
    except Exception as e:
        errors.append(f"Doc retriever: {e}")
        print(f"   ERROR: {e}")

    # 3. Crawl service (dry run - just import)
    print("\n3. Crawl service...")
    try:
        from app.services.crawl_service import crawl_and_index, DEFAULT_CRAWL_URLS
        print(f"   Crawl URLs: {len(DEFAULT_CRAWL_URLS)}")
    except Exception as e:
        errors.append(f"Crawl service: {e}")
        print(f"   ERROR: {e}")

    # 4. Jira index + embedding
    print("\n4. Jira index + embedding...")
    try:
        from app.db.session import SessionLocal
        from app.db.jira_models import JiraIssue
        from app.services.jira_index_service import _update_embedding_for_issue
        db = SessionLocal()
        try:
            issue = db.query(JiraIssue).first()
            if issue:
                has_emb = bool(getattr(issue, "embedding_json", None))
                print(f"   Sample issue: {issue.issue_key}, has embedding: {has_emb}")
            else:
                print("   No Jira issues in DB (OK)")
        finally:
            db.close()
    except Exception as e:
        errors.append(f"Jira embedding: {e}")
        print(f"   ERROR: {e}")

    # 5. Migrations
    print("\n5. Migrations...")
    try:
        from app.db.migrations import run_migrations
        run_migrations()
        print("   OK")
    except Exception as e:
        errors.append(f"Migrations: {e}")
        print(f"   ERROR: {e}")

    # 6. Evidence extractor
    print("\n6. Evidence extractor...")
    try:
        from app.utils.evidence_extractor import extract_evidence_context
        ctx = extract_evidence_context({"summary": "keyref test", "description": ""})
        assert "keyref" in ctx or "test" in ctx
        print("   OK")
    except Exception as e:
        errors.append(f"Evidence extractor: {e}")
        print(f"   ERROR: {e}")

    # 7. FastAPI app loads
    print("\n7. FastAPI app...")
    try:
        from app.main import app
        print(f"   App: {app.title}")
    except Exception as e:
        errors.append(f"FastAPI: {e}")
        print(f"   ERROR: {e}")

    print("\n" + "=" * 60)
    if errors:
        print(f"FAILED: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("PASSED: All services OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
