"""Re-export UAC evidence gate (``backend`` on path — see ``run_local.py``)."""

from __future__ import annotations

from app.services.uac_evidence_gate import (  # noqa: F401
    DroppedPoint,
    UacEvidenceGateResult,
    apply_uac_evidence_gate,
    is_generic_statement,
)

__all__ = [
    "DroppedPoint",
    "UacEvidenceGateResult",
    "apply_uac_evidence_gate",
    "is_generic_statement",
]
