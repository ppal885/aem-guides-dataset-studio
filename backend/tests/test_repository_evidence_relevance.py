"""Regression tests for relevance-ranked repository evidence selection.

The scanner previously broke out of the directory walk as soon as it had
collected its match budget, so the retained "current implementation evidence"
was whichever files came first in directory order rather than the files that
actually matched the ticket.  These tests pin the selection contract.
"""

from __future__ import annotations

import pytest

from app.services.repository_evidence_service import (
    _MAX_MATCHES_PER_DIR,
    _build_query_plan,
    _derive_query_terms,
    _derive_subject_terms,
    _iter_text_files,
    _match_pattern,
    _query_specificity,
    _search_repo,
)


def _write(root, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _relative_paths(matches) -> list[str]:
    return [match["relative_path"] for match in matches]


class TestQuerySpecificity:
    def test_multi_word_phrase_outranks_single_token(self):
        assert _query_specificity("topic list") > _query_specificity("topic")

    def test_longer_token_outranks_shorter_token(self):
        assert _query_specificity("ordering") > _query_specificity("order")

    def test_path_like_query_outranks_plain_token_of_equal_length(self):
        assert _query_specificity("a/bcdefgh") > _query_specificity("abcdefghi")


class TestWholeWordMatching:
    @pytest.mark.parametrize(
        "text",
        ["a sitemap entry", "the mapping table", "roadmap planning"],
    )
    def test_generic_token_does_not_match_inside_another_word(self, text):
        assert _match_pattern("map").search(text) is None

    @pytest.mark.parametrize(
        "text",
        ["load the map", "map.get(key)", "a map, then a topic"],
    )
    def test_generic_token_still_matches_the_real_word(self, text):
        assert _match_pattern("map").search(text) is not None

    def test_path_like_query_matches(self):
        assert _match_pattern("/bin/export").search("post to /bin/export now")


class TestRelevanceOverWalkOrder:
    def test_specific_match_is_retained_over_alphabetically_earlier_generic_match(
        self, tmp_path
    ):
        # 'aaa_readme' sorts first and matches only the generic token; the
        # genuinely relevant file sorts last.  The old walk-order break kept
        # the readme and never reached the relevant file.
        for index in range(40):
            _write(tmp_path, f"aaa_{index:02d}/notes.md", "a report of the work")
        _write(tmp_path, "zzz/reports_panel.py", 'LABEL = "Topic List"')

        matches = _search_repo(
            tmp_path,
            ["topic list", "report"],
            repo_id="repo",
            max_matches=5,
        )

        assert "zzz/reports_panel.py" in _relative_paths(matches)
        assert matches[0]["relative_path"] == "zzz/reports_panel.py"
        assert matches[0]["matched_query"] == "topic list"

    def test_file_is_attributed_to_its_most_specific_query(self, tmp_path):
        _write(tmp_path, "src/panel.py", "the topic list report renders here")

        matches = _search_repo(
            tmp_path, ["report", "topic list"], repo_id="repo", max_matches=5
        )

        assert matches[0]["matched_query"] == "topic list"

    def test_selection_is_deterministic(self, tmp_path):
        for index in range(12):
            _write(tmp_path, f"src{index}/file.py", "a report here")

        first = _relative_paths(
            _search_repo(tmp_path, ["report"], repo_id="repo", max_matches=6)
        )
        second = _relative_paths(
            _search_repo(tmp_path, ["report"], repo_id="repo", max_matches=6)
        )

        assert first == second


class TestEvidenceDiversity:
    def test_one_directory_cannot_consume_the_budget(self, tmp_path):
        for index in range(30):
            _write(tmp_path, f"crowded/run_{index:02d}.json", '{"name": "report"}')
        _write(tmp_path, "src/panel.py", "a report panel")
        _write(tmp_path, "lib/helper.py", "another report helper")

        matches = _search_repo(tmp_path, ["report"], repo_id="repo", max_matches=6)
        paths = _relative_paths(matches)

        crowded = [path for path in paths if path.startswith("crowded/")]
        assert len(crowded) <= _MAX_MATCHES_PER_DIR
        assert "src/panel.py" in paths
        assert "lib/helper.py" in paths

    def test_crowded_directory_is_not_capped_when_it_is_the_only_source(
        self, tmp_path
    ):
        # Diversity must not cost evidence when diversity is impossible.
        for index in range(10):
            _write(tmp_path, f"only/file_{index:02d}.py", "a report here")

        matches = _search_repo(tmp_path, ["report"], repo_id="repo", max_matches=6)

        assert len(matches) == 6


class TestGeneratedOutputExclusion:
    @pytest.mark.parametrize(
        "relative",
        [
            "result/run/case.json",
            "test-results/case.json",
            "allure-results/case.json",
            "coverage/report.json",
            "logs/run.json",
        ],
    )
    def test_generated_output_is_not_scanned(self, tmp_path, relative):
        _write(tmp_path, relative, "a report")

        assert list(_iter_text_files(tmp_path)) == []

    def test_hidden_directories_are_not_scanned(self, tmp_path):
        _write(tmp_path, ".agent/skills/guide.md", "a report")
        _write(tmp_path, "src/panel.py", "a report")

        assert _relative_paths(
            _search_repo(tmp_path, ["report"], repo_id="repo", max_matches=5)
        ) == ["src/panel.py"]

    def test_source_beside_generated_output_is_still_scanned(self, tmp_path):
        _write(tmp_path, "result/run/case.json", "a report")
        _write(tmp_path, "src/panel.py", "a report")

        assert _relative_paths(
            _search_repo(tmp_path, ["report"], repo_id="repo", max_matches=5)
        ) == ["src/panel.py"]

    def test_a_clone_living_under_an_excluded_directory_is_still_scanned(
        self, tmp_path
    ):
        # A clone checked out beneath `.cache`, `build`, or similar must not be
        # excluded wholesale; only directories inside the repository count.
        for parent in (".cache", "build", "target"):
            root = tmp_path / parent / "repo"
            _write(root, "src/panel.py", "a report")

            assert _relative_paths(
                _search_repo(root, ["report"], repo_id="repo", max_matches=5)
            ) == ["src/panel.py"]


class TestSymbolsDescribeTheMatch:
    def test_symbols_come_from_around_the_matched_line(self, tmp_path):
        body = "\n".join(
            ["def unrelated_symbol_at_top(): ..."]
            + ["filler"] * 200
            + ["def renders_topic_list(): ...", "the topic list lives here"]
        )
        _write(tmp_path, "src/panel.py", body)

        matches = _search_repo(
            tmp_path, ["topic list"], repo_id="repo", max_matches=5
        )
        symbols = matches[0]["symbols"]

        assert "renders_topic_list" in symbols
        assert "unrelated_symbol_at_top" not in symbols


class TestSubjectTermDerivation:
    """Every ticket must contribute its own searchable vocabulary.

    Query derivation previously recognised only a fixed ladder of historical
    scenarios, so any ticket outside that ladder produced no subject terms and
    its evidence was chosen by ticket-independent seeds.
    """

    def test_ui_label_is_derived_as_a_phrase(self):
        terms = _derive_subject_terms("New Reports UI - Topic List (and export CSV)")

        assert "Topic List" in terms

    def test_phrases_are_ranked_before_bare_words(self):
        terms = _derive_subject_terms("New Reports UI - Topic List")

        assert terms.index("Topic List") < terms.index("Reports")

    def test_stopwords_do_not_become_queries(self):
        terms = [term.lower() for term in _derive_subject_terms("the order of that map")]

        assert "the" not in terms
        assert "that" not in terms

    def test_terms_are_deduplicated_case_insensitively(self):
        terms = [term.lower() for term in _derive_subject_terms("Report report REPORT")]

        assert terms.count("report") == 1

    def test_empty_text_derives_nothing(self):
        assert _derive_subject_terms("   ") == []

    @pytest.mark.parametrize(
        "summary",
        [
            "Need a way to view list of topics in same order as they are in map",
            "Publishing preset does not honour the selected output folder",
            "Baseline Panel shows stale entries after a version revert",
        ],
    )
    def test_arbitrary_ticket_wording_still_derives_terms(self, summary):
        # The point of the fix: derivation is not limited to known scenarios.
        assert _derive_subject_terms(summary)

    def test_derivation_is_reachable_through_the_public_query_builder(self):
        terms = _derive_query_terms("New Reports UI - Topic List (and export CSV)")

        assert "Topic List" in terms

    def test_existing_scenario_ladder_still_contributes(self):
        terms = _derive_query_terms("broken links report is empty")

        assert "Broken Links Report" in terms


class TestDerivedTermsSelectRelevantEvidence:
    def test_ticket_vocabulary_reaches_the_matching_file(self, tmp_path):
        _write(tmp_path, "src/unrelated.py", "preset and folder profile handling")
        _write(tmp_path, "src/reports_panel.py", 'LABEL = "Topic List"')

        terms = _derive_subject_terms("New Reports UI - Topic List (and export CSV)")
        matches = _search_repo(tmp_path, terms, repo_id="repo", max_matches=5)

        assert matches[0]["relative_path"] == "src/reports_panel.py"


class TestSubjectProvenanceOutranksGenericVocabulary:
    """The defect this guards: configured focus queries are identical for every
    ticket, so without a provenance tier they crowd the issue's own subject out
    of the evidence budget even when the subject matches exactly."""

    def _tree(self, tmp_path):
        # A realistic shape: generic product vocabulary is everywhere, the
        # ticket's actual subject appears in exactly one place.
        for index in range(40):
            _write(
                tmp_path,
                f"tests/publishing_{index}/case_{index}.py",
                "output preset and folder profile publishing",
            )
        _write(tmp_path, "pages/panels/reports_panel.py", 'LABEL = "Topic List"')

    def test_subject_match_wins_against_longer_generic_phrase(self, tmp_path):
        self._tree(tmp_path)
        queries = ["output preset and folder profile publishing", "Topic List"]

        without_tier = _search_repo(
            tmp_path, queries, repo_id="repo", max_matches=10
        )
        with_tier = _search_repo(
            tmp_path,
            queries,
            repo_id="repo",
            max_matches=10,
            subject_queries=frozenset({"Topic List"}),
        )

        # The generic phrase is longer, so raw specificity alone ranks it first.
        assert without_tier[0]["relative_path"] != "pages/panels/reports_panel.py"
        assert with_tier[0]["relative_path"] == "pages/panels/reports_panel.py"

    def test_generic_evidence_is_excluded_when_the_subject_matches(self, tmp_path):
        self._tree(tmp_path)

        matches = _search_repo(
            tmp_path,
            ["output preset and folder profile publishing", "Topic List"],
            repo_id="repo",
            max_matches=10,
            subject_queries=frozenset({"Topic List"}),
        )

        assert _relative_paths(matches) == ["pages/panels/reports_panel.py"]

    def test_repo_without_subject_match_reports_no_implementation_evidence(self, tmp_path):
        # A clone that contains none of the subject terms must not yield a
        # generic match from another feature.
        _write(tmp_path, "src/publish.py", "output preset handling")

        matches = _search_repo(
            tmp_path,
            ["output preset", "Topic List"],
            repo_id="repo",
            max_matches=5,
            subject_queries=frozenset({"Topic List"}),
        )

        assert matches == []


class TestQueryPlanProvenance:
    def test_issue_terms_are_marked_and_config_terms_are_not(self):
        queries, subject = _build_query_plan(
            {"summary": "New Reports UI - Topic List (and export CSV)"},
            {},
            {"focus_queries": ["output preset", "folder profile"]},
        )

        assert "Topic List" in subject
        assert "output preset" not in subject
        assert "folder profile" not in subject
        assert "output preset" in queries

    def test_subject_only_contains_queries_that_survived_the_cap(self):
        queries, subject = _build_query_plan(
            {"summary": "New Reports UI - Topic List (and export CSV)"},
            {},
            {"focus_queries": [f"configured focus query {i}" for i in range(60)]},
        )

        assert len(queries) == 40
        # Anything dropped by the cap must not be reported as a subject query.
        assert subject <= set(queries)

    def test_build_queries_still_returns_a_plain_list(self):
        queries = _build_query_plan(
            {"summary": "Topic List"}, {}, {"focus_queries": ["preset"]}
        )[0]

        assert isinstance(queries, list)
        assert all(isinstance(query, str) for query in queries)

    def test_planning_seeds_do_not_widen_ticket_repository_search(self):
        queries, _ = _build_query_plan(
            {"summary": "Topic List report columns"},
            {
                "features": ["publishing"],
                "outputs": ["Native PDF"],
                "regression_risk_seed": [
                    {"surface": "output preset", "risk": "DITA-OT"}
                ],
            },
            {"focus_queries": ["Topic List report columns"]},
        )

        assert "publishing" not in queries
        assert "Native PDF" not in queries
        assert "output preset" not in queries
        assert "DITA-OT" not in queries


class TestNoMatchesContract:
    def test_absent_query_returns_no_evidence(self, tmp_path):
        _write(tmp_path, "src/panel.py", "unrelated content")

        assert _search_repo(
            tmp_path, ["topic list"], repo_id="repo", max_matches=5
        ) == []

    def test_short_queries_are_ignored(self, tmp_path):
        _write(tmp_path, "src/panel.py", "a b c")

        assert _search_repo(tmp_path, ["a", "b"], repo_id="repo", max_matches=5) == []
