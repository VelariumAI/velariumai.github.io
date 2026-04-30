"""Capability pack selection based on symbolic overlap."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.index.index import CapabilityPackIndex


@dataclass(frozen=True)
class PackSelection:
    pack_id: str
    score: float


class PackSelector:
    def select(
        self,
        packs: list[CapabilityPackIndex],
        query_tokens: list[str],
        relation_hints: set[str],
        top_k: int = 5,
    ) -> list[PackSelection]:
        if top_k < 1:
            return []
        qset = set(query_tokens)
        selected: list[PackSelection] = []
        for pack in packs:
            token_overlap = len(qset & set(pack.tokens))
            relation_overlap = len(relation_hints & set(pack.relations))
            type_coverage = len(pack.artifact_types)
            if token_overlap == 0 and relation_overlap == 0:
                continue
            score = (
                token_overlap
                + (relation_overlap * 2.0)
                + min(1.0, type_coverage / 4.0)
                + (1.0 / max(1, pack.priority))
            )
            selected.append(PackSelection(pack_id=pack.pack_id, score=round(score, 8)))

        selected.sort(key=lambda item: (-item.score, item.pack_id))
        return selected[:top_k]
