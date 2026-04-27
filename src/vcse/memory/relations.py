"""Relation schema definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RelationSchema:
    """Typed metadata for a relation in world-state memory."""

    name: str
    symmetric: bool = False
    transitive: bool = False
    reflexive: bool = False
    functional: bool = False
    inverse: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("RelationSchema.name must be non-empty")

    @property
    def canonical_name(self) -> str:
        return self.name.strip()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.canonical_name,
            "symmetric": self.symmetric,
            "transitive": self.transitive,
            "reflexive": self.reflexive,
            "functional": self.functional,
            "inverse": self.inverse,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "RelationSchema":
        return cls(
            name=str(data["name"]),
            symmetric=bool(data.get("symmetric", False)),
            transitive=bool(data.get("transitive", False)),
            reflexive=bool(data.get("reflexive", False)),
            functional=bool(data.get("functional", False)),
            inverse=str(data["inverse"]) if data.get("inverse") is not None else None,
        )
