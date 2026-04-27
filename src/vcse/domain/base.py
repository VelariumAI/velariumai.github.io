"""Base domain pack interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RelationSchema:
    """Schema for a relation type."""
    name: str
    transitive: bool = False
    symmetric: bool = False
    description: str = ""


@dataclass
class ProposerRule:
    """A rule for generating proposer transitions."""
    name: str
    description: str = ""
    enabled: bool = True


@dataclass
class VerifierRule:
    """A rule for verification."""
    name: str
    description: str = ""
    enabled: bool = True


@dataclass
class DomainPack:
    """A domain pack providing relations, synonyms, patterns, and rules."""
    name: str
    relation_schemas: list[RelationSchema] = field(default_factory=list)
    synonyms: dict[str, str] = field(default_factory=dict)
    patterns: list[str] = field(default_factory=list)
    proposer_rules: list[ProposerRule] = field(default_factory=list)
    verifier_rules: list[VerifierRule] = field(default_factory=list)
    benchmark_files: list[str] = field(default_factory=list)

    def get_relation(self, name: str) -> RelationSchema | None:
        """Get a relation schema by name."""
        for schema in self.relation_schemas:
            if schema.name == name:
                return schema
        return None

    def has_relation(self, name: str) -> bool:
        """Check if pack supports a relation."""
        return any(s.name == name for s in self.relation_schemas)
