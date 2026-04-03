#!/usr/bin/env python3
"""Test script to verify all imports work correctly."""

import sys
import traceback

def test_imports():
    """Test all critical imports."""
    print("Testing imports...")
    
    # Test 1: Basic session import
    try:
        from app.db.session import Session, db_session
        print("[OK] Successfully imported Session and db_session from app.db.session")
        print(f"   db_session type: {type(db_session)}")
        print(f"   db_session: {db_session}")
    except ImportError as e:
        print(f"[FAIL] Failed to import from app.db.session: {e}")
        traceback.print_exc()
        return False
    
    # Test 2: Import through __init__
    try:
        from app.db import Session, db_session
        print("[OK] Successfully imported Session and db_session from app.db")
    except ImportError as e:
        print(f"[FAIL] Failed to import from app.db: {e}")
        traceback.print_exc()
        return False
    
    # Test 3: Import schedule route (the one that's failing)
    try:
        from app.api.v1.routes import schedule
        print("[OK] Successfully imported schedule route")
    except ImportError as e:
        print(f"[FAIL] Failed to import schedule route: {e}")
        traceback.print_exc()
        return False
    
    # Test 4: Import router (which imports all routes)
    try:
        from app.api.v1.router import api_router
        print("[OK] Successfully imported api_router")
    except ImportError as e:
        print(f"[FAIL] Failed to import api_router: {e}")
        traceback.print_exc()
        return False
    
    # Test 5: Try to import main (if it exists)
    try:
        from app import main
        print("[OK] Successfully imported main")
    except ImportError as e:
        print(f"[WARN] Could not import main (this is OK if main.py doesn't exist): {e}")
    
    print("\n[SUCCESS] All critical imports successful!")
    return True

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
