"""
Modular screenshot + reference DITA topic generation.

Public entry: :class:`TopicGenerationOrchestrator` (wired from ``dita_authoring_pipeline``).
"""

from app.services.topic_generation.dita_serializer_service import DitaSerializerService
from app.services.topic_generation.dita_style_profile_builder import DitaStyleProfileBuilder
from app.services.topic_generation.dita_validation_service import DitaValidationService
from app.services.topic_generation.reference_dita_analyzer import ReferenceDitaAnalyzer
from app.services.topic_generation.screenshot_understanding_service import ScreenshotUnderstandingService
from app.services.topic_generation.structured_topic_draft_builder import StructuredTopicDraftBuilder
from app.services.topic_generation.topic_generation_orchestrator import TopicGenerationOrchestrator
from app.services.topic_generation.topic_type_inference_service import TopicTypeInferenceService

__all__ = [
    "DitaSerializerService",
    "DitaStyleProfileBuilder",
    "DitaValidationService",
    "ReferenceDitaAnalyzer",
    "ScreenshotUnderstandingService",
    "StructuredTopicDraftBuilder",
    "TopicGenerationOrchestrator",
    "TopicTypeInferenceService",
]
