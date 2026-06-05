---
name: dita-batch-planner
description: >
  Plan and execute large DITA dataset generation that requires multiple chained jobs —
  when a single create_job isn't enough. Use this skill whenever the user wants a COMPLETE
  content architecture for a domain: "generate a full DITA content set for X", "create
  everything I need for Y documentation", "build a complete dataset covering A, B, and C",
  "I need task topics AND reference topics AND a glossary for X", "generate 200+ topics
  about Y", "create a full training dataset for Z", "build a comprehensive DITA package".
  Also triggers when the user wants mixed recipe types together (e.g. hierarchy + flat topics +
  glossary), or when the requested topic count exceeds the 50-topic per-job cap. Always plan
  before executing — show the job breakdown and get confirmation before launching anything.
---

# DITA Batch Dataset Planner

This skill orchestrates multi-job DITA generation: it analyzes the user's domain and intent,
designs a job plan covering all the content types needed, and executes the jobs in sequence
after the user confirms.

---

## 1. Why Multiple Jobs?

Single `create_job` caps:
- `topic_count` ≤ 50 per job
- One recipe type per job (hierarchy OR tasks OR glossary, not all at once)

A "complete dataset" for a domain typically needs 3–5 complementary recipe types.

---

## 2. Analyze the Request

Extract from the user's message:

| Signal | What to capture |
|---|---|
| **Domain** | "Kubernetes", "AEM Guides authoring", "Terraform AWS" |
| **Scale hint** | "comprehensive", "full coverage", "200+ topics" |
| **Content types mentioned** | "tasks and reference tables", "hierarchy plus glossary" |
| **JIRA key** | AG-1234 — if present, enrich ALL jobs with it |
| **Priority** | what to generate first if the user can only run some jobs now |

---

## 3. Design the Job Plan

Map the domain to a standard job set. Adapt based on what the user actually asked for.

**Standard full-coverage plan (5 jobs):**

| Job | Recipe | What it produces | Config |
|---|---|---|---|
| 1 | `deep_hierarchy` | Structural backbone — parent/child map | `depth=4, children_per_level=4` |
| 2 | `task_topics` | Step-by-step procedures | `topic_count=50` |
| 3 | `concept_topics` | Explanatory articles, overviews | `topic_count=30` |
| 4 | `reference_topics` | Tables, parameters, API reference | `topic_count=30` |
| 5 | `glossary_pack` | Terms and definitions | `term_count=40` |

**Lightweight plan (3 jobs) — when user wants "solid but not exhaustive":**

| Job | Recipe | Config |
|---|---|---|
| 1 | `flat_hierarchical_dita` | `topic_count=50` |
| 2 | `task_topics` | `topic_count=40` |
| 3 | `glossary_pack` | `term_count=30` |

**Large-scale flat plan (when user says 200+ topics):**
- Split into multiple `flat_hierarchical_dita` or `large_scale` jobs of 50 each
- Use the same `subject` across all jobs so LLM authoring stays coherent

Adjust: drop recipe types the user didn't ask for, add specialized ones they did
(e.g. `conref_pack` if they need content reuse examples, `relationship_table` if they
need reltables, `bookmap_structure` if they need a publication).

---

## 4. Present the Plan (Required Before Any Job)

Show the full breakdown and ask for confirmation:

```
Here's the generation plan for **[domain]**:

| # | Recipe | Produces | Subject |
|---|---|---|---|
| 1 | deep_hierarchy | ~85 topics, 4-level map | [specific subject] |
| 2 | task_topics | 50 task procedures | [specific subject] |
| 3 | concept_topics | 30 concept articles | [specific subject] |
| 4 | reference_topics | 30 reference tables | [specific subject] |
| 5 | glossary_pack | 40 terms + definitions | [specific subject] |

**Total: ~235 DITA topics across 5 ZIP bundles**

Each job runs separately and requires approval. Want me to start with Job 1, or adjust
the plan first?
```

---

## 5. Execute Job by Job

After confirmation, run jobs **one at a time**:

1. Call `create_job(...)` for Job 1 → wait for approval → monitor with `get_job_status`
2. Report the result (download URL, topic count)
3. Ask: *"Job 1 complete. Ready to launch Job 2 (task_topics)?"*
4. Repeat

**Never queue all jobs at once** — each needs the user's approval gate.

---

## 6. Building Each `create_job` Call

Use the SAME `subject` across all jobs in a plan (with minor specialization):

```
# Job 1 — Hierarchy
create_job(
  recipe_type = "deep_hierarchy",
  subject     = "Kubernetes networking: Services, Ingress, NetworkPolicy, DNS",
  prompt_text = "[full user description]",
  config      = {"depth": 4, "children_per_level": 4},
  jira_id     = "[key if present]"
)

# Job 2 — Tasks
create_job(
  recipe_type = "task_topics",
  subject     = "Kubernetes networking procedures: deploying Services, configuring Ingress, applying NetworkPolicies",
  prompt_text = "[full user description]",
  config      = {"topic_count": 50}
)

# Job 3 — Concepts
create_job(
  recipe_type = "concept_topics",
  subject     = "Kubernetes networking concepts: ClusterIP, NodePort, LoadBalancer, Ingress controllers, CNI",
  prompt_text = "[full user description]",
  config      = {"topic_count": 30}
)
```

Key rules:
- `subject` = base domain + recipe-specific focus (procedures / concepts / terms)
- All jobs share the same `jira_id` if one was provided
- Param caps: `topic_count` ≤ 50, `depth` ≤ 5, `children_per_level` ≤ 5

---

## 7. Splitting 200+ Topic Requests

When topic count exceeds 50, split into batches with different subject specializations:

```
# Batch 1: core concepts
create_job(recipe_type="flat_hierarchical_dita", topic_count=50,
           subject="Terraform AWS: provider config, resources, data sources")

# Batch 2: modules and state
create_job(recipe_type="flat_hierarchical_dita", topic_count=50,
           subject="Terraform AWS: modules, state backend, workspaces, remote state")

# Batch 3: advanced
create_job(recipe_type="flat_hierarchical_dita", topic_count=50,
           subject="Terraform AWS: provisioners, expressions, functions, meta-arguments")
```

Each batch covers a different sub-domain slice so the LLM authors non-overlapping content.

---

## 8. Example Plans

**"Full content set for Kubernetes networking"**
→ 5-job standard plan: hierarchy + tasks + concepts + reference + glossary, all with
subject focused on Services, Ingress, NetworkPolicy, DNS, CNI

**"Build training data for AEM Guides authoring — 200 topics"**
→ 4 × `flat_hierarchical_dita` jobs of 50 each, each covering a different authoring area
(maps, topics, publishing, content reuse)

**"I need tasks, a reference table, and a glossary for Terraform"**
→ 3-job targeted plan: `task_topics` (Terraform workflows), `reference_topics`
(resource types, arguments, attributes), `glossary_pack` (Terraform terminology)
