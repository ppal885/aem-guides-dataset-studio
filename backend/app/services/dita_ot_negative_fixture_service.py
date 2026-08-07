"""Deterministic negative DITA-OT fixtures requested by publishing prompts."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path


_NEGATIVE_REQUEST = re.compile(
    r"\b(negative|invalid|broken|missing|dangling|unresolved|conflict(?:ing)?|collision|duplicate)\b",
    re.I,
)


@dataclass(frozen=True)
class NegativeFixture:
    fixture_id: str
    map_path: Path
    expected_signal: str
    purpose: str


def wants_negative_fixtures(prompt: str) -> bool:
    return bool(_NEGATIVE_REQUEST.search(prompt or ""))


def _topic(topic_id: str, title: str, body: str) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="{topic_id}" xml:lang="en-US">
  <title>{title}</title>
  <body>{body}</body>
</topic>
'''


def _map(title: str, entries: str) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map id="negative-fixture" xml:lang="en-US">
  <title>{title}</title>
{entries}
</map>
'''


def write_negative_fixtures(work_dir: Path, prompt: str) -> list[NegativeFixture]:
    if not wants_negative_fixtures(prompt):
        return []

    root = work_dir / "negative-cases"
    root.mkdir(parents=True, exist_ok=True)
    fixtures: list[NegativeFixture] = []

    def add(
        fixture_id: str,
        map_text: str,
        files: dict[str, str | bytes],
        expected_signal: str,
        purpose: str,
    ) -> None:
        case_dir = root / fixture_id
        case_dir.mkdir(parents=True, exist_ok=True)
        map_path = case_dir / "root.ditamap"
        map_path.write_text(map_text, encoding="utf-8")
        for relative_path, content in files.items():
            path = case_dir / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
        fixtures.append(NegativeFixture(fixture_id, map_path, expected_signal, purpose))

    shared_topic = _topic(
        "shared",
        "Shared copy-to source",
        '<p id="shared-marker">Shared source marker for duplicate and collision checks.</p>',
    )
    add(
        "duplicate-reference",
        _map(
            "Duplicate reference control",
            '  <topicref href="shared.dita"/>\n  <topicref href="shared.dita"/>',
        ),
        {"shared.dita": shared_topic},
        "observe_duplicate_reference_output",
        "Observe whether two references to one physical topic are retained, collapsed, or warned about.",
    )
    add(
        "conflicting-copy-to",
        _map(
            "Conflicting copy-to targets",
            '  <topicref href="source-a.dita" copy-to="collision.dita"/>\n'
            '  <topicref href="source-b.dita" copy-to="collision.dita"/>',
        ),
        {
            "source-a.dita": _topic("source-a", "Collision source A", '<p id="marker-a">Marker A.</p>'),
            "source-b.dita": _topic("source-b", "Collision source B", '<p id="marker-b">Marker B.</p>'),
        },
        "warning_error_or_deterministic_winner",
        "Capture the processor response when two sources claim the same effective copy-to URI.",
    )
    add(
        "unresolved-keyref",
        _map("Unresolved keyref", '  <topicref href="consumer.dita"/>'),
        {
            "consumer.dita": _topic(
                "unresolved-keyref",
                "Unresolved key reference",
                '<p>Missing key value: <ph keyref="missing-product">fallback marker</ph>.</p>',
            )
        },
        "warning_error_or_fallback",
        "Capture unresolved-key diagnostics and whether fallback text survives.",
    )
    add(
        "dangling-conref",
        _map("Dangling conref", '  <topicref href="consumer.dita"/>'),
        {
            "consumer.dita": _topic(
                "dangling-conref",
                "Dangling conref target",
                '<p conref="missing-source.dita#missing-topic/missing-element">Fallback conref marker.</p>',
            )
        },
        "warning_or_error",
        "Capture diagnostics for a conref whose source file and element do not exist.",
    )
    add(
        "broken-relative-xref",
        _map("Broken relative xref", '  <topicref href="consumer.dita"/>'),
        {
            "consumer.dita": _topic(
                "broken-relative-xref",
                "Broken relative link",
                '<p><xref href="missing/target.dita#target/section">Broken relative target</xref>.</p>',
            )
        },
        "warning_or_error",
        "Capture diagnostics and generated-link behavior for a missing relative DITA target.",
    )
    add(
        "missing-image",
        _map("Missing image", '  <topicref href="image-topic.dita"/>'),
        {
            "image-topic.dita": _topic(
                "missing-image",
                "Missing image target",
                '<p><image href="images/not-found.png"><alt>Missing image oracle</alt></image></p>',
            )
        },
        "warning_error_or_broken_output_reference",
        "Capture diagnostics and HTML behavior for a referenced image that is absent.",
    )
    add(
        "invalid-chunk-token",
        _map("Invalid chunk token", '  <topicref href="topic.dita" chunk="split to-navigation"/>'),
        {"topic.dita": _topic("invalid-chunk", "Invalid chunk value", "<p>Invalid chunk marker.</p>")},
        "validation_warning_error_or_ignored_token",
        "Capture validation and transformation behavior for non-standard chunk tokens.",
    )

    pixel = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    add(
        "nested-map-image-control",
        _map("Nested map and image control", '  <mapref href="submap.ditamap"/>'),
        {
            "submap.ditamap": _map("Nested submap", '  <topicref href="nested-topic.dita"/>'),
            "nested-topic.dita": _topic(
                "nested-map-image",
                "Nested map image control",
                '<p><image href="images/pixel.png"><alt>Valid image control</alt></image></p>',
            ),
            "images/pixel.png": pixel,
        },
        "successful_control",
        "Prove nested map resolution and valid binary-image copying beside the negative image case.",
    )
    return fixtures
