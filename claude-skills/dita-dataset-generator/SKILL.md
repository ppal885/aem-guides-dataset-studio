---
name: dita-dataset-generator
description: >
  Generate high-quality DITA XML datasets for AEM Guides from a free-text prompt
  or a JIRA ticket key. Use this skill whenever the user wants to produce DITA
  content bundles — topics, maps, keydefs, conrefs, reltables, glossaries, or
  any structured DITA XML dataset. Trigger on phrases like "generate a DITA
  dataset", "create topics about X", "make a dataset from JIRA AG-123",
  "generate task topics for Kubernetes", "build a DITA map", "author DITA
  content about X", "produce training data for Y", or any time a user describes
  a domain + DITA structure they want. Also trigger when the user just pastes a
  JIRA key or says "use ticket AG-123 to generate content".
---

# DITA Dataset Generator

This skill drives end-to-end DITA XML dataset generation using the AEM Guides
Dataset Studio backend. It covers two entry paths — **free-text prompt** and
**JIRA ticket** — and guides recipe selection, job creation, quality enrichment,
and output retrieval.

---

## 1. Understand the Request

Before picking a recipe, extract three things from the user's message:

| Signal | How to find it | Example |
|---|---|---|
| **Domain / subject** | "about X", "for Y", "on Z" | Kubernetes networking, AEM Guides authoring |
| **DITA structure intent** | keywords like "deep", "hierarchy", "task", "reference", "glossary", "map", "conref" | "task topics", "deep hierarchy" |
| **JIRA key** | pattern `[A-Z]+-\d+` | AG-1234, DOCS-567 |

If the intent is unclear, ask one focused question: *"What domain should the topics cover, and do you want task procedures, reference tables, a hierarchical map, or a glossary?"*

---

## 2. JIRA Flow (when a ticket key is present)

When the user provides a JIRA key (e.g. `AG-1234`):

1. **Search first** — call `search_jira_issues` with the key or a short JQL query to confirm the ticket exists and retrieve its summary.
2. **Announce what you found** — one-line summary of the ticket: title, issue type, and any DITA-relevant keywords from the description (constructs, element names, affected outputs).
3. **Map to a recipe** — use the ticket's issue type and description to pick the best recipe (see §3 below). Set `jira_id` on the `create_job` call so the backend auto-enriches the generation with Jira context.
4. **Set `prompt_text`** — paste in the Acceptance Criteria or key description text from the ticket. The backend uses this to author domain-accurate titles and body text.

Good JIRA-to-recipe mappings:
- Bug / validation issue about a specific construct → `freeform` (targeted fix/example)
- Test coverage for a workflow → `task_topics`
- API/feature reference → `reference_topics`
- Conceptual explanation needed → `concept_topics`
- Large test dataset for a DITA construct → `deep_hierarchy` or `flat_hierarchical_dita`
- Terminology / glossary gap → `glossary_pack`

---

## 3. Recipe Selection

Use `find_recipes` when uncertain, or apply this decision table directly:

| User wants | Best `recipe_type` | Key config params |
|---|---|---|
| Deep tree structure, many levels | `deep_hierarchy` | `depth` (3–5), `children_per_level` (3–5) |
| Wide branching, many top-level nodes | `wide_branching` | `root_topics` (5–15), `children_per_root` (3–8) |
| Large flat set of topics (500+) | `large_scale` or `flat_hierarchical_dita` | `topic_count` (≤50 per run) |
| Procedures / how-tos | `task_topics` | `topic_count` |
| Explanatory articles | `concept_topics` | `topic_count` |
| Tables, parameters, API docs | `reference_topics` | `topic_count` |
| Terms and definitions | `glossary_pack` | `term_count` |
| Conref / content reuse examples | `conref_pack` or `dita_conref_keyref_dataset_recipe` | `conref_density` |
| Maps with relationship tables | `relationship_table` or `maps_reltable_basic` | |
| Bookmap / publication | `bookmap_structure` | |
| Mixed constructs, free-form | `freeform` | — (no config; fully LLM-authored) |

