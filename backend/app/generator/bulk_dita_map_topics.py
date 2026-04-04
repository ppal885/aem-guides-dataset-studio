"""Generate N simple DITA topics plus one root map with topicrefs (bulk scale testing).

Mirrors the standalone ``generate_dita_20k_dataset.py`` layout:
  ``{base}/dita_dataset_{count}/topics/topic_XXXXX.dita``
  ``{base}/dita_dataset_{count}/rootmap_{count}.ditamap``
  ``{base}/dita_dataset_{count}/README.txt`` (optional)

When ``include_local_dtd_stubs`` is True (default), emits ``technicalContent/dtd/topic.dtd`` and
``map.dtd`` and uses doctypes so topics under ``topics/`` resolve via ``../technicalContent/dtd/``.
"""

from __future__ import annotations

import random
import re
from typing import Any

from app.generator.dtd_stubs import BULK_MAP_TOPICS_MAP_DTD, BULK_MAP_TOPICS_TOPIC_DTD


def _rewrite_doctype_system(doctype_line: str, new_system_path: str) -> str:
    """Replace the SYSTEM literal in a PUBLIC doctype declaration."""
    s = doctype_line.strip()
    if not s:
        return ""
    return re.sub(
        r'(PUBLIC\s+"[^"]+"\s+)"[^"]*"',
        lambda m: f'{m.group(1)}"{new_system_path}"',
        s,
        count=1,
        flags=re.IGNORECASE,
    )


def _topic_xml(doctype: str, index: int) -> str:
    topic_id = f"topic_{index:05d}"
    title = f"Generated Topic {index:05d}"
    body = (
        f"This is generated DITA topic number {index:05d}. "
        "It is included in the root map for large-scale dataset testing."
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<topic id="{topic_id}">
  <title>{title}</title>
  <shortdesc>Auto-generated topic for bulk DITA dataset testing.</shortdesc>
  <body>
    <p>{body}</p>
  </body>
</topic>
"""


def _root_map_xml(doctype: str, count: int) -> str:
    lines = []
    for i in range(1, count + 1):
        href = f"topics/topic_{i:05d}.dita"
        navtitle = f"Generated Topic {i:05d}"
        lines.append(f'  <topicref href="{href}" navtitle="{navtitle}"/>')
    topicrefs_str = "\n".join(lines)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<map id="rootmap_{count}">
  <title>Root Map for Generated DITA Dataset</title>
  <topicmeta>
    <shortdesc>Root map that references {count} generated topics.</shortdesc>
  </topicmeta>
{topicrefs_str}
</map>
"""


def generate_bulk_dita_map_topics_dataset(
    dataset_config: Any,
    base: str,
    topic_count: int,
    *,
    include_readme: bool = True,
    pretty_print: bool = True,
    include_local_dtd_stubs: bool = True,
    rand: random.Random | None = None,
) -> dict[str, bytes]:
    """Build topic files, one root ditamap, optional README, and optional DTD stubs under the dataset folder."""
    _ = rand  # reserved for future variation
    base = (base or "dataset").strip("/")
    count = max(1, int(topic_count))
    folder = f"{base}/dita_dataset_{count}"

    raw_topic = (getattr(dataset_config, "doctype_topic", None) or "").strip()
    raw_map = (getattr(dataset_config, "doctype_map", None) or "").strip()

    if include_local_dtd_stubs:
        topic_doctype = (
            _rewrite_doctype_system(raw_topic, "../technicalContent/dtd/topic.dtd")
            if raw_topic
            else '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "../technicalContent/dtd/topic.dtd">'
        )
        map_doctype = (
            _rewrite_doctype_system(raw_map, "technicalContent/dtd/map.dtd")
            if raw_map
            else '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">'
        )
    else:
        topic_doctype = (
            _rewrite_doctype_system(raw_topic, "../topic.dtd")
            if raw_topic
            else '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "../topic.dtd">'
        )
        map_doctype = (
            _rewrite_doctype_system(raw_map, "map.dtd")
            if raw_map
            else '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">'
        )

    files: dict[str, bytes] = {}
    for i in range(1, count + 1):
        path = f"{folder}/topics/topic_{i:05d}.dita"
        xml = _topic_xml(topic_doctype, i)
        if not pretty_print:
            xml = "".join(line.strip() for line in xml.splitlines() if line.strip())
        files[path] = xml.encode("utf-8")

    map_path = f"{folder}/rootmap_{count}.ditamap"
    map_xml = _root_map_xml(map_doctype, count)
    if not pretty_print:
        map_xml = "".join(line.strip() for line in map_xml.splitlines() if line.strip())
    files[map_path] = map_xml.encode("utf-8")

    if include_local_dtd_stubs:
        files[f"{folder}/technicalContent/dtd/topic.dtd"] = BULK_MAP_TOPICS_TOPIC_DTD.encode("utf-8")
        files[f"{folder}/technicalContent/dtd/map.dtd"] = BULK_MAP_TOPICS_MAP_DTD.encode("utf-8")
    else:
        files[f"{folder}/topic.dtd"] = BULK_MAP_TOPICS_TOPIC_DTD.encode("utf-8")
        files[f"{folder}/map.dtd"] = BULK_MAP_TOPICS_MAP_DTD.encode("utf-8")

    if include_readme:
        readme = "\n".join(
            [
                "DITA bulk dataset (Dataset Studio recipe: bulk_dita_map_topics)",
                "",
                f"Topics generated: {count}",
                f"Root map: rootmap_{count}.ditamap",
                "Topics folder: topics/",
                "",
                "All topic references are relative and valid within this dataset layout.",
            ]
        )
        if include_local_dtd_stubs:
            readme += "\n\nMinimal DITA DTD stubs: technicalContent/dtd/topic.dtd and map.dtd"
        else:
            readme += "\n\nMinimal DITA DTD stubs: topic.dtd and map.dtd at dataset root"
        files[f"{folder}/README.txt"] = readme.encode("utf-8")

    return files
