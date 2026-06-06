---
name: dita-training-data-optimizer
description: >
  Optimize DITA dataset generation parameters to produce the richest, most accurate
  training data possible. Use this skill when a user explicitly wants high-quality
  training data, mentions model fine-tuning, wants to maximize content realism, or
  asks how to get better output: "how do I get better DITA training data",
  "the generated topics are too generic", "titles are not domain-specific enough",
  "how to generate more realistic DITA content", "optimize my dataset generation",
  "improve training data quality", "the content feels templated not real",
  "how to make generated DITA look like real documentation", "best parameters
  for DITA training corpus", "generate diverse high-quality DITA examples",
  or any time the user wants to understand how to get maximum quality from the
  generation pipeline. Also use when reviewing a planned create_job call and
  the subject or prompt_text looks weak.
---

# DITA Training Data Quality Optimizer

This skill maximizes the quality of generated DITA training data by ensuring the
LLM authoring pipeline has enough signal to produce realistic, domain-accurate content.

---

## 1. The Quality Hierarchy

These levers affect output quality most to least:

| Rank | Lever | Effect on quality |
|---|---|---|
| 1 | `subject` specificity | Drives LLM title + body authoring |
| 2 | `prompt_text` content | Injects vocabulary and constraints |
| 3 | `recipe_type` match | Correct structure (task vs reference vs hierarchy) |
| 4 | `topic_count` / scale | More topics = more diversity |
| 5 | Config params | `depth`, `children_per_level` for structure variety |

**The single biggest quality mistake:** a vague `subject` like `"software documentation"` or `"Kubernetes"`.
The LLM authoring step only gets up to 60 authored nodes — if `subject` is vague, those nodes get
generic titles like "Introduction" and "Overview" instead of "Configuring a Kubernetes NetworkPolicy
for Namespace Isolation."

---

## 2. Subject Quality Checklist

Score the `subject` field. If it scores below 3, improve it before calling `create_job`.

| Check | Bad example | Good example |
|---|---|---|
| Names the domain | "documentation" | "Kubernetes" ✓ |
| Includes sub-areas (4–8) | "Kubernetes" | "Kubernetes: Services, Ingress, NetworkPolicy, DNS" ✓ |
| Uses domain-specific terms | "network features" | "NetworkPolicy, CNI, kube-proxy, CoreDNS" ✓ |
| Not longer than 200 chars | — | Stay under the 200-char cap ✓ |

**Improve weak subjects:**
- `"Docker"` → `"Docker: container lifecycle, networking (bridge/overlay/host), volumes, docker-compose, Dockerfile best practices, health checks"`
- `"AEM authoring"` → `"AEM Guides authoring: DITA maps, topicrefs, DITAVAL filters, native PDF presets, keydef management, cross-references"`
- `"API docs"` → `"REST API documentation: authentication (OAuth2/API key), endpoint design, request/response schemas, error handling, rate limiting, pagination"`

---

## 3. prompt_text Quality Checklist

The `prompt_text` feeds the LLM that authors the first N topic titles and bodies.
Rich `prompt_text` = rich content.

| What to include | Example |
|---|---|
| Specific sub-topics to cover | "Cover: pod affinity rules, node taints/tolerations, resource requests/limits, priority classes, preemption" |
| Key terms / commands / element names | "Key terms: kubectl, YAML manifest, nodeSelector, tolerations, topologyKey, PriorityClass" |
| Content style | "Task topics: each step should use a code block for the kubectl command" |
| Constraints | "Titles under 80 chars. No marketing language. Technical audience." |
| Domain-specific values | "Use realistic values: cpu: 500m, memory: 256Mi, priorityClassName: high-priority" |

**Weak:** `"Generate DITA about Kubernetes"`
**Strong:** `"Kubernetes operational procedures: configuring pod scheduling with nodeSelector and affinity rules, applying taints and tolerations, setting resource requests (cpu: 500m/memory: 256Mi) and limits, creating PriorityClass objects for QoS, debugging scheduling failures with kubectl describe pod. Steps use kubectl commands in fenced code blocks. Titles under 80 chars."`

