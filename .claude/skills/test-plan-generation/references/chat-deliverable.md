# Chat Deliverable — 5-Section Widget

After `run_gates.py` exits 0 and the plan is indexed, render the plan as a compact 5-section
widget in the chat UI using `show_widget`. Do NOT paste the full 11-section markdown — it is too
long to scan and QA engineers need a quick-glance view.

## When to use this

Always — every plan that passes gates gets the widget rendered in chat. The full markdown file
(`output/test-plans/<KEY>-test-plan.md`) is the durable artifact; the widget is the chat
summary. Both are always produced.

## The 5 sections (fixed order)

1. **Acceptance Criteria** — all ACs with Confirmed/Proposed badge and **full Given/When/Then text** (never condensed to a one-liner)
2. **Test Scenarios** — table: ID, Priority (P0/P1/P2), AC, one-line description
3. **Automation Coverage** — table: AC, status (covered/partial/not covered), gap or target file
4. **Known Jira Bugs** — each bug as a coloured card with **all 8 fields**: ID, Similarity (with strength word), Status, Resolution, Affected version, Fix version, RCA, Test evidence, Impact; plus the historical search status line
5. **Open Questions** — table: ID, impact (High/Med/Low), one-line question + QA impact

Above the 5 sections: a header row with ticket ID, summary, and chips (priority, component,
customer, lifecycle stage) + a stat bar (4 cards: AC count, scenario count, automation ratio,
fix version).

## Stat bar values — derive from the plan

| Card      | Value to compute                                                              |
|-----------|-------------------------------------------------------------------------------|
| ACs       | Count lines matching `- AC-\d+`; note Confirmed vs Proposed split             |
| Scenarios | Count lines matching `- P[012] TC-`                                           |
| Automation| `<covered+partial>/<total ACs>` — e.g. `1/5`; note breakdown below           |
| Fix ver.  | From Scope From Git / Jira lifecycle (e.g. `2605`, `Backlog`, `2608`)        |

## Color conventions (use CSS variables throughout)

| Meaning       | Background var       | Text var          |
|---------------|----------------------|-------------------|
| Confirmed     | `--bg-accent`        | `--text-accent`   |
| Proposed      | `--bg-warning`       | `--text-warning`  |
| P0 priority   | `--bg-danger`        | `--text-danger`   |
| P1 priority   | `--bg-warning`       | `--text-warning`  |
| P2 priority   | `--bg-success`       | `--text-success`  |
| Not covered   | `--bg-danger`        | `--text-danger`   |
| Partial       | `--bg-warning`       | `--text-warning`  |
| Covered       | `--bg-success`       | `--text-success`  |
| Bug card      | `--bg-warning` border `--border-warning`                        |

## Widget HTML template

Copy this shell and fill in the DATA SLOTS marked with `<!-- SLOT: ... -->`.
Keep all CSS variables — never hardcode hex. No DOCTYPE, html, head, or body tags.

