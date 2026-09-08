"""Offline conformance checks for the curated Native PDF sibling discovery.

These test discovery and provenance, not a PDF renderer or acceptance correctness.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import coverage_hypotheses
import dimension_synthesizer
import feature_map


def _native_candidates(pairs, map_path=None):
    return [candidate for candidate in feature_map.candidates_for(pairs, map_path)
            if candidate["surface"] == "NATIVE_PDF_CONTENT"]


def run_tests(check):
    pairs = [("E-PDF", "Native PDF cross-reference text uses the output language.")]
    before = deepcopy(pairs)
    candidates = _native_candidates(pairs)
    by_feature = {item["feature"]: item for item in candidates}
    check("Native PDF discovers Variables and Variable Sets without either sibling in the headline",
          set(by_feature) == {"Variables", "Variable Sets"})
    check("feature discovery does not mutate evidence", pairs == before)
    check("Native PDF siblings have independent equivalence keys",
          len({item["equivalence_key"] for item in candidates}) == 2)
    check("Native PDF siblings preserve source identity and matched evidence",
          all(item["current_evidence"] == ["E-PDF"]
              and item["reference"] == "Experience League native-pdf-variables"
              and all(url.startswith(feature_map.EXPERIENCE_LEAGUE_PREFIX)
                      and url.endswith("/native-pdf-variables")
                      for url in item["reference_urls"])
              for item in candidates))
    check("Native PDF siblings remain advisory investigation candidates",
          all(item["status"] == "INVESTIGATION_CANDIDATE"
              and item["advisory_only"] and item["requires_more_evidence"]
              and item["technical_basis"]
              and not any(field in item for field in
                          ("ac_id", "ac_refs", "verdict", "acceptance_promotions"))
              for item in candidates))
    check("Native PDF siblings satisfy canonical coverage-hypothesis shape",
          coverage_hypotheses.validate_coverage_block(candidates) == [])
    variables = by_feature.get("Variables", {})
    sets = by_feature.get("Variable Sets", {})
    check("Variables and Variable Sets investigate different coverage axes",
          variables.get("implied_dimension_axis") == "CODE_PATH_CONSUMER"
          and sets.get("implied_dimension_axis") == "CONFIG_BRANCH")
    check("Variables candidate preserves the separate Language Variables boundary",
          "keep Variables separate from Language Variables" in variables.get("candidate", ""))
    set_question = sets.get("candidate", "")
    check("Variable Set selection keeps the documented default and custom cases",
          "selected in its output preset" in set_question
          and "(Default)" in set_question and "custom set" in set_question)
    check("Variable Sets do not inherit output-language selection or fallback",
          "do not infer automatic set selection or Language Variable fallback" in set_question)

    busy_pairs = [("E-ENGINE", "Native PDF output preset resolves localized cross-reference text.")]
    explicit_probes = ["How is the output language resolved?", "Which settings govern references?"]
    busy_features = feature_map.candidates_for(busy_pairs)
    queries, deferred = dimension_synthesizer._offline_doc_query_plan(
        busy_pairs, explicit_probes, busy_features)
    variable_queries = [query for query in queries if query[0].startswith("feature_map:")
                        and "Variables" in query[1] and "Variable Sets" in query[1]]
    check("large publishing checklist cannot starve the Native PDF sibling source",
          len(variable_queries) == 1)
    check("same-source sibling query keeps the exact documented reference filter",
          bool(variable_queries)
          and variable_queries[0][2] == tuple(sets.get("reference_urls", [])))
    check("sibling query scheduling preserves explicit probes and current behavior",
          queries[:2] == [("rag_probe:1", explicit_probes[0], ()),
                          ("rag_probe:2", explicit_probes[1], ())]
          and queries[-1][0] == "current_behavior"
          and len(queries) <= dimension_synthesizer.MAX_OFFLINE_DOC_QUERIES)
    check("query budget records deferred feature groups explicitly", bool(deferred))

    # Different synthetic vocabulary proves the scheduling is not a product rule.
    synthetic = [{"surface": "LARGE_SURFACE", "feature": f"large option {index}",
                  "shared_flows": ["shared route"],
                  "reference_urls": [f"https://example.test/large/{index}"]}
                 for index in range(8)]
    synthetic += [{"surface": "SMALL_SURFACE", "feature": name,
                   "shared_flows": ["another route"],
                   "reference_urls": ["https://example.test/small"]}
                  for name in ("first sibling", "second sibling")]
    synthetic_before = deepcopy(synthetic)
    synthetic_queries, synthetic_deferred = dimension_synthesizer._offline_doc_query_plan(
        [("E-FLOW", "Change the route.")], explicit_probes, synthetic)
    check("generic round-robin gives small matched surfaces a query slot",
          any("first sibling" in query[1] and "second sibling" in query[1]
              for query in synthetic_queries))
    check("same-source grouping saves calls without enlarging the budget",
          len(dimension_synthesizer._feature_query_groups(synthetic)) == 9
          and len(synthetic_queries) == dimension_synthesizer.MAX_OFFLINE_DOC_QUERIES
          and len(synthetic_deferred) == 6)
    check("query scheduling does not mutate candidate provenance", synthetic == synthetic_before)

    source_url = sets.get("reference_urls", [""])[0]
    calls = []

    def retrieve_docs(query, count):
        calls.append((query, count))
        return ([{"title": "Variables in the PDF output", "url": source_url,
                  "source_ref": source_url, "snippet": "Selected set values.", "distance": 0.2}]
                if "Variables" in query and "Variable Sets" in query else [])

    offline = SimpleNamespace(retrieve_docs=retrieve_docs,
                              retrieval_status=lambda _kind: {"status": "SUCCESS"})
    rows, gaps = dimension_synthesizer._offline_rag_candidates(
        offline, busy_pairs, explicit_probes, busy_features)
    check("grouped retrieval produces only returned supporting discovery evidence",
          len(rows) == 1 and rows[0]["retrieved_url"] == source_url
          and rows[0]["source_label"] == "OFFLINE_CHROMA"
          and rows[0]["authority_class"] == "SUPPORTING_DISCOVERY"
          and rows[0]["status"] == "INVESTIGATION_CANDIDATE")
    check("partial retrieval retains deferred-group gaps and fixed query/result budgets",
          any("deferred" in gap and "not retrieved" in gap for gap in gaps)
          and len(calls) <= dimension_synthesizer.MAX_OFFLINE_DOC_QUERIES
          and all(count == dimension_synthesizer.OFFLINE_DOC_RESULTS_PER_QUERY
                  for _, count in calls))
    absent_rows, absent_gaps = dimension_synthesizer._offline_rag_candidates(
        None, busy_pairs, explicit_probes, busy_features)
    check("unavailable RAG reports both retrieval absence and deferred groups without invention",
          absent_rows == [] and any("unavailable" in gap for gap in absent_gaps)
          and any("deferred" in gap for gap in absent_gaps))

    partial_calls = []

    def partial_docs(query, count):
        partial_calls.append((query, count))
        return ([{"title": "First inspected source", "source_ref": "https://example.test/first",
                  "snippet": "Only the first query returned evidence.", "distance": 0.2}]
                if len(partial_calls) == 1 else [])

    partial_offline = SimpleNamespace(
        retrieve_docs=partial_docs,
        retrieval_status=lambda _kind: {"status": "SUCCESS" if len(partial_calls) == 1 else "ERROR",
                                       "reason": "private_exception_detail"},
    )
    partial_rows, partial_gaps = dimension_synthesizer._offline_rag_candidates(
        partial_offline, busy_pairs, explicit_probes, busy_features)
    check("provider error after success retains the real first result and stops calls",
          len(partial_rows) == 1 and len(partial_calls) == 2
          and partial_rows[0]["retrieved_title"] == "First inspected source")
    check("partial success cannot hide the provider failure or unexecuted query count",
          any("provider status ERROR" in gap and "4 planned query group(s) not executed" in gap
              for gap in partial_gaps)
          and not any("private_exception_detail" in gap for gap in partial_gaps))

    capped_calls = []

    def capped_docs(query, count):
        capped_calls.append((query, count))
        return [{"title": f"Source {len(capped_calls)} {index}",
                 "source_ref": f"https://example.test/source/{len(capped_calls)}/{index}",
                 "distance": 0.2} for index in range(count)]

    capped_offline = SimpleNamespace(retrieve_docs=capped_docs,
                                     retrieval_status=lambda _kind: {"status": "SUCCESS"})
    with patch.object(dimension_synthesizer, "MAX_OFFLINE_DOC_CANDIDATES", 2):
        capped_rows, capped_gaps = dimension_synthesizer._offline_rag_candidates(
            capped_offline, busy_pairs, explicit_probes, busy_features)
    check("candidate limit records planned queries not executed without extra calls",
          len(capped_rows) == 2 and len(capped_calls) == 1
          and any("CANDIDATE_LIMIT" in gap and "5 planned query group(s) not executed" in gap
                  for gap in capped_gaps))

    for engine in ("Native PDF", "NativePDF", "native-pdf"):
        check(f"documented Native PDF spelling activates sibling discovery: {engine}",
              len(_native_candidates([("E-ENGINE", f"{engine} cross-reference text changes.")])) == 2)
    for text in (
        "The Editor language label is translated incorrectly.",
        "Language Variables are listed in the Editor panel.",
        "Variables editor default values can be changed.",
        "An HTML5 output preset generates localized cross-reference text.",
        "DITA-OT PDF publishing generates cross-reference text.",
        "Output path variables select the output folder.",
    ):
        check(f"adjacent surface does not activate Native PDF siblings: {text}",
              _native_candidates([("E-OTHER", text)]) == [])

    manifest = {
        "behavior_model": {"facts": [{"fact": pairs[0][1], "evidence_ids": ["E-PDF"]}]},
        "evidence_catalog": [{"id": "E-PDF", "note": pairs[0][1]}],
    }
    unavailable_advice = SimpleNamespace(
        candidates_for=lambda _pairs: [],
        discover=lambda _manifest, _pairs: {"candidates": [], "gaps": []},
    )
    original = deepcopy(manifest)
    # Deterministic offline test: no RAG, customer files, model, network, or Jira calls.
    with patch.object(dimension_synthesizer, "_load_feature_map", return_value=feature_map), \
            patch.object(dimension_synthesizer, "_load_offline_retrieval", return_value=None), \
            patch.object(dimension_synthesizer, "_load_sibling_module", return_value=unavailable_advice):
        result = dimension_synthesizer.synthesize(manifest)
        siblings = [item for item in result["candidates"]
                    if item.get("surface") == "NATIVE_PDF_CONTENT"]
        check("synthesizer carries Native PDF siblings without live or offline RAG",
              {item["feature"] for item in siblings} == {"Variables", "Variable Sets"}
              and all(item["hypothesis_id"].startswith("DS-") for item in siblings))
        check("synthesizer leaves the original manifest unchanged", manifest == original)
        notes = dimension_synthesizer.review_notes(manifest)
        check("both unrepresented siblings produce existing discovery review notes",
              all(any(f"feature={name}," in note for note in notes)
                  for name in ("Variables", "Variable Sets")))
        check("unavailable RAG is recorded instead of claimed as retrieved",
              any("RAG_NEIGHBORHOOD" in gap for gap in result["gaps"])
              and not any(item.get("source_label") == "OFFLINE_CHROMA" for item in siblings))

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        check("missing advisory map remains fail-open",
              _native_candidates(pairs, root / "absent.json") == [])
        malformed = root / "malformed.json"
        malformed.write_text("{broken", encoding="utf-8")
        check("malformed advisory map remains fail-open",
              _native_candidates(pairs, malformed) == [])
        unapproved = deepcopy(feature_map.load_map())
        surface = next(item for item in unapproved["surfaces"]
                       if item["surface"] == "NATIVE_PDF_CONTENT")
        for feature in surface["native_features"]:
            feature["approval_status"] = "MODEL_PROPOSED"
        path = root / "unapproved.json"
        path.write_text(json.dumps(unapproved), encoding="utf-8")
        check("unapproved Native PDF feature entries emit no candidates",
              _native_candidates(pairs, path) == [])
        check("strict curation audit rejects unapproved feature entries",
              bool(feature_map.validate_repository_map(path)))
    check("curated map passes strict governance", feature_map.validate_repository_map() == [])


if __name__ == "__main__":
    def check(name, result):
        if not result:
            raise AssertionError(name)
        print("PASS " + name)
    run_tests(check)
