"""Symbolic index structures."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from vcse.index.features import ArtifactFeatures


@dataclass(frozen=True)
class IndexedArtifact:
    artifact_id: str
    artifact_type: str
    source_bundle: str
    priority: int
    feature_vector: dict[str, int]
    relations: tuple[str, ...] = field(default_factory=tuple)
    domain_tags: tuple[str, ...] = field(default_factory=tuple)
    frame_types: tuple[str, ...] = field(default_factory=tuple)

    @property
    def length(self) -> int:
        return sum(self.feature_vector.values())


@dataclass(frozen=True)
class CapabilityPackIndex:
    pack_id: str
    tokens: tuple[str, ...]
    relations: tuple[str, ...]
    artifact_types: tuple[str, ...]
    priority: int = 100


@dataclass
class SymbolicIndex:
    artifacts: dict[str, IndexedArtifact] = field(default_factory=dict)
    inverted_index: dict[str, list[str]] = field(default_factory=dict)
    document_frequency: dict[str, int] = field(default_factory=dict)
    packs: dict[str, CapabilityPackIndex] = field(default_factory=dict)
    average_doc_length: float = 0.0

    def build(self, items: list[ArtifactFeatures]) -> None:
        artifacts: dict[str, IndexedArtifact] = {}
        posting_lists: dict[str, set[str]] = defaultdict(set)
        total_length = 0

        for item in items:
            indexed = IndexedArtifact(
                artifact_id=item.artifact_id,
                artifact_type=item.artifact_type,
                source_bundle=item.source_bundle,
                priority=item.priority,
                feature_vector=dict(item.token_freq),
                relations=tuple(item.relations),
                domain_tags=tuple(item.domain_tags),
                frame_types=tuple(item.frame_types),
            )
            artifacts[indexed.artifact_id] = indexed
            total_length += indexed.length
            for token in indexed.feature_vector:
                posting_lists[token].add(indexed.artifact_id)

        self.artifacts = artifacts
        self.inverted_index = {
            token: sorted(ids)
            for token, ids in sorted(posting_lists.items())
        }
        self.document_frequency = {
            token: len(ids)
            for token, ids in self.inverted_index.items()
        }
        count = len(self.artifacts)
        self.average_doc_length = total_length / count if count else 0.0

    def set_packs(self, packs: list[CapabilityPackIndex]) -> None:
        self.packs = {pack.pack_id: pack for pack in sorted(packs, key=lambda p: p.pack_id)}

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)

    @property
    def token_count(self) -> int:
        return len(self.inverted_index)

    @property
    def pack_count(self) -> int:
        return len(self.packs)

    def stats(self) -> dict[str, object]:
        return {
            "artifact_count": self.artifact_count,
            "token_count": self.token_count,
            "pack_count": self.pack_count,
            "average_doc_length": round(self.average_doc_length, 6),
        }
