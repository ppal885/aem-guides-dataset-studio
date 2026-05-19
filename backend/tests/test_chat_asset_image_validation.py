"""Raster magic-byte checks for chat image uploads."""

import pytest
from fastapi import HTTPException

from app.services import chat_asset_service as mod


def test_validate_accepts_minimal_png():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    mod._validate_raster_image_bytes(png)


def test_validate_rejects_plain_text():
    with pytest.raises(HTTPException) as ei:
        mod._validate_raster_image_bytes(b"not an image file")
    assert ei.value.status_code == 400