**Always prefer a named recipe over `freeform`** unless the user explicitly wants free-form authoring or the request involves advanced/mixed constructs. Named recipes produce more reliable, validatable output.

---

## 4. Building the `create_job` Call

Assemble the call with these guidelines:

```
create_job(
  recipe_type = "<chosen recipe>",
  subject     = "<domain in 3-8 words>",     # e.g. "Kubernetes networking and services"
  prompt_text = "<verbatim key excerpt>",     # ACs, description, or user's own words (≤4000 chars)
  config      = { ... },                      # recipe-specific params, see §3
  jira_id     = "<key>"                       # only when a JIRA key was provided
)
```

**`subject` is the most important field for quality.** It drives the LLM enrichment that generates real, domain-accurate titles and body text instead of placeholder content. Be specific: `"Kubernetes NetworkPolicy and Ingress"` is far better than `"Kubernetes"`.

**Param caps** — never request more than these per job:
- `topic_count` ≤ 50
- `map_count` ≤ 10
- `topicrefs_per_map` ≤ 20
- `keydef_count` ≤ 30
- `conref_density` ≤ 0.5

If the user wants more than 50 topics, explain you'll need multiple jobs and offer to chain them.

---

## 5. Pre-flight Explanation (required before approval)

`create_job` and `generate_dita` require user approval in the UI. Before the approval prompt appears, give the user a brief, useful preview:

```
I'll generate a **[recipe label]** dataset about **[subject]**.

What this produces:
- [N] DITA [topic type] topics with domain-accurate titles and body text
- [A DITA map / keydefs / conrefs / reltable — whatever applies]
- Validated DITA XML, auto-repaired if validation fails

[If from JIRA]: Content will be grounded in ticket AG-XXXX — [one-line ticket summary].

Config: [list key params you're setting, e.g. depth=4, children_per_level=3]
```

This lets the user correct the plan before the job runs — much cheaper than regenerating.

---

## 6. After Job Approval

Once the user approves and the job runs:

1. **Monitor with `get_job_status`** if the job takes more than a few seconds.
2. **Report the result** — include the download URL and a short summary of what was produced (topic count, map structure, any auto-repairs applied).
3. **Offer refinement** — *"Want me to adjust the depth, add conrefs, or focus on a different sub-domain?"*

---

## 7. Quality Checklist

Before finalizing the `create_job` call, mentally verify:

- [ ] `subject` is specific and domain-accurate (not vague like "software")
- [ ] `recipe_type` matches the structural intent (task ≠ reference ≠ hierarchy)
- [ ] `config` params are within caps
- [ ] `prompt_text` contains concrete content hints (ACs, bullet points, element names)
- [ ] For JIRA: `jira_id` is set so the backend can pull live Jira enrichment
- [ ] Pre-flight explanation given to user so they can correct before approval

Following this checklist is the difference between a stub-filled dataset and one with meaningful, reusable DITA content.

---

## 8. Example Invocations

**From free-text prompt:**
> "Generate a deep hierarchy DITA dataset about Kubernetes networking — Services, Ingress, NetworkPolicies, DNS."

```
create_job(
  recipe_type = "deep_hierarchy",
  subject     = "Kubernetes networking: Services, Ingress, NetworkPolicy, DNS",
  prompt_text = "Kubernetes networking — Services, Ingress, NetworkPolicies, DNS",
  config      = {"depth": 4, "children_per_level": 4}
)
```

**From JIRA key:**
> "Use ticket AG-4821 to generate DITA content."

1. `search_jira_issues("AG-4821")` → title: "Add conref coverage for note elements"
2. Map: conref coverage → `conref_pack`
3. `create_job(recipe_type="conref_pack", subject="DITA note element conref patterns", jira_id="AG-4821", prompt_text="<AC text from ticket>")`

**Glossary from domain:**
> "Make a glossary for cloud networking — VPC, subnet, NAT gateway, route table, peering."

```
create_job(
  recipe_type = "glossary_pack",
  subject     = "cloud networking: VPC, subnet, NAT gateway, route table, peering",
  prompt_text = "Cloud networking glossary covering VPC, subnet, NAT gateway, route table, peering connections"
)
```
