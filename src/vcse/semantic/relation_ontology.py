"""Deterministic relation ontology mapping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RelationDefinition:
    canonical: str
    inverse: str | None


RELATION_MAP: dict[str, RelationDefinition] = {
    "has_capital": RelationDefinition("has_capital", "capital_of"),
    "capital_of": RelationDefinition("has_capital", "capital_of"),
}


def canonicalize_relation(rel: str) -> str:
    relation = rel.strip()
    if relation in RELATION_MAP:
        return RELATION_MAP[relation].canonical
    return relation
