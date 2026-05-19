"""UAC strict validation, parity analysis, and payload repair helpers."""

from services.uac.uac_output_parity import build_output_parity
from services.uac.historical_learning_service import extract_learning
from services.uac.anti_repetition_service import (
    AntiRepetitionMeta,
    apply_anti_repetition,
    finalize_payload_with_anti_repetition,
)
from services.uac.claim_verifier import UacEvidenceStore, verify_uac_claims
from services.uac.uac_decision_record_service import build_uac_decision_record
from services.uac.uac_guardrails import check_uac_guardrails
from services.uac.uac_output_validator import (
    apply_strict_uac_validation,
    apply_sync_validation_only,
    normalize_uac_payload_partial,
    repair_uac_payload_via_llm,
    validate_uac_payload,
)

__all__ = [
    "AntiRepetitionMeta",
    "UacEvidenceStore",
    "apply_anti_repetition",
    "finalize_payload_with_anti_repetition",
    "verify_uac_claims",
    "apply_strict_uac_validation",
    "apply_sync_validation_only",
    "build_output_parity",
    "build_uac_decision_record",
    "check_uac_guardrails",
    "extract_learning",
    "normalize_uac_payload_partial",
    "repair_uac_payload_via_llm",
    "validate_uac_payload",
]
