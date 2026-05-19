"""
Run generate-from-text once with a rich natural-language prompt (intent pipeline + recipe execution).

Usage (from repo root or backend/):
  cd backend
  python scripts/example_complex_generate_from_text.py

Requires ANTHROPIC_API_KEY (or your configured LLM provider). Uses backend/.env when present.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

# Load .env before importing app services
_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

try:
    from dotenv import load_dotenv

    load_dotenv(_backend_root / ".env")
except ImportError:
    pass


COMPLEX_PROMPT = """
Issue Summary: AEM Guides editorial sample — root map with keys, reltable, and mixed topics

Description:
- Root map `products_guide.ditamap` with @id and a meaningful <title>.
- Key definitions for at least two product name keys used in topic bodies.
- Keyscope `acme` on a map branch for scoped keys or keyrefs where appropriate.
- Three authored topics: one concept, one task with <steps>, one reference with a small properties table or simpletable.
- Relationship table in the root map linking concept, task, and reference.
- Conref reuse: shared boilerplate (e.g. <note> caution) lives in a separate topic; the task pulls it via conref.
- DITA 1.3 only; every href/conref resolvable inside the bundle.

Scope: compact editorial bundle (about 6–12 XML files), not a performance or stress dataset.
""".strip()


async def main() -> None:
    from app.services.generate_from_text_service import run_generate_from_text

    run_id = str(uuid4())
    print(f"run_id={run_id}")
    print("Calling run_generate_from_text (may take 1–3 minutes)...")

    result = await run_generate_from_text(
        text=COMPLEX_PROMPT,
        instructions=(
            "Prefer deterministic recipes such as parent_child_maps_keys_conref_conkeyref_selfrefs, "
            "nested_keydef_map_map_topic, dita_conref_keyref_dataset_recipe, relationship_table, or conref_pack. "
            "Do not select stress-test or multi-thousand-line single-topic recipes. "
            "Root map must list all topics and include a reltable."
        ),
        bundle_contract=None,
        run_id=run_id,
        request=None,
        user_id=os.getenv("EXAMPLE_GEN_USER_ID", "example-cli-user"),
        tenant_id=os.getenv("EXAMPLE_GEN_TENANT_ID", "kone"),
        skip_rag_check=True,
    )

    print("\n--- Result ---")
    print("jira_id:", result.get("jira_id"))
    print("run_id:", result.get("run_id"))
    print(result.get("bundle_summary"))
    print("artifact_counts:", result.get("artifact_counts"))
    print("representative_files:", result.get("representative_files"))
    b = result.get("bundle") or {}
    print("zip_path:", b.get("zip_path"))
    print("bundle_dir:", b.get("bundle_dir"))
    print("download_url:", result.get("download_url"))
    draft = (result.get("llm_usage") or {}).get("draft_stage") or {}
    print("generation_path:", draft.get("path"), "| llm_draft_used:", draft.get("llm_draft_used"))
    dbg = result.get("generation_debug") or {}
    if dbg:
        print("generation_debug:", dbg.get("outcome"), dbg.get("trace_path"))
    print("build_validation:", result.get("build_validation"))


if __name__ == "__main__":
    asyncio.run(main())
