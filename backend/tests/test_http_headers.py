"""Content-Disposition headers must stay latin-1-encodable for Starlette."""

from app.utils.http_headers import content_disposition


def test_content_disposition_ascii_only_is_latin1_safe():
    value = content_disposition("sample.zip")
    value.encode("latin-1")
    assert 'filename="sample.zip"' in value
    assert "filename*=UTF-8''sample.zip" in value


def test_content_disposition_en_dash_recipe_title_is_latin1_safe():
    # Matches curated_realtime_corpus recipe title (U+2013 en dash).
    name = "Curated realtime corpus (1–2 lakh topics).zip"
    value = content_disposition(name)
    value.encode("latin-1")  # must not raise
    assert "filename=" in value
    assert "filename*=UTF-8''" in value
    assert "%E2%80%93" in value  # UTF-8 encoding of U+2013
    # ASCII fallback must not contain the raw en dash.
    assert "–" not in value.split("filename*=", 1)[0]


def test_content_disposition_inline_and_path_separators():
    value = content_disposition("a/b\\c\".dita", disposition="inline")
    value.encode("latin-1")
    assert value.startswith("inline;")
    assert "/" not in value.split("filename*=", 1)[0]
    assert "\\" not in value.split("filename*=", 1)[0]
