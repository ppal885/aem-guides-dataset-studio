"""Tests for image_generation_service — DITA image extraction and generation."""
import pytest
from pathlib import Path
from app.services.image_generation_service import (
    extract_image_refs,
    _build_image_prompt,
    _strip_tags,
    generate_placeholder_image,
)


class TestExtractImageRefs:
    def test_simple_image(self):
        xml = '<topic><body><image href="images/screenshot.png"/></body></topic>'
        refs = extract_image_refs(xml)
        assert len(refs) == 1
        assert refs[0]["href"] == "images/screenshot.png"

    def test_image_with_alt(self):
        xml = '<topic><body><image href="img/dialog.png"><alt>Settings dialog</alt></image></body></topic>'
        refs = extract_image_refs(xml)
        assert len(refs) == 1
        assert refs[0]["href"] == "img/dialog.png"

    def test_fig_with_title_and_image(self):
        xml = """<topic><body>
            <fig>
                <title>Configuration panel</title>
                <image href="images/config.png"/>
            </fig>
        </body></topic>"""
        refs = extract_image_refs(xml)
        assert len(refs) == 1
        assert refs[0]["href"] == "images/config.png"
        assert refs[0]["fig_title"] == "Configuration panel"

    def test_multiple_images(self):
        xml = """<topic><body>
            <image href="img/step1.png"/>
            <image href="img/step2.png"/>
            <fig><title>Result</title><image href="img/result.png"/></fig>
        </body></topic>"""
        refs = extract_image_refs(xml)
        assert len(refs) == 3

    def test_no_images(self):
        xml = '<topic><body><p>No images here</p></body></topic>'
        refs = extract_image_refs(xml)
        assert len(refs) == 0

    def test_no_duplicate_from_fig(self):
        """Image inside fig should not appear twice."""
        xml = """<topic><body>
            <fig><title>Test</title><image href="img/test.png"/></fig>
        </body></topic>"""
        refs = extract_image_refs(xml)
        assert len(refs) == 1

    def test_self_closing_image(self):
        xml = '<image href="images/icon.svg" placement="inline"/>'
        refs = extract_image_refs(xml)
        assert len(refs) == 1
        assert refs[0]["href"] == "images/icon.svg"


class TestBuildImagePrompt:
    def test_with_fig_title(self):
        ref = {"fig_title": "Settings dialog", "alt_text": "", "context": ""}
        prompt = _build_image_prompt(ref)
        assert "Settings dialog" in prompt
        assert "technical" in prompt.lower()

    def test_with_alt_text(self):
        ref = {"fig_title": "", "alt_text": "User clicking save button", "context": ""}
        prompt = _build_image_prompt(ref)
        assert "save button" in prompt

    def test_with_context_only(self):
        ref = {"fig_title": "", "alt_text": "", "context": "Step 3: Configure the output preset"}
        prompt = _build_image_prompt(ref)
        assert "output preset" in prompt

    def test_empty_ref(self):
        ref = {"fig_title": "", "alt_text": "", "context": ""}
        prompt = _build_image_prompt(ref)
        assert "placeholder" in prompt.lower()

    def test_prompt_max_length(self):
        ref = {"fig_title": "x" * 2000, "alt_text": "", "context": ""}
        prompt = _build_image_prompt(ref)
        assert len(prompt) <= 1000


class TestStripTags:
    def test_simple(self):
        assert _strip_tags("<b>bold</b>") == "bold"

    def test_nested(self):
        assert _strip_tags("<p>Hello <b>world</b></p>") == "Hello world"

    def test_no_tags(self):
        assert _strip_tags("plain text") == "plain text"


class TestPlaceholderImage:
    def _make_temp_dir(self):
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="test_img_"))
        return d

    def test_generates_svg(self):
        tmp = self._make_temp_dir()
        try:
            output = tmp / "images" / "test.svg"
            result = generate_placeholder_image(output, "Test Image")
            assert Path(result).exists()
            content = Path(result).read_text()
            assert "<svg" in content
            assert "Test Image" in content
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_creates_parent_dirs(self):
        tmp = self._make_temp_dir()
        try:
            output = tmp / "deep" / "nested" / "dir" / "image.svg"
            generate_placeholder_image(output, "Nested")
            assert output.exists()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_escapes_special_chars(self):
        tmp = self._make_temp_dir()
        try:
            output = tmp / "test.svg"
            generate_placeholder_image(output, 'Image with <special> & "chars"')
            content = output.read_text()
            assert "&amp;" in content
            assert "&lt;" in content
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
