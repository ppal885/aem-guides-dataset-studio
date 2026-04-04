from io import BytesIO
import zipfile

from app.services.github_dita_examples_service import (
    _iter_dita_files_from_zip,
    configured_github_dita_index_urls,
    parse_github_tree_url,
)


def _build_sample_zip() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "userguide-master/DITA/topics/intro.dita",
            """<?xml version="1.0" encoding="UTF-8"?>
<concept id="intro"><title>Introduction</title><conbody><p>Hello.</p></conbody></concept>""",
        )
        archive.writestr(
            "userguide-master/DITA/tasks/run-task.dita",
            """<?xml version="1.0" encoding="UTF-8"?>
<task id="run-task"><title>Run the task</title><taskbody><steps><step><cmd>Do it.</cmd></step></steps></taskbody></task>""",
        )
        archive.writestr(
            "userguide-master/DITA/maps/userguide.ditamap",
            """<?xml version="1.0" encoding="UTF-8"?>
<map id="guide-map"><title>User Guide</title></map>""",
        )
        archive.writestr("userguide-master/README.md", "# Not a DITA file")
    return buffer.getvalue()


def test_parse_github_tree_url_extracts_repo_branch_and_subtree():
    source = parse_github_tree_url("https://github.com/oxygenxml/userguide/tree/master/DITA")

    assert source.owner == "oxygenxml"
    assert source.repo == "userguide"
    assert source.branch == "master"
    assert source.subtree == "DITA"
    assert source.archive_url == "https://codeload.github.com/oxygenxml/userguide/zip/refs/heads/master"


def test_parse_github_blob_url_matches_tree_and_normalizes_to_tree_url():
    tree = parse_github_tree_url("https://github.com/oxygenxml/userguide/tree/master/DITA/dev_guide")
    blob = parse_github_tree_url("https://github.com/oxygenxml/userguide/blob/master/DITA/dev_guide")
    assert tree.subtree == blob.subtree == "DITA/dev_guide"
    assert "/tree/" in blob.source_url
    assert "blob" not in blob.source_url


def test_configured_urls_include_dev_guide_subtree():
    urls = configured_github_dita_index_urls()
    assert any("dev_guide" in u for u in urls)


def test_iter_dita_files_from_zip_filters_to_supported_subtree_files():
    dita_files = _iter_dita_files_from_zip(
        _build_sample_zip(),
        subtree="DITA",
        max_files=10,
        include_maps=True,
    )

    paths = {item.path for item in dita_files}
    topic_types = {item.path: item.topic_type for item in dita_files}

    assert "DITA/topics/intro.dita" in paths
    assert "DITA/tasks/run-task.dita" in paths
    assert "DITA/maps/userguide.ditamap" in paths
    assert len(dita_files) == 3
    assert topic_types["DITA/topics/intro.dita"] == "concept"
    assert topic_types["DITA/tasks/run-task.dita"] == "task"


def test_iter_dita_files_from_zip_can_exclude_maps():
    dita_files = _iter_dita_files_from_zip(
        _build_sample_zip(),
        subtree="DITA",
        max_files=10,
        include_maps=False,
    )

    paths = {item.path for item in dita_files}
    assert "DITA/maps/userguide.ditamap" not in paths
    assert len(dita_files) == 2
