"""Structured constraints stored in world-state memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VALID_OPERATORS = {">", ">=", "<", "<=", "==", "!="}


@dataclass(frozen=True)
class Constraint:
    kind: str
    target: str
    operator: str
    value: Any
    description: str = ""

    def __post_init__(self) -> None:
        if not self.kind or not self.kind.strip():
            raise ValueError("Constraint.kind must be non-empty")
        if not self.target or not self.target.strip():
            raise ValueError("Constraint.target must be non-empty")
        if self.operator not in VALID_OPERATORS:
            raise ValueError(f"Unsupported constraint operator: {self.operator}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.strip(),
            "target": self.target.strip(),
            "operator": self.operator,
            "value": self.value,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Constraint":
        return cls(
            kind=str(data["kind"]),
            target=str(data["target"]),
            operator=str(data["operator"]),
            value=data["value"],
            description=str(data.get("description", "")),
        )