```html
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-sans);font-size:13.5px;color:var(--text-primary);line-height:1.6}
.hdr{display:flex;align-items:center;gap:10px;padding:.75rem 0 1rem}
.title{font-size:18px;font-weight:500}
.chips{display:flex;gap:5px;flex-wrap:wrap;margin-left:auto}
.chip{font-size:11px;padding:2px 8px;border-radius:99px;border:0.5px solid var(--border);color:var(--text-secondary);background:var(--surface-1)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:1.25rem}
.stat{background:var(--surface-1);border:0.5px solid var(--border);border-radius:var(--radius);padding:.6rem .75rem}
.stat-n{font-size:20px;font-weight:500}
.stat-l{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em}
.stat-s{font-size:11px;color:var(--text-secondary);margin-top:1px}
.sec{margin-bottom:1.1rem}
.sec-h{font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:.07em;color:var(--text-muted);padding:.35rem .6rem;background:var(--surface-1);border-radius:var(--radius);border-left:3px solid var(--border-accent);margin-bottom:.5rem}
.ac{display:flex;gap:8px;align-items:baseline;padding:.4rem .6rem;border-radius:var(--radius);border:0.5px solid var(--border);margin:.3rem 0;background:var(--surface-1)}
.ac-id{font-weight:500;color:var(--text-accent);font-size:12px;min-width:38px}
.ac-txt{font-size:13px}
.badge{font-size:10px;padding:1px 6px;border-radius:99px;font-weight:500;flex-shrink:0}
.confirmed{background:var(--bg-accent);color:var(--text-accent)}
.proposed{background:var(--bg-warning);color:var(--text-warning)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;font-weight:500;color:var(--text-secondary);padding:5px 7px;border-bottom:0.5px solid var(--border)}
td{padding:5px 7px;border-bottom:0.5px solid var(--border);vertical-align:top}
.p0{background:var(--bg-danger);color:var(--text-danger);font-size:10px;padding:1px 6px;border-radius:99px;font-weight:500}
.p1{background:var(--bg-warning);color:var(--text-warning);font-size:10px;padding:1px 6px;border-radius:99px;font-weight:500}
.p2{background:var(--bg-success);color:var(--text-success);font-size:10px;padding:1px 6px;border-radius:99px;font-weight:500}
.cov-g{color:var(--text-danger);font-size:11px}
.cov-p{color:var(--text-warning);font-size:11px}
.cov-c{color:var(--text-success);font-size:11px}
code{font-family:var(--font-mono);font-size:11.5px;background:var(--surface-0);padding:1px 4px;border-radius:3px}
.bug{padding:.4rem .6rem;border-radius:var(--radius);border:0.5px solid var(--border-warning);background:var(--bg-warning);margin:.3rem 0;font-size:13px}
.bug-id{font-weight:500;color:var(--text-warning)}
</style>

<h2 class="sr-only"><!-- SLOT: one-sentence screen-reader summary --></h2>

<div style="padding:.75rem 0">

<!-- HEADER -->
<div class="hdr">
  <div>
    <div class="title"><!-- SLOT: GUIDES-XXXXX --></div>
    <div style="font-size:12px;color:var(--text-secondary);margin-top:2px"><!-- SLOT: short defect summary --></div>
  </div>
  <div class="chips">
    <span class="chip"><!-- priority --></span>
    <span class="chip"><!-- component --></span>
    <span class="chip"><!-- customer · version --></span>
    <span class="chip"><!-- lifecycle stage --></span>
  </div>
</div>

<!-- STAT BAR -->
<div class="stats">
  <div class="stat"><div class="stat-l">ACs</div><div class="stat-n"><!-- N --></div><div class="stat-s"><!-- X Confirmed · Y Proposed --></div></div>
  <div class="stat"><div class="stat-l">Scenarios</div><div class="stat-n"><!-- N --></div><div class="stat-s"><!-- X P0 · Y P1 · Z P2 --></div></div>
  <div class="stat"><div class="stat-l">Automation</div><div class="stat-n"><!-- X/N --></div><div class="stat-s"><!-- breakdown --></div></div>
  <div class="stat"><div class="stat-l">Fix version</div><div class="stat-n"><!-- version --></div><div class="stat-s"><!-- Affected: XXXX --></div></div>
</div>

<!-- SECTION 1: ACCEPTANCE CRITERIA -->
<div class="sec">
  <div class="sec-h">1 · Acceptance criteria</div>
  <!-- Repeat for each AC: -->
  <div class="ac">
    <span class="ac-id">AC-01</span>
    <span class="badge confirmed">Confirmed</span>
    <!-- OR: <span class="badge proposed">Proposed</span> -->
    <span class="ac-txt"><!-- one-line Given/When/Then summary --></span>
  </div>
</div>

<!-- SECTION 2: TEST SCENARIOS -->
<div class="sec">
  <div class="sec-h">2 · Test scenarios</div>
  <table>
    <thead><tr><th>ID</th><th>P</th><th>AC</th><th>What it checks</th></tr></thead>
    <tbody>
      <!-- Repeat for each TC: -->
      <tr>
        <td><code>TC-01</code></td>
        <td><span class="p0">P0</span></td><!-- or p1/p2 -->
        <td>AC-01</td>
        <td><!-- one-line description --></td>
      </tr>
    </tbody>
  </table>
</div>

<!-- SECTION 3: AUTOMATION COVERAGE -->
<div class="sec">
  <div class="sec-h">3 · Automation coverage</div>
  <table>
    <thead><tr><th>AC</th><th>Status</th><th>Gap / action</th></tr></thead>
    <tbody>
      <!-- Repeat for each AC: -->
      <tr>
        <td>AC-01</td>
        <td>
          <!-- pick one: -->
          <span class="cov-c">● Covered</span>
          <!-- <span class="cov-p">◐ Partial</span> -->
          <!-- <span class="cov-g">● Not covered</span> -->
        </td>
        <td><!-- file/method or gap action --></td>
      </tr>
    </tbody>
  </table>
</div>

<!-- SECTION 4: KNOWN JIRA BUGS -->
<div class="sec">
  <div class="sec-h">4 · Known jira bugs</div>
  <!-- Repeat for each bug: -->
  <div class="bug">
    <span class="bug-id">GUIDES-XXXXX</span> — <!-- similarity line and TC impact -->
  </div>
  <!-- If no structural twin was found: -->
  <!-- <div style="font-size:13px;color:var(--text-secondary)">No prior same-defect-class history found in jira_qa.</div> -->
</div>

<!-- SECTION 5: OPEN QUESTIONS -->
<div class="sec">
  <div class="sec-h">5 · Open questions</div>
  <table>
    <thead><tr><th>ID</th><th>Impact</th><th>Question</th></tr></thead>
    <tbody>
      <!-- Repeat for each OQ: -->
      <tr>
        <td>OQ-01</td>
        <td style="color:var(--text-danger)">High</td>
        <!-- or: style="color:var(--text-warning)">Med  /  color:var(--text-secondary)">Low -->
        <td><!-- one-line question --></td>
      </tr>
    </tbody>
  </table>
</div>

</div>
```

