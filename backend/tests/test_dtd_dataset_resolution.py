"""Tests for global DTD path normalization."""

from app.generator.dtd_dataset_resolution import ensure_dataset_dtd_resolution
from app.generator.specialized import generate_task_topics_dataset
from types import SimpleNamespace


def test_ensure_dataset_dtd_resolution_fixes_reference_public_id_when_topic_id_was_wrong():
    """<reference> must not keep -//OASIS//DTD DITA Topic//EN or validators load topic grammar."""
    base = "content/dam/dataset-studio"
    nested = f"{base}/topics/references/properties_tables/properties_ref_00001.dita"
    bad = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Topic//EN" "../../../technicalContent/dtd/reference.dtd">
<reference id="t1" xml:lang="en"><title>T</title><shortdesc>S</shortdesc><refbody><refsyn><p>x</p></refsyn></refbody></reference>
"""
    files = {nested: bad}
    ensure_dataset_dtd_resolution(files, base)
    text = files[nested].decode("utf-8")
    assert "DITA Reference//EN" in text
    assert "DITA Topic//EN" not in text


def test_ensure_dataset_dtd_resolution_fixes_nested_topic_path():
    cfg = SimpleNamespace(
        seed="s",
        windows_safe_filenames=True,
        doctype_topic=(
            '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">'
        ),
        doctype_map='<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
    )
    base = "content/dam/dataset-studio"
    files = generate_task_topics_dataset(
        cfg,
        base,
        topic_count=2,
        steps_per_task=2,
        include_map=True,
    )
    ensure_dataset_dtd_resolution(files, base)

    stub = f"{base}/technicalContent/dtd/task.dtd"
    assert stub in files

    tpath = f"{base}/topics/tasks/task_00001.dita"
    text = files[tpath].decode("utf-8")
    assert "technicalContent/dtd/task.dtd" in text
    assert text.split("<task", 1)[0].count("technicalContent/dtd/task.dtd") == 1
