---
name: dita-large-scale-generation
description: >
  Generate large-scale DITA datasets at 100, 1000, or 10000+ topic scale for performance
  testing, stress testing, model fine-tuning, or enterprise content pipelines. Use this
  skill whenever the user asks for bulk/large/massive dataset generation: "generate 1000
  DITA topics", "create a 10k topic dataset", "bulk generate for performance testing",
  "stress test dataset", "large-scale training corpus", "generate 500 task topics",
  "need 10000 DITA files", "performance benchmark dataset", "enterprise-scale content",
  "generate as many topics as possible", or any time the requested topic count is >= 100.
  This skill handles scale constraints, batching strategy, recipe selection for each scale
  tier, and subject variation to avoid duplicate content across jobs.
---

# Large-Scale DITA Dataset Generation

Generating 100–10,000+ DITA topics requires batching multiple `create_job` calls with
varied subjects. Each job has a hard cap of 50 topics. This skill handles the math,
recipe selection, and subject variation strategy automatically.

---

## 1. Scale Tiers & Strategy

| Scale | Topics | Jobs needed | Approach |
|---|---|---|---|
| **Small** | 50–100 | 1–2 | Single recipe, one subject |
| **Medium** | 100–500 | 3–10 | Single recipe type, varied subject slices |
| **Large** | 500–2000 | 10–40 | Multiple recipe types, domain sub-areas |
| **Stress** | 2000–10000 | 40–200 | `large_scale` recipe + batches |
| **Extreme** | 10000+ | 200+ | `large_scale` batches + async execution |

**Hard cap:** Each `create_job` allows max `topic_count = 50` (enforced by PARAM_CAPS).
For `large_scale` recipe: min `topic_count = 50`, max = unlimited.

---

## 2. Recipe Selection by Scale

| Scale | Best recipe | Config |
|---|---|---|
| 50–200 | `task_topics` or `concept_topics` | `topic_count: 50` per job |
| 200–1000 | `flat_hierarchical_dita` | `topic_count: 50` per job |
| 1000–10000 | `large_scale` | `topic_count: 500–1000` per job |
| 10000+ | `large_scale` | `topic_count: 1000` per job, many batches |

`large_scale` is the only recipe designed for high-volume output — it disables formatting,
skips map generation, and uses batch processing. Use it for any corpus > 500 topics.

---

## 3. Subject Variation Strategy (critical for quality)

Never repeat the same subject across jobs — this produces duplicate content.
Divide the domain into sub-areas, one per job:

**Example: 1000 Kubernetes topics (20 jobs × 50 topics)**
```
Job 1:  subject="Kubernetes Pods: creation, lifecycle, restart policies, init containers"
Job 2:  subject="Kubernetes Services: ClusterIP, NodePort, LoadBalancer, ExternalName"
Job 3:  subject="Kubernetes Deployments: rolling updates, rollback, scaling, replicas"
Job 4:  subject="Kubernetes ConfigMaps and Secrets: creation, mounting, env vars"
Job 5:  subject="Kubernetes Networking: NetworkPolicy, CNI, DNS, kube-proxy"
Job 6:  subject="Kubernetes Storage: PersistentVolumes, StorageClass, StatefulSets"
Job 7:  subject="Kubernetes RBAC: Roles, ClusterRoles, ServiceAccounts, Bindings"
Job 8:  subject="Kubernetes Ingress: nginx, traefik, TLS, path routing"
Job 9:  subject="Kubernetes Monitoring: Prometheus, metrics-server, alerts, dashboards"
Job 10: subject="Kubernetes Troubleshooting: pod failures, OOMKilled, CrashLoopBackOff"
... (repeat pattern for remaining 10 jobs with advanced topics)
```

**Rule of thumb:** 1 sub-area per 50 topics. For `large_scale` jobs with 500+ topics,
list 8–10 sub-areas per job to keep content varied.

---

## 4. Build the Job Sequence

Always confirm the plan before executing ANY jobs:

```
Here is the generation plan for [N] [recipe_type] topics about [domain]:

Job batch: [total_jobs] jobs × [topics_per_job] topics = [total] topics

| Job | Subject slice | topic_count |
|---|---|---|
| 1  | [sub-area 1] | 50 |
| 2  | [sub-area 2] | 50 |
...

Estimated time: ~[N] minutes
Shall I start? I will launch jobs one at a time and wait for each to complete.
```

Then run jobs **sequentially** (not all at once) — each needs the user's approval.

---

## 5. create_job Call Template

```python
# For flat/task/concept at medium scale
create_job(
  recipe_type = "task_topics",         # or concept_topics, flat_hierarchical_dita
  subject     = "[domain: sub-area1, sub-area2, sub-area3]",
  prompt_text = "[domain vocabulary + element requirements]",
  config      = {"topic_count": 50, "include_map": True}
)

# For large_scale (500+ topics per job)
create_job(
  recipe_type = "large_scale",
  subject     = "[domain covering multiple sub-areas for variety]",
  prompt_text = "[domain terms, key concepts, title style guidance]",
  config      = {"topic_count": 500, "batch_size": 100}
)
```

---

## 6. Performance Notes

| Recipe | Topics/job | Generation time | File size |
|---|---|---|---|
| `task_topics` | 50 | ~30s | Small |
| `flat_hierarchical_dita` | 50 | ~30s | Small |
| `large_scale` | 500 | ~2 min | Large (no formatting) |
| `large_scale` | 1000 | ~4 min | Very large |

For `large_scale`: files are plain XML without pretty-printing. Good for training data,
not for human review. Set `include_map: False` to skip the map (too large to be useful).

---

## 7. Example: 1000 Task Topics for Kubernetes

User says: *"I need 1000 task topics about Kubernetes for our training corpus."*

```
Plan: 20 jobs × 50 topics = 1000 task_topics
Recipe: task_topics (40 jobs) + flat_hierarchical_dita (covers more variety)

I'll divide Kubernetes into 20 sub-domains, one job each.
Estimated time: ~10 minutes total.

Shall I start with Job 1?
```

**Job 1:**
```python
create_job(recipe_type="task_topics", config={"topic_count":50},
  subject="Kubernetes Pods: creation, lifecycle, scheduling, init containers, sidecars",
  prompt_text="Kubernetes pod management tasks: kubectl run, apply, delete, describe. Steps use codeblock for kubectl commands. Key terms: pod spec, container, restartPolicy, namespace."
)
```

**After approval**, move to Job 2, etc.

---

## 8. Example: 10,000 Topics (Stress/Benchmark)

User says: *"I need 10,000 DITA topics for performance benchmarking."*

```
Plan: 20 jobs × 500 topics = 10,000 topics using large_scale recipe.
Total estimated time: ~40 minutes.
Files will be plain XML (no pretty-print) optimized for bulk processing.
```

**Each job:**
```python
create_job(recipe_type="large_scale", config={"topic_count":500, "include_map":False},
  subject="[domain sub-area covering 500 distinct topic titles]",
  prompt_text="[domain vocabulary for title variation]"
)
```
