"""Network-free checks for article image extraction."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

from scripts import extract_ui_images


PAGE_URL = "https://experienceleague.adobe.com/en/docs/guides/article"
SVG_ICON = b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"></svg>'
PNG_SCREENSHOT = b"\x89PNG\r\n\x1a\n" + b"x" * 2100


def response(content: bytes, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=content, request=httpx.Request("GET", PAGE_URL))


class ExtractImagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.out = Path(self.temporary.name) / "images"

    @mock.patch("httpx.get")
    def test_all_images_includes_small_svg(self, get: mock.Mock) -> None:
        get.side_effect = [response(b'<img src="media_abc.svg">'), response(SVG_ICON)]

        saved = extract_ui_images.extract(PAGE_URL, self.out, 20, all_images=True)

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0][1].read_bytes(), SVG_ICON)

    @mock.patch("httpx.get")
    def test_all_images_overrides_twenty_image_limit(self, get: mock.Mock) -> None:
        refs = [f"media_{index:02x}.png" for index in range(25)]
        get.side_effect = [response(" ".join(refs).encode())] + [
            response(PNG_SCREENSHOT) for _ in refs
        ]

        saved = extract_ui_images.extract(PAGE_URL, self.out, 20, all_images=True)

        self.assertEqual(len(saved), 25)
        self.assertEqual(get.call_count, 26)
        self.assertTrue(all(path.is_file() for _, path in saved))

    @mock.patch("httpx.get")
    def test_default_keeps_size_filter_and_maximum(self, get: mock.Mock) -> None:
        refs = ["media_abc.svg"] + [f"media_{index:02x}.png" for index in range(25)]
        get.side_effect = [response(" ".join(refs).encode()), response(SVG_ICON),
                           response(SVG_ICON)] + [response(PNG_SCREENSHOT) for _ in range(20)]

        saved = extract_ui_images.extract(PAGE_URL, self.out, 20)

        self.assertEqual(len(saved), 20)
        self.assertTrue(all(path.suffix == ".png" for _, path in saved))
        self.assertEqual(get.call_count, 23)

    @mock.patch("httpx.get")
    def test_http_error_page_is_not_reported_as_no_images(self, get: mock.Mock) -> None:
        get.return_value = response(b"Service unavailable", 503)
        stdout, stderr = io.StringIO(), io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = extract_ui_images.main([PAGE_URL, "--out", str(self.out), "--all-images"])

        self.assertEqual(result, 1)
        self.assertIn("ERROR:", stderr.getvalue())
        self.assertNotIn("No images found", stdout.getvalue())
        self.assertFalse(self.out.exists())

    @mock.patch("httpx.get")
    def test_html_or_failed_media_response_is_not_saved(self, get: mock.Mock) -> None:
        html_error = b"<html><body>Unavailable</body></html>" + b" " * 2100
        get.side_effect = [response(b"media_abc.png"), response(html_error),
                           response(PNG_SCREENSHOT, 404)]

        with self.assertRaisesRegex(ValueError, "Incomplete extraction"):
            extract_ui_images.extract(PAGE_URL, self.out, 20, all_images=True)
        self.assertEqual(list(self.out.iterdir()), [])

    @mock.patch("httpx.get")
    def test_all_images_cli_fails_on_partial_download_and_preserves_success(self, get: mock.Mock) -> None:
        get.side_effect = [response(b"media_abc.png media_def.svg"),
                           response(PNG_SCREENSHOT), response(b"missing", 404),
                           response(b"missing", 404)]
        stdout, stderr = io.StringIO(), io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = extract_ui_images.main([PAGE_URL, "--out", str(self.out), "--all-images"])

        self.assertEqual(result, 1)
        self.assertIn("Incomplete extraction", stderr.getvalue())
        self.assertEqual((self.out / "00_media_abc.png").read_bytes(), PNG_SCREENSHOT)
        self.assertNotIn("No images found", stdout.getvalue())

    @mock.patch("httpx.get")
    def test_fallback_and_size_sorting_are_preserved(self, get: mock.Mock) -> None:
        larger_image = PNG_SCREENSHOT + b"larger"
        get.side_effect = [response(b"media_abc.png media_def.jpg"), response(b"missing", 404),
                           response(larger_image), response(b"\xff\xd8\xff" + b"x" * 2100)]

        saved = extract_ui_images.extract(PAGE_URL, self.out, 20)

        self.assertEqual(len(saved), 2)
        self.assertGreater(saved[0][0], saved[1][0])
        self.assertEqual(get.call_args_list[2].args[0],
                         "https://experienceleague.adobe.com/docs/guides/media_abc.png")


if __name__ == "__main__":
    unittest.main()
