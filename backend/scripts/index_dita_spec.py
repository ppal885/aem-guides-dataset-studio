"""CLI script to index DITA spec from OASIS or load seed."""
import argparse
import json
import sys
from pathlib import Path

# Ensure app is importable
backend = Path(__file__).resolve().parent.parent
if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))

from app.db.session import SessionLocal
from app.services.dita_spec_index_service import index_oasis_spec, load_seed_into_db


def main():
    parser = argparse.ArgumentParser(description="Index DITA spec for RAG")
    parser.add_argument("--urls", help="JSON file with list of URLs to fetch")
    parser.add_argument("--seed-only", action="store_true", help="Load seed corpus only, skip OASIS fetch")
    args = parser.parse_args()

    urls = None
    if args.urls:
        with open(args.urls, encoding="utf-8") as f:
            urls = json.load(f)

    session = SessionLocal()
    try:
        if args.seed_only:
            result = load_seed_into_db(session)
            print(f"Loaded {result['indexed']} chunks from seed")
        else:
            try:
                result = index_oasis_spec(session, urls)
                print(f"Indexed {result['indexed']} chunks from {result['urls_processed']} URLs")
                if result.get("errors"):
                    print("Errors:", result["errors"])
                    print("Falling back to seed...")
                    session.rollback()
                    result = load_seed_into_db(session)
                    print(f"Loaded {result['indexed']} chunks from seed")
            except Exception as e:
                print(f"OASIS fetch failed: {e}. Loading seed...")
                session.rollback()
                result = load_seed_into_db(session)
                print(f"Loaded {result['indexed']} chunks from seed")
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
