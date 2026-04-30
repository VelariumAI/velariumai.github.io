"""World-state memory primitives."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from copy import deepcopy
from pathlib import Path
from typing import Any

from vcse.memory.constraints import Constraint
from vcse.memory.relations import RelationSchema
from vcse.memory.serialization import JSONDict, PathLike


class TruthStatus(str, Enum):
    ASSERTED = "ASSERTED"
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    ASSUMED = "ASSUMED"
    UNKNOWN = "UNKNOWN"


@dataclass
class Claim:
    id: str
    subject: str
    relation: str
    object: str
    status: TruthStatus = TruthStatus.UNKNOWN
    qualifiers: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    source: str = "memory"

    @property
    def text(self) -> str:
        return f"{self.subject} {self.relation} {self.object}"


@dataclass
class Goal:
    id: str
    subject: str
    relation: str
    object: str

    @property
    def text(self) -> str:
        return f"{self.subject} {self.relation} {self.object}"


@dataclass
class Contradiction:
    id: str
    element_ids: list[str]
    reason: str
    severity: str = "high"

    def to_dict(self) -> JSONDict:
        return {
            "id": self.id,
            "element_ids": list(self.element_ids),
            "reason": self.reason,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "Contradiction":
        return cls(
            id=str(data["id"]),
            element_ids=[str(item) for item in data.get("element_ids", [])],
            reason=str(data["reason"]),
            severity=str(data.get("severity", "high")),
        )


def _norm(value: object) -> str:
    return " ".join(str(value).strip().split())


def _norm_qualifiers(qualifiers: dict[str, object] | None) -> tuple[tuple[str, str], ...]:
    if not qualifiers:
        return ()
    return tuple(sorted((_norm(key), _norm(value)) for key, value in qualifiers.items()))


def _qualifiers_dict(qualifiers: dict[str, object] | None) -> dict[str, str]:
    return {key: value for key, value in _norm_qualifiers(qualifiers)}


class WorldStateMemory:
    """Structured state substrate for verifier-centered reasoning."""

    def __init__(self) -> None:
        self.claims: dict[str, Claim] = {}
        self._claim_index: dict[tuple[str, str, str, tuple[tuple[str, str], ...]], str] = {}
        self.relation_schemas: dict[str, RelationSchema] = {}
        self.constraints: list[Constraint] = []
        self.symbol_bindings: dict[str, Any] = {}
        self.evidence: dict[str, list[dict[str, Any]]] = {}
        self.goals: list[Goal] = []
        self.contradictions: dict[str, list[Contradiction]] = {}
        self.version: int = 0
        self.parent_version: int | None = None
        self._next_claim_num: int = 1
        self._next_goal_num: int = 1
        self._next_contradiction_num: int = 1

    def clone(self) -> "WorldStateMemory":
        cloned = deepcopy(self)
        cloned.parent_version = self.version
        return cloned

    def canonical_claim_key(
        self,
        subject: object,
        relation: object,
        object_: object,
        qualifiers: dict[str, object] | None = None,
    ) -> tuple[str, str, str, tuple[tuple[str, str], ...]]:
        return (_norm(subject), _norm(relation), _norm(object_), _norm_qualifiers(qualifiers))

    def add_relation_schema(self, schema: RelationSchema) -> None:
        self.relation_schemas[schema.canonical_name] = schema
        self.version += 1

    def add_relation_schema_from_name(self, name: str, **properties: Any) -> None:
        self.add_relation_schema(RelationSchema(name=name, **properties))

    def get_relation_schema(self, relation: str) -> RelationSchema | None:
        return self.relation_schemas.get(_norm(relation))

    def add_claim(
        self,
        subject: object,
        relation: object,
        object_: object,
        status: TruthStatus = TruthStatus.UNKNOWN,
        qualifiers: dict[str, object] | None = None,
        dependencies: list[str] | None = None,
        source: str = "memory",
    ) -> str:
        key = self.canonical_claim_key(subject, relation, object_, qualifiers)
        existing = self._claim_index.get(key)
        if existing is not None:
            return existing

        if not isinstance(status, TruthStatus):
            status = TruthStatus(str(status))

        claim_id = f"claim:{self._next_claim_num}"
        self._next_claim_num += 1
        self.claims[claim_id] = Claim(
            id=claim_id,
            subject=key[0],
            relation=key[1],
            object=key[2],
            status=status,
            qualifiers=dict(key[3]),
            dependencies=list(dependencies or []),
            source=source,
        )
        self._claim_index[key] = claim_id
        self.version += 1
        return claim_id

    def find_claim(
        self,
        subject: object,
        relation: object,
        object_: object,
        qualifiers: dict[str, object] | None = None,
    ) -> Claim | None:
        claim_id = self._claim_index.get(
            self.canonical_claim_key(subject, relation, object_, qualifiers)
        )
        if claim_id is None:
            return None
        return self.claims[claim_id]

    def get_claim(self, claim_id: str) -> Claim | None:
        return self.claims.get(claim_id)

    def add_goal(self, subject: object, relation: object, object_: object) -> str:
        goal_id = f"goal:{self._next_goal_num}"
        self._next_goal_num += 1
        self.goals.append(
            Goal(id=goal_id, subject=_norm(subject), relation=_norm(relation), object=_norm(object_))
        )
        self.version += 1
        return goal_id

    def add_constraint(self, constraint: Constraint) -> None:
        self.constraints.append(constraint)
        self.version += 1

    def constraint_id_for_index(self, index: int) -> str:
        return f"constraint:{index + 1}"

    def update_truth_status(self, claim_id: str, status: TruthStatus) -> bool:
        claim = self.claims.get(claim_id)
        if claim is None:
            return False
        claim.status = status
        self.version += 1
        return True

    def bind_symbol(self, name: object, value: Any) -> str:
        symbol = _norm(name)
        self.symbol_bindings[symbol] = value
        self.version += 1
        return f"symbol:{symbol}"

    def add_evidence(self, target_id: str, content: object, source: str = "transition") -> str:
        entry = {"content": _norm(content), "source": _norm(source)}
        self.evidence.setdefault(target_id, []).append(entry)
        self.version += 1
        return f"evidence:{target_id}:{len(self.evidence[target_id])}"

    def record_contradiction(
        self,
        element_id: str,
        reason: str,
        related_element_ids: list[str] | None = None,
        severity: str = "high",
    ) -> str:
        element_ids = [element_id, *list(related_element_ids or [])]
        contradiction_id = f"contradiction:{self._next_contradiction_num}"
        self._next_contradiction_num += 1
        contradiction = Contradiction(
            id=contradiction_id,
            element_ids=element_ids,
            reason=reason,
            severity=severity,
        )
        for item in element_ids:
            self.contradictions.setdefault(item, []).append(contradiction)
        self.version += 1
        return contradiction_id

    def get_contradictions_for(self, element_id: str) -> list[Contradiction]:
        return list(self.contradictions.get(element_id, []))

    def has_contradiction_on_path(self, element_ids: list[str]) -> bool:
        return any(self.contradictions.get(element_id) for element_id in element_ids)

    def dependency_path_for_claim(self, claim_id: str) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []

        def visit(current_id: str) -> None:
            if current_id in seen:
                return
            seen.add(current_id)
            claim = self.claims.get(current_id)
            if claim is None:
                return
            for dependency_id in claim.dependencies:
                visit(dependency_id)
            ordered.append(current_id)

        visit(claim_id)
        return ordered

    def proof_trace_for_claim(self, claim_id: str) -> list[str]:
        return [self.claims[item].text for item in self.dependency_path_for_claim(claim_id)]

    def to_dict(self) -> JSONDict:
        unique_contradictions: dict[str, Contradiction] = {}
        for indexed in self.contradictions.values():
            for contradiction in indexed:
                unique_contradictions[contradiction.id] = contradiction

        return {
            "version": self.version,
            "parent_version": self.parent_version,
            "next_claim_num": self._next_claim_num,
            "next_goal_num": self._next_goal_num,
            "next_contradiction_num": self._next_contradiction_num,
            "relation_schemas": [
                schema.to_dict() for schema in self.relation_schemas.values()
            ],
            "claims": [
                {
                    "id": claim.id,
                    "subject": claim.subject,
                    "relation": claim.relation,
                    "object": claim.object,
                    "status": claim.status.value,
                    "qualifiers": dict(claim.qualifiers),
                    "dependencies": list(claim.dependencies),
                    "source": claim.source,
                }
                for claim in self.claims.values()
            ],
            "constraints": [constraint.to_dict() for constraint in self.constraints],
            "symbol_bindings": dict(self.symbol_bindings),
            "evidence": {
                target_id: [dict(entry) for entry in entries]
                for target_id, entries in self.evidence.items()
            },
            "goals": [
                {
                    "id": goal.id,
                    "subject": goal.subject,
                    "relation": goal.relation,
                    "object": goal.object,
                }
                for goal in self.goals
            ],
            "contradictions": [
                contradiction.to_dict() for contradiction in unique_contradictions.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "WorldStateMemory":
        state = cls()
        state.version = int(data.get("version", 0))
        raw_parent = data.get("parent_version")
        state.parent_version = int(raw_parent) if raw_parent is not None else None
        state._next_claim_num = int(data.get("next_claim_num", 1))
        state._next_goal_num = int(data.get("next_goal_num", 1))
        state._next_contradiction_num = int(data.get("next_contradiction_num", 1))

        for schema_data in data.get("relation_schemas", []):
            schema = RelationSchema.from_dict(schema_data)
            state.relation_schemas[schema.canonical_name] = schema

        for claim_data in data.get("claims", []):
            claim = Claim(
                id=str(claim_data["id"]),
                subject=str(claim_data["subject"]),
                relation=str(claim_data["relation"]),
                object=str(claim_data["object"]),
                status=TruthStatus(str(claim_data["status"])),
                qualifiers=_qualifiers_dict(claim_data.get("qualifiers", {})),
                dependencies=[str(item) for item in claim_data.get("dependencies", [])],
                source=str(claim_data.get("source", "memory")),
            )
            state.claims[claim.id] = claim
            state._claim_index[
                state.canonical_claim_key(
                    claim.subject, claim.relation, claim.object, claim.qualifiers
                )
            ] = claim.id

        state.constraints = [
            Constraint.from_dict(item) for item in data.get("constraints", [])
        ]
        state.symbol_bindings = dict(data.get("symbol_bindings", {}))
        state.evidence = {
            str(target_id): [dict(entry) for entry in entries]
            for target_id, entries in data.get("evidence", {}).items()
        }

        state.goals = [
            Goal(
                id=str(item["id"]),
                subject=str(item["subject"]),
                relation=str(item["relation"]),
                object=str(item["object"]),
            )
            for item in data.get("goals", [])
        ]

        for contradiction_data in data.get("contradictions", []):
            contradiction = Contradiction.from_dict(contradiction_data)
            for element_id in contradiction.element_ids:
                state.contradictions.setdefault(element_id, []).append(contradiction)

        return state

    def save_json(self, path: PathLike) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")

    @classmethod
    def load_json(cls, path: PathLike) -> "WorldStateMemory":
        return cls.from_dict(json.loads(Path(path).read_text()))
