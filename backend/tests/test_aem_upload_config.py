"""Tests for AEM upload properties config loader."""
from pathlib import Path

from app.core import aem_upload_config as cfg


def test_parse_properties_and_resolve(tmp_path, monkeypatch):
    config_file = tmp_path / "aem-upload.properties"
    config_file.write_text(
        "\n".join(
            [
                "# comment",
                "aem.base.url=https://author.example.com",
                "aem.username=qa-user",
                "aem.password=qa-pass",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AEM_UPLOAD_CONFIG", str(config_file))
    cfg.load_aem_upload_config.cache_clear()

    resolved = cfg.resolve_aem_upload_credentials()
    assert resolved["base_url"] == "https://author.example.com"
    assert resolved["username"] == "qa-user"
    assert resolved["password"] == "qa-pass"


def test_tool_args_override_properties_file(tmp_path, monkeypatch):
    config_file = tmp_path / "aem-upload.properties"
    config_file.write_text("aem.base.url=https://from-file.com\n", encoding="utf-8")
    monkeypatch.setenv("AEM_UPLOAD_CONFIG", str(config_file))
    cfg.load_aem_upload_config.cache_clear()

    resolved = cfg.resolve_aem_upload_credentials(aem_base_url="https://from-tool.com")
    assert resolved["base_url"] == "https://from-tool.com"


def test_default_config_path_points_to_project_config():
    path = cfg.get_config_path()
    assert path.name == "aem-upload.properties"
    assert path.parent.name == "config"
