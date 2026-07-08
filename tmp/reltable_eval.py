from __future__ import annotations

from app.services.learned_qa_service import retrieve_learned_qa


CASES = [
    ("What is a reltable in DITA and when should I use it?", ["<reltable>", "related links"], "dita_reltable_senior_seed"),
    ("Explain reltable relrow relcell with XML example.", ["<relrow>", "<relcell>"], "dita_reltable_senior_seed"),
    ("What does relrow do inside a DITA relationship table?", ["relationship set", "<relrow>"], "dita_reltable_senior_seed"),
    ("What does relcell mean in a DITA reltable?", ["same relationship role", "<relcell>"], "dita_reltable_senior_seed"),
    ("Can relcell contain multiple topicrefs?", ["Multiple topicrefs", "<topicref"], "dita_reltable_senior_seed"),
    ("How do relheader and relcolspec work in DITA reltables?", ["<relheader>", "<relcolspec"], "dita_reltable_senior_seed"),
    ("What does relcolspec type mean in a relationship table?", ["column metadata", "type=\"concept\""], "dita_reltable_senior_seed"),
    ("Which attributes control reltable links?", ["@toc", "@linking", "@processing-role"], "dita_reltable_senior_seed"),
    ("How does linking sourceonly affect reltable generated links?", ["sourceonly", "source of generated links"], "dita_reltable_senior_seed"),
    ("Why are my reltable links one-way instead of two-way?", ["linking", "sourceonly", "targetonly"], "dita_reltable_senior_seed"),
    ("How does collection-type affect relationship-table links?", ["sequence", "choice", "family"], "dita_reltable_senior_seed"),
    ("Can reltable topicrefs use keyref instead of href?", ["keyref", "active map"], "dita_reltable_senior_seed"),
    ("Can I use scoped keys inside relcell topicrefs?", ["keyref", "key scope"], "dita_reltable_senior_seed"),
    ("Can a DITA reltable link to external HTML or PDF resources?", ["scope=\"external\"", "format=\"pdf\""], "dita_reltable_senior_seed"),
    ("Can reltable use scope external and format pdf for related links?", ["scope=\"external\"", "format=\"pdf\""], "dita_reltable_senior_seed"),
    ("What is the difference between toc, linking, and processing-role in reltables?", ["navigation visibility", "generated-link participation", "processing resource"], "dita_reltable_senior_seed"),
    ("How do I troubleshoot reltable related links that do not appear in output?", ["effective map", "linking", "filtering"], "dita_reltable_senior_seed"),
    ("Why does a related link appear in HTML but not PDF?", ["HTML", "PDF", "transform"], "dita_reltable_senior_seed"),
    ("How do copy-to and branch filtering affect reltable links?", ["output identity", "branch filtering", "copy-to"], "dita_reltable_senior_seed"),
    ("Can relationship tables create duplicate related links?", ["duplicates", "related links"], None),
    ("How should duplicate reltable links be handled?", ["duplicate", "source"], None),
    ("What happens when a relation target is resource-only?", ["resource-only", "output"], None),
    ("Can relationship tables reference scoped keys?", ["scoped keys", "key"], None),
    ("How does filtering remove generated related links?", ["filtering", "related links"], None),
    ("How does args.rellinks affect DITA-OT HTML related links?", ["args.rellinks", "HTML"], "dita_ot_docs_researched"),
]


def main() -> int:
    failures: list[str] = []
    for index, (query, must_have, expected_source) in enumerate(CASES, 1):
        rows = retrieve_learned_qa(query, k=1)
        if not rows:
            failures.append(f"{index}. no result: {query}")
            continue
        row = rows[0]
        answer = row.get("final_answer") or ""
        source = row.get("source_type")
        missing = [term for term in must_have if term.lower() not in answer.lower()]
        source_bad = bool(expected_source and source != expected_source)
        status = "PASS" if not missing and not source_bad else "FAIL"
        print(f"{index:02d} {status} | source={source} | prompt={row.get('prompt')}")
        if missing or source_bad:
            failures.append(
                f"{index}. {query} source={source} expected={expected_source} missing={missing} matched={row.get('prompt')}"
            )
    print(f"\nSUMMARY passed={len(CASES) - len(failures)} failed={len(failures)} total={len(CASES)}")
    if failures:
        print("\nFAILURES")
        for failure in failures:
            print(f"- {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
