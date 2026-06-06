---
name: dita-domain-dataset
description: >
  Generate domain-specialized DITA datasets that use expert vocabulary, correct topic
  structures, and domain-accurate content for a specific industry or technology area.
  Use this skill whenever a user names a specific domain and wants high-quality data
  tailored to it: "generate DITA dataset for Kubernetes", "create DITA for cloud
  infrastructure docs", "generate dataset for medical device software", "DITA training
  data for AEM Guides authoring", "generate data for Terraform documentation",
  "dataset for Docker", "DITA for network security", "generate for API documentation",
  "DITA dataset for CI/CD pipelines", "generate DITA for enterprise software",
  or any request where a named technology, industry, or product domain is the focus.
  This skill picks the right recipe AND crafts a domain-expert subject and prompt_text
  to maximize content richness and accuracy.
---

# DITA Domain Dataset Generator

This skill turns a domain name into a high-quality DITA dataset by:
1. Mapping the domain to the right recipe type
2. Writing an expert-level `subject` that covers the domain's key sub-areas
3. Crafting a `prompt_text` that injects domain vocabulary into the LLM authoring step

---

## 1. Domain → Recipe Mapping

Pick the recipe that matches how the domain is structured:

| Domain type | Best recipe | Why |
|---|---|---|
| Software platform with procedures | `task_topics` | Users need step-by-step instructions |
| API / configuration reference | `reference_topics` | Tables, parameters, flag listings |
| Conceptual architecture | `concept_topics` | Background, how-it-works content |
| Large software ecosystem (Kubernetes, AWS, etc.) | `deep_hierarchy` | Deep tree of topics across sub-domains |
| Terminology-heavy domain (cloud, security) | `glossary_pack` | Term definitions and acronyms |
| Full coverage of a product | `flat_hierarchical_dita` or `large_scale` | Broad flat set across all areas |
| Mixed (most real domains) | Two jobs: `task_topics` + `concept_topics` | Pair procedures with explanations |

---

## 2. Domain Sub-area Expansion

Before calling `create_job`, expand the domain into its key sub-areas. This becomes the `subject` field — the single biggest lever for content quality.

**Template:** `"[Domain]: [sub-area 1], [sub-area 2], [sub-area 3], [sub-area 4]"`

**Examples by domain:**

| Domain | Expanded subject |
|---|---|
| Kubernetes | `"Kubernetes: Pods, Deployments, Services, Ingress, ConfigMaps, NetworkPolicy, RBAC"` |
| Docker | `"Docker: container lifecycle, networking, volumes, Compose, Dockerfile, health checks"` |
| Terraform AWS | `"Terraform AWS: providers, resources, modules, state backend, workspaces, variables"` |
| AEM Guides authoring | `"AEM Guides: DITA maps, conditional content, output presets, keydefs, PDF templates"` |
| REST API docs | `"REST API: authentication, endpoints, request/response schemas, error codes, rate limits"` |
| Network security | `"Network security: firewalls, VPN, zero-trust, TLS, IDS/IPS, access control lists"` |
| Medical device software | `"Medical device software: IEC 62304, risk management, traceability, software lifecycle"` |
| Cloud infrastructure | `"Cloud infrastructure: compute, storage, networking, IAM, monitoring, cost management"` |

**Rule:** Always include 4–8 sub-areas. Too few → generic content. Too many → shallow coverage per area.

---

## 3. Prompt Text for Domain Vocabulary

Set `prompt_text` to inject expert terminology that the LLM authoring step uses for titles and body text.

**Good `prompt_text` pattern:**
```
"[Domain] documentation covering: [sub-areas with key terms].
Key vocabulary: [5-10 domain-specific terms, commands, or element names].
[Any constraints: title length, element requirements, style notes]."
```

**Examples:**

For Kubernetes task topics:
```
"Kubernetes operational procedures covering: pod scheduling with node affinity and
taints/tolerations, deploying applications with Deployments and StatefulSets, exposing
services via ClusterIP/NodePort/LoadBalancer, configuring Ingress controllers, applying
NetworkPolicies. Key terms: kubectl, YAML manifest, namespace, label selector, annotation,
kube-apiserver. Titles under 80 chars. Steps should use code blocks for kubectl commands."
```

For Terraform reference:
```
"Terraform AWS reference documentation covering: provider configuration, resource blocks
for EC2/S3/RDS/VPC, data sources, module composition, remote state with S3 backend,
workspace isolation. Key terms: HCL, terraform.tfvars, plan/apply/destroy, state locking,
provider version constraints, count/for_each meta-arguments."
```

---

## 4. Full create_job Call Pattern

```
create_job(
  recipe_type = "[chosen from §1]",
  subject     = "[domain: sub-area1, sub-area2, sub-area3, sub-area4]",
  prompt_text = "[domain vocabulary + constraints from §3]",
  config      = { "topic_count": N },   # or depth/children for hierarchy
)
```

**Config recommendations by recipe:**
- `task_topics` / `concept_topics` / `reference_topics`: `topic_count` = 20–50
- `glossary_pack`: `term_count` = 30–60
- `deep_hierarchy`: `depth` = 3–5, `children_per_level` = 3–5
- `flat_hierarchical_dita`: `topic_count` = 50 (max per job)

---

## 5. Pre-flight Explanation

Before approval, tell the user:

```
I'll generate a **[recipe]** dataset for **[domain]**.

Domain coverage:
[list the sub-areas being covered]

What this produces:
- [N] DITA [type] topics with [domain]-accurate titles and body content
- Domain vocabulary injected: [3-4 key terms]
- [Map / glossary / whatever applies]
- Validated DITA 1.3 XML

Config: [key params]
```

---

## 6. Domain Quick-start Examples

**User:** "Generate a DITA dataset for Kubernetes networking"
```
create_job(
  recipe_type = "task_topics",
  subject     = "Kubernetes networking: Services, Ingress, NetworkPolicy, DNS, CNI plugins",
  prompt_text = "Kubernetes networking tasks: creating ClusterIP/NodePort/LoadBalancer Services, configuring Ingress with nginx/traefik, applying NetworkPolicies with podSelector/namespaceSelector, debugging DNS with nslookup/dig, installing CNI plugins. Key terms: kubectl, kube-proxy, CoreDNS, calico, flannel. Steps use kubectl commands in code blocks.",
  config      = {"topic_count": 30}
)
```

**User:** "Create reference DITA for Terraform AWS resources"
```
create_job(
  recipe_type = "reference_topics",
  subject     = "Terraform AWS resources: EC2, S3, RDS, VPC, IAM, Lambda, CloudWatch",
  prompt_text = "Terraform AWS reference topics for each resource type: aws_instance, aws_s3_bucket, aws_db_instance, aws_vpc, aws_iam_role, aws_lambda_function. Each topic: resource block syntax, required/optional arguments, exported attributes, example configuration. Key terms: HCL, provider, plan, apply, state, module.",
  config      = {"topic_count": 35}
)
```

**User:** "Generate a Kubernetes training dataset — I need everything"
→ Use `dita-batch-planner` to chain: `task_topics` (operations) + `concept_topics` (architecture) + `reference_topics` (API objects) + `glossary_pack` (terminology)
