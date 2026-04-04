from app.services.jira_client import _adf_to_plain_text


def test_adf_to_plain_text_handles_nested_comment_content():
    adf = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Hover state breaks in author mode."},
                    {
                        "type": "text",
                        "text": "See recording",
                        "marks": [{"type": "link", "attrs": {"href": "https://example.test/video"}}],
                    },
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Open the topic preview."}]}],
                    },
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Move the cursor away to clear the hover state."}]}],
                    },
                ],
            },
            {
                "type": "orderedList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Check CSS specificity."}]}],
                    }
                ],
            },
            {
                "type": "codeBlock",
                "content": [{"type": "text", "text": "console.log('hover')"}],
            },
        ],
    }

    text = _adf_to_plain_text(adf)

    assert "Hover state breaks in author mode." in text
    assert "See recording (https://example.test/video)" in text
    assert "- Open the topic preview." in text
    assert "- Move the cursor away to clear the hover state." in text
    assert "1. Check CSS specificity." in text
    assert "console.log('hover')" in text
