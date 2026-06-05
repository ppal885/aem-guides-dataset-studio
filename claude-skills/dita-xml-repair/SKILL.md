---
name: dita-xml-repair
description: >
  Validate, diagnose, and fix broken or invalid DITA XML. Use this skill whenever the user
  shares DITA XML that has errors, paste DITA that needs checking, or says things like
  "fix this DITA", "my XML is invalid", "this topic won't validate", "DTD error in my DITA",
  "the conref is broken", "element X not allowed here", "fix my DITA map", "repair this topic",
  "XML is malformed", "schema validation failed", or pastes any DITA XML snippet and asks
  what's wrong with it. Also trigger when a generated dataset has validation warnings and the
  user wants them resolved. Use review_dita_xml first to diagnose, then fix_dita_xml to repair.
---

# DITA XML Repair

This skill validates DITA XML, surfaces the specific errors, and fixes them using
`review_dita_xml` → `fix_dita_xml`. The two-step approach lets the user review the diagnosis
before committing to a repair.

---

## 1. Step 1 — Review (Always First)

Call `review_dita_xml` with the user's XML. This returns:
- **validation errors** — DTD/schema violations (element nesting, missing required attrs)
- **quality issues** — semantic problems (empty shortdesc, missing cmd in step, etc.)
- **error count** — severity breakdown

```
review_dita_xml(xml_content = "<the DITA XML>")
```

**Present the findings clearly:**

```
Found **[N] errors** and **[M] warnings**:

Errors:
- [error 1 description — element, line if available]
- [error 2 ...]

Warnings:
- [warning 1]

[One-line root cause if obvious, e.g. "The <step> element is missing a required <cmd> child."]
```

---

## 2. Step 2 — Fix (Requires Approval)

`fix_dita_xml` requires user approval. Before the prompt, confirm the plan:

```
I'll repair the XML by:
- [Fix 1: what will be changed]
- [Fix 2: ...]

The structure and content will be preserved — only the invalid markup will be corrected.
```

Then call:

```
fix_dita_xml(
  xml_content  = "<the DITA XML>",
  issues       = ["<issue 1 from review>", "<issue 2>", ...]
)
```

Pass the specific issues from the review result into `issues` — this focuses the repair
and prevents unnecessary changes to valid parts of the document.

---

## 3. After Repair

1. Show a **diff summary**: what was changed (element added/removed/moved, attribute fixed).
2. Note if any issues could **not** be auto-repaired (content-level semantic problems that
   need human judgment).
3. Offer to **re-validate**: *"Want me to run a final validation pass to confirm everything
   is clean?"*

---

## 4. Common DITA Errors and What Causes Them

| Error | Typical Cause | Fix |
|---|---|---|
| `Element type "X" must be declared` | Wrong DTD or missing DOCTYPE | Add correct DOCTYPE declaration |
| `Element X not allowed in Y` | Wrong parent/child nesting | Move element to correct parent |
| `Attribute X not declared` | Typo in attribute name | Correct the attribute name |
| `<cmd> is required in <step>` | Step has no cmd child | Wrap action text in `<cmd>` |
| `<shortdesc> too long` | Shortdesc > 50 words | Trim to one sentence |
| `<conref> target not found` | Wrong file path or id | Correct the conref path |
| `<keyref> key not defined` | Key not in keydef map | Add keydef or fix key name |
| Unclosed tag / malformed XML | Hand-edited XML | Serialize properly |

---

## 5. Handling Large XML

If the user pastes a large file (many topics, full map):
- Call `review_dita_xml` on the full content.
- If there are > 10 errors, group them by type and fix the most critical ones first.
- Offer to process one topic at a time if the file is very large.

---

## 6. Examples

**User pastes broken topic:**
> "This DITA keeps failing validation — `<step>` missing required `<cmd>`. Here's the XML: [paste]"

1. `review_dita_xml(xml_content=...)` → confirms the missing `<cmd>` elements
2. Present findings: "3 `<step>` elements are missing a `<cmd>` child."
3. Confirm repair plan, then call `fix_dita_xml(xml_content=..., issues=["<step> missing <cmd>"])`

**User reports conref resolution failure:**
> "My conref isn't working — `conref="shared/notes.dita#notes/safety-note"` gives an error."

1. `review_dita_xml` to check the conref syntax
2. Check if the fragment ID format is correct (`topicid/elementid`)
3. Fix the conref path if malformed, or explain if it's a missing source file
