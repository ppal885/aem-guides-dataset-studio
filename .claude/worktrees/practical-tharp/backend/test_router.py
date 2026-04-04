#!/usr/bin/env python3
"""Test router imports."""
import traceback

try:
    from app.api.v1.router import api_router
    print("[OK] Router imported successfully")
    print(f"Included routes: {len(api_router.routes)}")
    
    # Check if limits route exists
    limits_routes = [r for r in api_router.routes if hasattr(r, 'path') and 'limit' in r.path.lower()]
    print(f"Limits routes found: {len(limits_routes)}")
    for r in limits_routes:
        print(f"  - {r.path} {r.methods}")
        
except Exception as e:
    print(f"[ERROR] Import failed: {e}")
    traceback.print_exc()
