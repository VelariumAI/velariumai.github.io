"""Deterministic shard definitions and assignment for runtime claims."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ShardDefinition:
    shard_id: str
    domain: str
    pack_id: str
    relation_patterns: tuple[str, ...]
    description: str


_FALLBACK_SHARD_DEFINITIONS: tuple[ShardDefinition, ...] = (
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


def _domain_spec_candidates() -> tuple[Path, ...]:
    return (
        Path("domains/geography.yaml"),
        Path(__file__).resolve().parents[3] / "domains" / "geography.yaml",
    )


def _load_shards_from_domain_spec() -> tuple[ShardDefinition, ...] | None:
    for candidate in _domain_spec_candidates():
        if not candidate.exists():
            continue
        try:
            payload = _load_spec_payload(candidate)
            domain_id = str(payload.get("domain_id", "geography"))
            shard_rules = payload.get("shard_rules", [])
            if not isinstance(shard_rules, list):
                return None
        except Exception:
            return None
        return tuple(
            ShardDefinition(
                shard_id=str(rule.get("shard_id", "")).strip(),
                domain=domain_id if str(rule.get("shard_id", "")).strip() != "misc.unknown" else "misc",
                pack_id="*",
                relation_patterns=tuple(str(v).strip() for v in rule.get("relations", [])),
                description=f"Domain spec shard ({domain_id})",
            )
            for rule in shard_rules
        )
    return None


def _load_spec_payload(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text())
    else:
        import yaml  # type: ignore[import-not-found]

        data = yaml.safe_load(path.read_text())
    return data if isinstance(data, dict) else {}


SHARD_DEFINITIONS: tuple[ShardDefinition, ...] = _load_shards_from_domain_spec() or _FALLBACK_SHARD_DEFINITIONS


def _build_relation_to_shard() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for definition in SHARD_DEFINITIONS:
        for relation in definition.relation_patterns:
            mapping[relation.lower()] = definition.shard_id
    return mapping


_RELATION_TO_SHARD = _build_relation_to_shard()


def assign_shard(claim: dict[str, Any]) -> str:
    relation = str(claim.get("relation", "")).strip().lower()
    if not relation:
        return "misc.unknown"
    return _RELATION_TO_SHARD.get(relation, "misc.unknown")
