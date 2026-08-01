from pathlib import Path


def test_ask_dita_command_blocks_partial_grounding_overclaims():
    command_path = Path(__file__).resolve().parents[2] / ".claude" / "commands" / "aem-ask-dita-expert.md"
    command = command_path.read_text(encoding="utf-8")

    assert "confidence below `0.75`" in command
    assert "Not verified from current evidence; execute the fixture" in command
    assert "never emit `--keep-temp`" in command
    assert "Generation coverage and DITA-OT runtime semantics are separate" in command
