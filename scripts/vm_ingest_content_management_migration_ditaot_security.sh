#!/usr/bin/env bash
# Run the validated 11-document ingestion against the existing VM corpus.
set -euo pipefail

repo_dir="${AEM_GUIDES_DATASET_STUDIO_DIR:-$HOME/aem-guides-dataset-studio}"
backend_dir="$repo_dir/backend"

if [[ ! -d "$backend_dir" ]]; then
  echo "Backend directory not found: $backend_dir" >&2
  exit 2
fi

cd "$backend_dir"

python_bin=".venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  python_bin="python3"
fi

"$python_bin" ingest_content_management_migration_ditaot_security.py --activate
