"""Deterministic semantic region utilities."""

from vcse.semantic.region import SemanticRegion
from vcse.semantic.relation_ontology import RELATION_MAP, RelationDefinition, canonicalize_relation
from vcse.semantic.region_builder import build_regions
from vcse.semantic.runtime_regions import RuntimeRegionIndex

__all__ = [
    "RELATION_MAP",
    "RelationDefinition",
    "SemanticRegion",
    "RuntimeRegionIndex",
    "build_regions",
    "canonicalize_relation",
]