## Rules

- Do not add extra sections. The 5 listed above are the only ones.
- Show the **complete Given/When/Then text** for every AC exactly as written in the plan body — never paraphrase or shorten to a label. Use 12–13px font and allow AC cards to grow in height. The user reads these to verify the acceptance contract; condensed labels lose fixture details, threshold values, and expected outcomes.
- For Known Jira Bugs, show all 8 fields per ticket in the card body: Similarity (with a strength word: strongest/adjacent/weak), Status, Resolution, Affected version, Fix version, RCA, Test evidence, Impact. Also include the historical search status line (JQL intent and jira_qa ChromaDB result). Never reduce a bug card to just the similarity line and impact.
- For automation status, use exactly these three markers:
  - `● Covered` (--text-success) — Exact and strong
  - `◐ Partial` (--text-warning) — Exact but weak oracle, or Partially covered
  - `● Not covered` (--text-danger) — Not covered or Not suitable for automation
- OQ impact colours: High → `--text-danger`, Med → `--text-warning`, Low → `--text-secondary`.
- The widget uses `show_widget` with `title` = `<KEY>-5section` (e.g. `GUIDES-53707-5section`)
  and one short `loading_messages` entry.
- The full 11-section file is still saved and indexed — the widget is the chat view only.
- Never render the raw 11-section markdown in chat. The widget replaces it.
- Jira MCP attachment downloads: use the PAT bearer token (`JIRA_PAT` from `.env`) when basic
  auth returns 401 on `/secure/attachment/` URLs. The pattern is:
  `requests.get(url, headers={"Authorization": f"Bearer {pat}"}, timeout=30, allow_redirects=True)`
