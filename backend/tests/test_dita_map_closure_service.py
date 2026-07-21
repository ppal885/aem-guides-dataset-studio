from pathlib import Path

from app.services.dita_map_closure_service import collect_map_closure, copy_map_closure_to_dir


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_collect_map_closure_excludes_peer_and_external(tmp_path: Path):
    root = tmp_path / "root.ditamap"
    included = tmp_path / "included.dita"
    nested = tmp_path / "nested.ditamap"
    nested_topic = tmp_path / "nested-topic.dita"
    peer_map = tmp_path / "peer.ditamap"
    external = tmp_path / "external.dita"
    noise = tmp_path / "noise.dita"

    _write(
        included,
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="included"><title>Included</title><body><p>ok</p></body></topic>""",
    )
    _write(
        nested_topic,
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="nested"><title>Nested</title><body><p>ok</p></body></topic>""",
    )
    _write(
        nested,
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map id="nested"><title>Nested</title><topicref href="{nested_topic.name}"/></map>""",
    )
    _write(
        peer_map,
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map id="peer"><title>Peer</title></map>""",
    )
    _write(
        external,
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="external"><title>External</title><body><p>ok</p></body></topic>""",
    )
    _write(
        noise,
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="noise"><title>Noise</title><body><p>noise</p></body></topic>""",
    )
    _write(
        root,
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map id="root">
  <title>Root</title>
  <topicref href="{included.name}"/>
  <topicref href="{nested.name}"/>
  <topicref href="{peer_map.name}" scope="peer" format="ditamap"/>
  <topicref href="https://example.com/{external.name}" scope="external" format="dita"/>
</map>""",
    )

    closure = {path.name for path in collect_map_closure(root)}

    assert "root.ditamap" in closure
    assert "included.dita" in closure
    assert "nested.ditamap" in closure
    assert "nested-topic.dita" in closure
    assert "peer.ditamap" not in closure
    assert "external.dita" not in closure
    assert "noise.dita" not in closure


def test_copy_map_closure_to_dir_only_copies_reachable_files(tmp_path: Path):
    root = tmp_path / "source" / "root.ditamap"
    topic = tmp_path / "source" / "topic-a.dita"
    noise = tmp_path / "source" / "noise.dita"
    dest = tmp_path / "dest"

    _write(
        topic,
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="a"><title>A</title><body><p>a</p></body></topic>""",
    )
    _write(
        noise,
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="noise"><title>Noise</title><body><p>noise</p></body></topic>""",
    )
    _write(
        root,
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map id="root"><title>Root</title><topicref href="{topic.name}"/></map>""",
    )

    copied = copy_map_closure_to_dir(root, dest)
    copied_names = {path.name for path in copied}

    assert copied_names == {"root.ditamap", "topic-a.dita"}
    assert not (dest / "noise.dita").exists()
