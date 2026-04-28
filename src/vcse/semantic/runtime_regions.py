"""Runtime semantic region index."""

from __future__ import annotations

from collections import defaultdict

from vcse.knowledge.pack_model import KnowledgeClaim
from vcse.semantic.region import SemanticRegion
from vcse.semantic.region_builder import build_regions


class RuntimeRegionIndex:
    def __init__(self, claims: list[KnowledgeClaim]):
        self._regions = build_regions(claims)
        self._by_relation: dict[str, list[SemanticRegion]] = defaultdict(list)
        self._by_subject: dict[str, list[SemanticRegion]] = defaultdict(list)

        for region in self._regions:
            for relation in sorted(region.relations):
                self._by_relation[relation].append(region)
            for subject in sorted(region.subjects):
                self._by_subject[subject].append(region)

        for relation in list(self._by_relation.keys()):
            self._by_relation[relation] = sorted(self._by_relation[relation], key=lambda r: r.region_id)
        for subject in list(self._by_subject.keys()):
            self._by_subject[subject] = sorted(self._by_subject[subject], key=lambda r: r.region_id)

    @property
    def regions(self) -> list[SemanticRegion]:
        return list(self._regions)

    def get_region_by_relation(self, relation: str) -> SemanticRegion:
        relation_key = relation.strip()
        matches = self._by_relation.get(relation_key, [])
        if not matches:
            raise KeyError(f"region not found for relation: {relation_key}")
        return matches[0]

    def get_regions_for_subject(self, subject: str) -> list[SemanticRegion]:
        return list(self._by_subject.get(subject.strip(), []))
