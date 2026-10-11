"""Video attachments give the attachment researcher still frames and a speech
transcript; a missing tool or a failure records the exact reason, and other
attachments are untouched."""

from __future__ import annotations

import subprocess
import sys
import types

from app.services import agent_execution_provider as provider
from app.services.agent_execution_provider import _VIDEO_MAX_BYTES, _extract_video_evidence


def _entry(filename: str = "meeting.mp4", size: int = 1000, mime: str = "video/mp4") -> dict:
    return {"filename": filename, "mime_type": mime, "size_bytes": size}


def _no_whisper(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", None)


def test_non_video_attachment_is_untouched(tmp_path) -> None:
    entry = _entry("shot.png", mime="image/png")
    _extract_video_evidence(entry, tmp_path / "shot.png")
    assert "frame_paths" not in entry and "transcript_path" not in entry


def test_missing_tools_record_the_exact_reason(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(provider.shutil, "which", lambda name: None)
    _no_whisper(monkeypatch)
    entry = _entry()
    _extract_video_evidence(entry, tmp_path / "meeting.mp4")
    assert entry["frame_paths"] == []
    assert entry["frames_error"] == "ffmpeg is not installed on this machine"
    assert entry["transcript_path"] == ""
    assert entry["transcript_error"] == "faster-whisper is not installed on this machine"


def test_oversized_video_is_not_extracted(tmp_path) -> None:
    entry = _entry(size=_VIDEO_MAX_BYTES + 1)
    _extract_video_evidence(entry, tmp_path / "meeting.mp4")
    assert entry["frame_paths"] == [] and "oversized video" in entry["frames_error"]
    assert "oversized video" in entry["transcript_error"]


def test_frames_are_written_beside_the_video(tmp_path, monkeypatch) -> None:
    target = tmp_path / "meeting.mp4"
    target.write_bytes(b"video")
    monkeypatch.setattr(provider.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    _no_whisper(monkeypatch)

    def fake_run(command, **kwargs):
        frame_dir = tmp_path / "meeting.mp4.frames"
        for index in (1, 2):
            (frame_dir / f"frame_{index:03d}.jpg").write_bytes(b"jpg")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(provider.subprocess, "run", fake_run)
    entry = _entry(size=5)
    _extract_video_evidence(entry, target)
    assert entry["frames_error"] == ""
    assert [p.rsplit("frame_", 1)[1] for p in entry["frame_paths"]] == ["001.jpg", "002.jpg"]


def test_ffmpeg_failure_records_its_message(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(provider.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    _no_whisper(monkeypatch)
    monkeypatch.setattr(provider.subprocess, "run",
                        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "moov atom not found"))
    entry = _entry()
    _extract_video_evidence(entry, tmp_path / "meeting.mp4")
    assert entry["frame_paths"] == []
    assert entry["frames_error"] == "ffmpeg exit 1: moov atom not found"


def test_transcript_has_timestamps(tmp_path, monkeypatch) -> None:
    target = tmp_path / "meeting.mp4"
    target.write_bytes(b"video")
    monkeypatch.setattr(provider.shutil, "which", lambda name: None)

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, path, **kwargs):
            segments = [types.SimpleNamespace(start=5.2, text=" Rename the Japanese copy too. "),
                        types.SimpleNamespace(start=75.0, text="Move happens on the next translation.")]
            return iter(segments), None

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Model))
    entry = _entry(size=5)
    _extract_video_evidence(entry, target)
    assert entry["transcript_error"] == ""
    text = open(entry["transcript_path"], encoding="utf-8").read()
    assert text == "[00:05] Rename the Japanese copy too.\n[01:15] Move happens on the next translation."


def test_switches_turn_extraction_off(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UAC_VIDEO_FRAMES", "0")
    monkeypatch.setenv("UAC_VIDEO_TRANSCRIBE", "0")
    entry = _entry()
    _extract_video_evidence(entry, tmp_path / "meeting.mp4")
    assert "UAC_VIDEO_FRAMES=0" in entry["frames_error"]
    assert "UAC_VIDEO_TRANSCRIBE=0" in entry["transcript_error"]
