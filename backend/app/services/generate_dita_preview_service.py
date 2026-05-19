"""Preview and execution-contract helpers for /generate_dita."""

from __future__ import annotations

from typing import Any

from app.services.dita_generation_contract_service import (
    build_dita_generation_contract,
    build_execution_contract,
)


def build_generate_dita_preview(
    *,
    text: str,
    instructions: str | None = None,
    screenshot_attached: bool = False,
    reference_attached: bool = False,
) -> dict[str, Any]:
    contract = build_dita_generation_contract(
        text=text,
        instructions=instructions,
        screenshot_attached=screenshot_attached,
        reference_attached=reference_attached,
    )
    return contract.model_dump(mode="json")


def build_generate_dita_execution_contract(*, preview: dict[str, Any]) -> dict[str, Any] | None:
    return build_execution_contract(preview)
