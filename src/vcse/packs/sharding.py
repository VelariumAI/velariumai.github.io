"""Deterministic shard definitions and assignment for runtime claims."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ShardDefinition:
    shard_id: str
    domain: str
    pack_id: str
    relation_patterns: tuple[str, ...]
    description: str


SHARD_DEFINITIONS: tuple[ShardDefinition, ...] = (
    ShardDefinition("geography.capitals", "geography", "*", ("has_capital", "capital_of"), "Capital/country relations"),
    ShardDefinition(
        "geography.location",
        "geography",
        "*",
        ("located_in_country", "located_in_region", "located_in_subregion", "part_of"),
        "Location and containment relations",
    ),
    ShardDefinition("geography.currency", "geography", "*", ("uses_currency",), "Currency usage relations"),
    ShardDefinition("geography.language", "geography", "*", ("language_of",), "Language relations"),
    ShardDefinition("geography.codes", "geography", "*", ("has_country_code",), "Country code relations"),
    ShardDefinition("geography.borders", "geography", "*", ("shares_border_with",), "Border relations"),
    ShardDefinition("misc.unknown", "misc", "*", tuple(), "Fallback shard"),
)


_RELATION_TO_SHARD: dict[str, str] = {}
for _definition in SHARD_DEFINITIONS:
    for _relation in _definition.relation_patterns:
        _RELATION_TO_SHARD[_relation.lower()] = _definition.shard_id


def assign_shard(claim: dict[str, Any]) -> str:
    relation = str(claim.get("relation", "")).strip().lower()
    if not relation:
        return "misc.unknown"
    return _RELATION_TO_SHARD.get(relation, "misc.unknown")

