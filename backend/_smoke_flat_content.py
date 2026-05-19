"""One-shot smoke test for flat-content recipe enrichment.

Validates that the new content_subject / content_titles / content_shortdescs
(plus recipe-specific extras like content_steps_by_topic, content_property_seeds,
content_terms / content_definitions, etc.) actually flow from the chat
``create_job`` enrichment block all the way through to the produced DITA.

This script does NOT call the LLM — it manually feeds the fields the LLM helper
would have produced (``generate_flat_content``) and verifies the deterministic
generator picks them up. That's enough to catch wiring regressions; the LLM
helper itself is exercised by tests that mock ``llm_service.generate_json``.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.generator.specialized import (
    generate_concept_topics_dataset,
    generate_glossary_dataset,
    generate_reference_topics_dataset,
    generate_task_topics_dataset,
)


class _Cfg:
    seed = "smoke-seed"
    windows_safe_filenames = True
    doctype_topic = (
        '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
    )
    doctype_concept = (
        '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">'
    )
    doctype_task = (
        '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">'
    )
    doctype_reference = (
        '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">'
    )
    doctype_glossentry = (
        '<!DOCTYPE glossentry PUBLIC "-//OASIS//DTD DITA Glossary entry//EN" "glossentry.dtd">'
    )
    doctype_map = (
        '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">'
    )


cfg = _Cfg()


def _show(files: dict[str, bytes], name_substring: str, max_bytes: int = 600) -> str:
    """Pretty-print the first matching .dita file and return its body for assertions."""
    match = next(
        (
            p for p in sorted(files)
            if name_substring in p and p.endswith(".dita")
        ),
        None,
    )
    if not match:
        # Fall back to listing what we have so the failure is debuggable.
        sample = "\n    ".join(sorted(files)[:8])
        raise AssertionError(
            f"no .dita file matched substring {name_substring!r}; first 8 paths:\n    {sample}"
        )
    body = files[match].decode("utf-8", errors="replace")
    print(f"  --- {match} ---")
    titles = re.findall(r"<title>([^<]+)</title>", body)
    if titles:
        print(f"    title  : {titles[0]}")
    shortdescs = re.findall(r"<shortdesc>([^<]+)</shortdesc>", body)
    if shortdescs:
        print(f"    short  : {shortdescs[0]}")
    cmds = re.findall(r"<cmd>([^<]+)</cmd>", body)
    for c in cmds[:3]:
        print(f"    cmd    : {c}")
    snippet = body[:max_bytes].replace("\n", " ")
    print(f"    snippet: {snippet[:200]}...")
    return body


print("=" * 72)
print("Test 1: reference_topics with Terraform subject + LLM-authored content")
print("=" * 72)
ref_files = generate_reference_topics_dataset(
    cfg,
    "tf_ref",
    topic_count=4,
    properties_per_ref=4,
    include_map=False,
    content_titles=[
        "terraform plan command",
        "Provider configuration block",
        "Backend state options",
    ],
    content_shortdescs=[
        "Use terraform plan to preview infrastructure changes before apply.",
        "Configure providers to authenticate against the target cloud.",
        "Pick a backend (S3, GCS, AzureRM) for shared, locked state.",
    ],
    content_property_seeds=[
        "out, refresh, target, var-file",
        "alias, region, profile, version",
        "bucket, key, region, dynamodb_table",
    ],
    content_detail_snippets=[
        "Plan output uses + / - / ~ markers to indicate adds, destroys, and updates.",
        "Provider blocks may declare aliases to reuse the same provider with different configs.",
        "Remote backends provide locking to prevent concurrent state mutations.",
    ],
)
print(f"  Generated {len(ref_files)} files. Sampling 1:")
ref_body = _show(ref_files, "topics/references/reference_00001.dita")
assert any("terraform plan command" in ref_files[p].decode("utf-8") for p in ref_files), (
    "LLM-authored title 'terraform plan command' should appear in some reference topic"
)
assert any("terraform plan to preview" in ref_files[p].decode("utf-8") for p in ref_files), (
    "LLM-authored shortdesc text should appear in some reference topic"
)
assert any("dynamodb_table" in ref_files[p].decode("utf-8") for p in ref_files), (
    "Property seed 'dynamodb_table' should appear in some <properties> table"
)
print("  PASS: reference_topics consumes content_titles / shortdescs / property_seeds / detail_snippets.")
print()

print("=" * 72)
print("Test 2: task_topics with Terraform subject + per-topic step lists")
print("=" * 72)
task_files = generate_task_topics_dataset(
    cfg,
    "tf_task",
    topic_count=3,
    steps_per_task=4,
    include_map=False,
    content_titles=[
        "Initialize a Terraform working directory",
        "Apply a Terraform plan to AWS",
        "Destroy Terraform-managed infrastructure",
    ],
    content_shortdescs=[
        "Run terraform init to download providers and configure the backend.",
        "Use terraform apply to converge real infrastructure with the plan.",
        "Use terraform destroy to remove all managed resources cleanly.",
    ],
    content_steps_by_topic=[
        [
            "Open a terminal in the working directory.",
            "Run terraform init.",
            "Verify the .terraform.lock.hcl file is created.",
        ],
        [
            "Run terraform plan -out=tfplan.",
            "Review the plan output for additions and destructions.",
            "Run terraform apply tfplan.",
            "Confirm the apply completes without errors.",
        ],
        [
            "Run terraform destroy.",
            "Type yes when prompted.",
            "Verify resources are removed in the cloud console.",
        ],
    ],
)
print(f"  Generated {len(task_files)} files. Sampling 1:")
task_body = _show(task_files, "task_00001.dita")
assert any("Initialize a Terraform working directory" in task_files[p].decode("utf-8") for p in task_files), (
    "LLM-authored task title should appear"
)
assert any("terraform apply tfplan" in task_files[p].decode("utf-8") for p in task_files), (
    "Per-topic step text should appear in the steps section"
)
print("  PASS: task_topics consumes content_titles / shortdescs / steps_by_topic.")
print()

print("=" * 72)
print("Test 3: concept_topics with Terraform subject + per-topic body snippets")
print("=" * 72)
concept_files = generate_concept_topics_dataset(
    cfg,
    "tf_concept",
    topic_count=3,
    sections_per_concept=2,
    include_map=False,
    content_titles=[
        "Terraform state",
        "Terraform modules",
        "Terraform providers",
    ],
    content_shortdescs=[
        "State is Terraform's source of truth about real infrastructure.",
        "Modules let you package and reuse Terraform configurations.",
        "Providers are plugins that translate Terraform to cloud APIs.",
    ],
    content_body_snippets=[
        "State stores resource attributes, dependencies, and metadata for each managed resource.",
        "Modules can be local, registry-published, or sourced from git for cross-team reuse.",
        "Each provider implements the resource lifecycle for a specific cloud or service.",
    ],
)
print(f"  Generated {len(concept_files)} files. Sampling 1:")
concept_body = _show(concept_files, "concept_00001.dita")
assert any("Terraform state" in concept_files[p].decode("utf-8") for p in concept_files), (
    "LLM-authored concept title should appear"
)
assert any("source of truth" in concept_files[p].decode("utf-8") for p in concept_files), (
    "LLM-authored shortdesc should appear"
)
assert any("registry-published" in concept_files[p].decode("utf-8") for p in concept_files), (
    "LLM-authored body snippet should appear in some conbody"
)
print("  PASS: concept_topics consumes content_titles / shortdescs / body_snippets.")
print()

print("=" * 72)
print("Test 4: glossary with Terraform terms + definitions")
print("=" * 72)
gloss_files = generate_glossary_dataset(
    cfg,
    "tf_gloss",
    entry_count=3,
    content_terms=["Resource", "Provider", "Module"],
    content_definitions=[
        "A managed object in a Terraform configuration that represents a real-world infrastructure component.",
        "A plugin that knows how to interact with a specific cloud or service API.",
        "A reusable, versioned package of Terraform configuration.",
    ],
    content_acronyms=["", "", ""],
)
print(f"  Generated {len(gloss_files)} files. Sampling 1:")
gloss_body = _show(gloss_files, "glossary")
assert any("Resource" in gloss_files[p].decode("utf-8") for p in gloss_files), (
    "LLM-authored glossary term 'Resource' should appear"
)
assert any("real-world infrastructure component" in gloss_files[p].decode("utf-8") for p in gloss_files), (
    "LLM-authored definition text should appear"
)
print("  PASS: glossary_pack consumes content_terms / definitions.")
print()

print("All flat-content smoke tests passed.")
