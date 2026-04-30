"""Deterministic state signatures for TS3."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from vcse.memory.world_state import WorldStateMemory


@dataclass(frozen=True)
class StateSignature:
    """Canonical memory-state signature."""

    value: str

    @classmethod
    def from_memory(cls, memory: WorldStateMemory) -> "StateSignature":
        payload = {
            "claims": sorted(
                (
                    claim.subject,
                    claim.relation,
                    claim.object,
                    claim.status.value,
                    tuple(sorted(claim.qualifiers.items())),
                    tuple(sorted(claim.dependencies)),
                )
                for claim in memory.claims.values()
            ),
            "constraints": sorted(
                (
                    constraint.kind,
                    constraint.target,
                    constraint.operator,
                    str(constraint.value),
                    constraint.description,
                )
                for constraint in memory.constraints
            ),
            "goals": sorted(
                (goal.subject, goal.relation, goal.object)
                for goal in memory.goals
            ),
            "contradictions": sorted(_canonical_contradictions(memory)),
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return cls(value=digest)


def _canonical_contradictions(memory: WorldStateMemory) -> list[tuple[str, str, tuple[str, ...]]]:
    unique: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for contradictions in memory.contradictions.values():
        for contradiction in contradictions:
            mapped = tuple(sorted(_canonical_element_id(memory, item) for item in contradiction.element_ids))
            unique[contradiction.id] = (contradiction.reason, contradiction.severity, mapped)
    return list(unique.values())


def _canonical_element_id(memory: WorldStateMemory, element_id: str) -> str:
    claim = memory.get_claim(element_id)
    if claim is None:
        return element_id
    return f"claim:{claim.subject}/{claim.relation}/{claim.object}/{claim.status.value}"
