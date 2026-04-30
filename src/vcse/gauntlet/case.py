"""Gauntlet case schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vcse.gauntlet.errors import GauntletError


SUPPORTED_MODES = {"ask", "generate", "ingest"}
SUPPORTED_EXPECTED_STATUSES = {
    "VERIFIED",
    "INCONCLUSIVE",
    "CONTRADICTORY",
    "UNSATISFIABLE",
    "NEEDS_CLARIFICATION",
    "VERIFIED_ARTIFACT",
    "INCONCLUSIVE_ARTIFACT",
    "FAILED_ARTIFACT",
    "CONTRADICTORY_ARTIFACT",
}


@dataclass(frozen=True)
class GauntletCase:
    id: str
    category: str
    input: str | dict[str, Any]
    mode: str
    expected_status: str
    expected_answer: Any | None = None
    failure_if: list[str] = field(default_factory=list)
    constraints: dict[str, Any] | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any], source_ref: str) -> "GauntletCase":
        if not isinstance(payload, dict):
            raise GauntletError("INVALID_CASE", f"{source_ref}: case must be object")

        item = cls(
            id=str(payload.get("id", "")).strip(),
            category=str(payload.get("category", "")).strip(),
            input=payload.get("input"),
            mode=str(payload.get("mode", "")).strip(),
            expected_status=str(payload.get("expected_status", "")).strip(),
            expected_answer=payload.get("expected_answer"),
            failure_if=[str(item) for item in payload.get("failure_if", [])],
            constraints=(dict(payload.get("constraints")) if isinstance(payload.get("constraints"), dict) else None),
            notes=(str(payload.get("notes")) if payload.get("notes") is not None else None),
        )
        item.validate(source_ref)
        return item

    def validate(self, source_ref: str) -> None:
        if not self.id:
            raise GauntletError("INVALID_CASE", f"{source_ref}: id is required")
        if not self.category:
            raise GauntletError("INVALID_CASE", f"{source_ref}: category is required")
        if self.mode not in SUPPORTED_MODES:
            raise GauntletError(
                "INVALID_CASE",
                f"{source_ref}: unsupported mode {self.mode!r}",
            )
        if self.expected_status not in SUPPORTED_EXPECTED_STATUSES:
            raise GauntletError(
                "INVALID_CASE",
                f"{source_ref}: unsupported expected_status {self.expected_status!r}",
            )
        if not isinstance(self.input, (str, dict)):
            raise GauntletError(
                "INVALID_CASE",
                f"{source_ref}: input must be string or object",
            )
        invalid_failure_if = [item for item in self.failure_if if item not in SUPPORTED_EXPECTED_STATUSES]
        if invalid_failure_if:
            raise GauntletError(
                "INVALID_CASE",
                f"{source_ref}: invalid failure_if statuses {invalid_failure_if}",
            )
