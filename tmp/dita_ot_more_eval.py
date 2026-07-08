from __future__ import annotations

from app.services.learned_qa_service import retrieve_learned_qa


CASES = [
    ("How do args.css args.cssroot args.copycss and args.csspath work in DITA-OT HTML5?", ["args.cssroot", "args.copycss"], "dita_ot_docs_more"),
    ("Why is my custom CSS not copied to the HTML5 output folder?", ["args.copycss", "args.csspath"], "dita_ot_docs_researched"),
    ("How do I inject a header footer and head fragment into DITA-OT HTML output?", ["args.hdr", "args.ftr", "args.hdf"], "dita_ot_docs_more"),
    ("What does args.html5.classattr do?", ["args.html5.classattr", "class ancestry"], "dita_ot_docs_more"),
    ("What is args.xhtml.classattr used for in DITA-OT?", ["args.xhtml.classattr", "PRESERVE-DITA-CLASS"], "dita_ot_docs_more"),
    ("How do I generate nav-toc partial or full in HTML5 output?", ["nav-toc", "partial", "full"], "dita_ot_docs_more"),
    ("Why is my HTML5 TOC file missing?", ["html5.toc.generate", "TOC"], "dita_ot_docs_more"),
    ("How do I change generated HTML file extensions with args.outext?", ["args.outext", "extension"], "dita_ot_docs_more"),
    ("How do args.indexshow and args.artlbl affect visible HTML output?", ["args.indexshow", "args.artlbl"], "dita_ot_docs_more"),
    ("How do args.figurelink.style and args.tablelink.style affect generated xref text?", ["args.figurelink.style", "args.tablelink.style"], "dita_ot_docs_more"),
    ("What does remove-broken-links do in DITA-OT?", ["remove-broken-links", "broken related links"], "dita_ot_docs_more"),
    ("How do result.rewrite-rule.class and result.rewrite-rule.xsl affect generated filenames?", ["result.rewrite-rule.class", "result.rewrite-rule.xsl"], "dita_ot_docs_more"),
    ("How does transtype relate to --format and custom output plugins?", ["transtype", "--format", "plug-ins"], "dita_ot_docs_more"),
    ("What does validate=true actually validate in DITA-OT?", ["validate", "grammar"], "dita_ot_docs_more"),
    ("How do args.chapter.layout and args.bookmark.style affect PDF output?", ["args.chapter.layout", "args.bookmark.style"], "dita_ot_docs_more"),
    ("How do I retain bookmap frontmatter and backmatter order in PDF?", ["args.bookmap-order", "bookmap"], "dita_ot_docs_more"),
    ("How do I pass a FOP user configuration file to DITA-OT PDF?", ["args.fo.userconfig", "pdf.formatter"], "dita_ot_docs_more"),
    ("What is org.dita.pdf2.i18n.enabled for?", ["org.dita.pdf2.i18n.enabled", "font"], "dita_ot_docs_more"),
    ("Does PDF2 honor chunk attributes?", ["org.dita.pdf2.chunk.enabled", "chunk"], "dita_ot_docs_more"),
    ("Should I use DITA-OT PDF theme or customization.dir?", ["theme", "customization.dir"], "dita_ot_docs_more"),
    ("Why does .ditaotrc make CI output different from local output?", [".ditaotrc", "first value found wins"], "dita_ot_docs_more"),
    ("What is the precedence between --property, --propertyfile, .ditaotrc and local.properties?", ["--propertyfile", ".ditaotrc", "first value found wins"], "dita_ot_docs_more"),
    ("How should I debug args.filter with multiple DITAVAL files?", ["filter-file order", "OS path separator"], "dita_ot_docs_more"),
    ("How do I keep DITA-OT temp files and xtrf xtrc for debugging?", ["clean.temp=no", "xtrf"], "dita_ot_docs_researched"),
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
        source_bad = source != expected_source
        status = "PASS" if not missing and not source_bad else "FAIL"
        print(f"{index:02d} {status} | source={source} | prompt={row.get('prompt')}")
        if missing or source_bad:
            failures.append(f"{index}. {query} source={source} expected={expected_source} missing={missing} matched={row.get('prompt')}")
    print(f"\nSUMMARY passed={len(CASES) - len(failures)} failed={len(failures)} total={len(CASES)}")
    for failure in failures:
        print(f"- {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