---

## 4. Recipe + Scale Optimization

For training data (not just a sample), optimize scale:

| Goal | Recipe | Scale recommendation |
|---|---|---|
| Diverse task procedures | `task_topics` | 40–50 per job (max for quality) |
| Reference coverage | `reference_topics` | 30–40 per job |
| Conceptual variety | `concept_topics` | 25–35 per job |
| Tree structure diversity | `deep_hierarchy` | depth=4, children=4 (≈85 nodes) |
| Terminology richness | `glossary_pack` | 40–60 terms per job |
| Maximum flat diversity | `large_scale` or `flat_hierarchical_dita` | 50 per job, multiple jobs with different sub-domain subjects |

**For large training corpora (200+ topics):** use `dita-batch-planner` to chain jobs, giving each job a different subject slice of the domain so topics don't repeat across jobs.

---

## 5. Anti-patterns That Produce Poor Data

| Anti-pattern | Why it's bad | Fix |
|---|---|---|
| `subject = "software"` | Too vague — LLM generates generic titles | Name the specific product/technology |
| `subject` lists only 1-2 sub-areas | LLM runs out of domain-specific material quickly | Add 4–8 sub-areas |
| `prompt_text` repeats the subject verbatim | No new signal for the LLM | Add vocabulary, constraints, content type hints |
| `topic_count = 3` with a complex domain | Too few to cover the domain | Minimum 15 for meaningful diversity |
| `recipe_type = "freeform"` for large requests | Slow, inconsistent structure | Use a named recipe + good subject instead |
| Same subject across multiple jobs | Overlapping content, low diversity | Vary the subject slice per job |

---

## 6. Quality Review — Before Calling create_job

Run this checklist mentally before every generation:

```
subject check:
  [ ] Names specific technology/domain
  [ ] Lists 4-8 sub-areas
  [ ] Uses domain-specific terms (not generic words)
  [ ] Under 200 chars

prompt_text check:
  [ ] Adds vocabulary not already in subject
  [ ] Specifies content style (steps with code blocks, tables, etc.)
  [ ] Mentions key domain terms / commands / element names

recipe check:
  [ ] task for procedures, reference for tables, concept for explanations
  [ ] Not freeform unless truly mixed/advanced constructs are needed

scale check:
  [ ] topic_count is at least 15 for meaningful diversity
  [ ] topic_count ≤ 50 (hard cap)
  [ ] For large corpora: split into multiple jobs with varied subjects
```

---

## 7. Example: Transforming a Weak Call into a Strong One

**Weak (what users often type):**
```
create_job(
  recipe_type = "task_topics",
  subject     = "Kubernetes",
  prompt_text = "generate kubernetes documentation"
)
```
→ Produces: generic "Introduction to Kubernetes", "Getting Started", etc.

**Optimized:**
```
create_job(
  recipe_type = "task_topics",
  subject     = "Kubernetes operations: pod scheduling, service exposure, ConfigMap/Secret management, RBAC, namespace isolation",
  prompt_text = "Kubernetes cluster administration procedures: scheduling pods with nodeSelector and resource requests (cpu/memory), exposing deployments via ClusterIP/NodePort/LoadBalancer Services, managing configuration with ConfigMaps and Secrets (env/volume mounts), creating RBAC roles and RoleBindings, isolating workloads with namespaces and NetworkPolicies. Each step must include the kubectl command in a code block. Key terms: kubectl apply, -n namespace, --dry-run=client, labels, annotations.",
  config      = {"topic_count": 40}
)
```
→ Produces: "Configure a NetworkPolicy to Restrict Ingress Traffic", "Create a Secret from a Literal Value", "Bind a ClusterRole to a ServiceAccount", etc.
