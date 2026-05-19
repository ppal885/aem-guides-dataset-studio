"""One-shot smoke test for subject-aware hierarchy generators.

Validates that the new content_subject / content_titles / content_bodies
fields actually flow through to the produced DITA, and that unfilled slots
fall back to subject-templated text instead of the old "Generated Topic 00001"
placeholder.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.generator.flat_hierarchical_dita import generate_flat_hierarchical_dita
from app.generator.performance_scale import (
    PerformanceMetrics,
    ScalabilityGenerator,
)


class _Cfg:
    seed = "smoke-seed"
    windows_safe_filenames = True
    doctype_topic = (
        '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
    )
    doctype_map = (
        '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">'
    )


cfg = _Cfg()

print("=" * 72)
print("Test 1: flat_hierarchical_dita with subject + 3 LLM-authored titles, 5 total topics")
print("=" * 72)
files = generate_flat_hierarchical_dita(
    cfg,
    "k8s",
    topic_count=5,
    topics_per_section=2,
    content_subject="Kubernetes",
    content_titles=[
        "Kubernetes overview",
        "Pods deep dive",
        "Deployments and ReplicaSets",
    ],
    content_bodies=[
        "Kubernetes orchestrates containers across a cluster.",
        "A Pod is the smallest deployable unit in Kubernetes.",
        "A Deployment manages a ReplicaSet that keeps Pods at a desired replica count.",
    ],
)
print(f"  Generated {len(files)} files. Sampling 3:")
for needle in ("topic_00001.dita", "topic_00004.dita", "rootmap_5.ditamap"):
    match = next((p for p in sorted(files) if p.endswith(needle) and "/flat_" in p), None)
    if not match:
        continue
    body = files[match].decode("utf-8")
    print(f"  --- {match} ---")
    titles = re.findall(r"<title>([^<]+)</title>", body)
    paras = re.findall(r"<p>([^<]+)</p>", body)
    refs = re.findall(r'<topicref [^/]*navtitle="([^"]+)"', body)
    for t in titles[:1]:
        print(f"    title: {t}")
    for p in paras[:1]:
        print(f"    body : {p}")
    for r in refs[:3]:
        print(f"    nav  : {r}")

assert any("Kubernetes overview" in files[p].decode("utf-8") for p in files), \
    "LLM-authored title 'Kubernetes overview' should appear in some file"
assert any("Kubernetes \u2014 Topic 00004" in files[p].decode("utf-8") for p in files), \
    "Subject-templated fallback 'Kubernetes — Topic 00004' should appear for unfilled slot"
assert not any(
    "Generated Topic 00004" in files[p].decode("utf-8") for p in files
), "Old 'Generated Topic 00004' placeholder must NOT appear when subject is set"
print("  PASS: titles and bodies are subject-aware; fallback themed by subject.")

print()
print("=" * 72)
print("Test 2: deep_hierarchy with subject + 4 LLM-authored titles, depth=2 children=2")
print("=" * 72)
import random as _random
gen = ScalabilityGenerator(cfg, _random.Random(cfg.seed), PerformanceMetrics())
deep_files = gen.generate_deep_hierarchy_dataset(
    base="k8s_deep",
    depth=2,
    children_per_level=2,
    include_maps=True,
    content_subject="Kubernetes",
    content_titles=[
        "Kubernetes platform overview",
        "Workload primitives",
        "Cluster networking",
    ],
    content_bodies=[
        "Kubernetes is a platform for running containerized workloads at scale.",
        "Pods, Deployments, Jobs, and StatefulSets are the workload primitives.",
        "Services, Ingresses, and NetworkPolicies define cluster-internal traffic.",
    ],
)
print(f"  Generated {len(deep_files)} files. Sampling 3:")
for needle in (
    "topic_l0_00000.dita",  # root: should get 'Kubernetes platform overview'
    "topic_l1_00000.dita",  # first L1 child: 'Workload primitives'
    "topic_l2_00000.dita",  # first L2 grandchild: subject-templated fallback
):
    match = next((p for p in sorted(deep_files) if p.endswith(needle)), None)
    if not match:
        continue
    body = deep_files[match].decode("utf-8")
    print(f"  --- {match} ---")
    titles = re.findall(r"<title>([^<]+)</title>", body)
    paras = re.findall(r"<p>([^<]+)</p>", body)
    for t in titles[:1]:
        print(f"    title: {t}")
    for p in paras[:1]:
        print(f"    body : {p}")

l0 = next(p for p in deep_files if p.endswith("topic_l0_00000.dita"))
l2 = next(p for p in deep_files if p.endswith("topic_l2_00000.dita"))
assert "Kubernetes platform overview" in deep_files[l0].decode("utf-8"), \
    "Root (flat_idx=0) should use the first LLM-authored title"
fallback_xml = deep_files[l2].decode("utf-8")
fallback_title = re.findall(r"<title>([^<]+)</title>", fallback_xml)[0]
assert fallback_title.startswith("Kubernetes"), \
    f"Deeper unfilled node title must be themed by subject; got {fallback_title!r}"
assert "covers one slice of the Kubernetes domain" in fallback_xml, \
    "Deeper unfilled node body must be themed by subject"
print("  PASS: deep_hierarchy honors subject + uses subject-templated fallback for unfilled depth.")

print()
print("All smoke tests passed.")
