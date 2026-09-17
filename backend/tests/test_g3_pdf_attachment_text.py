"""G3: bounded PDF text materialization for the attachment researcher.

Accessible PDF Jira attachments expose bounded extracted text (real text
layer, no OCR) via ``text_path``; encrypted, corrupt, oversized, or
image-only files record the exact reason in ``text_error`` instead.  Non-PDF
attachments are untouched.
"""

from __future__ import annotations

import base64

from app.services.agent_execution_provider import (
    _PDF_MAX_BYTES,
    _extract_pdf_text,
)

# A one-page PDF with a real text layer (generated once with PyMuPDF and
# embedded as static bytes so the test needs only the declared pypdf
# dependency).
_TEXT_PDF_B64 = (
    "JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjkuMAoKMSAwIG9iago8PC9UeXBlL0NhdGFs"
    "b2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjkuMCk+Pj4+CmVuZG9iagoKMiAwIG9i"
    "ago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDwvRm9udDw8"
    "L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKNCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDU5NSA4"
    "NDJdL1JvdGF0ZSAwL1Jlc291cmNlcyAzIDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbNiAwIFJdPj4KZW5k"
    "b2JqCgo1IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYS9FbmNv"
    "ZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKCjYgMCBvYmoKPDwvTGVuZ3RoIDEzMS9GaWx0ZXIvRmxh"
    "dGVEZWNvZGU+PgpzdHJlYW0KeNoljLEKQjEMRfd8Rf7AJm3vfQ/EQXBxE7qJg0iLgw4ufr/pMxnCvZwT+cix"
    "iWmKNaWruWt7y+7ZX1810zb0uq+FDsOcFdkTHnGJhYUzAYPuiSmogYzKzBxEB/N96yt8OtEumz3A6AkLo//J"
    "yCXM+LkRxjWSez/c2llOTS7yA9FuJnwKZW5kc3RyZWFtCmVuZG9iagoKeHJlZgowIDcKMDAwMDAwMDAwMCA2"
    "NTUzNSBmIAowMDAwMDAwMDQyIDAwMDAwIG4gCjAwMDAwMDAxMjAgMDAwMDAgbiAKMDAwMDAwMDE3MiAwMDAw"
    "MCBuIAowMDAwMDAwMjEzIDAwMDAwIG4gCjAwMDAwMDAzMjAgMDAwMDAgbiAKMDAwMDAwMDQwOSAwMDAwMCBu"
    "IAoKdHJhaWxlcgo8PC9TaXplIDcvUm9vdCAxIDAgUi9JRFs8QzI5MDcxMzFDM0I1QzI5QjJCNzhDMzlCQzJB"
    "REMzQjQ+PDQ2NTE4Rjk5QkMxMkQ4Q0FDRERFNzE2OTlEMTI4OTdCPl0+PgpzdGFydHhyZWYKNjA5CiUlRU9G"
    "Cg=="
)


def _entry(filename: str, size: int) -> dict:
    return {
        "filename": filename,
        "mime_type": "application/pdf",
        "size_bytes": size,
    }


def test_pdf_text_layer_is_materialized(tmp_path) -> None:
    target = tmp_path / "slide.pdf"
    target.write_bytes(base64.b64decode(_TEXT_PDF_B64))
    entry = _entry("slide.pdf", target.stat().st_size)
    _extract_pdf_text(entry, target)
    assert entry["text_error"] == ""
    text_path = entry["text_path"]
    assert text_path
    text = open(text_path, encoding="utf-8").read()
    assert "Traffic lights for processing" in text


def test_oversized_pdf_records_the_exact_reason(tmp_path) -> None:
    target = tmp_path / "big.pdf"
    target.write_bytes(base64.b64decode(_TEXT_PDF_B64))
    entry = _entry("big.pdf", _PDF_MAX_BYTES + 1)
    _extract_pdf_text(entry, target)
    assert entry["text_path"] == ""
    assert "oversized PDF" in entry["text_error"]


def test_corrupt_pdf_records_the_exact_reason(tmp_path) -> None:
    target = tmp_path / "broken.pdf"
    target.write_bytes(b"%PDF-1.4 not a real pdf body")
    entry = _entry("broken.pdf", 28)
    _extract_pdf_text(entry, target)
    assert entry["text_path"] == ""
    assert "text extraction failed" in entry["text_error"]


def test_non_pdf_is_untouched(tmp_path) -> None:
    target = tmp_path / "shot.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\n")
    entry = {
        "filename": "shot.png",
        "mime_type": "image/png",
        "size_bytes": 8,
    }
    _extract_pdf_text(entry, target)
    assert "text_path" not in entry
    assert "text_error" not in entry
