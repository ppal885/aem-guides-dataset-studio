#!/usr/bin/env python3
"""
Create a zip file with cyclic conref dependency content for testing.

Generates the conrefend_cyclic_duplicate_id dataset (Topic A <-> Topic B conref cycle)
and packages it as a zip in the project root.
"""
import os
import sys
import zipfile
import tempfile
from pathlib import Path

# Add backend to path for imports
backend = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend))

from app.jobs.schemas import DatasetConfig
from app.generator.map_cyclic import generate_map_cyclic


def main():
    config = DatasetConfig(name="map_cyclic", recipes=[])
    base = "."
    files = generate_map_cyclic(config, base, id_prefix="t", pretty_print=True)

    out_dir = Path(tempfile.mkdtemp(prefix="map_cyclic_"))
    try:
        for rel_path, content in files.items():
            path = out_dir / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        zip_path = Path(__file__).resolve().parent.parent.parent / "map_cyclic_test.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in out_dir.rglob("*"):
                if f.is_file():
                    arcname = f.relative_to(out_dir)
                    zf.write(f, arcname)

        print(f"Created: {zip_path}")
        print("Contents: topics (topic_a.dita, topic_b.dita), maps (map_a.ditamap, map_b.ditamap), README.txt")
    finally:
        import shutil
        shutil.rmtree(out_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
