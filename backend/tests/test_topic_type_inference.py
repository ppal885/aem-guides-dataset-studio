"""Tests for topic type inference from screenshot IR and reference profile."""

from app.core.schemas_chat_authoring import (
    ChatDitaGenerationOptions,
    ChatImageContext,
    ReferenceStyleProfile,
    ScreenshotContentModel,
)
from app.services.dita_topic_draft import infer_topic_type


def test_override_from_options():
    img = ChatImageContext(structured=ScreenshotContentModel())
    profile = ReferenceStyleProfile(root_local_name="concept")
    t = infer_topic_type(
        options=ChatDitaGenerationOptions(dita_type="task"),
        user_prompt="hello",
        image_context=img,
        profile=profile,
    )
    assert t == "task"


def test_prompt_keyword():
    img = ChatImageContext(structured=ScreenshotContentModel())
    t = infer_topic_type(
        options=ChatDitaGenerationOptions(),
        user_prompt="make a reference topic",
        image_context=img,
        profile=None,
    )
    assert t == "reference"


def test_numbered_steps_bias_task():
    img = ChatImageContext(
        structured=ScreenshotContentModel(numbered_steps=["a", "b", "c"]),
    )
    t = infer_topic_type(
        options=ChatDitaGenerationOptions(),
        user_prompt="document this",
        image_context=img,
        profile=None,
    )
    assert t == "task"


def test_reference_root_fallback():
    img = ChatImageContext(structured=ScreenshotContentModel())
    profile = ReferenceStyleProfile(root_local_name="reference")
    t = infer_topic_type(
        options=ChatDitaGenerationOptions(),
        user_prompt="document this",
        image_context=img,
        profile=profile,
    )
    assert t == "reference"
