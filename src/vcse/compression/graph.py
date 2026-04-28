"""Graph-based relationship compression for claims."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphIndex:
    """
    Adjacency list representation of claim relationships.

    Each node (subject or object) maps to a list of (relation, counterpart) edges.
    Deduplicates edges — identical (relation, from, to) triplets stored once.
    """
    _edges: dict[str, set[tuple[str, str]]] = field(default_factory=lambda: defaultdict(set))

    def add_claim(self, subject: str, relation: str, obj: str) -> None:
        """Add a claim as a directed edge subject → object via relation."""
        self._edges[subject].add((relation, obj))

    def neighbors(self, node: str) -> list[tuple[str, str]]:
        """Get all (relation, target) edges for a node, sorted deterministically."""
        edges = self._edges.get(node, set())
        return sorted(edges)

    def nodes(self) -> list[str]:
        """Get all nodes, sorted."""
        return sorted(self._edges.keys())

    def edge_count(self) -> int:
        """Total number of unique edges."""
        return sum(len(s) for s in self._edges.values())

    def to_dict(self) -> dict[str, list[tuple[str, str]]]:
        """Serialize: node -> sorted (relation, target) list."""
        return {node: self.neighbors(node) for node in self.nodes()}

    @classmethod
    def from_dict(cls, data: dict[str, list[tuple[str, str]]]) -> "GraphIndex":
        """Deserialize."""
        inst = cls()
        for node, edges in data.items():
            for rel, tgt in edges:
                inst._edges[node].add((rel, tgt))
        return inst